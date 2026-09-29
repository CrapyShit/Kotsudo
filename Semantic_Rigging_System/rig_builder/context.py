from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)


class RigContext:
    def __init__(self, rig, logger=None):
        self.rig = rig
        self.hierarchy = rig.hierarchy
        self.hierarchy_controller = rig.get_hierarchy_controller()
        self.graph_controller = unreal.ControlRigBlueprintLibrary.get_controller(rig)
        self.model = rig.get_model()
        self.logger = logger
        # Global end of the exec chain.  Each module advances this after it builds
        # so the next module always chains onto the true last node.
        self._exec_tail = None
        # Horizontal cursor for placing module node groups side-by-side in the graph.
        # Each module claims a column via claim_module_column() so nodes don't pile up.
        self._module_col_x = 600
        # Stores every module's build result keyed by module_name so child modules
        # can resolve their parent's attach points and control keys.
        self._module_results = {}
        # Names of modules the builder decided NOT to build (failed, skipped by
        # preflight, or skipped because their own parent was skipped). Tracked
        # separately from _module_results so warnings can distinguish "parent
        # never existed" from "parent existed but failed to build" from
        # "parent built fine but doesn't have that attach point".
        self._failed_module_names = set()
        # Control names claimed in this build: name -> identity of the Maya
        # controller (or the semantic name) that owns it.
        self._claimed_names = {}
        # Maya controller short name -> control key already built for it, so a
        # controller used by several bones/modules becomes ONE control.
        self.maya_controls = {}
        # Maya controller short name -> UE control name chosen for it.
        self._maya_name_map = {}

        # Follow spaces (see follow_space): bone -> null name, bones whose
        # update waits for their owning module, and bone -> owning module.
        self._follow_spaces = {}
        self._pending_follow = {}
        self.bone_owner = {}
        self._finished_modules = set()

        # Solve stages (see begin_stage). When the builder installs a stage
        # Sequence node, each stage has its own exec tail; otherwise a single
        # chain is used, as before.
        self._stage_tails = {}
        self._stage = None

    # ------------------------------------------------------------------
    # Parents: Maya hierarchy, driven spaces, follow spaces
    # ------------------------------------------------------------------

    def control_key_for_maya(self, maya_name):
        """Key of the UE control built for a Maya controller, or None."""
        if not maya_name:
            return None
        key = self.maya_controls.get(maya_name)
        if key is not None and self.hierarchy.contains(key):
            return key
        name = self._maya_name_map.get(maya_name)
        if name:
            key = unreal.RigElementKey(type=unreal.RigElementType.CONTROL, name=str(name))
            if self.hierarchy.contains(key):
                return key
        return None

    def world_key(self):
        from . import graph_utils
        return graph_utils.get_world_parent_key(self.hierarchy, self.hierarchy_controller)

    def resolve_control_parent(self, record, default_key):
        """Parent for the UE control of a Maya controller record.

        1. The nearest Maya parent controller (through static groups) that
           exists in the rebuilt rig -- the Maya hierarchy, exactly.
        2. A driven space (constraint/blend/driven-key group) between the
           controller and its parent: follow the bone that group tracks, so
           the control follows the solved result (e.g. a foot FK control
           blended between the IK and FK controls, the IK/FK switch).
        3. Maya parents exist but none was built: world, as in Maya's own
           top-level controls.
        Records without this data (older manifests) keep ``default_key``.
        """
        if not record or "parent_controllers" not in record:
            return default_key
        for name in record.get("parent_controllers") or []:
            key = self.control_key_for_maya(name)
            if key is not None:
                return key
        space_bone = self._acyclic_space_bone(record, record.get("parent_space_bone"))
        if space_bone:
            key = self.follow_space(space_bone)
            if key is not None:
                return key
            return default_key
        return self.world_key()

    # Records whose transform does not move any bone (a settings control only
    # carries channels), so following any bone is safe for them.
    _NON_DRIVING_ROLES = ("settings",)

    def _bone_parent(self, bone):
        from . import graph_utils

        key = graph_utils.make_key(unreal.RigElementType.BONE, bone)
        try:
            parent = self.hierarchy.get_first_parent(key)
        except Exception:
            try:
                parents = self.hierarchy.get_parents(key) or []
                parent = parents[0] if parents else None
            except Exception:
                parent = None
        if parent is None or str(parent.name) in ("", "None"):
            return None
        if getattr(parent, "type", None) != unreal.RigElementType.BONE:
            return None
        return str(parent.name)

    def _acyclic_space_bone(self, record, space_bone):
        """``space_bone`` unless following it would make a control follow a
        bone it drives itself (control -> bone -> follow space -> control, a
        feedback loop that runs away as soon as anything moves).

        Such a space is replaced by the parent of the control's driven bone:
        the nearest space outside the control's own influence (a petal
        control follows the head, a toe control the ankle).
        """
        if not space_bone:
            return space_bone
        space_bone = str(space_bone).split("|")[-1]
        driven = str(record.get("driven_bone") or "").split("|")[-1]
        if not driven or str(record.get("role") or "") in self._NON_DRIVING_ROLES:
            return space_bone
        current, depth = space_bone, 0
        while current and depth < 256:
            if current == driven:
                replacement = self._bone_parent(driven)
                print(
                    f"[RigBuilder] Controller '{record.get('name')}': parent space bone "
                    f"'{space_bone}' is driven by the control itself; following "
                    f"'{replacement or 'world'}' instead."
                )
                return replacement
            current, depth = self._bone_parent(current), depth + 1
        return space_bone

    def follow_space(self, bone):
        """A null that tracks ``bone``'s FINAL transform every evaluation.

        Created once per bone, on demand. Its update runs right after the
        module that drives the bone: immediately when that module is already
        built (or no module owns the bone), otherwise when it finishes
        (module_finished). Returns the null's key, or None.
        """
        from . import graph_utils

        bone = str(bone).split("|")[-1]
        name = self._follow_spaces.get(bone)
        if name is None:
            bone_key = graph_utils.make_key(unreal.RigElementType.BONE, bone)
            if not self.hierarchy.contains(bone_key):
                return None
            name = graph_utils.create_follow_null(
                self.hierarchy, self.hierarchy_controller, f"RB_{graph_utils.sanitize_name(bone)}_Follow",
                graph_utils.get_bone_global_transform(self.hierarchy, bone), self.world_key(),
            )
            if not name:
                return None
            self._follow_spaces[bone] = name
            owner = self.bone_owner.get(bone)
            if not owner and self.bone_owner:
                self._warn(f"Follow space on '{bone}', which no module drives: controls under it "
                           "will not move (re-export: the exporter now prefers module joints).")
            if owner and owner not in self._finished_modules:
                self._pending_follow.setdefault(owner, []).append(bone)
            else:
                self._emit_follow_update(bone)
        return unreal.RigElementKey(type=unreal.RigElementType.NULL, name=str(name))

    def _emit_follow_update(self, bone):
        from . import graph_utils

        name = self._follow_spaces[bone]
        tail = self.get_exec_tail() or graph_utils.find_forwards_solve_node_name(self.model)
        position = unreal.Vector2D(self.claim_module_column(width=700), -400)
        self.set_exec_tail(graph_utils.add_follow_update(
            self.graph_controller, self.model, name, bone, position, tail,
        ))

    def module_finished(self, module_name):
        """Called by the builder after a module is built (or failed)."""
        self._finished_modules.add(module_name)
        for bone in self._pending_follow.pop(module_name, []):
            self._emit_follow_update(bone)

    def flush_follow_spaces(self):
        """Emit every still-pending update (owner failed or never built)."""
        for owner in list(self._pending_follow):
            for bone in self._pending_follow.pop(owner):
                self._warn(f"Follow space of '{bone}' updated without its module '{owner}'.")
                self._emit_follow_update(bone)

    # ------------------------------------------------------------------
    # Solve stages
    # ------------------------------------------------------------------

    def install_stages(self, stage_pins):
        """{stage: exec pin} from the builder's Sequence node."""
        self._stage_tails = dict(stage_pins)

    def begin_stage(self, stage):
        """Route get/set_exec_tail to ``stage`` (no-op without stages)."""
        self._stage = stage if stage in self._stage_tails else None

    def control_name(self, record, fallback):
        """Control name for a Maya controller record: its Maya name when free.

        Uses the record's ``ue_control_name`` or Maya ``name``. Falls back to
        the semantic ``fallback`` when the Maya name is missing or already
        taken by a different controller (Maya allows duplicate short names
        under different groups; Control Rig does not).
        """
        from . import graph_utils

        preferred = graph_utils.sanitize_name(
            (record or {}).get("ue_control_name") or (record or {}).get("name") or ""
        ) if record else ""
        identity = (record or {}).get("dag_path") or (record or {}).get("name") or fallback
        chosen = None
        for candidate in (preferred, graph_utils.sanitize_name(fallback)):
            if not candidate or candidate == "Module":
                continue
            owner = self._claimed_names.get(candidate)
            if owner is None or owner == identity:
                self._claimed_names[candidate] = identity
                chosen = candidate
                break
        if chosen is None:
            # Both taken: make the fallback unique.
            base, index = graph_utils.sanitize_name(fallback), 2
            while f"{base}_{index}" in self._claimed_names:
                index += 1
            chosen = f"{base}_{index}"
            self._claimed_names[chosen] = identity
        for maya_name in (
            (record or {}).get("name"), (record or {}).get("ue_control_name"),
            (record or {}).get("shape_source"),
        ):
            if maya_name:
                self._maya_name_map.setdefault(maya_name, chosen)
        return chosen

    def _warn(self, message):
        if self.logger and hasattr(self.logger, "log"):
            self.logger.log(f"[RigContext] Warning: {message}")
        else:
            print(f"[RigContext] Warning: {message}")

    def mark_failed(self, module_name):
        """Record that a module was skipped or failed to build, so children
        that declare it as their parent can be warned with a precise reason
        instead of silently falling back to world space.
        """
        self._failed_module_names.add(module_name)

    def is_failed(self, module_name):
        return module_name in self._failed_module_names

    # ------------------------------------------------------------------
    # Exec chain API
    # ------------------------------------------------------------------

    def get_exec_tail(self):
        """Current last node (or stage exec pin) of the active chain, or None
        (the caller then starts from Forwards Solve)."""
        if self._stage is not None:
            return self._stage_tails[self._stage]
        return self._exec_tail

    def set_exec_tail(self, node_name):
        """Advance the active chain after appending nodes."""
        if self._stage is not None:
            self._stage_tails[self._stage] = node_name
        else:
            self._exec_tail = node_name

    def claim_module_column(self, width=900):
        """Reserve a horizontal column for one module's nodes and advance the cursor.

        Returns the x-origin the module should use for all its Vector2D positions.
        Successive modules are placed right of the previous one, keeping the graph
        readable without manual layout.
        """
        x = self._module_col_x
        self._module_col_x += width
        return x

    # ------------------------------------------------------------------
    # Module result registry
    # ------------------------------------------------------------------

    def register_result(self, module_name, result):
        """Store a module's build result so later modules can look up its attach points."""
        self._module_results[module_name] = result

    def get_attach_point(self, module_name, point_name):
        """
        Return the control name (or bone name) at a named attach point of a
        previously built module, or None if the module or point was not found.
        """
        result = self._module_results.get(module_name)
        if not result:
            return None
        return result.get("attach_points", {}).get(point_name)

    def get_parent_control_key(self, parent_module_name, parent_attach_point):
        """
        Resolve a parent module's attach point to a RigElementKey usable as a
        control hierarchy parent.

        Returns None when:
          - parent_module_name is empty / not yet built
          - the attach point name maps to a bone (not a control)
          - the control does not exist in the hierarchy yet

        Every None-returning path now warns with the specific reason, since
        callers fall back to get_world_parent_key() -- previously this was a
        silent fallback, which on a complex rig meant a mis-parented or
        mistyped module would build fine but end up floating at world
        origin with no indication anything was wrong.
        """
        if not parent_module_name:
            return None

        if parent_module_name not in self._module_results:
            reason = (
                "its build failed or was skipped"
                if self.is_failed(parent_module_name)
                else "no module with that name was found in this manifest"
            )
            self._warn(
                f"Could not parent to module '{parent_module_name}' ({reason}). "
                "Falling back to world space."
            )
            return None

        attach_point_name = parent_attach_point or "fk_tip_ctrl"

        # A parent whose bones are moved by a solver (IK/FK limb) publishes
        # "follow spaces": nulls tracking the FINAL bone transforms. Children
        # parent to those so they follow whichever mode is active, instead of
        # to a control that only reflects the FK pose.
        follow_name = (
            (self._module_results.get(parent_module_name) or {}).get("follow_spaces") or {}
        ).get(attach_point_name)
        if follow_name:
            follow_key = unreal.RigElementKey(
                type=unreal.RigElementType.NULL, name=str(follow_name)
            )
            if self.hierarchy.contains(follow_key):
                return follow_key

        ctrl_name = self.get_attach_point(parent_module_name, attach_point_name)
        if not ctrl_name:
            available = list(
                (self._module_results.get(parent_module_name) or {}).get("attach_points", {}).keys()
            )
            self._warn(
                f"Parent module '{parent_module_name}' has no attach point "
                f"'{attach_point_name}' (available: {available}). Falling back to world space."
            )
            return None

        ctrl_key = unreal.RigElementKey(
            type=unreal.RigElementType.CONTROL, name=str(ctrl_name)
        )
        if self.hierarchy.contains(ctrl_key):
            return ctrl_key

        self._warn(
            f"Parent module '{parent_module_name}' attach point '{attach_point_name}' "
            f"resolves to control '{ctrl_name}', which does not exist in the hierarchy. "
            "Falling back to world space."
        )
        return None