import importlib
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def prioritize_project_root():
    normalized_root = os.path.normcase(os.path.normpath(PROJECT_ROOT))
    preserved_paths = []
    for path_entry in sys.path:
        if not path_entry:
            preserved_paths.append(path_entry)
            continue

        normalized_entry = os.path.normcase(os.path.normpath(path_entry))
        if normalized_entry != normalized_root:
            preserved_paths.append(path_entry)

    sys.path[:] = [PROJECT_ROOT] + preserved_paths


def purge_rig_builder_modules():
    stale_modules = [
        module_name
        for module_name in list(sys.modules)
        if module_name == "rig_builder" or module_name.startswith("rig_builder.")
    ]
    for module_name in stale_modules:
        del sys.modules[module_name]


def purge_import_finder_caches():
    normalized_root = os.path.normcase(os.path.normpath(PROJECT_ROOT))
    stale_finders = [
        cache_path
        for cache_path in list(sys.path_importer_cache)
        if isinstance(cache_path, str)
        and os.path.normcase(os.path.normpath(cache_path)).startswith(normalized_root)
    ]
    for cache_path in stale_finders:
        del sys.path_importer_cache[cache_path]


def prepare_local_imports():
    prioritize_project_root()
    purge_rig_builder_modules()
    purge_import_finder_caches()
    importlib.invalidate_caches()


prepare_local_imports()

import unreal
rig_builder_context = importlib.import_module("rig_builder.context")
rig_builder_graph_utils = importlib.import_module("rig_builder.graph_utils")
rig_builder_logger = importlib.import_module("rig_builder.logger")
rig_builder_metadata_reader = importlib.import_module("rig_builder.metadata_reader")
rig_builder_rig_module = importlib.import_module("rig_builder.modules.rig_module")
rig_builder_fk_module = importlib.import_module("rig_builder.modules.fk_module")
rig_builder_ik_module = importlib.import_module("rig_builder.modules.ik_module")
rig_builder_ikfk_module = importlib.import_module("rig_builder.modules.ikfk_module")
rig_builder_spline_ik_module = importlib.import_module("rig_builder.modules.spline_ik_module")
rig_builder_builder = importlib.import_module("rig_builder.builder")


def reload_rig_builder_modules():
    importlib.invalidate_caches()
    importlib.reload(rig_builder_context)
    importlib.reload(rig_builder_graph_utils)
    importlib.reload(rig_builder_logger)
    importlib.reload(rig_builder_metadata_reader)
    importlib.reload(rig_builder_rig_module)
    importlib.reload(rig_builder_fk_module)
    importlib.reload(rig_builder_ik_module)
    importlib.reload(rig_builder_ikfk_module)
    importlib.reload(rig_builder_spline_ik_module)
    importlib.reload(rig_builder_builder)


reload_rig_builder_modules()
RigBuilder = rig_builder_builder.RigBuilder

SOURCE_ASSET_PATH = None  # None = auto-derive skeleton from the open Control Rig's preview mesh.
                          # Set to a path string to override, e.g.:
                          # "/Game/.../MyCharacter_Skeleton.MyCharacter_Skeleton"
CONTROL_RIG_PATH = None
RECIPE_ASSET_PATHS = {
    "IKLimb": "/Game/KotsudoProject/Python_Tests/MetadataTags_Tests/20260309/DA_IKLimb.DA_IKLimb",
}


def load_control_rig_blueprint(rig_path=None):
    unreal.load_module("ControlRigDeveloper")

    if rig_path:
        rig = unreal.EditorAssetLibrary.load_asset(rig_path)
        if not rig:
            raise RuntimeError(f"Invalid Control Rig path: {rig_path}")
        return rig

    rigs = unreal.ControlRigBlueprint.get_currently_open_rig_blueprints()
    if not rigs:
        raise RuntimeError("No Control Rig Blueprint is open. Open one or set CONTROL_RIG_PATH.")

    return rigs[0]


def main():
    rig = load_control_rig_blueprint(CONTROL_RIG_PATH)
    builder = RigBuilder(
        source_asset_path=SOURCE_ASSET_PATH,
        rig=rig,
        recipe_map=RECIPE_ASSET_PATHS,
    )

    built_modules = builder.run()
    print("Built modules:", built_modules)


if __name__ == "__main__":
    main()
