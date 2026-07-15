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
        """Return the current last node in the exec chain, or None (caller uses ForwardsSolve)."""
        return self._exec_tail

    def set_exec_tail(self, node_name):
        """Advance the exec chain tail after a module finishes building."""
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