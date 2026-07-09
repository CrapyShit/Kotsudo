# Naming Conventions

## Module Types

- Use `PascalCase`.
- Keep names structural and reusable.
- Examples: `IKLimb`, `FKChain`, `IKFKLimb`, `SplineSpine`.

## Module Names

- Use unique semantic instance names per rig.
- Prefer body-region naming plus side suffix.
- Examples: `arm_L`, `arm_R`, `leg_L`, `spine_C`.

## Recipe Fields

- Use `PascalCase` for canonical field names.
- Examples: `ModuleType`, `SolverType`, `NumControls`, `CreatePoleVector`, `ControlShape`, `ControlScale`.

## Attachment Points

- Use lowercase semantic names.
- Examples: `root`, `mid`, `tip`, `effector`, `pole_vector`, `fk_root_ctrl`, `fk_tip_ctrl`.

## Rule Of Thumb

- Use `module_type` for builder behavior and contract shape.
- Use `module_name` for the unique instance inside a specific rig.
- Use recipe fields for variants inside the same `module_type`.