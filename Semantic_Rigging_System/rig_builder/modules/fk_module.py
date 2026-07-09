from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)

from .. import graph_utils
from .rig_module import RigModule


class FKModule(RigModule):
    module_type = "FKChain"

    @classmethod
    def describe_contract(cls):
        return {
            "module_type": cls.module_type,
            "chain": {
                "min_length": 1,
                "max_length": None,
                "exact_length": None,
                "roles": ["Start", "Mid", "End"],
            },
            "required_metadata": ["ModuleType", "ModuleName"],
            "required_recipe_fields": [],
            "attachment_points": ["root", "tip", "fk_root_ctrl", "fk_tip_ctrl"],
            "build_products": ["controls", "nodes", "attach_points"],
        }

    def validate(self):
        if not self.chain:
            raise RuntimeError(f"FK module '{self.name}' must have at least 1 bone.")

        if not self.context:
            raise RuntimeError(f"FK module '{self.name}' requires a valid rig context.")

    def build(self):
        self.validate()

        if self.logger:
            self.logger.push(f"[FKModule] Building {self.name}")

        recipe_data = self.read_recipe()
        hierarchy = self.context.hierarchy
        hierarchy_controller = self.context.hierarchy_controller
        controller = self.context.graph_controller
        model = self.context.model
        forwards_solve = graph_utils.find_forwards_solve_node_name(model)

        if not forwards_solve:
            raise RuntimeError("No Forwards Solve node found in the Control Rig graph.")

        if not hasattr(unreal, "RigUnit_SetTransform"):
            raise RuntimeError("RigUnit_SetTransform is not available in this Unreal Python API.")

        module_prefix = graph_utils.sanitize_name(self.name)
        parent_key = (
            self.context.get_parent_control_key(self.parent_module_name, self.parent_attach_point)
            or graph_utils.get_world_parent_key(hierarchy, hierarchy_controller)
        )
        control_scale_multiplier = float(recipe_data.get("ControlScale") or 1.0)
        control_scale = graph_utils.compute_chain_scale(
            hierarchy, self.chain, fraction=0.35, multiplier=control_scale_multiplier
        )
        control_shape = recipe_data.get("ControlShape") or "Circle_Thick"

        x_origin = self.context.claim_module_column()

        controls = []
        nodes = []
        attach_points = {
            "root": self.chain[0],
            "tip": self.chain[-1],
        }
        previous_control_key = parent_key
        previous_exec_node = self.context.get_exec_tail() or forwards_solve

        for index, bone_name in enumerate(self.chain):
            bone_transform = graph_utils.get_bone_global_transform(hierarchy, bone_name)
            bone_position = graph_utils.transform_to_location(bone_transform)
            chain_direction = graph_utils.get_chain_direction(hierarchy, self.chain, index)
            shape_rotation = graph_utils.get_control_shape_rotation(bone_transform, chain_direction)
            safe_bone_name = graph_utils.sanitize_name(bone_name)
            control_name = f"{module_prefix}_{safe_bone_name}_FK_CTRL"
            get_control_node = f"{module_prefix}_{safe_bone_name}_GetFK"
            set_transform_node = f"{module_prefix}_{safe_bone_name}_SetFK"

            control_key = graph_utils.create_control(
                hierarchy,
                hierarchy_controller,
                previous_control_key,
                control_name,
                bone_position,
                unreal.LinearColor(1.0, 0.65, 0.1, 1.0),
                (control_scale, control_scale, control_scale),
                shape_name=control_shape,
                shape_rotation=shape_rotation,
            )
            hierarchy.set_global_transform(control_key, bone_transform, True, True)

            graph_utils.create_unit_node(
                controller,
                model,
                get_control_node,
                unreal.RigUnit_GetControlTransform,
                unreal.Vector2D(x_origin, 180 + index * 220),
            )
            graph_utils.create_unit_node(
                controller,
                model,
                set_transform_node,
                unreal.RigUnit_SetTransform,
                unreal.Vector2D(x_origin + 520, 180 + index * 220),
            )

            graph_utils.set_pin_default(controller, model, f"{get_control_node}.Control", control_name)
            graph_utils.set_pin_default(controller, model, f"{get_control_node}.Space", "GlobalSpace")
            graph_utils.set_key_pin(controller, model, set_transform_node, ["Item", "Bone", "Child"], "Bone", bone_name)
            graph_utils.set_any_pin(controller, model, set_transform_node, ["Space"], "GlobalSpace")
            graph_utils.set_any_pin(controller, model, set_transform_node, ["Initial"], "False")
            graph_utils.set_any_pin(controller, model, set_transform_node, ["Weight"], "1.0")
            graph_utils.set_any_pin(
                controller,
                model,
                set_transform_node,
                ["bPropagateToChildren", "PropagateToChildren", "propagate_to_children"],
                "True",
            )

            if not graph_utils.connect_pins(controller, model, f"{get_control_node}.Transform", f"{set_transform_node}.Value"):
                graph_utils.connect_pins(controller, model, f"{get_control_node}.Transform", f"{set_transform_node}.Transform")

            source_exec = (
                f"{previous_exec_node}.ExecuteContext"
                if graph_utils.pin_exists(model, f"{previous_exec_node}.ExecuteContext")
                else f"{previous_exec_node}.Execute"
            )
            target_exec = (
                f"{set_transform_node}.ExecuteContext"
                if graph_utils.pin_exists(model, f"{set_transform_node}.ExecuteContext")
                else f"{set_transform_node}.Execute"
            )
            graph_utils.connect_pins(controller, model, source_exec, target_exec)

            controls.append(control_name)
            nodes.extend([get_control_node, set_transform_node])

            if index == 0:
                attach_points["fk_root_ctrl"] = control_name
            if index == len(self.chain) - 1:
                attach_points["fk_tip_ctrl"] = control_name
            if index == len(self.chain) // 2 and len(self.chain) > 2:
                attach_points["mid"] = bone_name
                attach_points["fk_mid_ctrl"] = control_name

            previous_control_key = control_key
            previous_exec_node = set_transform_node

        # Advance the shared exec tail so the next module chains after FK.
        self.context.set_exec_tail(previous_exec_node)

        if self.logger:
            self.logger.pop()

        return self.build_result(
            controls=controls,
            nodes=nodes,
            attach_points=attach_points,
            outputs={
                "fk_controls": list(controls),
                "driven_bones": list(self.chain),
            },
            recipe_data=recipe_data,
            metadata={
                "control_shape": recipe_data.get("ControlShape"),
                "control_scale": recipe_data.get("ControlScale"),
            },
        )

    def read_recipe(self):
        recipe_fields = {
            "ModuleType": None,
            "ControlShape": "Circle_Thick",
            "ControlScale": 1.0,
        }

        fallback_names = {
            "ModuleType": ["module_type"],
            "ControlShape": ["control_shape"],
            "ControlScale": ["control_scale"],
        }

        return self.resolve_recipe_fields(recipe_fields, fallback_names=fallback_names)