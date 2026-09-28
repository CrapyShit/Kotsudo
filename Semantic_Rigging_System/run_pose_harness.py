"""Pose-match harness entry point (run inside Unreal, after run_rig_builder.py).

Replays the Maya test poses (<name>.poses.json, written by the Maya export next
to the FBX) on the open Control Rig and writes <name>.harness_report.json next
to the poses file, with a summary in the Output Log. See
rig_builder/pose_harness.py for the method.
"""

import importlib
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
for name in [m for m in list(sys.modules) if m == "rig_builder" or m.startswith("rig_builder.")]:
    del sys.modules[name]
importlib.invalidate_caches()

import unreal  # noqa: E402

from rig_builder import manifest_schema, pose_harness  # noqa: E402
from rig_builder.builder import RigBuilder  # noqa: E402
from rig_builder.metadata_reader import get_asset_metadata, read_manifest_document  # noqa: E402

CONTROL_RIG_PATH = None     # None = the open Control Rig
SOURCE_ASSET_PATH = None    # None = derived from the rig's preview mesh, as in run_rig_builder
POSES_PATH = None           # None = found next to the imported FBX (manifest "poses_file")


def main():
    unreal.load_module("ControlRigDeveloper")
    if CONTROL_RIG_PATH:
        rig = unreal.EditorAssetLibrary.load_asset(CONTROL_RIG_PATH)
    else:
        rigs = unreal.ControlRigBlueprint.get_currently_open_rig_blueprints()
        if not rigs:
            raise RuntimeError("No Control Rig Blueprint is open. Open one or set CONTROL_RIG_PATH.")
        rig = rigs[0]

    builder = RigBuilder(source_asset_path=SOURCE_ASSET_PATH, rig=rig)
    source = builder.load_source_asset()
    skeleton = builder.resolve_skeleton(source)
    mesh = source if isinstance(source, unreal.SkeletalMesh) else None
    metadata = {}
    metadata.update(get_asset_metadata(mesh))
    metadata.update(get_asset_metadata(skeleton))
    manifest = read_manifest_document(metadata)
    if manifest is not None:
        manifest, _notes = manifest_schema.migrate(manifest)

    poses_path = POSES_PATH or pose_harness.find_poses_file(
        [mesh, skeleton, rig.get_preview_mesh() if hasattr(rig, "get_preview_mesh") else None],
        (manifest or {}).get("poses_file"),
    )
    if not poses_path:
        raise RuntimeError(
            "No <name>.poses.json found next to the imported FBX or in the repo's FBXs folder. "
            "Re-export from Maya (the export writes it), or set POSES_PATH."
        )
    pose_harness.run(rig, poses_path, manifest=manifest)


if __name__ == "__main__":
    main()
