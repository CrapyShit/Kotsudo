"""Blendshapes: drive Unreal morph targets from the Maya controller sliders.

The FBX already carries the targets (Unreal imports them as morph targets,
named like the Maya targets). What the manifest adds is the wiring: for each
target, the controller attribute that drives its weight and the maths in
between (``blendshapes`` in the manifest, see export_rig_manifest
``_blendshape_records``). Per target the graph gets:

    Get channel (control.attribute) -> float nodes (driver_ops) -> Set Curve Value (morph)

A morph target follows the curve of the same name, so writing that curve in
the Control Rig moves the shape. Missing curves are added to the hierarchy.
"""

from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)

from . import driver_ops, graph_utils

NODE_PREFIX = "RB_BS_"        # removed with every other RB_ node on rebuild
_TRANSFORM_CHANNELS = {f"{k}{a}" for k in ("translate", "rotate", "scale") for a in "XYZ"}


def _ensure_curve(context, morph):
    key = graph_utils.make_key(unreal.RigElementType.CURVE, morph)
    if context.hierarchy.contains(key):
        return True
    add = getattr(context.hierarchy_controller, "add_curve", None)
    if add is None:
        return False
    for args in ((morph, 0.0, False, False), (morph, 0.0, False), (morph, 0.0)):
        try:
            add(*args)
            break
        except TypeError:
            continue
        except Exception:
            return False
    return context.hierarchy.contains(key)


def build(context, entries, log=print):
    """Wire every supported blendshape target. Returns (built, problems)."""
    built, problems = [], []
    unit = getattr(unreal, "RigUnit_SetCurveValue", None)
    for entry in entries or []:
        morph = entry.get("morph") or entry.get("target")
        label = f"{entry.get('blendshape')}.{entry.get('target')}"
        try:
            if entry.get("unsupported"):
                raise RuntimeError(f"Maya wiring not supported ({entry['unsupported']})")
            driver = entry.get("driver")
            if not driver:
                continue      # a constant weight: nothing to drive
            if unit is None:
                raise RuntimeError("Set Curve Value is not available in this engine build")
            if driver.get("attr") in _TRANSFORM_CHANNELS:
                raise RuntimeError(f"driven by {driver['control']}.{driver['attr']} (a transform channel; "
                                   "only controller sliders are supported for now)")
            if context.control_key_for_maya(driver.get("control")) is None:
                raise RuntimeError(f"driver control '{driver.get('control')}' is not in the rig")
            if not _ensure_curve(context, morph):
                raise RuntimeError(f"no curve '{morph}' in the rig (was the FBX imported with morph targets?)")
            base = f"{NODE_PREFIX}{graph_utils.sanitize_name(morph)}"
            pin = driver_ops.driver_pin(context, base, dict(driver, ops=entry.get("ops") or []))
            set_node = f"{base}_Set"
            graph_utils.create_unit_node(context.graph_controller, context.model, set_node, unit,
                                         unreal.Vector2D(0, 0))
            graph_utils.set_any_pin(context.graph_controller, context.model, set_node, ["Curve"], morph)
            if not (graph_utils.pin_exists(context.model, f"{set_node}.Value")
                    and graph_utils.connect_pins(context.graph_controller, context.model, pin, f"{set_node}.Value")):
                raise RuntimeError(f"could not connect the weight to {set_node}.Value")
            tail = context.get_exec_tail() or graph_utils.find_forwards_solve_node_name(context.model)
            graph_utils.connect_exec(context.graph_controller, context.model, tail, set_node)
            context.set_exec_tail(set_node)
            built.append(morph)
        except Exception as exc:
            problems.append(f"{label}: {exc}")
    if built:
        log(f"[RigBuilder] Blendshapes: {len(built)} morph target(s) driven by their Maya sliders "
            f"({', '.join(built[:6])}{' ...' if len(built) > 6 else ''}).")
    for problem in problems:
        log(f"[RigBuilder] WARNING Blendshape not driven: {problem}")
    return built, problems
