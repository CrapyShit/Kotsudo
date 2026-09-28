"""Pose-match harness (Unreal side).

Replays the Maya test poses (tools/maya/export_test_poses.py) on the rebuilt
Control Rig and measures, per joint, how far Unreal's result is from Maya's.

Method
------
* A fresh rig instance is created from the blueprint, initialised, and run
  once at rest.
* Calibration first (rest pose): exported Maya world positions of joints AND
  controls vs Unreal's. This isolates the Maya->Unreal conversion from rig
  error -- if calibration fails, rig numbers are meaningless and the report
  says so. (Control positions include front/back offsets such as pole
  vectors, which a planar skeleton cannot reveal.)
* Every pose: reset to initial, apply the posed controls' world transforms
  (as rest offset x Maya delta, so each UE control keeps its own frame) and
  channel values, run Forwards Solve, read the bones.
* Errors: position |p_ue - p_maya| (cm); rotation = angle between the Unreal
  and Maya world rotation *deltas from rest* (deg). Using deltas cancels the
  constant per-bone frame difference the FBX importer introduces, so the
  number is pure rig error.
* Aggregates per joint, per module and per pose group; T0/T1 thresholds from
  the research reference (T0: 0.01 cm / 0.01 deg, T1: 0.1 cm / 0.5 deg).

run_pose_harness.py is the entry point.
"""

import json
import math
import os
from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)

from . import control_shapes, graph_utils

TIERS = (("T0", 0.01, 0.01), ("T1", 0.1, 0.5))
CALIBRATION_TOLERANCE_CM = 0.1


def _log(message):
    unreal.log(f"[PoseHarness] {message}")


def _warn(message):
    unreal.log_warning(f"[PoseHarness] {message}")


# ---------------------------------------------------------------------------
# Quaternion helpers (plain tuples: x, y, z, w)
# ---------------------------------------------------------------------------

def _q(values):
    return tuple(float(c) for c in values)


def _q_from_ue(quat):
    return (float(quat.x), float(quat.y), float(quat.z), float(quat.w))


def _q_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _q_inv(q):
    return (-q[0], -q[1], -q[2], q[3])


def _q_angle(a, b):
    dot = abs(sum(x * y for x, y in zip(a, b)))
    return math.degrees(2.0 * math.acos(max(-1.0, min(1.0, dot))))


def _distance(a, b):
    return math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))


def _stats(values):
    if not values:
        return None
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    return {"mean": sum(values) / len(values), "p95": p95, "max": ordered[-1], "n": len(values)}


# ---------------------------------------------------------------------------
# Rig instance
# ---------------------------------------------------------------------------

class RigInstance:
    """A runtime instance of a Control Rig blueprint driven from Python."""

    def __init__(self, rig_blueprint):
        self.rig = rig_blueprint.create_control_rig()
        if self.rig is None:
            raise RuntimeError("ControlRigBlueprint.create_control_rig() returned None.")
        self.rig.request_init()
        events = [str(e) for e in (self.rig.get_supported_events() or [])]
        self.forward = next((e for e in events if "forward" in e.lower()), None) or (
            "Update" if "Update" in events else (events[0] if events else "Forwards Solve")
        )
        self.construction = next((e for e in events if "construct" in e.lower()), None)
        self.hierarchy = self.rig.get_hierarchy()
        if self.construction:
            self.rig.execute(self.construction)
        self.rig.execute(self.forward)

    def reset(self):
        for type_name in ("ALL",):
            element_type = getattr(unreal.RigElementType, type_name, None)
            if element_type is not None:
                try:
                    self.hierarchy.reset_pose_to_initial(element_type)
                    return
                except Exception:
                    pass
        for type_name in ("BONE", "NULL", "CONTROL"):
            self.hierarchy.reset_pose_to_initial(getattr(unreal.RigElementType, type_name))

    def run(self):
        self.rig.execute(self.forward)

    def key(self, element_type, name):
        key = graph_utils.make_key(getattr(unreal.RigElementType, element_type), name)
        return key if self.hierarchy.contains(key) else None

    def global_transform(self, key, initial=False):
        return self.hierarchy.get_global_transform(key, initial)

    def set_global(self, key, transform):
        self.hierarchy.set_global_transform(key, transform, False, True)

    def channel_key(self, control_key, attribute):
        try:
            children = self.hierarchy.get_children(control_key, False) or []
        except TypeError:
            children = self.hierarchy.get_children(control_key) or []
        # Channels are control children named after the attribute (the engine
        # may suffix a duplicate name, e.g. "IK_FK_2").
        controls = [c for c in children if c.type == unreal.RigElementType.CONTROL]
        for child in controls:
            if str(child.name) == attribute:
                return child
        for child in controls:
            if str(child.name).startswith(attribute):
                return child
        return None

    def set_float(self, key, value):
        self.hierarchy.set_control_value(
            key, unreal.RigHierarchy.make_control_value_from_float(float(value)),
            unreal.RigControlValueType.CURRENT,
        )


def _transform(position, quat):
    t = unreal.Transform(location=unreal.Vector(*[float(c) for c in position]))
    t.rotation = unreal.Quat(*[float(c) for c in quat])
    return t


def _to_q(transform):
    return _q_from_ue(graph_utils.get_transform_rotation(transform))


def _to_p(transform):
    loc = graph_utils.transform_to_location(transform)
    return (float(loc.x), float(loc.y), float(loc.z))


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

def find_poses_file(assets, file_name):
    for directory in control_shapes._search_directories(assets):
        if file_name:
            path = os.path.join(directory, file_name)
            if os.path.isfile(path):
                return path
    for directory in control_shapes._search_directories(assets):
        candidates = sorted(
            (os.path.join(directory, f) for f in os.listdir(directory) if f.endswith(".poses.json"))
            if os.path.isdir(directory) else [],
            key=os.path.getmtime, reverse=True,
        )
        if candidates:
            return candidates[0]
    return None


def run(rig_blueprint, poses_path, manifest=None, report_path=None):
    """Replay every pose; write and return the report dict."""
    with open(poses_path, encoding="utf-8") as handle:
        document = json.load(handle)
    poses = document.get("poses") or []
    if not poses or poses[0].get("group") != "rest":
        raise RuntimeError(f"{poses_path}: no rest pose; re-export from Maya.")

    instance = RigInstance(rig_blueprint)
    rest = poses[0]
    module_of = {}
    for module in (manifest or {}).get("modules") or []:
        for bone in module.get("chain") or []:
            module_of[bone] = module.get("module_name")

    # -- rest state in Unreal ------------------------------------------------
    instance.reset()
    instance.run()
    joint_keys, ue_rest = {}, {}
    for name in rest["joints"]:
        key = instance.key("BONE", name)
        if key is not None:
            joint_keys[name] = key
            transform = instance.global_transform(key)
            ue_rest[name] = (_to_p(transform), _to_q(transform))
    missing_joints = sorted(set(rest["joints"]) - set(joint_keys))

    control_names = document.get("controls") or []
    control_keys, missing_controls = {}, []
    for name in control_names:
        key = instance.key("CONTROL", graph_utils.sanitize_name(name))
        if key is None:
            missing_controls.append(name)
        else:
            control_keys[name] = key

    # -- calibration -----------------------------------------------------------
    joint_calibration = [
        _distance(ue_rest[n][0], rest["joints"][n]["t"]) for n in joint_keys
    ]
    calibration = {
        "joints_position_cm": _stats(joint_calibration),
        "worst_joints": sorted(
            ((n, round(_distance(ue_rest[n][0], rest["joints"][n]["t"]), 4)) for n in joint_keys),
            key=lambda item: -item[1],
        )[:10],
    }
    ue_control_rest = {name: instance.global_transform(key, True) for name, key in control_keys.items()}
    # Controls: Unreal rest position vs the Maya controller origin. Unlike the
    # joints (a planar skeleton hides a front/back mirror), controls such as
    # pole vectors sit off that plane, so this catches mapping sign errors.
    control_errors = {}
    for name, transform in ue_control_rest.items():
        rest_state = _maya_control_rest(document, name) or {}
        if rest_state.get("o"):
            control_errors[name] = _distance(_to_p(transform), rest_state["o"])
    calibration["controls_position_cm"] = _stats(list(control_errors.values()))
    calibration["worst_controls"] = sorted(
        ((n, round(e, 4)) for n, e in control_errors.items()), key=lambda item: -item[1]
    )[:10]
    calibration_ok = (calibration["joints_position_cm"] or {}).get("max", 0.0) <= CALIBRATION_TOLERANCE_CM
    if not calibration_ok:
        _warn(
            "Calibration FAILED: at rest, Unreal joints differ from the exported Maya positions by up "
            f"to {calibration['joints_position_cm']['max']:.3f} cm -- the Maya->Unreal conversion is "
            "wrong, rig error below is not meaningful. Worst: " + str(calibration["worst_joints"][:3])
        )
    misplaced = [item for item in calibration["worst_controls"] if item[1] > CALIBRATION_TOLERANCE_CM]
    if misplaced:
        _warn("Controls not at their Maya origin at rest (cm): " + str(misplaced[:5]))

    # -- poses -----------------------------------------------------------------
    per_joint = {n: {"p": [], "r": []} for n in joint_keys}
    per_group = {}
    per_pose = []
    skipped = 0
    for pose in poses[1:]:
        instance.reset()
        applied = True
        for name, state in (pose.get("controls") or {}).items():
            key = control_keys.get(name)
            if key is None:
                applied = False
                continue
            rest_state = _maya_control_rest(document, name)
            target = _posed_control(ue_control_rest[name], rest_state, state)
            instance.set_global(key, target)
        for plug, value in (pose.get("channels") or {}).items():
            control_name, attribute = plug.split(".", 1)
            control_key = control_keys.get(control_name)
            channel = instance.channel_key(control_key, attribute) if control_key is not None else None
            if channel is None:
                applied = False
                continue
            instance.set_float(channel, value)
        if not applied:
            skipped += 1
        instance.run()

        pose_p, pose_r = [], []
        for name, key in joint_keys.items():
            transform = instance.global_transform(key)
            p_ue, q_ue = _to_p(transform), _to_q(transform)
            maya = pose["joints"].get(name)
            if not maya:
                continue
            e_p = _distance(p_ue, maya["t"])
            delta_ue = _q_mul(q_ue, _q_inv(ue_rest[name][1]))
            delta_maya = _q_mul(_q(maya["q"]), _q_inv(_q(rest["joints"][name]["q"])))
            e_r = _q_angle(delta_ue, delta_maya)
            per_joint[name]["p"].append(e_p)
            per_joint[name]["r"].append(e_r)
            pose_p.append(e_p)
            pose_r.append(e_r)
        group = per_group.setdefault(pose.get("group", "?"), {"p": [], "r": []})
        group["p"].extend(pose_p)
        group["r"].extend(pose_r)
        per_pose.append({
            "name": pose.get("name"), "applied": applied,
            "max_position_cm": round(max(pose_p), 4) if pose_p else None,
            "max_rotation_deg": round(max(pose_r), 4) if pose_r else None,
        })

    # -- aggregate --------------------------------------------------------------
    def tier(p_max, r_max):
        for name, p_limit, r_limit in TIERS:
            if p_max <= p_limit and r_max <= r_limit:
                return name
        return "above T1"

    joints_report = {}
    per_module = {}
    for name, errors in per_joint.items():
        p, r = _stats(errors["p"]), _stats(errors["r"])
        if not p:
            continue
        joints_report[name] = {"position_cm": p, "rotation_deg": r, "tier": tier(p["max"], r["max"]),
                               "module": module_of.get(name)}
        module = per_module.setdefault(module_of.get(name) or "(unowned)", {"p": [], "r": []})
        module["p"].extend(errors["p"])
        module["r"].extend(errors["r"])

    report = {
        "schema": "kotsudo.pose_report",
        "rig_name": document.get("rig_name"),
        "poses_file": poses_path,
        "poses": len(poses) - 1,
        "poses_not_fully_applied": skipped,
        "calibration": calibration,
        "calibration_ok": calibration_ok,
        "interface": {
            "maya_controls": len(control_names),
            "matched_by_name": len(control_keys),
            "missing_controls": missing_controls,
            "missing_joints": missing_joints,
        },
        "by_group": {g: {"position_cm": _stats(v["p"]), "rotation_deg": _stats(v["r"])} for g, v in per_group.items()},
        "by_module": {
            m: {"position_cm": _stats(v["p"]), "rotation_deg": _stats(v["r"]),
                "tier": tier(max(v["p"] or [0]), max(v["r"] or [0]))}
            for m, v in per_module.items()
        },
        "by_joint": joints_report,
        "worst_poses": sorted(
            (p for p in per_pose if p["max_position_cm"] is not None),
            key=lambda p: -(p["max_position_cm"] + p["max_rotation_deg"] / 10.0),
        )[:15],
    }
    report_path = report_path or poses_path.replace(".poses.json", ".harness_report.json")
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
    _summarise(report, report_path)
    return report


def _maya_control_rest(document, name):
    """Maya rest state {t, q, o} of a control (exported with the poses)."""
    return (document.get("control_rest") or {}).get(name)


def _posed_control(ue_rest, maya_rest, maya_posed):
    """Unreal control target = Unreal rest x (Maya rest^-1 x Maya posed).

    The Maya delta is applied in world space (rotation about the control's
    rest pivot, then translation), so the Unreal control keeps its own frame.
    Without a Maya rest state the posed Maya transform is used directly.
    """
    posed_q = _q(maya_posed["q"])
    posed_p = [float(c) for c in maya_posed["t"]]
    if not maya_rest:
        return _transform(posed_p, posed_q)
    rest_q = _q(maya_rest["q"])
    rest_p = [float(c) for c in maya_rest["t"]]
    delta_q = _q_mul(posed_q, _q_inv(rest_q))
    ue_q = _q_from_ue(graph_utils.get_transform_rotation(ue_rest))
    ue_p = graph_utils.transform_to_location(ue_rest)
    # Rotate the UE control's offset from the Maya pivot by the delta, then
    # add the Maya pivot's translation.
    offset = (float(ue_p.x) - rest_p[0], float(ue_p.y) - rest_p[1], float(ue_p.z) - rest_p[2])
    rotated = _q_mul(_q_mul(delta_q, offset + (0.0,)), _q_inv(delta_q))[:3]
    new_p = [posed_p[i] + rotated[i] for i in range(3)]
    new_q = _q_mul(delta_q, ue_q)
    return _transform(new_p, new_q)


def _summarise(report, report_path):
    interface = report["interface"]
    _log(
        f"{report['poses']} pose(s); controls matched by name "
        f"{interface['matched_by_name']}/{interface['maya_controls']}"
        + (f" (missing: {', '.join(interface['missing_controls'][:8])})" if interface["missing_controls"] else "")
    )
    cal = report["calibration"]["joints_position_cm"] or {}
    ctl = report["calibration"].get("controls_position_cm") or {}
    _log(f"Calibration (rest): joints max {cal.get('max', 0):.4f} cm -> "
         + ("OK" if report["calibration_ok"] else "FAILED")
         + f"; controls vs Maya origin max {ctl.get('max', 0):.4f} cm")
    for group, data in report["by_group"].items():
        p, r = data["position_cm"] or {}, data["rotation_deg"] or {}
        _log(f"  {group:7s}: position mean {p.get('mean', 0):.3f} / p95 {p.get('p95', 0):.3f} / "
             f"max {p.get('max', 0):.3f} cm; rotation mean {r.get('mean', 0):.3f} / "
             f"max {r.get('max', 0):.3f} deg")
    for module, data in sorted(report["by_module"].items()):
        p, r = data["position_cm"] or {}, data["rotation_deg"] or {}
        _log(f"  {module:18s} {data['tier']:9s} max {p.get('max', 0):.3f} cm / {r.get('max', 0):.3f} deg")
    _log(f"Report: {report_path}")
