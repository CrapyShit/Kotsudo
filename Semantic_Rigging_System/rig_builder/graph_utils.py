import math
from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)

from . import control_shapes


def make_key(elem_type, name):
    return unreal.RigElementKey(type=elem_type, name=str(name))


def transform_to_location(transform):
    for attr_name in ("translation", "location"):
        if hasattr(transform, attr_name):
            return getattr(transform, attr_name)
        try:
            return transform.get_editor_property(attr_name)
        except Exception:
            continue

    return unreal.Vector(0.0, 0.0, 0.0)


def vector_add(lhs, rhs):
    return unreal.Vector(float(lhs.x) + float(rhs.x), float(lhs.y) + float(rhs.y), float(lhs.z) + float(rhs.z))


def vector_sub(lhs, rhs):
    return unreal.Vector(float(lhs.x) - float(rhs.x), float(lhs.y) - float(rhs.y), float(lhs.z) - float(rhs.z))


def vector_scale(vector, scalar):
    return unreal.Vector(float(vector.x) * scalar, float(vector.y) * scalar, float(vector.z) * scalar)


def vector_dot(lhs, rhs):
    return float(lhs.x) * float(rhs.x) + float(lhs.y) * float(rhs.y) + float(lhs.z) * float(rhs.z)


def vector_cross(lhs, rhs):
    return unreal.Vector(
        float(lhs.y) * float(rhs.z) - float(lhs.z) * float(rhs.y),
        float(lhs.z) * float(rhs.x) - float(lhs.x) * float(rhs.z),
        float(lhs.x) * float(rhs.y) - float(lhs.y) * float(rhs.x),
    )


def vector_length(vector):
    return vector_dot(vector, vector) ** 0.5


def normalize_vector(vector):
    length = vector_length(vector)
    if length < 1e-6:
        return unreal.Vector(0.0, 0.0, 0.0)
    return vector_scale(vector, 1.0 / length)


def make_identity_quat():
    return unreal.Quat(0.0, 0.0, 0.0, 1.0)


def get_transform_rotation(transform):
    if hasattr(transform, "rotation"):
        return transform.rotation

    try:
        return transform.get_editor_property("rotation")
    except Exception:
        return make_identity_quat()


def get_chain_direction(hierarchy, chain, index):
    if not chain:
        return unreal.Vector(1.0, 0.0, 0.0)

    bone_transform = get_bone_global_transform(hierarchy, chain[index])
    bone_rotation = get_transform_rotation(bone_transform)

    if len(chain) == 1:
        return bone_rotation.get_axis_x() if hasattr(bone_rotation, "get_axis_x") else unreal.Vector(1.0, 0.0, 0.0)

    if index < len(chain) - 1:
        start_position = get_bone_global_position(hierarchy, chain[index])
        end_position = get_bone_global_position(hierarchy, chain[index + 1])
    else:
        start_position = get_bone_global_position(hierarchy, chain[index - 1])
        end_position = get_bone_global_position(hierarchy, chain[index])

    direction = normalize_vector(vector_sub(end_position, start_position))
    if vector_length(direction) < 1e-6:
        return bone_rotation.get_axis_x() if hasattr(bone_rotation, "get_axis_x") else unreal.Vector(1.0, 0.0, 0.0)

    return direction


def quat_from_to(start_vector, end_vector):
    start = normalize_vector(start_vector)
    end = normalize_vector(end_vector)
    if vector_length(start) < 1e-6 or vector_length(end) < 1e-6:
        return make_identity_quat()

    dot_value = max(-1.0, min(1.0, vector_dot(start, end)))
    if dot_value > 1.0 - 1e-6:
        return make_identity_quat()

    if dot_value < -1.0 + 1e-6:
        orthogonal = vector_cross(unreal.Vector(1.0, 0.0, 0.0), start)
        if vector_length(orthogonal) < 1e-6:
            orthogonal = vector_cross(unreal.Vector(0.0, 1.0, 0.0), start)
        orthogonal = normalize_vector(orthogonal)
        return unreal.Quat(float(orthogonal.x), float(orthogonal.y), float(orthogonal.z), 0.0)

    cross_value = vector_cross(start, end)
    scale = math.sqrt((1.0 + dot_value) * 2.0)
    inverse_scale = 1.0 / scale
    rotation = unreal.Quat(
        float(cross_value.x) * inverse_scale,
        float(cross_value.y) * inverse_scale,
        float(cross_value.z) * inverse_scale,
        scale * 0.5,
    )
    if hasattr(rotation, "normalize"):
        rotation.normalize()
    return rotation


def get_control_shape_rotation(control_transform, chain_direction, shape_normal_axis=None):
    desired_world_normal = normalize_vector(chain_direction)
    if vector_length(desired_world_normal) < 1e-6:
        return make_identity_quat()

    shape_normal_axis = shape_normal_axis or unreal.Vector(0.0, 0.0, 1.0)

    control_rotation = get_transform_rotation(control_transform)
    if hasattr(control_rotation, "inversed") and hasattr(control_rotation, "rotate_vector"):
        desired_local_normal = normalize_vector(control_rotation.inversed().rotate_vector(desired_world_normal))
    else:
        desired_local_normal = desired_world_normal

    return quat_from_to(shape_normal_axis, desired_local_normal)


def invalid_key():
    return unreal.RigElementKey()


def is_valid_key(hierarchy, key):
    return isinstance(key, unreal.RigElementKey) and hierarchy.contains(key)


def get_world_parent_key(hierarchy, hierarchy_controller):
    """The generated root null every builder-made control lives under.

    Always the same dedicated null (created on demand, under a user
    "WorldSpace" null when the rig has one), so a rebuild can remove exactly
    what the builder made. Picking "any root null" instead could return a
    follow-space null or a user null.
    """
    generated_root_name = GENERATED_ROOT_NAME
    generated_root_key = make_key(unreal.RigElementType.NULL, generated_root_name)
    if hierarchy.contains(generated_root_key):
        return generated_root_key

    world_key = make_key(unreal.RigElementType.NULL, "WorldSpace")
    created_key = hierarchy_controller.add_null(
        generated_root_name,
        world_key if hierarchy.contains(world_key) else invalid_key(),
        unreal.Transform(),
        True,
        False,
        False,
    )
    if hierarchy.contains(created_key):
        return created_key

    if hierarchy.contains(generated_root_key):
        return generated_root_key

    raise RuntimeError("Control Rig hierarchy has no stable world parent and failed to create one.")


def get_bone_global_position(hierarchy, bone_name):
    bone_key = make_key(unreal.RigElementType.BONE, bone_name)
    if not hierarchy.contains(bone_key):
        raise RuntimeError(f"Bone '{bone_name}' was not found in the Control Rig hierarchy.")

    return transform_to_location(hierarchy.get_global_transform(bone_key, initial=True))


def get_bone_global_transform(hierarchy, bone_name):
    bone_key = make_key(unreal.RigElementType.BONE, bone_name)
    if not hierarchy.contains(bone_key):
        raise RuntimeError(f"Bone '{bone_name}' was not found in the Control Rig hierarchy.")

    return hierarchy.get_global_transform(bone_key, initial=True)


def compute_chain_scale(hierarchy, chain, fraction=0.30, multiplier=1.0):
    """Return a uniform control scale proportional to the skeleton's bone lengths.

    The scale equals the average bone-segment length in the chain multiplied by
    ``fraction`` and then by the artist-supplied ``multiplier`` (from the recipe's
    ControlScale field, treated as a plain number, defaulting to 1.0).

    This keeps controls visually proportional on any skeleton -- a 10-unit test
    rig and a 200-unit production character both get correctly-sized gizmos.
    """
    if len(chain) < 2:
        # Single bone: fall back to a fraction of its distance from the world origin.
        pos = get_bone_global_position(hierarchy, chain[0])
        origin_dist = vector_length(pos)
        raw = max(origin_dist * fraction, 1.0)
        return round(raw * float(multiplier), 4)

    total_length = 0.0
    for i in range(len(chain) - 1):
        seg = vector_sub(
            get_bone_global_position(hierarchy, chain[i + 1]),
            get_bone_global_position(hierarchy, chain[i]),
        )
        total_length += vector_length(seg)

    avg_length = total_length / (len(chain) - 1)
    raw = max(avg_length * fraction, 0.1)
    return round(raw * float(multiplier), 4)


def compute_pole_vector(chain, hierarchy, pole_distance_scale=0.75):
    start_pos = get_bone_global_position(hierarchy, chain[0])
    mid_pos = get_bone_global_position(hierarchy, chain[1])
    end_pos = get_bone_global_position(hierarchy, chain[2])

    ab = vector_sub(mid_pos, start_pos)
    ac = vector_sub(end_pos, start_pos)
    ac_normalized = normalize_vector(ac)

    projection = vector_add(start_pos, vector_scale(ac_normalized, vector_dot(ab, ac_normalized)))
    pole_direction = normalize_vector(vector_sub(mid_pos, projection))

    if vector_length(pole_direction) < 1e-6:
        up_axis = unreal.Vector(0.0, 0.0, 1.0)
        right_axis = unreal.Vector(1.0, 0.0, 0.0)
        pole_direction = normalize_vector(vector_cross(ac_normalized, up_axis))
        if vector_length(pole_direction) < 1e-6:
            pole_direction = normalize_vector(vector_cross(ac_normalized, right_axis))

    limb_length = vector_length(vector_sub(mid_pos, start_pos)) + vector_length(vector_sub(end_pos, mid_pos))
    pole_distance = max(limb_length * pole_distance_scale, 1.0)
    pole_position = vector_add(mid_pos, vector_scale(pole_direction, pole_distance))

    return pole_position


def locked_groups(locked_channels):
    """Channel groups ('translate'/'rotate'/'scale') locked on all three axes.

    Only whole groups are honoured: a UE control's axes are the bone's frame,
    not the Maya controller's, so a single locked Maya axis has no reliable
    Unreal counterpart. Whole-group locks (e.g. an IK/FK switch with every
    transform channel locked) are axis-independent and map exactly.
    """
    locked = {str(c).lower() for c in (locked_channels or [])}
    groups = set()
    for group, prefix in (("translate", "t"), ("rotate", "r"), ("scale", "s")):
        if all(f"{prefix}{axis}" in locked for axis in "xyz"):
            groups.add(group)
    return groups


def channel_lock_limits(locked_channels):
    """limit_enabled list for an EulerTransform control (t xyz, r xyz, s xyz).

    With min == max == identity (see create_control), an enabled limit pins
    the channel: the control can be selected but not moved on that group.
    """
    groups = locked_groups(locked_channels)
    flags = []
    for group in ("translate", "rotate", "scale"):
        on = group in groups
        flags.extend(unreal.RigControlLimitEnabled(on, on) for _ in range(3))
    return flags


def apply_channel_filter(settings, locked_channels):
    """Hide locked channel groups from gizmos/details where the engine supports it."""
    groups = locked_groups(locked_channels)
    if not groups or not hasattr(settings, "filtered_channels"):
        return
    channel_enum = getattr(unreal, "RigControlTransformChannel", None)
    if channel_enum is None:
        return
    names = {
        "translate": ("TRANSLATION_X", "TRANSLATION_Y", "TRANSLATION_Z"),
        "rotate": ("PITCH", "YAW", "ROLL"),
        "scale": ("SCALE_X", "SCALE_Y", "SCALE_Z"),
    }
    allowed = []
    for group, members in names.items():
        if group not in groups:
            allowed.extend(getattr(channel_enum, m) for m in members if hasattr(channel_enum, m))
    try:
        # An empty filter means "all channels" in UE, so a fully locked control
        # keeps the list empty and relies on the limits alone.
        if allowed:
            settings.filtered_channels = allowed
    except Exception:
        pass


def euler_value(loc=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0), scl=(1.0, 1.0, 1.0)):
    euler_transform = unreal.EulerTransform(location=list(loc), rotation=list(rot), scale=list(scl))
    return unreal.RigHierarchy.make_control_value_from_euler_transform(euler_transform)


def unit_scale_transform(source_transform):
    """Copy a transform's location and rotation with scale forced to 1.

    Bone globals can carry import scale. A control must not inherit it: control
    size comes from the shape transform, and a non-unit offset scale would skew
    every child control chained under it.
    """
    result = unreal.Transform(location=transform_to_location(source_transform))
    result.rotation = get_transform_rotation(source_transform)
    result.scale3d = unreal.Vector(1.0, 1.0, 1.0)
    return result


def transform_alignment_error(actual, expected):
    """Return (position_error, rotation_error_degrees) between two transforms."""
    position_error = vector_length(
        vector_sub(transform_to_location(actual), transform_to_location(expected))
    )
    qa = get_transform_rotation(actual)
    qe = get_transform_rotation(expected)
    dot = abs(
        float(qa.x) * float(qe.x) + float(qa.y) * float(qe.y)
        + float(qa.z) * float(qe.z) + float(qa.w) * float(qe.w)
    )
    dot = max(-1.0, min(1.0, dot))
    return position_error, math.degrees(2.0 * math.acos(dot))


def _log_warning(message):
    if unreal is not None and hasattr(unreal, "log_warning"):
        unreal.log_warning(f"[RigBuilder] {message}")


def _log_info(message):
    if unreal is not None and hasattr(unreal, "log"):
        unreal.log(f"[RigBuilder] {message}")


# A control placed on a bone is "aligned" when the read-back global transform
# matches the bone within these tolerances (cm / degrees).
ALIGN_POSITION_TOLERANCE = 0.01
ALIGN_ROTATION_TOLERANCE = 0.05


def _relative_transform_candidates(desired_global_transform, parent_global):
    """Yield candidate parent-local transforms for a desired global transform.

    The Python binding's ``make_relative`` semantics are not the same across
    engine builds, so every candidate is validated by reading the control's
    resulting global transform back from the hierarchy (see place_control).
    """
    for method_name in ("make_relative", "get_relative_transform"):
        method = getattr(desired_global_transform, method_name, None)
        if method is None:
            continue
        try:
            yield method_name, method(parent_global)
        except Exception:
            continue


def place_control(hierarchy, control_key, parent_key, desired_global_transform, label=None):
    """Place a control so its initial global transform equals the given one.

    The FULL transform (translation AND rotation) is written into the control's
    offset, with the animatable value left at identity. That way the control's
    resting global transform is the bone's bind pose, so driving the bone from
    the control in GlobalSpace reproduces the bind pose exactly. Writing only
    the translation leaves the control at world/parent orientation and every
    driven bone loses its bind rotation, which tears the skinned mesh.

    Each candidate placement is verified against the hierarchy's read-back
    global transform; the first one within tolerance wins. Returns
    (position_error, rotation_error_degrees) of the final placement.
    """
    label = label or str(getattr(control_key, "name", control_key))
    parent_global = (
        hierarchy.get_global_transform(parent_key, initial=True)
        if is_valid_key(hierarchy, parent_key)
        else None
    )

    candidates = []
    if parent_global is None:
        candidates.append(("world", desired_global_transform))
    else:
        candidates.extend(_relative_transform_candidates(desired_global_transform, parent_global))

    best = None
    for strategy, local_offset in candidates:
        hierarchy.set_control_offset_transform(control_key, local_offset, True, True)
        hierarchy.set_control_offset_transform(control_key, local_offset, False, True)
        actual = hierarchy.get_global_transform(control_key, initial=True)
        errors = transform_alignment_error(actual, desired_global_transform)
        if best is None or (errors[1], errors[0]) < (best[1][1], best[1][0]):
            best = (strategy, errors, local_offset)
        if errors[0] <= ALIGN_POSITION_TOLERANCE and errors[1] <= ALIGN_ROTATION_TOLERANCE:
            return errors

    # Last resort: let the hierarchy solve it.
    try:
        hierarchy.set_global_transform(control_key, desired_global_transform, True, True)
        actual = hierarchy.get_global_transform(control_key, initial=True)
        errors = transform_alignment_error(actual, desired_global_transform)
        if best is None or (errors[1], errors[0]) < (best[1][1], best[1][0]):
            best = ("set_global_transform", errors, None)
        if errors[0] <= ALIGN_POSITION_TOLERANCE and errors[1] <= ALIGN_ROTATION_TOLERANCE:
            return errors
    except Exception:
        pass

    if best is not None and best[2] is not None:
        hierarchy.set_control_offset_transform(control_key, best[2], True, True)
        hierarchy.set_control_offset_transform(control_key, best[2], False, True)
    errors = best[1] if best else (0.0, 0.0)
    _log_warning(
        f"Control '{label}' could not be aligned to its bone "
        f"(best strategy '{best[0] if best else 'none'}': position error "
        f"{errors[0]:.4f}, rotation error {errors[1]:.2f} deg). Driven bones "
        "will not hold their bind pose."
    )
    return errors


def global_to_parent_local_transform(
    hierarchy, parent_key, desired_global_transform, translation_only=False
):
    """Convert a hierarchy-global position to the control parent's local space.

    Used for controls that only need a position (spline/pole controls); their
    local rotation stays identity and inherits the parent orientation. Controls
    that must match a bone's orientation go through ``place_control`` instead.
    """
    if not is_valid_key(hierarchy, parent_key):
        return desired_global_transform

    parent_global = hierarchy.get_global_transform(parent_key, initial=True)
    desired_location = transform_to_location(desired_global_transform)
    if hasattr(parent_global, "inverse_transform_location"):
        local_location = parent_global.inverse_transform_location(desired_location)
    elif hasattr(unreal, "MathLibrary"):
        local_location = unreal.MathLibrary.inverse_transform_location(parent_global, desired_location)
    else:
        local_location = desired_location
    return unreal.Transform(location=local_location)


def create_control(
    hierarchy,
    hierarchy_controller,
    parent_key,
    control_name,
    position,
    color,
    shape_scale,
    shape_name="Circle_Thick",
    shape_rotation=None,
    global_transform=None,
    locked_channels=None,
    display_name=None,
):
    control_key = make_key(unreal.RigElementType.CONTROL, control_name)
    control_settings = unreal.RigControlSettings()
    control_settings.primary_axis = unreal.RigControlAxis.X
    control_settings.maximum_value = euler_value()
    control_settings.minimum_value = euler_value()
    control_settings.limit_enabled = channel_lock_limits(locked_channels)
    apply_channel_filter(control_settings, locked_channels)
    control_settings.is_transient_control = False
    control_settings.shape_visible = True
    if shape_name is not None:
        control_settings.shape_name = shape_name
    control_settings.shape_color = color
    control_settings.draw_limits = False
    control_settings.display_name = display_name or "None"
    control_settings.control_type = unreal.RigControlType.EULER_TRANSFORM
    control_settings.animation_type = unreal.RigControlAnimationType.ANIMATION_CONTROL

    if not hierarchy.contains(control_key):
        hierarchy_controller.add_control(control_name, parent_key, control_settings, euler_value())
        if not hierarchy.contains(control_key):
            raise RuntimeError(
                f"Failed to create control '{control_name}'. "
                f"Check for a name collision or an invalid control shape: {shape_name!r}."
            )
    else:
        if hasattr(hierarchy_controller, "set_control_settings"):
            hierarchy_controller.set_control_settings(control_key, control_settings, False)
        current_parent = hierarchy.get_first_parent(control_key)
        if current_parent != parent_key:
            hierarchy_controller.set_parent(control_key, parent_key, True, False, False)

    # Reset every stored value first so no stale pose from an earlier build
    # (or a previous set_global_transform) survives on top of the new offset.
    for value_type_name in ("INITIAL", "CURRENT", "MINIMUM", "MAXIMUM"):
        value_type = getattr(unreal.RigControlValueType, value_type_name, None)
        if value_type is not None:
            hierarchy.set_control_value(control_key, euler_value(), value_type)

    if global_transform is not None:
        # Full bone-aligned placement: rotation goes into the offset, verified
        # by read-back. Scale is normalised so it never leaks into children.
        place_control(
            hierarchy, control_key, parent_key,
            unit_scale_transform(global_transform), label=control_name,
        )
    else:
        local_offset = global_to_parent_local_transform(
            hierarchy,
            parent_key,
            unreal.Transform(location=position),
            translation_only=True,
        )
        # Control offsets are parent-local. Set both initial and current offsets
        # so rebuilds do not retain a stale current offset from an earlier
        # hierarchy.
        hierarchy.set_control_offset_transform(control_key, local_offset, True, True)
        hierarchy.set_control_offset_transform(control_key, local_offset, False, True)

    shape_transform = unreal.Transform()
    if shape_rotation is not None:
        shape_transform.rotation = shape_rotation
    shape_transform.scale3d = unreal.Vector(float(shape_scale[0]), float(shape_scale[1]), float(shape_scale[2]))

    hierarchy.set_control_shape_transform(control_key, shape_transform, True)
    hierarchy.set_control_shape_transform(control_key, shape_transform, False)
    return control_key


def find_forwards_solve_node_name(model):
    for node in model.get_nodes():
        if hasattr(node, "get_node_title") and node.get_node_title() == "Forwards Solve":
            return node.get_name()

    for node in model.get_nodes():
        if "RigUnit_BeginExecution" in node.get_name():
            return node.get_name()

    return None


def pin_exists(model, pin_path):
    return model.find_pin(pin_path) is not None


def exec_pin(model, node_or_pin):
    """Execution pin of a node, or ``node_or_pin`` itself when it already names
    a pin (e.g. a Sequence output such as "RB_SolveStages.B")."""
    if "." in str(node_or_pin) and pin_exists(model, node_or_pin):
        return node_or_pin
    for name in ("ExecuteContext", "Execute"):
        path = f"{node_or_pin}.{name}"
        if pin_exists(model, path):
            return path
    return f"{node_or_pin}.ExecuteContext"


def connect_exec(controller, model, source, target):
    """Chain execution from ``source`` (node or exec pin) into node ``target``."""
    return connect_pins(controller, model, exec_pin(model, source), exec_pin(model, target))


def set_pin_default(controller, model, pin_path, value):
    if pin_exists(model, pin_path):
        controller.set_pin_default_value(pin_path, value, True)


def set_any_pin(controller, model, node_name, pin_names, value):
    for pin_name in pin_names:
        pin_path = f"{node_name}.{pin_name}"
        if pin_exists(model, pin_path):
            set_pin_default(controller, model, pin_path, value)
            return pin_path
    return None


def set_key_pin(controller, model, node_name, pin_names, item_type, item_name):
    for pin_name in pin_names:
        name_pin_path = f"{node_name}.{pin_name}.Name"
        if pin_exists(model, name_pin_path):
            set_any_pin(controller, model, node_name, [f"{pin_name}.Type"], item_type)
            set_any_pin(controller, model, node_name, [f"{pin_name}.Name"], item_name)
            return

    set_any_pin(controller, model, node_name, pin_names, item_name)


def create_unit_node(controller, model, node_name, script_struct, position, method_name="Execute"):
    existing_node = model.find_node(node_name)
    if existing_node:
        return existing_node

    return controller.add_unit_node(
        script_struct=script_struct.static_struct(),
        method_name=method_name,
        position=position,
        node_name=node_name,
    )


def connect_pins(controller, model, source_pin, target_pin):
    if not pin_exists(model, source_pin) or not pin_exists(model, target_pin):
        return False

    link_repr = f"{source_pin} -> {target_pin}"
    if model.find_link(link_repr) is None:
        controller.add_link(source_pin, target_pin)
    return True


def pick_ik_unit_struct(solver_type):
    preferred_solver = str(solver_type or "").lower()

    if preferred_solver == "basicik":
        candidates = ["RigUnit_BasicIK", "RigUnit_TwoBoneIKSimple", "RigUnit_TwoBoneIK", "RigUnit_TwoBoneIKFK"]
    else:
        candidates = ["RigUnit_TwoBoneIKSimple", "RigUnit_TwoBoneIK", "RigUnit_TwoBoneIKFK", "RigUnit_BasicIK"]

    for candidate in candidates:
        if hasattr(unreal, candidate):
            return getattr(unreal, candidate)

    raise RuntimeError("Could not find a supported IK unit in this Unreal Python API.")


def sanitize_name(name):
    safe_chars = []
    for char in str(name):
        safe_chars.append(char if (char.isalnum() or char == "_") else "_")
    return "".join(safe_chars).strip("_") or "Module"


# ---------------------------------------------------------------------------
# Node-type-tolerant helpers, shared by IKModule and IKFKModule.
#
# UE 5.6 can create RigUnit_TwoBoneIKSimple while displaying the node's
# title in the graph as "Basic IK" rather than "Two Bone IK" -- these
# helpers were proven out in IKFKModule and are promoted here so both
# modules use one implementation instead of two copies drifting apart.
# ---------------------------------------------------------------------------

def title_matches_expected(title, expected_title_contains) -> bool:
    """Return True if a node title matches one accepted title pattern.

    Accepted formats:
        "fabrik"                         -> substring match
        ("two", "ik")                    -> all words must be present
        (("two", "ik"), ("basic", "ik")) -> any option may match
    """
    title_lower = str(title).lower()

    if expected_title_contains is None:
        return True

    if isinstance(expected_title_contains, str):
        return expected_title_contains.lower() in title_lower

    try:
        items = list(expected_title_contains)
    except TypeError:
        return str(expected_title_contains).lower() in title_lower

    if not items:
        return True

    if all(isinstance(item, str) for item in items):
        return all(item.lower() in title_lower for item in items)

    for item in items:
        if isinstance(item, str):
            if item.lower() in title_lower:
                return True
            continue
        try:
            words = list(item)
        except TypeError:
            if str(item).lower() in title_lower:
                return True
            continue
        if all(str(word).lower() in title_lower for word in words):
            return True

    return False


def remove_stale_node_if_wrong_type(controller, model, node_name, expected_title_contains):
    """Remove an existing node if it clearly has the wrong type/title.

    Keeps rebuilds safe when the same module name changes solver type
    (e.g. FABRIK <-> TwoBoneIK) between runs.
    """
    node = model.find_node(node_name)
    if not node or not hasattr(node, "get_node_title"):
        return

    title = str(node.get_node_title())
    if title_matches_expected(title, expected_title_contains):
        return

    if hasattr(unreal, "log_warning"):
        unreal.log_warning(
            f"[RigBuilder] Removing stale node '{node_name}' with title '{title}'. "
            f"Expected {expected_title_contains!r}."
        )

    for remove_method in ("remove_node", "remove_node_by_name"):
        if hasattr(controller, remove_method):
            try:
                arg = node if remove_method == "remove_node" else node_name
                getattr(controller, remove_method)(arg)
                return
            except Exception:
                continue


def verify_node_title(node_name, model, expected_options=None) -> bool:
    """Check a node's title without aborting the build; only logs a warning."""
    node = model.find_node(node_name)
    if not node or not hasattr(node, "get_node_title"):
        return True

    title = str(node.get_node_title())
    if title_matches_expected(title, expected_options):
        return True

    if hasattr(unreal, "log_warning"):
        unreal.log_warning(
            f"[RigBuilder] Node '{node_name}' has title '{title}', expected "
            f"{expected_options!r}. Continuing; pin wiring will fail later if "
            "this is truly the wrong node type."
        )
    return False


def pick_fabrik_struct():
    """Return the FABRIK unit struct class, or None for struct-path fallback."""
    for candidate in ("RigUnit_FABRIK", "RigUnit_Fabrik", "RigUnit_BasicFabrik"):
        if hasattr(unreal, candidate):
            return getattr(unreal, candidate)
    return None


def pick_two_bone_ik_struct():
    """Return the Two Bone IK unit struct class for UE Control Rig.

    May display in the graph as "Basic IK" -- see title_matches_expected.
    """
    for candidate in ("RigUnit_TwoBoneIKSimple",):
        if hasattr(unreal, candidate):
            return getattr(unreal, candidate)
    raise RuntimeError(
        "Could not find RigUnit_TwoBoneIKSimple in this Unreal Python API. "
        "For UE 5.6 this class should exist in the ControlRig module."
    )


def connect_first_available(controller, model, source_pin, target_pins):
    """Try connecting source_pin to each target_pin in order; stop at first success."""
    for target_pin in target_pins:
        if connect_pins(controller, model, source_pin, target_pin):
            return True
    return False


def connect_transform_translation_to_vector_pin(controller, model, get_transform_node, vector_pin):
    """Connect a GetControlTransform translation/location sub-pin to a vector pin."""
    source_candidates = (
        f"{get_transform_node}.Transform.Translation",
        f"{get_transform_node}.Transform.Location",
        f"{get_transform_node}.Transform.Position",
    )
    for source_pin in source_candidates:
        if connect_pins(controller, model, source_pin, vector_pin):
            return True
    return False


def set_vector_pin(controller, model, pin_path, vector):
    """Set an FVector-style pin by sub-pins when possible, else compound default."""
    values = {"X": float(vector.x), "Y": float(vector.y), "Z": float(vector.z)}

    found_subpins = False
    for axis, value in values.items():
        sub_pin = f"{pin_path}.{axis}"
        if pin_exists(model, sub_pin):
            set_pin_default(controller, model, sub_pin, str(value))
            found_subpins = True

    if found_subpins:
        return True

    if pin_exists(model, pin_path):
        set_pin_default(
            controller, model, pin_path,
            f"(X={values['X']},Y={values['Y']},Z={values['Z']})",
        )
        return True

    return False


def recipe_vector(value, fallback):
    """Parse a vector from recipe data: Unreal Vector, list/tuple, dict, or string."""
    if value is None:
        return fallback

    if hasattr(value, "x") and hasattr(value, "y") and hasattr(value, "z"):
        return unreal.Vector(float(value.x), float(value.y), float(value.z))

    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return unreal.Vector(float(value[0]), float(value[1]), float(value[2]))

    if isinstance(value, dict):
        x = value.get("X", value.get("x", fallback.x))
        y = value.get("Y", value.get("y", fallback.y))
        z = value.get("Z", value.get("z", fallback.z))
        return unreal.Vector(float(x), float(y), float(z))

    if isinstance(value, str):
        cleaned = value.strip().replace("(", "").replace(")", "")
        if "=" in cleaned:
            parts = {}
            for item in cleaned.split(","):
                if "=" in item:
                    key, raw = item.split("=", 1)
                    parts[key.strip().lower()] = float(raw.strip())
            if {"x", "y", "z"}.issubset(parts.keys()):
                return unreal.Vector(parts["x"], parts["y"], parts["z"])
        else:
            pieces = [p.strip() for p in cleaned.split(",")]
            if len(pieces) >= 3:
                return unreal.Vector(float(pieces[0]), float(pieces[1]), float(pieces[2]))

    return fallback


def recipe_bool(value, fallback=False):
    if value is None:
        return bool(fallback)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}
    return bool(fallback)


def source_vector_to_unreal(value, coordinate_system=None, apply_unit_scale=False):
    """Convert raw DCC metadata to Unreal coordinates.

    FBX converts the skeleton, but custom JSON strings remain untouched. This
    helper mirrors the Maya exporter mapping and also supports older manifests
    that do not yet contain an explicit ``coordinate_system`` block.
    """
    vector = recipe_vector(value, None)
    if vector is None:
        return None

    coordinate_system = dict(coordinate_system or {})
    source_app = str(
        coordinate_system.get("source_application") or "Maya"
    ).strip().lower()
    source_up = str(
        coordinate_system.get("source_up_axis") or "Y"
    ).strip().lower()

    x, y, z = float(vector.x), float(vector.y), float(vector.z)
    if source_app == "maya":
        # Mirrors the FBX importer: to Z-up, then flip Y (right- to
        # left-handed). Must be a reflection; see the Maya exporter.
        if source_up == "z":
            converted = unreal.Vector(x, -y, z)
        else:
            converted = unreal.Vector(x, z, y)
    else:
        converted = unreal.Vector(x, y, z)

    if not apply_unit_scale:
        return converted

    unit = str(
        coordinate_system.get("source_linear_unit") or "cm"
    ).strip().lower()
    scale = {
        "mm": 0.1,
        "millimeter": 0.1,
        "millimeters": 0.1,
        "cm": 1.0,
        "centimeter": 1.0,
        "centimeters": 1.0,
        "m": 100.0,
        "meter": 100.0,
        "meters": 100.0,
        "in": 2.54,
        "inch": 2.54,
        "inches": 2.54,
        "ft": 30.48,
        "foot": 30.48,
        "feet": 30.48,
        "yd": 91.44,
        "yard": 91.44,
        "yards": 91.44,
    }.get(unit, 1.0)
    return vector_scale(converted, scale)


def inverse_transform_direction(transform, direction):
    """Transform a world-space direction into transform-local space."""
    for method_name in ("inverse_transform_vector_no_scale", "inverse_transform_vector"):
        method = getattr(transform, method_name, None)
        if method:
            try:
                return method(direction)
            except Exception:
                pass

    math_library = getattr(unreal, "MathLibrary", None)
    if math_library:
        for method_name in ("inverse_transform_direction", "inverse_transform_vector"):
            method = getattr(math_library, method_name, None)
            if method:
                try:
                    return method(transform, direction)
                except Exception:
                    pass

    rotation = get_transform_rotation(transform)
    if hasattr(rotation, "inversed") and hasattr(rotation, "rotate_vector"):
        try:
            return rotation.inversed().rotate_vector(direction)
        except Exception:
            pass
    return direction


def derive_two_bone_axes(
    hierarchy,
    chain,
    pole_world_position,
    fallback_primary=None,
    fallback_secondary=None,
):
    """Derive Basic IK's local axes from the imported UE reference pose.

    This is safer than blindly applying Maya local-axis numbers because FBX
    converts joint bases while leaving JSON metadata unchanged. The exported
    per-leg axes remain valid fallbacks, but the actual imported skeleton is
    the source of truth whenever it provides a usable chain and PV location.
    """
    fallback_primary = fallback_primary or unreal.Vector(1.0, 0.0, 0.0)
    fallback_secondary = fallback_secondary or unreal.Vector(0.0, 1.0, 0.0)
    if len(chain) < 2:
        return fallback_primary, fallback_secondary

    bone_a_transform = get_bone_global_transform(hierarchy, chain[0])
    bone_a_position = transform_to_location(bone_a_transform)
    bone_b_position = get_bone_global_position(hierarchy, chain[1])

    primary_world = normalize_vector(vector_sub(bone_b_position, bone_a_position))
    primary_local = normalize_vector(
        inverse_transform_direction(bone_a_transform, primary_world)
    )
    if vector_length(primary_local) < 1e-6:
        primary_local = normalize_vector(fallback_primary)

    secondary_local = None
    if pole_world_position is not None:
        pole_world_direction = normalize_vector(
            vector_sub(pole_world_position, bone_a_position)
        )
        candidate = inverse_transform_direction(
            bone_a_transform, pole_world_direction
        )
        candidate = vector_sub(
            candidate,
            vector_scale(primary_local, vector_dot(candidate, primary_local)),
        )
        candidate = normalize_vector(candidate)
        if vector_length(candidate) >= 1e-6:
            secondary_local = candidate

    if secondary_local is None:
        candidate = vector_sub(
            fallback_secondary,
            vector_scale(
                primary_local, vector_dot(fallback_secondary, primary_local)
            ),
        )
        secondary_local = normalize_vector(candidate)

    if vector_length(secondary_local) < 1e-6:
        candidates = (
            unreal.Vector(0.0, 1.0, 0.0),
            unreal.Vector(0.0, 0.0, 1.0),
            unreal.Vector(1.0, 0.0, 0.0),
        )
        for candidate in candidates:
            projected = vector_sub(
                candidate,
                vector_scale(primary_local, vector_dot(candidate, primary_local)),
            )
            projected = normalize_vector(projected)
            if vector_length(projected) >= 1e-6:
                secondary_local = projected
                break

    return primary_local, secondary_local


_SIGNED_AXES = (
    ("X", (1.0, 0.0, 0.0)), ("-X", (-1.0, 0.0, 0.0)),
    ("Y", (0.0, 1.0, 0.0)), ("-Y", (0.0, -1.0, 0.0)),
    ("Z", (0.0, 0.0, 1.0)), ("-Z", (0.0, 0.0, -1.0)),
)


def axis_label_to_vector(label):
    for name, values in _SIGNED_AXES:
        if name == str(label).upper():
            return unreal.Vector(*values)
    return None


def derive_chain_primary_axis(hierarchy, chain):
    """Find which local axis of each bone runs along the chain, from the skeleton.

    For every bone with a successor the world direction to that successor is
    taken into the bone's own local frame and snapped to the nearest signed
    axis; the chain's answer is the majority vote. The imported UE reference
    pose is the source of truth: DCC metadata and hard-coded "X" defaults are
    wrong whenever the rig's joints run along Y or Z (a Maya Y-up spine with no
    joint orient runs along +Y), and a solver told the wrong axis twists every
    bone it drives.

    Returns (label, vector, confidence) where confidence is the mean alignment
    (1.0 = every bone points exactly along the axis). Returns (None, None, 0.0)
    for chains with fewer than two bones.
    """
    if len(chain) < 2:
        return None, None, 0.0

    votes = {}
    alignment = {}
    for index in range(len(chain) - 1):
        bone_transform = get_bone_global_transform(hierarchy, chain[index])
        direction = normalize_vector(
            vector_sub(
                get_bone_global_position(hierarchy, chain[index + 1]),
                transform_to_location(bone_transform),
            )
        )
        local = normalize_vector(inverse_transform_direction(bone_transform, direction))
        if vector_length(local) < 1e-6:
            continue
        best_label, best_dot = None, -2.0
        for name, values in _SIGNED_AXES:
            dot = vector_dot(local, unreal.Vector(*values))
            if dot > best_dot:
                best_label, best_dot = name, dot
        votes[best_label] = votes.get(best_label, 0) + 1
        alignment.setdefault(best_label, []).append(best_dot)

    if not votes:
        return None, None, 0.0

    winner = max(votes, key=lambda name: (votes[name], sum(alignment[name])))
    confidence = sum(alignment[winner]) / len(alignment[winner])
    if len(votes) > 1 or confidence < 0.9:
        _log_warning(
            f"Chain {chain[0]}..{chain[-1]}: bones do not agree on one primary axis "
            f"(votes {votes}, alignment {confidence:.2f}); using {winner}."
        )
    return winner, axis_label_to_vector(winner), confidence


def vector_axis_label(vector):
    """Signed axis label ('+X', '-Y'...) within ~37 degrees of a local vector, or None."""
    best, best_dot = None, 0.8
    for name, values in _SIGNED_AXES:
        dot = vector_dot(normalize_vector(vector), unreal.Vector(*values))
        if dot > best_dot:
            best, best_dot = name, dot
    return None if best is None else (best if best.startswith("-") else "+" + best)


def measure_chain_bend_label(hierarchy, chain):
    """Local axis of the first bone pointing toward the bend (mid joint side
    of the start->end line), measured on the imported skeleton, or None."""
    if len(chain) < 3:
        return None
    start = get_bone_global_transform(hierarchy, chain[0])
    p0 = transform_to_location(start)
    p1 = get_bone_global_position(hierarchy, chain[1])
    p2 = get_bone_global_position(hierarchy, chain[2])
    line = vector_sub(p2, p0)
    length_sq = vector_dot(line, line)
    if length_sq < 1e-9:
        return None
    foot = vector_add(p0, vector_scale(line, vector_dot(vector_sub(p1, p0), line) / length_sq))
    bend = vector_sub(inverse_transform_location(start, p1), inverse_transform_location(start, foot))
    if vector_length(bend) < 1e-4:
        return None
    return vector_axis_label(bend)


def check_chain_axes(module_name, chain_axes, measured_aim=None, measured_up=None):
    """Compare the manifest's per-chain axes with the imported skeleton.

    The manifest declares, from Maya, which joint-local axis runs down the
    chain and toward the bend, already mirrored to Unreal's joint convention.
    Agreement confirms the Maya->Unreal joint-frame mapping for this chain;
    a mismatch means the transport assumption is wrong for this rig and is
    reported (the builder keeps using the measured axes).
    """
    if not chain_axes:
        return None
    normalise = lambda label: None if not label else (label if label[0] in "+-" else "+" + label)
    results = []
    for kind, declared, measured in (
        ("aim", chain_axes.get("aim_axis_unreal"), measured_aim),
        ("up", chain_axes.get("up_axis_unreal"), measured_up),
    ):
        declared, measured = normalise(declared), normalise(measured)
        if not declared or not measured:
            continue
        if declared == measured:
            results.append(f"{kind} {declared} ok")
        else:
            _log_warning(
                f"{module_name}: {kind} axis mismatch -- manifest says {declared} "
                f"(Maya {chain_axes.get(kind + '_axis')}), skeleton says {measured}."
            )
            results.append(f"{kind} MISMATCH")
    if results:
        _log_info(f"{module_name}: chain axes " + ", ".join(results) + ".")
    return results


def pick_perpendicular_axis(primary_label, preferred_label=None):
    """Return an axis label perpendicular to ``primary_label``.

    ``preferred_label`` is honoured when it is already perpendicular; otherwise
    the first of Y, Z, X that is not on the primary axis is used.
    """
    primary_letter = str(primary_label or "X").upper().lstrip("-")
    if preferred_label:
        preferred_letter = str(preferred_label).upper().lstrip("-")
        if preferred_letter in ("X", "Y", "Z") and preferred_letter != primary_letter:
            return str(preferred_label).upper()
    for letter in ("Y", "Z", "X"):
        if letter != primary_letter:
            return letter
    return "Y"


# ---------------------------------------------------------------------------
# Controllers whose origin differs from their bone
#
# In Maya an animator control often sits away from the joint it drives (a
# gizmo floating in front of a hand, a pivot set beside a bone) and the bone
# follows it through a maintained-offset constraint. The UE control must sit
# at that same spot, yet the bone still has to be written at ITS OWN place.
# So the control is created at the Maya controller's origin and a hidden
# "driver" null holding the bone's exact transform is parented under it. The
# rig graph then reads the null's global transform instead of the control's:
# the null follows every control move, so bone = control * fixed offset.
# ---------------------------------------------------------------------------

# Offsets shorter than this (cm) are treated as "same origin as the bone".
# Export precision only (offsets are written to 1e-6): any real offset is
# honoured, since the control's origin is the pivot the animator rotates
# about (Murakami's neck controls sit 0.11-0.13 cm off their joints; a
# former 0.5 cm threshold snapped them onto the bone).
ORIGIN_OFFSET_TOLERANCE = 0.001
# Maya->UE mapping is accepted when the reference bone direction agrees within
# this angle (degrees).
ORIGIN_MAPPING_ANGLE_TOLERANCE = 10.0
ORIGIN_LOCAL_LENGTH_TOLERANCE = 0.05   # joint-local reference length vs real bone distance


def controller_records(recipe_data):
    records = (recipe_data or {}).get("ControllerRecords") or []
    return records if isinstance(records, (list, tuple)) else []


def find_controller_record(recipe_data, bone_name, roles):
    """Return the record for ``bone_name`` with one of ``roles``, or None."""
    wanted_roles = {str(role).strip().lower() for role in roles}
    for record in controller_records(recipe_data):
        if str(record.get("role") or "").strip().lower() not in wanted_roles:
            continue
        target = record.get("driven_bone") or record.get("anchor_bone")
        if str(target or "").split("|")[-1] == str(bone_name):
            return record
    return None


def controller_origin_position(hierarchy, record, anchor_bone, min_offset=None, label=None):
    """Return the UE world position of a Maya controller's origin, or None.

    The exporter stores the origin as a displacement from the anchor bone
    (already in UE axes/cm). It is added to the anchor bone's imported position
    after being cross-checked against the imported skeleton: the exported
    anchor->neighbour vector must point the same way as the real one. When it
    does not, the axis mapping is unreliable and None is returned so the
    control safely stays on its bone. A pure unit-scale difference is
    corrected by the measured length ratio.

    ``min_offset`` (cm) defaults to ORIGIN_OFFSET_TOLERANCE; offsets below it
    return None because the control is effectively on the bone already.
    """
    if not record:
        return None
    label = label or str(record.get("name") or anchor_bone)
    threshold = ORIGIN_OFFSET_TOLERANCE if min_offset is None else float(min_offset)

    # Preferred (schema 6): the offset in the anchor bone's OWN frame. No
    # world-axis conversion is involved, so a wrong world mapping cannot
    # affect it; it is validated the same way against a neighbour bone.
    local_result = _local_origin_position(hierarchy, record, anchor_bone, label)
    world_result = _world_origin_position(hierarchy, record, anchor_bone, label)
    # A joint-local offset is only trusted once validated against a neighbour
    # bone (reference_local); single-bone modules have none, so their
    # validated world offset wins.
    if local_result is not None and world_result is not None and not (record.get("reference_local") or {}).get("vector"):
        local_result = None
    result = local_result or world_result
    if local_result is not None and world_result is not None:
        # Two independent encodings of the same point. When they agree the
        # joint-local one is used (no world mapping involved). When they do
        # not, one is corrupt and nothing here can prove which, so the
        # long-standing world path wins and the disagreement is reported --
        # a bad joint-local export can never move a control on its own.
        disagreement = vector_length(vector_sub(local_result[0], world_result[0]))
        if disagreement > max(1.0, 0.02 * vector_length(world_result[1])):
            _log_warning(
                f"Controller '{label}': joint-local and world offsets disagree by "
                f"{disagreement:.2f} cm; using the world one (re-export from Maya)."
            )
            result = world_result
    if result is None:
        return None
    position, offset_length = result[0], vector_length(result[1])
    # A zero threshold means "always use the record" -- including when the
    # controller sits exactly on the bone (offset 0), which is a valid answer.
    if threshold > 0.0 and offset_length <= threshold:
        return None
    return position


def _local_origin_position(hierarchy, record, anchor_bone, label):
    """(world position, world offset) from offset_local, or None."""
    offset = recipe_vector(record.get("offset_local"), None)
    if offset is None:
        return None
    anchor = get_bone_global_transform(hierarchy, anchor_bone)
    reference = record.get("reference_local") or {}
    expected = recipe_vector(reference.get("vector"), None)
    reference_bone = reference.get("bone")
    if reference_bone and expected is not None:
        key = make_key(unreal.RigElementType.BONE, str(reference_bone).split("|")[-1])
        if hierarchy.contains(key):
            actual = inverse_transform_location(
                anchor, transform_to_location(hierarchy.get_global_transform(key, initial=True))
            )
            expected_length, actual_length = vector_length(expected), vector_length(actual)
            if expected_length > 1e-6 and actual_length > 1e-6:
                cosine = vector_dot(normalize_vector(expected), normalize_vector(actual))
                angle = math.degrees(math.acos(max(-1.0, min(1.0, cosine))))
                if angle > ORIGIN_MAPPING_ANGLE_TOLERANCE:
                    _log_warning(
                        f"Controller '{label}': joint-local mapping disagrees with the imported "
                        f"skeleton by {angle:.1f} deg (bone '{anchor_bone}'); not using it."
                    )
                    return None
                # Length too: a joint-local vector is world length on rotated
                # axes, so the bone-to-bone distance must match. A mismatch
                # means a unit error in the export, not a mapping error.
                ratio = expected_length / actual_length
                if abs(ratio - 1.0) > ORIGIN_LOCAL_LENGTH_TOLERANCE:
                    _log_warning(
                        f"Controller '{label}': joint-local reference is {ratio:.3g}x the real "
                        f"distance to '{reference_bone}' (unit error in the export); not using it."
                    )
                    return None
    position = transform_location(anchor, offset)
    return position, vector_sub(position, transform_to_location(anchor))


def inverse_transform_location(transform, location):
    """Transform-local coordinates of a world location."""
    method = getattr(transform, "inverse_transform_location", None)
    if method:
        return method(location)
    return unreal.MathLibrary.inverse_transform_location(transform, location)


def transform_location(transform, local):
    """World location of a transform-local point."""
    method = getattr(transform, "transform_location", None)
    if method:
        return method(local)
    return unreal.MathLibrary.transform_location(transform, local)


def _world_origin_position(hierarchy, record, anchor_bone, label):
    """(world position, world offset) from offset_from_anchor_unreal, or None."""
    offset = recipe_vector(record.get("offset_from_anchor_unreal"), None)
    if offset is None:
        return None

    anchor_position = get_bone_global_position(hierarchy, anchor_bone)
    scale = 1.0

    reference = record.get("reference") or {}
    reference_bone = reference.get("bone")
    expected = recipe_vector(reference.get("unreal_vector"), None)
    if reference_bone and expected is not None:
        reference_key = make_key(unreal.RigElementType.BONE, str(reference_bone).split("|")[-1])
        if hierarchy.contains(reference_key):
            actual = vector_sub(
                transform_to_location(hierarchy.get_global_transform(reference_key, initial=True)),
                anchor_position,
            )
            expected_length = vector_length(expected)
            actual_length = vector_length(actual)
            if expected_length > 1e-6 and actual_length > 1e-6:
                cosine = vector_dot(normalize_vector(expected), normalize_vector(actual))
                angle = math.degrees(math.acos(max(-1.0, min(1.0, cosine))))
                if angle > ORIGIN_MAPPING_ANGLE_TOLERANCE:
                    _log_warning(
                        f"Controller '{label}': exported axes disagree with the imported "
                        f"skeleton by {angle:.1f} deg; keeping the control on bone "
                        f"'{anchor_bone}'."
                    )
                    return None
                scale = actual_length / expected_length

    scaled = vector_scale(offset, scale)
    return vector_add(anchor_position, scaled), scaled


def transform_pin_string(transform):
    """Pin default text for an FTransform."""
    q = get_transform_rotation(transform)
    t = transform_to_location(transform)
    sc = transform.scale3d
    return ("(Rotation=(X={:.9g},Y={:.9g},Z={:.9g},W={:.9g}),Translation=(X={:.9g},Y={:.9g},Z={:.9g}),"
            "Scale3D=(X={:.9g},Y={:.9g},Z={:.9g}))").format(q.x, q.y, q.z, q.w, t.x, t.y, t.z, sc.x, sc.y, sc.z)


def bone_aligned_transform_at(bone_transform, position):
    """Bone rotation (unit scale) placed at ``position``."""
    result = unit_scale_transform(bone_transform)
    result.translation = position
    return result


def create_offset_driver(hierarchy, hierarchy_controller, control_key, driver_name, bone_transform):
    """Create a null under a control that sits exactly on the bone (bind pose).

    Returns the null's name, or None if it could not be created (the caller
    then keeps the control on the bone origin instead).
    """
    if not hasattr(unreal, "RigUnit_GetTransform"):
        return None

    driver_key = make_key(unreal.RigElementType.NULL, driver_name)
    if hierarchy.contains(driver_key):
        try:
            hierarchy_controller.remove_element(driver_key, False, False)
        except Exception:
            pass

    desired = unit_scale_transform(bone_transform)
    try:
        hierarchy_controller.add_null(driver_name, control_key, desired, True, False, False)
    except Exception as exc:
        _log_warning(f"Could not create offset driver '{driver_name}': {exc}")
        return None
    if not hierarchy.contains(driver_key):
        return None

    actual = hierarchy.get_global_transform(driver_key, initial=True)
    position_error, rotation_error = transform_alignment_error(actual, desired)
    if position_error > ALIGN_POSITION_TOLERANCE or rotation_error > ALIGN_ROTATION_TOLERANCE:
        _log_warning(
            f"Offset driver '{driver_name}' is off its bone (position {position_error:.4f}, "
            f"rotation {rotation_error:.2f} deg); keeping the control on the bone origin."
        )
        try:
            hierarchy_controller.remove_element(driver_key, False, False)
        except Exception:
            pass
        return None
    return driver_name


def create_transform_getter(controller, model, node_name, position, control_name, driver_null=None):
    """Create the node that outputs the transform to write onto a bone/effector.

    Reads the driver null when one exists (control origin != bone origin),
    otherwise the control itself. Returns the node name.
    """
    # A rebuild may switch this node between the two types; drop a stale one.
    remove_stale_node_if_wrong_type(
        controller, model, node_name,
        "get transform" if driver_null else "get control transform",
    )
    if driver_null:
        create_unit_node(controller, model, node_name, unreal.RigUnit_GetTransform, position)
        set_key_pin(controller, model, node_name, ["Item"], "Null", driver_null)
        set_any_pin(controller, model, node_name, ["Space"], "GlobalSpace")
        set_any_pin(controller, model, node_name, ["bInitial", "Initial"], "False")
    else:
        create_unit_node(controller, model, node_name, unreal.RigUnit_GetControlTransform, position)
        set_pin_default(controller, model, f"{node_name}.Control", control_name)
        set_pin_default(controller, model, f"{node_name}.Space", "GlobalSpace")
    return node_name


# ---------------------------------------------------------------------------
# Attribute ("settings") controls
#
# A Maya controller exposes settings as custom attributes (IK/FK switch,
# blend amounts, toggles). In Control Rig the equivalent is a float control:
# an animatable slider the graph can read. Every numeric/enum/bool attribute
# becomes one FLOAT control carrying the Maya range and value; enum and bool
# attributes keep their integer values (0..N-1 / 0..1).
# ---------------------------------------------------------------------------

def create_float_control(
    hierarchy,
    hierarchy_controller,
    parent_key,
    control_name,
    info,
    position,
    color,
    shape_name="Circle_Thick",
    shape_rotation=None,
    shape_scale=(1.0, 1.0, 1.0),
    shape_visible=True,
):
    """Create (or refresh) a FLOAT control from a Maya attribute description."""
    control_key = make_key(unreal.RigElementType.CONTROL, control_name)
    minimum = float(info.get("min", 0.0))
    maximum = float(info.get("max", 1.0))
    if maximum < minimum:
        minimum, maximum = maximum, minimum
    value = max(minimum, min(maximum, float(info.get("value", info.get("default", minimum)))))

    make_value = unreal.RigHierarchy.make_control_value_from_float
    settings = unreal.RigControlSettings()
    settings.control_type = unreal.RigControlType.FLOAT
    settings.animation_type = unreal.RigControlAnimationType.ANIMATION_CONTROL
    settings.primary_axis = unreal.RigControlAxis.X
    settings.limit_enabled = [unreal.RigControlLimitEnabled(True, True)]
    settings.minimum_value = make_value(minimum)
    settings.maximum_value = make_value(maximum)
    settings.is_transient_control = False
    settings.shape_visible = bool(shape_visible)
    if shape_name is not None:
        settings.shape_name = shape_name
    settings.shape_color = color
    settings.draw_limits = False
    settings.display_name = sanitize_name(info.get("name") or control_name)

    if not hierarchy.contains(control_key):
        hierarchy_controller.add_control(control_name, parent_key, settings, make_value(value))
        if not hierarchy.contains(control_key):
            raise RuntimeError(f"Failed to create attribute control '{control_name}'.")
    else:
        if hasattr(hierarchy_controller, "set_control_settings"):
            hierarchy_controller.set_control_settings(control_key, settings, False)
        if hierarchy.get_first_parent(control_key) != parent_key:
            hierarchy_controller.set_parent(control_key, parent_key, True, False, False)

    local_offset = global_to_parent_local_transform(
        hierarchy, parent_key, unreal.Transform(location=position), translation_only=True
    )
    hierarchy.set_control_offset_transform(control_key, local_offset, True, True)
    hierarchy.set_control_offset_transform(control_key, local_offset, False, True)
    for value_type_name, item in (
        ("INITIAL", value), ("CURRENT", value), ("MINIMUM", minimum), ("MAXIMUM", maximum),
    ):
        value_type = getattr(unreal.RigControlValueType, value_type_name, None)
        if value_type is not None:
            hierarchy.set_control_value(control_key, make_value(item), value_type)

    shape_transform = unreal.Transform()
    if shape_rotation is not None:
        shape_transform.rotation = shape_rotation
    shape_transform.scale3d = unreal.Vector(
        float(shape_scale[0]), float(shape_scale[1]), float(shape_scale[2])
    )
    hierarchy.set_control_shape_transform(control_key, shape_transform, True)
    hierarchy.set_control_shape_transform(control_key, shape_transform, False)
    return control_key


def create_attribute_controls(
    hierarchy, hierarchy_controller, parent_key, record, base_name, position, color,
    shape_name="Circle_Thick", shape_rotation=None, shape_scale=(1.0, 1.0, 1.0),
    attribute_infos=None, show_first_shape=True,
):
    """Create one FLOAT control per attribute of a Maya controller record.

    With ``show_first_shape`` the first control shows the controller's shape
    (this is "the settings control"); the rest are slider-only. Returns
    {attribute_name: control_name}.
    """
    infos = attribute_infos if attribute_infos is not None else (record or {}).get("attributes") or []
    created = {}
    for index, info in enumerate(infos):
        attribute = info.get("name")
        if not attribute:
            continue
        control_name = f"{base_name}_{sanitize_name(attribute)}"
        try:
            create_float_control(
                hierarchy, hierarchy_controller, parent_key, control_name, info,
                position, color, shape_name=shape_name, shape_rotation=shape_rotation,
                shape_scale=shape_scale, shape_visible=(show_first_shape and index == 0),
            )
            created[attribute] = control_name
        except Exception as exc:
            _log_warning(f"Could not create attribute control '{control_name}': {exc}")
    return created


def build_record_control(
    rig, hierarchy, hierarchy_controller, recipe_data, parent_key, control_name,
    anchor_bone, bone_transform, record, color, default_shape, default_scale,
    default_shape_rotation=None, min_offset=None,
):
    """Create the UE control for one bone from its Maya controller record.

    Handles, in one place: the control's origin (at the Maya controller when it
    differs from the bone, with a driver null carrying the bone's transform),
    its shape (custom mesh or built-in fallback), and its custom attributes
    (as slider controls). Without a record this is a plain bone-aligned
    control. Returns (control_key, driver_null_name_or_None).
    """
    origin = controller_origin_position(
        hierarchy, record, anchor_bone, min_offset=min_offset, label=control_name
    )
    bone_position = transform_to_location(bone_transform)
    bone_rotation = get_transform_rotation(bone_transform)
    scale = tuple(default_scale)

    def _make(position, placement_transform):
        shape_name, shape_rotation, shape_scale = control_shapes.resolve_control_shape(
            rig, recipe_data, record, bone_rotation, default_shape, scale, default_shape_rotation
        )
        return create_control(
            hierarchy, hierarchy_controller, parent_key, control_name, position, color,
            shape_scale, shape_name=shape_name, shape_rotation=shape_rotation,
            global_transform=placement_transform,
            locked_channels=(record or {}).get("locked_channels"),
        )

    driver_null = None
    position = bone_position
    if origin is not None:
        control_key = _make(origin, bone_aligned_transform_at(bone_transform, origin))
        driver_null = create_offset_driver(
            hierarchy, hierarchy_controller, control_key, f"{control_name}_Drv", bone_transform
        )
        if driver_null is not None:
            position = origin
        else:
            # No driver possible: keep the control on the bone so the bind
            # pose still holds.
            control_key = _make(bone_position, bone_transform)
    else:
        control_key = _make(bone_position, bone_transform)

    attach_record_attributes(
        hierarchy, hierarchy_controller, control_key, record, control_name, position, color
    )
    return control_key, driver_null


def build_pole_control(context, parent_key, fallback_name, position, record, color, fallback_scale):
    """Pole vector control: Maya name, stock sphere sized like the Maya
    controller, Maya attributes as channels. Returns (control_name, key)."""
    hierarchy = context.hierarchy
    hierarchy_controller = context.hierarchy_controller
    name = context.control_name(record, fallback_name)
    shape = control_shapes.pole_vector_shape()
    scale = control_shapes.builtin_scale_for_size(
        shape, (record or {}).get("size_unreal"), fallback_scale
    )
    key = create_control(
        hierarchy, hierarchy_controller, context.resolve_control_parent(record, parent_key),
        name, position, color, scale,
        shape_name=shape, locked_channels=(record or {}).get("locked_channels"),
    )
    attach_record_attributes(hierarchy, hierarchy_controller, key, record, name, position, color)
    return name, key


def attach_record_attributes(hierarchy, hierarchy_controller, control_key, record,
                             control_name, position, color, infos=None):
    """Recreate a Maya controller's custom attributes on its UE control.

    Animation channels first (the native equivalent); slider float controls
    only for attributes the engine could not create as channels. Returns
    {attribute: ("channel", key_name) | ("control", control_name)}.
    """
    infos = list(infos if infos is not None else (record or {}).get("attributes") or [])
    if not infos:
        return {}
    result = {
        name: ("channel", key)
        for name, key in create_animation_channels(
            hierarchy, hierarchy_controller, control_key, infos
        ).items()
    }
    remaining = [info for info in infos if info.get("name") not in result]
    if remaining:
        controls = create_attribute_controls(
            hierarchy, hierarchy_controller, control_key, record, control_name,
            position, color, attribute_infos=remaining, show_first_shape=False,
        )
        result.update({name: ("control", key) for name, key in controls.items()})
    return result


def create_float_control_getter(controller, model, node_name, control_name, position):
    """Node reading a float control. Returns the output pin path, or None."""
    unit = getattr(unreal, "RigUnit_GetControlFloat", None)
    if unit is None:
        return None
    create_unit_node(controller, model, node_name, unit, position)
    set_pin_default(controller, model, f"{node_name}.Control", control_name)
    for output in ("FloatValue", "Value", "Result"):
        if pin_exists(model, f"{node_name}.{output}"):
            return f"{node_name}.{output}"
    return None


# ---------------------------------------------------------------------------
# Follow spaces
#
# A child module (toes under a foot, fingers under a wrist) normally parents
# its controls to a control of the parent module. For an IK/FK limb that
# control is the FK one, which stays at the FK pose while the IK solver moves
# the bones -- the child then stays behind and stretches the limb. A follow
# space is a null re-written every frame from the parent's FINAL bone
# transform (after the IK/FK solve); children parented to it follow whichever
# mode is active.
# ---------------------------------------------------------------------------

def create_follow_null(hierarchy, hierarchy_controller, space_name, bone_transform, parent_key=None):
    """The null half of a follow space (placed on the bone's bind pose). Returns its name or None."""
    if not (hasattr(unreal, "RigUnit_GetTransform") and hasattr(unreal, "RigUnit_SetTransform")):
        return None
    null_key = make_key(unreal.RigElementType.NULL, space_name)
    if hierarchy.contains(null_key):
        try:
            hierarchy_controller.remove_element(null_key, False, False)
        except Exception:
            pass
    try:
        hierarchy_controller.add_null(
            space_name, parent_key if parent_key is not None else invalid_key(),
            unit_scale_transform(bone_transform), True, False, False,
        )
    except Exception as exc:
        _log_warning(f"Could not create follow space '{space_name}': {exc}")
        return None
    return space_name if hierarchy.contains(null_key) else None


def create_bone_follow_space(
    hierarchy, hierarchy_controller, controller, model, space_name, bone_name,
    bone_transform, position, exec_source,
):
    """Create a null that tracks a bone. Returns (null_name, last_exec_node).

    ``exec_source`` is the exec node after which the update runs (normally the
    module's IK solve). On any failure the original ``exec_source`` is
    returned with a None name, so the module keeps working without the space.
    """
    if not create_follow_null(hierarchy, hierarchy_controller, space_name, bone_transform):
        return None, exec_source
    return space_name, add_follow_update(controller, model, space_name, bone_name, position, exec_source)


def add_follow_update(controller, model, space_name, bone_name, position, exec_source):
    """The update half: copy the bone's current global onto the null. Returns the new exec tail."""
    get_node = f"{space_name}_GetBone"
    set_node = f"{space_name}_Update"
    create_unit_node(controller, model, get_node, unreal.RigUnit_GetTransform, position)
    set_key_pin(controller, model, get_node, ["Item", "Bone", "Child"], "Bone", bone_name)
    set_any_pin(controller, model, get_node, ["Space"], "GlobalSpace")
    set_any_pin(controller, model, get_node, ["bInitial", "Initial"], "False")

    create_unit_node(
        controller, model, set_node, unreal.RigUnit_SetTransform,
        unreal.Vector2D(position.x + 320, position.y),
    )
    set_key_pin(controller, model, set_node, ["Item", "Bone", "Child"], "Null", space_name)
    set_any_pin(controller, model, set_node, ["Space"], "GlobalSpace")
    set_any_pin(controller, model, set_node, ["Initial"], "False")
    set_any_pin(controller, model, set_node, ["Weight"], "1.0")
    set_any_pin(
        controller, model, set_node,
        ["bPropagateToChildren", "PropagateToChildren", "propagate_to_children"], "True",
    )
    if not connect_pins(controller, model, f"{get_node}.Transform", f"{set_node}.Value"):
        connect_pins(controller, model, f"{get_node}.Transform", f"{set_node}.Transform")
    connect_exec(controller, model, exec_source, set_node)
    return set_node


def record_rotation(record):
    """Maya controller world orientation (exported as UE axes) as a Quat, or None."""
    axes = (record or {}).get("world_axes_unreal")
    if not axes or len(axes) != 3:
        return None
    try:
        x_axis, y_axis, z_axis = (normalize_vector(unreal.Vector(*a)) for a in axes)
    except Exception:
        return None
    # Re-orthogonalise (Maya matrices can carry shear/rounding).
    z_axis = normalize_vector(vector_cross(x_axis, y_axis))
    y_axis = normalize_vector(vector_cross(z_axis, x_axis))
    if min(vector_length(v) for v in (x_axis, y_axis, z_axis)) < 1e-6:
        return None
    return control_shapes.quat_from_basis(
        (x_axis.x, x_axis.y, x_axis.z), (y_axis.x, y_axis.y, y_axis.z), (z_axis.x, z_axis.y, z_axis.z)
    )


def record_transform(hierarchy, record, anchor_bone, fallback_transform=None, label=None):
    """Global transform of a Maya controller in UE: its origin and orientation.

    Position from the anchor-relative offset (skeleton-validated), rotation
    from the exported world axes. Missing parts come from ``fallback_transform``
    (or the anchor bone). Returns None when no position can be resolved.
    """
    position = controller_origin_position(hierarchy, record, anchor_bone, min_offset=0.0, label=label)
    fallback = fallback_transform or get_bone_global_transform(hierarchy, anchor_bone)
    if position is None:
        position = transform_to_location(fallback)
    result = unreal.Transform(location=position)
    rotation = record_rotation(record)
    result.rotation = rotation if rotation is not None else get_transform_rotation(fallback)
    result.scale3d = unreal.Vector(1.0, 1.0, 1.0)
    return result


# ---------------------------------------------------------------------------
# Animation channels: Maya custom attributes on a controller
#
# Control Rig's equivalent of "an attribute on a controller" is an animation
# channel: a float child of a control, listed under that control in the
# Details panel, the Anim Outliner and Sequencer (select the control, the
# channel appears there -- it has no viewport gizmo). The graph reads it with
# "Get Float Channel" (RigUnit_GetFloatAnimationChannel: Control + Channel).
# ---------------------------------------------------------------------------

def create_animation_channels(hierarchy, hierarchy_controller, control_key, infos):
    """Add one float channel per Maya attribute under ``control_key``.

    Returns {attribute_name: channel_key_name}. Attributes that cannot be
    created (engine without channels) are left out; callers fall back.
    """
    add_channel = getattr(hierarchy_controller, "add_animation_channel", None)
    if add_channel is None:
        return {}
    make_value = unreal.RigHierarchy.make_control_value_from_float
    created = {}
    for info in infos or []:
        name = info.get("name")
        if not name:
            continue
        minimum = float(info.get("min", 0.0))
        maximum = float(info.get("max", 1.0))
        if maximum < minimum:
            minimum, maximum = maximum, minimum
        value = max(minimum, min(maximum, float(info.get("value", info.get("default", minimum)))))

        settings = unreal.RigControlSettings()
        settings.control_type = unreal.RigControlType.FLOAT
        settings.animation_type = unreal.RigControlAnimationType.ANIMATION_CHANNEL
        settings.limit_enabled = [unreal.RigControlLimitEnabled(True, True)]
        settings.minimum_value = make_value(minimum)
        settings.maximum_value = make_value(maximum)
        settings.display_name = str(name)
        try:
            key = add_channel(str(name), control_key, settings, False, False)
        except TypeError:
            key = add_channel(str(name), control_key, settings)
        except Exception as exc:
            _log_warning(f"Could not add animation channel '{name}' on '{control_key.name}': {exc}")
            continue
        if not key or not hierarchy.contains(key):
            continue
        for value_type_name, item in (
            ("INITIAL", value), ("CURRENT", value), ("MINIMUM", minimum), ("MAXIMUM", maximum),
        ):
            value_type = getattr(unreal.RigControlValueType, value_type_name, None)
            if value_type is not None:
                hierarchy.set_control_value(key, make_value(item), value_type)
        created[str(name)] = str(key.name)
    return created


def create_channel_getter(controller, model, node_name, control_name, channel_name,
                          channel_key_name, position):
    """Node reading an animation channel. Returns the output pin path, or None."""
    unit = getattr(unreal, "RigUnit_GetFloatAnimationChannel", None)
    if unit is not None:
        create_unit_node(controller, model, node_name, unit, position)
        set_pin_default(controller, model, f"{node_name}.Control", control_name)
        set_pin_default(controller, model, f"{node_name}.Channel", channel_name)
        set_any_pin(controller, model, node_name, ["bInitial", "Initial"], "False")
        for output in ("Value", "FloatValue"):
            if pin_exists(model, f"{node_name}.{output}"):
                return f"{node_name}.{output}"
    # Channels are float controls, so the plain float getter works too.
    return create_float_control_getter(controller, model, f"{node_name}_Ctl", channel_key_name, position)


def parent_global_rotation(hierarchy, parent_key):
    """Rotation a position-only control inherits from its parent."""
    if not is_valid_key(hierarchy, parent_key):
        return make_identity_quat()
    return get_transform_rotation(hierarchy.get_global_transform(parent_key, initial=True))


def record_color(record, fallback):
    """LinearColor from a controller record's Maya display colour, else fallback."""
    values = (record or {}).get("display_color")
    if isinstance(values, (list, tuple)) and len(values) >= 3:
        try:
            return unreal.LinearColor(float(values[0]), float(values[1]), float(values[2]), 1.0)
        except Exception:
            pass
    return fallback


GENERATED_ROOT_NAME = "PythonWorldControls"
# Prefix of builder-owned graph nodes/elements that belong to no module
# (solve-stage sequence, follow spaces); cleared with the module prefixes.
BUILDER_PREFIX = "RB"
SOLVE_STAGE_NODE = "RB_SolveStages"


def create_solve_stages(controller, model, forwards_solve, stage_names):
    """Sequence node after Forwards Solve with one exec output per stage.

    Stages run top to bottom (Sequence executes A, then B, ...), so a module
    in a later stage always sees the results of every earlier stage,
    whatever order modules were built in. Returns {stage: exec_pin}, or {}
    when the Sequence unit is unavailable (the caller then keeps one chain).
    """
    unit = None
    for name in ("RigVMFunction_Sequence", "RigUnit_SequenceExecution", "RigUnit_SequenceAggregate"):
        unit = getattr(unreal, name, None)
        if unit is not None:
            break
    if unit is None or not forwards_solve:
        return {}
    try:
        create_unit_node(controller, model, SOLVE_STAGE_NODE, unit, unreal.Vector2D(250, -300))
    except Exception as exc:
        _log_warning(f"Could not create the solve-stage Sequence node ({exc}); using one chain.")
        return {}

    letters = [chr(ord("A") + i) for i in range(26)]

    def outputs():
        return [f"{SOLVE_STAGE_NODE}.{l}" for l in letters if pin_exists(model, f"{SOLVE_STAGE_NODE}.{l}")]

    guard = 0
    while len(outputs()) < len(stage_names) and guard < len(stage_names):
        guard += 1
        try:
            controller.add_aggregate_pin(SOLVE_STAGE_NODE, "", "")
        except Exception:
            break
    pins = outputs()
    if len(pins) < len(stage_names):
        _log_warning(
            f"Solve-stage Sequence has {len(pins)} output(s) for {len(stage_names)} stages; using one chain."
        )
        return {}
    connect_exec(controller, model, forwards_solve, SOLVE_STAGE_NODE)
    return dict(zip(stage_names, pins))


def _element_children(hierarchy, key):
    try:
        return list(hierarchy.get_children(key, False) or [])
    except TypeError:
        return list(hierarchy.get_children(key) or [])


def clear_generated_rig(hierarchy, hierarchy_controller, graph_controller, model, module_prefixes):
    """Remove everything a previous build generated, before rebuilding.

    Removed: every element under the generated root null, root-level nulls
    whose name starts with a module prefix (follow spaces), and graph nodes
    whose name starts with a module prefix. Bones and anything the user built
    by hand are left alone. Without this, renamed or re-typed controls from
    earlier builds stay behind -- and their old SetTransform nodes keep
    writing bones after the new setup.
    Returns (elements_removed, nodes_removed).
    """
    prefixes = tuple(f"{sanitize_name(p)}_" for p in module_prefixes if p)
    removed_elements = 0

    def _remove_subtree(key):
        nonlocal removed_elements
        for child in _element_children(hierarchy, key):
            _remove_subtree(child)
        if key.type == unreal.RigElementType.BONE:
            return
        try:
            if hierarchy_controller.remove_element(key, False, False):
                removed_elements += 1
        except Exception:
            pass

    root_key = make_key(unreal.RigElementType.NULL, GENERATED_ROOT_NAME)
    if hierarchy.contains(root_key):
        for child in _element_children(hierarchy, root_key):
            _remove_subtree(child)

    if prefixes:
        keys = []
        for getter in ("get_controls", "get_nulls"):
            try:
                keys.extend(getattr(hierarchy, getter)() or [])
            except Exception:
                pass
        for key in keys:
            if str(key.name).startswith(prefixes) and hierarchy.contains(key):
                _remove_subtree(key)

    removed_nodes = 0
    if prefixes and model is not None:
        for node in list(model.get_nodes() or []):
            name = str(node.get_name())
            if name.startswith(prefixes):
                for method in ("remove_node_by_name", "remove_node"):
                    fn = getattr(graph_controller, method, None)
                    if fn is None:
                        continue
                    try:
                        fn(name if method == "remove_node_by_name" else node, False)
                        removed_nodes += 1
                        break
                    except Exception:
                        continue
    return removed_elements, removed_nodes


def remove_generated_control_if_present(
    hierarchy,
    hierarchy_controller,
    control_name,
    generated_root_names=("PythonWorldControls", "WorldSpace"),
):
    """Remove a stale pipeline-generated control without touching artist controls."""
    if not control_name:
        return False
    key = make_key(unreal.RigElementType.CONTROL, control_name)
    if not hierarchy.contains(key):
        return False

    generated_roots = {str(name) for name in generated_root_names}
    current = key
    is_generated = False
    for _ in range(64):
        try:
            parent = hierarchy.get_first_parent(current)
        except Exception:
            break
        if not is_valid_key(hierarchy, parent):
            break
        parent_name = str(getattr(parent, "name", ""))
        if parent_name in generated_roots:
            is_generated = True
            break
        current = parent

    if not is_generated:
        return False

    try:
        return bool(
            hierarchy_controller.remove_element(
                key, setup_undo=False, print_python_command=False
            )
        )
    except TypeError:
        try:
            return bool(hierarchy_controller.remove_element(key, False, False))
        except Exception:
            return False
    except Exception:
        return False
