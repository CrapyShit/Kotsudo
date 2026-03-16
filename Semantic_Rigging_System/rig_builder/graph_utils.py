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


def create_control(hierarchy, hierarchy_controller, parent_key, control_name, position, color, shape_scale):
    control_key = make_key(unreal.RigElementType.CONTROL, control_name)
    control_settings = unreal.RigControlSettings()
    control_settings.primary_axis = unreal.RigControlAxis.X
    control_settings.maximum_value = euler_value()
    control_settings.minimum_value = euler_value()
    control_settings.limit_enabled = [unreal.RigControlLimitEnabled(False, False) for _ in range(9)]
    control_settings.is_transient_control = False
    control_settings.shape_visible = True
    control_settings.shape_name = "Circle_Thick"
    control_settings.shape_color = color
    control_settings.draw_limits = True
    control_settings.display_name = "None"
    control_settings.control_type = unreal.RigControlType.EULER_TRANSFORM
    control_settings.animation_type = unreal.RigControlAnimationType.ANIMATION_CONTROL

    if not hierarchy.contains(control_key):
        hierarchy_controller.add_control(control_name, parent_key, control_settings, euler_value())
    else:
        current_parent = hierarchy.get_first_parent(control_key)
        if current_parent != parent_key:
            hierarchy_controller.set_parent(control_key, parent_key, True, False, False)

    hierarchy.set_control_offset_transform(control_key, unreal.Transform(location=position), True, True)
    hierarchy.set_control_value(control_key, euler_value(), unreal.RigControlValueType.CURRENT)
    hierarchy.set_control_value(control_key, euler_value(), unreal.RigControlValueType.MINIMUM)
    hierarchy.set_control_value(control_key, euler_value(), unreal.RigControlValueType.MAXIMUM)
    hierarchy.set_control_shape_transform(control_key, unreal.Transform(scale=list(shape_scale)), True)
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
