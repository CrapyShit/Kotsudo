# Pose check (Maya vs Unreal)

Measures how closely the rebuilt Unreal Control Rig reproduces the Maya rig:
the same control moves are applied in both, and every joint is compared.

## Workflow

1. **Maya — export.** The normal export (rig tagger → Export) also writes
   `<name>.poses.json` next to the FBX. To regenerate only the poses (after
   changing the rig's behaviour, without re-exporting the FBX):

   ```python
   import export_test_poses; export_test_poses.export_from_scene()
   ```

   It uses the manifest last written on the root joint and writes into the
   repo's `FBXs` folder.
2. **Unreal — build.** `run_rig_builder.py` builds the rig, then runs the pose
   check automatically (`RUN_POSE_CHECK = False` at the top turns it off). To
   re-run the check alone on the open rig: `run_pose_harness.py`.
3. **Read the result.** The Output Log ends with a `VERDICT` line, the modules
   and their tiers, the 5 worst controls, and what changed since the last run.
   The full report is next to the poses file:
   * `<name>.harness_report.html` — open in a browser;
   * `<name>.harness_report.json` — everything, for tools;
   * `<name>.harness_report.prev.json` — the previous run.

## What is tested

* **Rest (calibration):** joints and controls at rest vs Maya. It FAILS only
  when most joints are off (p95 above 0.1 cm): that is a conversion error
  (axes, units). A few joints off are listed as *rest offsets* -- a rig
  placement problem, reported once.
* **Probes:** every unlocked rotate/translate channel of every control (+20°,
  +5 cm) and every custom attribute (to its min/max), one at a time. IK/FK
  limbs are put in the matching mode first: FK controls are probed in FK, IK
  controls in IK.
* **Random poses:** 12 seeded poses moving 4 controls each, every limb in a
  random IK or FK mode.

Every pose records all IK/FK switch values, so Unreal replays the same modes.

## How to read it

* **Tiers per module:** T0 ≤ 0.01 cm / 0.01°, T1 ≤ 0.1 cm / 0.5°, otherwise
  "above T1".
* **Pose errors measure motion:** position error compares each joint's
  displacement from rest in Maya and Unreal, rotation error its rotation
  change from rest. A joint misplaced at rest (see calibration) therefore
  doesn't add the same error to every pose, and the importer's fixed per-bone
  axis differences don't count.
* **Worst poses** list their three worst joints, so you see where a chain
  breaks (e.g. ankle fine, toe off = the toe's parent is wrong).
* **Controls whose probe breaks the most** point at the setup to fix: e.g.
  `L_ArmFKctrl_01 (fk) → worst joint L_ArmLeaf3` means the FK arm is wrong.
* **Probes that move nothing in Maya** are flagged at export; Unreal must not
  move anything for them either (any error there is an extra behaviour).
* **vs previous run** marks each module `better`, `WORSE`, `mixed` or `same`,
  so a fix that breaks something else shows immediately.

## Replaying controls with moved pivots

A control is replayed with its Maya WORLD MATRIX motion, not its translate
channel: for a frozen control whose pivot sits away from its origin (common
for pole vectors, pelvis and chest controls), only the matrix rotates about
the pivot as Maya does.

## Limits

* Attribute-driven setups not transferred yet (e.g. the petal open/close
  sliders) will show as errors on those probes — expected until supported.
* The Unreal side drives a rig instance from Python; if the engine gives no
  fresh instance it uses the editor's own, reset before every pose.
* **Perfectly straight limbs.** When a leg or arm is exactly straight at rest
  (Murakami's), the knee/elbow position on poses that keep it straight is
  decided by sub-0.0001 cm differences in reach. Unreal solves in 32-bit
  floats (about 0.00006 cm of precision 10 m from the origin), so the middle
  joint can differ by a few tenths of a cm (Murakami: knee 0.15–0.19 cm,
  elbow 0.39 cm on 5 cm probes) while the end joints match. This is
  numerical, not a rig difference; it disappears as soon as the limb bends.
* **Bind pose vs rest pose.** Unreal's skeleton is the skin's bind pose. If
  the rig rests elsewhere (Murakami's toes: 1.01 cm), the builder starts the
  Control Rig from the exported Maya rest (`rest_pose` in the manifest) and
  logs which bones it moved.
