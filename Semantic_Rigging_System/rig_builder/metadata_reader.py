import json
from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)

MODULE_TYPE_ATTR = "ModuleType"
MODULE_NAME_ATTR = "ModuleName"
ROLE_ATTR = "Role"
ROLE_ORDER = {"Start": 0, "Mid": 1, "End": 2}

MANIFEST_JSON_ATTR = "rig_manifest_json"


def get_asset_metadata(asset):
    if not asset:
        return {}

    raw_metadata = unreal.EditorAssetLibrary.get_metadata_tag_values(asset) or {}
    return {str(key): str(value) for key, value in raw_metadata.items()}


def build_bone_attr_map(metadata, wanted_attributes=None):
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


def get_bone_attr(bone_attrs, bone_name, attr_name):
    if bone_name in bone_attrs and attr_name in bone_attrs[bone_name]:
        return bone_attrs[bone_name][attr_name]

    lowered_bone_name = bone_name.lower()
    for mapped_bone_name, attrs in bone_attrs.items():
        if mapped_bone_name.lower() == lowered_bone_name and attr_name in attrs:
            return attrs[attr_name]

    return ""


def detect_ik_modules(bone_names, bone_attrs, supported_module_types=None):
    supported_module_types = set(supported_module_types or [])
    module_groups = {}

    for bone_name in bone_names:
        module_type = get_bone_attr(bone_attrs, bone_name, MODULE_TYPE_ATTR)
        if not module_type:
            continue

        if supported_module_types and module_type not in supported_module_types:
            continue

        module_name = get_bone_attr(bone_attrs, bone_name, MODULE_NAME_ATTR) or module_type
        role = get_bone_attr(bone_attrs, bone_name, ROLE_ATTR)

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
        ordered_bones = sorted(module_data["bones"], key=lambda item: item["order"])
        ordered_chain = [
            item["bone_name"]
            for item in ordered_bones
        ]
        detected_modules.append(
            {
                "module_type": module_data["module_type"],
                "module_name": module_data["module_name"],
                "chain": ordered_chain,
                "chain_items": ordered_bones,
            }
        )

    return detected_modules


def detect_modules(bone_names, bone_attrs, supported_module_types=None):
    return detect_ik_modules(
        bone_names,
        bone_attrs,
        supported_module_types=supported_module_types,
    )


def read_manifest_from_ue_metadata(metadata):
    """
    Look for a 'rig_manifest_json' attribute on the RIG_MANIFEST bone inside
    the already-loaded UE5 asset metadata dict (from get_asset_metadata).

    UE5's Interchange importer stores FBX bone custom attributes with keys:
        'INTERCHANGE.<BoneName>.<AttributeName>'  or  'FBX.<BoneName>.<AttributeName>'

    Returns a list of module definition dicts, or None if not found.
    """
    suffix = ".{}".format(MANIFEST_JSON_ATTR).lower()
    json_str = None
    for raw_key, raw_value in metadata.items():
        if str(raw_key).lower().endswith(suffix):
            json_str = str(raw_value)
            break

    if not json_str:
        return None

    try:
        data = json.loads(json_str)
    except (ValueError, TypeError):
        return None

    return _parse_modules_from_manifest_data(data)


def read_asset_metadata(asset):
    return get_asset_metadata(asset)


def _strip_dag_prefix(name):
    """Strip Maya full DAG path prefix (e.g. '|root|spine_01_jnt' -> 'spine_01_jnt')."""
    return name.split("|")[-1] if name else name


def _parse_modules_from_manifest_data(data):
    """Shared helper: convert a parsed manifest dict to a list of module defs."""
    raw_modules = data.get("modules") or []
    result = []
    for raw in raw_modules:
        module_def = {
            "module_type": raw.get("module_type", ""),
            "module_name": raw.get("module_name", ""),
            "chain": [_strip_dag_prefix(b) for b in (raw.get("chain") or [])],
            "chain_items": [
                {
                    "bone_name": _strip_dag_prefix(item.get("bone_name", "")),
                    "role": item.get("role", ""),
                }
                for item in (raw.get("chain_items") or [])
            ],
        }
        if raw.get("connections"):
            module_def["connections"] = dict(raw["connections"])
        if raw.get("recipe"):
            module_def["recipe"] = dict(raw["recipe"])
        if raw.get("params"):
            module_def["params"] = dict(raw["params"])
        result.append(module_def)
    return result


def build_bone_attribute_map(metadata, wanted_attributes=None):
    return build_bone_attr_map(metadata, wanted_attributes=wanted_attributes)


def detect_modules_from_metadata(bone_names, bone_attribute_map, supported_module_types=None):
    return detect_modules(
        bone_names,
        bone_attribute_map,
        supported_module_types=supported_module_types,
    )
