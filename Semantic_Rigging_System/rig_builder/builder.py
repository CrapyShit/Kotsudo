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
from .modules.rig_module import RigModule
from .modules.spline_ik_module import SplineIKModule

MODULE_REGISTRY = {
    "FKChain": FKModule,
    "IKLimb": IKModule,
    "IKFKSwitch": IKFKModule,
    "SplineIK": SplineIKModule,
}


class _MergedModuleRecipe:
    """Recipe view seen by each RigModule instance.

    Root-cause fix: instantiate_module() previously passed each module the
    SHARED, per-module-TYPE recipe from self.recipe_map only -- the manifest's
    per-instance "recipe" and "params" dicts (parsed correctly by
    metadata_reader.py, DAG-path-stripped and all) were computed, carried all
    the way through the pipeline, and then never read again. Every IKLimb
    instance got the identical recipe regardless of what Maya actually
    detected for that specific limb (primary_axis, pole_vector_world_position,
    stretch_enabled, twist_mode, switch default_value, etc).

    This wrapper merges, in priority order (highest first):
        1. module_definition["recipe"]   (explicit per-instance overrides)
        2. module_definition["params"]   (Maya's structural detection output)
        3. the shared type-level recipe asset (self.recipe_map), as a fallback
           for fields Maya doesn't detect per-instance (e.g. ControlShape)

    RigModule.resolve_recipe_fields() only ever calls dir(self.recipe) and
    get_editor_property()/getattr(self.recipe, name) -- both are implemented
    here, so no change to rig_module.py or any module's read_recipe() is
    required for this bridge to work. Existing fallback_names in each
    module's read_recipe() (e.g. IKFKModule already listing "default_value"
    as a fallback for a not-yet-existing "DefaultBlend" field) will pick up
    the newly-available manifest data automatically once each module adds
    the corresponding field.
    """

    def __init__(self, manifest_recipe=None, manifest_params=None, base_recipe=None):
        merged = {}

        if base_recipe is not None:
            for prop_name in [n for n in dir(base_recipe) if not n.startswith("_")]:
                try:
                    merged[prop_name] = RigModule.read_unreal_property(base_recipe, prop_name)
                except Exception:
                    continue

        # Per-instance manifest data overrides the shared type-level recipe.
        # "params" (raw Maya detection output) is applied first, then
        # "recipe" (explicit overrides) on top, so recipe always wins if both
        # happen to define the same field.
        merged.update(manifest_params or {})
        merged.update(manifest_recipe or {})

        self._data = merged

    def __dir__(self):
        return list(self._data.keys())

    def __bool__(self):
        return True

    def get_editor_property(self, name):
        if name in self._data:
            return self._data[name]
        lowered = name.lower()
        for key, value in self._data.items():
            if key.lower() == lowered:
                return value
        raise AttributeError(name)

    def __getattr__(self, name):
        # __getattr__ only fires for attributes not already found normally,
        # so this never intercepts _data itself.
        return self.get_editor_property(name)

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


def _module_depth(name, by_name, dep_graph, depths, visiting, cycle_report):
    """Recursively compute build depth (root = 0) with cycle protection.

    cycle_report is a list the caller can inspect afterward -- a cycle is no
    longer silently swallowed, the offending module names are recorded so
    the builder can warn about it explicitly.
    """
    if name in depths:
        return depths[name]
    if name in visiting:          # cycle — treat as root, but report it
        cycle_report.append(name)
        depths[name] = 0
        return 0
    visiting.add(name)
    parent = dep_graph.get(name)
    if parent is None or parent not in by_name:
        depths[name] = 0
    else:
        depths[name] = _module_depth(parent, by_name, dep_graph, depths, visiting, cycle_report) + 1
    visiting.discard(name)
    return depths[name]


def _topological_sort(module_defs, warn=None):
    """
    Sort module_defs so every parent module is built before its children.
    Within the same depth level MODULE_BUILD_ORDER is used as a tiebreaker
    (FK always before IK at the same depth).
    """
    dep_graph = _build_dependency_graph(module_defs)
    by_name = {m["module_name"]: m for m in module_defs}
    depths = {}
    cycle_report = []
    for m in module_defs:
        _module_depth(m["module_name"], by_name, dep_graph, depths, set(), cycle_report)

    if cycle_report and warn:
        warn(
            "Parent-module cycle detected involving: " + ", ".join(sorted(set(cycle_report))) +
            ". These modules were treated as roots (built at world space) to avoid an infinite "
            "loop -- fix the connections.parent_module chain in the manifest."
        )

    return sorted(
        module_defs,
        key=lambda m: (
            depths[m["module_name"]],
            MODULE_BUILD_ORDER.get(m.get("module_type", ""), 99),
        ),
    )


def _preflight_validate(module_defs, warn):
    """Whole-manifest sanity pass, run once before any module is built.

    Catches the class of bug that's easy to miss on a complex, multi-module
    rig: two modules silently fighting over the same bone, a duplicated
    module name silently shadowing an earlier module's build result, or a
    parent reference that points at a module which doesn't exist anywhere
    in this manifest. All of these previously either crashed deep inside a
    module's build() with a confusing error, or -- worse -- built
    "successfully" while producing a visibly wrong rig.

    Returns a filtered list of module_defs with the offending duplicates/
    bone-collisions already removed (each with a warning explaining why).
    Dangling parent references are NOT removed here -- they're allowed
    through so the module still gets built, just parented to world space
    with a loud warning from RigContext.get_parent_control_key at build time.
    """
    seen_names = {}
    deduped = []
    for module_def in module_defs:
        name = module_def.get("module_name")
        if name in seen_names:
            warn(
                f"Duplicate module_name '{name}' found in the manifest "
                f"(first seen as {seen_names[name]}, again as "
                f"{module_def.get('module_type')}). Keeping the first occurrence "
                "only -- rename one of them in Maya so each module has a unique name."
            )
            continue
        seen_names[name] = module_def.get("module_type")
        deduped.append(module_def)

    all_names = {m["module_name"] for m in deduped}
    for module_def in deduped:
        parent = (module_def.get("connections") or {}).get("parent_module")
        if parent and parent not in all_names:
            warn(
                f"Module '{module_def['module_name']}' declares parent_module "
                f"'{parent}', which does not exist anywhere in this manifest. "
                "It will be built parented to world space instead."
            )

    # Bone-ownership collision check: if two modules claim the same bone,
    # both would silently write SetTransform to it in the same build with
    # no error -- whichever happens to execute last in the topological
    # sort wins, with zero indication anything was wrong. First-declared
    # module (manifest order) keeps the bone; every later conflicting
    # module is dropped entirely, since stripping just the conflicting
    # bones out of its chain would usually break that module's own chain
    # contract anyway (e.g. an exact-length-3 IKFKSwitch losing one bone).
    bone_owner = {}
    result = []
    dropped_names = set()
    for module_def in deduped:
        chain = module_def.get("chain") or []
        conflicts = [(b, bone_owner[b]) for b in chain if b in bone_owner]
        if conflicts:
            conflict_desc = ", ".join(f"'{b}' (owned by '{owner}')" for b, owner in conflicts)
            warn(
                f"Module '{module_def['module_name']}' ({module_def.get('module_type')}) "
                f"claims bone(s) already owned by another module: {conflict_desc}. "
                "Dropping this module entirely -- fix the overlapping chains in Maya. "
                "First-declared module in the manifest always wins the conflicting bone(s)."
            )
            dropped_names.add(module_def["module_name"])
            continue
        for b in chain:
            bone_owner[b] = module_def["module_name"]
        result.append(module_def)

    # A module that got dropped for a bone conflict might itself have been
    # declared as someone else's parent_module -- if so, that declared
    # parent no longer exists in `result`, and the dangling-parent warning
    # above will apply to it naturally on the next pass. Re-check here so
    # the warning fires even when the "missing" parent is a conflict
    # casualty rather than a manifest typo.
    if dropped_names:
        remaining_names = {m["module_name"] for m in result}
        for module_def in result:
            parent = (module_def.get("connections") or {}).get("parent_module")
            if parent in dropped_names:
                warn(
                    f"Module '{module_def['module_name']}' declares parent_module "
                    f"'{parent}', which was dropped due to a bone-ownership conflict "
                    "(see warning above). It will be built parented to world space instead."
                )

    return result


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

    def validate_module_definition(self, module_definition, merged_recipe=None):
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

        # Required-recipe-field check. Every module's describe_contract()
        # declares required_recipe_fields, but until now nothing actually
        # checked them -- a module could silently build with a required
        # field resolving to None and only fail (or worse, build with a
        # wrong default) deep inside build(). Checked here, before any
        # graph nodes exist, against the SAME merged per-instance recipe
        # (manifest params/recipe + shared type-level asset) the module
        # will actually receive.
        required_recipe_fields = list(contract.get("required_recipe_fields") or [])
        if required_recipe_fields and merged_recipe is not None:
            missing_fields = []
            for field_name in required_recipe_fields:
                try:
                    value = RigModule.read_unreal_property(merged_recipe, field_name)
                except Exception:
                    value = None
                if value is None:
                    missing_fields.append(field_name)
            if missing_fields:
                issues.append(
                    "missing required recipe field(s): " + ", ".join(missing_fields)
                )

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

        return RigContext(self.rig, logger=self.logger)

    def build_merged_recipe(self, module_definition):
        module_type = module_definition["module_type"]
        base_recipe = self.get_recipe_for_module(module_type)
        return _MergedModuleRecipe(
            manifest_recipe=module_definition.get("recipe"),
            manifest_params=module_definition.get("params"),
            base_recipe=base_recipe,
        )

    def instantiate_module(self, module_definition, context, merged_recipe=None):
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
        if merged_recipe is None:
            merged_recipe = self.build_merged_recipe(module_definition)
        return module_class(
            context=context,
            chain=module_definition["chain"],
            recipe=merged_recipe,
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

        # Whole-manifest sanity pass: duplicate module names, bone-ownership
        # collisions between modules, and dangling parent references are all
        # caught here, once, before any node is built -- rather than
        # surfacing as a confusing per-module exception or, worse, building
        # "successfully" into a visibly wrong rig.
        detected_modules = _preflight_validate(detected_modules, self.warn)

        # Sort by dependency depth (parents always before children).
        # Within the same depth, MODULE_BUILD_ORDER is the tiebreaker (FK < IK).
        detected_modules = _topological_sort(detected_modules, warn=self.warn)

        context = self.create_context()
        self.logger.push("[RigBuilder] Building modules")
        built_modules = []
        for module_definition in detected_modules:
            module_name = module_definition["module_name"]

            # Cascading skip: if this module's declared parent already failed
            # or was skipped, don't build this module detached at world
            # space -- skip it too, and record it as failed so ITS children
            # cascade the same way. Modules are processed in topological
            # order (parents before children) so the parent's outcome is
            # always already known by the time we get here.
            parent_name = (module_definition.get("connections") or {}).get("parent_module")
            if parent_name and context.is_failed(parent_name):
                self.warn(
                    f"Skipping module '{module_name}' ({module_definition['module_type']}): "
                    f"its parent module '{parent_name}' was skipped or failed to build."
                )
                context.mark_failed(module_name)
                continue

            merged_recipe = self.build_merged_recipe(module_definition)
            if not self.validate_module_definition(module_definition, merged_recipe):
                context.mark_failed(module_name)
                continue

            module_instance = self.instantiate_module(module_definition, context, merged_recipe)
            if not module_instance:
                context.mark_failed(module_name)
                continue

            try:
                module_instance.validate()
                result = module_instance.build()
                context.register_result(module_name, result)
                built_modules.append(result)
            except Exception as exc:
                self.warn(
                    f"Skipping module '{module_name}' ({module_definition['module_type']}): {exc}"
                )
                context.mark_failed(module_name)

        self.logger.pop()

        if built_modules and self.rig:
            self.logger.log("[RigBuilder] Compiling rig")
            self.compile_rig()

        return built_modules

