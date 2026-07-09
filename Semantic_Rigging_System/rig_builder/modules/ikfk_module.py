from typing import Any, Iterable, Optional, Sequence, Tuple, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)

from .. import graph_utils
from .rig_module import RigModule

# ---------------------------------------------------------------------------
# IKFKSwitch module
# ---------------------------------------------------------------------------
# Build strategy:
#
#   - FK controls are always created for every bone in the chain.
#   - FK SetTransform nodes always run first, writing a full FK base pose.
#   - A transform lerp blends the FK tip transform with the IK effector
#     transform. The blend is driven by the module IKFKBlend variable.
#   - The IK solver runs after the FK writes.
#
# Solver selection:
#
#   SolverType recipe field:
#       Auto / None     -> len(chain) == 3 uses TwoBoneIKSimple,
#                          every other length uses FABRIK.
#       TwoBoneIK       -> force RigUnit_TwoBoneIKSimple, requires 3 joints.
#       BasicIK         -> alias for TwoBoneIK.
#       FABRIK          -> force RigUnit_FABRIK.
#
# Why:
#   - RigUnit_TwoBoneIKSimple is the correct Control Rig unit for a classic
#     3-joint limb: upper -> lower -> tip.
#   - RigUnit_FABRIK remains the fallback for arbitrary-length chains such as
#     4+ joint tests, tentacles, tails, or custom limbs.
# ---------------------------------------------------------------------------


class IKFKModule(RigModule):
    """IK/FK switch module for 2+ joint chains.

    For a 3-joint chain the module automatically builds a Two Bone IK solver.
    For all other chain lengths it builds a FABRIK solver unless the recipe
    explicitly overrides ``SolverType``.

    Attach points
    -------------
    root            - first bone
    mid             - middle bone/index, for compatibility
    tip             - last bone
    fk_ctrl_N       - FK control for bone index N (0-based)
    ik_effector     - IK effector control
    ik_pole         - pole vector control, only created for TwoBoneIK mode
    """

    module_type = "IKFKSwitch"

    @classmethod
    def describe_contract(cls):
        return {
            "module_type": cls.module_type,
            "chain": {
                "min_length": 2,
                "roles": ["Start", "End"],
            },
            "required_metadata": ["ModuleType", "ModuleName"],
            "required_recipe_fields": ["ControlScale"],
            "attachment_points": [
                "root",
                "tip",
                "ik_effector",
                "ik_pole",
            ],
            "build_products": ["controls", "nodes", "attach_points"],
        }

    def validate(self):
        if len(self.chain) < 2:
            raise RuntimeError(
                f"IKFKSwitch module '{self.name}' requires at least 2 bones, "
                f"got {len(self.chain)}."
            )
        if not self.context:
            raise RuntimeError(
                f"IKFKSwitch module '{self.name}' requires a valid rig context."
            )

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self):
        self.validate()

        if self.logger:
            self.logger.push(f"[IKFKModule] Building {self.name}")

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
        scale_mult = float(recipe_data.get("ControlScale") or 1.0)
        fk_scale = graph_utils.compute_chain_scale(
            hierarchy, self.chain, fraction=0.35, multiplier=scale_mult
        )
        ik_scale = graph_utils.compute_chain_scale(
            hierarchy, self.chain, fraction=0.30, multiplier=scale_mult
        )
        pv_scale = graph_utils.compute_chain_scale(
            hierarchy, self.chain, fraction=0.22, multiplier=scale_mult
        )

        parent_key = (
            self.context.get_parent_control_key(self.parent_module_name, self.parent_attach_point)
            or graph_utils.get_world_parent_key(hierarchy, hierarchy_controller)
        )

        x_origin = self.context.claim_module_column(width=1600)

        # ------------------------------------------------------------------
        # 1. FK controls, one per bone, parented as a control chain
        # ------------------------------------------------------------------
        fk_controls = []
        fk_get_nodes = []
        prev_fk_key = parent_key

        for idx, bone_name in enumerate(self.chain):
            bone_transform = graph_utils.get_bone_global_transform(hierarchy, bone_name)
            bone_position = graph_utils.transform_to_location(bone_transform)
            chain_dir = graph_utils.get_chain_direction(hierarchy, self.chain, idx)
            shape_rot = graph_utils.get_control_shape_rotation(bone_transform, chain_dir)
            safe_bone = graph_utils.sanitize_name(bone_name)

            fk_ctrl = f"{module_prefix}_{safe_bone}_FK_CTRL"
            fk_key = graph_utils.create_control(
                hierarchy,
                hierarchy_controller,
                prev_fk_key,
                fk_ctrl,
                bone_position,
                unreal.LinearColor(1.0, 0.65, 0.1, 1.0),
                (fk_scale, fk_scale, fk_scale),
                shape_name="Circle_Thick",
                shape_rotation=shape_rot,
            )
            hierarchy.set_global_transform(fk_key, bone_transform, True, True)
            fk_controls.append(fk_ctrl)
            prev_fk_key = fk_key

            get_node = f"{module_prefix}_{safe_bone}_GetFK"
            graph_utils.create_unit_node(
                controller,
                model,
                get_node,
                unreal.RigUnit_GetControlTransform,
                unreal.Vector2D(x_origin, 200 + idx * 260),
            )
            graph_utils.set_pin_default(controller, model, f"{get_node}.Control", fk_ctrl)
            graph_utils.set_pin_default(controller, model, f"{get_node}.Space", "GlobalSpace")
            fk_get_nodes.append(get_node)

        # ------------------------------------------------------------------
        # 2. IK controls and blend data nodes
        # ------------------------------------------------------------------
        tip_transform = graph_utils.get_bone_global_transform(hierarchy, self.chain[-1])
        effector_pos = graph_utils.transform_to_location(tip_transform)

        ik_effector_ctrl = f"{module_prefix}_IK_CTRL"
        ik_effector_key = graph_utils.create_control(
            hierarchy,
            hierarchy_controller,
            parent_key,
            ik_effector_ctrl,
            effector_pos,
            unreal.LinearColor(0.0, 0.7, 1.0, 1.0),
            (ik_scale, ik_scale, ik_scale),
        )
        hierarchy.set_global_transform(ik_effector_key, tip_transform, True, True)

        get_eff_node = f"{module_prefix}_GetIKEff"
        lerp_node = f"{module_prefix}_IKFKLerp"
        ik_node = f"{module_prefix}_IKSolve"

        # IK/blend nodes sit to the right of the FK section.
        n_bones = len(self.chain)
        ik_col = x_origin + 500 + n_bones * 60 + 700

        graph_utils.create_unit_node(
            controller,
            model,
            get_eff_node,
            unreal.RigUnit_GetControlTransform,
            unreal.Vector2D(ik_col, 100),
        )
        graph_utils.set_pin_default(controller, model, f"{get_eff_node}.Control", ik_effector_ctrl)
        graph_utils.set_pin_default(controller, model, f"{get_eff_node}.Space", "GlobalSpace")

        lerp_struct = _pick_transform_lerp_struct()
        graph_utils.create_unit_node(
            controller,
            model,
            lerp_node,
            lerp_struct,
            unreal.Vector2D(ik_col + 320, 100),
        )
        fk_tip_out = f"{fk_get_nodes[-1]}.Transform"
        ik_eff_out = f"{get_eff_node}.Transform"
        _connect_lerp_inputs(controller, model, lerp_node, fk_tip_out, ik_eff_out)

        # ------------------------------------------------------------------
        # 3. IK solver node, auto-selected from chain length / recipe
        # ------------------------------------------------------------------
        all_nodes = [get_eff_node, lerp_node] + fk_get_nodes
        all_controls = list(fk_controls) + [ik_effector_ctrl]
        ik_pole_ctrl = None
        get_pole_node = None

        if solver_mode == "TwoBoneIK":
            ik_pole_ctrl, get_pole_node = self._build_two_bone_ik_solver(
                controller=controller,
                model=model,
                hierarchy=hierarchy,
                hierarchy_controller=hierarchy_controller,
                parent_key=parent_key,
                module_prefix=module_prefix,
                ik_node=ik_node,
                get_pole_node=f"{module_prefix}_GetIKPole",
                ik_pole_ctrl=f"{module_prefix}_PV_CTRL",
                ik_col=ik_col,
                pv_scale=pv_scale,
                recipe_data=recipe_data,
                lerp_node=lerp_node,
            )
            all_controls.append(ik_pole_ctrl)
            all_nodes.extend([get_pole_node, ik_node])
        else:
            self._build_fabrik_solver(
                controller=controller,
                model=model,
                ik_node=ik_node,
                ik_col=ik_col,
                lerp_node=lerp_node,
            )
            all_nodes.append(ik_node)

        # ------------------------------------------------------------------
        # 4. IKFKBlend variable  (0 = full FK, 1 = full IK)
        # ------------------------------------------------------------------
        blend_var = f"{module_prefix}_IKFKBlend"
        _ensure_float_variable(self.context.rig, blend_var, default_value=0.0)
        _bind_lerp_alpha_to_variable(
            controller,
            model,
            lerp_node,
            blend_var,
            unreal.Vector2D(ik_col + 320, 500),
        )

        # ------------------------------------------------------------------
        # 5. Execution chain: FK SetTransforms -> IK solver
        # ------------------------------------------------------------------
        exec_tail = self.context.get_exec_tail() or forwards_solve

        for idx, bone_name in enumerate(self.chain):
            safe_bone = graph_utils.sanitize_name(bone_name)
            set_node = f"{module_prefix}_{safe_bone}_SetFK"

            graph_utils.create_unit_node(
                controller,
                model,
                set_node,
                unreal.RigUnit_SetTransform,
                unreal.Vector2D(x_origin + 500, 200 + idx * 260),
            )
            graph_utils.set_key_pin(
                controller,
                model,
                set_node,
                ["Item", "Bone", "Child"],
                "Bone",
                bone_name,
            )
            graph_utils.set_any_pin(controller, model, set_node, ["Space"], "GlobalSpace")
            graph_utils.set_any_pin(controller, model, set_node, ["Initial"], "False")
            graph_utils.set_any_pin(controller, model, set_node, ["Weight"], "1.0")
            graph_utils.set_any_pin(
                controller,
                model,
                set_node,
                ["bPropagateToChildren", "PropagateToChildren"],
                "True",
            )

            fk_out = f"{fk_get_nodes[idx]}.Transform"
            if not graph_utils.connect_pins(controller, model, fk_out, f"{set_node}.Value"):
                graph_utils.connect_pins(controller, model, fk_out, f"{set_node}.Transform")

            _chain_exec(controller, model, exec_tail, set_node)
            exec_tail = set_node
            all_nodes.append(set_node)

        _chain_exec(controller, model, exec_tail, ik_node)
        exec_tail = ik_node
        self.context.set_exec_tail(exec_tail)

        if self.logger:
            self.logger.pop()

        attach_pts = {
            "root": self.chain[0],
            "tip": self.chain[-1],
            "ik_effector": ik_effector_ctrl,
        }
        if ik_pole_ctrl:
            attach_pts["ik_pole"] = ik_pole_ctrl

        for _i, _ctrl in enumerate(fk_controls):
            attach_pts[f"fk_ctrl_{_i}"] = _ctrl

        # Legacy names / convenience aliases.
        if len(self.chain) >= 2:
            attach_pts["mid"] = self.chain[len(self.chain) // 2]
        if len(fk_controls) >= 1:
            attach_pts["fk_root_ctrl"] = fk_controls[0]
        if len(fk_controls) >= 2:
            attach_pts["fk_tip_ctrl"] = fk_controls[-1]
        if len(fk_controls) == 3:
            attach_pts["fk_mid_ctrl"] = fk_controls[1]

        return self.build_result(
            controls=all_controls,
            nodes=all_nodes,
            attach_points=attach_pts,
            outputs={
                "fk_controls": fk_controls,
                "ik_effector_ctrl": ik_effector_ctrl,
                "ik_pole_ctrl": ik_pole_ctrl,
                "ik_node": ik_node,
                "blend_variable": blend_var,
                "solver_mode": solver_mode,
            },
            recipe_data=recipe_data,
            metadata={
                "control_scale": recipe_data.get("ControlScale"),
                "solver_type": recipe_data.get("SolverType"),
                "resolved_solver_mode": solver_mode,
                "default_blend": 0.0,
            },
        )

    # ------------------------------------------------------------------
    # Solver builders
    # ------------------------------------------------------------------

    def _build_two_bone_ik_solver(
        self,
        controller,
        model,
        hierarchy,
        hierarchy_controller,
        parent_key,
        module_prefix,
        ik_node,
        get_pole_node,
        ik_pole_ctrl,
        ik_col,
        pv_scale,
        recipe_data,
        lerp_node,
    ):
        """Build RigUnit_TwoBoneIKSimple for a classic 3-joint limb."""
        if len(self.chain) != 3:
            raise RuntimeError(
                f"TwoBoneIK mode requires exactly 3 joints, got {len(self.chain)} "
                f"for module '{self.name}'."
            )

        pole_distance_scale = float(recipe_data.get("PoleDistanceScale") or 0.75)
        pole_pos = graph_utils.compute_pole_vector(
            self.chain,
            hierarchy,
            pole_distance_scale=pole_distance_scale,
        )

        pole_key = graph_utils.create_control(
            hierarchy,
            hierarchy_controller,
            parent_key,
            ik_pole_ctrl,
            pole_pos,
            unreal.LinearColor(0.0, 0.35, 1.0, 1.0),
            (pv_scale, pv_scale, pv_scale),
        )
        hierarchy.set_control_offset_transform(pole_key, unreal.Transform(location=pole_pos), True, True)

        graph_utils.create_unit_node(
            controller,
            model,
            get_pole_node,
            unreal.RigUnit_GetControlTransform,
            unreal.Vector2D(ik_col, 380),
        )
        graph_utils.set_pin_default(controller, model, f"{get_pole_node}.Control", ik_pole_ctrl)
        graph_utils.set_pin_default(controller, model, f"{get_pole_node}.Space", "GlobalSpace")

        two_bone_struct = _pick_two_bone_ik_struct()
        _remove_stale_node_if_wrong_type(
            controller,
            model,
            ik_node,
            expected_title_contains=("two", "ik"),
        )

        existing = model.find_node(ik_node)
        if not existing:
            graph_utils.create_unit_node(
                controller,
                model,
                ik_node,
                two_bone_struct,
                unreal.Vector2D(ik_col + 700, 100),
            )
            _verify_node_title(ik_node, model, expected_words=("two", "ik"))

        graph_utils.set_any_pin(controller, model, ik_node, ["BoneA"], self.chain[0])
        graph_utils.set_any_pin(controller, model, ik_node, ["BoneB"], self.chain[1])
        graph_utils.set_any_pin(controller, model, ik_node, ["EffectorBone"], self.chain[2])

        lerp_out = f"{lerp_node}.Result"
        if not _connect_first_available(
            controller,
            model,
            lerp_out,
            [f"{ik_node}.Effector", f"{ik_node}.EffectorTransform"],
        ):
            _log_node_pins(ik_node, model)
            raise RuntimeError(
                f"Could not connect FK/IK lerp result to the TwoBoneIK effector pin "
                f"on node '{ik_node}'."
            )

        if not _connect_transform_translation_to_vector_pin(
            controller,
            model,
            get_pole_node,
            f"{ik_node}.PoleVector",
        ):
            # Fallback: solver still works with a static pole position, but the
            # pole control will not drive the pin until the pin path is updated.
            _set_vector_pin(controller, model, f"{ik_node}.PoleVector", pole_pos)
            _log_warning(
                f"Could not connect {get_pole_node}.Transform translation to "
                f"{ik_node}.PoleVector. A static pole vector default was set instead."
            )

        primary_axis = _recipe_vector(recipe_data.get("PrimaryAxis"), unreal.Vector(1.0, 0.0, 0.0))
        secondary_axis = _recipe_vector(recipe_data.get("SecondaryAxis"), unreal.Vector(0.0, 1.0, 0.0))
        pole_kind = str(recipe_data.get("PoleVectorKind") or "Location")

        _set_vector_pin(controller, model, f"{ik_node}.PrimaryAxis", primary_axis)
        _set_vector_pin(controller, model, f"{ik_node}.SecondaryAxis", secondary_axis)
        graph_utils.set_any_pin(controller, model, ik_node, ["SecondaryAxisWeight"], "1.0")
        graph_utils.set_any_pin(controller, model, ik_node, ["PoleVectorKind"], pole_kind)
        graph_utils.set_any_pin(controller, model, ik_node, ["PoleVectorSpace"], "None")
        graph_utils.set_any_pin(controller, model, ik_node, ["Weight"], "1.0")
        graph_utils.set_any_pin(controller, model, ik_node, ["PropagateToChildren"], "true")
        graph_utils.set_any_pin(controller, model, ik_node, ["BoneALength"], "0.0")
        graph_utils.set_any_pin(controller, model, ik_node, ["BoneBLength"], "0.0")

        enable_stretch = _recipe_bool(recipe_data.get("EnableStretch"), False)
        graph_utils.set_any_pin(
            controller,
            model,
            ik_node,
            ["EnableStretch"],
            "true" if enable_stretch else "false",
        )
        if enable_stretch:
            graph_utils.set_any_pin(
                controller,
                model,
                ik_node,
                ["StretchStartRatio"],
                str(float(recipe_data.get("StretchStartRatio") or 1.0)),
            )
            graph_utils.set_any_pin(
                controller,
                model,
                ik_node,
                ["StretchMaximumRatio"],
                str(float(recipe_data.get("StretchMaximumRatio") or 1.2)),
            )

        return ik_pole_ctrl, get_pole_node

    def _build_fabrik_solver(self, controller, model, ik_node, ik_col, lerp_node):
        """Build RigUnit_FABRIK for arbitrary-length IK/FK chains."""
        fabrik_struct = _pick_fabrik_struct()
        _remove_stale_node_if_wrong_type(
            controller,
            model,
            ik_node,
            expected_title_contains="fabrik",
        )

        existing = model.find_node(ik_node)
        if not existing:
            if fabrik_struct is not None:
                graph_utils.create_unit_node(
                    controller,
                    model,
                    ik_node,
                    fabrik_struct,
                    unreal.Vector2D(ik_col + 700, 100),
                )
            else:
                controller.add_unit_node_from_struct_path(
                    "/Script/ControlRig.RigUnit_FABRIK",
                    "Execute",
                    unreal.Vector2D(ik_col + 700, 100),
                    ik_node,
                )
            _verify_node_title(ik_node, model, expected_words=("fabrik",))

        graph_utils.set_any_pin(controller, model, ik_node, ["StartBone"], self.chain[0])
        graph_utils.set_any_pin(controller, model, ik_node, ["EffectorBone"], self.chain[-1])

        lerp_out = f"{lerp_node}.Result"
        if not _connect_first_available(
            controller,
            model,
            lerp_out,
            [f"{ik_node}.EffectorTransform", f"{ik_node}.Effector"],
        ):
            _log_node_pins(ik_node, model)
            raise RuntimeError(
                f"Could not connect FK/IK lerp result to the FABRIK effector pin "
                f"on node '{ik_node}'."
            )

        graph_utils.set_any_pin(controller, model, ik_node, ["SetEffectorTransform"], "true")
        graph_utils.set_any_pin(controller, model, ik_node, ["MaxIterations"], "16")
        graph_utils.set_any_pin(controller, model, ik_node, ["Precision"], "0.01")
        graph_utils.set_any_pin(controller, model, ik_node, ["Weight"], "1.0")
        graph_utils.set_any_pin(controller, model, ik_node, ["PropagateToChildren"], "true")

    # ------------------------------------------------------------------
    # Recipe
    # ------------------------------------------------------------------

    def read_recipe(self):
        recipe_fields = {
            "ModuleType": None,
            "ControlScale": 1.0,
            "SolverType": "Auto",
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
            "ControlScale": ["control_scale", "controlscale"],
            "SolverType": ["solver_type", "solvertype"],
            "PrimaryAxis": ["primary_axis", "primaryaxis"],
            "SecondaryAxis": ["secondary_axis", "secondaryaxis"],
            "PoleVectorKind": ["pole_vector_kind", "polevectorkind"],
            "PoleDistanceScale": ["pole_distance_scale", "poledistancescale"],
            "EnableStretch": ["enable_stretch", "enablestretch"],
            "StretchStartRatio": ["stretch_start_ratio", "stretchstartratio"],
            "StretchMaximumRatio": ["stretch_maximum_ratio", "stretchmaximumratio"],
        }
        return self.resolve_recipe_fields(recipe_fields, fallback_names=fallback_names)


# ---------------------------------------------------------------------------
# Solver selection helpers
# ---------------------------------------------------------------------------


def _choose_solver_mode(chain: Sequence[str], recipe_data: dict) -> str:
    raw_solver = str(recipe_data.get("SolverType") or "Auto").strip().lower()
    aliases = {
        "": "auto",
        "auto": "auto",
        "automatic": "auto",
        "default": "auto",
        "basicik": "twoboneik",
        "basic_ik": "twoboneik",
        "two bone ik": "twoboneik",
        "two_bone_ik": "twoboneik",
        "twoboneik": "twoboneik",
        "twoboneiksimple": "twoboneik",
        "two_bone_ik_simple": "twoboneik",
        "fabrik": "fabrik",
        "basicfabrik": "fabrik",
        "basic_fabrik": "fabrik",
    }

    solver = aliases.get(raw_solver)
    if solver is None:
        raise RuntimeError(
            f"Unsupported IKFK SolverType '{recipe_data.get('SolverType')}'. "
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


# ---------------------------------------------------------------------------
# Graph helpers specific to IKFKSwitch
# ---------------------------------------------------------------------------


def _chain_exec(controller, model, from_node, to_node):
    """Connect execution from from_node to to_node."""
    src = (
        f"{from_node}.ExecuteContext"
        if graph_utils.pin_exists(model, f"{from_node}.ExecuteContext")
        else f"{from_node}.Execute"
    )
    dst = (
        f"{to_node}.ExecuteContext"
        if graph_utils.pin_exists(model, f"{to_node}.ExecuteContext")
        else f"{to_node}.Execute"
    )
    graph_utils.connect_pins(controller, model, src, dst)


def _remove_stale_node_if_wrong_type(controller, model, node_name, expected_title_contains):
    """Remove an existing node if it has the wrong type/title.

    This keeps rebuilds safe when the same module name changes from FABRIK to
    TwoBoneIK or the other way around.
    """
    node = model.find_node(node_name)
    if not node or not hasattr(node, "get_node_title"):
        return

    title = str(node.get_node_title())
    title_lower = title.lower()

    if isinstance(expected_title_contains, str):
        expected_ok = expected_title_contains.lower() in title_lower
    else:
        expected_ok = all(str(word).lower() in title_lower for word in expected_title_contains)

    if expected_ok:
        return

    _log_warning(
        f"Removing stale node '{node_name}' with title '{title}'. "
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


def _verify_node_title(node_name, model, expected_words: Iterable[str]):
    node = model.find_node(node_name)
    if not node or not hasattr(node, "get_node_title"):
        return

    title = str(node.get_node_title())
    title_lower = title.lower()
    if all(str(word).lower() in title_lower for word in expected_words):
        return

    raise RuntimeError(
        f"Node '{node_name}' was created but its title is '{title}', which does "
        f"not match expected words {tuple(expected_words)!r}. Check the Control "
        "Rig node palette/API name for this Unreal build."
    )


def _pick_fabrik_struct():
    """Return the FABRIK unit struct class, or None for struct-path fallback."""
    for candidate in ("RigUnit_FABRIK", "RigUnit_Fabrik", "RigUnit_BasicFabrik"):
        if hasattr(unreal, candidate):
            return getattr(unreal, candidate)
    return None


def _pick_two_bone_ik_struct():
    """Return the Two Bone IK unit struct class for UE Control Rig."""
    for candidate in ("RigUnit_TwoBoneIKSimple",):
        if hasattr(unreal, candidate):
            return getattr(unreal, candidate)
    raise RuntimeError(
        "Could not find RigUnit_TwoBoneIKSimple in this Unreal Python API. "
        "For UE 5.6 this class should exist in the ControlRig module."
    )


def _pick_transform_lerp_struct():
    """Return a transform-lerp unit struct class for blending FK/IK targets."""
    for candidate in (
        "RigUnit_MathTransformLerp",
        "RigVMFunction_MathTransformLerp",
        "RigUnit_MathTransformInterpolate",
    ):
        if hasattr(unreal, candidate):
            return getattr(unreal, candidate)
    raise RuntimeError(
        "Could not find a transform-lerp unit in this Unreal Python API. "
        "Check the Control Rig math function library for the correct struct name "
        "and add it to _pick_transform_lerp_struct."
    )


def _connect_lerp_inputs(controller, model, lerp_node, a_pin, b_pin):
    """Wire the two transform inputs of a transform-lerp node."""
    candidate_pairs = (("A", "B"), ("Min", "Max"), ("From", "To"))
    for first, second in candidate_pairs:
        first_pin = f"{lerp_node}.{first}"
        second_pin = f"{lerp_node}.{second}"
        if graph_utils.pin_exists(model, first_pin) and graph_utils.pin_exists(model, second_pin):
            graph_utils.connect_pins(controller, model, a_pin, first_pin)
            graph_utils.connect_pins(controller, model, b_pin, second_pin)
            return

    _log_node_pins(lerp_node, model)
    raise RuntimeError(
        f"Could not find transform input pins on lerp node '{lerp_node}'. "
        "Check the log above for the actual sub-pin names."
    )


def _bind_lerp_alpha_to_variable(controller, model, lerp_node, blend_var, getter_pos):
    alpha_pin = None
    for candidate in ("Alpha", "T", "Blend"):
        pin_path = f"{lerp_node}.{candidate}"
        if graph_utils.pin_exists(model, pin_path):
            alpha_pin = pin_path
            break

    if not alpha_pin:
        _log_node_pins(lerp_node, model)
        raise RuntimeError(
            f"Could not find an alpha/blend pin on lerp node '{lerp_node}'."
        )

    try:
        controller.bind_pin_to_variable(alpha_pin, blend_var)
        return
    except Exception:
        pass

    get_blend_node = f"{lerp_node}_GetBlend"
    _create_variable_getter(controller, model, get_blend_node, blend_var, getter_pos)
    for out_pin in (blend_var, "Value", "ReturnValue"):
        if graph_utils.connect_pins(controller, model, f"{get_blend_node}.{out_pin}", alpha_pin):
            return

    _log_node_pins(get_blend_node, model)
    raise RuntimeError(
        f"Could not bind or connect blend variable '{blend_var}' to '{alpha_pin}'."
    )


def _connect_first_available(controller, model, source_pin: str, target_pins: Sequence[str]) -> bool:
    for target_pin in target_pins:
        if graph_utils.connect_pins(controller, model, source_pin, target_pin):
            return True
    return False


def _connect_transform_translation_to_vector_pin(controller, model, get_transform_node, vector_pin) -> bool:
    """Connect a GetControlTransform translation/location sub-pin to a vector pin."""
    source_candidates = (
        f"{get_transform_node}.Transform.Translation",
        f"{get_transform_node}.Transform.Location",
        f"{get_transform_node}.Transform.Position",
    )
    for source_pin in source_candidates:
        if graph_utils.connect_pins(controller, model, source_pin, vector_pin):
            return True
    return False


def _set_vector_pin(controller, model, pin_path, vector) -> bool:
    """Set a FVector-style pin by sub-pins when possible, then compound default."""
    values = {
        "X": float(vector.x),
        "Y": float(vector.y),
        "Z": float(vector.z),
    }

    found_subpins = False
    for axis, value in values.items():
        sub_pin = f"{pin_path}.{axis}"
        if graph_utils.pin_exists(model, sub_pin):
            graph_utils.set_pin_default(controller, model, sub_pin, str(value))
            found_subpins = True

    if found_subpins:
        return True

    if graph_utils.pin_exists(model, pin_path):
        graph_utils.set_pin_default(
            controller,
            model,
            pin_path,
            f"(X={values['X']},Y={values['Y']},Z={values['Z']})",
        )
        return True

    return False


def _recipe_vector(value, fallback):
    """Parse a vector from recipe data.

    Accepts Unreal Vector, tuple/list [x, y, z], dict {X/Y/Z}, or string
    "x,y,z". Returns fallback on unsupported data.
    """
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
        # Support either "1,0,0" or "X=1,Y=0,Z=0".
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


def _recipe_bool(value, fallback=False):
    if value is None:
        return bool(fallback)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}
    return bool(fallback)


def _log_node_pins(node_name, model):
    """Log every pin and nested sub-pin on a node for diagnosing UE API changes."""
    node = model.find_node(node_name)
    if not node or not hasattr(unreal, "log"):
        return
    for pin in node.get_pins():
        unreal.log(
            f"[RigBuilder] '{node_name}' pin: '{pin.get_name()}' "
            f"cpp_type='{pin.get_cpp_type()}'"
        )
        for sub in pin.get_sub_pins():
            unreal.log(
                f"[RigBuilder]   sub-pin: '{sub.get_name()}' "
                f"cpp_type='{sub.get_cpp_type()}'"
            )


def _log_warning(message):
    if hasattr(unreal, "log_warning"):
        unreal.log_warning(f"[RigBuilder] {message}")
    elif hasattr(unreal, "log"):
        unreal.log(f"[RigBuilder] WARNING: {message}")


def _ensure_float_variable(rig, var_name, default_value=0.0):
    """Declare a float member variable on the rig blueprint if missing."""
    existing = [v for v in (rig.get_member_variables() or []) if str(v.name) == var_name]
    if not existing:
        rig.add_member_variable(var_name, "float", True, False, str(default_value))


def _create_variable_getter(controller, model, node_name, var_name, position):
    """Place a getter node for a rig variable."""
    if model.find_node(node_name):
        return
    controller.add_variable_node(
        var_name,
        "float",
        None,
        True,
        "0.0",
        position,
        node_name,
    )


def _create_variable_setter(controller, model, node_name, var_name, position):
    """Place a setter node for a rig variable (not wired into exec here)."""
    if model.find_node(node_name):
        return
    controller.add_variable_node(
        var_name,
        "float",
        None,
        False,
        "0.0",
        position,
        node_name,
    )
