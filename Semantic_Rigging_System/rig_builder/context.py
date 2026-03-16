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