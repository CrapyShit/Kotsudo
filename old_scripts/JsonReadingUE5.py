import unreal
import json
import os

# Make sure Control Rig editing API is available
unreal.load_module('ControlRigDeveloper')  # needed for Control Rig editing in UE5.6


# --------------------------------------------------------
# CONFIG – EDIT THESE PATHS FOR YOUR SETUP
# --------------------------------------------------------

# JSON exported from Maya (on your disk)
JSON_SOURCE_PATH = r"C:\Users\jeanf\Desktop\Kotsudo_test\test_rig.json"

# SkeletalMesh you imported manually in Unreal
# (Right-click the SkeletalMesh in Content Browser → Copy Reference, then keep only the /Game/... part)
SKELETAL_MESH_PATH = "/Game/KotsudoProject/test_rig"  # <-- CHANGE THIS

# Where to create/control the Control Rig Blueprint
DEST_CONTENT_PATH = "/Game/KotsudoProject"
CONTROL_RIG_NAME = "CR_KotsudoTest"


# --------------------------------------------------------
# SMALL HELPERS
# --------------------------------------------------------

def _log_header(title):
    unreal.log("\n" + "-" * 60)
    unreal.log(f"Kotsudo: {title}")
    unreal.log("-" * 60)


# --------------------------------------------------------
# STEP 1 – Load SkeletalMesh & Skeleton (manual import)
# --------------------------------------------------------

def kotsudo_get_skeletal_mesh():
    """
    Load the SkeletalMesh and Skeleton that you already imported manually
    into the Content Browser.
    """
    _log_header("STEP 1 – Get SkeletalMesh (manual import)")

    skm = unreal.load_asset(SKELETAL_MESH_PATH)
    if not skm:
        unreal.log_error(f"Could not load SkeletalMesh at {SKELETAL_MESH_PATH}")
        return None, None

    skeleton = skm.skeleton
    if not skeleton:
        unreal.log_error("SkeletalMesh has no Skeleton.")
        return None, None

    unreal.log(f"Loaded SkeletalMesh: {skm.get_path_name()}")
    unreal.log(f"Using Skeleton    : {skeleton.get_path_name()}")
    return skm, skeleton


# --------------------------------------------------------
# STEP 2 – Load JSON description exported from Maya
# --------------------------------------------------------

def kotsudo_load_json():
    """
    Load the JSON file exported from Maya (controller metadata, links, etc.).
    Expecting something like:

    {
        "nodes": [...],
        "controllers": [...],
        "controllerLinks": [
            { "controller": "world_ctrl", "joint": "Root_bind" },
            ...
        ]
    }
    """
    _log_header("STEP 2 – Load JSON")

    if not os.path.exists(JSON_SOURCE_PATH):
        unreal.log_error(f"JSON file not found: {JSON_SOURCE_PATH}")
        return None

    with open(JSON_SOURCE_PATH, "r") as f:
        data = json.load(f)

    nodes = data.get("nodes", [])
    links = data.get("controllerLinks", [])

    unreal.log(f"JSON loaded from {JSON_SOURCE_PATH}")
    unreal.log(f"  Nodes           : {len(nodes)}")
    unreal.log(f"  ControllerLinks : {len(links)}")

    for link in links:
        unreal.log(f"  - {link['controller']} -> {link['joint']}")

    return data


# --------------------------------------------------------
# STEP 3 – Create / get Control Rig for this skeleton
# --------------------------------------------------------

def kotsudo_get_or_create_control_rig(skeleton):
    """
    Returns a Control Rig asset for the project.

    NOTE (UE5.6):
      ControlRigBlueprintFactory no longer has a 'target_skeleton' property in Python,
      so we just create a generic Control Rig asset and then set its preview mesh
      after creation using ControlRigBlueprintLibrary.set_preview_mesh().
    """
    _log_header("STEP 3 – Get / Create Control Rig")

    rig_path = f"{DEST_CONTENT_PATH}/{CONTROL_RIG_NAME}"

    # If it already exists, just load it
    if unreal.EditorAssetLibrary.does_asset_exist(rig_path):
        rig = unreal.load_asset(rig_path)
        unreal.log(f"Found existing Control Rig: {rig_path}")
        return rig

    # Otherwise, create a new Control Rig Blueprint
    unreal.log(f"Creating new Control Rig: {rig_path}")

    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    rig_factory = unreal.ControlRigBlueprintFactory()

    rig = asset_tools.create_asset(
        asset_name=CONTROL_RIG_NAME,
        package_path=DEST_CONTENT_PATH,
        asset_class=unreal.ControlRigBlueprint,
        factory=rig_factory
    )

    unreal.log(f"Created Control Rig asset: {rig_path}")
    return rig


# --------------------------------------------------------
# STEP 4 – Construction: create controls from controllerLinks
# --------------------------------------------------------

def kotsudo_create_controls_from_links(rig, controller_links):
    """
    For each {controller, joint} link in JSON, create a control in the Control Rig hierarchy.

    This version is aligned with the UE5.6 Python API:

      * Uses RigControlType.EULER_TRANSFORM (no more TRANSFORM / TRANSFORM_CURVE).
      * Calls RigHierarchyController.add_control(name, parent, settings, value, ...)
        with positional arguments (the 5.6 API does NOT expose 'key=' or 'shape=' kwargs).
    """
    _log_header("STEP 4 – Create Controls From JSON")

    # For UE 5.6 it's recommended to go through the ControlRigBlueprintLibrary
    hierarchy = unreal.ControlRigBlueprintLibrary.get_hierarchy(rig)
    if not hierarchy:
        unreal.log_error("Control Rig has no hierarchy.")
        return

    hierarchy_controller = unreal.ControlRigBlueprintLibrary.get_hierarchy_controller(rig)

    for link in controller_links:
        ctrl_name = link["controller"]
        joint_name = link["joint"]

        unreal.log(f"Creating control '{ctrl_name}' for joint '{joint_name}'")

        control_key = unreal.RigElementKey(
            type=unreal.RigElementType.CONTROL,
            name=ctrl_name
        )

        # Skip if control already exists (so you can re-run the script)
        if hierarchy.contains(control_key):
            unreal.log(f"  - Control '{ctrl_name}' already exists, skipping.")
            continue

        # Basic settings: full TRS control (translation + rotation + scale)
        settings = unreal.RigControlSettings()
        settings.control_type = unreal.RigControlType.EULER_TRANSFORM  # full transform in UE5.6
        settings.display_name = ctrl_name

        # Default value (identity transform; we'll place it later if we want)
        default_value = unreal.RigControlValue()

        # Parent: None / root for now. Later you can use a bone key if you
        # populate the hierarchy with bones that match 'joint_name'.
        parent_key = unreal.RigElementKey()  # empty -> root

        # UE5.6 signature:
        #   add_control(name, parent, settings, value, setup_undo=True, print_python_command=False)
        hierarchy_controller.add_control(
            ctrl_name,
            parent_key,
            settings,
            default_value,
            True,
            False
        )

    unreal.log("Finished creating controls. Open the Control Rig asset to see them.")


# --------------------------------------------------------
# MAIN ENTRYPOINT – one call builds everything
# --------------------------------------------------------

def kotsudo_build_all():
    """
    1) Load SkeletalMesh & Skeleton (FBX is imported manually)
    2) Load JSON rig description
    3) Create / get Control Rig bound to skeleton
    4) Construct controls from JSON controllerLinks
    """
    _log_header("KOTsudo BUILD ALL")

    skm, skeleton = kotsudo_get_skeletal_mesh()
    if not skm or not skeleton:
        unreal.log_error("Stopping: could not get SkeletalMesh/Skeleton.")
        return

    data = kotsudo_load_json()
    if not data:
        unreal.log_error("Stopping: JSON load failed.")
        return

    rig = kotsudo_get_or_create_control_rig(skeleton)
    if not rig:
        unreal.log_error("Stopping: could not create / load Control Rig.")
        return

    # Set preview mesh so the rig knows which SkeletalMesh it drives (UE5.6 way)
    try:
        unreal.ControlRigBlueprintLibrary.set_preview_mesh(rig, skm, True)
    except Exception as e:
        unreal.log_warning(f"Could not set preview mesh on Control Rig: {e}")

    controller_links = data.get("controllerLinks", [])
    if not controller_links:
        unreal.log_warning("JSON has no controllerLinks – nothing to build.")
    else:
        kotsudo_create_controls_from_links(rig, controller_links)

    unreal.log(
        "\nKotsudo: BUILD ALL finished.\n"
        "  - SkeletalMesh : {}\n"
        "  - Skeleton     : {}\n"
        "  - Control Rig  : {}\n".format(
            skm.get_path_name(),
            skeleton.get_path_name(),
            rig.get_path_name()
        )
    )


def run():
    """Convenience entrypoint (used at bottom)."""
    kotsudo_build_all()


# --------------------------------------------------------
# AUTO-RUN WHEN SENT FROM VSCODE → UE
# --------------------------------------------------------

run()
