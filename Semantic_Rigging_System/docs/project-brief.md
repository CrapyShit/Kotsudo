# Semantic Rigging System

## Goal

- Build a metadata-driven, recipe-based Control Rig construction system for Unreal Engine 5.6.
- Use skeletal metadata plus recipe assets to reconstruct rig modules automatically.
- Grow from isolated module generation into a reusable builder for larger rig reconstruction.

## Current Direction

- `RigBuilder` is the orchestration layer.
- `metadata_reader` detects modules from bone metadata.
- `graph_utils` owns Control Rig hierarchy and graph helper logic.
- `rig_builder/modules` contains module implementations.
- `IKLimb` is the first working module type.

## Current Scope

- Source asset loading from skeleton or skeletal mesh.
- Metadata parsing for `ModuleType`, `ModuleName`, and `Role`.
- Module detection and module instantiation.
- Control Rig graph/control generation for IK limbs.
- Recipe asset hookup for module-specific settings.

## Working Assumption

- The project is heading toward semantic rig reconstruction: a system that reads structure and meaning from assets, then builds the matching Control Rig automatically.