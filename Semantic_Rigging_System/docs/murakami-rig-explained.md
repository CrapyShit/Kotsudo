# The Murakami rig, Maya to Unreal: how every part works

This is the full explanation of how the Murakami character rig is rebuilt from
Maya in Unreal Engine 5.6. For each part it covers how it is made, what is
exported, how Unreal rebuilds it, what went wrong, and exactly what fixed it.

Final state (pose check, 290 poses): **21/21 modules within T1**
(T1 = 0.1 cm / 0.5°), nothing off at rest, every control on its Maya pivot.

---

## 0. The pipeline in one picture

```
MAYA                                             UNREAL 5.6
----                                             ----------
1. Rig Tagger  (rig_tagger_tool.py)
   tags joint chains as modules
          |
2. Exporter  (export_rig_manifest.py)
   - FBX (skeleton + mesh)            ---->  3. Import FBX (skeleton = skin BIND pose)
   - manifest JSON inside the FBX            4. run_rig_builder.py
     (attribute rig_manifest_json             - reads the manifest from the mesh metadata
      on the root joint)                      - builds one module after another into a
   - murakami_shapes/RB_<id>.fbx               Control Rig (controls, nulls, graph nodes)
     (one tube mesh per controller shape)     - compiles, bakes rest corrections, recompiles
   - murakami.poses.json  (test poses)  ---->  5. Pose check (pose_harness.py)
                                                - replays every Maya pose on the new rig
                                                - writes murakami.harness_report.json/.html
```

Your day-to-day loop:

1. Export in Maya with the shelf button (`kotsudo_launcher.launch()`).
2. In Unreal, re-import the FBX and run `run_rig_builder.py`. It builds the rig
   and then runs the pose check by itself.
3. Read `FBXs/murakami.harness_report.json` (or the `.html` next to it).

---

## 1. Shared foundations

### 1.1 Tagging (what "a module" is)

The Rig Tagger writes `rigTag_*` attributes on joints: module type, module
name, start/end bone, role. There are four module types:

| Type | Murakami modules | Unreal module |
|---|---|---|
| `SplineIK` | Spine (Spine1–Spine4) | `spline_ik_module.py` |
| `FKChain` | Neck (Spine5–Head), L_LegLeafToe, eyes, 12 petals | `fk_module.py` |
| `IKFKSwitch` | L/R_ArmLeaf, L/R_LegLeaf (3 joints each) | `ikfk_module.py` |
| `IKLimb` | (none on Murakami) | `ik_module.py` |

Modules are built in dependency order (the spine before the limbs, the leg
before its toe), so each one can attach to the one above it.

### 1.2 Maya to Unreal conversion (axes and units)

Murakami is a Y-up Maya scene with **metres** as its UI unit. Unreal is Z-up,
left-handed, in centimetres.

- **World vectors:** Maya (X, Y, Z) becomes Unreal (X, Z, Y). Swapping two
  axes is the reflection that turns right-handed into left-handed.
- **Orientations:** the rotation is conjugated by the same swap
  (`_world_axes_unreal`), exactly as the FBX importer converts joints.
- **Units:** `xform -matrix` answers in Maya's internal unit, which is
  **always cm**. `xform -translation` and `-rotatePivot` answer in **UI units**
  (metres on Murakami).

  *Problem:* the joint-local offset math mixed those two, so some offsets came
  out 100× wrong. *Fix:* joint-local vectors are built from the world matrix
  axes plus the translation query with the correct unit scale. The schema
  check (`manifest_schema._inconsistent_offsets`) now refuses a manifest whose
  joint-local and world offsets disagree in length, so a unit error can never
  silently move a control again.

### 1.3 How a controller is described (the "controller record")

For every Maya controller the exporter writes a record (`bone_controllers` in
the manifest). Its main fields:

- **Origin.** The point the animator rotates around (`_controller_origin_world`):
  the rotate pivot, unless the pivot was left at the world origin, in which
  case the shape's bounding-box centre is used.
- **Two encodings of that origin, relative to an anchor bone:**
  - `offset_from_anchor_unreal`: a world-space offset, cross-checked against a
    neighbour bone (`reference`).
  - `offset_local`: the same offset in the anchor joint's own frame, checked
    against the neighbour by both direction and length (`reference_local`).

  Unreal uses the joint-local one only when it passes that check. If the two
  disagree, the world one wins and a warning is logged.
- **Orientation** (`world_axes_unreal`), size, colour, locked channels, custom
  attributes (which become animation channels in Unreal).
- **Parent space.** `parent_controllers` (the Maya controller hierarchy) and,
  when a constraint drives the controller's group, `parent_space_bone` /
  `parent_space_blend` (see §4).

**Driver nulls (how a control can sit away from its bone).** When a control's
origin is not on its bone, Unreal creates the control at the Maya origin and
parents a hidden null (`<control>_Drv`) under it, placed exactly on the bone.
The rig reads the null, not the control, so: bone = control × fixed offset.

### 1.4 Controller shapes (curves become meshes)

Control Rig cannot draw a Maya NURBS curve, so:

1. The exporter samples each curve into polylines, in Unreal axes and cm,
   centred on the controller origin (`_curve_strands`).
2. The exporter builds a thin square **tube mesh** around those polylines
   (radius 1.2 % of the shape's diagonal) and saves one FBX per shape:
   `murakami_shapes/RB_<shape_id>.fbx`. The shape id is a hash, so identical
   shapes are shared.
3. In Unreal, `control_shapes.prepare_shape_library` imports those meshes into
   `/Game/RigBuilder/Shapes` and registers them in a shape library. Each
   control references its shape by name. Because the points are stored in
   world orientation, the shape transform cancels the control's rotation: the
   control turns, and the drawing still matches Maya.

If a shape can't be imported, a stock circle/box/sphere is picked from the
shape's descriptor.

### 1.5 Bind pose vs rest pose (fixed last)

Unreal's skeleton is the skin's **bind pose** (when the mesh was skinned), not
the pose the rig rests in. On Murakami these differ: the four toe joints were
bound **1.0114 cm** lower than where the rig keeps them (the foot FK control
carries a −1.0114 translate). Hip/spine differ by under 0.007 cm.

- *Symptom:* the toe and its control sat 1 cm off at rest, and rotating the
  control swung the toe around the wrong point (0.35 cm error).
- *Fix:* the exporter writes `rest_pose`. For every joint it stores the current
  frame and the bind frame (`bindPreMatrix⁻¹` from the skinCluster). Before
  building any module, the builder moves each bone that differs onto Maya's
  rest (`builder.apply_maya_rest_pose`):
  - position: the exported rest position
  - rotation: the delta rest × bind⁻¹, applied on top of Unreal's own bone
    rotation, so no absolute axis convention is assumed

  The log says which bones moved. *Side bug:* Unreal 5.6's Python `Quat` has
  no `inverse()`, which crashed the first try. The quaternion math is now
  plain Python.

---

## 2. Spine: Spline IK (`SplineIK`)

### How it's made in Maya
A spline IK handle on Spine1–Spine4. The curve's CVs are skinned to three
hidden helper joints (`Pelvis_IKSplinectrl`, `spine_IKSplinectrl_01`,
`chest_IKSplinectrl`). Each sits under an animator control: `Pelvis_IKctrl`,
`spine_ctrl_01`, `chest_ctrl`. Spine4 is also orient-constrained to the chest.
Murakami's spline does not stretch.

### What is exported
`params.spline`:
- **The controls:** one record per helper joint, named after its animator
  control (`ue_control_name`), with that control's shape, orientation and
  parent. Since the last fix, each record also carries the animator control's
  own origin (`ue_control_origin`).
- **The CVs:** each CV's position plus its **skin weights** on every control.
- **Curve settings:** degree, CV count, and `stretch_enabled`, detected by
  `_spline_stretches`.
- **The extra constraint:** Spine4 orient → chest (`params.constraints`).

### How Unreal rebuilds it
1. **Controls.** One control per animator control, under its Maya parent.
2. **CV points.** For every CV, one null per influencing control, riding on
   that control (`_CVxx_Cyy_Pt`). The CV position is the **weighted average of
   all its influences** with Maya's weights, built as a chain of lerps. After
   adding influence i, the running weight is Wᵢ and the lerp uses wᵢ/Wᵢ.
3. **Curve and fit.** *Spline From Points* builds the curve. *Fit Chain on
   Spline Curve* places the bones on it, with Alignment "Front" (bones keep
   their length), or "Stretched" if Maya stretches.
4. **Constraint.** The exported constraint runs after the fit (Spine4 follows
   the chest's rotation), as in Maya.
5. **Rest correction** (see the problems below).

### Problems and fixes
| Problem | Cause | Fix |
|---|---|---|
| Spine bent unlike Maya's | Each CV used only its 2 strongest influences | Weighted average of **all** influences with Maya's weights |
| Spine stretched when Maya's doesn't | Stretch defaulted to on | `StretchEnabled` defaults off; on only when detected in Maya |
| Every limb on the spine inherited a 0.038 cm rest error, which broke the knees (see §5) | Fit Chain doesn't land exactly on the bind pose: an approximation of ~0.04 cm | **Rest correction.** After the fit, each spine bone is re-applied as `RestOffset × solved`. Right after compiling, the builder runs the rig at rest, measures each bone (offset = bind × solved⁻¹), writes it into the graph, and recompiles (`bake_rest_corrections`; log: "largest rest offset 0.0379 cm"). |
| chest_ctrl drawn 0.59 cm away from its Maya pivot (spine_ctrl_01: 0.065 cm) | The control was placed at the helper joint, not at the animator control | Exporter writes `ue_control_origin` (the animator control's pivot) and saves the shape around it. The spline module places the control there. The curve isn't affected, because CV nulls are placed from the CVs. |

What remains: up to 0.056 cm on Spine3 when the spine controls rotate. That's
the spline fit approximating Maya's curve, inside T1.

---

## 3. Neck, toe, eyes and petals: FK chains (`FKChain`)

### How it's made in Maya
One controller per joint, usually with a parent constraint from the control
to the joint (neck_ctrl_01…05 and head_ctrl, petal controls `pedal_ctrl_xx`,
eye controls, `L_FootFKctrl` for the toe).

### How Unreal rebuilds it
Per bone: a control at the Maya origin (driver null if needed, §1.3), under
its Maya parent control or its parent space (§4). The graph reads the control
(or its null) and sets the bone. When the Maya constraints can't be expressed
as plain FK, the module switches to **constraint mode** (§4.3).

### Problems and fixes
| Problem | Cause | Fix |
|---|---|---|
| Petals didn't follow the head, and clipped far away when the head rotated | Their parent space followed a bone they drive themselves (a feedback loop), or a bone nobody drives | `_acyclic_space_bone` replaces such a space with the parent of the driven bone. A warning is logged when a follow space tracks a bone no module drives. |
| Petals rotated around the shape centre, not their custom pivot | The origin used the bounding-box centre | `_controller_origin_world` keeps the rotate pivot; bounding box only when the pivot sits at the world origin |
| Neck controls 0.11–0.13 cm off their Maya pivot (arm controls ~0.005 cm) | Controls closer than **0.5 cm** to their bone were snapped onto it | `ORIGIN_OFFSET_TOLERANCE` 0.5 → 0.001 cm. Every real offset is kept through the driver null. |
| Toe 1 cm off at rest | Bind pose vs rest pose | §1.5 |
| Toe 1 cm off in left-leg FK poses | Maya's per-target constraint offsets | §4.2 |
| Petals "0.14° off" in the report | Not a rig error (measurement artifact) | §6 |

---

## 4. Parent spaces and constraints

### 4.1 Follow spaces
When a controller's group is driven (constraint, matrix, driven keys), its
Maya parent isn't its real driver. The exporter finds the joint the
constraint's **targets** sit on (`parent_space_bone`). Unreal creates a null
that follows that bone's solved transform and puts the control under it.
The null's update is emitted right after the module that drives that bone.

*Problem:* the toe control followed the knee. *Cause:*
- the IK/FK switch's weight input is also connected under the constraint's
  `.target[]`, so it was counted as a target;
- the helper IK/FK chain joints sit at the same positions as the real ones.

*Fix:* targets are read only from `targetParentMatrix` (`_constraint_targets`),
and module joints are preferred over helper joints (`_nearest_exported_joint`).
An older duplicate `_constraint_targets` further down the file was silently
overriding the fixed one. It has been removed (the manifest output on Murakami
is unchanged).

### 4.2 Blended spaces (the foot FK control)
`L_FootFKctrl_grp` is parent-constrained to **both** `L_LegIKctrl` and
`L_LegFKctrl_03`. The weights come from the IK/FK switch and its reverse node.

- **Export:** `parent_space_blend`: the targets, each weight's source
  (control, attribute, inverted or not, via `_weight_source`), and the
  controller's pose with **each target alone** (`solo`). The solo poses are
  measured by setting the switch, then restoring it.
- **Unreal** (`context.blended_space`): a null `RB_<name>_Space` driven by a
  Parent Constraint, with each weight read live from the switch channel
  (1 − x when inverted).

*Problem:* in FK poses the toe was 1.0114 cm off. *Cause:* a Maya
parentConstraint keeps **one offset per target**, set when it was created.
Murakami's IK and FK offsets disagree: flipping the switch from IK to FK at
rest drops the toe by 1.0114 cm in Maya itself (checked in Maya batch).
Unreal's "maintain offset" measures a single relation from the rest pose, so
it can't reproduce that drop. *Fix:* one null per target, parented under that
target control, placed where the space sits with that target alone. The
blend constrains to those nulls without maintain offset.

### 4.3 Constraints on bones
Maya point/orient/scale/parent constraints become Control Rig constraint
nodes with maintain offset. Maya keeps a maintained offset in the
**constrained node's parent space**, so the "Local Space Offset" variants are
used. The plain variants keep it in world space, and the bone then drifts as
soon as its parent rotates.

---

## 5. Arms and legs: IK/FK limbs (`IKFKSwitch`)

### How it's made in Maya
Three bound joints per limb (shoulder–elbow–wrist, hip–knee–ankle). Two
helper chains (`*_IKLeg*` with an IK handle and pole vector, `*_FKLeg*` with FK
controls) are children of Spine1 (legs) or Spine4 (arms). The bound joints
copy the helper chains' **local** values through pairBlend nodes, weighted by
`*_IKFK_Switch.IK_FK`. Facts measured in Maya:
- the wrists and ankles do **not** turn with the IK controls;
- the knee stays exactly in the hip/foot/pole plane;
- both legs and arms are **perfectly straight** at rest.

### How Unreal rebuilds it
- FK controls, the IK control, the pole vector and the switch (with
  `IK_FK` as a channel).
- **IK:** Control Rig's two-bone solver (`TwoBoneIKSimple`, "Basic IK").
  - The **switch drives the solver's Weight** (1 − value, because the Maya
    enum is IK:FK). FK = the solver is fully off; IK = fully on.
  - **Bone lengths are fixed to the rest lengths** (BoneALength/BoneBLength).
- **Exported flags:** `ik_end_orient` (does the end joint follow the IK
  control?) and `root_local_blend` (are the chains blended locally?).

### Problems and fixes
| Problem | Cause | Fix |
|---|---|---|
| FK controls sometimes moved the 3 bones "as if an IK were tied to them" | The IK solver kept acting in FK mode, and the end bone was handled wrongly | The switch drives the solver's Weight, so FK really disables IK. The end bone's rotation is handled separately (next rows). |
| End bone rotation not applied | Set Rotation was wired to a "Rotation" pin; the real pin is "**Value**" | Wired to Value (with a fallback) |
| Wrists turned with the IK controls | I had assumed Maya's do. Measured: they don't. | The end bone keeps its rest local rotation in IK, unless the export says `ik_end_orient` |
| Hips/shoulders didn't follow the spine | Maya blends the chains locally, so the root rides on its parent joint (hip on the spine), not on the FK control's parent (the pelvis control) | **Root rebase.** The FK pose is taken relative to the FK control's parent and re-applied under a null that follows the root's parent bone (MakeRelative → MakeAbsolute). Done for the whole chain. |
| Knee 3.16 cm off on chest/spine poses | (1) The solver measured bone lengths from the current pose; on a straight leg a millimetre of length moves the knee by centimetres. (2) The spine's 0.038 cm rest error lifted the hip, giving the straight leg 0.04 cm of slack. A chest rotation that shortens hip-to-ankle by 0.04 cm bends Maya's knee 3 cm, while Unreal's leg just used up the slack. | (1) Rest bone lengths on the solver. (2) Spine rest correction (§2). Knee: 3.16 → 0.15 cm. |

### The "near-straight limb" effect (why 0.15–0.39 cm remains and is fine)
On a nearly straight limb, the middle joint's distance from the root–tip line
is h ≈ √(2·k·slack), where k = A·B/(A+B) from the two bone lengths and
slack = A + B − reach. So a tiny change of reach moves it a lot. On
Murakami's straight 7 m arm, 0.0005 cm of slack moves the elbow ~0.4 cm. The
poses file stores positions to 0.0001 cm, so Maya's own data can't pin the
elbow down better than that.

The hands, feet, shoulders and hips match. The report handles this honestly
(§6.4).

---

## 6. The pose check (harness)

### 6.1 What it does
- **Maya side** (`export_test_poses.py`, run by the export):
  - a **rest** pose;
  - a **probe** per control channel: ±20° rotation, ±5 cm translation, with
    each limb set to the mode the control belongs to (IK or FK);
  - **12 random** multi-control poses.

  For each pose it records every joint's world position and rotation in
  Unreal axes, plus each control's rest frame and origin.
- **Unreal side** (`pose_harness.py`), per pose:
  1. reset the rig;
  2. set each posed control to "Unreal rest × Maya motion" (world matrix,
     so pivots are respected);
  3. set the switch channels;
  4. solve, re-apply, solve twice more;
  5. read the bones.

  The error is Unreal's **motion from rest** vs Maya's motion from rest, in
  cm and in degrees.
- **Calibration** first: rest joints and controls vs Maya. It fails only if
  most joints are off (p95 > 0.1 cm), which would mean a conversion error.
- **Tiers:** T0 ≤ 0.01 cm / 0.01°; T1 ≤ 0.1 cm / 0.5°. The report also gives
  per-module/joint/control tables, the worst poses, a comparison with the
  previous run (`.prev.json`), and an HTML page.

### 6.2 Harness bugs fixed along the way
| Bug | Fix |
|---|---|
| Controls with moved pivots replayed wrongly | Replay with the world **matrix** motion (rotation about the pivot) |
| Stale Maya rest pose | Rest re-captured after settling |
| Constant rest offsets counted on every pose | Error measured as motion from rest |
| Calibration failed on a few misplaced joints | Fails only when the bulk (p95) is off; a few are reported as rest offsets |
| Helper chains (IK/FK joints Unreal doesn't drive) scored | Only module joints scored; the others listed |
| Wrong IK/FK mode per probe | Records looked up by module name |
| Toe 17°/9 cm on a random pose | Controls under rig-driven spaces were set before their space moved; targets re-applied after a solve |
| No poses file after export | Maya kept old module code in memory: the shelf launcher reloads the modules, plus `importlib.invalidate_caches()` for files added after Maya started |

### 6.3 The petal "0.14°" (an artifact, not a rig error)
Every petal showed a constant 0.13–0.15°. Maya measured its petals perfectly
stable. The real cause: the poses file stores rounded quaternions (length off
by ~3e-7), and the angle was computed as `acos(|dot|)`. Near zero, acos turns
that rounding into ~0.1°. The rest pose even disagreed with itself by 0.1355°.
*Fix:* normalise, then use `2·atan2(|v|, |w|)` of the difference. The petals
are now T0.

### 6.4 Near-straight limbs in the report
For each three-joint IK limb, the middle joint is scored only on the error
that is **not explained** by:
1. the limb's own root/tip error;
2. the measured Unreal vs Maya reach, using exact triangle heights;
3. the poses file's precision (`SLACK_ROUNDING_CM` = 5e-4 cm).

On a bent limb this allowance is ~0. In the offline test, a fake 0.3 cm error
on a bent arm still scored 0.299. Raw and unexplained numbers are listed under
`straight_limb` (and "Near-straight limbs" in the HTML). Murakami: elbows
0.39 cm and knees 0.15–0.19 cm raw, all fully explained.

---

## 7. Final numbers

| | Start of this round | Now |
|---|---|---|
| Modules within T1 | 16/21 | **21/21** |
| Joints off at rest | toe 1.01 cm; 95% of joints within 0.038 cm | none (95% within 0.0003 cm) |
| Knee (chest rotation) | 3.16 cm | 0.15 cm, explained |
| Toe | 1.01 cm rest; 17° random pose | T0 |
| Petals | 0.14° | T0 |
| Worst control vs Maya pivot | 1.01 cm (toe), 0.59 cm (chest) | 0.013 cm |

## 8. Lessons to reuse on the next character
1. **Check the scene, not assumptions.** Several fixes came from measuring
   Maya in batch (mayapy on a scene copy): wrists not following IK, the IK→FK
   toe drop, the bind pose offset.
2. **Bind pose ≠ rest pose** is common. `rest_pose` handles it now.
3. **Straight limbs are hypersensitive.** Any rest offset upstream (spine fit)
   shows up as centimetres at the knee.
4. **Constraints keep per-target offsets in Maya;** Unreal's maintain offset
   doesn't.
5. **Units:** `xform -matrix` is always cm; translation/pivot queries are UI
   units.
6. **Measure with the right maths:** rounded quaternions plus acos produce
   fake angles.
7. **Unreal Python quirks:** `Quat` has no `inverse()`; pin names differ from
   node titles ("Value", not "Rotation").

## 9. Not done yet
- Petal open/close sliders (`Petal_Translate` / `Petal_Rotation`): Maya
  drives these through attribute networks, which aren't transferred yet.
