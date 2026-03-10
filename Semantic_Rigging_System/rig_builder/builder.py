from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)

try:
    from .metadata_reader import (
        build_bone_attribute_map,
        detect_modules_from_metadata,
        read_asset_metadata,
    )
    from .modules.ik_module import IKModule
except ImportError:
    from metadata_reader import (
        build_bone_attribute_map,
        detect_modules_from_metadata,
        read_asset_metadata,
    )
    from modules.ik_module import IKModule

MODULE_REGISTRY = {
    "IKLimb": IKModule,
}


class RigBuilder:
    def __init__(self, source_asset_path, rig=None, recipe_map=None, module_registry=None):
        self.source_asset_path = source_asset_path
        self.rig = rig
        self.recipe_map = recipe_map or {}
        self.module_registry = module_registry or MODULE_REGISTRY

    def load_source_asset(self):
        asset = unreal.EditorAssetLibrary.load_asset(self.source_asset_path)
        if not asset:
            raise RuntimeError(f"Invalid asset path: {self.source_asset_path}")
        return asset

    def resolve_skeleton(self, asset):
        if isinstance(asset, unreal.SkeletalMesh):
            skeleton = asset.get_editor_property("skeleton")
            if not skeleton:
                raise RuntimeError("SkeletalMesh has no skeleton assigned.")
            return skeleton

        if isinstance(asset, unreal.Skeleton):
            return asset

        raise RuntimeError(f"Expected a Skeleton or SkeletalMesh, got: {type(asset)}")

    def get_bone_names(self, skeleton):
        reference_pose = skeleton.get_reference_pose()
        if not reference_pose or not reference_pose.is_valid():
            raise RuntimeError("Could not read the skeleton reference pose.")

        return [str(bone_name) for bone_name in reference_pose.get_bone_names()]

    def get_recipe_for_module(self, module_type):
        return self.recipe_map.get(module_type)

    def instantiate_module(self, module_definition):
        module_type = module_definition["module_type"]
        module_class = self.module_registry.get(module_type)
        if not module_class:
            message = f"No registered module class for module type: {module_type}"
            if hasattr(unreal, "log_warning"):
                unreal.log_warning(message)
            else:
                print(message)
            return None

        return module_class(
            rig=self.rig,
            chain=module_definition["chain"],
            recipe=self.get_recipe_for_module(module_type),
            name=module_definition["module_name"],
        )

    def run(self):
        source_asset = self.load_source_asset()
        skeleton = self.resolve_skeleton(source_asset)
        skeletal_mesh = source_asset if isinstance(source_asset, unreal.SkeletalMesh) else None

        metadata = {}
        metadata.update(read_asset_metadata(skeletal_mesh))
        metadata.update(read_asset_metadata(skeleton))

        bone_names = self.get_bone_names(skeleton)
        bone_attribute_map = build_bone_attribute_map(metadata)
        detected_modules = detect_modules_from_metadata(
            bone_names,
            bone_attribute_map,
            supported_module_types=self.module_registry.keys(),
        )

        built_modules = []
        for module_definition in detected_modules:
            module_instance = self.instantiate_module(module_definition)
            if not module_instance:
                continue

            module_instance.build()
            built_modules.append(module_instance)

        return built_modules
