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
#   - FK SetTransform nodes always run first, writing the full FK pose.
#   - The IK solver runs after them, aimed at the IK effector control, and
#     its Weight IS the IK/FK blend: at 0 it leaves the FK pose untouched
#     (every FK control moves only its own bone), at 1 the chain is pure IK,
#     in between the solver blends each bone's rotation. Blending the
#     EFFECTOR target instead (an earlier design) kept the solver on at full
#     weight in FK mode, so it re-solved the FK chain toward the pole and
#     the whole limb reacted to a single FK control.
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

        parent_key = self.default_parent_key()

        x_origin = self.context.claim_module_column(width=1600)

        # ------------------------------------------------------------------
        # 1. FK controls, one per bone, parented as a control chain
        # ------------------------------------------------------------------
        fk_controls = []
        fk_get_nodes = []
        prev_fk_key = parent_key
        fk_root_parent = None

        for idx, bone_name in enumerate(self.chain):
            bone_transform = graph_utils.get_bone_global_transform(hierarchy, bone_name)
            bone_position = graph_utils.transform_to_location(bone_transform)
            chain_dir = graph_utils.get_chain_direction(hierarchy, self.chain, idx)
            shape_rot = graph_utils.get_control_shape_rotation(bone_transform, chain_dir)
            safe_bone = graph_utils.sanitize_name(bone_name)

            fk_ctrl = f"{module_prefix}_{safe_bone}_FK_CTRL"
            fk_color = unreal.LinearColor(1.0, 0.65, 0.1, 1.0)

            # The Maya FK controller of this bone: origin, exact shape and
            # custom attributes all come from its exported record.
            record = graph_utils.find_controller_record(recipe_data, bone_name, ("bone_driver",))
            fk_ctrl = self.context.control_name(record, fk_ctrl)
            fk_parent = self.context.resolve_control_parent(record, prev_fk_key)
            if idx == 0:
                fk_root_parent = fk_parent
            fk_key, driver_null = graph_utils.build_record_control(
                self.context.rig, hierarchy, hierarchy_controller, recipe_data,
                fk_parent,
                fk_ctrl, bone_name, bone_transform, record,
                graph_utils.record_color(record, fk_color),
                "Circle_Thick", (fk_scale, fk_scale, fk_scale), shape_rot,
            )
            fk_controls.append(fk_ctrl)
            prev_fk_key = fk_key

            get_node = f"{module_prefix}_{safe_bone}_GetFK"
            graph_utils.create_transform_getter(
                controller, model, get_node,
                unreal.Vector2D(x_origin, 200 + idx * 260),
                fk_ctrl, driver_null,
            )
            fk_get_nodes.append(get_node)

        # ------------------------------------------------------------------
        # 2. IK controls and blend data nodes
        # ------------------------------------------------------------------
        tip_transform = graph_utils.get_bone_global_transform(hierarchy, self.chain[-1])
        effector_pos = graph_utils.transform_to_location(tip_transform)

        ik_color = unreal.LinearColor(0.0, 0.7, 1.0, 1.0)
        effector_record = graph_utils.find_controller_record(
            recipe_data, self.chain[-1], ("ik_effector", "effector")
        )
        ik_effector_ctrl = self.context.control_name(effector_record, f"{module_prefix}_IK_CTRL")
        ik_effector_key, effector_driver = graph_utils.build_record_control(
            self.context.rig, hierarchy, hierarchy_controller, recipe_data,
            self.context.resolve_control_parent(effector_record, parent_key),
            ik_effector_ctrl, self.chain[-1], tip_transform, effector_record,
            graph_utils.record_color(effector_record, ik_color),
            "Circle_Thick", (ik_scale, ik_scale, ik_scale),
        )

        get_eff_node = f"{module_prefix}_GetIKEff"
        ik_node = f"{module_prefix}_IKSolve"

        # IK/blend nodes sit to the right of the FK section.
        n_bones = len(self.chain)
        ik_col = x_origin + 500 + n_bones * 60 + 700

        graph_utils.create_transform_getter(
            controller, model, get_eff_node,
            unreal.Vector2D(ik_col, 100),
            ik_effector_ctrl, effector_driver,
        )

        ik_eff_out = f"{get_eff_node}.Transform"

        # ------------------------------------------------------------------
        # 3. IK solver node (always TwoBoneIK -- chain length is guaranteed
        #    to be exactly 3 by validate() above)
        # ------------------------------------------------------------------
        all_nodes = [get_eff_node] + fk_get_nodes
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
            effector_pin=ik_eff_out,
        )
        all_controls.append(ik_pole_ctrl)
        all_nodes.extend([get_pole_node, ik_node])

        # The Maya switch control (if exported) drives the solver weight.
        weight_pin = f"{ik_node}.Weight"
        switch_control = self._build_switch(
            controller, model, hierarchy, hierarchy_controller, recipe_data,
            parent_key, module_prefix, weight_pin, ik_col, fk_scale,
        )
        if switch_control:
            all_controls.append(switch_control)

        # ------------------------------------------------------------------
        # 4. IKFKBlend variable  (0 = full FK, 1 = full IK) = solver weight
        #
        # default_blend comes from Maya's detected switch attribute value
        # (params.default_value in the manifest, via the DefaultBlend recipe
        # field) so the UE5 rig opens in whatever FK/IK mix the rig was left
        # in when exported, instead of always resetting to full FK.
        # ------------------------------------------------------------------
        blend_var = f"{module_prefix}_IKFKBlend"
        default_blend = float(recipe_data.get("DefaultBlend") or 0.0)
        if switch_control is None:
            # No exported switch control: fall back to a plain rig variable.
            _ensure_float_variable(self.context.rig, blend_var, default_value=default_blend)
            _bind_pin_to_variable(
                controller,
                model,
                weight_pin,
                blend_var,
                unreal.Vector2D(ik_col + 320, 500),
            )
        else:
            blend_var = switch_control

        # Root rebase (before the exec tail is read: it may add a follow-space
        # update). Maya limbs blended with pairBlends copy the IK/FK chains'
        # LOCAL values onto the bound joints, so the root rides on its parent
        # joint (a hip on the spine), not on the FK control's parent (the
        # pelvis control). The root is then written as: the FK pose relative
        # to the FK control's parent, re-applied under a null that follows the
        # root's parent bone from the same rest relation.
        rebase = None
        if graph_utils.recipe_bool(recipe_data.get("RootLocalBlend"), False):
            rebase = self._root_rebase(hierarchy, hierarchy_controller, module_prefix, fk_root_parent)

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
            # The whole FK chain is rebased, not just the root: Maya's FK chain
            # lives under the root's parent joint, so every bone rides on it.
            if rebase:
                fk_out = self._rebased_pin(controller, model, f"{module_prefix}_{idx}", fk_out, rebase,
                                           unreal.Vector2D(x_origin + 200, 100 + idx * 300)) or fk_out
            if not graph_utils.connect_pins(controller, model, fk_out, f"{set_node}.Value"):
                graph_utils.connect_pins(controller, model, fk_out, f"{set_node}.Transform")

            _chain_exec(controller, model, exec_tail, set_node)
            exec_tail = set_node
            all_nodes.append(set_node)

        _chain_exec(controller, model, exec_tail, ik_node)
        exec_tail = ik_node

        # End bone (wrist/ankle) rotation. Control Rig's two-bone node ALWAYS
        # gives the end bone the effector's rotation; Maya's IK solver never
        # does. So:
        #  * Maya orients the IK end joint (orient/parent constraint, exported
        #    as ik_end_orient): the hand/foot takes the IK control's rotation;
        #  * otherwise (measured on Murakami): the end bone keeps its rest
        #    rotation relative to its parent, as Maya's IK chain end joint does.
        # Both IK-weighted, so FK and the blend are untouched.
        follows_control = graph_utils.recipe_bool(recipe_data.get("IKEndOrient"), False)
        tip_node = self._build_tip_rotation(
            controller, model, hierarchy, hierarchy_controller, module_prefix,
            ik_effector_key, tip_transform, ik_col, weight_pin,
            blend_var if switch_control is None else None,
            follow_control=follows_control,
        )
        if tip_node:
            _chain_exec(controller, model, exec_tail, tip_node)
            exec_tail = tip_node
            all_nodes.append(tip_node)

        # Show only the controls of the active mode (IK controls hidden in
        # full FK and vice versa); both sets while blending.
        if switch_control and graph_utils.recipe_bool(recipe_data.get("SwitchDrivesVisibility"), True):
            exec_tail = self._build_switch_visibility(
                controller, model, module_prefix, exec_tail, ik_col,
                fk_controls, [ik_effector_ctrl, ik_pole_ctrl],
            )
        # Children of this limb (toes, fingers...) follow its solved bones
        # through follow spaces the context creates on demand.
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
        if switch_control:
            attach_pts["ik_fk_switch"] = switch_control

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
    # Control visibility from the switch
    # ------------------------------------------------------------------

    def _root_rebase(self, hierarchy, hierarchy_controller, prefix, fk_parent_key):
        """(fk parent key, rebase null) or None: a null under the follow space
        of the root bone's parent, placed at the FK control parent's rest."""
        if fk_parent_key is None or not graph_utils.is_valid_key(hierarchy, fk_parent_key):
            return None
        root_key = graph_utils.make_key(unreal.RigElementType.BONE, self.chain[0])
        try:
            parent_bone = hierarchy.get_first_parent(root_key)
        except Exception:
            parent_bone = None
        if parent_bone is None or parent_bone.type != unreal.RigElementType.BONE:
            return None
        follow = self.context.follow_space(str(parent_bone.name))
        if follow is None:
            return None
        null = graph_utils.create_follow_null(
            hierarchy, hierarchy_controller, f"{prefix}_RootRebase",
            hierarchy.get_global_transform(fk_parent_key, True), follow,
        )
        if not null:
            return None
        _log_info(f"{self.name}: root '{self.chain[0]}' rides on '{parent_bone.name}' "
                  "(Maya blends this limb's chains locally).")
        return fk_parent_key, null

    def _rebased_pin(self, controller, model, prefix, global_pin, rebase, position):
        """Pin: global_pin made relative to the FK parent, then absolute under the rebase null."""
        fk_parent_key, null = rebase
        relative = _pick_unit(("RigVMFunction_MathTransformMakeRelative", "RigUnit_MathTransformMakeRelative"))
        absolute = _pick_unit(("RigVMFunction_MathTransformMakeAbsolute", "RigUnit_MathTransformMakeAbsolute"))
        if relative is None or absolute is None:
            _log_warning(f"{self.name}: Make Relative/Absolute units unavailable; root not rebased.")
            return None
        parent_get, null_get = f"{prefix}_FKParent", f"{prefix}_RebaseGet"
        for node, item_type, name, y in ((parent_get, fk_parent_key.type, str(fk_parent_key.name), 0),
                                         (null_get, unreal.RigElementType.NULL, null, 140)):
            graph_utils.create_unit_node(controller, model, node, unreal.RigUnit_GetTransform,
                                         unreal.Vector2D(position.x, position.y + y))
            type_name = {unreal.RigElementType.CONTROL: "Control", unreal.RigElementType.NULL: "Null",
                         unreal.RigElementType.BONE: "Bone"}.get(item_type, "Control")
            graph_utils.set_key_pin(controller, model, node, ["Item"], type_name, name)
            graph_utils.set_any_pin(controller, model, node, ["Space"], "GlobalSpace")
            graph_utils.set_any_pin(controller, model, node, ["bInitial", "Initial"], "False")
        rel, absn = f"{prefix}_Relative", f"{prefix}_Rebased"
        graph_utils.create_unit_node(controller, model, rel, relative, unreal.Vector2D(position.x + 300, position.y))
        graph_utils.create_unit_node(controller, model, absn, absolute, unreal.Vector2D(position.x + 550, position.y))
        ok = (graph_utils.connect_pins(controller, model, global_pin, f"{rel}.Global")
              and graph_utils.connect_pins(controller, model, f"{parent_get}.Transform", f"{rel}.Parent")
              and graph_utils.connect_pins(controller, model, f"{rel}.Local", f"{absn}.Local")
              and graph_utils.connect_pins(controller, model, f"{null_get}.Transform", f"{absn}.Parent"))
        if not ok:
            _log_node_pins(rel, model)
            _log_warning(f"{self.name}: root rebase could not be wired; root kept in world space.")
            return None
        return f"{absn}.Global"

    def _build_tip_rotation(self, controller, model, hierarchy, hierarchy_controller, prefix,
                            effector_key, tip_transform, ik_col, weight_pin, blend_var,
                            follow_control=True):
        """SetRotation on the chain's end bone after the IK solve, IK-weighted.

        follow_control=True: the IK control's rotation, read from a null under
        the control that sits on the end bone at rest (the bone keeps its own
        axes; only the control's motion applies). False: the bone's REST
        rotation relative to its parent (Maya's plain IK end joint).
        Returns the node name, or None when the engine lacks the units.
        """
        set_rotation = getattr(unreal, "RigUnit_SetRotation", None)
        if set_rotation is None or (follow_control and effector_key is None):
            _log_warning(f"{self.name}: RigUnit_SetRotation unavailable; the IK end bone keeps "
                         "the solver's rotation.")
            return None
        get_node = f"{prefix}_GetIKTipAlign" if follow_control else f"{prefix}_GetIKTipRest"
        if follow_control:
            align_null = graph_utils.create_offset_driver(
                hierarchy, hierarchy_controller, effector_key, f"{prefix}_IKTipAlign", tip_transform
            )
            if not align_null:
                return None
            graph_utils.create_transform_getter(
                controller, model, get_node, unreal.Vector2D(ik_col + 700, 520), None, align_null
            )
        else:
            graph_utils.create_unit_node(controller, model, get_node, unreal.RigUnit_GetTransform,
                                         unreal.Vector2D(ik_col + 700, 520))
            graph_utils.set_key_pin(controller, model, get_node, ["Item"], "Bone", self.chain[-1])
            graph_utils.set_any_pin(controller, model, get_node, ["Space"], "LocalSpace")
            graph_utils.set_any_pin(controller, model, get_node, ["bInitial", "Initial"], "True")
        node = f"{prefix}_IKTipRotation"
        graph_utils.create_unit_node(controller, model, node, set_rotation, unreal.Vector2D(ik_col + 1000, 520))
        graph_utils.set_key_pin(controller, model, node, ["Item"], "Bone", self.chain[-1])
        graph_utils.set_any_pin(controller, model, node, ["Space"],
                                "GlobalSpace" if follow_control else "LocalSpace")
        graph_utils.set_any_pin(controller, model, node, ["bInitial", "Initial"], "False")
        graph_utils.set_any_pin(controller, model, node, ["bPropagateToChildren", "PropagateToChildren"], "True")
        # The quaternion input is "Value" on UE5's Set Rotation ("Rotation" on
        # older builds). An unconnected pin would silently write identity.
        if not any(
            graph_utils.connect_pins(controller, model, f"{get_node}.Transform.Rotation", f"{node}.{pin}")
            for pin in ("Value", "Rotation")
            if graph_utils.pin_exists(model, f"{node}.{pin}")
        ):
            _log_node_pins(node, model)
            _log_warning(f"{self.name}: could not wire the IK end-bone rotation; removed.")
            try:
                controller.remove_node_by_name(node)
            except Exception:
                pass
            return None
        _log_info(f"{self.name}: in IK, '{self.chain[-1]}' "
                  + ("follows the IK control's rotation." if follow_control
                     else "keeps its rest rotation relative to its parent (as Maya's IK end joint)."))
        # Same weight as the solver: the switch source, or the blend variable.
        source = getattr(self, "_ik_weight_source", None)
        if source:
            graph_utils.connect_pins(controller, model, source, f"{node}.Weight")
        elif blend_var:
            _bind_pin_to_variable(controller, model, f"{node}.Weight", blend_var,
                                  unreal.Vector2D(ik_col + 700, 700))
        else:
            graph_utils.set_any_pin(controller, model, node, ["Weight"],
                                    str(float(self.read_recipe().get("DefaultBlend") or 0.0)))
        return node

    def _build_switch_visibility(self, controller, model, prefix, exec_tail, ik_col,
                                 fk_controls, ik_controls):
        """Set Control Visibility on FK and IK controls from the switch value.

        The switch channel holds the Maya attribute value (IK/FK polarity
        taken from the export). FK controls are shown while the FK weight is
        above zero, IK controls while the IK weight is above zero, so both
        sets are visible mid-blend. Skipped with a warning when this engine
        lacks the units.
        """
        out_pin = getattr(self, "_switch_out_pin", None)
        visibility_unit = getattr(unreal, "RigUnit_SetControlVisibility", None)
        greater = _pick_unit(("RigVMFunction_MathFloatGreater", "RigUnit_MathFloatGreater"))
        less = _pick_unit(("RigVMFunction_MathFloatLess", "RigUnit_MathFloatLess"))
        if not (out_pin and visibility_unit and greater and less):
            _log_warning(f"{self.name}: switch-driven visibility unavailable in this engine build; skipped.")
            return exec_tail

        ik_value = float(getattr(self, "_switch_ik_value", 1.0))
        fk_value = float(getattr(self, "_switch_fk_value", 0.0))
        epsilon = 0.001 * max(abs(ik_value - fk_value), 1e-6)
        # "IK weight > 0" means the value has left fk_value toward ik_value.
        tests = {
            "IK": (greater if ik_value > fk_value else less, fk_value + epsilon if ik_value > fk_value else fk_value - epsilon),
            "FK": (less if ik_value > fk_value else greater, ik_value - epsilon if ik_value > fk_value else ik_value + epsilon),
        }
        compare_pins = {}
        for mode, (unit, threshold) in tests.items():
            node = f"{prefix}_{mode}Visible"
            graph_utils.create_unit_node(controller, model, node, unit, unreal.Vector2D(ik_col + 700, 700 + len(compare_pins) * 160))
            graph_utils.connect_pins(controller, model, out_pin, f"{node}.A")
            graph_utils.set_pin_default(controller, model, f"{node}.B", str(threshold))
            compare_pins[mode] = f"{node}.Result"

        for index, (mode, names) in enumerate((("FK", fk_controls), ("IK", ik_controls))):
            for offset, control_name in enumerate(n for n in names if n):
                node = f"{prefix}_{graph_utils.sanitize_name(control_name)}_Vis"
                graph_utils.create_unit_node(
                    controller, model, node, visibility_unit,
                    unreal.Vector2D(ik_col + 1000, 700 + (index * 4 + offset) * 160),
                )
                graph_utils.set_key_pin(controller, model, node, ["Item"], "Control", control_name)
                for visible_pin in ("bVisible", "Visible"):
                    if graph_utils.connect_pins(controller, model, compare_pins[mode], f"{node}.{visible_pin}"):
                        break
                graph_utils.connect_exec(controller, model, exec_tail, node)
                exec_tail = node
        return exec_tail

    # ------------------------------------------------------------------
    # IK/FK switch control
    # ------------------------------------------------------------------

    def _build_switch(
        self, controller, model, hierarchy, hierarchy_controller, recipe_data,
        parent_key, module_prefix, weight_pin, ik_col, scale,
    ):
        """Recreate the Maya IK/FK switch as a control that drives the blend.

        The Maya controller (position, shape) becomes a Control Rig control
        carrying one FLOAT slider per exported attribute; the IK/FK attribute's
        slider drives ``weight_pin`` (the IK solver weight). Returns the
        control name, or None when no switch was exported/buildable (the
        caller then falls back to a rig variable).

        Polarity: the weight is the IK weight. With IK at attribute value 1 the
        slider is wired straight in; with IK at 0 (Maya enum "IK:FK") it goes
        through 1 - value, so the animator's numbers keep the meaning they had
        in Maya. A range other than 0..1 is normalised to an IK-weight slider.
        """
        switch = recipe_data.get("Switch")
        if not isinstance(switch, dict):
            return None
        record = switch.get("control") or {}
        attribute = switch.get("attribute")
        info = dict(switch.get("attribute_info") or {})
        if not record or not attribute or not info:
            return None

        try:
            ik_value = float(switch.get("ik_value", 1.0))
            fk_value = float(switch.get("fk_value", 0.0))
            invert_inputs = False
            if {round(ik_value, 6), round(fk_value, 6)} == {0.0, 1.0}:
                invert_inputs = ik_value == 0.0
            else:
                # Normalise to a 0..1 "IK weight" slider.
                info["min"], info["max"] = 0.0, 1.0
                info["value"] = float(switch.get("default_ik_weight", 0.0))
                _log_warning(
                    f"Switch '{attribute}' of '{self.name}' uses values IK={ik_value}, "
                    f"FK={fk_value}; exposing it as a 0..1 IK-weight slider."
                )

            # The switch is the Maya controller itself (L_Leg_IKFK_Switch):
            # same name, place, orientation, shape and locked channels. Its
            # attributes become animation channels on it -- select the control
            # and IK_FK is in the Details panel / Anim Outliner / Sequencer,
            # exactly like the attribute in Maya's channel box.
            anchor = record.get("anchor_bone") or self.chain[0]
            placement = graph_utils.record_transform(
                hierarchy, record, anchor, label=f"{self.name} switch"
            )
            position = graph_utils.transform_to_location(placement)
            host_name = self.context.control_name(record, f"{module_prefix}_Switch_CTRL")
            color = graph_utils.record_color(record, unreal.LinearColor(1.0, 0.9, 0.2, 1.0))
            shape_name, shape_rotation, shape_scale = graph_utils.control_shapes.resolve_control_shape(
                self.context.rig, recipe_data, record,
                graph_utils.get_transform_rotation(placement),
                "Circle_Thick", (scale, scale, scale),
            )
            # Maya: the switch group is parent-constrained between the IK and
            # FK controls by the switch itself, i.e. it follows the blended
            # limb -- resolve_control_parent maps that to the follow space of
            # the bone the group tracks.
            host_parent = self.context.resolve_control_parent(record, parent_key)
            host_key = graph_utils.create_control(
                hierarchy, hierarchy_controller, host_parent, host_name, position, color,
                shape_scale, shape_name=shape_name, shape_rotation=shape_rotation,
                global_transform=placement,
                locked_channels=record.get("locked_channels"),
            )

            # The driving attribute first; other settings of the same Maya
            # controller follow.
            infos = [info] + [
                item for item in (record.get("attributes") or [])
                if item.get("name") != attribute
            ]
            created = graph_utils.attach_record_attributes(
                hierarchy, hierarchy_controller, host_key, record, host_name,
                position, color, infos=infos,
            )
            kind, key_name = created.get(attribute, (None, None))
            if not key_name:
                return None

            if kind == "channel":
                out_pin = graph_utils.create_channel_getter(
                    controller, model, f"{module_prefix}_GetSwitch", host_name, attribute,
                    key_name, unreal.Vector2D(ik_col + 320, 500),
                )
            else:
                out_pin = graph_utils.create_float_control_getter(
                    controller, model, f"{module_prefix}_GetSwitch", key_name,
                    unreal.Vector2D(ik_col + 320, 500),
                )
            control_name = host_name
            weight_source = out_pin
            if out_pin and invert_inputs:
                weight_source = _one_minus(
                    controller, model, f"{module_prefix}_SwitchToIKWeight", out_pin,
                    unreal.Vector2D(ik_col + 520, 500),
                )
            self._ik_weight_source = weight_source
            if not weight_source or not graph_utils.connect_pins(
                controller, model, weight_source, weight_pin
            ):
                _log_warning(
                    f"Switch control '{control_name}' could not be wired to '{weight_pin}'; "
                    "using a rig variable instead."
                )
                return None
            _log_info(
                f"IK/FK switch: control '{control_name}', {kind} '{attribute}' drives "
                f"'{weight_pin}' (IK={ik_value}, FK={fk_value}"
                f"{', through 1 - value' if invert_inputs else ''})."
            )
            self._switch_out_pin = out_pin
            # The channel is 0..1 with IK at 0 when the inputs are swapped
            # (Maya "IK:FK" enum), IK at 1 otherwise (incl. normalised sliders).
            self._switch_ik_value = 0.0 if invert_inputs else 1.0
            self._switch_fk_value = 1.0 - self._switch_ik_value
            return control_name
        except Exception as exc:
            _log_warning(f"Could not build the IK/FK switch control for '{self.name}': {exc}")
            return None

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
        effector_pin,
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

        # Use the Maya pole-vector controller's own position when the export
        # captured one (any offset from the mid bone counts, so no minimum).
        pole_record = graph_utils.find_controller_record(
            recipe_data, self.chain[1], ("pole_vector", "pv")
        )
        recorded_pole = graph_utils.controller_origin_position(
            hierarchy, pole_record, self.chain[1], min_offset=0.0, label=ik_pole_ctrl
        )
        if recorded_pole is not None:
            pole_pos = recorded_pole

        # Sphere sized like the Maya pole controller, under its Maya name.
        ik_pole_ctrl, _pole_key = graph_utils.build_pole_control(
            self.context, parent_key, ik_pole_ctrl, pole_pos, pole_record,
            graph_utils.record_color(pole_record, unreal.LinearColor(0.0, 0.35, 1.0, 1.0)),
            (pv_scale, pv_scale, pv_scale),
        )

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

        if not _connect_first_available(
            controller,
            model,
            effector_pin,
            [f"{ik_node}.Effector", f"{ik_node}.EffectorTransform"],
        ):
            _log_node_pins(ik_node, model)
            raise RuntimeError(
                f"Could not connect the IK effector control to the TwoBoneIK effector pin "
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

        # Solver axes come from the imported skeleton (which local axis of the
        # upper bone runs to the mid bone, and which points at the pole), not
        # from a hard-coded X/Y: a limb whose joints run along another axis
        # would otherwise be twisted the moment the solver writes its bones.
        # Recipe values are only a fallback for degenerate (collinear) chains.
        fallback_primary = graph_utils.recipe_vector(
            recipe_data.get("PrimaryAxis"), unreal.Vector(1.0, 0.0, 0.0)
        )
        fallback_secondary = graph_utils.recipe_vector(
            recipe_data.get("SecondaryAxis"), unreal.Vector(0.0, 1.0, 0.0)
        )
        primary_axis, secondary_axis = graph_utils.derive_two_bone_axes(
            hierarchy,
            self.chain,
            pole_pos,
            fallback_primary=fallback_primary,
            fallback_secondary=fallback_secondary,
        )
        graph_utils.check_chain_axes(
            self.name, recipe_data.get("ChainAxes"),
            measured_aim=graph_utils.vector_axis_label(primary_axis),
            measured_up=graph_utils.measure_chain_bend_label(hierarchy, self.chain),
        )
        pole_kind = str(recipe_data.get("PoleVectorKind") or "Location")

        _set_vector_pin(controller, model, f"{ik_node}.PrimaryAxis", primary_axis)
        _set_vector_pin(controller, model, f"{ik_node}.SecondaryAxis", secondary_axis)
        graph_utils.set_any_pin(controller, model, ik_node, ["SecondaryAxisWeight"], "1.0")
        graph_utils.set_any_pin(controller, model, ik_node, ["PoleVectorKind"], pole_kind)
        graph_utils.set_any_pin(controller, model, ik_node, ["PoleVectorSpace"], "None")
        # Solver weight = IK weight; the switch/variable drives it, this is the
        # default when neither can be wired.
        graph_utils.set_any_pin(
            controller, model, ik_node, ["Weight"], str(float(recipe_data.get("DefaultBlend") or 0.0))
        )
        graph_utils.set_any_pin(controller, model, ik_node, ["PropagateToChildren"], "true")
        # Rest bone lengths, explicitly. With 0 the node measures the CURRENT
        # pose, and any small offset of the input pose changes the lengths --
        # on a nearly straight limb a millimetre of length moves the knee by
        # centimetres. Maya's IK chain keeps its joint lengths.
        length_a = graph_utils.vector_length(graph_utils.vector_sub(
            graph_utils.get_bone_global_position(hierarchy, self.chain[1]),
            graph_utils.get_bone_global_position(hierarchy, self.chain[0])))
        length_b = graph_utils.vector_length(graph_utils.vector_sub(
            graph_utils.get_bone_global_position(hierarchy, self.chain[2]),
            graph_utils.get_bone_global_position(hierarchy, self.chain[1])))
        graph_utils.set_any_pin(controller, model, ik_node, ["BoneALength"], str(round(length_a, 6)))
        graph_utils.set_any_pin(controller, model, ik_node, ["BoneBLength"], str(round(length_b, 6)))

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
            "ControllerRecords": None,
            "ShapeTable": None,
            "Switch": None,
            "SwitchDrivesVisibility": True,
            "IKEndOrient": False,
            "RootLocalBlend": False,
            "ChainAxes": None,
        }
        fallback_names = {
            "ControllerRecords": ["controller_records", "controllerrecords"],
            "ShapeTable": ["shape_table", "shapetable"],
            "Switch": ["switch"],
            "SwitchDrivesVisibility": ["switch_drives_visibility"],
            "IKEndOrient": ["ik_end_orient"],
            "RootLocalBlend": ["root_local_blend"],
            "ChainAxes": ["chain_axes"],
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
    """Connect execution from from_node (node or exec pin) to to_node."""
    graph_utils.connect_exec(controller, model, from_node, to_node)


def _pick_unit(candidates):
    for name in candidates:
        unit = getattr(unreal, name, None)
        if unit is not None:
            return unit
    return None


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


def _one_minus(controller, model, node_name, source_pin, position):
    """Pin carrying 1 - source (a float), or None when no subtract unit exists."""
    unit = _pick_unit(("RigVMFunction_MathFloatSub", "RigUnit_MathFloatSub"))
    if unit is None:
        return None
    graph_utils.create_unit_node(controller, model, node_name, unit, position)
    graph_utils.set_pin_default(controller, model, f"{node_name}.A", "1.0")
    if not graph_utils.connect_pins(controller, model, source_pin, f"{node_name}.B"):
        return None
    return f"{node_name}.Result"


def _bind_pin_to_variable(controller, model, pin, variable, getter_pos):
    """Drive a float pin from a rig variable."""
    try:
        controller.bind_pin_to_variable(pin, variable)
        return
    except Exception:
        pass
    getter = f"{pin.split('.')[0]}_Get{variable}"
    _create_variable_getter(controller, model, getter, variable, getter_pos)
    for out_pin in (variable, "Value", "ReturnValue"):
        if graph_utils.connect_pins(controller, model, f"{getter}.{out_pin}", pin):
            return
    _log_node_pins(getter, model)
    raise RuntimeError(f"Could not bind or connect variable '{variable}' to '{pin}'.")


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