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
assert tabs == ["Modules", "Blendshapes"], tabs
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
print("TOOL UI OK")
maya.standalone.uninitialize()
