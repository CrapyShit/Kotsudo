from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)

from .. import graph_utils
from .rig_module import RigModule


class IKModule(RigModule):
    module_type = "IKLimb"

    @classmethod
    def describe_contract(cls):
        return {
            "module_type": cls.module_type,
            "chain": {
                "min_length": 3,
                "max_length": 3,
                "exact_length": 3,
                "roles": ["Start", "Mid", "End"],
            },
            "required_metadata": ["ModuleType", "ModuleName", "Role"],
            "required_recipe_fields": ["SolverType", "NumControls", "CreatePoleVector"],
            "attachment_points": ["root", "mid", "tip", "effector", "pole_vector"],
            "build_products": ["controls", "nodes", "attach_points"],
        }

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
        parent_key = (
            self.context.get_parent_control_key(self.parent_module_name, self.parent_attach_point)
            or graph_utils.get_world_parent_key(hierarchy, hierarchy_controller)
        )

        scale_multiplier = float(recipe_data.get("ControlScale") or 1.0)
        effector_scale = graph_utils.compute_chain_scale(
            hierarchy, self.chain, fraction=0.35, multiplier=scale_multiplier
        )
        pv_scale = graph_utils.compute_chain_scale(
            hierarchy, self.chain, fraction=0.12, multiplier=scale_multiplier
        )

        graph_utils.create_control(
            hierarchy,
            hierarchy_controller,
            parent_key,
            effector_control_name,
            effector_position,
            unreal.LinearColor(0.0, 0.7, 1.0, 1.0),
            (effector_scale, effector_scale, effector_scale),
        )
        graph_utils.create_control(
            hierarchy,
            hierarchy_controller,
            parent_key,
            pole_control_name,
            pole_position,
            unreal.LinearColor(0.4, 1.0, 0.3, 1.0),
            (pv_scale, pv_scale, pv_scale),
            shape_name=None,
        )

        get_effector_node = f"{module_prefix}_GetEffector"
        get_pole_node = f"{module_prefix}_GetPole"
        ik_node_name = f"{module_prefix}_IK"
        ik_unit_struct = graph_utils.pick_ik_unit_struct(recipe_data.get("SolverType"))

        x_origin = self.context.claim_module_column()

        graph_utils.create_unit_node(
            controller,
            model,
            get_effector_node,
            unreal.RigUnit_GetControlTransform,
            unreal.Vector2D(x_origin, 200),
        )
        graph_utils.create_unit_node(
            controller,
            model,
            get_pole_node,
            unreal.RigUnit_GetControlTransform,
            unreal.Vector2D(x_origin, 380),
        )
        graph_utils.create_unit_node(
            controller,
            model,
            ik_node_name,
            ik_unit_struct,
            unreal.Vector2D(x_origin + 520, 290),
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

        chain_start = self.context.get_exec_tail() or forwards_solve
        source_exec = (
            f"{chain_start}.ExecuteContext"
            if graph_utils.pin_exists(model, f"{chain_start}.ExecuteContext")
            else f"{chain_start}.Execute"
        )
        target_exec = f"{ik_node_name}.ExecuteContext" if graph_utils.pin_exists(model, f"{ik_node_name}.ExecuteContext") else f"{ik_node_name}.Execute"
        graph_utils.connect_pins(controller, model, source_exec, target_exec)
        self.context.set_exec_tail(ik_node_name)

        if self.logger:
            self.logger.pop()

        return self.build_result(
            controls=[effector_control_name, pole_control_name],
            nodes=[get_effector_node, get_pole_node, ik_node_name],
            attach_points={
                "root": self.chain[0],
                "mid": self.chain[1],
                "tip": self.chain[2],
                "effector": effector_control_name,
                "pole_vector": pole_control_name,
            },
            outputs={
                "ik_node": ik_node_name,
                "get_effector_node": get_effector_node,
                "get_pole_node": get_pole_node,
            },
            recipe_data=recipe_data,
            metadata={
                "solver_type": recipe_data.get("SolverType"),
                "num_controls": recipe_data.get("NumControls"),
                "create_pole_vector": recipe_data.get("CreatePoleVector"),
            },
        )

    def read_recipe(self):
        recipe_fields = {
            "ModuleType": None,
            "SolverType": None,
            "NumControls": None,
            "CreatePoleVector": True,
            "ControlScale": 1.0,
        }

        fallback_names = {
            "ModuleType": ["module_type"],
            "SolverType": ["solver_type"],
            "NumControls": ["num_controls"],
            "CreatePoleVector": ["create_pole_vector"],
            "ControlScale": ["control_scale"],
        }

        return self.resolve_recipe_fields(recipe_fields, fallback_names=fallback_names)
