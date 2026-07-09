# Handoff

## Current State

- The builder loads a source asset, reads metadata, detects `IKLimb` modules, and builds Control Rig content.
- The builder now also supports `FKChain` modules.
- `run_rig_builder.py` reloads local Python modules before each Unreal run.
- The builder recompiles and refreshes the Control Rig editor for UE5.6.
- Existing controls are updated instead of being left fully stale across reruns.
- A first module contract is now defined in `docs/module-contract.md` and reflected in `RigModule` / `IKModule`.
- Naming conventions are documented in `docs/naming-conventions.md`.

## Recent UE5.6 Findings

- Control Rig editor preview instances can stay stale unless the rig is reinitialized and the editor is refreshed.
- Unreal Python caches imported modules across runs, so reloads are needed during active iteration.
- Recipe values may require Blueprint/default-object resolution and flexible property lookup.

## Next Recommended Check

- Re-run the builder in Unreal and confirm the printed `recipe` block resolves real values from the recipe asset.
- Add an `FKChain` module to the test skeleton metadata and verify `IKLimb` and `FKChain` can build in the same rig.

## How To Use These Files

- Update `project-brief.md` when the project direction changes.
- Update `roadmap.md` when priorities change.
- Update `handoff.md` at the end of a work session with the last verified state and next step.