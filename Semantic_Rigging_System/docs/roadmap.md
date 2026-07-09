# Roadmap

## Milestones

- Milestone 1: build the `FK` module.
- Milestone 2: build the `IK / FK` switch workflow.
- Bigger milestone: build a module compiler that attaches modules together and resolves hierarchy connections between them.

## Foundation Requirements

- Define a formal module interface contract so every module exposes the same kind of inputs, outputs, controls, attach points, and dependencies.
- Define a connection metadata spec so modules can declare how they attach to other modules before the module compiler is implemented.
- Build a validation layer that catches invalid chains, missing metadata, incompatible connections, and naming conflicts before build execution.

## Now

- Stabilize the `IKLimb` module in UE5.6.
- Confirm recipe fields resolve correctly from the recipe asset.
- Make reruns reliable when controls and graph nodes already exist.
- Keep generated rig output valid after compile and editor refresh.

## After Current Fixes

- Start the `FK` module implementation.
- Define the minimum recipe and metadata contract for `FK` modules.
- Decide how `FK` and `IKLimb` modules will expose compatible connection points for later compilation.

## Next

- Build the `IK / FK` switch after `FK` is stable.
- Design the module compiler around hierarchy attachment rules, parent/child module relationships, and connection metadata.
- Expand the recipe schema beyond the initial IK settings.
- Improve validation and failure reporting.
- Separate detection, recipe resolution, and build execution more cleanly.

## Later

- Add more module types such as spine, foot, clavicle, hand, or twist helpers.
- Build a full reconstruction pass for larger rigs.
- Add repeatable validation or tests for metadata detection and module generation.
- Add tooling or UI to launch builder workflows from the editor.

## Open Questions

- What is the final recipe asset class strategy: native class, Blueprint-based data asset, or both?
- Should reruns update existing controls and nodes in place, or rebuild module content from scratch?
- What naming convention should be enforced for modules, controls, and recipe fields?
- What metadata or recipe fields will define how one module attaches to another?
- Will the module compiler connect modules only structurally, or also propagate settings such as spaces, controls, and switch logic?