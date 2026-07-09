from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)

from .context import RigContext
from .logger import RigLogger
from .metadata_reader import (
    ROLE_ATTR,
    build_bone_attr_map,
    detect_modules,
    get_asset_metadata,
    read_manifest_from_ue_metadata,
)
from .modules.fk_module import FKModule
from .modules.ik_module import IKModule
from .modules.ikfk_module import IKFKModule
from .modules.spline_ik_module import SplineIKModule

MODULE_REGISTRY = {
    "FKChain": FKModule,
    "IKLimb": IKModule,
    "IKFKSwitch": IKFKModule,
    "SplineIK": SplineIKModule,
}

# Build order tiebreaker used within the same dependency depth level.
# FK must execute before IK/IKFK so FK SetTransform with bPropagateToChildren=True
# does not overwrite IK-solved bones.
# IKFKSwitch runs after IKLimb because it internally runs the same IK solve pass.
MODULE_BUILD_ORDER = {
    "FKChain": 0,
    "IKLimb": 1,
    "IKFKSwitch": 2,
    "SplineIK": 3,
}


def _build_dependency_graph(module_defs):
    """
    Return {module_name: parent_module_name | None} for every module in the list.
    The parent comes from the manifest's connections.parent_module field.
    """
    return {
        m["module_name"]: (m.get("connections") or {}).get("parent_module")
        for m in module_defs
    }


def _module_depth(name, by_name, dep_graph, depths, visiting):
    """Recursively compute build depth (root = 0) with cycle protection."""
    if name in depths:
        return depths[name]
    if name in visiting:          # cycle — treat as root
        depths[name] = 0
        return 0
    visiting.add(name)
    parent = dep_graph.get(name)
    if parent is None or parent not in by_name:
        depths[name] = 0
    else:
        depths[name] = _module_depth(parent, by_name, dep_graph, depths, visiting) + 1
    visiting.discard(name)
    return depths[name]


def _topological_sort(module_defs):
    """
    Sort module_defs so every parent module is built before its children.
    Within the same depth level MODULE_BUILD_ORDER is used as a tiebreaker
    (FK always before IK at the same depth).
    """
    dep_graph = _build_dependency_graph(module_defs)
    by_name = {m["module_name"]: m for m in module_defs}
    depths = {}
    for m in module_defs:
        _module_depth(m["module_name"], by_name, dep_graph, depths, set())
    return sorted(
        module_defs,
        key=lambda m: (
            depths[m["module_name"]],
            MODULE_BUILD_ORDER.get(m.get("module_type", ""), 99),
        ),
    )


class RigBuilder:
    def __init__(self, source_asset_path, rig=None, recipe_map=None, module_registry=None):
        self.source_asset_path = source_asset_path
        self.rig = rig
        self.recipe_map = recipe_map or {}
        self.module_registry = module_registry or MODULE_REGISTRY
        self.logger = RigLogger()

    def warn(self, message):
        formatted_message = f"[RigBuilder] Warning: {message}"
        if hasattr(unreal, "log_warning"):
            unreal.log_warning(formatted_message)
        else:
            print(formatted_message)

    def validate_module_definition(self, module_definition):
        module_type = module_definition.get("module_type")
        module_name = module_definition.get("module_name") or module_type or "<unknown>"
        chain = list(module_definition.get("chain") or [])
        chain_items = list(module_definition.get("chain_items") or [])
        module_class = self.module_registry.get(module_type)
        if not module_class:
            self.warn(f"Skipping module '{module_name}': no registered class for module type '{module_type}'.")
            return False

        contract = {}
        if hasattr(module_class, "describe_contract"):
            try:
                contract = module_class.describe_contract() or {}
            except Exception as exc:
                self.warn(
                    f"Could not read contract for module '{module_name}' ({module_type}): {exc}."
                )
                return False

        chain_rules = contract.get("chain") or {}
        exact_length = chain_rules.get("exact_length")
        min_length = chain_rules.get("min_length")
        max_length = chain_rules.get("max_length")
        issues = []

        if exact_length is not None and len(chain) != exact_length:
            issues.append(f"expected {exact_length} bones but detected {len(chain)}")
        else:
            if min_length is not None and len(chain) < min_length:
                issues.append(f"expected at least {min_length} bones but detected {len(chain)}")
            if max_length is not None and len(chain) > max_length:
                issues.append(f"expected at most {max_length} bones but detected {len(chain)}")

        required_metadata = set(contract.get("required_metadata") or [])
        expected_roles = list(chain_rules.get("roles") or [])
        if ROLE_ATTR in required_metadata and expected_roles:
            present_roles = [item.get("role") for item in chain_items if item.get("role")]
            missing_roles = [role for role in expected_roles if role not in present_roles]
            if missing_roles:
                issues.append("missing roles " + ", ".join(missing_roles))

        if issues:
            chain_summary = ", ".join(
                f"{item.get('bone_name')}:{item.get('role') or '?'}" for item in chain_items
            ) or ", ".join(chain)
            self.warn(
                f"Skipping module '{module_name}' ({module_type}): {'; '.join(issues)}. "
                f"Detected chain: [{chain_summary}]"
            )
            return False

        return True

    def _derive_skeleton_from_rig(self):
        """Derive the Skeleton asset directly from the open Control Rig's preview mesh.

        Returns a Skeleton object, or None if the rig has no preview mesh assigned.
        """
        if not self.rig:
            return None
        try:
            mesh = self.rig.get_preview_mesh()
            if mesh:
                skel = mesh.get_editor_property("skeleton")
                if skel:
                    return skel
        except Exception:
            pass
        return None

    def load_source_asset(self):
        self.logger.log("[RigBuilder] Loading asset")
        if not self.source_asset_path:
            # Auto-derive skeleton from the open Control Rig blueprint so
            # SOURCE_ASSET_PATH never needs to be updated when creating new skeletons.
            skeleton = self._derive_skeleton_from_rig()
            if skeleton:
                self.logger.log(f"[RigBuilder] Auto-derived skeleton: {skeleton.get_name()}")
                return skeleton
            raise RuntimeError(
                "source_asset_path is not set and could not auto-derive the skeleton "
                "from the Control Rig blueprint (no preview mesh assigned). "
                "Set SOURCE_ASSET_PATH to the skeleton or skeletal mesh asset path."
            )
        asset = unreal.EditorAssetLibrary.load_asset(self.source_asset_path)
        if not asset:
            raise RuntimeError(f"Invalid asset path: {self.source_asset_path}")
        return asset

    def load_any_asset(self, asset_path):
        self.logger.log(f"[RigBuilder] Loading asset: {asset_path}")
        asset = unreal.EditorAssetLibrary.load_asset(asset_path)
        if not asset:
            raise RuntimeError(f"Invalid asset path: {asset_path}")
        return self.resolve_blueprint_asset(asset)

    @staticmethod
    def resolve_blueprint_asset(asset):
        if not asset:
            return asset

        is_blueprint_asset = False
        if hasattr(unreal, "Blueprint"):
            try:
                is_blueprint_asset = isinstance(asset, unreal.Blueprint)
            except Exception:
                is_blueprint_asset = False

        if not is_blueprint_asset:
            return asset

        generated_class = None
        if hasattr(asset, "generated_class"):
            try:
                generated_class = asset.generated_class()
            except Exception:
                generated_class = None

        if not generated_class and hasattr(unreal, "BlueprintEditorLibrary") and hasattr(unreal.BlueprintEditorLibrary, "generated_class"):
            try:
                generated_class = unreal.BlueprintEditorLibrary.generated_class(asset)
            except Exception:
                generated_class = None

        if not generated_class:
            return asset

        if hasattr(generated_class, "get_default_object"):
            try:
                default_object = generated_class.get_default_object()
                if default_object:
                    return default_object
            except Exception:
                pass

        if hasattr(unreal, "get_default_object"):
            try:
                default_object = unreal.get_default_object(generated_class)
                if default_object:
                    return default_object
            except Exception:
                pass

        return asset

    @staticmethod
    def load_control_rig_blueprint(rig_path=None):
        unreal.load_module("ControlRigDeveloper")

        if rig_path:
            rig = unreal.EditorAssetLibrary.load_asset(rig_path)
            if not rig:
                raise RuntimeError(f"Invalid Control Rig path: {rig_path}")
            return rig

        rigs = unreal.ControlRigBlueprint.get_currently_open_rig_blueprints()
        if not rigs:
            raise RuntimeError("No Control Rig Blueprint is open. Open one or set a rig path.")

        return rigs[0]

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
        recipe = self.recipe_map.get(module_type)
        if isinstance(recipe, str):
            return self.load_any_asset(recipe)
        return recipe

    def compile_rig(self):
        if not self.rig:
            return

        if hasattr(self.rig, "recompile_vm"):
            self.rig.recompile_vm()

        if hasattr(unreal, "BlueprintEditorLibrary") and hasattr(unreal.BlueprintEditorLibrary, "compile_blueprint"):
            unreal.BlueprintEditorLibrary.compile_blueprint(self.rig)

        if hasattr(unreal, "ControlRigBlueprintLibrary") and hasattr(unreal.ControlRigBlueprintLibrary, "request_control_rig_init"):
            unreal.ControlRigBlueprintLibrary.request_control_rig_init(self.rig)

        if hasattr(unreal, "BlueprintEditorLibrary") and hasattr(unreal.BlueprintEditorLibrary, "refresh_open_editors_for_blueprint"):
            unreal.BlueprintEditorLibrary.refresh_open_editors_for_blueprint(self.rig)

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

        connections = module_definition.get("connections") or {}
        return module_class(
            context=context,
            chain=module_definition["chain"],
            recipe=self.get_recipe_for_module(module_type),
            name=module_definition["module_name"],
            logger=self.logger,
            parent_module_name=connections.get("parent_module"),
            parent_attach_point=connections.get("parent_attach_point"),
        )

    def run(self):
        source_asset = self.load_source_asset()
        skeleton = self.resolve_skeleton(source_asset)
        skeletal_mesh = source_asset if isinstance(source_asset, unreal.SkeletalMesh) else None

        self.logger.log("[RigBuilder] Reading metadata")
        metadata = {}
        metadata.update(get_asset_metadata(skeletal_mesh))
        metadata.update(get_asset_metadata(skeleton))

        # Primary: read the rich manifest embedded in the RIG_MANIFEST bone
        # (exported from Maya via tools/maya/export_rig_manifest.py).
        detected_modules = []
        manifest_modules = read_manifest_from_ue_metadata(metadata)
        if manifest_modules is not None:
            detected_modules = [
                m for m in manifest_modules
                if m.get("module_type") in self.module_registry
            ]
            self.logger.log(
                "[RigBuilder] Loaded {} module(s) from embedded manifest.".format(len(detected_modules))
            )

        # Fallback: detect modules from per-bone ModuleType/ModuleName/Role attributes.
        if not detected_modules:
            self.logger.log("[RigBuilder] No embedded manifest found, detecting from bone attributes")
            bone_names = self.get_bone_names(skeleton)
            bone_attribute_map = build_bone_attr_map(metadata)
            detected_modules = detect_modules(
                bone_names,
                bone_attribute_map,
                supported_module_types=self.module_registry.keys(),
            )

        if detected_modules and not self.rig:
            raise RuntimeError("RigBuilder detected modules but no Control Rig instance was provided.")

        # Sort by dependency depth (parents always before children).
        # Within the same depth, MODULE_BUILD_ORDER is the tiebreaker (FK < IK).
        detected_modules = _topological_sort(detected_modules)

        context = self.create_context()
        self.logger.push("[RigBuilder] Building modules")
        built_modules = []
        for module_definition in detected_modules:
            if not self.validate_module_definition(module_definition):
                continue

            module_instance = self.instantiate_module(module_definition, context)
            if not module_instance:
                continue

            try:
                module_instance.validate()
                result = module_instance.build()
                context.register_result(module_definition["module_name"], result)
                built_modules.append(result)
            except Exception as exc:
                self.warn(
                    f"Skipping module '{module_definition['module_name']}' ({module_definition['module_type']}): {exc}"
                )

        self.logger.pop()

        if built_modules and self.rig:
            self.logger.log("[RigBuilder] Compiling rig")
            self.compile_rig()

        return built_modules

