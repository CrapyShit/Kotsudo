"""Driven offset groups, checked against Maya itself (run with mayapy).

    "C:/Program Files/Autodesk/Maya2026/bin/mayapy.exe" tests/maya_driven_groups_test.py

Builds controllers whose offset groups are driven by settings sliders
through multiplyDivide nodes (like Murakami's petals) -- with random rotate
orders and rotateAxis, a driven joint with jointOrient, rotated static
groups above, in cm and m scenes -- and checks:
  * the exporter classifies the stack (static / driven) and finds each
    driven channel's slider and maths;
  * the Unreal-side maths (rig_builder/driven_groups.local_unreal, applied as
    L(values) o L(rest)^-1 o G_rest) gives the world pose Maya computes, for
    random slider values.
"""
import math
import os
import random
import sys

import maya.standalone

maya.standalone.initialize(name="python")
import maya.cmds as cmds  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools", "maya"))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import export_rig_manifest as erm  # noqa: E402
import export_test_poses as etp  # noqa: E402
from driver_ops_reference import apply_ops  # noqa: E402
from rig_builder import driven_groups as dg  # noqa: E402


def angle(a, b):
    """Angle between two rotations; normalised + atan2 (acos near 1 turns
    the 6-decimal rounding of exported quaternions into a fake ~0.1 deg)."""
    a = [c / math.sqrt(sum(x * x for x in a)) for c in a]
    b = [c / math.sqrt(sum(x * x for x in b)) for c in b]
    d = dg.q_mul([-a[0], -a[1], -a[2], a[3]], b)
    return math.degrees(2.0 * math.atan2(math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2), abs(d[3])))


def build(rng, use_joint):
    settings = cmds.circle(name="settings_ctrl")[0]
    for attr in ("open", "twist"):
        if not cmds.attributeQuery(attr, node=settings, exists=True):
            cmds.addAttr(settings, longName=attr, attributeType="double", minValue=-10, maxValue=10, keyable=True)
    parent = cmds.circle(name="parent_ctrl#")[0]
    cmds.xform(parent, worldSpace=True, translation=[rng.uniform(-5, 5) for _ in range(3)],
               rotation=[rng.uniform(-90, 90) for _ in range(3)])
    static = cmds.group(empty=True, name="petal_grp#", parent=parent)
    cmds.xform(static, objectSpace=True, translation=[rng.uniform(-3, 3) for _ in range(3)],
               rotation=[rng.uniform(-180, 180) for _ in range(3)])
    if use_joint:
        cmds.select(clear=True)
        driven = cmds.joint(name="petal_NULL_jnt#")
        cmds.parent(driven, static, relative=True)
        cmds.setAttr(driven + ".jointOrient", *[rng.uniform(-60, 60) for _ in range(3)])
    else:
        driven = cmds.group(empty=True, name="petal_NULL#", parent=static)
    cmds.setAttr(driven + ".rotateOrder", rng.randint(0, 5))
    cmds.setAttr(driven + ".rotateAxis", *[rng.uniform(-45, 45) for _ in range(3)])
    cmds.setAttr(driven + ".translate", *[rng.uniform(-1, 1) for _ in range(3)])
    cmds.setAttr(driven + ".rotate", *[rng.uniform(-30, 30) for _ in range(3)])
    md = cmds.createNode("multiplyDivide")
    cmds.connectAttr(settings + ".open", md + ".input1X")
    cmds.setAttr(md + ".input2X", 0.2)
    cmds.connectAttr(settings + ".open", md + ".input1Y")
    cmds.setAttr(md + ".input2Y", 8.0)
    cmds.connectAttr(settings + ".twist", md + ".input1Z")
    cmds.setAttr(md + ".input2Z", -5.0)
    cmds.connectAttr(md + ".outputX", driven + ".translateY")
    cmds.connectAttr(md + ".outputY", driven + ".rotateX")
    cmds.connectAttr(md + ".outputZ", driven + ".rotateZ")
    control = cmds.circle(name="petal_ctrl#")[0]
    cmds.parent(control, driven, relative=True)
    return settings, control, driven


def check(unit, rng):
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear=unit)
    worst_cm = worst_deg = 0.0
    for trial in range(6):
        settings, control, driven = build(rng, use_joint=(trial % 2 == 1))
        for attr in ("open", "twist"):
            cmds.setAttr("{}.{}".format(settings, attr), 0.0)
        stack = erm.offset_stack(control)
        kinds = [g["kind"] for g in stack]
        assert kinds[:2] == ["driven", "static"], kinds
        group = stack[0]
        assert sorted(group["driven"]) == ["rotateX", "rotateZ", "translateY"], group["driven"]
        assert not group["problems"], group["problems"]
        rest_world = dg.pose_to_transform(group["rest_world"])
        rest_local = dg.local_unreal(group, group["rest"])
        for _ in range(8):
            sliders = {"open": rng.uniform(-10, 10), "twist": rng.uniform(-10, 10)}
            for attr, value in sliders.items():
                cmds.setAttr("{}.{}".format(settings, attr), value)
            values = dict(group["rest"])
            for channel, driver in group["driven"].items():
                values[channel] = apply_ops(sliders[driver["attr"]], driver["ops"])
                maya_value = cmds.getAttr("{}.{}".format(driven, channel))
                assert abs(values[channel] - maya_value) < 1e-4, (channel, values[channel], maya_value)
            predicted = dg.compose(dg.compose(dg.local_unreal(group, values), dg.inverse(rest_local)), rest_world)
            position, rotation = etp.world_state(driven)
            worst_cm = max(worst_cm, math.dist(predicted[1], position))
            worst_deg = max(worst_deg, angle(predicted[0], rotation))
        for attr in ("open", "twist"):
            cmds.setAttr("{}.{}".format(settings, attr), 0.0)
    assert worst_cm < 1e-3 and worst_deg < 1e-3, (unit, worst_cm, worst_deg)
    print("{} scene: worst {:.2e} cm / {:.2e} deg over 48 poses (6 rigs, groups and joints)".format(
        unit, worst_cm, worst_deg))


rng = random.Random(11)
for scene_unit in ("cm", "m"):
    check(scene_unit, rng)
print("DRIVEN GROUPS OK")
maya.standalone.uninitialize()
