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
#       v                              SetTransform (bone)
#   BlendFK ─────────────────────────►     Value  ◄──── BlendIK
#                                              ^
#   GetIK (GetControlTransform)           MathFloatLerp.Result
#       |                                 /            \
#       v                         Weight(0=FK)   Weight(1=IK)
#   (feeds BlendIK)                       \            /
#                                      IKFKBlend variable
#
# For chains of any length the IK side uses a RigUnit_FullbodyIK (FBIK) node
# driven by an effector control + pole vector, exactly like IKModule does.
# The FK side creates one FK control per bone, exactly like FKModule does.
#
# The IKFKBlend variable is a float (0 = full FK, 1 = full IK) added as a
# rig variable so it appears in the CR detail panel and can be animated.
# ---------------------------------------------------------------------------


class IKFKModule(RigModule):
    """IK/FK switch module for any-length joint chain (2+ bones).

    Builds both an FK chain (one control per bone) and an IK setup from the
    same joint chain, then blends between them via FBIK ``PositionAlpha`` /
    ``RotationAlpha`` pins bound to the ``IKFKBlend`` variable.

    Uses the Full Body IK (FBIK) solver (``RigUnit_FullbodyIK``) for all
    chain lengths. Requires the **FullBodyIK** plugin to be enabled in the
    project.

    The blend is driven by a ``SetTransform`` node on the tip bone whose
    ``Weight`` pin is bound to the ``IKFKBlend`` variable (0 = FK, 1 = IK).

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
        fk_set_nodes = []
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
        # 2. IK controls (effector only) + Full Body IK node
        # ------------------------------------------------------------------
        # FBIK blend design — avoids all array-element sub-pin link issues:
        #
        #   a) FK SetTransforms write every bone to the FK ctrl pose (weight=1).
        #   b) A single "IK target" SetTransform writes the IK ctrl position
        #      onto chain[-1] with Weight = IKFKBlend variable.
        #        blend=0 → no change (chain[-1] stays at FK)
        #        blend=1 → chain[-1] = IK ctrl position
        #   c) FBIK (PositionAlpha=1 always) reads chain[-1]'s current position
        #      as the effector target and solves the full chain toward it.
        #
        # At blend=0: target == FK tip → FBIK preserves the FK pose exactly.
        # At blend=1: target == IK ctrl → FBIK solves entire chain toward IK.

        effector_pos = graph_utils.get_bone_global_position(hierarchy, self.chain[-1])

        ik_effector_ctrl = f"{module_prefix}_IK_CTRL"
        graph_utils.create_control(
            hierarchy, hierarchy_controller,
            parent_key, ik_effector_ctrl, effector_pos,
            unreal.LinearColor(0.0, 0.7, 1.0, 1.0),
            (ik_scale, ik_scale, ik_scale),
        )

        get_eff_node    = f"{module_prefix}_GetIKEff"
        ik_target_node  = f"{module_prefix}_SetIKTarget"
        ik_node         = f"{module_prefix}_IKSolve"

        # IK nodes sit to the RIGHT of all FK columns.
        n_bones = len(self.chain)
        ik_col  = x_origin + 500 + n_bones * 60 + 700

        # GetControlTransform for the IK effector control.
        graph_utils.create_unit_node(
            controller, model, get_eff_node,
            unreal.RigUnit_GetControlTransform,
            unreal.Vector2D(ik_col, 100),
        )
        graph_utils.set_pin_default(controller, model, f"{get_eff_node}.Control", ik_effector_ctrl)
        graph_utils.set_pin_default(controller, model, f"{get_eff_node}.Space", "GlobalSpace")

        # SetTransform for the IK target: writes IK ctrl position onto the tip
        # bone with Weight = IKFKBlend.  This is the blend mechanism — no
        # array-element sub-pin linking required.
        graph_utils.create_unit_node(
            controller, model, ik_target_node,
            unreal.RigUnit_SetTransform,
            unreal.Vector2D(ik_col + 320, 100),
        )
        graph_utils.set_key_pin(controller, model, ik_target_node,
            ["Item", "Bone", "Child"], "Bone", self.chain[-1])
        graph_utils.set_any_pin(controller, model, ik_target_node, ["Space"], "GlobalSpace")
        graph_utils.set_any_pin(controller, model, ik_target_node, ["Initial"], "False")
        graph_utils.set_any_pin(controller, model, ik_target_node,
            ["bPropagateToChildren", "PropagateToChildren"], "False")
        # Weight is set below when the variable is declared.

        # Wire IK ctrl transform → ik_target_node.Value / .Transform
        if not graph_utils.connect_pins(controller, model,
                                        f"{get_eff_node}.Transform", f"{ik_target_node}.Value"):
            graph_utils.connect_pins(controller, model,
                                     f"{get_eff_node}.Transform", f"{ik_target_node}.Transform")

        # PBIK node — /Script/PBIK.RigUnit_PBIK is the current non-deprecated
        # Full Body IK solver in UE5.6.  Must use add_unit_node_from_struct_path
        # because the struct lives in the PBIK plugin module, not unreal.*.
        existing = model.find_node(ik_node)
        if not existing:
            controller.add_unit_node_from_struct_path(
                '/Script/PBIK.RigUnit_PBIK',
                'Execute',
                unreal.Vector2D(ik_col + 700, 100),
                ik_node,
            )

        # Root — PBIK uses a plain bone name string, not a FRigElementKey struct.
        controller.set_pin_default_value(f"{ik_node}.Root", self.chain[0])

        # One effector: the tip bone.
        # The exact pin name for the bone field varies across PBIK versions.
        # Probe all known candidates; if none match, log the actual sub-pins
        # so the name can be hardcoded on the next run.
        controller.insert_array_pin(f"{ik_node}.Effectors", -1, "")

        _bone_set = False
        for _field in ("Bone", "BoneName", "Item", "EffectorBone", "TargetBone", "EffectorItem"):
            # Try as FRigElementKey struct (has .Type / .Name sub-pins)
            try:
                controller.set_pin_default_value(
                    f"{ik_node}.Effectors.0.{_field}.Type", "Bone")
                controller.set_pin_default_value(
                    f"{ik_node}.Effectors.0.{_field}.Name", self.chain[-1])
                _bone_set = True
                break
            except Exception:
                pass
            # Try as plain FName / string pin
            try:
                controller.set_pin_default_value(
                    f"{ik_node}.Effectors.0.{_field}", self.chain[-1])
                _bone_set = True
                break
            except Exception:
                pass

        if not _bone_set:
            # Log the actual sub-pin names so we can hardcode the right one.
            _pbik_node = model.find_node(ik_node)
            if _pbik_node:
                for _p in _pbik_node.get_pins():
                    if _p.get_name() == "Effectors":
                        for _elem in _p.get_sub_pins():
                            for _sub in _elem.get_sub_pins():
                                unreal.log(
                                    f"[RigBuilder] PBIK Effectors.0 pin: "
                                    f"'{_sub.get_name()}' cpp_type='{_sub.get_cpp_type()}'"
                                )
            raise RuntimeError(
                "Could not find bone field in PBIK Effectors.0. "
                "Check the log above for the actual sub-pin names."
            )

        controller.set_pin_default_value(f"{ik_node}.Effectors.0.PositionAlpha", "1.0")
        controller.set_pin_default_value(f"{ik_node}.Effectors.0.RotationAlpha", "1.0")

        # ------------------------------------------------------------------
        # 3. IKFKBlend variable  (0 = full FK, 1 = full IK)
        # ------------------------------------------------------------------
        blend_var = f"{module_prefix}_IKFKBlend"
        _ensure_float_variable(self.context.rig, blend_var, default_value=0.0)

        # Bind the IK target SetTransform Weight directly to the blend variable.
        try:
            controller.bind_pin_to_variable(f"{ik_target_node}.Weight", blend_var)
        except Exception:
            get_blend_node = f"{module_prefix}_GetBlend"
            _create_variable_getter(controller, model, get_blend_node, blend_var,
                                    unreal.Vector2D(ik_col + 320, 500))
            for _out_pin in (blend_var, "Value", "ReturnValue"):
                try:
                    controller.add_link(f"{get_blend_node}.{_out_pin}",
                                        f"{ik_target_node}.Weight")
                    break
                except Exception:
                    pass

        # ------------------------------------------------------------------
        # 4. Execution chain: FK SetTransforms → IK target set → PBIK solver.
        #
        #   a) Per-bone FK SetTransform(weight=1.0) writes the FK ctrl pose.
        #   b) ik_target_node(chain[-1], weight=blend) overlays the IK position.
        #   c) PBIK(PositionAlpha=1) solves the full chain toward the tip bone.
        # ------------------------------------------------------------------
        all_nodes = [get_eff_node, ik_target_node, ik_node] + fk_get_nodes

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

        # IK phase: wire ik_target_node → FBIK into the exec chain.
        _chain_exec(controller, model, exec_tail, ik_target_node)
        exec_tail = ik_target_node
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



