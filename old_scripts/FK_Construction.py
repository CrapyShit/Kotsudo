import unreal

cr = unreal.ControlRigBlueprint.get_currently_open_rig_blueprints()[0]
hc = unreal.ControlRigBlueprintLibrary.get_hierarchy_controller(cr)

# Transforms in UE5.6: Transform(location, rotation, scale)
t0 = unreal.Transform([0, 0, 0],  [0, 0, 0], [1, 1, 1])
t1 = unreal.Transform([0, 0, 20], [0, 0, 0], [1, 1, 1])
t2 = unreal.Transform([0, 0, 20], [0, 0, 0], [1, 1, 1])

# Bones: b0 -> b1 -> b2
b0 = hc.add_bone("b0", unreal.RigElementKey(), t0, True)
b1 = hc.add_bone("b1", b0,                    t1, False)
b2 = hc.add_bone("b2", b1,                    t2, False)

# Controls: use EULER_TRANSFORM in UE5.6
settings = unreal.RigControlSettings()
settings.control_type = unreal.RigControlType.EULER_TRANSFORM

value = unreal.RigControlValue()  # identity
c0 = hc.add_control("c0_ctrl", unreal.RigElementKey(), settings, value, True)
c1 = hc.add_control("c1_ctrl", c0,                     settings, value, True)
c2 = hc.add_control("c2_ctrl", c1,                     settings, value, True)

# Match control offsets to bone globals (keeps hierarchies separate)
hierarchy = unreal.ControlRigBlueprintLibrary.get_hierarchy(cr)
b0_g = hierarchy.get_global_transform(b0, True)
b1_g = hierarchy.get_global_transform(b1, True)
b2_g = hierarchy.get_global_transform(b2, True)
hierarchy.set_control_offset_transform(c0, b0_g, initial=True, affect_children=True)
hierarchy.set_control_offset_transform(c1, b1_g, initial=True, affect_children=True)
hierarchy.set_control_offset_transform(c2, b2_g, initial=True, affect_children=True)

# Build graph: controls drive bones
controller = cr.get_controller_by_name("Rig Graph")
if not controller:
	controller = cr.get_controller()

controller.open_undo_bracket("Build FK Graph")
try:
	controller.remove_nodes_by_name([
		"FK_Begin",
		"FK_Get_c0", "FK_Get_c1", "FK_Get_c2",
		"FK_Set_b0", "FK_Set_b1", "FK_Set_b2"
	])
except Exception:
	pass

begin = controller.add_unit_node_from_struct_path(
	"/Script/ControlRig.RigUnit_BeginExecution",
	"Execute",
	unreal.Vector2D(0, 0),
	"FK_Begin"
)

get0 = controller.add_unit_node_from_struct_path(
	"/Script/ControlRig.RigUnit_GetControlTransform",
	"Execute",
	unreal.Vector2D(200, -200),
	"FK_Get_c0"
)
get1 = controller.add_unit_node_from_struct_path(
	"/Script/ControlRig.RigUnit_GetControlTransform",
	"Execute",
	unreal.Vector2D(200, 0),
	"FK_Get_c1"
)
get2 = controller.add_unit_node_from_struct_path(
	"/Script/ControlRig.RigUnit_GetControlTransform",
	"Execute",
	unreal.Vector2D(200, 200),
	"FK_Get_c2"
)

set0 = controller.add_unit_node_from_struct_path(
	"/Script/ControlRig.RigUnit_SetBoneTransform",
	"Execute",
	unreal.Vector2D(500, -200),
	"FK_Set_b0"
)
set1 = controller.add_unit_node_from_struct_path(
	"/Script/ControlRig.RigUnit_SetBoneTransform",
	"Execute",
	unreal.Vector2D(500, 0),
	"FK_Set_b1"
)
set2 = controller.add_unit_node_from_struct_path(
	"/Script/ControlRig.RigUnit_SetBoneTransform",
	"Execute",
	unreal.Vector2D(500, 200),
	"FK_Set_b2"
)

controller.set_pin_default_value("FK_Get_c0.Control", "c0_ctrl")
controller.set_pin_default_value("FK_Get_c1.Control", "c1_ctrl")
controller.set_pin_default_value("FK_Get_c2.Control", "c2_ctrl")
controller.set_pin_default_value("FK_Get_c0.Space", "GlobalSpace")
controller.set_pin_default_value("FK_Get_c1.Space", "GlobalSpace")
controller.set_pin_default_value("FK_Get_c2.Space", "GlobalSpace")

controller.set_pin_default_value("FK_Set_b0.Bone", "b0")
controller.set_pin_default_value("FK_Set_b1.Bone", "b1")
controller.set_pin_default_value("FK_Set_b2.Bone", "b2")
controller.set_pin_default_value("FK_Set_b0.Space", "GlobalSpace")
controller.set_pin_default_value("FK_Set_b1.Space", "GlobalSpace")
controller.set_pin_default_value("FK_Set_b2.Space", "GlobalSpace")
controller.set_pin_default_value("FK_Set_b0.Weight", "1.0")
controller.set_pin_default_value("FK_Set_b1.Weight", "1.0")
controller.set_pin_default_value("FK_Set_b2.Weight", "1.0")
controller.set_pin_default_value("FK_Set_b0.bPropagateToChildren", "True")
controller.set_pin_default_value("FK_Set_b1.bPropagateToChildren", "True")
controller.set_pin_default_value("FK_Set_b2.bPropagateToChildren", "True")

controller.add_link("FK_Begin.Execute", "FK_Set_b0.Execute")
controller.add_link("FK_Set_b0.Execute", "FK_Set_b1.Execute")
controller.add_link("FK_Set_b1.Execute", "FK_Set_b2.Execute")
controller.add_link("FK_Get_c0.Transform", "FK_Set_b0.Transform")
controller.add_link("FK_Get_c1.Transform", "FK_Set_b1.Transform")
controller.add_link("FK_Get_c2.Transform", "FK_Set_b2.Transform")

controller.close_undo_bracket()

cr.recompile_vm()
unreal.ControlRigBlueprintLibrary.request_control_rig_init(cr)
print("OK")
