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

Usage: export() in export_rig_manifest.py writes <name>.poses.json next to
the FBX; call export_test_poses(path, manifest) directly to regenerate.
"""

import json
import math
import random

import maya.cmds as cmds

import export_rig_manifest as erm

POSES_SCHEMA_VERSION = 1
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


def export_test_poses(path, manifest):
    """Write the probe + random pose set. Restores every touched attribute."""
    joints = erm._exported_joints()
    controls = manifest_controls(manifest)
    unit_scale = erm._maya_linear_to_centimeters_scale()
    attribute_info = {}
    for record in _records(manifest):
        for info in record.get("attributes") or []:
            owner = record.get("shape_source") or record.get("ue_control_name") or record.get("name")
            attribute_info[(owner, info.get("name"))] = info

    plan = []   # (control, node, channel)
    for control_name, node in sorted(controls.items()):
        rotate, translate, custom = _channels(node, _attribute_names(manifest, control_name))
        plan.extend((control_name, node, c) for c in rotate + translate + custom)

    poses = [_capture(joints, {}, {}, "rest", "rest")]
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

    try:
        for control_name, node, channel in plan:
            plug = "{}.{}".format(node, channel)
            current = cmds.getAttr(plug)
            info = attribute_info.get((control_name, channel), {})
            if not _set(node, channel, _probe_value(channel, current, info, unit_scale)):
                continue
            is_custom = channel not in _ROTATE + _TRANSLATE
            poses.append(_capture(
                joints,
                {} if is_custom else {control_name: node},
                {"{}.{}".format(control_name, channel): cmds.getAttr(plug)} if is_custom else {},
                "{}.{}".format(control_name, channel), "probe",
            ))
            cmds.setAttr(plug, touched.pop(plug))

        rng = random.Random(RANDOM_SEED)
        transform_plan = [p for p in plan if p[2] in _ROTATE + _TRANSLATE]
        for index in range(RANDOM_POSES if transform_plan else 0):
            chosen = rng.sample(transform_plan, min(RANDOM_CONTROLS_PER_POSE, len(transform_plan)))
            posed = {}
            for control_name, node, channel in chosen:
                current = cmds.getAttr("{}.{}".format(node, channel))
                if channel in _ROTATE:
                    value = current + rng.uniform(-30.0, 30.0)
                else:
                    value = current + rng.uniform(-8.0, 8.0) / unit_scale
                if _set(node, channel, value):
                    posed[control_name] = node
            if not posed:
                continue
            poses.append(_capture(joints, posed, {}, "random_{:02d}".format(index), "random"))
            for plug in list(touched):
                cmds.setAttr(plug, touched.pop(plug))
    finally:
        for plug, value in touched.items():
            cmds.setAttr(plug, value)

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
        "poses": poses,
    }
    with open(path, "w") as handle:
        json.dump(document, handle, separators=(",", ":"))
    print("[RigManifest] Test poses: {} pose(s) over {} control(s) -> {}".format(
        len(poses), len(controls), path))
    if skipped:
        print("[RigManifest] Test poses: {} channel(s) Maya refused to set, skipped: {}".format(
            len(skipped), ", ".join(skipped[:10]) + (" ..." if len(skipped) > 10 else "")))
    return path
