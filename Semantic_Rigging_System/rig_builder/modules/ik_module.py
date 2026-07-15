from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)

from .. import graph_utils
from .rig_module import RigModule

# ---------------------------------------------------------------------------
# IKLimb module
# ---------------------------------------------------------------------------
# Solver selection (no SolverType override needed -- clean and automatic):
#
#   len(chain) == 3   -> RigUnit_TwoBoneIKSimple ("Basic IK" in the graph)
#   len(chain) != 3   -> RigUnit_FABRIK
#
# This mirrors IKFKModule's proven solver-selection logic exactly (same
# title-tolerant node verification, same stale-node cleanup on rebuild),
# just without the FK layer / blend variable -- IKLimb is pure IK.
# ---------------------------------------------------------------------------


class IKModule(RigModule):
    """Pure IK module (no FK, no switch) for any chain length >= 2.

    3-bone chains get Control Rig's native two-bone solver (displays as
    "Basic IK" in UE 5.6). Any other chain length gets FABRIK, matching
    the same solver-selection rule used by IKFKModule.

    Attach points
    -------------
    root          - first bone
    tip           - last bone
    mid           - middle bone (only meaningful/present for 3-bone chains)
    effector      - IK effector control
    pole_vector   - pole vector control (only created for 3-bone/TwoBoneIK)
    """

    module_type = "IKLimb"

    @classmethod
    def describe_contract(cls):
        return {
            "module_type": cls.module_type,
            "chain": {
                "min_length": 2,
                "max_length": None,
                "exact_length": None,
                "roles": [],
            },
            "required_metadata": ["ModuleType", "ModuleName"],
            "required_recipe_fields": [],
            "attachment_points": ["root", "tip", "effector", "pole_vector"],
            "build_products": ["controls", "nodes", "attach_points"],
        }

    def validate(self):
        if len(self.chain) < 2:
            raise RuntimeError(
                f"IK module '{self.name}' requires at least 2 bones, got: {self.chain}"
            )
        if not self.context:
            raise RuntimeError(f"IK module '{self.name}' requires a valid rig context.")

    def build(self):
        self.validate()

        if self.logger:
            self.logger.push(f"[IKModule] Building {self.name}")

        recipe_data = self.read_recipe()
        solver_mode = _choose_solver_mode(self.chain, recipe_data)

        hierarchy = self.context.hierarchy
        hierarchy_controller = self.context.hierarchy_controller
        controller = self.context.graph_controller
        model = self.context.model
        forwards_solve = graph_utils.find_forwards_solve_node_name(model)

        if not forwards_solve:
            raise RuntimeError("No Forwards Solve node found in the Control Rig graph.")

        module_prefix = graph_utils.sanitize_name(self.name)
        effector_control_name = f"{module_prefix}_IK_CTRL"

        effector_position = graph_utils.get_bone_global_position(hierarchy, self.chain[-1])
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
            hierarchy, hierarchy_controller,
            parent_key, effector_control_name, effector_position,
            unreal.LinearColor(0.0, 0.7, 1.0, 1.0),
            (effector_scale, effector_scale, effector_scale),
        )

        get_effector_node = f"{module_prefix}_GetEffector"
        ik_node_name = f"{module_prefix}_IK"

        x_origin = self.context.claim_module_column()

        graph_utils.create_unit_node(
            controller, model, get_effector_node,
            unreal.RigUnit_GetControlTransform,
            unreal.Vector2D(x_origin, 200),
        )
        graph_utils.set_pin_default(controller, model, f"{get_effector_node}.Control", effector_control_name)
        graph_utils.set_pin_default(controller, model, f"{get_effector_node}.Space", "GlobalSpace")

        all_controls = [effector_control_name]
        all_nodes = [get_effector_node]
        pole_ctrl = None
        get_pole_node = None

        if solver_mode == "TwoBoneIK":
            pole_ctrl, get_pole_node = self._build_two_bone_ik_solver(
                controller=controller, model=model, hierarchy=hierarchy,
                hierarchy_controller=hierarchy_controller, parent_key=parent_key,
                module_prefix=module_prefix, ik_node=ik_node_name,
                get_effector_node=get_effector_node,
                ik_col=x_origin + 520, pv_scale=pv_scale, recipe_data=recipe_data,
            )
            all_controls.append(pole_ctrl)
            all_nodes.append(get_pole_node)
        else:
            self._build_fabrik_solver(
                controller=controller, model=model, ik_node=ik_node_name,
                get_effector_node=get_effector_node, ik_col=x_origin + 520,
            )

        all_nodes.append(ik_node_name)

        chain_start = self.context.get_exec_tail() or forwards_solve
        source_exec = (
            f"{chain_start}.ExecuteContext"
            if graph_utils.pin_exists(model, f"{chain_start}.ExecuteContext")
            else f"{chain_start}.Execute"
        )
        target_exec = (
            f"{ik_node_name}.ExecuteContext"
            if graph_utils.pin_exists(model, f"{ik_node_name}.ExecuteContext")
            else f"{ik_node_name}.Execute"
        )
        graph_utils.connect_pins(controller, model, source_exec, target_exec)
        self.context.set_exec_tail(ik_node_name)

        if self.logger:
            self.logger.pop()

        attach_points = {
            "root": self.chain[0],
            "tip": self.chain[-1],
            "effector": effector_control_name,
        }
        if len(self.chain) == 3:
            attach_points["mid"] = self.chain[1]
        if pole_ctrl:
            attach_points["pole_vector"] = pole_ctrl

        return self.build_result(
            controls=all_controls,
            nodes=all_nodes,
            attach_points=attach_points,
            outputs={
                "ik_node": ik_node_name,
                "get_effector_node": get_effector_node,
                "get_pole_node": get_pole_node,
                "solver_mode": solver_mode,
            },
            recipe_data=recipe_data,
            metadata={
                "solver_type": recipe_data.get("SolverType"),
                "resolved_solver_mode": solver_mode,
                "create_pole_vector": bool(pole_ctrl),
            },
        )

    # ------------------------------------------------------------------
    # Solver builders
    # ------------------------------------------------------------------

    def _build_two_bone_ik_solver(
        self, controller, model, hierarchy, hierarchy_controller, parent_key,
        module_prefix, ik_node, get_effector_node, ik_col, pv_scale, recipe_data,
    ):
        """Build RigUnit_TwoBoneIKSimple ("Basic IK") for a 3-joint limb."""
        if len(self.chain) != 3:
            raise RuntimeError(
                f"TwoBoneIK mode requires exactly 3 joints, got {len(self.chain)} "
                f"for module '{self.name}'."
            )

        pole_distance_scale = float(recipe_data.get("PoleDistanceScale") or 0.75)
        pole_position = graph_utils.compute_pole_vector(
            self.chain, hierarchy, pole_distance_scale=pole_distance_scale
        )
        pole_control_name = f"{module_prefix}_PV_CTRL"

        graph_utils.create_control(
            hierarchy, hierarchy_controller, parent_key, pole_control_name, pole_position,
            unreal.LinearColor(0.4, 1.0, 0.3, 1.0),
            (pv_scale, pv_scale, pv_scale), shape_name=None,
        )

        get_pole_node = f"{module_prefix}_GetPole"
        graph_utils.create_unit_node(
            controller, model, get_pole_node,
            unreal.RigUnit_GetControlTransform,
            unreal.Vector2D(ik_col - 520, 380),
        )
        graph_utils.set_pin_default(controller, model, f"{get_pole_node}.Control", pole_control_name)
        graph_utils.set_pin_default(controller, model, f"{get_pole_node}.Space", "GlobalSpace")

        two_bone_struct = graph_utils.pick_two_bone_ik_struct()
        title_pattern = (("two", "ik"), ("basic", "ik"), "basic ik")
        graph_utils.remove_stale_node_if_wrong_type(controller, model, ik_node, title_pattern)

        existing = model.find_node(ik_node)
        if not existing:
            graph_utils.create_unit_node(
                controller, model, ik_node, two_bone_struct,
                unreal.Vector2D(ik_col, 100),
            )
            graph_utils.verify_node_title(ik_node, model, expected_options=title_pattern)

        graph_utils.set_any_pin(controller, model, ik_node, ["BoneA"], self.chain[0])
        graph_utils.set_any_pin(controller, model, ik_node, ["BoneB"], self.chain[1])
        graph_utils.set_any_pin(controller, model, ik_node, ["EffectorBone"], self.chain[2])

        effector_out = f"{get_effector_node}.Transform"
        if not graph_utils.connect_first_available(
            controller, model, effector_out,
            [f"{ik_node}.Effector", f"{ik_node}.EffectorTransform"],
        ):
            raise RuntimeError(
                f"Could not connect the effector control's transform to node '{ik_node}'."
            )

        if not graph_utils.connect_transform_translation_to_vector_pin(
            controller, model, get_pole_node, f"{ik_node}.PoleVector"
        ):
            graph_utils.set_vector_pin(controller, model, f"{ik_node}.PoleVector", pole_position)

        primary_axis = graph_utils.recipe_vector(recipe_data.get("PrimaryAxis"), unreal.Vector(1.0, 0.0, 0.0))
        secondary_axis = graph_utils.recipe_vector(recipe_data.get("SecondaryAxis"), unreal.Vector(0.0, 1.0, 0.0))
        pole_kind = str(recipe_data.get("PoleVectorKind") or "Location")

        graph_utils.set_vector_pin(controller, model, f"{ik_node}.PrimaryAxis", primary_axis)
        graph_utils.set_vector_pin(controller, model, f"{ik_node}.SecondaryAxis", secondary_axis)
        graph_utils.set_any_pin(controller, model, ik_node, ["SecondaryAxisWeight"], "1.0")
        graph_utils.set_any_pin(controller, model, ik_node, ["PoleVectorKind"], pole_kind)
        graph_utils.set_any_pin(controller, model, ik_node, ["PoleVectorSpace"], "None")
        graph_utils.set_any_pin(controller, model, ik_node, ["Weight"], "1.0")
        graph_utils.set_any_pin(controller, model, ik_node, ["PropagateToChildren"], "true")
        graph_utils.set_any_pin(controller, model, ik_node, ["BoneALength"], "0.0")
        graph_utils.set_any_pin(controller, model, ik_node, ["BoneBLength"], "0.0")

        enable_stretch = graph_utils.recipe_bool(recipe_data.get("EnableStretch"), False)
        graph_utils.set_any_pin(
            controller, model, ik_node, ["EnableStretch"], "true" if enable_stretch else "false"
        )
        if enable_stretch:
            graph_utils.set_any_pin(
                controller, model, ik_node, ["StretchStartRatio"],
                str(float(recipe_data.get("StretchStartRatio") or 1.0)),
            )
            graph_utils.set_any_pin(
                controller, model, ik_node, ["StretchMaximumRatio"],
                str(float(recipe_data.get("StretchMaximumRatio") or 1.2)),
            )

        return pole_control_name, get_pole_node

    def _build_fabrik_solver(self, controller, model, ik_node, get_effector_node, ik_col):
        """Build RigUnit_FABRIK for any chain length other than 3."""
        fabrik_struct = graph_utils.pick_fabrik_struct()
        graph_utils.remove_stale_node_if_wrong_type(controller, model, ik_node, "fabrik")

        existing = model.find_node(ik_node)
        if not existing:
            if fabrik_struct is not None:
                graph_utils.create_unit_node(
                    controller, model, ik_node, fabrik_struct,
                    unreal.Vector2D(ik_col, 100),
                )
            else:
                controller.add_unit_node_from_struct_path(
                    "/Script/ControlRig.RigUnit_FABRIK", "Execute",
                    unreal.Vector2D(ik_col, 100), ik_node,
                )
            graph_utils.verify_node_title(ik_node, model, expected_options=("fabrik",))

        graph_utils.set_any_pin(controller, model, ik_node, ["StartBone"], self.chain[0])
        graph_utils.set_any_pin(controller, model, ik_node, ["EffectorBone"], self.chain[-1])

        effector_out = f"{get_effector_node}.Transform"
        if not graph_utils.connect_first_available(
            controller, model, effector_out,
            [f"{ik_node}.EffectorTransform", f"{ik_node}.Effector"],
        ):
            raise RuntimeError(
                f"Could not connect the effector control's transform to node '{ik_node}'."
            )

        graph_utils.set_any_pin(controller, model, ik_node, ["SetEffectorTransform"], "true")
        graph_utils.set_any_pin(controller, model, ik_node, ["MaxIterations"], "16")
        graph_utils.set_any_pin(controller, model, ik_node, ["Precision"], "0.01")
        graph_utils.set_any_pin(controller, model, ik_node, ["Weight"], "1.0")
        graph_utils.set_any_pin(controller, model, ik_node, ["PropagateToChildren"], "true")

    def read_recipe(self):
        recipe_fields = {
            "ModuleType": None,
            "SolverType": "Auto",
            "ControlScale": 1.0,
            "PrimaryAxis": None,
            "SecondaryAxis": None,
            "PoleVectorKind": "Location",
            "PoleDistanceScale": 0.75,
            "EnableStretch": False,
            "StretchStartRatio": 1.0,
            "StretchMaximumRatio": 1.2,
        }
        fallback_names = {
            "ModuleType": ["module_type"],
            "SolverType": ["solver_type", "solvertype"],
            "ControlScale": ["control_scale", "controlscale"],
            "PrimaryAxis": ["primary_axis", "primaryaxis"],
            "SecondaryAxis": ["secondary_axis", "secondaryaxis"],
            "PoleVectorKind": ["pole_vector_kind", "polevectorkind"],
            "PoleDistanceScale": ["pole_distance_scale", "poledistancescale"],
            "EnableStretch": ["enable_stretch", "enablestretch"],
            "StretchStartRatio": ["stretch_start_ratio", "stretchstartratio"],
            "StretchMaximumRatio": ["stretch_maximum_ratio", "stretchmaximumratio"],
        }
        return self.resolve_recipe_fields(recipe_fields, fallback_names=fallback_names)


def _choose_solver_mode(chain, recipe_data):
    """Same rule as IKFKModule: Auto picks TwoBoneIK for exactly 3 joints,
    FABRIK otherwise. An explicit SolverType override is still honored.
    """
    raw_solver = str(recipe_data.get("SolverType") or "Auto").strip().lower()
    aliases = {
        "": "auto", "auto": "auto", "automatic": "auto", "default": "auto",
        "basicik": "twoboneik", "basic_ik": "twoboneik",
        "two bone ik": "twoboneik", "two_bone_ik": "twoboneik",
        "twoboneik": "twoboneik", "twoboneiksimple": "twoboneik",
        "two_bone_ik_simple": "twoboneik",
        "fabrik": "fabrik", "basicfabrik": "fabrik", "basic_fabrik": "fabrik",
    }

    solver = aliases.get(raw_solver)
    if solver is None:
        raise RuntimeError(
            f"Unsupported IKLimb SolverType '{recipe_data.get('SolverType')}'. "
            "Use Auto, TwoBoneIK/BasicIK, or FABRIK."
        )

    if solver == "auto":
        return "TwoBoneIK" if len(chain) == 3 else "FABRIK"

    if solver == "twoboneik":
        if len(chain) != 3:
            raise RuntimeError(
                f"SolverType TwoBoneIK/BasicIK requires exactly 3 joints, got {len(chain)}."
            )
        return "TwoBoneIK"

    return "FABRIK"
