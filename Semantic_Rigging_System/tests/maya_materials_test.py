"""Materials export and blendshape-target exclusion, in Maya (run with mayapy).

    "C:/Program Files/Autodesk/Maya2026/bin/mayapy.exe" tests/maya_materials_test.py

  * material_records: lambert (diffuse 0.5), blinn, standardSurface (base
    0.7), per-face assignment, a textured and a transparent material reported;
  * colour conversion: ACEScg -> linear sRGB keeps white white; colour x weight;
  * blendshape target meshes stay in the export: an FBX round trip keeps the
    target names (Unreal's morph target names) and the material names.
"""
import os
import sys
import tempfile

import maya.standalone

maya.standalone.initialize(name="python")
import maya.cmds as cmds  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools", "maya"))
import export_rig_manifest as erm  # noqa: E402

white, problem = erm.to_linear_srgb([1.0, 1.0, 1.0], "ACEScg")
assert problem is None and all(abs(c - 1.0) < 2e-3 for c in white), white
same, problem = erm.to_linear_srgb([0.2, 0.4, 0.6], "scene-linear Rec.709-sRGB")
assert same == [0.2, 0.4, 0.6] and problem is None
_, problem = erm.to_linear_srgb([0.2, 0.4, 0.6], "Some Custom Space")
assert problem and "unknown rendering space" in problem


def material(kind, name, color, weight=None):
    node = cmds.shadingNode(kind, asShader=True, name=name)
    engine = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(node + ".outColor", engine + ".surfaceShader")
    attr = "baseColor" if kind == "standardSurface" else "color"
    cmds.setAttr("{}.{}".format(node, attr), *color, type="double3")
    if weight is not None:
        cmds.setAttr("{}.{}".format(node, "base" if kind == "standardSurface" else "diffuse"), weight)
    return node, engine


cmds.file(new=True, force=True)
cmds.loadPlugin("fbxmaya", quiet=True)
cmds.select(clear=True)
root = cmds.joint(name="root")
body = cmds.polyCube(name="GEO_Body", subdivisionsX=2)[0]
cmds.skinCluster(root, body, toSelectedBones=True)
target = cmds.duplicate(body, name="Body_BS_Smile")[0]
cmds.move(0, 1, 0, target + ".vtx[0]", relative=True)
cmds.blendShape(target, body, name="BodyBS")
cmds.setAttr(target + ".visibility", 0)
lam, lam_sg = material("lambert", "M_Skin", (0.8, 0.6, 0.4), weight=0.5)
std, std_sg = material("standardSurface", "M_Cloth", (0.1, 0.2, 0.9), weight=0.7)
cmds.sets(body + ".f[0:3]", edit=True, forceElement=lam_sg)
cmds.sets(body + ".f[4:9]", edit=True, forceElement=std_sg)
other = cmds.polySphere(name="GEO_Ball")[0]
cmds.skinCluster(root, other, toSelectedBones=True)
blinn, blinn_sg = material("blinn", "M_Ball", (0.3, 0.3, 0.3))
cmds.sets(other, edit=True, forceElement=blinn_sg)
cmds.setAttr(blinn + ".transparency", 0.5, 0.5, 0.5, type="double3")
tex = cmds.shadingNode("file", asTexture=True, name="skin_tex")
leaf = cmds.polyPlane(name="GEO_Leaf")[0]
cmds.skinCluster(root, leaf, toSelectedBones=True)
leaf_mat, leaf_sg = material("lambert", "M_Leaf", (0.0, 1.0, 0.0))
cmds.connectAttr(tex + ".outColor", leaf_mat + ".color")
cmds.sets(leaf, edit=True, forceElement=leaf_sg)

meshes = erm.collect_visible_mesh_transforms()
names = sorted(m.split("|")[-1] for m in meshes)
assert names == ["Body_BS_Smile", "GEO_Ball", "GEO_Body", "GEO_Leaf"], names   # targets kept (see below)
records = {r["name"]: r for r in erm.material_records(meshes)}
# (the target mesh keeps Maya's default shader, which is listed too)
assert {"M_Ball", "M_Cloth", "M_Leaf", "M_Skin"} <= set(records), sorted(records)
assert records["M_Skin"]["meshes"] == ["GEO_Body"] and records["M_Cloth"]["meshes"] == ["GEO_Body"]
space = records["M_Skin"]["color_space"]
expected, _ = erm.to_linear_srgb([0.4, 0.3, 0.2], space)                # colour x diffuse 0.5
assert records["M_Skin"]["color_unreal"] == expected, (records["M_Skin"], expected)
expected, _ = erm.to_linear_srgb([0.07, 0.14, 0.63], space)             # baseColor x base 0.7
assert all(abs(a - b) < 1e-5 for a, b in zip(records["M_Cloth"]["color_unreal"], expected))
assert any("transparency" in p for p in records["M_Ball"]["problems"])
assert any("texture" in p for p in records["M_Leaf"]["problems"]) and records["M_Leaf"]["texture"] == "skin_tex"
print("materials:", {n: (r["type"], r["color_unreal"]) for n, r in records.items()}, "space:", space)

folder = tempfile.mkdtemp()
fbx = os.path.join(folder, "materials_test.fbx").replace("\\", "/")
erm.export_fbx(fbx, [cmds.ls(root, long=True)[0]] + meshes)
cmds.file(new=True, force=True)
cmds.file(fbx, i=True, type="FBX", ignoreVersion=True)
shapes = {bs: cmds.listAttr(bs + ".w", multi=True) for bs in cmds.ls(type="blendShape")}
assert any("Body_BS_Smile" in (targets or []) for targets in shapes.values()), shapes
imported = set(cmds.ls(materials=True))
assert {"M_Skin", "M_Cloth", "M_Ball", "M_Leaf"} <= imported, imported
print("FBX round trip: blendshapes", shapes, "| materials present")
print("MATERIALS OK")
maya.standalone.uninitialize()
