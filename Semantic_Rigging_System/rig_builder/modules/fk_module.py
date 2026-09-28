from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)

from .. import constraints, graph_utils
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
        parent_key = self.default_parent_key()
        control_scale_multiplier = float(recipe_data.get("ControlScale") or 1.0)
        control_scale = graph_utils.compute_chain_scale(
            hierarchy, self.chain, fraction=0.35, multiplier=control_scale_multiplier
        )
        control_shape = recipe_data.get("ControlShape") or "Circle_Thick"

        x_origin = self.context.claim_module_column()

        # Bones driven channel-by-channel in Maya (point-only, orient-only,
        # several targets, one controller feeding several bones...) are rebuilt
        # from the exported constraints instead of one FK control per bone.
        records = constraints.constraint_records(recipe_data)
        mode = str(recipe_data.get("ConstraintMode") or "auto").strip().lower()
        if records and (mode == "always" or (mode == "auto" and constraints.needs_constraint_mode(records))):
            return self._build_from_constraints(
                recipe_data, records, parent_key, module_prefix, control_scale,
                x_origin, forwards_solve,
            )

        controls = []
        nodes = []
        attach_points = {
            "root": self.chain[0],
            "tip": self.chain[-1],
        }
        # Pass 1: every control. Parent resolution may add follow-space update
        # nodes to the exec chain, so no exec wiring happens until all the
        # module's controls exist (pass 2 reads the exec tail afterwards).
        built = []
        previous_control_key = parent_key
        for index, bone_name in enumerate(self.chain):
            bone_transform = graph_utils.get_bone_global_transform(hierarchy, bone_name)
            chain_direction = graph_utils.get_chain_direction(hierarchy, self.chain, index)
            shape_rotation = graph_utils.get_control_shape_rotation(bone_transform, chain_direction)
            control_name = f"{module_prefix}_{graph_utils.sanitize_name(bone_name)}_FK_CTRL"

            # One call resolves everything the Maya controller contributes:
            # its origin (control at the controller, bone driven through a
            # null), its exact shape, and its custom attributes. The parent is
            # the Maya parent controller when it exists in the rig.
            record = graph_utils.find_controller_record(recipe_data, bone_name, ("bone_driver",))
            control_name = self.context.control_name(record, control_name)
            control_key, driver_null = graph_utils.build_record_control(
                self.context.rig, hierarchy, hierarchy_controller, recipe_data,
                self.context.resolve_control_parent(record, previous_control_key),
                control_name, bone_name, bone_transform, record,
                graph_utils.record_color(record, unreal.LinearColor(1.0, 0.65, 0.1, 1.0)),
                control_shape, (control_scale, control_scale, control_scale), shape_rotation,
            )
            if driver_null and self.logger:
                self.logger.log(
                    f"[FKModule] '{control_name}' placed at the Maya controller origin, "
                    f"bone driven through '{driver_null}'."
                )
            built.append((control_name, driver_null))
            previous_control_key = control_key

        # Pass 2: graph nodes and exec wiring.
        previous_exec_node = self.context.get_exec_tail() or forwards_solve
        for index, bone_name in enumerate(self.chain):
            control_name, driver_null = built[index]
            safe_bone_name = graph_utils.sanitize_name(bone_name)
            get_control_node = f"{module_prefix}_{safe_bone_name}_GetFK"
            set_transform_node = f"{module_prefix}_{safe_bone_name}_SetFK"

            graph_utils.create_transform_getter(
                controller, model, get_control_node,
                unreal.Vector2D(x_origin, 180 + index * 220),
                control_name, driver_null,
            )
            graph_utils.create_unit_node(
                controller,
                model,
                set_transform_node,
                unreal.RigUnit_SetTransform,
                unreal.Vector2D(x_origin + 520, 180 + index * 220),
            )

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

            graph_utils.connect_exec(controller, model, previous_exec_node, set_transform_node)

            controls.append(control_name)
            nodes.extend([get_control_node, set_transform_node])

            if index == 0:
                attach_points["fk_root_ctrl"] = control_name
            if index == len(self.chain) - 1:
                attach_points["fk_tip_ctrl"] = control_name
            if index == len(self.chain) // 2 and len(self.chain) > 2:
                attach_points["mid"] = bone_name
                attach_points["fk_mid_ctrl"] = control_name

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

    def _build_from_constraints(self, recipe_data, records, parent_key, module_prefix,
                                control_scale, x_origin, forwards_solve):
        """Constraint mode: Maya controllers + native constraint nodes."""
        builder = constraints.ConstraintBuilder(
            self, recipe_data, parent_key, module_prefix,
            (control_scale, control_scale, control_scale),
        )
        # Children track the constrained bones through follow spaces the
        # context creates on demand.
        self.context.set_exec_tail(builder.build(records, forwards_solve, x_origin))

        if self.logger:
            self.logger.log(
                f"[FKModule] {self.name}: constraint mode, {len(records)} constraint(s), "
                f"controls {builder.controls}."
            )
            self.logger.pop()

        attach_points = {"root": self.chain[0], "tip": self.chain[-1]}
        if builder.controls:
            attach_points["fk_root_ctrl"] = builder.controls[0]
            attach_points["fk_tip_ctrl"] = builder.controls[-1]
        return self.build_result(
            controls=builder.controls,
            nodes=builder.nodes,
            attach_points=attach_points,
            outputs={"driven_bones": list(self.chain), "mode": "constraints"},
            recipe_data=recipe_data,
            metadata={"constraint_count": len(records)},
        )

    def read_recipe(self):
        recipe_fields = {
            "ModuleType": None,
            "ControlShape": "Circle_Thick",
            "ControlScale": 1.0,
            "ControllerRecords": None,
            "ShapeTable": None,
            "Constraints": None,
            "ConstraintMode": "auto",
        }

        fallback_names = {
            "ModuleType": ["module_type"],
            "ControlShape": ["control_shape"],
            "ControlScale": ["control_scale"],
            "Constraints": ["constraints"],
            "ConstraintMode": ["constraint_mode"],
            "ControllerRecords": ["controller_records", "controllerrecords"],
            "ShapeTable": ["shape_table", "shapetable"],
        }

        return self.resolve_recipe_fields(recipe_fields, fallback_names=fallback_names)