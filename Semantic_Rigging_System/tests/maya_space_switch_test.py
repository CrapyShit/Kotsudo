"""Space switching export, checked against Maya itself (run with mayapy).

    "C:/Program Files/Autodesk/Maya2026/bin/mayapy.exe" tests/maya_space_switch_test.py

Builds the space-switch set-ups studios commonly use and checks what the
exporter describes:
  * hand_ctrl  - enum World/Chest/Head -> condition nodes -> parentConstraint
                 weights; targets are a world locator, a controller and a
                 joint; one target's offset edited so the spaces disagree.
  * elbow_ctrl - enum -> driven keys -> parentConstraint weights.
  * aim_ctrl   - float "follow" (+ reverse) -> orientConstraint (rotation space).
  * matrix_ctrl- space through offsetParentMatrix: must be REPORTED, not guessed.
For every driver value the exported maths must equal Maya's actual weights.
"""
import math
import os
import sys

import maya.standalone

maya.standalone.initialize(name="python")
import maya.cmds as cmds  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools", "maya"))
sys.path.insert(0, HERE)
import export_rig_manifest as erm  # noqa: E402
from driver_ops_reference import apply_ops  # noqa: E402


def control(name, position, parent=None):
    node = cmds.circle(name=name, normal=(0, 1, 0))[0]
    zero = cmds.group(empty=True, name=name + "_zero")
    space = cmds.group(empty=True, name=name + "_space")
    cmds.parent(node, space)
    cmds.parent(space, zero)
    cmds.xform(zero, worldSpace=True, translation=position)
    if parent:
        cmds.parent(zero, parent)
    return node, space


def build():
    cmds.file(new=True, force=True)
    cmds.select(clear=True)
    root = cmds.joint(name="root", position=(0, 0, 0))
    chest = cmds.joint(name="chest_jnt", position=(0, 10, 0))
    head = cmds.joint(name="head_jnt", position=(0, 15, 0))
    cmds.select(clear=True)
    world_loc = cmds.spaceLocator(name="world_space")[0]
    chest_ctrl, _ = control("chest_ctrl", (0, 10, 0))
    cmds.parentConstraint(chest_ctrl, chest, maintainOffset=True)

    # hand: enum through condition nodes, three kinds of targets
    hand, hand_space = control("hand_ctrl", (5, 12, 0), parent=None)
    cmds.addAttr(hand, longName="space", attributeType="enum", enumName="World:Chest:Head", keyable=True)
    con = cmds.parentConstraint(world_loc, chest_ctrl, head, hand_space, maintainOffset=True)[0]
    aliases = cmds.parentConstraint(con, query=True, weightAliasList=True)
    for index, alias in enumerate(aliases):
        cond = cmds.createNode("condition", name="hand_space_is_{}".format(index))
        cmds.connectAttr(hand + ".space", cond + ".firstTerm")
        cmds.setAttr(cond + ".secondTerm", index)
        cmds.setAttr(cond + ".colorIfTrueR", 1)
        cmds.setAttr(cond + ".colorIfFalseR", 0)
        cmds.connectAttr(cond + ".outColorR", "{}.{}".format(con, alias))
    offset = con + ".target[2].targetOffsetTranslateX"
    cmds.setAttr(offset, cmds.getAttr(offset) + 2.0)                 # the Head space disagrees by 2 units

    # elbow: enum through driven keys
    elbow, elbow_space = control("elbow_ctrl", (3, 11, 0))
    cmds.addAttr(elbow, longName="space", attributeType="enum", enumName="Chest:World", keyable=True)
    con2 = cmds.parentConstraint(chest_ctrl, world_loc, elbow_space, maintainOffset=True)[0]
    a0, a1 = cmds.parentConstraint(con2, query=True, weightAliasList=True)
    for driver_value, (w0, w1) in ((0, (1, 0)), (1, (0, 1))):
        cmds.setDrivenKeyframe("{}.{}".format(con2, a0), currentDriver=elbow + ".space", driverValue=driver_value,
                               value=w0, inTangentType="linear", outTangentType="linear")
        cmds.setDrivenKeyframe("{}.{}".format(con2, a1), currentDriver=elbow + ".space", driverValue=driver_value,
                               value=w1, inTangentType="linear", outTangentType="linear")

    # aim: orient-only space with a float follow slider and a reverse node
    aim, aim_space = control("aim_ctrl", (0, 16, 2))
    cmds.addAttr(aim, longName="follow", attributeType="double", minValue=0, maxValue=1, keyable=True)
    con3 = cmds.orientConstraint(head, world_loc, aim_space, maintainOffset=True)[0]
    b0, b1 = cmds.orientConstraint(con3, query=True, weightAliasList=True)
    rev = cmds.createNode("reverse")
    cmds.connectAttr(aim + ".follow", "{}.{}".format(con3, b0))
    cmds.connectAttr(aim + ".follow", rev + ".inputX")
    cmds.connectAttr(rev + ".outputX", "{}.{}".format(con3, b1))

    # matrix-driven space
    matrix_ctrl, matrix_space = control("matrix_ctrl", (-4, 12, 0))
    mult = cmds.createNode("multMatrix")
    cmds.connectAttr(chest_ctrl + ".worldMatrix[0]", mult + ".matrixIn[0]")
    cmds.connectAttr(mult + ".matrixSum", matrix_space + ".offsetParentMatrix")
    return {"hand": (hand, con), "elbow": (elbow, con2), "aim": (aim, con3), "matrix": matrix_ctrl}


def actual_weights(constraint, targets):
    return [cmds.getAttr("{}.target[{}].targetWeight".format(constraint, t["index"])) for t in targets]


def check_weights(name, driver_plug, values, blend, constraint):
    for value in values:
        cmds.setAttr(driver_plug, value)
        want = actual_weights(constraint, blend["targets"])
        got = [apply_ops(cmds.getAttr("{}.{}".format(t["weight"]["control"], t["weight"]["attr"])),
                         t["weight"].get("ops")) if "attr" in t["weight"] else t["weight"]["value"]
               for t in blend["targets"]]
        assert all(abs(a - b) < 1e-6 for a, b in zip(got, want)), (name, value, got, want)
    cmds.setAttr(driver_plug, values[0])


rig = build()

hand, con = rig["hand"]
blend, reason = erm.describe_space(hand)
assert reason is None and blend["kind"] == "parent", (blend, reason)
kinds = [next(k for k in ("controller", "bone", "world") if k in t) for t in blend["targets"]]
assert kinds == ["world", "controller", "bone"], kinds
assert blend["switch"]["labels"] == ["World", "Chest", "Head"] and blend["switch"]["values"] == [0.0, 1.0, 2.0], \
    blend["switch"]
check_weights("hand", hand + ".space", [0, 1, 2], blend, con)
rest = blend["rest"]["position"]
shifts = [math.dist(rest, t["solo"]["position"]) for t in blend["targets"]]
assert shifts[0] < 1e-3 and shifts[1] < 1e-3 and abs(shifts[2] - 2.0) < 1e-3, shifts      # scene in cm
print("hand_ctrl: parent space, targets", kinds, "labels", blend["switch"]["labels"], "per-space shifts",
      [round(x, 3) for x in shifts])

elbow, con2 = rig["elbow"]
blend, reason = erm.describe_space(elbow)
assert reason is None and blend["switch"]["labels"] == ["Chest", "World"], (blend, reason)
assert all(t["weight"]["ops"][0]["op"] == "curve" for t in blend["targets"])
check_weights("elbow", elbow + ".space", [0, 1], blend, con2)
print("elbow_ctrl: driven keys ->", [erm.describe_ops(t["weight"]["ops"]) for t in blend["targets"]])

aim, con3 = rig["aim"]
blend, reason = erm.describe_space(aim)
assert reason is None and blend["kind"] == "orient", (blend, reason)
assert [t["weight"].get("invert") for t in blend["targets"]] == [False, True]
check_weights("aim", aim + ".follow", [0.0, 0.25, 1.0], blend, con3)
assert blend["switch"]["values"] == [1.0, 0.0], blend["switch"]
print("aim_ctrl: orient space, follow =", blend["switch"]["values"], "selects", [t["node"] for t in blend["targets"]])

blend, reason = erm.describe_space(rig["matrix"])
assert blend is None and "offsetParentMatrix" in reason, (blend, reason)
print("matrix_ctrl: reported ->", reason)
print("SPACE SWITCH EXPORT OK")
maya.standalone.uninitialize()
