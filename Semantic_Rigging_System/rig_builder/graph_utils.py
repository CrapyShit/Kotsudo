import math
from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)


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
    world_key = make_key(unreal.RigElementType.NULL, "WorldSpace")
    if hierarchy.contains(world_key):
        return world_key

    nulls = hierarchy.get_nulls() or []
    for null_key in nulls:
        parent_key = hierarchy.get_first_parent(null_key)
        if not is_valid_key(hierarchy, parent_key):
            return null_key

    generated_root_name = "PythonWorldControls"
    generated_root_key = make_key(unreal.RigElementType.NULL, generated_root_name)
    if hierarchy.contains(generated_root_key):
        return generated_root_key

    created_key = hierarchy_controller.add_null(
        generated_root_name,
        invalid_key(),
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


def euler_value(loc=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0), scl=(1.0, 1.0, 1.0)):
    euler_transform = unreal.EulerTransform(location=list(loc), rotation=list(rot), scale=list(scl))
    return unreal.RigHierarchy.make_control_value_from_euler_transform(euler_transform)


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
):
    control_key = make_key(unreal.RigElementType.CONTROL, control_name)
    control_settings = unreal.RigControlSettings()
    control_settings.primary_axis = unreal.RigControlAxis.X
    control_settings.maximum_value = euler_value()
    control_settings.minimum_value = euler_value()
    control_settings.limit_enabled = [unreal.RigControlLimitEnabled(False, False) for _ in range(9)]
    control_settings.is_transient_control = False
    control_settings.shape_visible = True
    if shape_name is not None:
        control_settings.shape_name = shape_name
    control_settings.shape_color = color
    control_settings.draw_limits = True
    control_settings.display_name = "None"
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

    hierarchy.set_control_offset_transform(control_key, unreal.Transform(location=position), True, True)
    hierarchy.set_control_value(control_key, euler_value(), unreal.RigControlValueType.CURRENT)
    hierarchy.set_control_value(control_key, euler_value(), unreal.RigControlValueType.MINIMUM)
    hierarchy.set_control_value(control_key, euler_value(), unreal.RigControlValueType.MAXIMUM)

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
