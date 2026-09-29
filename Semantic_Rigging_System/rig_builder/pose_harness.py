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

def _make_rig_instance(rig_blueprint):
    """A Control Rig object to drive: a fresh instance when the API offers
    one, else the editor's preview/debug instance (reset before every pose,
    so replaying on it is equally valid)."""
    tried = []
    for getter in ("create_control_rig", "get_preview_instance", "get_debugged_control_rig",
                   "get_object_being_debugged"):
        method = getattr(rig_blueprint, getter, None)
        if method is None:
            continue
        tried.append(getter)
        try:
            rig = method()
        except Exception as exc:
            _warn(f"{getter}() failed: {exc}")
            continue
        if rig is not None and hasattr(rig, "get_hierarchy"):
            if getter != "create_control_rig":
                _log(f"Using the editor's rig instance ({getter}).")
            return rig
    raise RuntimeError(
        "Could not get a Control Rig instance from the blueprint (tried: "
        f"{', '.join(tried) or 'nothing available'}). Compile the rig and keep it open."
    )


class RigInstance:
    """A runtime instance of a Control Rig blueprint driven from Python."""

    def __init__(self, rig_blueprint):
        self.rig = _make_rig_instance(rig_blueprint)
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
    # Only joints a module rebuilds are scored. Helper chains Maya exports
    # but the Unreal rig does not drive (e.g. separate FK/IK joint chains
    # behind a blended limb) would only add fake errors; they are listed.
    not_rebuilt = sorted(n for n in rest["joints"] if module_of and n not in module_of)
    for name in rest["joints"]:
        if name in not_rebuilt:
            continue
        key = instance.key("BONE", name)
        if key is not None:
            joint_keys[name] = key
            transform = instance.global_transform(key)
            ue_rest[name] = (_to_p(transform), _to_q(transform))
    missing_joints = sorted(set(rest["joints"]) - set(joint_keys) - set(not_rebuilt))

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
    # The CONVERSION is wrong when the bulk of the joints is off (a wrong axis
    # or unit moves nearly everything). A few joints off is rig placement,
    # reported as rest offsets -- the pose errors below measure MOTION from
    # rest, so they stay meaningful either way.
    joint_stats = calibration["joints_position_cm"] or {}
    calibration_ok = joint_stats.get("p95", 0.0) <= CALIBRATION_TOLERANCE_CM
    calibration["rest_offsets"] = [
        item for item in calibration["worst_joints"] if item[1] > CALIBRATION_TOLERANCE_CM
    ]
    if not calibration_ok:
        _warn(
            "Calibration FAILED: at rest, most Unreal joints differ from the exported Maya positions "
            f"(p95 {joint_stats.get('p95', 0):.3f} cm) -- the Maya->Unreal conversion is wrong. "
            "Worst: " + str(calibration["worst_joints"][:3])
        )
    elif calibration["rest_offsets"]:
        _warn("Joints not at their Maya position at rest (cm): " + str(calibration["rest_offsets"][:5]))
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
        worst = (0.0, None)
        scored = []
        for name, key in joint_keys.items():
            transform = instance.global_transform(key)
            p_ue, q_ue = _to_p(transform), _to_q(transform)
            maya = pose["joints"].get(name)
            if not maya:
                continue
            # Motion error: Unreal's displacement from rest vs Maya's, so a
            # joint placed slightly off at rest (reported in calibration) does
            # not add the same constant to every pose.
            rest_p = rest["joints"][name]["t"]
            e_p = _distance(
                [p_ue[i] - ue_rest[name][0][i] for i in range(3)],
                [float(maya["t"][i]) - float(rest_p[i]) for i in range(3)],
            )
            delta_ue = _q_mul(q_ue, _q_inv(ue_rest[name][1]))
            delta_maya = _q_mul(_q(maya["q"]), _q_inv(_q(rest["joints"][name]["q"])))
            e_r = _q_angle(delta_ue, delta_maya)
            per_joint[name]["p"].append(e_p)
            per_joint[name]["r"].append(e_r)
            if e_p + e_r / 10.0 > worst[0]:
                worst = (e_p + e_r / 10.0, name)
            scored.append((e_p + e_r / 10.0, name, round(e_p, 3), round(e_r, 2)))
            pose_p.append(e_p)
            pose_r.append(e_r)
        group = per_group.setdefault(pose.get("group", "?"), {"p": [], "r": []})
        group["p"].extend(pose_p)
        group["r"].extend(pose_r)
        per_pose.append({
            "name": pose.get("name"), "group": pose.get("group"), "applied": applied,
            "probe": pose.get("probe"), "maya_motion": pose.get("maya_motion"),
            "worst_joint": worst[1],
            "top_joints": [(n, p, r) for _, n, p, r in sorted(scored, reverse=True)[:3]],
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
            "joints_not_rebuilt": not_rebuilt,
        },
        "by_group": {g: {"position_cm": _stats(v["p"]), "rotation_deg": _stats(v["r"])} for g, v in per_group.items()},
        "by_module": {
            m: {"position_cm": _stats(v["p"]), "rotation_deg": _stats(v["r"]),
                "tier": tier(max(v["p"] or [0]), max(v["r"] or [0]))}
            for m, v in per_module.items()
        },
        "by_joint": joints_report,
        "by_control": _by_control(per_pose),
        "verdict": _verdict(calibration_ok, per_module, skipped, tier, calibration["rest_offsets"]),
        "worst_poses": sorted(
            (p for p in per_pose if p["max_position_cm"] is not None),
            key=lambda p: -(p["max_position_cm"] + p["max_rotation_deg"] / 10.0),
        )[:15],
    }
    report_path = report_path or poses_path.replace(".poses.json", ".harness_report.json")
    previous = _load_json(report_path)
    report["compared_to_previous"] = _compare(previous, report) if previous else None
    if previous:
        with open(report_path.replace(".json", ".prev.json"), "w", encoding="utf-8") as handle:
            json.dump(previous, handle, indent=1)
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
    html_path = report_path.replace(".json", ".html")
    try:
        with open(html_path, "w", encoding="utf-8") as handle:
            handle.write(_html(report))
    except Exception as exc:
        _warn(f"HTML report not written: {exc}")
        html_path = None
    _summarise(report, report_path, html_path)
    return report


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def _by_control(per_pose):
    """Probe errors per posed control: the control whose probe breaks the most
    joints points straight at the setup to fix."""
    result = {}
    for pose in per_pose:
        probe = pose.get("probe") or {}
        control = probe.get("control")
        if not control or pose["max_position_cm"] is None:
            continue
        entry = result.setdefault(control, {"max_position_cm": 0.0, "max_rotation_deg": 0.0,
                                            "worst_probe": None, "worst_joint": None, "mode": probe.get("mode")})
        score = pose["max_position_cm"] + pose["max_rotation_deg"] / 10.0
        if score >= entry["max_position_cm"] + entry["max_rotation_deg"] / 10.0:
            entry.update(max_position_cm=pose["max_position_cm"], max_rotation_deg=pose["max_rotation_deg"],
                         worst_probe=pose["name"], worst_joint=pose["worst_joint"])
    return dict(sorted(result.items(), key=lambda item: -(item[1]["max_position_cm"]
                                                          + item[1]["max_rotation_deg"] / 10.0)))


def _verdict(calibration_ok, per_module, skipped, tier, rest_offsets=()):
    if not calibration_ok:
        return "CALIBRATION FAILED - conversion error, fix before reading rig numbers"
    tiers = [tier(max(v["p"] or [0]), max(v["r"] or [0])) for v in per_module.values()]
    failing = sum(1 for t in tiers if t == "above T1")
    text = f"{len(tiers) - failing}/{len(tiers)} module(s) within T1"
    if rest_offsets:
        text += f"; {len(rest_offsets)} joint(s) off at rest"
    if skipped:
        text += f"; {skipped} pose(s) could not be fully applied"
    return text


def _compare(previous, report):
    """Per-module max error, previous run -> this run."""
    changes = {}
    old_modules = previous.get("by_module") or {}
    for module, data in (report.get("by_module") or {}).items():
        old = old_modules.get(module)
        if not old:
            continue
        before = (old.get("position_cm") or {}).get("max", 0.0), (old.get("rotation_deg") or {}).get("max", 0.0)
        after = (data.get("position_cm") or {}).get("max", 0.0), (data.get("rotation_deg") or {}).get("max", 0.0)
        delta_p, delta_r = after[0] - before[0], after[1] - before[1]
        if abs(delta_p) < 0.01 and abs(delta_r) < 0.05:
            state = "same"
        elif delta_p <= 0.01 and delta_r <= 0.05:
            state = "better"
        elif delta_p >= -0.01 and delta_r >= -0.05:
            state = "WORSE"
        else:
            state = "mixed"
        changes[module] = {"state": state, "position_cm": [round(before[0], 4), round(after[0], 4)],
                           "rotation_deg": [round(before[1], 3), round(after[1], 3)]}
    return changes


def _html(report):
    """Self-contained, readable report page."""
    import html as _h

    colors = {"T0": "#1f8f4e", "T1": "#5b8f1f", "above T1": "#b3261e"}

    def row(cells):
        return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"

    def tier_cell(t):
        return f'<b style="color:{colors.get(t, "#333")}">{_h.escape(t)}</b>'

    cal = report["calibration"]
    parts = [
        "<!doctype html><meta charset=utf-8><title>Pose report</title>",
        "<style>body{font:14px system-ui,sans-serif;margin:24px;max-width:1100px;color:#222}"
        "table{border-collapse:collapse;margin:8px 0 20px}td,th{border:1px solid #ddd;padding:4px 8px;"
        "text-align:left}th{background:#f3f3f3}h2{margin-top:28px}.bad{color:#b3261e}</style>",
        f"<h1>Pose report: {_h.escape(str(report.get('rig_name')))}</h1>",
        f"<p><b>{_h.escape(report['verdict'])}</b> &middot; {report['poses']} poses &middot; "
        f"controls matched {report['interface']['matched_by_name']}/{report['interface']['maya_controls']}</p>",
        "<p>Tiers: T0 &le; 0.01 cm / 0.01&deg;, T1 &le; 0.1 cm / 0.5&deg;. Rotation = difference of the "
        "rotation <i>change from rest</i> (Maya vs Unreal).</p>",
        "<h2>Calibration (rest pose)</h2>",
        f"<p class={'' if report['calibration_ok'] else 'bad'}>Joints max "
        f"{(cal['joints_position_cm'] or {}).get('max', 0):.4f} cm; controls vs Maya origin max "
        f"{(cal.get('controls_position_cm') or {}).get('max', 0):.4f} cm</p>",
    ]
    if cal.get("worst_controls"):
        parts.append("<table><tr><th>Control not at its Maya origin</th><th>cm</th></tr>"
                     + "".join(row([_h.escape(n), e]) for n, e in cal["worst_controls"] if e > 0.1)
                     + "</table>")
    parts.append("<h2>Modules</h2><table><tr><th>Module</th><th>Tier</th><th>max cm</th>"
                 "<th>max deg</th><th>vs previous</th></tr>")
    changes = report.get("compared_to_previous") or {}
    for module, data in sorted(report["by_module"].items(), key=lambda i: i[0]):
        change = changes.get(module)
        parts.append(row([
            _h.escape(module), tier_cell(data["tier"]),
            f"{(data['position_cm'] or {}).get('max', 0):.3f}", f"{(data['rotation_deg'] or {}).get('max', 0):.3f}",
            f"{change['state']} ({change['position_cm'][0]} &rarr; {change['position_cm'][1]} cm)" if change else "",
        ]))
    parts.append("</table><h2>Controls whose probe breaks the most</h2><table><tr><th>Control</th>"
                 "<th>mode</th><th>worst probe</th><th>worst joint</th><th>max cm</th><th>max deg</th></tr>")
    for control, data in list(report["by_control"].items())[:25]:
        parts.append(row([_h.escape(control), data.get("mode") or "", _h.escape(str(data["worst_probe"])),
                          _h.escape(str(data["worst_joint"])), f"{data['max_position_cm']:.3f}",
                          f"{data['max_rotation_deg']:.3f}"]))
    parts.append("</table>")
    missing = report["interface"]["missing_controls"]
    if missing:
        parts.append("<h2>Maya controls missing in Unreal</h2><p>" + ", ".join(map(_h.escape, missing)) + "</p>")
    return "\n".join(parts)


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


def _summarise(report, report_path, html_path=None):
    interface = report["interface"]
    _log(f"VERDICT: {report['verdict']}")
    if interface.get("joints_not_rebuilt"):
        _log(f"{len(interface['joints_not_rebuilt'])} exported joint(s) belong to no module and are not scored "
             f"(e.g. {', '.join(interface['joints_not_rebuilt'][:4])}).")
    _log(
        f"{report['poses']} pose(s); controls matched by name "
        f"{interface['matched_by_name']}/{interface['maya_controls']}"
        + (f" (missing: {', '.join(interface['missing_controls'][:8])})" if interface["missing_controls"] else "")
    )
    cal = report["calibration"]["joints_position_cm"] or {}
    ctl = report["calibration"].get("controls_position_cm") or {}
    _log(f"Calibration (rest): joints p95 {cal.get('p95', 0):.4f} / max {cal.get('max', 0):.4f} cm -> "
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
    for control, data in list(report["by_control"].items())[:5]:
        _log(f"  worst control {control}: {data['max_position_cm']:.3f} cm / {data['max_rotation_deg']:.3f} deg "
             f"({data['worst_probe']}, joint {data['worst_joint']})")
    for pose in report.get("worst_poses", [])[:5]:
        _log(f"  worst pose {pose['name']}: " + ", ".join(
            f"{n} {p} cm/{r} deg" for n, p, r in pose.get("top_joints") or []))
    for module, change in (report.get("compared_to_previous") or {}).items():
        if change["state"] != "same":
            _log(f"  vs previous run: {module} {change['state']} "
                 f"({change['position_cm'][0]} -> {change['position_cm'][1]} cm)")
    _log(f"Report: {report_path}" + (f"  |  open in a browser: {html_path}" if html_path else ""))


def run_after_build(rig_blueprint, assets, manifest):
    """Run the harness right after a build; never raises (the build stands)."""
    try:
        poses_path = find_poses_file(assets, (manifest or {}).get("poses_file"))
        if not poses_path:
            _log("No <name>.poses.json next to the FBX: pose check skipped (re-export from Maya).")
            return None
        return run(rig_blueprint, poses_path, manifest=manifest)
    except Exception as exc:
        _warn(f"Pose check failed to run ({type(exc).__name__}: {exc}); the rig build is unaffected.")
        return None
