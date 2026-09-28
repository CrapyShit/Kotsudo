# Foundation milestone (before the next L2 phase)

The six prerequisites from the research reference (section 12, G1–G3),
implemented. Manifest schema **v6**.

## 1. Children attach to the right parent

Every control records where it really hangs in Maya (`parent_controllers`,
`parent_space_bone`), and every module records the joint it hangs from
(`connections.parent_bone`). Unreal resolves a control's parent in this order
(`RigContext.resolve_control_parent`):

1. the nearest Maya parent controller that exists in the rebuilt rig
   (`neck_ctrl_01` → `chest_ctrl`, `L_ArmFKctrl_01` → `chest_ctrl`);
2. if a **driven** group (constraint, blend, driven key, matrix input) sits
   between the control and its Maya parent, the Maya parent is not the real
   driver: the control follows the bone that group tracks (`L_FootFKctrl`,
   blended between IK and FK, follows `L_LegLeaf3`; the IK/FK switch follows
   the hand);
3. Maya parents exist but none was built: world (`L_LegIKctrl` under the
   unexported `world_ctrl`).

Records without this data (older manifests) and controls without a Maya
record use the module default: the **follow space** of `parent_bone`.

A follow space is a null rewritten every evaluation from a bone's final
transform. The context creates one per bone, on demand. Its update runs right
after the module that drives the bone. The position-guessing attach-point
table (`spline_tip_ctrl` for "anything near the tip") is now only a fallback.

## 2. IK/FK switch is keyable and drives visibility

The switch is the Maya switch control with an `IK_FK` animation channel. It can
be keyed in Sequencer and edited in the Details panel. The channel also drives
Set Control Visibility: FK controls are shown while the FK weight is above 0,
and the IK effector and pole while the IK weight is above 0, so both are visible
mid-blend. Turn this off with the recipe field `SwitchDrivesVisibility`.

## 3. IK and FK chains identified by the ikHandle

`identify_ik_fk_roots` takes the chain an ikHandle solves as the IK chain.
Constraint target order is no longer trusted. Tagged roots are checked the
same way: a swapped pair is corrected and reported.

## 4. Solve stages

A Sequence node after Forwards Solve runs, in order: `spaces` → `primary` →
`helpers` → `dynamics` → `curves`. Each module declares its stage
(`RigModule.solve_stage`, `primary` for every module today). Within a stage,
modules run parents first. All exec wiring goes through
`graph_utils.connect_exec`. Modules create every control before they read the
exec tail, because resolving parents can insert follow-space updates.

## 5. Manifest contract

* `schema`, `schema_version` (6), `source`, `units`, and
  `coordinate_system` with both mappings: world `X,Z,Y` and joint-local
  `X,-Y,Z`.
* **Joint-relative positions**: `offset_local` is in the anchor joint's own
  frame, validated by `reference_local`. No world conversion is involved. The
  world offset stays as a fallback and cross-check, and a disagreement is
  logged.
* **Per-chain axes** (`modules[].axes`): the aim axis and the bend axis (toward
  the knee or elbow), in Maya and Unreal joint-local labels. Unreal compares
  them with the imported skeleton and logs `chain axes aim -Y ok` or a
  mismatch.
* **Validation** against `schema/kotsudo_manifest.schema.json`, with the same
  code (`rig_builder/manifest_schema.py`) in Maya before export and in Unreal
  before building. Errors block, warnings are reported.
* **Unit consistency**: a joint-local vector is a world vector on rotated
  axes, so its length must equal its world twin's. The validator checks
  every `offset_local` / `reference_local` against `offset_from_anchor_unreal`
  / `reference.unreal_vector` (this caught Maya's `xform -matrix` answering
  in internal cm while `xform -translation` answers in the UI unit, in metre
  scenes). Unreal additionally rejects a joint-local reference whose length
  does not match the real bone distance, and falls back to the world offset
  whenever the two encodings disagree.
* **Migration**: manifests recording the old world mapping `X,-Z,Y` get their
  world vectors corrected once (keyed on the mapping, not the version).

## 6. Pose-match harness

**Maya** (automatic on export): `<name>.poses.json` next to the FBX. It
contains the rest pose, one probe per unlocked rotate/translate channel and
custom attribute of every animator control, and 12 seeded random multi-control
poses. For each pose it stores the controls' input and every exported joint's
result, in Unreal axes and cm.

**Unreal**: after `run_rig_builder.py`, run `run_pose_harness.py`. It:

1. checks **calibration** at rest: joint positions, and control positions
   against their Maya origins. Controls such as poles sit off the skeleton's
   plane, so a front/back mirror shows here. If calibration fails, the rig
   numbers are flagged as meaningless;
2. replays every pose on a fresh rig instance (control = its rest × the Maya
   world delta, so each UE control keeps its own frame);
3. measures per joint the position error (cm) and the rotation error, as the
   angle between the Unreal and Maya rotation *deltas from rest* (this cancels
   the constant per-bone frame difference from the importer);
4. writes `<name>.harness_report.json`, grouped by pose group, module and
   joint, with T0/T1 tiers (T0: 0.01 cm / 0.01°, T1: 0.1 cm / 0.5°), the
   worst poses, and interface parity (Maya controls found by name).

## Not yet verified in the editor

These parts rely on API details that could not be run from here. Each one fails
soft with a log message:

* `RigVMFunction_Sequence` plus `add_aggregate_pin` for the stage outputs
  (fallback: one chain);
* `RigUnit_SetControlVisibility` and the float compare units (fallback: no
  visibility);
* `ControlRigBlueprint.create_control_rig()`, `execute()` and
  `reset_pose_to_initial()` for the harness.
