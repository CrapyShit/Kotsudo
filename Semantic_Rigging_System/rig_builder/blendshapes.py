"""Blendshapes: drive Unreal morph targets from the Maya controller sliders.

The FBX already carries the targets (Unreal imports them as morph targets,
named like the Maya targets). What the manifest adds is the wiring: for each
target, the controller attribute that drives its weight and the maths in
between (``blendshapes`` in the manifest, see export_rig_manifest
``_blendshape_records``). Per target the graph gets:

    Get channel (control.attribute) -> one float node per op -> Set Curve Value (morph)

A morph target follows the curve of the same name, so writing that curve in
the Control Rig moves the shape. Missing curves are added to the hierarchy.
"""

from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)

from . import graph_utils

NODE_PREFIX = "RB_BS_"        # removed with every other RB_ node on rebuild
_TRANSFORM_CHANNELS = {f"{k}{a}" for k in ("translate", "rotate", "scale") for a in "XYZ"}


def _unit(name):
    for candidate in (f"RigVMFunction_MathFloat{name}", f"RigUnit_MathFloat{name}"):
        unit = getattr(unreal, candidate, None)
        if unit is not None:
            return unit
    return None


def _pin(model, node, names):
    for name in names:
        if graph_utils.pin_exists(model, f"{node}.{name}"):
            return f"{node}.{name}"
    return None


class _Graph:
    """Small helper placing float nodes for one target."""

    def __init__(self, context, base):
        self.context, self.base = context, base
        self.controller, self.model = context.graph_controller, context.model
        self.count = 0
        self.nodes = []

    def node(self, unit_name, suffix):
        unit = _unit(unit_name)
        if unit is None:
            raise RuntimeError(f"float node '{unit_name}' is not available in this engine build")
        name = f"{self.base}_{self.count:02d}_{suffix}"
        self.count += 1
        graph_utils.create_unit_node(self.controller, self.model, name, unit, unreal.Vector2D(0, 0))
        self.nodes.append(name)
        return name

    def set(self, node, names, value):
        pin = _pin(self.model, node, names)
        if pin is None:
            raise RuntimeError(f"{node}: none of the pins {names} exists")
        graph_utils.set_pin_default(self.controller, self.model, pin, str(value))

    def link(self, source, node, names):
        pin = _pin(self.model, node, names)
        if pin is None or not graph_utils.connect_pins(self.controller, self.model, source, pin):
            raise RuntimeError(f"could not connect {source} -> {node}.{names[0]}")

    def output(self, node):
        pin = _pin(self.model, node, ["Result", "Value", "ReturnValue"])
        if pin is None:
            raise RuntimeError(f"{node}: no output pin")
        return pin

    def binary(self, unit_name, source, constant, constant_first=False):
        node = self.node(unit_name, unit_name)
        if constant_first:
            self.set(node, ["A"], constant)
            self.link(source, node, ["B"])
        else:
            self.link(source, node, ["A"])
            self.set(node, ["B"], constant)
        return self.output(node)

    def remap(self, source, from_range, to_range):
        node = self.node("Remap", "Remap")
        self.link(source, node, ["Value"])
        self.set(node, ["SourceMinimum"], from_range[0])
        self.set(node, ["SourceMaximum"], from_range[1])
        self.set(node, ["TargetMinimum"], to_range[0])
        self.set(node, ["TargetMaximum"], to_range[1])
        self.set(node, ["bClamp", "Clamp"], "True")
        return self.output(node)

    def add_pins(self, first, second):
        node = self.node("Add", "Add")
        self.link(first, node, ["A"])
        self.link(second, node, ["B"])
        return self.output(node)


def _apply(graph, pin, op):
    """Pin carrying ``op`` applied to ``pin`` (same rules as the exporter)."""
    kind = op.get("op")
    if kind in ("mul", "div", "pow", "add"):
        return graph.binary({"mul": "Mul", "div": "Div", "pow": "Pow", "add": "Add"}[kind], pin, float(op["value"]))
    if kind == "reverse":
        return graph.binary("Sub", pin, 1.0, constant_first=True)
    if kind == "clamp":
        node = graph.node("Clamp", "Clamp")
        graph.link(pin, node, ["Value"])
        graph.set(node, ["Minimum", "Min"], float(op["min"]))
        graph.set(node, ["Maximum", "Max"], float(op["max"]))
        return graph.output(node)
    if kind == "remap":
        return graph.remap(pin, [float(v) for v in op["from"]], [float(v) for v in op["to"]])
    if kind == "curve":
        # Linear driven keys, constant outside them: first key's value plus,
        # per segment, a clamped remap of the input onto that segment's rise.
        keys = [(float(x), float(y)) for x, y in op["keys"]]
        if len(keys) == 1:
            return graph.binary("Add", graph.binary("Mul", pin, 0.0), keys[0][1])
        result = None
        for (x0, y0), (x1, y1) in zip(keys, keys[1:]):
            if x1 == x0:
                continue
            segment = graph.remap(pin, [x0, x1], [0.0, y1 - y0])
            result = segment if result is None else graph.add_pins(result, segment)
        return graph.binary("Add", result, keys[0][1]) if keys[0][1] else result
    raise RuntimeError(f"unknown op '{kind}'")


def _channel_pin(context, graph, control_key, attribute):
    hierarchy = context.hierarchy
    try:
        children = hierarchy.get_children(control_key, False) or []
    except TypeError:
        children = hierarchy.get_children(control_key) or []
    channel = next((c for c in children if c.type == unreal.RigElementType.CONTROL
                    and str(c.name).startswith(attribute)), None)
    if channel is None:
        return None
    name = f"{graph.base}_Get"
    pin = graph_utils.create_channel_getter(
        context.graph_controller, context.model, name, str(control_key.name), attribute, str(channel.name),
        unreal.Vector2D(0, 0),
    )
    return pin


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
            control_key = context.control_key_for_maya(driver.get("control"))
            if control_key is None:
                raise RuntimeError(f"driver control '{driver.get('control')}' is not in the rig")
            if not _ensure_curve(context, morph):
                raise RuntimeError(f"no curve '{morph}' in the rig (was the FBX imported with morph targets?)")
            graph = _Graph(context, f"{NODE_PREFIX}{graph_utils.sanitize_name(morph)}")
            pin = _channel_pin(context, graph, control_key, driver["attr"])
            if pin is None:
                raise RuntimeError(f"'{driver['control']}' has no channel '{driver['attr']}'")
            for op in entry.get("ops") or []:
                pin = _apply(graph, pin, op)
            set_node = f"{graph.base}_Set"
            graph_utils.create_unit_node(context.graph_controller, context.model, set_node, unit,
                                         unreal.Vector2D(0, 0))
            graph.nodes.append(set_node)
            graph_utils.set_any_pin(context.graph_controller, context.model, set_node, ["Curve"], morph)
            graph.link(pin, set_node, ["Value"])
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
