# The Murakami rig, explained simply

This is the plain-language version of `murakami-rig-explained.md`. It
covers the same things in the same detail, but every technical word is
explained the first time it appears, and comparisons are used wherever they
help.

**The short story:** we built a translator. It reads a rigged character in
Maya and rebuilds the same rig, working the same way, in Unreal Engine.
Then we built a tester that moves both rigs the same way and measures how
far apart they end up. We kept fixing things until the two matched.

Where we ended: for every one of the 21 parts of the character, Unreal and
Maya match to within **1 millimetre** (0.1 cm) across all 290 test poses.

---

## Part A: Words you need (read this first)

**Joint / bone.** The skeleton's pieces. Maya says *joint*, Unreal says
*bone*; same thing. Murakami has joints like `Spine1`, `L_LegLeaf2` (left
leg, 2nd joint = knee) and `Head`.

**Skin / skinning.** Attaching the character's 3D surface (the mesh) to the
skeleton, so the surface moves when the bones move.

**Bind pose.** The pose the skeleton was in at the moment the skin was
attached. Think of it as the photo taken when the clothes were sewn on.

**Rest pose.** The pose the rig sits in when nobody touches the controls.
Usually the same as the bind pose, *but not always* (this mattered for the
toe).

**Controller (control).** The coloured curves the animator grabs and moves
(circles, boxes…). Controllers move the joints; animators never touch the
joints directly.

**Pivot.** The point a controller turns around, like the hinge of a door.
If the pivot is in the wrong place, the door swings wrong.

**Offset.** The distance between two things that move together. For
example, "the controller sits 7 cm in front of its joint".

**FK (Forward Kinematics).** You rotate each joint yourself, one after the
other: shoulder, then elbow, then wrist. Like posing a desk lamp by hand.

**IK (Inverse Kinematics).** You only move the end, like the hand or the
foot. The computer works out how the elbow or knee must bend to reach it.
Like pulling a puppet's hand: the arm follows on its own.

**IK/FK switch.** A slider that chooses between IK and FK for an arm or leg.
On Murakami: `IK_FK = 0` means IK, `1` means FK.

**Pole vector.** A small controller that tells the IK which way the elbow or
knee should point. Like telling the knee "point at that wall".

**Spline IK.** For the spine: a smooth curve runs along the back, and the
spine joints are laid along it. You bend the spine by moving a few
controllers that shape the curve. Like a garden hose you bend by moving a
few hands holding it.

**CV (curve point).** The points that shape a curve. Each CV is pulled by
the spine controllers, some more, some less. Those amounts are the
**weights** (for example 70% chest, 30% mid-spine).

**Constraint.** A rule like "this thing follows that thing". Example:
"Spine4 turns like the chest controller."

**Parent / child.** A child follows its parent. Move the parent, the child
comes along (hand follows forearm). A controller's **parent space** is
whatever it follows.

**Null.** An invisible helper point in Unreal. It holds a position and can
follow things. We use nulls as hooks, invisible handles and middlemen.

**Manifest.** The written description of the whole rig that Maya produces:
every module, controller, pivot, weight and constraint. Unreal reads it to
rebuild the rig. Think of it as the building plan.

**Module.** One part of the rig, built as a unit: the spine, the neck, each
arm, each leg, the toe, the eyes, each petal.

**Control Rig.** Unreal's system for building rigs: controllers, nulls,
and a "graph" of little calculation boxes (nodes) wired together that runs
every frame.

**Pose check (harness).** Our tester. It poses the Maya rig hundreds of
ways, replays the same poses on the Unreal rig, and measures the
difference.

**Units.** Unreal works in **centimetres**. The Murakami Maya scene works in
**metres**. Murakami is huge: about 16 m tall, the legs alone are about 6 m.

**T0 / T1 (grades in the report).**
- **T0** = within 0.01 cm (a tenth of a millimetre): perfect.
- **T1** = within 0.1 cm (1 mm) and 0.5°: our target, "matches Maya".
- **above T1** = something to look at.

---

## Part B: The whole journey in 5 steps

```
 MAYA                                              UNREAL
 1. Tagger: "these joints are the spine,
    these are the left arm..."
 2. Export button produces:
    - the character file (FBX)            --->  3. Import the FBX
      with the building plan (manifest)          4. Builder reads the plan and
      hidden inside it                              builds every part of the rig
    - the controller shapes as small 3D files
    - the test poses file                 --->  5. Tester replays the poses
                                                   and writes the report
```

1. **Tagger** (`rig_tagger_tool.py`). In Maya you label groups of joints:
   "Spine1 to Spine4 = Spine, type spline", "L_LegLeaf1 to 3 = left leg,
   type IK/FK"…
2. **Export** (`export_rig_manifest.py`). It writes:
   - the **FBX**, the standard file with the skeleton and the skin. The
     building plan is hidden inside it, stored as text on the root joint.
   - the **controller shapes**, one tiny 3D file per shape
     (`murakami_shapes/RB_xxxx.fbx`).
   - the **test poses** (`murakami.poses.json`).
3. **Import** the FBX into Unreal.
4. **Builder** (`run_rig_builder.py`). It reads the plan and builds each part
   into a Control Rig.
5. **Tester** (`pose_harness.py`). It runs automatically and writes
   `murakami.harness_report.json` (and an `.html` you can open in a browser).

---

## Part C: Things every part depends on

### C1. Translating directions and sizes

Maya and Unreal disagree on two basic things:

- **Which way is up.** In Maya, "up" is the Y axis; in Unreal it's Z. So
  every direction is translated: Maya (X, Y, Z) becomes Unreal (X, Z, Y).
  Rotations get the same translation.
- **Units.** Unreal works in cm, while Murakami's Maya scene is in metres.

**What went wrong:** Maya answers some questions in centimetres and others in
metres, depending on *how* you ask:
- asking for a "matrix" (a full position-and-rotation package) always
  answers in **cm**;
- asking for a "translation" or a "pivot" answers in the scene unit,
  **metres** here.

Our exporter mixed the two, so some distances came out **100 times too big
or too small**.

**How we fixed it:** each value is now read the right way, with the right
unit. Unreal also checks every controller's offset twice, in two different
forms. If the two lengths disagree, it refuses and tells you, instead of
silently putting a controller in the wrong place.

### C2. How a controller is described

For every Maya controller, the plan stores:

- **Its pivot (where it turns around).** We use the controller's real pivot.
  The only exception: if the pivot was left at the centre of the world (a
  sign nobody set it), we use the middle of the shape instead.
- **Where that pivot is, measured from a nearby joint (the "anchor").** It's
  stored twice:
  - once as a plain direction in the world ("7 cm forward");
  - once in the joint's own point of view ("7 cm along the joint's side").

  Each version is checked against another nearby joint. If both agree,
  great. If not, the world version wins and a warning is printed.
- **Its orientation, colour, size and locked channels,** plus its custom
  sliders. Those become sliders on the Unreal controller too.
- **What it follows (its parents).** The Maya controller hierarchy. If a
  constraint drives it, the plan stores what that constraint follows (see
  Part F).

**The hook trick (driver null).** A controller often floats away from its
joint: a big circle in front of the hand, a pivot set beside the bone. In
Unreal we place the controller exactly where it is in Maya. Then we hang an
invisible hook (a null called `<controller>_Drv`) under it, sitting exactly
on the joint. When the controller moves, the hook moves with it, and the
joint copies the hook. So the controller can be anywhere, and the joint
still lands in the right spot.

### C3. Controller shapes (curves become 3D tubes)

Unreal can't draw Maya's curves directly. So:

1. The exporter samples each curve into a series of points (in cm, Unreal
   directions), centred on the controller's pivot.
2. It wraps those points in a very thin square tube, like a wire, and saves
   each shape as its own small 3D file. Identical shapes are saved only once
   (each gets a name made from its content).
3. Unreal imports those tubes and registers them as controller shapes. A
   controller's shape is stored "facing the world", so Unreal cancels the
   controller's own rotation when drawing it. The result looks exactly like
   in Maya.

If a shape can't be imported, Unreal falls back to a standard circle, box or
sphere of the right size.

### C4. Bind pose vs rest pose (the photo vs reality)

When Unreal imports the character, it builds the skeleton from the **bind
pose**, the "photo taken when the clothes were sewn on". Normally that's
also where the rig rests. On Murakami it isn't:
- **the toes** rest **1.0114 cm higher** than when they were skinned. Someone
  later moved the foot controller by −1.0114 cm to compensate;
- the hips and spine differ by tiny amounts (less than 0.007 cm).

**What we saw:** the toe and its controller sat 1 cm off at rest. Rotating the
toe controller swung it around the wrong point, giving 0.35 cm of error.

**How we fixed it:** the exporter now also writes Maya's **real rest pose**
for every joint, plus the bind pose. Before building anything, the builder
moves any bone that differs onto Maya's rest pose. For the rotation it
applies only the *difference* between rest and bind, on top of what Unreal
already has, so it can't get the axis conventions wrong. The log tells you
which bones it moved.

*Small extra bug:* the first version used an Unreal feature (`inverse()` on a
rotation) that doesn't exist in Unreal 5.6's Python, so it crashed. We now do
that maths ourselves.

---

## Part D: The spine (spline IK)

### How Maya does it
A smooth curve runs along Spine1–Spine4. The curve's points (CVs) are
attached, with weights, to three **hidden helper joints**:
`Pelvis_IKSplinectrl`, `spine_IKSplinectrl_01` and `chest_IKSplinectrl`.
Each helper sits inside an animator controller:
- `Pelvis_IKctrl`
- `spine_ctrl_01`
- `chest_ctrl`

Moving the chest controller moves its helper, which pulls the curve, which
bends the spine. On top of that, Spine4 also *turns* like the chest (a
constraint). Murakami's spine never stretches.

### What we send
- **The controllers:** each helper, named after the animator controller it
  belongs to, with that controller's shape, orientation and parent. Since the
  last fix, also the animator controller's own pivot.
- **Every curve point (CV):** its position and its weights on each
  controller.
- **Whether the spine stretches** (detected in Maya: no).
- **The extra rule:** "Spine4 turns like the chest".

### How Unreal rebuilds it
1. **One controller per animator controller,** under its Maya parent.
2. **The curve points (the beads).** Picture each curve point as a bead on
   a string. Each bead is pulled by the spine controllers, but not equally.
   For example, one bead near the chest is pulled 70% by the chest
   controller, 30% by the mid-spine controller and 0% by the pelvis. Those
   percentages are the **weights**, copied from Maya. Unreal copies the
   effect in three steps:
   - **One invisible marker per controller that pulls on the bead.** Our
     example bead gets two markers: one for the chest, one for the
     mid-spine.
   - **Each marker is glued to its controller,** so it moves and turns with
     it.
   - **The bead sits between its markers, 70% of the way toward the chest
     marker and 30% toward the mid-spine marker.** For example, if the chest
     marker is at 10 and the mid-spine marker at 20, the bead sits at
     0.7×10 + 0.3×20 = 13.

   So when a controller moves, its marker moves, and the bead follows by
   exactly that controller's share, just like in Maya.
3. **A curve through those points** (Unreal's "Spline From Points"). The
   spine bones are laid along it ("Fit Chain on Spline Curve"), keeping their
   lengths because Murakami doesn't stretch.
4. **The extra rule runs after that:** Spine4 turns like the chest, as in
   Maya.
5. **The rest correction** (explained just below).

### What went wrong and how we fixed it

**1. The spine bent differently from Maya's.**
- *Why:* each bead only had markers for its two strongest controllers and
  ignored the rest. Some beads are pulled by three controllers.
- *Fix:* every bead now has a marker for **every** controller that pulls on
  it, with Maya's exact weights.

**2. The spine stretched when Maya's doesn't.**
- *Why:* stretching was on by default.
- *Fix:* it's off unless the exporter detects stretching in Maya.

**3. A tiny spine error ruined the knees** (explained fully in Part E).
- *Why:* Unreal's "lay the bones on the curve" tool is an approximation. Even
  at rest it put the spine bones about **0.04 cm** (0.4 mm) off. Everything
  hanging from the spine (hips, shoulders) inherited that.
- *Fix (rest correction):* right after building, the builder runs the rig
  once at rest and measures how far each spine bone landed from where it
  should be. It then writes a small correcting shift for each bone into the
  rig and rebuilds. From then on, at rest, the spine is exact. The log prints
  "largest rest offset 0.0379 cm".

**4. chest_ctrl sat 0.59 cm away from where it is in Maya** (spine_ctrl_01:
0.065 cm).
- *Why:* Unreal placed each spine controller at the **hidden helper joint**
  instead of at the animator controller. They're close but not identical, so
  the controller turned around the wrong point.
- *Fix:* the exporter now sends the animator controller's own pivot (and
  draws its shape around that pivot), and Unreal places the controller there.
  The curve doesn't change, because the curve points are placed on their own.

**What's left:** up to 0.056 cm (half a millimetre) on Spine3 when you rotate
the spine controllers. That comes from Unreal's curve tool being slightly
different from Maya's. It's within the target.

---

## Part E: Arms and legs (IK/FK limbs)

### How Maya does it
Each arm or leg has **3 real joints**: shoulder, elbow, wrist (or hip,
knee, ankle). Behind them hide **two invisible copies** of the limb:
- an **IK copy**, moved by the hand/foot controller and the pole vector;
- an **FK copy**, moved by the FK controllers.

The real joints copy a mix of the two, controlled by the switch: 0 = all IK,
1 = all FK. The copies hang from Spine1 (legs) and Spine4 (arms).

Things we **measured** in Maya:
- the wrists and ankles do **not** rotate with the IK controller (they keep
  their own rotation);
- the knee always stays exactly in the flat plane made by hip, foot and pole
  vector;
- Murakami's arms and legs are **perfectly straight** at rest. This turned
  out to be the root of the hardest problem.

### How Unreal rebuilds it
- **The controllers:** the FK controllers, the IK hand/foot controller, the
  pole vector, and the switch (with its `IK_FK` slider).
- **The IK:** Unreal's two-bone IK node (it calculates how elbow/knee bend
  to reach the target).
  - **The switch drives the IK's strength:** in FK the IK is completely off,
    in IK it's completely on.
  - **The bone lengths are fixed** to their rest lengths.

### What went wrong and how we fixed it

**1. "When I rotate FK controllers, the 3 bones move as if an IK is tied to
them."**
- *Why:* the IK was still partly active in FK mode, and the end bone (wrist /
  ankle) was handled wrongly.
- *Fix:* the switch now drives the IK's strength directly, so FK really
  turns the IK off. The end bone is handled separately (the next two
  points).

**2. The wrist rotation wasn't applied at all.**
- *Why:* we plugged the rotation into an input named "Rotation", but on that
  Unreal node the real input is called "**Value**".
- *Fix:* plugged into "Value".

**3. The wrists rotated with the IK controller.**
- *Why:* I assumed Maya's wrists do that. When we measured, they don't.
- *Fix:* in IK, the wrist/ankle keeps its rest rotation (unless the plan says
  this rig's wrist really follows the controller).

**4. The hips and shoulders didn't follow the spine.**
- *Why:* in Maya the legs hang from the spine joint. In Unreal they hung from
  the pelvis controller, so moving the spine left the legs behind.
- *Fix ("root rebase"):* Unreal takes the leg's pose, measures it relative
  to the pelvis controller, then re-applies it relative to a helper point
  that follows the spine joint. Now the legs ride on the spine like in Maya.
  This is done for every joint of the limb.

**5. The knee was 3.16 cm off when you rotated the chest.** This was the
hardest one.

- **A rope pulled tight.** Picture the leg as a rope pulled tight between hip
  and ankle. If the hip moves slightly *closer* to the ankle, the rope gets a
  little slack and the middle (the knee) pops out sideways. Because the leg
  is perfectly straight, a tiny bit of slack makes a big pop:
  - Murakami's leg is about 6 m long;
  - rotating the chest moves the hip **0.04 cm** closer to the ankle;
  - in Maya, that makes the knee pop out **3 cm**.
- **Two reasons Unreal's knee didn't pop:**
  - Unreal's IK measured the leg length from the current pose. If that pose
    was off by a hair, the leg got "longer" and stayed straight.
  - The spine's 0.04 cm rest error (Part D, point 3) had lifted the hip in
    Unreal, so the leg already had exactly that much slack *at rest*. The
    chest rotation only used up that slack, and the knee never popped.
- **Fixes:** fixed bone lengths on the IK, plus the spine rest correction.
  The knee went from **3.16 cm to 0.15 cm**.

### Why 0.15 cm (knee) and 0.39 cm (elbow) still show up, and why that's fine

Same rope idea. When a limb is almost perfectly straight, the knee/elbow
position depends **enormously** on the exact hip-to-ankle (or
shoulder-to-wrist) distance. For Murakami's 7 m straight arm, a change of
0.0005 cm (five thousandths of a millimetre) moves the elbow about 0.4 cm.

The test file stores positions rounded to 0.0001 cm, so even Maya's own data
can't pin the elbow down more precisely than that. Hands, feet, shoulders and
hips all match. So this isn't a rig difference; the tester knows how to
account for it (Part G4).

---

## Part F: "What follows what" (parent spaces and constraints)

### F1. Following a joint (follow spaces)

Sometimes a controller's Maya parent isn't what really moves it, because a
constraint moves its group instead. The exporter then works out **which
joint that constraint really follows**. Unreal creates an invisible point
that follows that joint, and puts the controller under it.

**What went wrong:** the toe controller followed the **knee**.
- *Why, reason 1:* the switch slider is also wired into the constraint (to
  set its weights), and the exporter mistook that wire for "something the
  constraint follows".
- *Why, reason 2:* the hidden IK/FK copies of the leg sit exactly on top of
  the real joints, so the exporter sometimes picked a hidden copy.

*Fix:* the exporter now only counts real "follow" targets (not weight wires)
and prefers real joints over hidden copies.

*Side discovery:* an old copy of that same function, further down the file,
was quietly overriding the fixed one. We deleted the old copy. We checked
that the exported plan for Murakami is identical with or without it.

### F2. Following two things at once (the foot FK controller)

`L_FootFKctrl` (the toe controller) follows **both** the IK foot controller
and the last FK leg controller, mixed by the switch: in IK it follows the IK
foot, in FK it follows the FK leg.

- **What we send:** the two things it follows, which slider sets the mix (and
  whether it's reversed), and where the controller sits when it follows
  *only* one of them (measured by flipping the switch in Maya, then putting
  it back).
- **How Unreal rebuilds it:** an invisible point mixed between the two, with
  the mix read live from the switch slider.

**What went wrong:** in FK poses the toe was 1.0114 cm off.
- *Why:* in Maya, "follow A or B" remembers **a separate distance for A and
  for B**, set when the rigger created it. On Murakami the two disagree:
  flipping the switch from IK to FK at rest makes **Maya's own toe drop
  1 cm** (we confirmed it in Maya). Unreal's version remembers **a single**
  distance, measured at rest, so it couldn't copy that drop.
- *Fix:* Unreal now uses two invisible points, one per thing being followed,
  each placed exactly where Maya puts the controller when following only
  that one. It mixes between those, so it copies Maya's drop exactly.

Think of it as two rulers. Maya measures with a different ruler for IK and
for FK, while Unreal had only one. Now Unreal has both rulers.

### F3. Constraints on joints

Maya rules like "this joint turns like that controller" become Unreal rule
nodes. Detail that matters: Maya remembers the starting distance **from the
point of view of the joint's parent**. Unreal has two versions of these
nodes. We use the one that does the same ("Local Space Offset"). The other
version remembers it in world terms, and the joint slowly drifts whenever its
parent turns.

---

## Part G: Neck, toe, eyes and petals (FK parts)

### How Maya does it
One controller per joint, each moving its joint:
- `neck_ctrl_01`–`05` and `head_ctrl`;
- the petal controllers `pedal_ctrl_01`–`12`;
- the eye controllers;
- `L_FootFKctrl` for the toe.

### How Unreal rebuilds it
For each joint: a controller placed at the Maya pivot (with the hook trick
when needed), under its Maya parent or its "follow" point (Part F). Each
frame, the joint copies the controller (or its hook).

### What went wrong and how we fixed it

**1. The petals didn't follow the head, and flew far away when the head
turned.**
- *Why:* the petals' "follow" point was following a joint that the petals
  themselves move. That's a loop: controller → joint → follow point →
  controller, which runs away as soon as anything moves. Some follow points
  also followed joints nobody moves.
- *Fix:* the builder detects such loops and follows the parent joint
  instead. It also warns when a follow point watches a joint nothing moves.

**2. The petals turned around the middle of their shape, not their custom
pivot.**
- *Why:* we used the middle of the shape as the pivot.
- *Fix:* we now use the real pivot. The middle is used only when the pivot
  was left at the centre of the world.

**3. The neck controllers sat 0.11–0.13 cm off** (arm controllers about
0.005 cm).
- *Why:* any controller closer than 0.5 cm to its joint was snapped onto the
  joint, "close enough". But that moves its pivot.
- *Fix:* the snap limit is now 0.001 cm (basically only rounding noise).
  Every real pivot is kept, using the hook trick.

**4. The toe was 1 cm off at rest:** the bind pose vs rest pose problem
(Part C4).

**5. The toe was 1 cm off in left-leg FK poses:** the two-rulers problem
(Part F2).

---

## Part H: The tester (pose check)

### H1. How it works

- **In Maya** (`export_test_poses.py`, runs during export):
  - **rest:** nobody touches anything;
  - **probes:** every controller moved one way at a time (rotate 20°, or
    move 5 cm), with the arm/leg set to the right mode (IK or FK) for that
    controller;
  - **12 random poses:** several controllers moved at once.

  For each pose it saves where every joint is and how it's rotated.
- **In Unreal** (`pose_harness.py`), for each pose:
  1. put the rig back to rest;
  2. move each controller the same way it moved in Maya, turning around the
     same pivot;
  3. set the switch sliders;
  4. let the rig calculate, re-place the controllers, and calculate twice
     more;
  5. read where every bone ended up.
- **The comparison:** how far each bone moved from rest in Unreal vs how far
  it moved in Maya. Comparing *movement* (not raw position) means a bone
  that's slightly off at rest doesn't count as wrong on every single pose.
- **Calibration** first: at rest, are bones and controllers where Maya says?
  If most of them are off, the translation itself is broken, and the report
  says not to trust the rest.
- **The report** gives a grade per part (T0 / T1 / above T1), the worst
  controllers, the worst poses, and "better/worse than last run". There's an
  HTML page too.

### H2. Mistakes in the tester itself (also fixed)

| What was wrong | What we changed |
|---|---|
| Controllers with a moved pivot were replayed turning around the wrong point | Replay the full movement, including the pivot |
| The Maya rest snapshot was taken before the rig had settled | Take it again after settling |
| A bone slightly off at rest counted as wrong on every pose | Compare movement, not position |
| Calibration failed because of one or two misplaced bones | Fail only when *most* bones are off; list the few as "off at rest" |
| The hidden IK/FK leg copies were graded even though Unreal doesn't use them | Only grade the joints Unreal actually builds; list the others |
| Some probes used the wrong IK/FK mode | Look up each controller's mode correctly |
| The toe showed 17° / 9 cm on one random pose | Its controller was placed before the thing it follows had moved; now controllers are re-placed after the first calculation |
| No poses file after exporting | Maya kept running the old version of our code from memory. The shelf button now reloads everything, including files added after Maya started. |

### H3. The petals' "0.14°": a measuring mistake, not a rig problem

Every petal showed the same tiny 0.13–0.15° error, even though Maya's petals
were perfectly still.

**Why:** rotations are stored in the test file as four numbers, rounded. The
formula we used to turn two rotations into "the angle between them" is
extremely sensitive near zero. It turned harmless rounding (0.0000003) into
a fake 0.1°. The proof: the rest pose disagreed **with itself** by 0.1355°.

**Fix:** a different formula that isn't sensitive near zero. The petals are
now graded T0 (perfect).

### H4. The tester and straight limbs

Because of the rope effect (Part E), the tester would always flag the knees
and elbows of straight limbs, even when the rig is right. So for each arm
and leg, the tester now works out how much of the knee/elbow error is
**explained** by:
1. the hip/ankle (or shoulder/wrist) themselves being slightly off in that
   pose;
2. the exact hip-to-ankle distance in Unreal vs Maya;
3. the rounding in the test file.

Only the part that's **not** explained counts towards the grade. On a bent
limb, almost nothing gets explained away: in our test, a fake 0.3 cm elbow
error on a bent arm still counted 0.299. So real problems still show up. The
raw numbers stay visible in a "Near-straight limbs" section.

On Murakami: elbows 0.39 cm and knees 0.15–0.19 cm raw, **all fully
explained**.

---

## Part I: Where we started and where we are

| | Start of this round | Now |
|---|---|---|
| Parts matching Maya (within 1 mm) | 16 of 21 | **21 of 21** |
| Bones off at rest | toe 1 cm off; most bones 0.04 cm off | none (most within 0.0003 cm) |
| Knee when rotating the chest | 3.16 cm | 0.15 cm, fully explained |
| Toe | 1 cm off at rest; 17° on one pose | perfect (T0) |
| Petals | 0.14° | perfect (T0) |
| Worst controller vs its Maya pivot | 1 cm (toe), 0.59 cm (chest) | 0.013 cm |

## Part J: Lessons for the next character

1. **Measure Maya, don't guess.** Several fixes only came from testing the
   real Maya scene (a copy, never your file): the wrists not following IK,
   the toe dropping when switching IK→FK, the toe's bind pose.
2. **Bind pose and rest pose can differ.** The tool now handles it
   automatically.
3. **Straight arms and legs amplify tiny errors.** A 0.4 mm spine error
   became a 3 cm knee error.
4. **Maya's "follow A or B" keeps a separate distance for each;** Unreal's
   keeps one. The tool now copies Maya's.
5. **Maya answers in cm or metres depending on how you ask.**
6. **Check the measuring tool too:** a bad formula invented the petals'
   0.14°.
7. **Unreal's Python has quirks:** missing functions, and inputs named
   differently from what the node shows.

## Part K: Reading the node graph in Unreal

When you open the Control Rig, the graph is now arranged automatically:
- **Each part of the rig sits in its own box** (a comment), titled with its
  name and type, e.g. "Spine (SplineIK)" or "L_LegLeaf (IKFKSwitch)". The
  colour shows the type:
  - blue = spine (spline);
  - orange = arms and legs (IK/FK);
  - green = FK parts (neck, toe, eyes, petals);
  - grey = the start (Forwards Solve and the solve order).
- **Inside a box, the calculation reads left to right.** A node is always to
  the right of the nodes that feed it. A node that only reads something
  (like a *Get Transform*) sits just left of the node it feeds.
- **Nothing overlaps:** neither the nodes inside a box nor the boxes
  themselves. Boxes are stacked top to bottom in build order, then in new
  columns to the right.
- **On every rebuild,** the old boxes are removed and the layout is redone.
  The log prints "Graph laid out: N node(s) in M named box(es)".

## Part L: Still to do

- **The petal open/close sliders** (`Petal_Translate` / `Petal_Rotation`).
  In Maya these sliders drive the petals through a network of maths nodes,
  which our tool doesn't translate yet.
