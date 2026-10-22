"""Materials: give the imported character its Maya colours.

The exporter describes every material on an exported mesh (``materials`` in
the manifest): its name, shader type and its visible colour already
converted to Unreal's linear sRGB (``color_unreal`` = colour x diffuse /
base weight, out of Maya's rendering space, e.g. ACEScg). Unreal's importer
names the skeletal mesh's material slots after the Maya materials, so:

* one master material ``M_KotsudoLambert`` (a BaseColor parameter, fully
  rough, no specular -- what a lambert is), created once in the project;
* one material instance per Maya material, ``MI_<name>``, next to the mesh
  (``<mesh folder>/Materials``), with its BaseColor set;
* each slot whose name matches a Maya material gets its instance.

Run after the rig build (run_rig_builder.py, APPLY_MATERIALS); re-running
updates the instances in place. Never raises: a failure is logged and the
rig build stands.
"""

from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)

MASTER_PATH = "/Game/RigBuilder/Materials"
MASTER_NAME = "M_KotsudoLambert"
COLOR_PARAMETER = "BaseColor"


def _log(message):
    print(f"[RigBuilder] {message}")


def _asset_tools():
    return unreal.AssetToolsHelpers.get_asset_tools()


def ensure_master():
    """The master material (created on first use)."""
    path = f"{MASTER_PATH}/{MASTER_NAME}"
    library = unreal.EditorAssetLibrary
    if library.does_asset_exist(path):
        return library.load_asset(path)
    material = _asset_tools().create_asset(MASTER_NAME, MASTER_PATH, unreal.Material, unreal.MaterialFactoryNew())
    edit = unreal.MaterialEditingLibrary
    color = edit.create_material_expression(material, unreal.MaterialExpressionVectorParameter, -400, 0)
    color.set_editor_property("parameter_name", COLOR_PARAMETER)
    color.set_editor_property("default_value", unreal.LinearColor(0.5, 0.5, 0.5, 1.0))
    edit.connect_material_property(color, "", unreal.MaterialProperty.MP_BASE_COLOR)
    for value, prop, y in ((1.0, unreal.MaterialProperty.MP_ROUGHNESS, 200),
                           (0.0, unreal.MaterialProperty.MP_SPECULAR, 300)):
        constant = edit.create_material_expression(material, unreal.MaterialExpressionConstant, -400, y)
        constant.set_editor_property("r", value)
        edit.connect_material_property(constant, "", prop)
    edit.recompile_material(material)
    library.save_loaded_asset(material)
    _log(f"Created the master material {path} (BaseColor parameter, lambert-like: rough, no specular).")
    return material


def _instance(folder, name, master, rgb):
    library = unreal.EditorAssetLibrary
    path = f"{folder}/MI_{name}"
    if library.does_asset_exist(path):
        instance = library.load_asset(path)
    else:
        instance = _asset_tools().create_asset(f"MI_{name}", folder, unreal.MaterialInstanceConstant,
                                               unreal.MaterialInstanceConstantFactoryNew())
    edit = unreal.MaterialEditingLibrary
    edit.set_material_instance_parent(instance, master)
    edit.set_material_instance_vector_parameter_value(
        instance, COLOR_PARAMETER, unreal.LinearColor(float(rgb[0]), float(rgb[1]), float(rgb[2]), 1.0))
    edit.update_material_instance(instance)
    library.save_loaded_asset(instance)
    return instance


def _slot_name(slot):
    for prop in ("material_slot_name", "imported_material_slot_name"):
        try:
            value = str(slot.get_editor_property(prop))
        except Exception:
            continue
        if value and value != "None":
            return value
    return ""


def _match(records, slot_name):
    """Material record for a slot: exact name, then case-insensitive, then a
    slot name the importer suffixed (e.g. 'M_Body_001')."""
    lowered = slot_name.lower()
    for test in (lambda r: r["name"] == slot_name,
                 lambda r: r["name"].lower() == lowered,
                 lambda r: lowered.startswith(r["name"].lower())):
        found = [r for r in records if test(r)]
        if found:
            return max(found, key=lambda r: len(r["name"]))
    return None


def apply(skeletal_mesh, records):
    """Create/update the instances and assign them to the mesh slots."""
    records = [r for r in records or [] if r.get("color_unreal")]
    if skeletal_mesh is None or not records:
        return 0
    master = ensure_master()
    package = skeletal_mesh.get_path_name().split(".")[0]
    folder = package.rsplit("/", 1)[0] + "/Materials"
    slots = list(skeletal_mesh.get_editor_property("materials") or [])
    assigned, unmatched = [], []
    for slot in slots:
        name = _slot_name(slot)
        record = _match(records, name)
        if record is None:
            unmatched.append(name)
            continue
        slot.set_editor_property("material_interface", _instance(folder, record["name"], master, record["color_unreal"]))
        assigned.append(f"{name} -> MI_{record['name']}")
    skeletal_mesh.set_editor_property("materials", slots)
    unreal.EditorAssetLibrary.save_loaded_asset(skeletal_mesh)
    _log(f"Materials: {len(assigned)} slot(s) coloured from Maya ({', '.join(assigned[:8])}"
         f"{' ...' if len(assigned) > 8 else ''}).")
    if unmatched:
        _log(f"Materials: slot(s) with no Maya material of that name, left as imported: {', '.join(unmatched)}")
    for record in records:
        for problem in record.get("problems") or []:
            _log(f"Materials: {record['name']}: {problem}")
    return len(assigned)


def apply_after_build(assets, manifest):
    """Run after a build; never raises."""
    try:
        meshes = [a for a in assets or [] if a is not None and isinstance(a, unreal.SkeletalMesh)]
        if not meshes:
            _log("Materials: no skeletal mesh found next to the rig; skipped.")
            return 0
        return apply(meshes[0], (manifest or {}).get("materials"))
    except Exception as exc:
        _log(f"Materials could not be applied ({type(exc).__name__}: {exc}); the rig build is unaffected.")
        return 0
