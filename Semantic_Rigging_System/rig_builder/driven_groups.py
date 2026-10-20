"""Driven offset groups: groups between a controller and its parent whose
channels are driven by controller sliders (set-driven-key / "auto" groups,
Murakami's petal groups).

Each driven group becomes a null between the control's parent and the
control. Every frame its local transform is rebuilt from the same channels
the Maya group has:

    local = L(channel values) o C

L is the group's Maya local transform (translate, then rotateAxis, the
rotation in its rotate order, jointOrient for joints) converted to Unreal
axes; C is a constant measured at build time so that any static groups and
the Unreal parent stay exactly where Maya has them:

    C = L(rest)^-1 o G_rest o U_rest^-1

(G_rest the group's rest world pose, U_rest the Unreal parent's.) Driven
channel values come from the controller sliders through driver_ops; the
others keep their rest values.

The maths (``local_unreal``) is plain python so the Maya test can check it
against Maya's own matrices.
"""

import math
from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)

NODE_PREFIX = "RB_DG_"        # removed with every other RB_ node on rebuild
_ROTATE = ("rotateX", "rotateY", "rotateZ")
_TRANSLATE = ("translateX", "translateY", "translateZ")


# ---------------------------------------------------------------------------
# Plain maths: quaternions [x, y, z, w]; a transform is (quat, translation);
# composing A then B (Unreal's A * B) = (qB qA, qB tA + tB).
# ---------------------------------------------------------------------------

def q_mul(a, b):
    """Hamilton product a * b: b applied first, then a."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return [aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz]


def q_axis_angle(axis, radians):
    n = math.sqrt(sum(c * c for c in axis)) or 1.0
    s = math.sin(radians / 2.0) / n
    return [axis[0] * s, axis[1] * s, axis[2] * s, math.cos(radians / 2.0)]


def q_rotate(q, v):
    p = q_mul(q_mul(q, [v[0], v[1], v[2], 0.0]), [-q[0], -q[1], -q[2], q[3]])
    return p[:3]


def compose(first, second):
    """Transform applying ``first`` then ``second``."""
    (qa, ta), (qb, tb) = first, second
    moved = q_rotate(qb, ta)
    return q_mul(qb, qa), [moved[i] + tb[i] for i in range(3)]


def inverse(transform):
    q, t = transform
    qi = [-q[0], -q[1], -q[2], q[3]]
    moved = q_rotate(qi, t)
    return qi, [-c for c in moved]


def rotation_sequence(group, values):
    """[(axis letter, degrees)] in the order Maya applies them: rotateAxis
    (x, y, z), the rotation in the group's rotate order, jointOrient."""
    sequence = [(a, d) for a, d in zip("xyz", group.get("rotate_axis") or [0, 0, 0])]
    for letter in group.get("rotate_order") or "xyz":
        sequence.append((letter, values["rotate" + letter.upper()]))
    sequence += [(a, d) for a, d in zip("xyz", group.get("joint_orient") or [0, 0, 0])]
    return sequence


def axis_rotation(group, letter, degrees):
    """A Maya rotation about local axis ``letter`` by ``degrees``, in Unreal
    axes: the axis maps like any vector, and the angle flips sign because
    the Maya -> Unreal axis mapping is a reflection (right- to left-handed)."""
    return q_axis_angle(group["axes_unreal"][letter], -math.radians(degrees))


def local_unreal(group, values):
    """(quat, translation in cm) of the group's local transform, Unreal axes,
    for channel ``values`` in UI units (degrees, scene units)."""
    q = [0.0, 0.0, 0.0, 1.0]
    for letter, degrees in rotation_sequence(group, values):
        q = q_mul(axis_rotation(group, letter, degrees), q)
    scale = float(group.get("unit_scale", 1.0))
    t = [0.0, 0.0, 0.0]
    for letter in "xyz":
        amount = values["translate" + letter.upper()] * scale
        axis = group["axes_unreal"][letter]
        t = [t[i] + amount * axis[i] for i in range(3)]
    return q, t


def _quat_from_basis(x_axis, y_axis, z_axis):
    """Quaternion of an orthonormal basis given as axes (rows), the same
    convention as the exported poses (export_test_poses.matrix_state)."""
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
    return [c / norm for c in q]


def _orthonormal(x_axis, y_axis):
    def norm(v):
        n = math.sqrt(sum(c * c for c in v)) or 1.0
        return [c / n for c in v]

    def cross(a, b):
        return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]

    x = norm(x_axis)
    z = norm(cross(x, y_axis))
    return x, cross(z, x), z


def pose_to_transform(pose):
    """(quat, translation) from an exported {'position', 'axes'} pose."""
    axes = pose["axes"]
    return _quat_from_basis(*_orthonormal(axes[0], axes[1])), [float(c) for c in pose["position"]]


# ---------------------------------------------------------------------------
# Unreal graph
# ---------------------------------------------------------------------------

def _unit(*names):
    for name in names:
        for prefix in ("RigVMFunction_", "RigUnit_"):
            unit = getattr(unreal, prefix + name, None)
            if unit is not None:
                return unit
    return None


def _vec(v):
    return "(X={:.9g},Y={:.9g},Z={:.9g})".format(*v)


def _quat(q):
    return "(X={:.9g},Y={:.9g},Z={:.9g},W={:.9g})".format(*q)


def _transform(q, t):
    return "(Rotation={},Translation={},Scale3D=(X=1,Y=1,Z=1))".format(_quat(q), _vec(t))


class _Builder:
    """Graph nodes for one driven group."""

    def __init__(self, context, base):
        from . import driver_ops, graph_utils

        self.context, self.base, self.gu = context, base, graph_utils
        self.ops = driver_ops.OpsGraph(context, base + "_Ops")
        self.driver_ops = driver_ops
        self.count = 0

    def node(self, names, suffix):
        unit = _unit(*names)
        if unit is None:
            raise RuntimeError(f"Control Rig node '{names[0]}' is not available in this engine build")
        name = f"{self.base}_{self.count:02d}_{suffix}"
        self.count += 1
        self.gu.create_unit_node(self.context.graph_controller, self.context.model, name, unit, unreal.Vector2D(0, 0))
        return name

    def set(self, node, pin, value):
        path = f"{node}.{pin}"
        if not self.gu.pin_exists(self.context.model, path):
            raise RuntimeError(f"{node} has no pin '{pin}'")
        self.gu.set_pin_default(self.context.graph_controller, self.context.model, path, value)

    def link(self, source, node, pin):
        path = f"{node}.{pin}"
        if not (self.gu.pin_exists(self.context.model, path)
                and self.gu.connect_pins(self.context.graph_controller, self.context.model, source, path)):
            raise RuntimeError(f"could not connect {source} -> {path}")

    def channel(self, group, channel):
        """Float pin of a driven channel (UI units), or None when not driven."""
        driver = (group.get("driven") or {}).get(channel)
        if not driver:
            return None
        return self.driver_ops.driver_pin(self.context, f"{self.base}_{channel}", driver)

    def rotation(self, group):
        """Quaternion pin: rotateAxis, then the rotation in rotate order, then jointOrient."""
        rest = group["rest"]
        constant = [0.0, 0.0, 0.0, 1.0]
        pin = None
        for index, (letter, degrees) in enumerate(rotation_sequence(group, rest)):
            is_channel = group.get("rotate_axis") is not None and 3 <= index < 6
            driven = self.channel(group, "rotate" + letter.upper()) if is_channel else None
            if driven is None:
                step = axis_rotation(group, letter, degrees)
                if pin is None:
                    constant = q_mul(step, constant)
                else:
                    mul = self.node(("MathQuaternionMul",), "QMul")
                    self.set(mul, "A", _quat(step))
                    self.link(pin, mul, "B")
                    pin = f"{mul}.Result"
                continue
            angle = self.ops.binary("Mul", driven, -math.pi / 180.0)
            make = self.node(("MathQuaternionFromAxisAndAngle",), "QAxis")
            self.set(make, "Axis", _vec(group["axes_unreal"][letter]))
            self.link(angle, make, "Angle")
            mul = self.node(("MathQuaternionMul",), "QMul")
            self.link(f"{make}.Result", mul, "A")
            if pin is None:
                self.set(mul, "B", _quat(constant))
            else:
                self.link(pin, mul, "B")
            pin = f"{mul}.Result"
        return pin, constant

    def translation(self, group):
        """Vector pin: rest translation plus each driven channel's change."""
        rest = group["rest"]
        scale = float(group.get("unit_scale", 1.0))
        base_q, base_t = local_unreal(group, rest)
        pin = None
        for channel in _TRANSLATE:
            driven = self.channel(group, channel)
            if driven is None:
                continue
            delta = self.ops.binary("Add", driven, -float(rest[channel]))
            axis = group["axes_unreal"][channel[-1].lower()]
            scaled = self.node(("MathVectorScale",), "VScale")
            self.set(scaled, "Value", _vec([c * scale for c in axis]))
            self.link(delta, scaled, "Factor")
            add = self.node(("MathVectorAdd",), "VAdd")
            self.link(f"{scaled}.Result", add, "A")
            if pin is None:
                self.set(add, "B", _vec(base_t))
            else:
                self.link(pin, add, "B")
            pin = f"{add}.Result"
        return pin, base_t


def _ue_transform_to_plain(transform):
    from . import graph_utils

    q = graph_utils.get_transform_rotation(transform)
    t = graph_utils.transform_to_location(transform)
    return [q.x, q.y, q.z, q.w], [t.x, t.y, t.z]


def build_group(context, control_label, group, parent_key):
    """Null + graph for one driven group under ``parent_key``. Returns the null key."""
    from . import graph_utils

    rest_world = pose_to_transform(group["rest_world"])
    world = unreal.Transform(location=unreal.Vector(*rest_world[1]))
    world.rotation = unreal.Quat(*rest_world[0])
    name = f"RB_{graph_utils.sanitize_name(control_label)}_{graph_utils.sanitize_name(group['name'])}"
    null = graph_utils.create_follow_null(context.hierarchy, context.hierarchy_controller, name, world, parent_key)
    if not null:
        raise RuntimeError(f"null '{name}' could not be created")
    if parent_key is not None and graph_utils.is_valid_key(context.hierarchy, parent_key):
        parent_rest = _ue_transform_to_plain(context.hierarchy.get_global_transform(parent_key, True))
    else:
        parent_rest = ([0.0, 0.0, 0.0, 1.0], [0.0, 0.0, 0.0])
    constant = compose(compose(inverse(local_unreal(group, group["rest"])), rest_world), inverse(parent_rest))

    builder = _Builder(context, f"{NODE_PREFIX}{graph_utils.sanitize_name(control_label)}_"
                                f"{graph_utils.sanitize_name(group['name'])}")
    rotation_pin, rotation_constant = builder.rotation(group)
    translation_pin, translation_constant = builder.translation(group)
    make = builder.node(("MathTransformMake",), "Make")
    if rotation_pin:
        builder.link(rotation_pin, make, "Rotation")
    else:
        builder.set(make, "Rotation", _quat(rotation_constant))
    if translation_pin:
        builder.link(translation_pin, make, "Translation")
    else:
        builder.set(make, "Translation", _vec(translation_constant))
    absolute = builder.node(("MathTransformMakeAbsolute",), "Offset")
    builder.link(f"{make}.Result", absolute, "Local")
    builder.set(absolute, "Parent", _transform(*constant))
    setter = builder.node(("SetTransform",), "Set")
    graph_utils.set_key_pin(context.graph_controller, context.model, setter, ["Item"], "Null", null)
    graph_utils.set_any_pin(context.graph_controller, context.model, setter, ["Space"], "LocalSpace")
    graph_utils.set_any_pin(context.graph_controller, context.model, setter, ["bInitial", "Initial"], "False")
    graph_utils.set_any_pin(context.graph_controller, context.model, setter, ["Weight"], "1.0")
    builder.link(f"{absolute}.Global", setter, "Value")
    tail = context.get_exec_tail() or graph_utils.find_forwards_solve_node_name(context.model)
    graph_utils.connect_exec(context.graph_controller, context.model, tail, setter)
    context.set_exec_tail(setter)
    return unreal.RigElementKey(type=unreal.RigElementType.NULL, name=str(null))


def insert_groups(context, record, parent_key):
    """Build the record's driven groups (outermost first) under ``parent_key``;
    returns the key the control should hang from. Groups that cannot be
    built are reported and skipped (the control then hangs from what was
    built so far)."""
    groups = [g for g in (record.get("offset_stack") or []) if g.get("kind") == "driven"]
    label = str(record.get("ue_control_name") or record.get("name") or "control")
    for group in reversed(groups):          # the stack is nearest-first
        for problem in group.get("problems") or []:
            context._warn(f"Offset group '{group['name']}' of '{label}': {problem}.")
        if not group.get("driven"):
            continue
        try:
            parent_key = build_group(context, label, group, parent_key)
            channels = ", ".join(f"{c} <- {d['control']}.{d['attr']}" for c, d in group["driven"].items())
            print(f"[RigBuilder] Controller '{label}': driven offset group '{group['name']}' ({channels}).")
        except Exception as exc:
            context._warn(f"Offset group '{group['name']}' of '{label}' not rebuilt ({exc}); it stays static.")
    return parent_key
