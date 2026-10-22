"""Blendshape driver export, checked against Maya itself (run with mayapy).

    "C:/Program Files/Autodesk/Maya2026/bin/mayapy.exe" tests/maya_blendshape_drivers_test.py [scene.ma]

Builds a scene whose blendshape weights are driven through every supported
node type, exports the driver records, then for random slider values checks
that applying the exported ops gives exactly the weight Maya computes. With a
scene path, also prints the records found in that scene (opened read-only).
"""
import os
import random
import sys

import maya.standalone

maya.standalone.initialize(name="python")
import maya.cmds as cmds  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "maya"))
import export_rig_manifest as erm  # noqa: E402


def apply_ops(value, ops):
    """Reference evaluation of exported ops (what Unreal must reproduce)."""
    for op in ops:
        kind = op["op"]
        if kind == "mul":
            value *= op["value"]
        elif kind == "div":
            value /= op["value"]
        elif kind == "pow":
            value = value ** op["value"]
        elif kind == "add":
            value += op["value"]
        elif kind == "reverse":
            value = 1.0 - value
        elif kind == "clamp":
            value = min(max(value, op["min"]), op["max"])
        elif kind == "remap":
            (a, b), (c, d) = op["from"], op["to"]
            t = 0.0 if b == a else min(max((value - a) / (b - a), 0.0), 1.0)
            value = c + (d - c) * t
        elif kind == "curve":
            keys = op["keys"]
            if value <= keys[0][0]:
                value = keys[0][1]
            elif value >= keys[-1][0]:
                value = keys[-1][1]
            else:
                for (x0, y0), (x1, y1) in zip(keys, keys[1:]):
                    if x0 <= value <= x1:
                        value = y0 + (y1 - y0) * (value - x0) / (x1 - x0)
                        break
        elif kind == "compare":
            ok = {"eq": value == op["value"], "ne": value != op["value"], "gt": value > op["value"],
                  "ge": value >= op["value"], "lt": value < op["value"], "le": value <= op["value"]}[op["test"]]
            value = op["true"] if ok else op["false"]
        else:
            raise ValueError(kind)
    return value


def build_scene():
    cmds.file(new=True, force=True)
    base = cmds.polyCube(name="Base")[0]
    names = ["direct", "md_mul", "md_div", "reverse", "pma_sub", "pma_avg", "adl", "clamp", "setrange",
             "sdk", "unitconv", "cond_eq", "cond_swapped", "unsupported"]
    targets = []
    for n in names:
        t = cmds.duplicate(base, name="T_" + n)[0]
        cmds.move(0, 1, 0, t + ".vtx[0]", relative=True)
        targets.append(t)
    bs = cmds.blendShape(targets, base, name="TestBS")[0]
    ctrl = cmds.circle(name="ctrl")[0]
    for a in ("a", "b"):
        cmds.addAttr(ctrl, longName=a, attributeType="double", minValue=-10, maxValue=10, keyable=True)

    def w(name):
        return "{}.T_{}".format(bs, name)

    cmds.connectAttr(ctrl + ".a", w("direct"))
    md = cmds.createNode("multiplyDivide")
    cmds.setAttr(md + ".operation", 1)
    cmds.connectAttr(ctrl + ".a", md + ".input1X")
    cmds.setAttr(md + ".input2X", 0.1)
    cmds.connectAttr(md + ".outputX", w("md_mul"))
    md2 = cmds.createNode("multiplyDivide")
    cmds.setAttr(md2 + ".operation", 2)
    cmds.connectAttr(ctrl + ".a", md2 + ".input1Y")
    cmds.setAttr(md2 + ".input2Y", 4.0)
    cmds.connectAttr(md2 + ".outputY", w("md_div"))
    rv = cmds.createNode("reverse")
    cmds.connectAttr(md + ".outputX", rv + ".inputX")
    cmds.connectAttr(rv + ".outputX", w("reverse"))
    pma = cmds.createNode("plusMinusAverage")
    cmds.setAttr(pma + ".operation", 2)
    cmds.setAttr(pma + ".input1D[0]", 3.0)
    cmds.connectAttr(ctrl + ".a", pma + ".input1D[1]")
    cmds.setAttr(pma + ".input1D[2]", 0.5)
    cmds.connectAttr(pma + ".output1D", w("pma_sub"))
    pma2 = cmds.createNode("plusMinusAverage")
    cmds.setAttr(pma2 + ".operation", 3)
    cmds.connectAttr(ctrl + ".b", pma2 + ".input3D[0].input3Dx")
    cmds.setAttr(pma2 + ".input3D[1].input3Dx", 2.0)
    cmds.connectAttr(pma2 + ".output3Dx", w("pma_avg"))
    adl = cmds.createNode("addDoubleLinear")
    if cmds.nodeType(adl) == "addDoubleLinear":      # not available in every Maya build
        cmds.connectAttr(ctrl + ".b", adl + ".input1")
        cmds.setAttr(adl + ".input2", -1.5)
        cmds.connectAttr(adl + ".output", w("adl"))
    else:
        cmds.delete(adl)
    cl = cmds.createNode("clamp")
    cmds.connectAttr(ctrl + ".a", cl + ".inputR")
    cmds.setAttr(cl + ".minR", -2.0)
    cmds.setAttr(cl + ".maxR", 3.0)
    cmds.connectAttr(cl + ".outputR", w("clamp"))
    sr = cmds.createNode("setRange")
    cmds.connectAttr(ctrl + ".b", sr + ".valueX")
    for attr, value in (("oldMinX", 0.0), ("oldMaxX", 10.0), ("minX", 0.0), ("maxX", 1.0)):
        cmds.setAttr(sr + "." + attr, value)
    cmds.connectAttr(sr + ".outValueX", w("setrange"))
    cmds.setDrivenKeyframe(w("sdk"), currentDriver=ctrl + ".a", driverValue=0, value=0, inTangentType="linear",
                           outTangentType="linear")
    cmds.setDrivenKeyframe(w("sdk"), currentDriver=ctrl + ".a", driverValue=5, value=1, inTangentType="linear",
                           outTangentType="linear")
    cmds.setDrivenKeyframe(w("sdk"), currentDriver=ctrl + ".a", driverValue=10, value=0.25,
                           inTangentType="linear", outTangentType="linear")
    loc = cmds.spaceLocator(name="drv")[0]
    cmds.connectAttr(loc + ".rotateX", w("unitconv"))     # adds a unitConversion node
    cmds.addAttr(ctrl, longName="space", attributeType="enum", enumName="World:Chest:Head", keyable=True)
    eq = cmds.createNode("condition")
    cmds.connectAttr(ctrl + ".space", eq + ".firstTerm")
    cmds.setAttr(eq + ".secondTerm", 2)
    cmds.setAttr(eq + ".operation", 0)
    cmds.setAttr(eq + ".colorIfTrueR", 1)
    cmds.setAttr(eq + ".colorIfFalseR", 0)
    cmds.connectAttr(eq + ".outColorR", w("cond_eq"))
    sw = cmds.createNode("condition")
    cmds.setAttr(sw + ".firstTerm", 1.5)
    cmds.connectAttr(ctrl + ".b", sw + ".secondTerm")
    cmds.setAttr(sw + ".operation", 2)            # 1.5 > b  ->  b < 1.5
    cmds.setAttr(sw + ".colorIfTrueG", 0.25)
    cmds.setAttr(sw + ".colorIfFalseG", 0.75)
    cmds.connectAttr(sw + ".outColorG", w("cond_swapped"))
    cond = cmds.createNode("condition")
    cmds.connectAttr(ctrl + ".a", cond + ".firstTerm")
    cmds.connectAttr(ctrl + ".b", cond + ".secondTerm")
    cmds.connectAttr(cond + ".outColorR", w("unsupported"))
    return bs, ctrl, loc


def driven_channels():
    """Slider -> maths -> a group's translate/rotate (the petals), in cm and in m scenes."""
    for unit in ("cm", "m"):
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear=unit)
        ctrl = cmds.circle(name="settings")[0]
        cmds.addAttr(ctrl, longName="open", attributeType="double", minValue=0, maxValue=10, keyable=True)
        group = cmds.group(empty=True, name="petal_offset")
        md = cmds.createNode("multiplyDivide")
        cmds.connectAttr(ctrl + ".open", md + ".input1X")
        cmds.setAttr(md + ".input2X", 0.2)
        cmds.connectAttr(ctrl + ".open", md + ".input1Z")
        cmds.setAttr(md + ".input2Z", 8.0)
        cmds.connectAttr(md + ".outputX", group + ".translateY")     # Maya adds unitConversion nodes
        cmds.connectAttr(md + ".outputZ", group + ".rotateX")
        for channel in ("translateY", "rotateX"):
            control, attribute, ops = erm._attribute_driver("{}.{}".format(group, channel))
            assert (control, attribute) == ("settings", "open"), (control, attribute, ops)
            for value in (0.0, 3.7, 10.0):
                cmds.setAttr(ctrl + ".open", value)
                got, want = apply_ops(value, ops), cmds.getAttr("{}.{}".format(group, channel))
                assert abs(got - want) < 1e-6, (unit, channel, ops, value, got, want)
    print("DRIVEN CHANNELS OK (cm and m scenes)")


def main():
    bs, ctrl, loc = build_scene()
    records = {r["target"]: r for r in erm._blendshape_records(only_registered=False) if r["blendshape"] == bs}
    assert records["T_unsupported"].get("unsupported"), records["T_unsupported"]
    assert records["T_unitconv"]["driver"]["control"] == "drv"
    rng = random.Random(1)
    worst = 0.0
    for _ in range(40):
        values = {"a": rng.uniform(-10, 10), "b": rng.uniform(-10, 10), "rotateX": rng.uniform(-90, 90)}
        cmds.setAttr(ctrl + ".space", rng.randint(0, 2))
        cmds.setAttr(ctrl + ".a", values["a"])
        cmds.setAttr(ctrl + ".b", values["b"])
        cmds.setAttr(loc + ".rotateX", values["rotateX"])
        for target, record in records.items():
            if record.get("unsupported") or not record.get("driver"):
                continue
            driver = record["driver"]
            plug_value = cmds.getAttr("{}.{}".format(driver["control"], driver["attr"]))
            expected = cmds.getAttr("{}.{}".format(bs, target))
            got = apply_ops(plug_value, record["ops"])
            worst = max(worst, abs(got - expected))
            assert abs(got - expected) < 1e-5, (target, record["ops"], plug_value, got, expected)
    driven_channels()
    print("BLENDSHAPE DRIVERS OK ({} supported targets, worst difference {:.2e})".format(
        sum(1 for r in records.values() if r.get("driver")), worst))

    if len(sys.argv) > 1:
        cmds.file(sys.argv[1], open=True, force=True, ignoreVersion=True)
        for record in erm._blendshape_records(only_registered=False):
            print("SCENE", record["blendshape"], record["target"], "->",
                  record.get("driver"), record.get("ops"), record.get("unsupported") or "")


main()
maya.standalone.uninitialize()
