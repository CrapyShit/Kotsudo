"""Rig Tagger window smoke test, offscreen (run with mayapy on a scene copy).

    "C:/Program Files/Autodesk/Maya2026/bin/mayapy.exe" tests/maya_tool_ui_test.py <scene_copy.ma>

Opens the scene (never saved), builds the real tool window without a screen,
and checks the Blendshapes tab: listing, registration through the checkboxes,
target exclusion, and that the export only takes what is registered.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtWidgets

# The GUI application must exist before Maya starts its own (non-GUI) one.
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
import maya.standalone  # noqa: E402

maya.standalone.initialize(name="python")
import maya.cmds as cmds  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "maya"))
import export_rig_manifest as erm  # noqa: E402
import rig_tagger_tool  # noqa: E402

cmds.file(sys.argv[1], open=True, force=True, ignoreVersion=True)
for blendshape in cmds.ls(type="blendShape"):
    for attr in (erm.BLENDSHAPE_EXPORT_ATTR, erm.BLENDSHAPE_EXCLUDED_ATTR):
        if cmds.attributeQuery(attr, node=blendshape, exists=True):
            cmds.deleteAttr(blendshape, attribute=attr)

window = rig_tagger_tool.RigTaggerWindow()
tabs = [window._tabs.tabText(i) for i in range(window._tabs.count())]
assert tabs == ["Modules", "Blendshapes", "Checks"], tabs
assert window._module_tree.topLevelItemCount() > 0, "modules tab is empty"
tree = window._bs_tree
nodes = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
print("UI nodes:", [n.text(0) for n in nodes], "| summary:", window._bs_summary.text())
assert len(nodes) == 3 and sum(n.childCount() for n in nodes) == 10
assert erm._blendshape_records() == [], "nothing registered yet, nothing exported"

face = next(n for n in nodes if n.text(0).startswith("Face"))
face.setCheckState(0, QtCore.Qt.Checked)               # register through the checkbox
app.processEvents()
assert erm.blendshape_registered("Face")
assert len(erm._blendshape_records()) == 4

nodes = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
face = next(n for n in nodes if n.text(0).startswith("Face"))
smile = next(face.child(i) for i in range(face.childCount()) if face.child(i).text(0) == "Head_BS_Smile")
print("UI Smile row:", [smile.text(c) for c in range(4)])
assert smile.text(1) == "head_ctrl.BS_Smile" and smile.text(2) == "x 0.1" and smile.text(3).startswith("slider")
smile.setCheckState(0, QtCore.Qt.Unchecked)            # exclude one target
app.processEvents()
records = erm._blendshape_records()
assert sorted(r["target"] for r in records) == ["Head_BS_CloseMouth", "Head_BS_Disgusting", "Head_BS_Omouth"]

window._register_all_blendshapes()
app.processEvents()
assert len(erm._blendshape_records()) == 9                     # Smile still excluded
print("UI summary after Register All:", window._bs_summary.text())
# --- 1 + 6: Analyze Scene -> controllers per module, Checks tab (twice) -----
import json
import tempfile
for _ in range(2):
    window._analyze_scene(quiet=True)
    app.processEvents()
checks = [window._checks_tree.topLevelItem(i) for i in range(window._checks_tree.topLevelItemCount())]
subjects = [c.text(1) for c in checks]
print("UI checks:", window._checks_summary.text(), subjects[:5])
# The petal sliders drive offset groups, which are transferred now: not flagged.
assert not any(s.startswith("Head_Settings_Ctrl.Petal") for s in subjects), subjects


def module_row(name):
    for g in range(window._module_tree.topLevelItemCount()):
        group = window._module_tree.topLevelItem(g)
        for m in range(group.childCount()):
            if group.child(m).text(0).endswith(name):
                return group.child(m)
    raise AssertionError(name)


spine = module_row("  Spine")
branch = next(spine.child(i) for i in range(spine.childCount()) if spine.child(i).text(0).startswith("Controllers"))
names = [branch.child(i).text(0) for i in range(branch.childCount())]
print("UI Spine controllers:", branch.text(0), names)
assert set(names) == {"Pelvis_IKctrl", "spine_ctrl_01", "chest_ctrl"}
petal = module_row("  PetalPurple")
petal_branch = next(petal.child(i) for i in range(petal.childCount())
                    if petal.child(i).text(0).startswith("Controllers"))
petal_details = petal_branch.child(0).text(2)
print("UI petal controller:", petal_details)
assert "pedal_NULLctrl_01 driven (translateY <- Head_Settings_Ctrl.Petal_Translate x 0.2" in petal_details

# --- 2-5: Setup branch (IK/FK, spline, constraints, parent spaces) ----------
def setup_rows(module):
    row = module_row("  " + module)
    group = next(row.child(i) for i in range(row.childCount()) if row.child(i).text(0).startswith("Setup"))
    return [(group.child(i).text(0), group.child(i).text(2)) for i in range(group.childCount())]


leg = dict(setup_rows("L_LegLeaf"))
print("UI leg setup:", leg)
assert leg["IK/FK switch"].startswith("L_Leg_IKFK_Switch.IK_FK") and leg["Pole vector"] == "L_LegPV"
spine_rows = setup_rows("Spine")
print("UI spine setup:", spine_rows)
assert any(label == "Curve point 1" and "%" in value for label, value in spine_rows)
assert any(label == "Constraint" and value.startswith("Spine4: orient -> chest_ctrl") for label, value in spine_rows)
toe = setup_rows("L_LegLeafToe")
print("UI toe setup:", toe)
assert any(label == "Per-target offset" and "1.011 cm" in value for label, value in toe)

# --- 7: Unreal report next to the export ------------------------------------
folder = tempfile.mkdtemp()
with open(os.path.join(folder, "uitest.harness_report.json"), "w") as handle:
    json.dump({"verdict": "21/21 module(s) within T1",
               "by_module": {"Spine": {"tier": "T1", "position_cm": {"max": 0.0564}, "rotation_deg": {"max": 0.05}}},
               "blendshapes": {"tolerance": 0.001, "missing_curves": ["Head_BS_Omouth"],
                               "targets": {"Head_BS_CloseMouth": {"max_error": 0.0002, "worst_pose": "x"}}}}, handle)
window._export_dir_field.setText(folder)
window._filename_field.setText("uitest")
window._on_export_field_edited()
app.processEvents()
spine = module_row("  Spine")
print("UI pose column:", spine.text(4), "|", window._report_label.text())
assert spine.text(4).startswith("T1") and "21/21" in window._report_label.text()
window.refresh_blendshapes()
face = next(window._bs_tree.topLevelItem(i) for i in range(window._bs_tree.topLevelItemCount())
            if window._bs_tree.topLevelItem(i).text(0).startswith("Face"))
cells = {face.child(i).text(0): face.child(i).text(4) for i in range(face.childCount())}
print("UI morph column:", cells)
assert cells["Head_BS_CloseMouth"].startswith("max error") and cells["Head_BS_Omouth"] == "no curve in Unreal"

# --- 9: export summary (real export into the temp folder) -----------------
cmds.loadPlugin("fbxmaya", quiet=True)
erm.export(folder, "uitest", "murakami", rig_tagger_tool.read_all_tagged_modules())
summary_text = window._export_summary_text(0)
print("UI export summary:", summary_text.replace(chr(10), " | "))
assert "Test poses for the Unreal pose check:" in summary_text and "Controller shapes:" in summary_text

# --- 8: export fields remembered ---------------------------------------------
second = rig_tagger_tool.RigTaggerWindow()
assert second._filename_field.text() == "uitest" and second._export_dir_field.text() == folder
for name in rig_tagger_tool.RigTaggerWindow._OPTION_VARS.values():
    cmds.optionVar(remove=name)
print("TOOL UI OK")
maya.standalone.uninitialize()
