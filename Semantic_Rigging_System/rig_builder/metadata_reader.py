from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)

MODULE_TYPE_ATTR = "ModuleType"
MODULE_NAME_ATTR = "ModuleName"
ROLE_ATTR = "Role"
ROLE_ORDER = {"Start": 0, "Mid": 1, "End": 2}


def read_asset_metadata(asset):
    if not asset:
        return {}

    raw_metadata = unreal.EditorAssetLibrary.get_metadata_tag_values(asset) or {}
    return {str(key): str(value) for key, value in raw_metadata.items()}



def build_bone_attribute_map(metadata, wanted_attributes=None):
    wanted_attributes = wanted_attributes or [MODULE_TYPE_ATTR, MODULE_NAME_ATTR, ROLE_ATTR]
    wanted_lookup = {attribute.lower(): attribute for attribute in wanted_attributes}
    bone_attribute_map = {}

    for raw_key, raw_value in metadata.items():
        key = str(raw_key)
        value = str(raw_value)
        lowered_key = key.lower()

        for lowered_attribute, attribute_name in wanted_lookup.items():
            suffix = "." + lowered_attribute
            if not lowered_key.endswith(suffix):
                continue

            bone_name = key[: -len(suffix)]
            for prefix in ("INTERCHANGE.", "FBX."):
                if bone_name.lower().startswith(prefix.lower()):
                    bone_name = bone_name[len(prefix):]
                    break

            bone_attribute_map.setdefault(bone_name, {})[attribute_name] = value
            break

    return bone_attribute_map



def detect_modules_from_metadata(bone_names, bone_attribute_map, supported_module_types=None):
    supported_module_types = set(supported_module_types or [])
    module_groups = {}

    for bone_name in bone_names:
        attributes = bone_attribute_map.get(bone_name)
        if not attributes:
            attributes = next(
                (
                    values
                    for mapped_bone_name, values in bone_attribute_map.items()
                    if mapped_bone_name.lower() == bone_name.lower()
                ),
                None,
            )

        if not attributes:
            continue

        module_type = attributes.get(MODULE_TYPE_ATTR)
        if not module_type:
            continue

        if supported_module_types and module_type not in supported_module_types:
            continue

        module_name = attributes.get(MODULE_NAME_ATTR) or module_type
        role = attributes.get(ROLE_ATTR, "")

        module_entry = module_groups.setdefault(
            module_name,
            {
                "module_type": module_type,
                "module_name": module_name,
                "bones": [],
            },
        )
        module_entry["bones"].append(
            {
                "bone_name": bone_name,
                "role": role,
                "order": ROLE_ORDER.get(role, len(ROLE_ORDER) + len(module_entry["bones"])),
            }
        )

    detected_modules = []
    for module_data in module_groups.values():
        ordered_chain = [
            item["bone_name"]
            for item in sorted(module_data["bones"], key=lambda item: item["order"])
        ]
        detected_modules.append(
            {
                "module_type": module_data["module_type"],
                "module_name": module_data["module_name"],
                "chain": ordered_chain,
            }
        )

    return detected_modules
