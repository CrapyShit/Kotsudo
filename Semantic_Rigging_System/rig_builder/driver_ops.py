"""Driver maths in the Control Rig graph: "slider -> maths -> something".

The exporter describes every attribute-driven value the same way (see
export_rig_manifest ``_attribute_driver``): a controller attribute plus an
ordered list of ops, in UI units at both ends. This module turns that into
float nodes, once, for every consumer -- blendshape weights, space-switch
constraint weights and driven offset-group channels:

    Get channel (control.attribute) -> one float node per op -> consumer pin

Supported ops: mul, div, pow, add, reverse (1 - x), clamp, remap (clamped),
curve (linear driven keys, constant outside them) and compare (condition
nodes: true/false value from eq/ne/gt/ge/lt/le against a constant).
"""

from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)

from . import graph_utils

_COMPARE_UNITS = {"eq": "Equals", "ne": "NotEquals", "gt": "Greater", "ge": "GreaterEqual",
                  "lt": "Less", "le": "LessEqual"}


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


class OpsGraph:
    """Places the float nodes of one driven value; node names start with ``base``."""

    def __init__(self, context, base):
        self.context, self.base = context, base
        self.controller, self.model = context.graph_controller, context.model
        self.count = 0
        self.nodes = []

    def node(self, unit_name, suffix=None):
        unit = _unit(unit_name)
        if unit is None:
            raise RuntimeError(f"float node '{unit_name}' is not available in this engine build")
        name = f"{self.base}_{self.count:02d}_{suffix or unit_name}"
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
        node = self.node(unit_name)
        if constant_first:
            self.set(node, ["A"], constant)
            self.link(source, node, ["B"])
        else:
            self.link(source, node, ["A"])
            self.set(node, ["B"], constant)
        return self.output(node)

    def remap(self, source, from_range, to_range):
        node = self.node("Remap")
        self.link(source, node, ["Value"])
        self.set(node, ["SourceMinimum"], from_range[0])
        self.set(node, ["SourceMaximum"], from_range[1])
        self.set(node, ["TargetMinimum"], to_range[0])
        self.set(node, ["TargetMaximum"], to_range[1])
        self.set(node, ["bClamp", "Clamp"], "True")
        return self.output(node)

    def add_pins(self, first, second):
        node = self.node("Add")
        self.link(first, node, ["A"])
        self.link(second, node, ["B"])
        return self.output(node)

    def constant(self, value):
        """A pin carrying ``value`` (for consumers that need a pin)."""
        node = self.node("Add", "Const")
        self.set(node, ["A"], float(value))
        self.set(node, ["B"], 0.0)
        return self.output(node)

    def compare(self, source, op):
        """true/false value of a condition, as a float pin."""
        test, value = op.get("test"), float(op["value"])
        when_true, when_false = float(op["true"]), float(op["false"])
        compare_unit = _unit(_COMPARE_UNITS.get(test, ""))
        select_unit = _unit("SelectBool")
        if compare_unit is not None and select_unit is not None:
            node = self.node(_COMPARE_UNITS[test])
            self.link(source, node, ["A"])
            self.set(node, ["B"], value)
            select = self.node("SelectBool", "Select")
            self.link(self.output(node), select, ["Condition"])
            self.set(select, ["IfTrue"], when_true)
            self.set(select, ["IfFalse"], when_false)
            return self.output(select)
        if test == "eq":
            # Arithmetic fallback, exact for whole numbers (enum channels):
            # false + (true - false) * clamp(1 - |x - value|, 0, 1).
            distance = self.binary("Sub", source, value)
            absolute = self.node("Abs")
            self.link(distance, absolute, ["Value"])
            closeness = self.binary("Sub", self.output(absolute), 1.0, constant_first=True)
            clamp = self.node("Clamp")
            self.link(closeness, clamp, ["Value"])
            self.set(clamp, ["Minimum", "Min"], 0.0)
            self.set(clamp, ["Maximum", "Max"], 1.0)
            scaled = self.binary("Mul", self.output(clamp), when_true - when_false)
            return self.binary("Add", scaled, when_false) if when_false else scaled
        raise RuntimeError(f"comparison '{test}' needs compare/select nodes this engine build does not have")

    def apply(self, pin, op):
        """Pin carrying ``op`` applied to ``pin`` (same rules as the exporter)."""
        kind = op.get("op")
        if kind in ("mul", "div", "pow", "add"):
            return self.binary({"mul": "Mul", "div": "Div", "pow": "Pow", "add": "Add"}[kind], pin, float(op["value"]))
        if kind == "reverse":
            return self.binary("Sub", pin, 1.0, constant_first=True)
        if kind == "clamp":
            node = self.node("Clamp")
            self.link(pin, node, ["Value"])
            self.set(node, ["Minimum", "Min"], float(op["min"]))
            self.set(node, ["Maximum", "Max"], float(op["max"]))
            return self.output(node)
        if kind == "remap":
            return self.remap(pin, [float(v) for v in op["from"]], [float(v) for v in op["to"]])
        if kind == "curve":
            # Linear driven keys, constant outside them: first key's value
            # plus, per segment, a clamped remap onto that segment's rise.
            keys = [(float(x), float(y)) for x, y in op["keys"]]
            if len(keys) == 1:
                return self.binary("Add", self.binary("Mul", pin, 0.0), keys[0][1])
            result = None
            for (x0, y0), (x1, y1) in zip(keys, keys[1:]):
                if x1 == x0:
                    continue
                segment = self.remap(pin, [x0, x1], [0.0, y1 - y0])
                result = segment if result is None else self.add_pins(result, segment)
            return self.binary("Add", result, keys[0][1]) if keys[0][1] else result
        if kind == "compare":
            return self.compare(pin, op)
        raise RuntimeError(f"unknown op '{kind}'")

    def apply_all(self, pin, ops):
        for op in ops or []:
            pin = self.apply(pin, op)
        return pin


def channel_pin(context, graph, control_key, attribute):
    """Pin reading ``attribute`` (an animation channel) on ``control_key``, or None."""
    hierarchy = context.hierarchy
    try:
        children = hierarchy.get_children(control_key, False) or []
    except TypeError:
        children = hierarchy.get_children(control_key) or []
    channel = next((c for c in children if c.type == unreal.RigElementType.CONTROL
                    and str(c.name).startswith(attribute)), None)
    if channel is None:
        return None
    return graph_utils.create_channel_getter(
        context.graph_controller, context.model, f"{graph.base}_Get", str(control_key.name), attribute,
        str(channel.name), unreal.Vector2D(0, 0),
    )


def driver_pin(context, base, driver):
    """Pin computing a driven value, or None for a constant.

    ``driver``: {'control', 'attr', 'ops'} (or the older 'invert' flag), or
    {'value': v}. Raises RuntimeError with the reason when it cannot be built.
    """
    if "attr" not in (driver or {}):
        return None
    control_key = context.control_key_for_maya(driver.get("control"))
    if control_key is None:
        raise RuntimeError(f"driver control '{driver.get('control')}' is not in the rig")
    graph = OpsGraph(context, base)
    pin = channel_pin(context, graph, control_key, str(driver["attr"]))
    if pin is None:
        raise RuntimeError(f"'{driver.get('control')}' has no channel '{driver['attr']}'")
    ops = driver.get("ops")
    if ops is None and driver.get("invert"):
        ops = [{"op": "reverse"}]
    return graph.apply_all(pin, ops)
