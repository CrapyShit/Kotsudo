from typing import Any, Iterable, Optional, Sequence, Tuple, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)

from .. import graph_utils
from .rig_module import RigModule

IKFK_MODULE_VERSION = "2026-07-14-three-bone-only-v3"

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
# Scope (as of 2026-07-14): IKFKSwitch is intentionally restricted to
# exactly 3-bone chains, using RigUnit_TwoBoneIKSimple ("Basic IK" in the
# UE 5.6 graph). Chains of 4+ bones are rejected at validate() rather than
# silently routed through FABRIK -- this was previously supported but is
# disabled for now to keep this module simple and predictable. IKModule
# (the plain non-switch IKLimb) still supports arbitrary chain lengths via
# FABRIK for spines/tails/tentacles; only the IKFKSwitch module is
# restricted to 3 bones.
# ---------------------------------------------------------------------------


class IKFKModule(RigModule):
    """IK/FK switch module for exactly 3-bone chains.

    Builds Control Rig's native two-bone solver (RigUnit_TwoBoneIKSimple,
    displays as "Basic IK" in UE 5.6). Chains of any other length are
    rejected in validate() with a clear error.

    Attach points
    -------------
    root            - first bone
    mid             - middle bone
    tip             - last bone
    fk_ctrl_N       - FK control for bone index N (0-based)
    ik_effector     - IK effector control
    ik_pole         - pole vector control
    """

    module_type = "IKFKSwitch"

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
            "required_metadata": ["ModuleType", "ModuleName"],
            "required_recipe_fields": ["ControlScale"],
            "attachment_points": [
                "root",
                "mid",
                "tip",
                "ik_effector",
                "ik_pole",
            ],
            "build_products": ["controls", "nodes", "attach_points"],
        }

    def validate(self):
        if len(self.chain) != 3:
            raise RuntimeError(
                f"IKFKSwitch module '{self.name}' only supports exactly 3-bone "
                f"chains (upper -> lower -> tip), got {len(self.chain)} bones: "
                f"{self.chain}. 4+ joint IK/FK chains are not supported by this "
                "module by design -- use IKLimb (plain IK, no switch) if you "
                "need FABRIK on a longer chain."
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
        _log_info(
            f"IKFKModule version: {IKFK_MODULE_VERSION}; "
            f"module={self.name}; solver=TwoBoneIK; chain_length={len(self.chain)}"
        )

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
        # 3. IK solver node (always TwoBoneIK -- chain length is guaranteed
        #    to be exactly 3 by validate() above)
        # ------------------------------------------------------------------
        all_nodes = [get_eff_node, lerp_node] + fk_get_nodes
        all_controls = list(fk_controls) + [ik_effector_ctrl]

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

        # ------------------------------------------------------------------
        # 4. IKFKBlend variable  (0 = full FK, 1 = full IK)
        #
        # default_blend comes from Maya's detected switch attribute value
        # (params.default_value in the manifest, via the DefaultBlend recipe
        # field) so the UE5 rig opens in whatever FK/IK mix the rig was left
        # in when exported, instead of always resetting to full FK.
        # ------------------------------------------------------------------
        blend_var = f"{module_prefix}_IKFKBlend"
        default_blend = float(recipe_data.get("DefaultBlend") or 0.0)
        _ensure_float_variable(self.context.rig, blend_var, default_value=default_blend)
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
            "mid": self.chain[1],
            "tip": self.chain[-1],
            "ik_effector": ik_effector_ctrl,
            "ik_pole": ik_pole_ctrl,
        }

        for _i, _ctrl in enumerate(fk_controls):
            attach_pts[f"fk_ctrl_{_i}"] = _ctrl

        # Legacy names / convenience aliases.
        attach_pts["fk_root_ctrl"] = fk_controls[0]
        attach_pts["fk_mid_ctrl"] = fk_controls[1]
        attach_pts["fk_tip_ctrl"] = fk_controls[-1]

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
                "solver_mode": "TwoBoneIK",
            },
            recipe_data=recipe_data,
            metadata={
                "control_scale": recipe_data.get("ControlScale"),
                "resolved_solver_mode": "TwoBoneIK",
                "default_blend": default_blend,
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
            expected_title_contains=(("two", "ik"), ("basic", "ik"), "basic ik"),
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
            _verify_node_title(
                ik_node,
                model,
                expected_options=(("two", "ik"), ("basic", "ik"), "basic ik"),
            )

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

    # ------------------------------------------------------------------
    # Recipe
    # ------------------------------------------------------------------

    def read_recipe(self):
        recipe_fields = {
            "ModuleType": None,
            "ControlScale": 1.0,
            "PrimaryAxis": None,
            "SecondaryAxis": None,
            "PoleVectorKind": "Location",
            "PoleDistanceScale": 0.75,
            "EnableStretch": False,
            "StretchStartRatio": 1.0,
            "StretchMaximumRatio": 1.2,
            "DefaultBlend": 0.0,
        }
        fallback_names = {
            "ModuleType": ["module_type"],
            "ControlScale": ["control_scale", "controlscale"],
            "PrimaryAxis": ["primary_axis", "primaryaxis"],
            "SecondaryAxis": ["secondary_axis", "secondaryaxis"],
            "PoleVectorKind": ["pole_vector_kind", "polevectorkind"],
            "PoleDistanceScale": ["pole_distance_scale", "poledistancescale"],
            "EnableStretch": ["enable_stretch", "enablestretch"],
            "StretchStartRatio": ["stretch_start_ratio", "stretchstartratio"],
            "StretchMaximumRatio": ["stretch_maximum_ratio", "stretchmaximumratio"],
            "DefaultBlend": ["default_value", "defaultvalue", "default_blend"],
        }
        return self.resolve_recipe_fields(recipe_fields, fallback_names=fallback_names)


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


def _title_matches_expected(title, expected_title_contains) -> bool:
    """Return True if a node title matches one accepted title pattern.

    Accepted formats:
        "fabrik"                         -> substring match
        ("two", "ik")                    -> all words must be present
        (("two", "ik"), ("basic", "ik")) -> any option may match

    This matters in UE 5.6 because RigUnit_TwoBoneIKSimple can appear in the
    Control Rig graph with the display title "Basic IK" instead of
    "Two Bone IK".
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

    # A flat tuple/list of strings means all words must be present.
    # Example: ("two", "ik")
    if all(isinstance(item, str) for item in items):
        return all(item.lower() in title_lower for item in items)

    # A nested tuple/list means any pattern may match.
    # Example: (("two", "ik"), ("basic", "ik"), "basic ik")
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


def _remove_stale_node_if_wrong_type(controller, model, node_name, expected_title_contains):
    """Remove an existing node if it clearly has the wrong type/title.

    This keeps rebuilds safe when the same module name changes from FABRIK to
    TwoBoneIK or the other way around.

    Important UE 5.6 note:
    RigUnit_TwoBoneIKSimple may display as "Basic IK". That is valid, so this
    helper supports multiple accepted title patterns.
    """
    node = model.find_node(node_name)
    if not node or not hasattr(node, "get_node_title"):
        return

    title = str(node.get_node_title())

    if _title_matches_expected(title, expected_title_contains):
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


def _verify_node_title(node_name, model, expected_words=None, expected_options=None) -> bool:
    """Check node title without aborting the build.

    Previous versions raised RuntimeError here. That was too fragile because
    UE 5.6 can create RigUnit_TwoBoneIKSimple while displaying the node title
    as "Basic IK". This function now only logs a warning and lets the later
    pin connections prove whether the node is usable.
    """
    node = model.find_node(node_name)
    if not node or not hasattr(node, "get_node_title"):
        return True

    title = str(node.get_node_title())
    expected = expected_options if expected_options is not None else expected_words

    if _title_matches_expected(title, expected):
        _log_info(
            f"Node '{node_name}' title '{title}' accepted for expected pattern "
            f"{expected!r}."
        )
        return True

    _log_warning(
        f"Node '{node_name}' has title '{title}', expected {expected!r}. "
        "Continuing because Control Rig display titles can differ from the "
        "Python struct name; pin wiring will fail later if this is truly the "
        "wrong node type."
    )
    return False


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


def _log_info(message):
    if hasattr(unreal, "log"):
        unreal.log(f"[RigBuilder] {message}")


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