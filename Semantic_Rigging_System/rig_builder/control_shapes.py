"""Resolve Maya controller shapes into Unreal Control Rig control shapes.

The Maya exporter stores each controller's curve as polylines (Unreal axes,
centimetres, centred on the controller origin, in WORLD orientation) plus a
coarse descriptor. Two strategies are tried, best first:

1. Custom mesh -- the polylines are turned into a thin tube mesh, saved as a
   StaticMesh asset, registered in a project shape library and referenced by
   name. This reproduces the exact Maya curve.
2. Built-in shape -- the descriptor's kind (circle / rectangle / box / sphere)
   picks a stock library shape, oriented and scaled to the measured extents.

If neither can be produced the caller keeps its default shape, so a missing
capability in the running engine build never breaks a rig build. Every
failure is logged once with its reason.

Because exported points are world-oriented while a control's own frame is the
bone frame, the shape transform's rotation is always the inverse of the
control's rotation: the control rotates, the shape does not.
"""

import math
from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)

# Exact shapes via the shapes FBX exported from Maya (see prepare_shape_library).
ENABLE_FBX_SHAPES = True

# Experimental in-Python mesh builder. OFF: an earlier version used a bare
# ``unreal.StaticMeshDescription()`` and hard-crashed the editor (null pointer
# in StaticMeshDescription.dll, EXCEPTION_ACCESS_VIOLATION 0x38 -- try/except
# cannot catch that). The code now uses StaticMesh.create_static_mesh_description
# but it is unverified in this project, so it stays opt-in.
ENABLE_CUSTOM_SHAPE_MESHES = False

SHAPE_ROOT = "/Game/RigBuilder/Shapes"
LIBRARY_NAME = "RigBuilder_ShapeLibrary"
DEFAULT_LIBRARY_PATH = "/ControlRig/Controls/DefaultControlShapeLibrary.DefaultControlShapeLibrary"

# Stock shape name per descriptor kind (first available wins).
_BUILTIN_BY_KIND = {
    "circle": ("Circle_Thick", "Circle_Thin"),
    "rectangle": ("Square_Thick", "Quad_Thick", "Box_Thick"),
    "box": ("Box_Thick", "Box_Thin"),
    "sphere": ("Sphere_Thick", "Sphere_Solid"),
}

_custom_cache = {}          # shape_id -> shape name or None
_custom_disabled_reason = None
_warned = set()


def _log(message):
    if unreal is not None and hasattr(unreal, "log"):
        unreal.log(f"[RigBuilder] {message}")


def _warn_once(key, message):
    if key in _warned:
        return
    _warned.add(key)
    if unreal is not None and hasattr(unreal, "log_warning"):
        unreal.log_warning(f"[RigBuilder] {message}")


# ---------------------------------------------------------------------------
# Small math helpers (kept local so this module has no dependency on
# graph_utils and can be imported first).
# ---------------------------------------------------------------------------

def _vec(values):
    return unreal.Vector(float(values[0]), float(values[1]), float(values[2]))


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _normalise(v):
    length = math.sqrt(_dot(v, v))
    if length < 1e-9:
        return (0.0, 0.0, 0.0)
    return (v[0] / length, v[1] / length, v[2] / length)


def quat_from_basis(x_axis, y_axis, z_axis):
    """Quaternion for a right-handed basis given as three unit vectors."""
    m00, m10, m20 = x_axis
    m01, m11, m21 = y_axis
    m02, m12, m22 = z_axis
    trace = m00 + m11 + m22
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        w, x, y, z = 0.25 * s, (m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s
    elif m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2.0
        w, x, y, z = (m21 - m12) / s, 0.25 * s, (m01 + m10) / s, (m02 + m20) / s
    elif m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2.0
        w, x, y, z = (m02 - m20) / s, (m01 + m10) / s, 0.25 * s, (m12 + m21) / s
    else:
        s = math.sqrt(1.0 + m22 - m00 - m11) * 2.0
        w, x, y, z = (m10 - m01) / s, (m02 + m20) / s, (m12 + m21) / s, 0.25 * s
    quat = unreal.Quat(x, y, z, w)
    if hasattr(quat, "normalize"):
        quat.normalize()
    return quat


def _inverse(quat):
    return quat.inversed() if hasattr(quat, "inversed") else quat


def _multiply(a, b):
    """Hamilton product a * b (rotation b applied first, then a)."""
    ax, ay, az, aw = float(a.x), float(a.y), float(a.z), float(a.w)
    bx, by, bz, bw = float(b.x), float(b.y), float(b.z), float(b.w)
    result = unreal.Quat(
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )
    if hasattr(result, "normalize"):
        result.normalize()
    return result


# ---------------------------------------------------------------------------
# Strategy 1: custom mesh
# ---------------------------------------------------------------------------

def _tube_geometry(strands, radius):
    """Triangulate polylines as thin 3-sided tubes.

    Returns (positions, triangles) with triangles as index triples.
    """
    positions, triangles = [], []
    for strand in strands:
        points = [tuple(p) for p in strand.get("points", [])]
        if strand.get("closed") and len(points) > 2 and points[0] != points[-1]:
            points.append(points[0])
        for a, b in zip(points[:-1], points[1:]):
            direction = _normalise(_sub(b, a))
            if direction == (0.0, 0.0, 0.0):
                continue
            helper = (0.0, 0.0, 1.0) if abs(direction[2]) < 0.9 else (1.0, 0.0, 0.0)
            side = _normalise(_cross(direction, helper))
            up = _cross(direction, side)
            ring = []
            for k in range(3):
                angle = 2.0 * math.pi * k / 3.0
                offset = tuple(
                    radius * (math.cos(angle) * side[i] + math.sin(angle) * up[i])
                    for i in range(3)
                )
                ring.append(offset)
            base = len(positions)
            for end in (a, b):
                for offset in ring:
                    positions.append((end[0] + offset[0], end[1] + offset[1], end[2] + offset[2]))
            for k in range(3):
                k2 = (k + 1) % 3
                triangles.append((base + k, base + k2, base + 3 + k))
                triangles.append((base + k2, base + 3 + k2, base + 3 + k))
    return positions, triangles


def _create_static_mesh_asset(name):
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    path = f"{SHAPE_ROOT}/{name}"
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        return unreal.EditorAssetLibrary.load_asset(path)

    errors = []
    factories = []
    if hasattr(unreal, "StaticMeshFactory"):
        factories.append(unreal.StaticMeshFactory())
    factories.append(None)
    for factory in factories:
        try:
            asset = tools.create_asset(name, SHAPE_ROOT, unreal.StaticMesh, factory)
            if asset:
                return asset
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError("could not create a StaticMesh asset (" + "; ".join(errors) + ")")


def _build_static_mesh(name, strands):
    all_points = [p for strand in strands for p in strand.get("points", [])]
    if not all_points:
        raise RuntimeError("shape has no points")
    lows = [min(p[i] for p in all_points) for i in range(3)]
    highs = [max(p[i] for p in all_points) for i in range(3)]
    diagonal = math.sqrt(sum((highs[i] - lows[i]) ** 2 for i in range(3)))
    radius = max(diagonal * 0.012, 0.15)

    positions, triangles = _tube_geometry(strands, radius)
    if not triangles:
        raise RuntimeError("shape produced no geometry")

    mesh = _create_static_mesh_asset(name)
    # NEVER build a description with a bare ``unreal.StaticMeshDescription()``:
    # its attributes are unregistered and the first vertex call dereferences a
    # null pointer (hard editor crash, see the 0x38 access violation in
    # Saved/Logs). The engine's factory function registers them, and takes the
    # mesh as outer.
    description = unreal.StaticMesh.create_static_mesh_description(mesh)
    if description is None:
        raise RuntimeError("StaticMesh.create_static_mesh_description returned None")

    polygon_group = description.create_polygon_group()
    vertex_ids = []
    for position in positions:
        vertex_id = description.create_vertex()
        description.set_vertex_position(vertex_id, _vec(position))
        vertex_ids.append(vertex_id)
    for a, b, c in triangles:
        instances = [description.create_vertex_instance(vertex_ids[i]) for i in (a, b, c)]
        description.create_triangle(polygon_group, instances)

    mesh.build_from_static_mesh_descriptions([description], False, True)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)
    return mesh


def _get_or_create_library():
    path = f"{SHAPE_ROOT}/{LIBRARY_NAME}"
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        return unreal.EditorAssetLibrary.load_asset(path)

    tools = unreal.AssetToolsHelpers.get_asset_tools()
    factory = None
    if hasattr(unreal, "ControlRigShapeLibraryFactory"):
        factory = unreal.ControlRigShapeLibraryFactory()
    else:
        try:
            factory_class = unreal.load_class(
                None, "/Script/ControlRigEditor.ControlRigShapeLibraryFactory"
            )
            factory = unreal.new_object(factory_class)
        except Exception:
            factory = None
    library = tools.create_asset(LIBRARY_NAME, SHAPE_ROOT, unreal.ControlRigShapeLibrary, factory)
    if not library:
        raise RuntimeError("could not create the ControlRigShapeLibrary asset")
    return library


def _register_shapes(rig, meshes_by_name):
    """Add {shape_name: static_mesh} to the project library and attach it."""
    library = _get_or_create_library()

    # A factory-made library has no materials of its own; borrow the stock
    # library's so shapes render like the built-in ones.
    try:
        stock = unreal.load_asset(DEFAULT_LIBRARY_PATH)
        for prop in ("default_material", "x_ray_material", "material_color_parameter"):
            if library.get_editor_property(prop) is None or str(library.get_editor_property(prop)) in ("None", ""):
                library.set_editor_property(prop, stock.get_editor_property(prop))
    except Exception:
        pass

    shapes = list(library.get_editor_property("shapes") or [])
    known = {str(s.get_editor_property("shape_name")) for s in shapes}
    for shape_name, mesh in meshes_by_name.items():
        if shape_name in known:
            for definition in shapes:
                if str(definition.get_editor_property("shape_name")) == shape_name:
                    definition.set_editor_property("static_mesh", mesh)
            continue
        definition = unreal.ControlRigShapeDefinition()
        definition.set_editor_property("shape_name", shape_name)
        definition.set_editor_property("static_mesh", mesh)
        definition.set_editor_property("transform", unreal.Transform())
        shapes.append(definition)
    library.set_editor_property("shapes", shapes)
    unreal.EditorAssetLibrary.save_loaded_asset(library)

    # Make the rig look the library up (shape_libraries is a plain array of
    # ControlRigShapeLibrary; the stock library stays in it).
    try:
        libraries = list(rig.get_editor_property("shape_libraries") or [])
        if not any(item is not None and item.get_path_name() == library.get_path_name() for item in libraries):
            libraries.append(library)
            rig.set_editor_property("shape_libraries", libraries)
    except Exception as exc:
        _warn_once(
            "shape-libraries",
            f"Could not attach the shape library to the rig ({exc}); add "
            f"'{SHAPE_ROOT}/{LIBRARY_NAME}' to the rig's Shape Libraries manually.",
        )


# ---------------------------------------------------------------------------
# Strategy 1 (default): import the exact shapes exported from Maya
#
# The Maya exporter writes a folder <name>_shapes/ next to the rig FBX with one
# FBX per distinct controller shape, RB_<shape_id>.fbx: a tube mesh around the
# Maya curve, centred on the controller origin, in Maya axes. Each is imported
# as a static mesh (the documented workflow for custom control shapes: static
# meshes listed in a Control Rig shape library), converted by the importer
# exactly like the skeleton.
#
# One file per shape is deliberate: UE 5.6 imports FBX through Interchange,
# which ignores the legacy FbxImportUI options and merges all meshes of a file
# into ONE static mesh named after the file.
# ---------------------------------------------------------------------------

SHAPE_PREFIX = "RB_"
# Extra folders searched for the shapes folder (besides the rig FBX's own
# folder, the repository's FBXs folder, and RIG_SHAPES_DIR).
SHAPE_SEARCH_DIRS = []

_registered = {}    # shape_id -> shape name usable as control_settings.shape_name


def _project_fbx_dir():
    import os
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "FBXs")


def _source_directories(assets):
    """Folders the rig FBX was imported from, read from the assets' import data."""
    import os
    directories = []
    for asset in assets:
        if asset is None:
            continue
        try:
            data = asset.get_editor_property("asset_import_data")
        except Exception:
            data = None
        if data is None:
            continue
        filenames = []
        for getter in ("extract_filenames", "get_first_filename"):
            try:
                value = getattr(data, getter)()
                filenames.extend(value if isinstance(value, (list, tuple)) else [value])
            except Exception:
                continue
        for filename in filenames:
            if filename:
                directories.append(os.path.dirname(str(filename)))
    return directories


def _search_directories(assets):
    import os
    directories = _source_directories(assets) + list(SHAPE_SEARCH_DIRS)
    if os.environ.get("RIG_SHAPES_DIR"):
        directories.append(os.environ["RIG_SHAPES_DIR"])
    directories.append(_project_fbx_dir())
    unique = []
    for directory in directories:
        if directory and directory not in unique:
            unique.append(directory)
    return unique


def find_shape_file(assets, shapes_dir_name, shape_id):
    """Path of RB_<shape_id>.fbx, or None.

    Looked for in <dir>/<shapes_dir_name>/, then any <dir>/*_shapes/, then
    <dir>/ itself, for each search directory.
    """
    import glob
    import os

    filename = f"{SHAPE_PREFIX}{shape_id}.fbx"
    for directory in _search_directories(assets):
        candidates = []
        if shapes_dir_name:
            candidates.append(os.path.join(directory, shapes_dir_name))
        candidates += sorted(glob.glob(os.path.join(directory, "*_shapes")),
                             key=os.path.getmtime, reverse=True)
        candidates.append(directory)
        for folder in candidates:
            path = os.path.join(folder, filename)
            if os.path.isfile(path):
                return path
    return None


def _shape_asset_path(shape_id):
    return f"{SHAPE_ROOT}/{SHAPE_PREFIX}{shape_id}"


def _missing_shapes(shape_ids):
    return [s for s in shape_ids if not unreal.EditorAssetLibrary.does_asset_exist(_shape_asset_path(s))]


def _package_path(object_path):
    return str(object_path).split(".")[0]


def _import_shape_file(fbx_path, shape_id):
    """Import one shape FBX and make sure it lands at RB_<shape_id>. Returns bool."""
    expected = _shape_asset_path(shape_id)
    tools = unreal.AssetToolsHelpers.get_asset_tools()

    task = unreal.AssetImportTask()
    task.set_editor_property("filename", fbx_path)
    task.set_editor_property("destination_path", SHAPE_ROOT)
    task.set_editor_property("destination_name", f"{SHAPE_PREFIX}{shape_id}")
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", True)
    tools.import_asset_tasks([task])

    if unreal.EditorAssetLibrary.does_asset_exist(expected):
        return True

    # The importer chose another name (Interchange may name the asset after
    # the mesh node or the file): rename the imported static mesh into place.
    try:
        imported = list(task.get_editor_property("imported_object_paths") or [])
    except Exception:
        imported = []
    for object_path in imported:
        asset = unreal.EditorAssetLibrary.load_asset(object_path)
        if isinstance(asset, unreal.StaticMesh):
            if unreal.EditorAssetLibrary.rename_asset(_package_path(object_path), expected):
                return True
    return unreal.EditorAssetLibrary.does_asset_exist(expected)


def prepare_shape_library(rig, assets, shape_ids, shapes_dir_name=None):
    """Make the exported controller shapes available as Control Rig shapes.

    Imports missing shape meshes, registers them in the project shape library
    and attaches it to the rig. Returns the number of shapes now available.
    Never raises: on any problem the rig still builds with built-in shapes.
    """
    _registered.clear()
    shape_ids = sorted(set(shape_ids or []))
    if not shape_ids or not ENABLE_FBX_SHAPES:
        return 0
    try:
        unreal.EditorAssetLibrary.make_directory(SHAPE_ROOT)
        missing = _missing_shapes(shape_ids)
        not_found, failed = [], []
        for shape_id in missing:
            path = find_shape_file(assets, shapes_dir_name, shape_id)
            if not path:
                not_found.append(shape_id)
                continue
            try:
                if not _import_shape_file(path, shape_id):
                    failed.append(shape_id)
            except Exception as exc:
                failed.append(f"{shape_id} ({exc})")
        if missing:
            _log(f"Imported {len(missing) - len(not_found) - len(failed)}/{len(missing)} new control shape(s).")
        if not_found:
            _warn_once(
                "shape-fbx",
                f"{len(not_found)} shape file(s) RB_<id>.fbx not found (looked in "
                f"'{shapes_dir_name or '*_shapes'}' next to the rig FBX, in '{_project_fbx_dir()}' "
                "and RIG_SHAPES_DIR). Re-export from Maya; those controls use built-in shapes.",
            )
        if failed:
            _warn_once("shape-import", "Shape import failed for: " + ", ".join(failed))

        meshes = {}
        for shape_id in shape_ids:
            path = _shape_asset_path(shape_id)
            if unreal.EditorAssetLibrary.does_asset_exist(path):
                mesh = unreal.EditorAssetLibrary.load_asset(path)
                if isinstance(mesh, unreal.StaticMesh):
                    meshes[f"{SHAPE_PREFIX}{shape_id}"] = mesh
        if not meshes:
            return 0
        _register_shapes(rig, meshes)
        for shape_id in shape_ids:
            if f"{SHAPE_PREFIX}{shape_id}" in meshes:
                _registered[shape_id] = f"{SHAPE_PREFIX}{shape_id}"
        _log(f"{len(_registered)}/{len(shape_ids)} control shape(s) registered in {SHAPE_ROOT}/{LIBRARY_NAME}.")
        return len(_registered)
    except Exception as exc:
        _warn_once("shape-library", f"Control shape library setup failed ({exc}); using built-in shapes.")
        return 0


def builtin_scale_for_size(shape_name, size, fallback_scale):
    """Uniform shape scale making a stock shape as big as a Maya controller.

    ``size`` is the controller's world bounding-box size in cm (exported as
    ``size_unreal``); the largest dimension is matched against the stock
    mesh's bounds. Returns ``fallback_scale`` when either is unknown.
    """
    try:
        target = max(float(c) for c in (size or []))
    except ValueError:
        target = 0.0
    measured = _builtin_half_extent(shape_name)
    if target <= 1e-6 or not measured or max(measured) <= 1e-6:
        return fallback_scale
    uniform = (target * 0.5) / max(measured)
    return (uniform, uniform, uniform)


def pole_vector_shape():
    """Stock sphere shape for pole vectors (first one this engine ships)."""
    for name in ("Sphere_Thick", "Sphere_Solid", "Sphere_Thin", "Diamond_Thick"):
        if _builtin_shape_available(name):
            return name
    return "Sphere_Thick"


def ensure_custom_shape(rig, shape_id, shape_data):
    """Name of the exact imported shape for ``shape_id``, or None.

    Shapes come from ``prepare_shape_library``; the experimental in-Python mesh
    builder is used only when ENABLE_CUSTOM_SHAPE_MESHES is set.
    """
    if shape_id in _registered:
        return _registered[shape_id]

    global _custom_disabled_reason
    if not ENABLE_CUSTOM_SHAPE_MESHES or _custom_disabled_reason:
        return None
    if shape_id in _custom_cache:
        return _custom_cache[shape_id]
    name = f"{SHAPE_PREFIX}{shape_id}"
    try:
        mesh = _build_static_mesh(name, shape_data.get("strands") or [])
        _register_shapes(rig, {name: mesh})
        _custom_cache[shape_id] = name
        return name
    except Exception as exc:
        _custom_cache[shape_id] = None
        _custom_disabled_reason = str(exc)
        _warn_once("custom-shapes", f"In-Python shape mesh builder failed ({exc}).")
        return None


# ---------------------------------------------------------------------------
# Strategy 2: built-in fallback
# ---------------------------------------------------------------------------

def _builtin_shape_available(name):
    try:
        library = unreal.load_asset(DEFAULT_LIBRARY_PATH)
        shapes = library.get_editor_property("shapes") or []
        return any(str(s.get_editor_property("shape_name")) == name for s in shapes)
    except Exception:
        return True   # cannot inspect the library; assume stock names exist


def _builtin_half_extent(name):
    """Half-size of a stock shape's mesh (x, y, z), or None if unmeasurable."""
    try:
        library = unreal.load_asset(DEFAULT_LIBRARY_PATH)
        for definition in library.get_editor_property("shapes") or []:
            if str(definition.get_editor_property("shape_name")) == name:
                mesh = definition.get_editor_property("static_mesh")
                extent = mesh.get_bounds().box_extent
                return (float(extent.x), float(extent.y), float(extent.z))
    except Exception:
        pass
    return None


def _builtin_for_descriptor(descriptor, control_rotation, default_scale):
    """Return (name, rotation, scale) for a stock shape, or None."""
    kind = (descriptor or {}).get("kind")
    for candidate in _BUILTIN_BY_KIND.get(kind, ()):
        if _builtin_shape_available(candidate):
            name = candidate
            break
    else:
        return None

    axes = descriptor.get("object_axes_unreal") or []
    extents = descriptor.get("extents_object") or []
    if len(axes) != 3 or len(extents) != 3:
        return name, _inverse(control_rotation), default_scale

    planar = descriptor.get("planar_axis")
    if planar in ("x", "y", "z"):
        plane_index = "xyz".index(planar)
        in_plane = [i for i in range(3) if i != plane_index]
        z_axis = _normalise(axes[plane_index])
        x_axis = _normalise(axes[in_plane[0]])
        y_axis = _normalise(_cross(z_axis, x_axis))
        half = [extents[in_plane[0]] * 0.5, extents[in_plane[1]] * 0.5, max(extents) * 0.02]
    else:
        x_axis, y_axis, z_axis = (_normalise(a) for a in axes)
        half = [e * 0.5 for e in extents]

    shape_rotation = _multiply(_inverse(control_rotation), quat_from_basis(x_axis, y_axis, z_axis))
    measured = _builtin_half_extent(name)
    if measured:
        scale = tuple(
            (half[i] / measured[i]) if measured[i] > 1e-6 and half[i] > 1e-6 else default_scale[i]
            for i in range(3)
        )
    else:
        scale = default_scale
    return name, shape_rotation, scale


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def resolve_control_shape(rig, recipe_data, record, control_rotation, default_name,
                          default_scale, default_rotation=None):
    """Return (shape_name, shape_rotation, shape_scale) for a control.

    ``control_rotation`` is the control's global rotation (a Quat);
    ``default_*`` are used when the record has no shape or nothing can be
    built. ``default_scale`` is a 3-tuple.
    """
    fallback = (default_name, default_rotation, default_scale)
    if not record or not record.get("shape_id"):
        return fallback

    shapes = (recipe_data or {}).get("ShapeTable") or {}
    shape_data = shapes.get(record["shape_id"])
    if not shape_data:
        return fallback

    name = ensure_custom_shape(rig, record["shape_id"], shape_data)
    if name:
        return name, _inverse(control_rotation), (1.0, 1.0, 1.0)

    try:
        builtin = _builtin_for_descriptor(shape_data.get("descriptor"), control_rotation, default_scale)
    except Exception as exc:
        _warn_once("builtin-shape", f"Built-in shape fallback failed ({exc}); using the default shape.")
        builtin = None
    return builtin or fallback
