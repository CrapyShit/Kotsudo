# Module Contract

## Purpose

- Define the common interface every rig module must follow.
- Keep `FK`, `IKLimb`, `IK / FK`, and future modules compatible with the same builder and future module compiler.
- Standardize what a module receives, validates, builds, and returns.

## Module Definition Input

Each detected module passed into the builder should follow this shape:

```python
{
    "module_type": str,
    "module_name": str,
    "chain": list[str],
}
```

Optional future fields can be added without breaking the contract:

```python
{
    "metadata": dict,
    "connections": dict,
    "namespace": str,
}
```

## Required Module Class Interface

Each module class should provide:

- `module_type`: canonical module type string used by the builder registry.
- `describe_contract()`: class method returning the module contract definition.
- `validate()`: checks chain length, metadata assumptions, recipe assumptions, and context requirements.
- `read_recipe()`: resolves the recipe object into plain runtime values.
- `build()`: generates hierarchy elements and graph nodes, then returns a standardized build result.

## Standard Contract Shape

`describe_contract()` should return a dictionary with these keys:

```python
{
    "module_type": str,
    "chain": {
        "min_length": int | None,
        "max_length": int | None,
        "exact_length": int | None,
        "roles": list[str],
    },
    "required_metadata": list[str],
    "required_recipe_fields": list[str],
    "attachment_points": list[str],
    "build_products": list[str],
}
```

## Standard Build Result

Every module `build()` should return this shape:

```python
{
    "module_name": str,
    "module_type": str,
    "chain": list[str],
    "controls": list[str],
    "nodes": list[str],
    "attach_points": dict[str, str],
    "outputs": dict,
    "recipe": dict,
    "metadata": dict,
}
```

## Attachment Point Rules

- `attach_points` are the stable names the future module compiler will use.
- Attachment points should refer to semantic anchors, not implementation details.
- Examples: `root`, `mid`, `tip`, `effector`, `pole_vector`, `fk_root_ctrl`, `fk_tip_ctrl`.
- Module-specific node names can change later, but semantic attachment point names should stay stable.

## Validation Rules

Every module should fail early when:

- the chain shape is invalid,
- required recipe fields are missing,
- required hierarchy elements do not exist,
- expected metadata is missing or ambiguous,
- generated control or node naming would collide in an invalid way.

## IKLimb Contract

Current `IKLimb` should follow this contract:

```python
{
    "module_type": "IKLimb",
    "chain": {
        "min_length": 3,
        "max_length": 3,
        "exact_length": 3,
        "roles": ["Start", "Mid", "End"],
    },
    "required_metadata": ["ModuleType", "ModuleName", "Role"],
    "required_recipe_fields": ["SolverType", "NumControls", "CreatePoleVector"],
    "attachment_points": ["root", "mid", "tip", "effector", "pole_vector"],
    "build_products": ["controls", "nodes", "attach_points"],
}
```

## FKChain Contract

Current `FKChain` should follow this contract:

```python
{
    "module_type": "FKChain",
    "chain": {
        "min_length": 1,
        "max_length": None,
        "exact_length": None,
        "roles": ["Start", "Mid", "End"],
    },
    "required_metadata": ["ModuleType", "ModuleName"],
    "required_recipe_fields": [],
    "attachment_points": ["root", "tip", "fk_root_ctrl", "fk_tip_ctrl"],
    "build_products": ["controls", "nodes", "attach_points"],
}
```

## Why This Matters Before FK

- `FK` should be built against the same return shape as `IKLimb`.
- `IK / FK` switching will need stable semantic outputs from both modules.
- The module compiler will only work cleanly if attach points and build products are standardized first.