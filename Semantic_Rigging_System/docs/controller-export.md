# Controller export (manifest schema v5)

Maya animator controllers are carried to Unreal Control Rig with their
**origin, shape, attributes and system data**. Everything is optional: a rig
without controller data builds exactly as before.

## What is exported (Maya, `tools/maya/export_rig_manifest.py`)

Each controller snapshot (`bone_controllers[bone][]`, and the records embedded
in `params.spline` / `params.switch`) gains:

| field | meaning |
|---|---|
| `origin_source` | `rotate_pivot` (default) or `bounding_box_center` when the pivot lies outside the curve (frozen control with pivot at world origin) |
| `offset_from_anchor_unreal` | controller origin minus its anchor bone, already in Unreal axes / cm. A displacement, so root/offset/scale differences cannot skew it |
| `reference` | anchor -> neighbouring bone vector, same mapping. Unreal uses it to verify the mapping and correct a pure unit-scale difference |
| `shape_id` | key into the top-level `control_shapes` table (identical shapes stored once) |
| `attributes` | user-defined keyable attributes: type, value, default, min/max, enum labels |

`control_shapes[shape_id]` = `{strands: [{points, closed}], descriptor}`.
Points are world-oriented, centred on the controller origin, Unreal axes, cm.
`descriptor` = `{kind, planar_axis, extents_object, object_axes_unreal}` for the
built-in fallback.

Module `params` additions:

* `IKFKSwitch.params.switch` -- `control` (record), `attribute`, `attribute_info`,
  `ik_value` / `fk_value` (which attribute value means fully IK / FK, read from
  enum labels, else from the blend node wiring), `default_ik_weight`.
* `SplineIK.params.spline` -- the exact controllers driving the curve (ordered
  along it), the curve's CVs, and each CV's per-control weights.

## What Unreal does (`rig_builder/`)

* `graph_utils.controller_origin_position` -- anchor bone position + offset,
  after validating against the imported skeleton. Returns `None` (control stays
  on the bone) when the mapping disagrees by more than 10 degrees.
* `graph_utils.build_record_control` -- one call per bone: control at the Maya
  origin, driver null carrying the bone transform (the graph reads the null),
  resolved shape, attribute controls.
* Controller shapes (the community workflow: shapes are static meshes listed in
  a Control Rig shape library):
  1. **Maya** builds a square-section tube mesh per distinct shape
     (`RB_<shape_id>`, centred on the controller origin, Maya axes) and exports
     each to its own file, `<name>_shapes/RB_<shape_id>.fbx`, next to the rig
     FBX; the manifest records `shapes_dir`. One file per shape because UE 5.6's
     Interchange importer ignores the legacy FbxImportUI options and merges all
     meshes of a file into one asset named after the file.
  2. **Unreal** (`control_shapes.prepare_shape_library`, called by the builder
     before any control is made) finds each file (rig FBX's folder, the repo's
     `FBXs`, `RIG_SHAPES_DIR`), imports it into `/Game/RigBuilder/Shapes`
     (renaming the imported static mesh to `RB_<shape_id>` if the importer
     picked another name), registers the meshes in
     `RigBuilder_ShapeLibrary` and appends that library to the rig's
     `shape_libraries`. The importer converts the meshes exactly like the
     skeleton. Shape ids are content hashes, so assets are re-imported only when
     a shape changes.
  3. `resolve_control_shape` uses the exact shape (shape rotation = inverse of
     the control's rotation, scale 1), else a built-in shape sized from the
     descriptor, else the module's default.
  The in-Python mesh builder (`ENABLE_CUSTOM_SHAPE_MESHES`) stays off: a bare
  `unreal.StaticMeshDescription()` crashes the editor; only
  `StaticMesh.create_static_mesh_description(outer)` is safe.
* Attributes become FLOAT controls (Maya range and value; enums keep 0..N-1).
* IKFK: the switch attribute's control feeds the FK/IK lerp alpha. When IK is
  attribute value 0 (Maya enum `IK:FK`) the lerp inputs are swapped so the
  animator's numbers keep their Maya meaning. A range other than 0..1 becomes a
  0..1 IK-weight slider. Without switch data the old rig variable is used.
* SplineIK: one UE control per Maya controller, at its exact place. Each Maya
  CV becomes a null riding on its influencing control(s) (a vector lerp when two
  controls share it); those feed *Spline From Points*, so 3 controls can drive a
  4-point native spline. Without data: evenly spaced controls as before.
* Pole vectors: exact position via the same anchor offset (IKLimb and IKFK).

## Naming, attributes, constraints (schema v5, later additions)

* **Coordinate mapping.** Maya Y-up -> Unreal is `(X, Z, Y)`: the FBX importer
  turns the scene Z-up, then flips Y (right- to left-handed). It must be a
  reflection; the earlier `(X, -Z, Y)` mirrored front/back offsets (poles in
  front of the character). Orientations are converted by conjugation: UE
  axes = [P(Maya X), P(Maya Z), P(Maya Y)] (`world_axes_unreal`).
* **Names.** Controls take the Maya controller's name (`RigContext.control_name`);
  a semantic name (`<Module>_IK_CTRL`...) is used only when the Maya short name
  is missing or used by two different controllers.
* **Attributes -> animation channels.** Each keyable user attribute becomes an
  animation channel under its control (select the control; the channel is in
  the Details panel, Anim Outliner and Sequencer). Float slider controls are the
  fallback where channels cannot be created. The IK/FK switch is the Maya switch
  controller itself with its `IK_FK` channel wired to the blend.
* **Locked channels.** Whole groups locked in Maya (all of t, r or s) are
  locked in Unreal (limits + channel filter). Single axes are not mapped (the
  UE control frame is not the Maya controller frame).
* **Pole vectors.** Stock sphere, scaled to the Maya controller's world size
  (`size_unreal`).
* **Constraint-driven bones** (`params.constraints`, FKChain modules). Every
  Maya parent/point/orient/scale constraint driving a module bone is exported
  (driven channels, targets, weights, the controller each target belongs to)
  and rebuilt with the native Parent/Position/Rotation/Scale Constraint node,
  maintain offset on. One control per Maya controller (shared across bones and
  modules), parented to its Maya parent controller when present; a target
  that is a node under a controller becomes a null under the control. Used
  automatically ("auto") whenever plain FK can't represent the rig (partial
  channels, several targets or constraints per bone, one controller driving
  several bones); recipe `ConstraintMode` = `always` / `never` overrides.
  Aim constraints are reported and skipped.
* **Rebuild cleanup.** Before building, everything under `PythonWorldControls`,
  root nulls starting with a module name, and graph nodes starting with a module
  name are removed, so renamed/re-typed controls never linger.

## Known limits

* Only NURBS-curve controllers export a shape (meshes/surfaces used as
  controllers fall back to the default shape). Controllers may be any DAG
  transform, joints included.
* Pole vectors always use the stock sphere shape (project convention).
* Controller orientation is not carried; controls take the bone's orientation
  so their gizmo axes follow the joints. Only position is preserved.
* Settings on controllers that belong to no module (face blend-shape sliders
  etc.) are exported only if a module's controller carries them.
* Attribute controls are created for every exported attribute, but only the
  IK/FK switch is wired into the graph.
