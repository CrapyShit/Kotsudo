"""Manifest contract: JSON-Schema validation, semantic checks, migrations.

Pure Python (no ``unreal``, no ``maya``) so the SAME code validates a
manifest in Maya before export and in Unreal before building.

* ``schema/kotsudo_manifest.schema.json`` is the single source of truth for
  structure; this module implements the small JSON-Schema subset it uses
  (type, const, enum, required, properties, additionalProperties, items,
  minItems/maxItems, minLength, minimum/maximum, local ``$ref``).
* ``semantic_checks`` adds what a schema cannot express (unique names, bone
  ownership, parent references).
* ``migrate`` upgrades older manifests in place and reports what it did.

``validate_manifest`` returns (errors, warnings). Errors block the export or
the build; warnings are reported. Unknown properties are always allowed.
"""

import copy
import json
import math
import os

SUPPORTED_SCHEMA_VERSION = 6
SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schema", "kotsudo_manifest.schema.json"
)

_schema_cache = None


def load_schema():
    global _schema_cache
    if _schema_cache is None:
        with open(SCHEMA_PATH, encoding="utf-8") as handle:
            _schema_cache = json.load(handle)
    return _schema_cache


# ---------------------------------------------------------------------------
# JSON-Schema subset
# ---------------------------------------------------------------------------

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}


def _is_type(value, name):
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    expected = _TYPES.get(name)
    return expected is not None and isinstance(value, expected) and not (
        name != "boolean" and isinstance(value, bool)
    )


def _resolve(schema, root):
    ref = schema.get("$ref")
    if not ref:
        return schema
    node = root
    for part in ref.lstrip("#/").split("/"):
        node = node[part]
    return node


def _validate(value, schema, root, path, errors, limit=200):
    if len(errors) >= limit:
        return
    schema = _resolve(schema, root)

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected {schema['const']!r}, got {value!r}")
        return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not one of {schema['enum']}")
        return
    types = schema.get("type")
    if types:
        names = types if isinstance(types, list) else [types]
        if not any(_is_type(value, name) for name in names):
            errors.append(f"{path}: expected {'/'.join(names)}, got {type(value).__name__}")
            return

    if isinstance(value, str) and "minLength" in schema and len(value) < schema["minLength"]:
        errors.append(f"{path}: empty string")
    if _is_type(value, "number"):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value} < minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {value} > maximum {schema['maximum']}")

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required '{key}'")
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties")
        for key, item in value.items():
            if key in properties:
                _validate(item, properties[key], root, f"{path}.{key}", errors, limit)
            elif isinstance(extra, dict):
                _validate(item, extra, root, f"{path}.{key}", errors, limit)

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: needs at least {schema['minItems']} item(s), has {len(value)}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: allows at most {schema['maxItems']} item(s), has {len(value)}")
        if "items" in schema:
            for index, item in enumerate(value):
                _validate(item, schema["items"], root, f"{path}[{index}]", errors, limit)


# ---------------------------------------------------------------------------
# Semantic checks
# ---------------------------------------------------------------------------

def semantic_checks(data):
    """(errors, warnings) the schema cannot express."""
    errors, warnings = [], []
    version = data.get("schema_version")
    if isinstance(version, int) and version > SUPPORTED_SCHEMA_VERSION:
        errors.append(
            f"schema_version {version} is newer than this builder supports "
            f"({SUPPORTED_SCHEMA_VERSION}); update the rig builder."
        )

    modules = data.get("modules") or []
    names, owners = set(), {}
    for module in modules:
        if not isinstance(module, dict):
            continue
        name = module.get("module_name")
        if name in names:
            errors.append(f"duplicate module_name '{name}'")
        names.add(name)
        for bone in module.get("chain") or []:
            if bone in owners and owners[bone] != name:
                warnings.append(f"bone '{bone}' is claimed by '{owners[bone]}' and '{name}'")
            owners.setdefault(bone, name)
    for module in modules:
        if not isinstance(module, dict):
            continue
        parent = (module.get("connections") or {}).get("parent_module")
        if parent and parent not in names:
            warnings.append(f"module '{module.get('module_name')}' has unknown parent_module '{parent}'")
        if not module.get("axes") and len(module.get("chain") or []) > 1:
            warnings.append(f"module '{module.get('module_name')}' has no per-chain axes")

    shapes = data.get("control_shapes") or {}
    for module in modules:
        for shape_id in _shape_ids(module):
            if shape_id not in shapes:
                warnings.append(f"module '{module.get('module_name')}' references unknown shape '{shape_id}'")

    bad = list(_inconsistent_offsets(modules))
    if bad:
        errors.append(
            f"{len(bad)} joint-local offset(s) disagree in LENGTH with the same offset in world "
            f"space (a rotation cannot change a length, so this is a unit error in the export), "
            f"e.g. {'; '.join(bad[:3])}. Re-export with the current exporter."
        )
    return errors, warnings


OFFSET_LENGTH_TOLERANCE_CM = 0.5
OFFSET_LENGTH_TOLERANCE_RATIO = 0.02


def _vector_length(value):
    try:
        return math.sqrt(sum(float(c) * float(c) for c in value[:3]))
    except (TypeError, ValueError, IndexError):
        return None


def _lengths_disagree(a, b):
    if a is None or b is None:
        return False
    return abs(a - b) > max(OFFSET_LENGTH_TOLERANCE_CM, OFFSET_LENGTH_TOLERANCE_RATIO * max(a, b))


def _inconsistent_offsets(value, owner=None):
    """Records whose joint-local and world encodings of one point differ in length.

    offset_local / offset_from_anchor_unreal, and reference_local.vector /
    reference.unreal_vector, are the same vectors on different axes: their
    lengths must match. (This is what caught a metres-vs-centimetres mix.)
    """
    if isinstance(value, dict):
        label = value.get("name") or value.get("anchor_bone") or owner
        local, world = value.get("offset_local"), value.get("offset_from_anchor_unreal")
        if isinstance(local, list) and isinstance(world, list):
            a, b = _vector_length(local), _vector_length(world)
            if _lengths_disagree(a, b):
                yield f"'{label}' offset {a:.2f} vs {b:.2f} cm"
        ref_local = (value.get("reference_local") or {}).get("vector") if isinstance(value.get("reference_local"), dict) else None
        ref_world = (value.get("reference") or {}).get("unreal_vector") if isinstance(value.get("reference"), dict) else None
        if isinstance(ref_local, list) and isinstance(ref_world, list):
            a, b = _vector_length(ref_local), _vector_length(ref_world)
            if _lengths_disagree(a, b):
                yield f"'{label}' reference {a:.2f} vs {b:.2f} cm"
        for child in value.values():
            yield from _inconsistent_offsets(child, label)
    elif isinstance(value, list):
        for child in value:
            yield from _inconsistent_offsets(child, owner)


def _shape_ids(value):
    if isinstance(value, dict):
        if value.get("shape_id"):
            yield value["shape_id"]
        for child in value.values():
            yield from _shape_ids(child)
    elif isinstance(value, list):
        for child in value:
            yield from _shape_ids(child)


def validate_manifest(data):
    """(errors, warnings) for a manifest dict. Never raises."""
    if not isinstance(data, dict):
        return ["manifest is not a JSON object"], []
    errors = []
    try:
        schema = load_schema()
        _validate(data, schema, schema, "$", errors)
    except Exception as exc:  # schema file missing/unreadable: say so, do not crash
        return [], [f"schema validation skipped ({exc})"]
    semantic_errors, warnings = semantic_checks(data)
    return errors + semantic_errors, warnings


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------

# Keys holding a single world vector already mapped to Unreal axes.
_WORLD_VECTOR_KEYS = {
    "offset_from_anchor_unreal", "unreal_world_position", "unreal_vector",
    "unreal_primary_axis", "unreal_secondary_axis", "pole_vector_unreal_world_position",
}
# Keys holding a list of world vectors mapped to Unreal axes.
_WORLD_VECTOR_LIST_KEYS = {"world_axes_unreal", "object_axes_unreal", "points"}


def _flip_y(vector):
    if isinstance(vector, list) and len(vector) == 3 and all(isinstance(c, (int, float)) for c in vector):
        return [vector[0], -vector[1], vector[2]]
    return vector


def _flip_world_vectors(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _WORLD_VECTOR_KEYS:
                value[key] = _flip_y(item)
            elif key in _WORLD_VECTOR_LIST_KEYS and isinstance(item, list):
                value[key] = [_flip_y(v) for v in item]
            else:
                _flip_world_vectors(item)
    elif isinstance(value, list):
        for item in value:
            _flip_world_vectors(item)


def migrate(data):
    """Upgrade a manifest to the current layout. Returns (data, notes).

    The input is not modified; a migrated deep copy is returned.
    """
    notes = []
    data = copy.deepcopy(data)
    coords = data.setdefault("coordinate_system", {})

    # Before schema 6 world vectors used the mapping (X, -Z, Y), a rotation
    # instead of the importer's reflection (X, Z, Y): every Unreal-mapped world
    # vector had its Y negated. Keyed on the recorded mapping, not the version,
    # so a manifest is corrected exactly once.
    if coords.get("vector_mapping") == "X,-Z,Y":
        _flip_world_vectors(data)
        coords["vector_mapping"] = "X,Z,Y"
        notes.append(
            "world vectors were exported with the old (X,-Z,Y) mapping; corrected to "
            "(X,Z,Y). Re-export from Maya to also get joint-local offsets and axes."
        )

    version = data.get("schema_version")
    if not isinstance(version, int):
        data["schema_version"] = version = 3
        notes.append("missing schema_version; assumed 3")
    if version < SUPPORTED_SCHEMA_VERSION:
        data.setdefault("units", {"linear": "cm", "angular": "deg"})
        data.setdefault("schema", "kotsudo.rig")
        notes.append(
            f"schema_version {version} read by a v{SUPPORTED_SCHEMA_VERSION} builder: "
            "joint-local offsets, per-chain axes and Maya parent spaces are missing, "
            "so older fallbacks are used."
        )
    return data, notes
