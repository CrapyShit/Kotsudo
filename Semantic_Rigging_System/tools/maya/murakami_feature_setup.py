"""Test setups on the Murakami rig for space switching and driven offset groups.

Run in Maya (Script Editor, Python tab) on the Murakami scene:

    import murakami_feature_setup as mfs
    mfs.setup_all()          # adds both setups (safe to run twice)
    mfs.remove_all()         # takes them out again

Nothing moves at rest: every new group is created where the rig already is,
and the default values select the current behaviour.

1. Space switch on the arm IK controls
   A group ``<side>_ArmIKctrl_space`` is inserted above ``<side>_ArmIKctrl_grp``
   (under world_ctrl) and parent-constrained to four spaces, chosen with a
   "Space" enum on the IK control: World (a locator outside the controls),
   Chest (chest_ctrl), Head (head_ctrl), Pelvis (Pelvis_IKctrl).
   The two arms use two common wirings, so both get tested:
     * left arm:  enum -> condition nodes (Space == i -> 1, else 0)
     * right arm: enum -> set driven keys on each weight

2. Driven offset groups on the neck ("curl on the first control")
   A "Neck_Curl" slider (-10..10) on neck_ctrl_01 bends the rest of the
   neck. A group ``neck_ctrl_drv_0N`` is inserted between neck_ctrl_grp_0N
   and neck_ctrl_0N (N = 2..5), with rotate order yzx so the rotate-order
   maths is exercised:
     * rotateZ <- Neck_Curl through set driven keys (-10 -> -12 deg, 10 -> +12 deg)
     * rotateX <- Neck_Curl through a multiplyDivide (x 1.5 deg)
   The static ``_grp`` groups stay the zero groups.

After setup: tag nothing new (the modules don't change), export as usual,
build in Unreal, and read the pose report: the Space enum is probed on each
value and Neck_Curl at its limits.
"""

import maya.cmds as cmds

SIDES = ("L", "R")
SPACES = (("World", None), ("Chest", "chest_ctrl"), ("Head", "head_ctrl"), ("Pelvis", "Pelvis_IKctrl"))
NECK_DRIVER = "neck_ctrl_01"
NECK_DRIVEN = (2, 3, 4, 5)
CURL_KEYS = ((-10.0, -12.0), (0.0, 0.0), (10.0, 12.0))   # (Neck_Curl, rotateZ degrees)
TWIST_FACTOR = 1.5                                         # rotateX degrees per Neck_Curl unit
TAG = "kotsudoFeatureTest"                                 # marks every node this script creates


def _tag(node):
    if not cmds.attributeQuery(TAG, node=node, exists=True):
        cmds.addAttr(node, longName=TAG, attributeType="bool", defaultValue=True)
    return node


def _insert_group(child, name, rotate_order=None):
    """Group between ``child`` and its parent, at the child's parent's frame
    (identity local transform), so nothing moves."""
    parent = cmds.listRelatives(child, parent=True, fullPath=True)
    group = cmds.group(empty=True, name=name, parent=parent[0]) if parent else cmds.group(empty=True, name=name)
    if rotate_order is not None:
        cmds.setAttr(group + ".rotateOrder", rotate_order)
    cmds.parent(child, group)
    return _tag(group)


# ---------------------------------------------------------------------------
# 1. Space switch on the arm IK controls
# ---------------------------------------------------------------------------

def setup_arm_spaces():
    for side in SIDES:
        ctrl, zero = "{}_ArmIKctrl".format(side), "{}_ArmIKctrl_grp".format(side)
        space_grp = "{}_ArmIKctrl_space".format(side)
        if cmds.objExists(space_grp):
            print("[Kotsudo test] {} already has a space switch; skipped.".format(ctrl))
            continue
        group = _insert_group(zero, space_grp)
        # World space: a locator outside every controller, where the space group is.
        world_parent = cmds.listRelatives("world_ctrl_grp", parent=True)[0]   # world_orig
        world = cmds.spaceLocator(name="{}_ArmIK_space_World_loc".format(side))[0]
        cmds.parent(world, world_parent)
        cmds.matchTransform(world, group)
        cmds.setAttr(world + ".visibility", 0)
        _tag(world)
        targets = [world if node is None else node for _, node in SPACES]
        constraint = cmds.parentConstraint(targets, group, maintainOffset=True,
                                           name="{}_ArmIKctrl_space_parentConstraint".format(side))[0]
        _tag(constraint)
        weights = cmds.parentConstraint(constraint, query=True, weightAliasList=True)
        cmds.addAttr(ctrl, longName="Space", attributeType="enum",
                     enumName=":".join(label for label, _ in SPACES), keyable=True, defaultValue=0)
        if side == "L":
            for index, weight in enumerate(weights):
                condition = _tag(cmds.createNode("condition", name="{}_ArmIK_space{}_cond".format(side, index)))
                cmds.setAttr(condition + ".operation", 0)           # equal
                cmds.setAttr(condition + ".secondTerm", index)
                cmds.setAttr(condition + ".colorIfTrueR", 1)
                cmds.setAttr(condition + ".colorIfFalseR", 0)
                cmds.connectAttr(ctrl + ".Space", condition + ".firstTerm")
                cmds.connectAttr(condition + ".outColorR", "{}.{}".format(constraint, weight), force=True)
        else:
            for index, weight in enumerate(weights):
                for value in range(len(SPACES)):
                    cmds.setDrivenKeyframe("{}.{}".format(constraint, weight), currentDriver=ctrl + ".Space",
                                           driverValue=value, value=1.0 if value == index else 0.0,
                                           inTangentType="linear", outTangentType="linear")
                for curve in cmds.listConnections("{}.{}".format(constraint, weight), type="animCurve") or []:
                    _tag(curve)
        print("[Kotsudo test] {}: Space = {} ({}).".format(
            ctrl, " / ".join(label for label, _ in SPACES),
            "condition nodes" if side == "L" else "set driven keys"))


def remove_arm_spaces():
    for side in SIDES:
        ctrl, zero = "{}_ArmIKctrl".format(side), "{}_ArmIKctrl_grp".format(side)
        space_grp = "{}_ArmIKctrl_space".format(side)
        if not cmds.objExists(space_grp):
            continue
        cmds.setAttr(ctrl + ".Space", 0)
        parent = cmds.listRelatives(space_grp, parent=True)[0]
        constraints = cmds.listRelatives(space_grp, type="parentConstraint") or []
        if constraints:
            cmds.delete(constraints)
        cmds.parent(zero, parent)
        cmds.delete(space_grp)
        for node in cmds.ls("{}_ArmIK_space*".format(side)):
            if cmds.objExists(node):
                cmds.delete(node)
        if cmds.attributeQuery("Space", node=ctrl, exists=True):
            cmds.deleteAttr(ctrl, attribute="Space")
        print("[Kotsudo test] {}: space switch removed.".format(ctrl))


# ---------------------------------------------------------------------------
# 2. Driven offset groups on the neck
# ---------------------------------------------------------------------------

def setup_neck_curl():
    if cmds.attributeQuery("Neck_Curl", node=NECK_DRIVER, exists=True):
        print("[Kotsudo test] {} already has Neck_Curl; skipped.".format(NECK_DRIVER))
        return
    cmds.addAttr(NECK_DRIVER, longName="Neck_Curl", attributeType="double", minValue=-10, maxValue=10,
                 defaultValue=0, keyable=True)
    twist = _tag(cmds.createNode("multiplyDivide", name="neck_curl_twist_mult"))
    cmds.connectAttr(NECK_DRIVER + ".Neck_Curl", twist + ".input1X")
    cmds.setAttr(twist + ".input2X", TWIST_FACTOR)
    for index in NECK_DRIVEN:
        ctrl = "neck_ctrl_{:02d}".format(index)
        drv = _insert_group(ctrl, "neck_ctrl_drv_{:02d}".format(index), rotate_order=1)   # yzx
        for driver_value, angle in CURL_KEYS:
            cmds.setDrivenKeyframe(drv + ".rotateZ", currentDriver=NECK_DRIVER + ".Neck_Curl",
                                   driverValue=driver_value, value=angle,
                                   inTangentType="linear", outTangentType="linear")
        for curve in cmds.listConnections(drv + ".rotateZ", type="animCurve") or []:
            _tag(curve)
        cmds.connectAttr(twist + ".outputX", drv + ".rotateX")
    print("[Kotsudo test] {}.Neck_Curl drives neck_ctrl_drv_02..05 (rotateZ by driven keys, "
          "rotateX x {} by multiplyDivide, rotate order yzx).".format(NECK_DRIVER, TWIST_FACTOR))


def remove_neck_curl():
    if not cmds.attributeQuery("Neck_Curl", node=NECK_DRIVER, exists=True):
        return
    cmds.setAttr(NECK_DRIVER + ".Neck_Curl", 0)
    for index in NECK_DRIVEN:
        ctrl, drv = "neck_ctrl_{:02d}".format(index), "neck_ctrl_drv_{:02d}".format(index)
        if not cmds.objExists(drv):
            continue
        parent = cmds.listRelatives(drv, parent=True)[0]
        for curve in cmds.listConnections(drv + ".rotateZ", type="animCurve") or []:
            cmds.delete(curve)
        cmds.parent(ctrl, parent)
        cmds.delete(drv)
    if cmds.objExists("neck_curl_twist_mult"):
        cmds.delete("neck_curl_twist_mult")
    cmds.deleteAttr(NECK_DRIVER, attribute="Neck_Curl")
    print("[Kotsudo test] Neck_Curl removed.")


# ---------------------------------------------------------------------------

def setup_all():
    cmds.undoInfo(openChunk=True, chunkName="Kotsudo feature tests")
    try:
        setup_arm_spaces()
        setup_neck_curl()
    finally:
        cmds.undoInfo(closeChunk=True)


def remove_all():
    cmds.undoInfo(openChunk=True, chunkName="Remove Kotsudo feature tests")
    try:
        remove_arm_spaces()
        remove_neck_curl()
        leftovers = [n for n in cmds.ls("*.{}".format(TAG), objectsOnly=True) or [] if cmds.objExists(n)]
        if leftovers:
            cmds.delete(leftovers)
    finally:
        cmds.undoInfo(closeChunk=True)
