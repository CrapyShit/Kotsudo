from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)

from .. import graph_utils
from .rig_module import RigModule

# ---------------------------------------------------------------------------
# IKFKSwitch module
# ---------------------------------------------------------------------------
# Graph layout per bone (left to right):
#
#   GetFK (GetControlTransform)
#       |
#       v                              SetTransform (bone, weight=1.0)
#   [FK pose written for every bone in the chain, unconditionally]
#
#   GetFK_tip.Transform ──────┐
#                              v
#                        MathTransformLerp ──► FABRIK.EffectorTransform
#                              ^
#   GetIK_effector.Transform ─┘
#            (alpha = IKFKBlend variable, 0 = FK, 1 = IK)
#
#   FABRIK (StartBone = self.chain[0], EffectorBone = self.chain[-1] --
#           solves every bone in between by walking the hierarchy)
#
# The FK phase always runs first and writes a full FK pose onto every bone.
# FABRIK then runs afterwards and re-solves the whole chain toward a single
# blended effector transform. Because FABRIK is iterative and converges from
# whatever pose the chain currently holds, running it after the FK write
# means that at IKFKBlend = 0 (target ≈ current FK tip position) the solve
# settles back onto the existing FK pose almost exactly, and at
# IKFKBlend = 1 the chain solves fully toward the IK control.
#
# FABRIK is a core Control Rig "Basic IK" chain solver (not a plugin, unlike
# the Full Body IK / PBIK node this module used previously). It takes the
# whole joint chain plus a single effector transform, which is a more direct
# fit for an arbitrary-length IK/FK chain than routing through a full-body
# solver.
#
# The IKFKBlend variable is a float (0 = full FK, 1 = full IK) added as a
# rig variable so it appears in the CR detail panel and can be animated.
# ---------------------------------------------------------------------------


class IKFKModule(RigModule):
    """IK/FK switch module for any-length joint chain (2+ bones).

    Builds both an FK chain (one control per bone) and an IK setup from the
    same joint chain, then blends between them by feeding a lerp of the FK
    tip transform and the IK effector transform into a FABRIK solver that
    covers the whole chain.

    Uses Control Rig's core FABRIK node (``RigUnit_Fabrik``) for all chain
    lengths. No extra plugin is required.

    The blend is driven by a transform lerp (FK tip ↔ IK effector) feeding
    FABRIK's effector pin, with the lerp alpha bound to the ``IKFKBlend``
    variable (0 = FK, 1 = IK).

    Attach points
    -------------
    root            – first bone
    tip             – last bone
    fk_ctrl_N       – FK control for bone index N  (0-based)
    ik_effector     – IK effector control

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
                "root", "tip",
                "ik_effector",
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

        parent_key = (
            self.context.get_parent_control_key(self.parent_module_name, self.parent_attach_point)
            or graph_utils.get_world_parent_key(hierarchy, hierarchy_controller)
        )

        x_origin = self.context.claim_module_column(width=1400)

        # ------------------------------------------------------------------
        # 1. FK controls (one per bone, parented in a chain)
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
                hierarchy, hierarchy_controller,
                prev_fk_key, fk_ctrl, bone_position,
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
                controller, model, get_node,
                unreal.RigUnit_GetControlTransform,
                unreal.Vector2D(x_origin, 200 + idx * 260),
            )
            graph_utils.set_pin_default(controller, model, f"{get_node}.Control", fk_ctrl)
            graph_utils.set_pin_default(controller, model, f"{get_node}.Space", "GlobalSpace")
            fk_get_nodes.append(get_node)

        # ------------------------------------------------------------------
        # 2. IK effector control + FABRIK node
        # ------------------------------------------------------------------
        # Blend design:
        #
        #   a) FK SetTransforms write every bone to the FK ctrl pose (weight=1),
        #      unconditionally, first in the exec chain.
        #   b) A MathTransformLerp blends [FK tip transform] <-> [IK ctrl
        #      transform] using IKFKBlend as alpha, feeding FABRIK's
        #      effector pin directly (no intermediate bone write/read-back
        #      needed -- FABRIK takes an explicit effector transform input).
        #   c) FABRIK solves the whole chain (root..tip) toward that target,
        #      running after the FK write so it converges from the current
        #      FK-posed chain rather than an arbitrary rest pose.
        #
        # At blend=0: target == FK tip transform -> FABRIK settles back onto
        # the FK pose it started from almost exactly.
        # At blend=1: target == IK ctrl transform -> FABRIK solves the chain
        # fully toward the IK control.

        effector_pos = graph_utils.get_bone_global_position(hierarchy, self.chain[-1])

        ik_effector_ctrl = f"{module_prefix}_IK_CTRL"
        graph_utils.create_control(
            hierarchy, hierarchy_controller,
            parent_key, ik_effector_ctrl, effector_pos,
            unreal.LinearColor(0.0, 0.7, 1.0, 1.0),
            (ik_scale, ik_scale, ik_scale),
        )

        get_eff_node = f"{module_prefix}_GetIKEff"
        lerp_node = f"{module_prefix}_IKFKLerp"
        ik_node = f"{module_prefix}_IKSolve"

        # IK/blend nodes sit to the RIGHT of all FK columns.
        n_bones = len(self.chain)
        ik_col = x_origin + 500 + n_bones * 60 + 700

        # GetControlTransform for the IK effector control.
        graph_utils.create_unit_node(
            controller, model, get_eff_node,
            unreal.RigUnit_GetControlTransform,
            unreal.Vector2D(ik_col, 100),
        )
        graph_utils.set_pin_default(controller, model, f"{get_eff_node}.Control", ik_effector_ctrl)
        graph_utils.set_pin_default(controller, model, f"{get_eff_node}.Space", "GlobalSpace")

        # Transform lerp: FK tip <-> IK effector, alpha = IKFKBlend.
        lerp_struct = _pick_transform_lerp_struct()
        graph_utils.create_unit_node(
            controller, model, lerp_node,
            lerp_struct,
            unreal.Vector2D(ik_col + 320, 100),
        )
        fk_tip_out = f"{fk_get_nodes[-1]}.Transform"
        ik_eff_out = f"{get_eff_node}.Transform"
        _connect_lerp_inputs(controller, model, lerp_node, fk_tip_out, ik_eff_out)

        # FABRIK node -- core Control Rig "Basic IK" chain solver.
        fabrik_struct = _pick_fabrik_struct()
        _remove_stale_node_if_wrong_type(controller, model, ik_node, expected_title_contains="Fabrik")
        existing = model.find_node(ik_node)
        if not existing:
            if fabrik_struct is not None:
                graph_utils.create_unit_node(
                    controller, model, ik_node,
                    fabrik_struct,
                    unreal.Vector2D(ik_col + 700, 100),
                )
            else:
                # Core struct not found under a known name -- fall back to
                # looking it up by struct path, same pattern used for
                # plugin-provided units elsewhere in this codebase.
                controller.add_unit_node_from_struct_path(
                    '/Script/ControlRig.RigUnit_Fabrik',
                    'Execute',
                    unreal.Vector2D(ik_col + 700, 100),
                    ik_node,
                )
            # Verify what actually got created -- if the struct path also
            # resolves to something unexpected (e.g. this engine build has
            # no core Fabrik struct at all), fail loudly instead of quietly
            # building against the wrong node type.
            created = model.find_node(ik_node)
            if created and hasattr(created, "get_node_title"):
                title = created.get_node_title()
                if "fabrik" not in title.lower():
                    raise RuntimeError(
                        f"Node '{ik_node}' was created but its title is '{title}', "
                        "not a Fabrik node. This engine build's Control Rig may not "
                        "expose a core Fabrik unit under the names this module tries "
                        "-- check the Control Rig node palette for the correct name "
                        "and add it to _pick_fabrik_struct's candidate list."
                    )

        # RigUnit_FABRIK solves everything between StartBone and
        # EffectorBone by walking the hierarchy between them -- it does NOT
        # take an explicit array of joints (that's a different node,
        # RigUnit_FABRIKItemArray). Confirmed against the UE5 Python API:
        #   RigUnit_FABRIK(start_bone, effector_bone, effector_transform,
        #                  precision, weight, propagate_to_children,
        #                  max_iterations, set_effector_transform)
        graph_utils.set_any_pin(controller, model, ik_node, ["StartBone"], self.chain[0])
        graph_utils.set_any_pin(controller, model, ik_node, ["EffectorBone"], self.chain[-1])

        # Effector transform input -- fed by the FK/IK lerp above.
        lerp_out = f"{lerp_node}.Result"
        if not graph_utils.connect_pins(controller, model, lerp_out, f"{ik_node}.EffectorTransform"):
            _log_node_pins(ik_node, model)
            raise RuntimeError(
                f"Could not connect the FK/IK lerp result to '{ik_node}.EffectorTransform'. "
                "Check the log above for the actual pin name."
            )

        # SetEffectorTransform gates whether the wired EffectorTransform pin
        # is actually used by the solver. We're driving it explicitly via
        # the lerp, so this needs to be true -- if the chain doesn't respond
        # to EffectorTransform in-editor, this is the first thing to check.
        graph_utils.set_any_pin(controller, model, ik_node, ["SetEffectorTransform"], "true")

        graph_utils.set_any_pin(controller, model, ik_node, ["MaxIterations"], "16")
        graph_utils.set_any_pin(controller, model, ik_node, ["Precision"], "0.01")
        graph_utils.set_any_pin(controller, model, ik_node, ["Weight"], "1.0")
        graph_utils.set_any_pin(controller, model, ik_node, ["PropagateToChildren"], "true")

        # ------------------------------------------------------------------
        # 3. IKFKBlend variable  (0 = full FK, 1 = full IK)
        # ------------------------------------------------------------------
        blend_var = f"{module_prefix}_IKFKBlend"
        _ensure_float_variable(self.context.rig, blend_var, default_value=0.0)

        # Bind the lerp's alpha pin directly to the blend variable.
        alpha_pin = None
        for candidate in ("Alpha", "T", "Blend"):
            pin_path = f"{lerp_node}.{candidate}"
            if graph_utils.pin_exists(model, pin_path):
                alpha_pin = pin_path
                break

        if alpha_pin:
            try:
                controller.bind_pin_to_variable(alpha_pin, blend_var)
            except Exception:
                get_blend_node = f"{module_prefix}_GetBlend"
                _create_variable_getter(controller, model, get_blend_node, blend_var,
                                        unreal.Vector2D(ik_col + 320, 500))
                for _out_pin in (blend_var, "Value", "ReturnValue"):
                    try:
                        controller.add_link(f"{get_blend_node}.{_out_pin}", alpha_pin)
                        break
                    except Exception:
                        pass
        else:
            _log_node_pins(lerp_node, model)
            raise RuntimeError(
                f"Could not find an alpha/blend pin on lerp node '{lerp_node}'. "
                "Check the log above for the actual sub-pin names."
            )

        # ------------------------------------------------------------------
        # 4. Execution chain: FK SetTransforms -> FABRIK.
        #
        #   a) Per-bone FK SetTransform(weight=1.0) writes the FK ctrl pose.
        #   b) FABRIK (fed by the FK/IK lerp above) solves the full chain.
        #
        # The lerp node has no exec pin (pure data node) -- it just needs to
        # sit upstream of FABRIK in the data graph, which it already does via
        # the Result -> EffectorTransform link made above.
        # ------------------------------------------------------------------
        all_nodes = [get_eff_node, lerp_node, ik_node] + fk_get_nodes

        exec_tail = self.context.get_exec_tail() or forwards_solve

        # FK phase: one SetTransform per bone, weight=1.0 (always full FK base)
        for idx, bone_name in enumerate(self.chain):
            safe_bone = graph_utils.sanitize_name(bone_name)
            set_node = f"{module_prefix}_{safe_bone}_SetFK"

            graph_utils.create_unit_node(
                controller, model, set_node,
                unreal.RigUnit_SetTransform,
                unreal.Vector2D(x_origin + 500, 200 + idx * 260),
            )
            graph_utils.set_key_pin(controller, model, set_node,
                ["Item", "Bone", "Child"], "Bone", bone_name)
            graph_utils.set_any_pin(controller, model, set_node, ["Space"], "GlobalSpace")
            graph_utils.set_any_pin(controller, model, set_node, ["Initial"], "False")
            graph_utils.set_any_pin(controller, model, set_node, ["Weight"], "1.0")
            graph_utils.set_any_pin(controller, model, set_node,
                ["bPropagateToChildren", "PropagateToChildren"], "True")

            fk_out = f"{fk_get_nodes[idx]}.Transform"
            if not graph_utils.connect_pins(controller, model, fk_out, f"{set_node}.Value"):
                graph_utils.connect_pins(controller, model, fk_out, f"{set_node}.Transform")

            _chain_exec(controller, model, exec_tail, set_node)
            exec_tail = set_node
            all_nodes.append(set_node)

        # IK phase: FABRIK runs after all FK writes are in place.
        _chain_exec(controller, model, exec_tail, ik_node)
        exec_tail = ik_node

        self.context.set_exec_tail(exec_tail)

        if self.logger:
            self.logger.pop()

        all_controls = fk_controls + [ik_effector_ctrl]

        # Build attach_points dynamically so any chain length is covered.
        attach_pts = {
            "root": self.chain[0],
            "tip": self.chain[-1],
            "ik_effector": ik_effector_ctrl,
        }
        for _i, _ctrl in enumerate(fk_controls):
            attach_pts[f"fk_ctrl_{_i}"] = _ctrl
        # Legacy 3-bone names for backwards compatibility.
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
                "ik_node": ik_node,
                "blend_variable": blend_var,
            },
            recipe_data=recipe_data,
            metadata={
                "control_scale": recipe_data.get("ControlScale"),
                "solver_type": recipe_data.get("SolverType"),
                "default_blend": 0.0,
            },
        )

    # ------------------------------------------------------------------
    # Recipe
    # ------------------------------------------------------------------

    def read_recipe(self):
        recipe_fields = {
            "ModuleType": None,
            "ControlScale": 1.0,
            "SolverType": None,
        }
        fallback_names = {
            "ModuleType": ["module_type"],
            "ControlScale": ["control_scale", "controlscale"],
            "SolverType": ["solver_type", "solvertype"],
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


def _remove_stale_node_if_wrong_type(controller, model, node_name, expected_title_contains):
    """If a node already exists under this name but isn't the type we expect
    (e.g. an old PBIK node left over from a previous build of this module,
    now sitting under the name this version wants to use for FABRIK), remove
    it so the idempotent "only create if missing" check below doesn't
    silently reuse the wrong node.
    """
    node = model.find_node(node_name)
    if not node or not hasattr(node, "get_node_title"):
        return

    title = node.get_node_title()
    if expected_title_contains.lower() in title.lower():
        return  # already the right kind of node, leave it alone

    if hasattr(unreal, "log"):
        unreal.log(
            f"[RigBuilder] Removing stale node '{node_name}' (title '{title}') "
            f"-- expected a node containing '{expected_title_contains}'."
        )

    for remove_method in ("remove_node", "remove_node_by_name"):
        if hasattr(controller, remove_method):
            try:
                arg = node if remove_method == "remove_node" else node_name
                getattr(controller, remove_method)(arg)
                return
            except Exception:
                continue


def _pick_fabrik_struct():
    """Return the FABRIK unit struct class, or None if not found under a
    known name in the core `unreal` module.

    FABRIK is a core Control Rig "Basic IK" unit, not a plugin -- unlike
    PBIK it should not need a struct-path lookup, but the exact exposed
    name has shifted across engine versions, so probe a short candidate
    list before falling back to a struct-path add in the caller.
    """
    for candidate in ("RigUnit_Fabrik", "RigUnit_FABRIK", "RigUnit_BasicFabrik"):
        if hasattr(unreal, candidate):
            return getattr(unreal, candidate)
    return None


def _pick_transform_lerp_struct():
    """Return a transform-lerp unit struct class for blending FK/IK targets.

    Tries a few known math-unit names across engine versions. Raises if
    none are found, since there is no safe silent fallback for a missing
    blend node -- the module cannot function without it.
    """
    for candidate in (
        "RigUnit_MathTransformLerp",
        "RigVMFunction_MathTransformLerp",
        "RigUnit_MathTransformInterpolate",
    ):
        if hasattr(unreal, candidate):
            return getattr(unreal, candidate)
    raise RuntimeError(
        "Could not find a transform-lerp unit (tried RigUnit_MathTransformLerp "
        "and known variants) in this Unreal Python API. Check the Control Rig "
        "math function library for the correct struct name and add it to the "
        "candidate list in _pick_transform_lerp_struct."
    )


def _connect_lerp_inputs(controller, model, lerp_node, a_pin, b_pin):
    """Wire the two transform inputs of a transform-lerp node.

    Different math-unit variants name their inputs differently (A/B vs
    Min/Max vs From/To) -- probe candidate pairs together so a partial
    mismatch (e.g. only 'A' exists but not 'B') doesn't leave the node
    half-wired.
    """
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
        f"Could not find a matching pair of transform-input pins on lerp node "
        f"'{lerp_node}'. Check the log above for the actual sub-pin names."
    )


def _log_node_pins(node_name, model):
    """Log every pin (and nested sub-pin) on a node, for diagnosing an
    unknown UE version's API surface -- mirrors the diagnostic logging the
    old PBIK code used when it couldn't find an expected pin.
    """
    node = model.find_node(node_name)
    if not node or not hasattr(unreal, "log"):
        return
    for pin in node.get_pins():
        unreal.log(f"[RigBuilder] '{node_name}' pin: '{pin.get_name()}' cpp_type='{pin.get_cpp_type()}'")
        for sub in pin.get_sub_pins():
            unreal.log(f"[RigBuilder]   sub-pin: '{sub.get_name()}' cpp_type='{sub.get_cpp_type()}'")


def _ensure_float_variable(rig, var_name, default_value=0.0):
    """Declare a float member variable on the rig blueprint if not already present.

    Uses the documented UE5.6 API:
        RigVMBlueprint.get_member_variables() -> Array[RigVMGraphVariableDescription]
        RigVMBlueprint.add_member_variable(name, cpp_type, is_public, is_read_only, default_value)
    """
    existing = [v for v in (rig.get_member_variables() or []) if str(v.name) == var_name]
    if not existing:
        rig.add_member_variable(var_name, "float", True, False, str(default_value))


def _create_variable_getter(controller, model, node_name, var_name, position):
    """Place a getter node for a rig variable.

    Documented signature (UE5.6):
        RigVMController.add_variable_node(
            variable_name, cpp_type, cpp_type_object,
            is_getter, default_value, position, node_name
        )
    """
    if model.find_node(node_name):
        return
    controller.add_variable_node(
        var_name, "float", None, True, "0.0", position, node_name
    )


def _create_variable_setter(controller, model, node_name, var_name, position):
    """Place a setter node for a rig variable (not wired into exec here)."""
    if model.find_node(node_name):
        return
    controller.add_variable_node(
        var_name, "float", None, False, "0.0", position, node_name
    )
