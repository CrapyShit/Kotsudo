from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)

try:
    from .context import RigContext
    from .logger import RigLogger
    from .metadata_reader import (
        build_bone_attr_map,
        detect_modules,
        get_asset_metadata,
    )
    from .modules.ik_module import IKModule
except ImportError:
    from context import RigContext
    from logger import RigLogger
    from metadata_reader import (
        build_bone_attr_map,
        detect_modules,
        get_asset_metadata,
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
        self.logger = RigLogger()

    def load_source_asset(self):
        self.logger.log("[RigBuilder] Loading asset")
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

    def create_context(self):
        if not self.rig:
            return None

        return RigContext(self.rig)

    def instantiate_module(self, module_definition, context):
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
            context=context,
            chain=module_definition["chain"],
            recipe=self.get_recipe_for_module(module_type),
            name=module_definition["module_name"],
            logger=self.logger,
        )

    def run(self):
        source_asset = self.load_source_asset()
        skeleton = self.resolve_skeleton(source_asset)
        skeletal_mesh = source_asset if isinstance(source_asset, unreal.SkeletalMesh) else None

        self.logger.log("[RigBuilder] Reading metadata")
        metadata = {}
        metadata.update(get_asset_metadata(skeletal_mesh))
        metadata.update(get_asset_metadata(skeleton))

        self.logger.log("[RigBuilder] Detecting modules")
        bone_names = self.get_bone_names(skeleton)
        bone_attribute_map = build_bone_attr_map(metadata)
        detected_modules = detect_modules(
            bone_names,
            bone_attribute_map,
            supported_module_types=self.module_registry.keys(),
        )

        context = self.create_context()
        self.logger.push("[RigBuilder] Building modules")
        built_modules = []
        for module_definition in detected_modules:
            module_instance = self.instantiate_module(module_definition, context)
            if not module_instance:
                continue

            module_instance.validate()
            built_modules.append(module_instance.build())

        self.logger.pop()

        return built_modules
