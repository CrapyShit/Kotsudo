"""Driven offset groups (Unreal side), evaluated offline (plain python).

    py tests/offline_driven_groups_test.py

Builds the rotation and translation part of a driven group's graph
(rig_builder/driven_groups._Builder) into a fake Control Rig, evaluates the
quaternion / vector / float nodes numerically, and checks them against
driven_groups.local_unreal -- the maths tests/maya_driven_groups_test.py
checks against Maya's own matrices.
"""
import math
import os
import random
import re
import sys
import types


class _Unit:
    def __init__(self, name):
        self.name = name


fake = types.ModuleType("unreal")
for name in ("MathFloatMul", "MathFloatAdd", "MathFloatSub", "MathQuaternionMul", "MathQuaternionFromAxisAndAngle",
             "MathVectorScale", "MathVectorAdd"):
    setattr(fake, "RigVMFunction_" + name, _Unit(name))
fake.RigUnit_GetFloatAnimationChannel = _Unit("Channel")
fake.Vector2D = lambda x=0, y=0: (x, y)
fake.RigElementType = types.SimpleNamespace(CONTROL="CONTROL", CURVE="CURVE", BONE="BONE", NULL="NULL")


class Key:
    def __init__(self, type_, name):
        self.type, self.name = type_, name


sys.modules["unreal"] = fake
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from rig_builder import driven_groups as dg, graph_utils  # noqa: E402
from driver_ops_reference import apply_ops  # noqa: E402

PINS = {"MathFloatMul": ("A", "B", "Result"), "MathFloatAdd": ("A", "B", "Result"), "MathFloatSub": ("A", "B", "Result"),
        "MathQuaternionMul": ("A", "B", "Result"), "MathQuaternionFromAxisAndAngle": ("Axis", "Angle", "Result"),
        "MathVectorScale": ("Value", "Factor", "Result"), "MathVectorAdd": ("A", "B", "Result"),
        "Channel": ("Control", "Channel", "bInitial", "Value")}
NODES, VALUES, LINKS = {}, {}, {}
graph_utils.create_unit_node = lambda c, m, name, unit, pos, *a: NODES.setdefault(name, unit.name)
graph_utils.pin_exists = lambda m, path: (path.split(".", 1)[0] in NODES
                                          and path.split(".", 1)[1] in PINS[NODES[path.split(".", 1)[0]]])
graph_utils.set_pin_default = lambda c, m, path, value: VALUES.__setitem__(path, value)
graph_utils.connect_pins = lambda c, m, a, b: LINKS.__setitem__(b, a) or True


def _channel_getter(c, m, name, control, attribute, channel_key, pos):
    NODES[name] = "Channel"
    VALUES[name + ".Channel"], VALUES[name + ".Control"] = attribute, control
    return name + ".Value"


graph_utils.create_channel_getter = _channel_getter


class Hierarchy:
    def get_children(self, key, recursive=False):
        return [Key("CONTROL", a) for a in ("open", "twist")]


class Context:
    hierarchy, graph_controller, model = Hierarchy(), object(), object()

    def control_key_for_maya(self, name):
        return Key("CONTROL", name) if name == "settings" else None


def parse(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        pass
    numbers = [float(x) for x in re.findall(r"[-+0-9.eE]+(?=[,)])", str(text))]
    return numbers[0] if len(numbers) == 1 else numbers


def evaluate(pin, sliders):
    node, _ = pin.split(".", 1)
    kind = NODES[node]

    def arg(p):
        path = "{}.{}".format(node, p)
        return evaluate(LINKS[path], sliders) if path in LINKS else parse(VALUES[path])

    if kind == "Channel":
        return sliders[VALUES[node + ".Channel"]]
    if kind == "MathFloatMul":
        return arg("A") * arg("B")
    if kind == "MathFloatAdd":
        return arg("A") + arg("B")
    if kind == "MathFloatSub":
        return arg("A") - arg("B")
    if kind == "MathQuaternionMul":
        return dg.q_mul(arg("A"), arg("B"))
    if kind == "MathQuaternionFromAxisAndAngle":
        return dg.q_axis_angle(arg("Axis"), arg("Angle"))
    if kind == "MathVectorScale":
        return [c * arg("Factor") for c in arg("Value")]
    if kind == "MathVectorAdd":
        a, b = arg("A"), arg("B")
        return [a[i] + b[i] for i in range(3)]
    raise ValueError(kind)


def angle(a, b):
    d = dg.q_mul([-a[0], -a[1], -a[2], a[3]], b)
    return math.degrees(2.0 * math.atan2(math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2), abs(d[3])))


rng = random.Random(5)
axes_y_up = {"x": [1, 0, 0], "y": [0, 0, 1], "z": [0, 1, 0]}     # Maya (X, Y, Z) -> Unreal (X, Z, Y)
worst_deg = worst_cm = 0.0
for trial in range(40):
    NODES.clear(), VALUES.clear(), LINKS.clear()
    group = {
        "name": "g{}".format(trial), "rotate_order": rng.choice(["xyz", "yzx", "zxy", "xzy", "yxz", "zyx"]),
        "rotate_axis": [rng.uniform(-45, 45) for _ in range(3)],
        "joint_orient": [rng.uniform(-60, 60) for _ in range(3)] if trial % 2 else [0.0, 0.0, 0.0],
        "rest": {c: rng.uniform(-30, 30) for c in ("translateX", "translateY", "translateZ",
                                                    "rotateX", "rotateY", "rotateZ")},
        "axes_unreal": axes_y_up, "unit_scale": rng.choice([1.0, 100.0]),
        "driven": {
            "translateY": {"control": "settings", "attr": "open", "ops": [{"op": "mul", "value": 0.2}]},
            "rotateX": {"control": "settings", "attr": "open", "ops": [{"op": "mul", "value": 8.0}]},
            "rotateZ": {"control": "settings", "attr": "twist", "ops": [{"op": "mul", "value": -5.0}]},
        },
    }
    builder = dg._Builder(Context(), "G{}".format(trial))
    rotation_pin, _ = builder.rotation(group)
    translation_pin, _ = builder.translation(group)
    for _ in range(10):
        sliders = {"open": rng.uniform(-10, 10), "twist": rng.uniform(-10, 10)}
        values = dict(group["rest"])
        for channel, driver in group["driven"].items():
            values[channel] = apply_ops(sliders[driver["attr"]], driver["ops"])
        want_q, want_t = dg.local_unreal(group, values)
        got_q, got_t = evaluate(rotation_pin, sliders), evaluate(translation_pin, sliders)
        worst_deg = max(worst_deg, angle(got_q, want_q))
        worst_cm = max(worst_cm, math.dist(got_t, want_t))
assert worst_deg < 1e-5 and worst_cm < 1e-4, (worst_deg, worst_cm)   # pin defaults carry 9 significant digits
print("OFFLINE DRIVEN GROUPS OK (40 groups x 10 poses, worst {:.1e} deg / {:.1e} cm)".format(worst_deg, worst_cm))
