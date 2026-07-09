from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)


class RigContext:
    def __init__(self, rig):
        self.rig = rig
        self.hierarchy = rig.hierarchy
        self.hierarchy_controller = rig.get_hierarchy_controller()
        self.graph_controller = unreal.ControlRigBlueprintLibrary.get_controller(rig)
        self.model = rig.get_model()
        # Global end of the exec chain.  Each module advances this after it builds
        # so the next module always chains onto the true last node.
        self._exec_tail = None
        # Horizontal cursor for placing module node groups side-by-side in the graph.
        # Each module claims a column via claim_module_column() so nodes don't pile up.
        self._module_col_x = 600
        # Stores every module's build result keyed by module_name so child modules
        # can resolve their parent's attach points and control keys.
        self._module_results = {}

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

        Callers should fall back to get_world_parent_key() when this returns None.
        """
        if not parent_module_name:
            return None
        ctrl_name = self.get_attach_point(
            parent_module_name, parent_attach_point or "fk_tip_ctrl"
        )
        if not ctrl_name:
            return None
        ctrl_key = unreal.RigElementKey(
            type=unreal.RigElementType.CONTROL, name=str(ctrl_name)
        )
        if self.hierarchy.contains(ctrl_key):
            return ctrl_key
        return None