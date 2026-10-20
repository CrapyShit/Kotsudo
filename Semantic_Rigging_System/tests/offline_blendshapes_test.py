"""Blendshape graph (Unreal side), evaluated offline (plain python).

    py tests/offline_blendshapes_test.py

Builds the morph-target graph into a fake Control Rig that records nodes, pin
values and links, then evaluates it numerically: for every kind of op the
exporter writes, Unreal's float nodes must give exactly the reference value
(the same rules the Maya test checks against Maya itself).
"""
import os
import random
import sys
import types


# --- fake unreal -------------------------------------------------------------
class _Unit:
    def __init__(self, name):
        self.name = name


fake = types.ModuleType("unreal")
for op in ("Mul", "Div", "Pow", "Add", "Sub", "Clamp", "Remap", "Abs", "SelectBool",
           "Equals", "NotEquals", "Greater", "GreaterEqual", "Less", "LessEqual"):
    setattr(fake, f"RigVMFunction_MathFloat{op}", _Unit(op))
fake.RigUnit_SetCurveValue = _Unit("SetCurve")
fake.RigUnit_GetFloatAnimationChannel = _Unit("Channel")
fake.Vector2D = lambda x=0, y=0: (x, y)
fake.RigElementType = types.SimpleNamespace(CONTROL="CONTROL", CURVE="CURVE", BONE="BONE", NULL="NULL")


class Key:
    def __init__(self, type_, name):
        self.type, self.name = type_, name

    def __eq__(self, other):
        return (self.type, self.name) == (other.type, other.name)

    def __hash__(self):
        return hash((self.type, self.name))


fake.RigElementKey = lambda type=None, name=None: Key(type, name)
sys.modules["unreal"] = fake
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rig_builder import blendshapes, driver_ops, graph_utils  # noqa: E402
from driver_ops_reference import apply_ops as reference  # noqa: E402

PINS = {
    "Mul": ("A", "B", "Result"), "Div": ("A", "B", "Result"), "Pow": ("A", "B", "Result"),
    "Add": ("A", "B", "Result"), "Sub": ("A", "B", "Result"),
    "Clamp": ("Value", "Minimum", "Maximum", "Result"),
    "Remap": ("Value", "SourceMinimum", "SourceMaximum", "TargetMinimum", "TargetMaximum", "bClamp", "Result"),
    "SetCurve": ("Curve", "Value", "ExecuteContext"), "Channel": ("Control", "Channel", "bInitial", "Value"),
    "Abs": ("Value", "Result"), "SelectBool": ("Condition", "IfTrue", "IfFalse", "Result"),
}
for _name in ("Equals", "NotEquals", "Greater", "GreaterEqual", "Less", "LessEqual"):
    PINS[_name] = ("A", "B", "Result")


class Graph:
    def __init__(self):
        self.nodes, self.values, self.links, self.exec = {}, {}, {}, []


G = Graph()
graph_utils.create_unit_node = lambda c, m, name, unit, pos, *a: G.nodes.setdefault(name, unit.name)
graph_utils.pin_exists = lambda m, path: path.split(".", 1)[0] in G.nodes and path.split(".", 1)[1] in PINS[G.nodes[path.split(".", 1)[0]]]
graph_utils.set_pin_default = lambda c, m, path, value: G.values.__setitem__(path, value)


def _set_any(c, m, node, names, value):
    for n in names:
        if graph_utils.pin_exists(m, f"{node}.{n}"):
            G.values[f"{node}.{n}"] = value
            return f"{node}.{n}"
    return None


graph_utils.set_any_pin = _set_any
graph_utils.connect_pins = lambda c, m, a, b: G.links.__setitem__(b, a) or True
graph_utils.connect_exec = lambda c, m, a, b: G.exec.append((a, b)) or True
graph_utils.find_forwards_solve_node_name = lambda m: "BeginExecution"


def _channel_getter(c, m, name, control, attribute, channel_key, pos):
    G.nodes[name] = "Channel"
    G.values[f"{name}.Channel"] = attribute
    G.values[f"{name}.Control"] = control
    return f"{name}.Value"


graph_utils.create_channel_getter = _channel_getter


class Hierarchy:
    def __init__(self, curves, channels):
        self.curves, self.channels = set(curves), channels

    def contains(self, key):
        return key.type != "CURVE" or key.name in self.curves

    def get_children(self, key, recursive=False):
        return [Key("CONTROL", f"{a}") for a in self.channels.get(key.name, [])]


class HierarchyController:
    def __init__(self, hierarchy):
        self.hierarchy = hierarchy

    def add_curve(self, name, value=0.0, undo=False, py=False):
        self.hierarchy.curves.add(name)


class Context:
    def __init__(self, hierarchy, controls):
        self.hierarchy, self.hierarchy_controller = hierarchy, HierarchyController(hierarchy)
        self.graph_controller, self.model, self.controls, self.tail = object(), object(), controls, None

    def control_key_for_maya(self, name):
        return Key("CONTROL", name) if name in self.controls else None

    def get_exec_tail(self):
        return self.tail

    def set_exec_tail(self, node):
        self.tail = node


def evaluate(pin, inputs):
    node, name = pin.split(".", 1)
    kind = G.nodes[node]

    def arg(p):
        path = f"{node}.{p}"
        return evaluate(G.links[path], inputs) if path in G.links else float(G.values[path])

    if kind == "Channel":
        return inputs[(G.values[f"{node}.Control"], G.values[f"{node}.Channel"])]
    if kind in ("Mul", "Div", "Pow", "Add", "Sub"):
        a, b = arg("A"), arg("B")
        return {"Mul": lambda: a * b, "Div": lambda: a / b, "Pow": lambda: a ** b,
                "Add": lambda: a + b, "Sub": lambda: a - b}[kind]()
    if kind == "Clamp":
        return min(max(arg("Value"), arg("Minimum")), arg("Maximum"))
    if kind == "Abs":
        return abs(arg("Value"))
    if kind in ("Equals", "NotEquals", "Greater", "GreaterEqual", "Less", "LessEqual"):
        a, b = arg("A"), arg("B")
        return {"Equals": a == b, "NotEquals": a != b, "Greater": a > b, "GreaterEqual": a >= b,
                "Less": a < b, "LessEqual": a <= b}[kind]
    if kind == "SelectBool":
        return arg("IfTrue") if arg("Condition") else arg("IfFalse")
    if kind == "Remap":
        v, a, b, c, d = (arg(p) for p in ("Value", "SourceMinimum", "SourceMaximum", "TargetMinimum", "TargetMaximum"))
        t = 0.0 if b == a else (v - a) / (b - a)
        if str(G.values.get(f"{node}.bClamp")) == "True":
            t = min(max(t, 0.0), 1.0)
        return c + (d - c) * t
    raise ValueError(kind)


CASES = {
    "Head_BS_Smile": [{"op": "mul", "value": 0.1}],
    "div": [{"op": "div", "value": 4.0}],
    "pow": [{"op": "add", "value": 11.0}, {"op": "pow", "value": 2.0}],
    "reverse": [{"op": "mul", "value": 0.1}, {"op": "reverse"}],
    "clamp": [{"op": "clamp", "min": -2.0, "max": 3.0}],
    "remap": [{"op": "remap", "from": [0.0, 10.0], "to": [0.0, 1.0]}],
    "chain": [{"op": "mul", "value": -1.0}, {"op": "add", "value": 2.5}, {"op": "clamp", "min": 0.0, "max": 1.0}],
    "curve3": [{"op": "curve", "keys": [[0.0, 0.0], [5.0, 1.0], [10.0, 0.25]]}],
    "curve_offset": [{"op": "curve", "keys": [[-2.0, 0.3], [4.0, 0.9]]}],
    "enum_eq": [{"op": "compare", "test": "eq", "value": 2.0, "true": 1.0, "false": 0.0}],
    "gt": [{"op": "compare", "test": "gt", "value": 1.5, "true": 0.25, "false": 0.75}],
    "cond_chain": [{"op": "mul", "value": 0.5}, {"op": "compare", "test": "le", "value": 1.0, "true": 3.0,
                                                 "false": -1.0}],
}
entries = [{"blendshape": "BS", "target": name, "morph": name,
            "driver": {"control": "ctrl", "attr": "a"}, "ops": ops} for name, ops in CASES.items()]
entries += [
    {"blendshape": "BS", "target": "bad", "morph": "bad", "unsupported": "condition node not supported"},
    {"blendshape": "BS", "target": "rot", "morph": "rot", "driver": {"control": "ctrl", "attr": "rotateX"}, "ops": []},
    {"blendshape": "BS", "target": "ghost", "morph": "ghost", "driver": {"control": "nobody", "attr": "a"}, "ops": []},
    {"blendshape": "BS", "target": "const", "morph": "const", "driver": None, "ops": []},
]
context = Context(Hierarchy(curves=["Head_BS_Smile"], channels={"ctrl": ["a"]}), controls={"ctrl"})
logs = []
built, problems = blendshapes.build(context, entries, logs.append)
assert sorted(built) == sorted(CASES), built
assert len(problems) == 3 and any("not supported" in p for p in problems) and \
    any("transform channel" in p for p in problems) and any("not in the rig" in p for p in problems), problems
assert all(name in context.hierarchy.curves for name in CASES), "missing curves were not added"
# every Set node is on the exec chain, in order
sets = [b for _, b in G.exec]
assert sets == [f"RB_BS_{graph_utils.sanitize_name(n)}_Set" for n in built], sets
rng = random.Random(4)
worst = 0.0
for name, ops in CASES.items():
    set_node = f"RB_BS_{graph_utils.sanitize_name(name)}_Set"
    assert G.values[f"{set_node}.Curve"] == name
    for _ in range(60):
        x = rng.uniform(-12, 12) if "compare" not in str(ops) else float(rng.randint(-4, 4))
        got = evaluate(G.links[f"{set_node}.Value"], {("ctrl", "a"): x})
        want = reference(x, ops)
        worst = max(worst, abs(got - want))
        assert abs(got - want) < 1e-9, (name, x, got, want)
print(f"OFFLINE BLENDSHAPES OK ({len(built)} targets, {len(problems)} rejected as expected, worst {worst:.1e})")


# --- the older weight form ('invert') and the arithmetic compare fallback ------
pin = driver_ops.driver_pin(context, "LEGACY", {"control": "ctrl", "attr": "a", "invert": True})
assert abs(evaluate(pin, {("ctrl", "a"): 0.3}) - 0.7) < 1e-12
assert driver_ops.driver_pin(context, "CONST", {"value": 0.5}) is None

del fake.RigVMFunction_MathFloatSelectBool                      # an engine build without select nodes
graph = driver_ops.OpsGraph(context, "FALLBACK")
G.nodes["FALLBACK_Get"] = "Channel"
G.values["FALLBACK_Get.Channel"], G.values["FALLBACK_Get.Control"] = "a", "ctrl"
eq = {"op": "compare", "test": "eq", "value": 1.0, "true": 0.8, "false": 0.1}
out = graph.apply("FALLBACK_Get.Value", eq)
for x in (-2.0, 0.0, 1.0, 2.0, 3.0):
    assert abs(evaluate(out, {("ctrl", "a"): x}) - reference(x, [eq])) < 1e-12, x
try:
    graph.apply("FALLBACK_Get.Value", {"op": "compare", "test": "gt", "value": 1.0, "true": 1.0, "false": 0.0})
    raise AssertionError("gt without select nodes must be rejected")
except RuntimeError:
    pass
print("DRIVER OPS OK (legacy invert, constant, arithmetic compare fallback)")
