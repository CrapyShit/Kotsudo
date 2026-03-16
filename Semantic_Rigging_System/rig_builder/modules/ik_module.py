from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)

try:
    from .. import graph_utils
    from .rig_module import RigModule
except ImportError:
    import graph_utils
    from modules.rig_module import RigModule


class IKModule(RigModule):
    def validate(self):
        if len(self.chain) != 3:
            raise RuntimeError(f"IK module '{self.name}' must have exactly 3 bones, got: {self.chain}")

    def build(self):
        self.validate()

        if self.logger:
            self.logger.push(f"[IKModule] Building {self.name}")

        recipe_data = self.read_recipe()
        hierarchy = self.context.hierarchy
        hierarchy_controller = self.context.hierarchy_controller
        controller = self.context.graph_controller
        model = self.context.model
        forwards_solve = graph_utils.find_forwards_solve_node_name(model)

        if not forwards_solve:
            raise RuntimeError("No Forwards Solve node found in the Control Rig graph.")

        module_prefix = graph_utils.sanitize_name(self.name)
        effector_control_name = f"{module_prefix}_IK_CTRL"
        pole_control_name = f"{module_prefix}_PV_CTRL"

        effector_position = graph_utils.get_bone_global_position(hierarchy, self.chain[2])
        pole_position = graph_utils.compute_pole_vector(self.chain, hierarchy)
        parent_key = graph_utils.get_world_parent_key(hierarchy, hierarchy_controller)

        graph_utils.create_control(
            hierarchy,
            hierarchy_controller,
            parent_key,
            effector_control_name,
            effector_position,
            unreal.LinearColor(0.0, 0.7, 1.0, 1.0),
            (4.0, 4.0, 4.0),
        )
        graph_utils.create_control(
            hierarchy,
            hierarchy_controller,
            parent_key,
            pole_control_name,
            pole_position,
            unreal.LinearColor(0.4, 1.0, 0.3, 1.0),
            (3.0, 3.0, 3.0),
        )

        get_effector_node = f"{module_prefix}_GetEffector"
        get_pole_node = f"{module_prefix}_GetPole"
        ik_node_name = f"{module_prefix}_IK"
        ik_unit_struct = graph_utils.pick_ik_unit_struct(recipe_data.get("SolverType"))

        graph_utils.create_unit_node(
            controller,
            model,
            get_effector_node,
            unreal.RigUnit_GetControlTransform,
            unreal.Vector2D(0, 200),
        )
        graph_utils.create_unit_node(
            controller,
            model,
            get_pole_node,
            unreal.RigUnit_GetControlTransform,
            unreal.Vector2D(0, 380),
        )
        graph_utils.create_unit_node(
            controller,
            model,
            ik_node_name,
            ik_unit_struct,
            unreal.Vector2D(520, 290),
        )

        graph_utils.set_pin_default(controller, model, f"{get_effector_node}.Control", effector_control_name)
        graph_utils.set_pin_default(controller, model, f"{get_effector_node}.Space", "GlobalSpace")
        graph_utils.set_pin_default(controller, model, f"{get_pole_node}.Control", pole_control_name)
        graph_utils.set_pin_default(controller, model, f"{get_pole_node}.Space", "GlobalSpace")

        graph_utils.set_key_pin(controller, model, ik_node_name, ["StartBone", "Root", "BoneA", "FirstBone", "ItemA", "Start"], "Bone", self.chain[0])
        graph_utils.set_key_pin(controller, model, ik_node_name, ["MidBone", "BoneB", "SecondBone", "ItemB", "Mid"], "Bone", self.chain[1])
        graph_utils.set_key_pin(controller, model, ik_node_name, ["EndBone", "Tip", "BoneC", "ThirdBone", "ItemC", "End"], "Bone", self.chain[2])
        graph_utils.set_key_pin(controller, model, ik_node_name, ["EffectorBone", "EffectorItem", "Effector", "EffectorTarget", "EffectorKey"], "Bone", self.chain[2])

        graph_utils.set_any_pin(controller, model, ik_node_name, ["Space", "EffectorSpace"], "GlobalSpace")
        graph_utils.set_any_pin(controller, model, ik_node_name, ["Weight"], "1.0")
        graph_utils.set_any_pin(controller, model, ik_node_name, ["bPropagateToChildren"], "True")
        graph_utils.set_any_pin(controller, model, ik_node_name, ["SecondaryAxisWeight"], "1.0")

        upper_length = graph_utils.vector_length(
            graph_utils.vector_sub(
                graph_utils.get_bone_global_position(hierarchy, self.chain[1]),
                graph_utils.get_bone_global_position(hierarchy, self.chain[0]),
            )
        )
        lower_length = graph_utils.vector_length(
            graph_utils.vector_sub(
                graph_utils.get_bone_global_position(hierarchy, self.chain[2]),
                graph_utils.get_bone_global_position(hierarchy, self.chain[1]),
            )
        )
        graph_utils.set_any_pin(controller, model, ik_node_name, ["BoneALength", "BoneLengthA", "LengthA", "ItemALength"], str(upper_length))
        graph_utils.set_any_pin(controller, model, ik_node_name, ["BoneBLength", "BoneLengthB", "LengthB", "ItemBLength"], str(lower_length))

        graph_utils.connect_pins(controller, model, f"{get_effector_node}.Transform", f"{ik_node_name}.EffectorTransform")
        graph_utils.connect_pins(controller, model, f"{get_effector_node}.Transform", f"{ik_node_name}.Effector")
        graph_utils.connect_pins(controller, model, f"{get_pole_node}.Transform.Translation", f"{ik_node_name}.PoleVector")
        graph_utils.connect_pins(controller, model, f"{get_pole_node}.Transform.Translation", f"{ik_node_name}.PoleVectorPosition")

        source_exec = f"{forwards_solve}.Execute" if graph_utils.pin_exists(model, f"{forwards_solve}.Execute") else f"{forwards_solve}.ExecuteContext"
        target_exec = f"{ik_node_name}.ExecuteContext" if graph_utils.pin_exists(model, f"{ik_node_name}.ExecuteContext") else f"{ik_node_name}.Execute"
        graph_utils.connect_pins(controller, model, source_exec, target_exec)

        if self.logger:
            self.logger.pop()

        return {
            "module_name": self.name,
            "chain": self.chain,
            "controls": [effector_control_name, pole_control_name],
            "ik_node": ik_node_name,
            "recipe": recipe_data,
        }

    def read_recipe(self):
        recipe_fields = {
            "ModuleType": None,
            "SolverType": None,
            "NumControls": None,
            "CreatePoleVector": True,
        }

        fallback_names = {
            "ModuleType": ["module_type"],
            "SolverType": ["solver_type"],
            "NumControls": ["num_controls"],
            "CreatePoleVector": ["create_pole_vector"],
        }

        for field_name in recipe_fields.keys():
            for candidate_name in [field_name] + fallback_names.get(field_name, []):
                try:
                    recipe_fields[field_name] = self.recipe.get_editor_property(candidate_name)
                    break
                except Exception:
                    continue

        return recipe_fields
