"""Test-pose export for the pose-match harness (Maya side).

For every animator control named in the manifest, each unlocked rotate /
translate channel and each exported custom attribute is nudged on its own
("probe" poses -- a behavioural probe of the rig), then a few seeded random
combinations of several controls are posed. For each pose the file records:

* the posed controls' world transforms and attribute values (the INPUT the
  animator gave), and
* every exported joint's world transform (the OUTPUT Maya's rig produced),

all converted to Unreal world axes and centimetres. Rotations are unit
quaternions [x, y, z, w] of the converted world frame. The rest pose is
pose 0. Unreal replays the inputs on the rebuilt Control Rig and compares
(rig_builder/pose_harness.py).

IK/FK limbs: a probe of an FK control is taken with its limb in FK, an IK
control's with the limb in IK; every pose records all switch values as
channels, so Unreal replays the same mode.

Usage: export() in export_rig_manifest.py writes <name>.poses.json next to
the FBX. To regenerate only the poses (no FBX export), in Maya:

    import export_test_poses; export_test_poses.export_from_scene()
"""

import json
import math
import os
import random

import maya.cmds as cmds

import export_rig_manifest as erm

POSES_SCHEMA_VERSION = 2   # 2: switch modes per pose, probe info, maya_motion
ROTATE_PROBE_DEGREES = 20.0
TRANSLATE_PROBE_CM = 5.0
RANDOM_POSES = 12
RANDOM_CONTROLS_PER_POSE = 4
RANDOM_SEED = 7

_ROTATE = ("rotateX", "rotateY", "rotateZ")
_TRANSLATE = ("translateX", "translateY", "translateZ")


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------

def _quat_from_basis(x_axis, y_axis, z_axis):
    m00, m10, m20 = x_axis
    m01, m11, m21 = y_axis
    m02, m12, m22 = z_axis
    trace = m00 + m11 + m22
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        q = ((m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s, 0.25 * s)
    elif m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2.0
        q = (0.25 * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s)
    elif m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2.0
        q = ((m01 + m10) / s, 0.25 * s, (m12 + m21) / s, (m02 - m20) / s)
    else:
        s = math.sqrt(1.0 + m22 - m00 - m11) * 2.0
        q = ((m02 + m20) / s, (m12 + m21) / s, 0.25 * s, (m10 - m01) / s)
    norm = math.sqrt(sum(c * c for c in q)) or 1.0
    return [round(c / norm, 6) for c in q]


def _orthonormal(x_axis, y_axis):
    def norm(v):
        length = math.sqrt(sum(c * c for c in v)) or 1.0
        return [c / length for c in v]

    def cross(a, b):
        return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]

    x_axis = norm(x_axis)
    z_axis = norm(cross(x_axis, y_axis))
    return x_axis, cross(z_axis, x_axis), z_axis


def world_state(node):
    """(position_cm_ue, quat_ue) of a node's world frame, Unreal convention."""
    axes = erm._world_axes_unreal(node)            # [P(X), P(Z), P(Y)] -- a proper basis
    x_axis, y_axis, z_axis = _orthonormal(axes[0], axes[1])
    # The frame's world origin (not the pivot): with it, pose x rest^-1 is the
    # exact rigid world delta even when pivots are moved. Queried with
    # -translation, NOT read from -matrix: the matrix answers in Maya's
    # internal cm while the unit scale below expects UI units (m scenes).
    position = cmds.xform(node, query=True, worldSpace=True, translation=True)
    return (
        [round(c, 4) for c in erm._maya_vector_to_unreal(position, apply_unit_scale=True)],
        _quat_from_basis(x_axis, y_axis, z_axis),
    )


# ---------------------------------------------------------------------------
# Controls and channels
# ---------------------------------------------------------------------------

def _records(value):
    if isinstance(value, dict):
        if value.get("dag_path") and value.get("name"):
            yield value
        for child in value.values():
            for item in _records(child):
                yield item
    elif isinstance(value, list):
        for child in value:
            for item in _records(child):
                yield item


def manifest_controls(manifest):
    """{ue_facing_name: maya_node} of every animator control in the manifest.

    The animator control is the shape holder when the record stands for one
    (spline influences sit under their control).
    """
    controls = {}
    for record in _records(manifest):
        maya_name = record.get("shape_source") or record.get("ue_control_name") or record.get("name")
        matches = cmds.ls(maya_name, long=True) or cmds.ls(record.get("dag_path"), long=True) or []
        if len(matches) != 1:
            continue
        node = matches[0]
        if not erm._has_controller_shape(node):
            continue
        controls.setdefault(erm._short_node_name(node), node)
    return controls


def _depth(node):
    return node.count("|")


def _channels(node, record_attributes):
    keyable = set(cmds.listAttr(node, keyable=True, unlocked=True, scalar=True) or [])
    rotate = [c for c in _ROTATE if c in keyable]
    translate = [c for c in _TRANSLATE if c in keyable]
    custom = [a for a in record_attributes if a in keyable]
    return rotate, translate, custom


def _attribute_names(manifest, control_name):
    names = set()
    for record in _records(manifest):
        if (record.get("shape_source") or record.get("ue_control_name") or record.get("name")) == control_name:
            names.update(a["name"] for a in (record.get("attributes") or []) if a.get("name"))
    return sorted(names)


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------

def _capture(joints, posed_controls, attribute_values, name, group):
    pose = {"name": name, "group": group, "controls": {}, "channels": attribute_values, "joints": {}}
    for control_name, node in sorted(posed_controls.items(), key=lambda item: _depth(item[1])):
        position, rotation = world_state(node)
        pose["controls"][control_name] = {"t": position, "q": rotation}
    for joint in joints:
        position, rotation = world_state(joint)
        pose["joints"][erm._short_node_name(joint)] = {"t": position, "q": rotation}
    return pose


def _probe_value(channel, current, attribute_info, unit_scale):
    if channel in _ROTATE:
        return current + ROTATE_PROBE_DEGREES
    if channel in _TRANSLATE:
        return current + TRANSLATE_PROBE_CM / unit_scale
    lo = attribute_info.get("min", 0.0)
    hi = attribute_info.get("max", 1.0)
    return lo if abs(current - hi) < 1e-6 else hi


# ---------------------------------------------------------------------------
# IK/FK switches
# ---------------------------------------------------------------------------

_FK_ROLES = ("bone_driver", "constraint_driver")
_IK_ROLES = ("ik_effector", "effector", "pole_vector", "pv")


def _record_name(record):
    return record.get("shape_source") or record.get("ue_control_name") or record.get("name")


def switches(manifest):
    """Every exported IK/FK switch: control, attribute, IK and FK values."""
    found = []
    for module in manifest.get("modules") or []:
        switch = ((module.get("params") or {}).get("switch")) or {}
        record = switch.get("control") or {}
        name = _record_name(record) if record else None
        matches = cmds.ls(name, long=True) if name else []
        if not matches or not switch.get("attribute"):
            continue
        found.append({
            "module": module.get("module_name"),
            "control": erm._short_node_name(matches[0]),
            "node": matches[0],
            "attribute": switch["attribute"],
            "ik": float(switch.get("ik_value", 1.0)),
            "fk": float(switch.get("fk_value", 0.0)),
        })
    return found


def control_modes(manifest, found_switches):
    """{control name: (switch index, "ik" | "fk")} for the controls of switched limbs.

    A probe of an FK control is only meaningful with its limb in FK (in IK
    the control moves nothing), and vice versa -- so each probe first puts
    the limb in the right mode, and records it.
    """
    # Controller records live all over the manifest (per bone, per module);
    # each one names its module, which is what ties it to a switch.
    index_of = {s["module"]: i for i, s in enumerate(found_switches)}
    modes = {}
    for record in _records(manifest):
        index = index_of.get(record.get("module_name"))
        if index is None:
            continue
        role = str(record.get("role") or "")
        mode = "fk" if role in _FK_ROLES else "ik" if role in _IK_ROLES else None
        if mode:
            modes.setdefault(_record_name(record), (index, mode))
    return modes


def _switch_channels(found_switches):
    """Current value of every switch, as pose channels."""
    return {
        "{}.{}".format(s["control"], s["attribute"]): float(cmds.getAttr("{}.{}".format(s["node"], s["attribute"])))
        for s in found_switches
    }


def _motion(pose, rest):
    """Largest joint motion of a pose vs rest (cm, deg): 0 means a dead probe."""
    cm = deg = 0.0
    for name, state in pose["joints"].items():
        base = rest["joints"].get(name)
        if not base:
            continue
        cm = max(cm, math.sqrt(sum((a - b) ** 2 for a, b in zip(state["t"], base["t"]))))
        dot = min(1.0, abs(sum(a * b for a, b in zip(state["q"], base["q"]))))
        deg = max(deg, math.degrees(2.0 * math.acos(dot)))
    return {"cm": round(cm, 4), "deg": round(deg, 4)}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_test_poses(path, manifest):
    """Write the probe + random pose set. Restores every touched attribute."""
    joints = erm._exported_joints()
    controls = manifest_controls(manifest)
    unit_scale = erm._maya_linear_to_centimeters_scale()
    attribute_info = {}
    for record in _records(manifest):
        for info in record.get("attributes") or []:
            attribute_info[(_record_name(record), info.get("name"))] = info

    found_switches = switches(manifest)
    modes = control_modes(manifest, found_switches)

    plan = []   # (control, node, channel)
    for control_name, node in sorted(controls.items()):
        rotate, translate, custom = _channels(node, _attribute_names(manifest, control_name))
        plan.extend((control_name, node, c) for c in rotate + translate + custom)

    poses = [_capture(joints, {}, _switch_channels(found_switches), "rest", "rest")]
    rest = poses[0]
    # Rest state of every control: its frame (t, q) for replaying deltas, and
    # its origin (o) as the builder places it, for calibration.
    control_rest = {}
    for control_name, node in controls.items():
        position, rotation = world_state(node)
        origin = erm._controller_origin_world(node)[0]
        control_rest[control_name] = {
            "t": position, "q": rotation,
            "o": [round(c, 4) for c in erm._maya_vector_to_unreal(origin, apply_unit_scale=True)],
        }
    touched = {}
    skipped = []

    def _set(node, channel, value):
        """Set a channel; False (and nothing touched) when Maya refuses it --
        a connected, locked or driven channel is not an animator input."""
        plug = "{}.{}".format(node, channel)
        previous = cmds.getAttr(plug)
        try:
            cmds.setAttr(plug, value)
        except Exception as exc:
            skipped.append("{} ({})".format(plug, str(exc).strip().splitlines()[0] if str(exc) else "refused"))
            return False
        touched.setdefault(plug, previous)
        return True

    def _restore():
        for plug in list(touched):
            cmds.setAttr(plug, touched.pop(plug))

    def _set_mode(control_name, mode=None):
        """Put the limb of ``control_name`` in its mode (or ``mode``)."""
        index, wanted = modes.get(control_name, (None, None))
        if index is None:
            return
        switch = found_switches[index]
        _set(switch["node"], switch["attribute"], switch[mode or wanted])

    def _add(pose):
        pose["maya_motion"] = _motion(pose, rest)
        poses.append(pose)

    try:
        for control_name, node, channel in plan:
            plug = "{}.{}".format(node, channel)
            is_custom = channel not in _ROTATE + _TRANSLATE
            if not is_custom:
                _set_mode(control_name)
            current = cmds.getAttr(plug)
            info = attribute_info.get((control_name, channel), {})
            if not _set(node, channel, _probe_value(channel, current, info, unit_scale)):
                _restore()
                continue
            channels = _switch_channels(found_switches)
            if is_custom:
                channels["{}.{}".format(control_name, channel)] = float(cmds.getAttr(plug))
            pose = _capture(
                joints, {} if is_custom else {control_name: node}, channels,
                "{}.{}".format(control_name, channel), "probe",
            )
            pose["probe"] = {"control": control_name, "channel": channel,
                             "mode": modes.get(control_name, (None, None))[1] if not is_custom else None}
            _add(pose)
            _restore()

        # Random multi-control poses, each limb in a random mode; only the
        # controls active in their limb's mode are posed.
        rng = random.Random(RANDOM_SEED)
        transform_plan = [p for p in plan if p[2] in _ROTATE + _TRANSLATE]
        for index in range(RANDOM_POSES if transform_plan else 0):
            chosen_modes = [rng.choice(("ik", "fk")) for _ in found_switches]
            for switch, mode in zip(found_switches, chosen_modes):
                _set(switch["node"], switch["attribute"], switch[mode])
            active = [
                p for p in transform_plan
                if p[0] not in modes or chosen_modes[modes[p[0]][0]] == modes[p[0]][1]
            ]
            posed = {}
            for control_name, node, channel in rng.sample(active, min(RANDOM_CONTROLS_PER_POSE, len(active))):
                current = cmds.getAttr("{}.{}".format(node, channel))
                if channel in _ROTATE:
                    value = current + rng.uniform(-30.0, 30.0)
                else:
                    value = current + rng.uniform(-8.0, 8.0) / unit_scale
                if _set(node, channel, value):
                    posed[control_name] = node
            if posed:
                _add(_capture(joints, posed, _switch_channels(found_switches),
                              "random_{:02d}".format(index), "random"))
            _restore()
    finally:
        _restore()

    dead = [p["name"] for p in poses[1:] if p["maya_motion"]["cm"] < 1e-3 and p["maya_motion"]["deg"] < 1e-3]
    document = {
        "schema": "kotsudo.poses",
        "schema_version": POSES_SCHEMA_VERSION,
        "rig_name": manifest.get("rig_name"),
        "manifest_schema_version": manifest.get("schema_version"),
        "units": {"linear": "cm", "rotation": "quat_xyzw_world"},
        "probe": {"rotate_deg": ROTATE_PROBE_DEGREES, "translate_cm": TRANSLATE_PROBE_CM,
                  "random_poses": RANDOM_POSES, "seed": RANDOM_SEED},
        "controls": sorted(controls),
        "control_rest": control_rest,
        "switches": [{k: s[k] for k in ("module", "control", "attribute", "ik", "fk")} for s in found_switches],
        "poses": poses,
    }
    with open(path, "w") as handle:
        json.dump(document, handle, separators=(",", ":"))
    print("[RigManifest] Test poses: {} pose(s) over {} control(s), {} IK/FK switch(es) -> {}".format(
        len(poses), len(controls), len(found_switches), path))
    if dead:
        print("[RigManifest] Test poses: {} probe(s) move no joint in Maya (e.g. {}); "
              "Unreal must not move anything for them either.".format(len(dead), ", ".join(dead[:6])))
    if skipped:
        print("[RigManifest] Test poses: {} channel(s) Maya refused to set, skipped: {}".format(
            len(skipped), ", ".join(skipped[:10]) + (" ..." if len(skipped) > 10 else "")))
    return path


def export_from_scene(out_dir=None):
    """Re-export ONLY the test poses, from the manifest last written on the root joint.

    For iterating on a rig without a full FBX export. The file goes where
    Unreal looks for it: ``out_dir`` (default: the repo's FBXs folder), named
    by the manifest's ``poses_file``. Run a full export first if the rig's
    modules or controls changed -- the manifest on the root joint must match
    the FBX Unreal built from.
    """
    plug = "{}.{}".format(erm.ROOT_JOINT_NAME, erm.MANIFEST_ATTR)
    if not cmds.objExists(plug):
        raise RuntimeError("No manifest on '{}': run a full export first.".format(plug))
    manifest = json.loads(cmds.getAttr(plug))
    if out_dir is None:
        repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        out_dir = os.path.join(repo, "FBXs")
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    name = manifest.get("poses_file") or "{}.poses.json".format(manifest.get("rig_name") or "rig")
    return export_test_poses(os.path.join(out_dir, name), manifest)
