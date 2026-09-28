"""
rig_tagger_tool.py

Explicit-tagging Maya tool for the Semantic Rigging System (JEFF Kotsudo).

Version 2 adds:
  - Explicit Start Bone / End Bone chain definition.
  - Automatic hierarchy path resolution between those endpoints.
  - Expandable module-type groups and per-module joint lists.
  - Green / orange / red validation dots.
  - Parent-module attachment discovery and deterministic UE5 build order.
  - Manifest schema-v2 compatibility while still reading legacy v1 tags.

The Maya tags remain the primary semantic source. Structural detection from
export_rig_manifest.py is used only as validation evidence.
"""

import os

try:
    import maya.cmds as cmds
    import maya.mel as mel
    import maya.OpenMayaUI as omui
except ImportError:
    cmds = None
    mel = None
    omui = None

try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from shiboken2 import wrapInstance

import export_rig_manifest as erm

try:
    USER_ROLE = QtCore.Qt.UserRole
except AttributeError:
    USER_ROLE = QtCore.Qt.ItemDataRole.UserRole


# ---------------------------------------------------------------------------
# Attribute schema
# ---------------------------------------------------------------------------

ATTR_VERSION = "rigTag_version"
ATTR_MODULE_TYPE = "rigTag_moduleType"
ATTR_MODULE_NAME = "rigTag_moduleName"
ATTR_INDEX = "rigTag_index"
ATTR_ROLE = "rigTag_role"
ATTR_START_BONE = "rigTag_startBone"
ATTR_END_BONE = "rigTag_endBone"
ATTR_IK_CHAIN_ROOT = "rigTag_ikChainRoot"
ATTR_FK_CHAIN_ROOT = "rigTag_fkChainRoot"
ATTR_SKIP_CONSTRAINT_DETECTION = "rigTag_skipConstraintDetection"

SCHEMA_VERSION = 2

MODULE_TYPES = ["FKChain", "IKLimb", "IKFKSwitch", "SplineIK"]

MODULE_COLORS = {
    "FKChain": "#FFA500",
    "IKLimb": "#00B3FF",
    "IKFKSwitch": "#66FF33",
    "SplineIK": "#33CCFF",
}

STATUS_COLORS = {
    "green": "#57D163",
    "orange": "#FFB84D",
    "red": "#FF5A5F",
    "gray": "#8A8A8A",
}

STATUS_LABELS = {
    "green": "Ready",
    "orange": "Review",
    "red": "Error",
    "gray": "Empty",
}

STATUS_RANK = {"gray": -1, "green": 0, "orange": 1, "red": 2}


# ---------------------------------------------------------------------------
# Attribute I/O
# ---------------------------------------------------------------------------

def _ensure_string_attr(node, attr):
    if not cmds.attributeQuery(attr, node=node, exists=True):
        cmds.addAttr(node, longName=attr, dataType="string")


def _ensure_int_attr(node, attr):
    if not cmds.attributeQuery(attr, node=node, exists=True):
        cmds.addAttr(node, longName=attr, attributeType="long")


def _set_string(node, attr, value):
    _ensure_string_attr(node, attr)
    cmds.setAttr("{}.{}".format(node, attr), value, type="string")


def _set_int(node, attr, value):
    _ensure_int_attr(node, attr)
    cmds.setAttr("{}.{}".format(node, attr), int(value))


def _get_string(node, attr, default=""):
    if not cmds.attributeQuery(attr, node=node, exists=True):
        return default
    value = cmds.getAttr("{}.{}".format(node, attr))
    return value if value is not None else default


def _get_int(node, attr, default=None):
    if not cmds.attributeQuery(attr, node=node, exists=True):
        return default
    value = cmds.getAttr("{}.{}".format(node, attr))
    return value if value is not None else default


def _delete_attr(node, attr):
    if cmds.attributeQuery(attr, node=node, exists=True):
        cmds.deleteAttr(node, attribute=attr)


def _role_for_index(index, count):
    if count == 1:
        return "Start"
    if index == 0:
        return "Start"
    if index == count - 1:
        return "End"
    return "Mid"


def _short_name(node):
    return str(node).split("|")[-1]


def _long_name(node):
    matches = cmds.ls(node, long=True, type="joint") or []
    if not matches:
        raise RuntimeError("Joint '{}' does not exist.".format(node))
    if len(matches) > 1:
        raise RuntimeError(
            "Joint name '{}' is ambiguous. Use its full Maya DAG path.".format(node)
        )
    return matches[0]


def _canonical_set(nodes):
    result = set()
    for node in nodes:
        try:
            result.add(_long_name(node))
        except Exception:
            result.add(str(node))
    return result


def is_tagged(joint):
    return cmds.attributeQuery(ATTR_MODULE_NAME, node=joint, exists=True) and bool(
        _get_string(joint, ATTR_MODULE_NAME)
    )


def clear_tag(joint):
    """Remove every rigTag_* attribute from one joint, if present."""
    for attr in (
        ATTR_VERSION,
        ATTR_MODULE_TYPE,
        ATTR_MODULE_NAME,
        ATTR_INDEX,
        ATTR_ROLE,
        ATTR_START_BONE,
        ATTR_END_BONE,
        ATTR_IK_CHAIN_ROOT,
        ATTR_FK_CHAIN_ROOT,
        ATTR_SKIP_CONSTRAINT_DETECTION,
    ):
        _delete_attr(joint, attr)


# ---------------------------------------------------------------------------
# Chain definition
# ---------------------------------------------------------------------------

def joint_chain_between(start_bone, end_bone):
    """Return the inclusive parent-to-child joint path from start to end.

    The end bone must be the start bone itself or one of its descendants.
    This removes the old requirement to manually select every joint in exact
    order and makes the chain endpoints explicit.
    """
    start_long = _long_name(start_bone)
    end_long = _long_name(end_bone)

    reverse_chain = [end_long]
    current = end_long
    visited = set()

    while current != start_long:
        if current in visited:
            raise RuntimeError("Cycle detected while resolving the joint hierarchy.")
        visited.add(current)

        parents = cmds.listRelatives(
            current, parent=True, type="joint", fullPath=True
        ) or []
        if not parents:
            raise ValueError(
                "End bone '{}' is not a descendant of start bone '{}'.".format(
                    _short_name(end_long), _short_name(start_long)
                )
            )
        current = parents[0]
        reverse_chain.append(current)

    reverse_chain.reverse()
    return reverse_chain


def _validate_chain_parenting(chain):
    if not chain:
        return False, "empty chain"
    canonical = [_long_name(joint) for joint in chain]
    for index in range(len(canonical) - 1):
        parents = cmds.listRelatives(
            canonical[index + 1], parent=True, type="joint", fullPath=True
        ) or []
        if not parents or parents[0] != canonical[index]:
            return False, "'{}' is not the direct parent of '{}'".format(
                _short_name(canonical[index]), _short_name(canonical[index + 1])
            )
    return True, "OK"


# ---------------------------------------------------------------------------
# Tagging operations
# ---------------------------------------------------------------------------

def tag_chain(chain, module_type, module_name, ik_chain_root=None, fk_chain_root=None):
    """Tag a complete module chain atomically.

    Version 2 stores explicit start/end bones on the module root. Existing
    joints from the same module name are updated; joints belonging to another
    module are rejected to prevent ambiguous ownership.
    """
    if module_type not in MODULE_TYPES:
        raise ValueError(
            "Unknown module_type '{}'. Must be one of {}.".format(
                module_type, MODULE_TYPES
            )
        )
    if not chain:
        raise ValueError("Cannot tag an empty chain.")
    if not module_name:
        raise ValueError("module_name is required.")

    chain = [_long_name(joint) for joint in chain]
    valid_parenting, parenting_message = _validate_chain_parenting(chain)
    if not valid_parenting:
        raise ValueError(parenting_message)

    new_chain_set = set(chain)
    conflicts = []
    for joint in chain:
        existing_name = _get_string(joint, ATTR_MODULE_NAME)
        if existing_name and existing_name != module_name:
            conflicts.append("{} ({})".format(_short_name(joint), existing_name))
    if conflicts:
        raise ValueError(
            "These joints already belong to another module: {}. Untag or edit "
            "that module first.".format(", ".join(conflicts))
        )

    # Remove stale joints when updating an existing module with a shorter or
    # different endpoint range.
    for joint in cmds.ls(type="joint", long=True) or []:
        if _get_string(joint, ATTR_MODULE_NAME) == module_name and joint not in new_chain_set:
            clear_tag(joint)

    count = len(chain)
    for index, joint in enumerate(chain):
        _set_int(joint, ATTR_VERSION, SCHEMA_VERSION)
        _set_string(joint, ATTR_MODULE_TYPE, module_type)
        _set_string(joint, ATTR_MODULE_NAME, module_name)
        _set_int(joint, ATTR_INDEX, index)
        _set_string(joint, ATTR_ROLE, _role_for_index(index, count))

    root_joint = chain[0]
    _set_string(root_joint, ATTR_START_BONE, _short_name(chain[0]))
    _set_string(root_joint, ATTR_END_BONE, _short_name(chain[-1]))

    if module_type == "IKFKSwitch":
        if ik_chain_root:
            _set_string(root_joint, ATTR_IK_CHAIN_ROOT, _short_name(ik_chain_root))
        if fk_chain_root:
            _set_string(root_joint, ATTR_FK_CHAIN_ROOT, _short_name(fk_chain_root))
    else:
        _delete_attr(root_joint, ATTR_IK_CHAIN_ROOT)
        _delete_attr(root_joint, ATTR_FK_CHAIN_ROOT)

    print("[RigTagger] Tagged '{}' ({}) -- {} joint(s): {}".format(
        module_name,
        module_type,
        count,
        [_short_name(joint) for joint in chain],
    ))


def untag_module(module_name):
    joints = [
        joint for joint in (cmds.ls(type="joint", long=True) or [])
        if _get_string(joint, ATTR_MODULE_NAME) == module_name
    ]
    for joint in joints:
        clear_tag(joint)
    print("[RigTagger] Untagged '{}' ({} joint(s)).".format(module_name, len(joints)))


# ---------------------------------------------------------------------------
# Reading tags
# ---------------------------------------------------------------------------

def read_all_tagged_modules():
    """Read v1/v2 tags into the modules_config shape used by the exporter."""
    groups = {}

    for joint in cmds.ls(type="joint") or []:
        module_name = _get_string(joint, ATTR_MODULE_NAME)
        if not module_name:
            continue

        module_type = _get_string(joint, ATTR_MODULE_TYPE)
        index = _get_int(joint, ATTR_INDEX, default=0)
        role = _get_string(joint, ATTR_ROLE, default="")
        version = _get_int(joint, ATTR_VERSION, default=1)

        entry = groups.setdefault(module_name, {
            "module_types": set(),
            "items": [],
            "start_bone": None,
            "end_bone": None,
            "explicit_endpoints": False,
        })
        entry["module_types"].add(module_type)
        entry["items"].append((index, joint, role, version))

        if index == 0:
            start_bone = _get_string(joint, ATTR_START_BONE) or None
            end_bone = _get_string(joint, ATTR_END_BONE) or None
            entry["start_bone"] = start_bone
            entry["end_bone"] = end_bone
            entry["explicit_endpoints"] = bool(start_bone and end_bone)

            if module_type == "IKFKSwitch":
                entry["ik_chain_root"] = _get_string(joint, ATTR_IK_CHAIN_ROOT) or None
                entry["fk_chain_root"] = _get_string(joint, ATTR_FK_CHAIN_ROOT) or None

    modules_config = []
    for module_name, data in groups.items():
        ordered = sorted(data["items"], key=lambda item: item[0])
        chain = [joint for _, joint, _, _ in ordered]
        indices = [index for index, _, _, _ in ordered]
        roles = [role for _, _, role, _ in ordered]
        versions = [version for _, _, _, version in ordered]
        module_types = sorted(item for item in data["module_types"] if item)
        module_type = module_types[0] if module_types else ""

        start_bone = data.get("start_bone") or (chain[0] if chain else "")
        end_bone = data.get("end_bone") or (chain[-1] if chain else "")
        chain_items = [
            {"bone_name": joint, "role": role}
            for joint, role in zip(chain, roles)
        ]

        module_def = {
            "module_type": module_type,
            "module_name": module_name,
            "chain": chain,
            "chain_items": chain_items,
            "start_bone": start_bone,
            "end_bone": end_bone,
            "_explicit_endpoints": data.get("explicit_endpoints", False),
            "_tag_indices": indices,
            "_tag_versions": versions,
            "_module_types": module_types,
        }

        if module_type == "IKFKSwitch":
            module_def["params"] = {
                "ik_chain_root": data.get("ik_chain_root"),
                "fk_chain_root": data.get("fk_chain_root"),
                "blend_node_type": None,
                "blend_node": None,
                "switch_control": None,
                "switch_attr": None,
                "default_value": 0.0,
            }

        modules_config.append(module_def)

    modules_config.sort(key=lambda module: module.get("module_name", "").lower())
    return modules_config


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _worst_status(statuses):
    statuses = list(statuses or [])
    if not statuses:
        return "green"
    return max(statuses, key=lambda status: STATUS_RANK.get(status, 0))


def validate_module(module_def, graph_analysis=None):
    """Return (green/orange/red, message) for one tagged module."""
    issues = []

    def add(status, message):
        issues.append((status, message))

    chain = list(module_def.get("chain", []) or [])
    module_type = module_def.get("module_type", "")
    module_name = module_def.get("module_name", "")

    if not chain:
        add("red", "module has no joints")
        return "red", "module has no joints"

    module_types = module_def.get("_module_types", [])
    if len(module_types) > 1:
        add("red", "inconsistent module types across tagged joints: {}".format(
            ", ".join(module_types)
        ))
    if module_type not in MODULE_TYPES:
        add("red", "unknown module type '{}'".format(module_type))

    indices = module_def.get("_tag_indices", [])
    expected_indices = list(range(len(chain)))
    if indices and indices != expected_indices:
        add("red", "tag indices are not a continuous 0..{} sequence".format(
            max(len(chain) - 1, 0)
        ))

    versions = module_def.get("_tag_versions", [])
    if versions and min(versions) < SCHEMA_VERSION:
        add("orange", "legacy v1 tag; retag to store explicit endpoints")

    if not module_def.get("_explicit_endpoints", False):
        add("orange", "start/end bones are inferred from legacy chain order")

    start_bone = module_def.get("start_bone")
    end_bone = module_def.get("end_bone")
    if start_bone and _short_name(start_bone) != _short_name(chain[0]):
        add("red", "stored start bone does not match chain index 0")
    if end_bone and _short_name(end_bone) != _short_name(chain[-1]):
        add("red", "stored end bone does not match the last chain joint")

    for joint in chain:
        if not cmds.objExists(joint):
            add("red", "joint '{}' no longer exists".format(joint))

    if not any(status == "red" for status, _ in issues):
        valid_parenting, parenting_message = _validate_chain_parenting(chain)
        if not valid_parenting:
            add("red", parenting_message)

    if not any(status == "red" for status, _ in issues):
        if module_type == "IKLimb":
            handle = erm.find_ik_handle_for_start_joint(chain[0])
            if not handle:
                add("red", "no ikHandle starts at '{}'".format(chain[0]))
            else:
                solver = erm._ik_solver_type(handle).lower()
                if "spline" in solver:
                    add("red", "found Spline IK solver instead of IKLimb")
                elif not solver:
                    add("orange", "IK solver type could not be confirmed")

        elif module_type == "SplineIK":
            handle = erm.find_ik_handle_for_start_joint(chain[0])
            if not handle:
                add("red", "no ikHandle starts at '{}'".format(chain[0]))
            elif "spline" not in erm._ik_solver_type(handle).lower():
                add("red", "ikHandle is not using a Spline IK solver")

        elif module_type == "IKFKSwitch":
            params = module_def.get("params") or {}
            roots = []
            for key in ("ik_chain_root", "fk_chain_root"):
                root = params.get(key)
                roots.append(root)
                if not root:
                    add("red", "missing {}".format(key))
                elif not cmds.objExists(root):
                    add("red", "{} '{}' no longer exists".format(key, root))
            if len(roots) == 2 and roots[0] and roots[0] == roots[1]:
                add("red", "IK and FK chain roots cannot be the same joint")

    if graph_analysis:
        for issue in graph_analysis.get("module_issues", {}).get(module_name, []):
            add(issue.get("severity", "orange"), issue.get("message", "module graph issue"))

    if not issues:
        return "green", "All checks passed"

    status = _worst_status([item[0] for item in issues])
    # De-duplicate while keeping the most useful ordering.
    messages = []
    for _, message in issues:
        if message not in messages:
            messages.append(message)
    return status, "; ".join(messages)


# ---------------------------------------------------------------------------
# Maya main window helper
# ---------------------------------------------------------------------------

def _maya_main_window():
    if not omui:
        return None
    ptr = omui.MQtUtil.mainWindow()
    if ptr is None:
        return None
    return wrapInstance(int(ptr), QtWidgets.QWidget)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

class RigTaggerWindow(QtWidgets.QDialog):

    OBJECT_NAME = "rigTaggerToolWindow"

    def __init__(self, parent=None):
        super(RigTaggerWindow, self).__init__(parent or _maya_main_window())
        self.setObjectName(self.OBJECT_NAME)
        self.setWindowTitle("Semantic Rig Tagger")
        self.setMinimumSize(850, 720)
        self.resize(980, 820)

        self._switch_bind_chain = []
        self._switch_fk_root = None
        self._switch_ik_root = None
        self._switch_confirm_btn = None
        self._last_modules = []
        self._last_graph = {}

        self._build_ui()
        self.refresh_module_list()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(7)

        main_layout.addWidget(self._section_label("1. Define the module chain"))
        main_layout.addLayout(self._build_chain_form())

        chain_actions = QtWidgets.QHBoxLayout()
        ordered_btn = QtWidgets.QPushButton("Use Ordered Selection")
        ordered_btn.clicked.connect(self._capture_ordered_selection)
        preview_btn = QtWidgets.QPushButton("Preview / Select Resolved Chain")
        preview_btn.clicked.connect(self._preview_resolved_chain)
        clear_btn = QtWidgets.QPushButton("Clear Fields")
        clear_btn.clicked.connect(self._clear_chain_fields)
        chain_actions.addWidget(ordered_btn)
        chain_actions.addWidget(preview_btn)
        chain_actions.addWidget(clear_btn)
        chain_actions.addStretch(1)
        main_layout.addLayout(chain_actions)

        main_layout.addWidget(self._section_label("2. Tag the resolved chain"))
        main_layout.addLayout(self._build_module_buttons())

        self._switch_status_label = QtWidgets.QLabel("")
        self._switch_status_label.setStyleSheet("color: #66FF33;")
        self._switch_status_label.setWordWrap(True)
        main_layout.addWidget(self._switch_status_label)

        main_layout.addWidget(self._section_label("3. Tagged modules in this scene"))
        self._module_tree = QtWidgets.QTreeWidget()
        self._module_tree.setColumnCount(4)
        self._module_tree.setHeaderLabels([
            "Module / Joint",
            "Type / Role",
            "Validation",
            "UE5 Attachment",
        ])
        self._module_tree.setAlternatingRowColors(True)
        self._module_tree.setRootIsDecorated(True)
        self._module_tree.setUniformRowHeights(True)
        self._module_tree.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._module_tree.itemDoubleClicked.connect(self._select_chain_of_current_item)
        main_layout.addWidget(self._module_tree, 1)

        list_buttons = QtWidgets.QHBoxLayout()
        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_module_list)
        select_btn = QtWidgets.QPushButton("Select Chain")
        select_btn.clicked.connect(self._select_chain_of_current_item)
        load_btn = QtWidgets.QPushButton("Load Start / End")
        load_btn.clicked.connect(self._load_current_module)
        expand_btn = QtWidgets.QPushButton("Expand All")
        expand_btn.clicked.connect(self._module_tree.expandAll)
        collapse_btn = QtWidgets.QPushButton("Collapse All")
        collapse_btn.clicked.connect(self._module_tree.collapseAll)
        untag_btn = QtWidgets.QPushButton("Untag Module")
        untag_btn.clicked.connect(self._untag_current_item)
        list_buttons.addWidget(refresh_btn)
        list_buttons.addWidget(select_btn)
        list_buttons.addWidget(load_btn)
        list_buttons.addWidget(expand_btn)
        list_buttons.addWidget(collapse_btn)
        list_buttons.addStretch(1)
        list_buttons.addWidget(untag_btn)
        main_layout.addLayout(list_buttons)

        main_layout.addWidget(self._section_label("4. UE5.6 module build order"))
        self._build_order_box = QtWidgets.QPlainTextEdit()
        self._build_order_box.setReadOnly(True)
        self._build_order_box.setMaximumHeight(115)
        self._build_order_box.setPlaceholderText("No modules tagged.")
        main_layout.addWidget(self._build_order_box)

        main_layout.addWidget(self._section_label("5. Export"))
        main_layout.addLayout(self._build_export_form())

        export_btn = QtWidgets.QPushButton("Export Manifest + FBX")
        export_btn.setStyleSheet("font-weight: bold; padding: 8px;")
        export_btn.clicked.connect(self._export)
        main_layout.addWidget(export_btn)

    def _section_label(self, text):
        label = QtWidgets.QLabel(text)
        label.setStyleSheet("font-weight: bold; margin-top: 5px;")
        return label

    def _build_chain_form(self):
        form = QtWidgets.QFormLayout()

        self._module_name_field = QtWidgets.QLineEdit()
        self._module_name_field.setPlaceholderText("Example: L_arm, spine, R_leg")
        form.addRow("Module Name:", self._module_name_field)

        start_row = QtWidgets.QHBoxLayout()
        self._start_bone_field = QtWidgets.QLineEdit()
        self._start_bone_field.setPlaceholderText("First bone of the chain")
        start_btn = QtWidgets.QPushButton("Use Selected as Start")
        start_btn.clicked.connect(lambda: self._capture_endpoint(self._start_bone_field, "start"))
        start_row.addWidget(self._start_bone_field)
        start_row.addWidget(start_btn)
        form.addRow("Start Bone:", start_row)

        end_row = QtWidgets.QHBoxLayout()
        self._end_bone_field = QtWidgets.QLineEdit()
        self._end_bone_field.setPlaceholderText("Last bone of the chain")
        end_btn = QtWidgets.QPushButton("Use Selected as End")
        end_btn.clicked.connect(lambda: self._capture_endpoint(self._end_bone_field, "end"))
        end_row.addWidget(self._end_bone_field)
        end_row.addWidget(end_btn)
        form.addRow("End Bone:", end_row)

        return form

    def _build_module_buttons(self):
        grid = QtWidgets.QGridLayout()
        for column, module_type in enumerate(MODULE_TYPES):
            label = module_type
            if module_type == "IKFKSwitch":
                label = "IKFKSwitch (guided)"
            button = QtWidgets.QPushButton(label)
            button.setStyleSheet(
                "background-color: {}; color: #111111; font-weight: bold; padding: 8px;".format(
                    MODULE_COLORS[module_type]
                )
            )
            if module_type == "IKFKSwitch":
                button.clicked.connect(self._start_switch_flow)
            else:
                button.clicked.connect(
                    lambda checked=False, current_type=module_type: self._tag_simple(current_type)
                )
            grid.addWidget(button, 0, column)
        return grid

    def _build_export_form(self):
        form = QtWidgets.QFormLayout()

        self._rig_name_field = QtWidgets.QLineEdit("MultiModule")
        form.addRow("Rig Name:", self._rig_name_field)

        self._filename_field = QtWidgets.QLineEdit("MultiModule")
        form.addRow("Filename:", self._filename_field)

        dir_row = QtWidgets.QHBoxLayout()
        self._export_dir_field = QtWidgets.QLineEdit(getattr(erm, "EXPORT_DIR", ""))
        browse_btn = QtWidgets.QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_export_dir)
        dir_row.addWidget(self._export_dir_field)
        dir_row.addWidget(browse_btn)
        form.addRow("Export Dir:", dir_row)

        return form

    # ------------------------------------------------------------------
    # Endpoint handling
    # ------------------------------------------------------------------

    def _capture_endpoint(self, field, endpoint_name):
        selected = cmds.ls(selection=True, type="joint", long=True) or []
        if not selected:
            self._warn("Select one joint to use as the {} bone.".format(endpoint_name))
            return
        field.setText(selected[0])

        if not self._module_name_field.text().strip() and endpoint_name == "start":
            self._module_name_field.setText(_short_name(selected[0]))

    def _capture_ordered_selection(self):
        selected = cmds.ls(orderedSelection=True, type="joint", long=True) or []
        if not selected:
            selected = cmds.ls(selection=True, type="joint", long=True) or []
        if not selected:
            self._warn("Select the start and end joints, or an ordered chain.")
            return

        self._start_bone_field.setText(selected[0])
        self._end_bone_field.setText(selected[-1])
        if not self._module_name_field.text().strip():
            self._module_name_field.setText(_short_name(selected[0]))

        try:
            chain = self._resolved_chain()
        except Exception as exc:
            self._warn(str(exc))
            return
        cmds.select(chain, replace=True)

    def _resolved_chain(self):
        start_bone = self._start_bone_field.text().strip()
        end_bone = self._end_bone_field.text().strip()
        if not start_bone or not end_bone:
            raise ValueError("Both Start Bone and End Bone must be specified.")
        return joint_chain_between(start_bone, end_bone)

    def _preview_resolved_chain(self):
        try:
            chain = self._resolved_chain()
        except Exception as exc:
            self._warn(str(exc))
            return
        cmds.select(chain, replace=True)

    def _clear_chain_fields(self):
        self._module_name_field.clear()
        self._start_bone_field.clear()
        self._end_bone_field.clear()
        self._reset_switch_flow()

    def _resolved_module_name(self, module_type, chain):
        module_name = self._module_name_field.text().strip()
        if not module_name:
            module_name = "{}_{}".format(module_type, _short_name(chain[0]))
            self._module_name_field.setText(module_name)
        return module_name

    # ------------------------------------------------------------------
    # Simple module tagging
    # ------------------------------------------------------------------

    def _tag_simple(self, module_type):
        try:
            chain = self._resolved_chain()
            module_name = self._resolved_module_name(module_type, chain)
            tag_chain(chain, module_type, module_name)
        except Exception as exc:
            self._warn(str(exc))
            return
        self.refresh_module_list()

    # ------------------------------------------------------------------
    # IKFKSwitch guided flow
    # ------------------------------------------------------------------

    def _start_switch_flow(self):
        try:
            self._switch_bind_chain = self._resolved_chain()
        except Exception as exc:
            self._warn(str(exc))
            return

        self._switch_fk_root = None
        self._switch_ik_root = None
        self._switch_status_label.setText(
            "IK/FK step 1/2 — Bind chain stored. Select the FK chain ROOT joint, "
            "then confirm it below."
        )
        self._show_switch_confirm_button("Confirm FK Root", self._confirm_switch_fk)

    def _confirm_switch_fk(self):
        selected = cmds.ls(selection=True, type="joint", long=True) or []
        if not selected:
            self._warn("Select the FK chain root joint first.")
            return
        self._switch_fk_root = selected[0]
        self._switch_status_label.setText(
            "IK/FK step 2/2 — FK root: {}. Select the IK chain ROOT joint, then confirm.".format(
                _short_name(self._switch_fk_root)
            )
        )
        self._show_switch_confirm_button("Confirm IK Root and Tag", self._confirm_switch_ik)

    def _confirm_switch_ik(self):
        selected = cmds.ls(selection=True, type="joint", long=True) or []
        if not selected:
            self._warn("Select the IK chain root joint first.")
            return
        self._switch_ik_root = selected[0]

        try:
            module_name = self._resolved_module_name("IKFKSwitch", self._switch_bind_chain)
            tag_chain(
                self._switch_bind_chain,
                "IKFKSwitch",
                module_name,
                ik_chain_root=self._switch_ik_root,
                fk_chain_root=self._switch_fk_root,
            )
        except Exception as exc:
            self._warn(str(exc))
            return

        self._reset_switch_flow()
        self.refresh_module_list()

    def _reset_switch_flow(self):
        self._switch_bind_chain = []
        self._switch_fk_root = None
        self._switch_ik_root = None
        if hasattr(self, "_switch_status_label"):
            self._switch_status_label.setText("")
        if self._switch_confirm_btn:
            self._switch_confirm_btn.setParent(None)
            self._switch_confirm_btn.deleteLater()
            self._switch_confirm_btn = None

    def _show_switch_confirm_button(self, text, callback):
        if self._switch_confirm_btn:
            self._switch_confirm_btn.setParent(None)
            self._switch_confirm_btn.deleteLater()
        self._switch_confirm_btn = QtWidgets.QPushButton(text)
        self._switch_confirm_btn.setStyleSheet("font-weight: bold; padding: 5px;")
        self._switch_confirm_btn.clicked.connect(callback)
        self.layout().insertWidget(6, self._switch_confirm_btn)

    # ------------------------------------------------------------------
    # Module tree / validation
    # ------------------------------------------------------------------

    def _status_icon(self, status):
        pixmap = QtGui.QPixmap(14, 14)
        pixmap.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(STATUS_COLORS.get(status, STATUS_COLORS["gray"])))
        painter.drawEllipse(2, 2, 10, 10)
        painter.end()
        return QtGui.QIcon(pixmap)

    def _expanded_keys(self):
        keys = set()
        root_count = self._module_tree.topLevelItemCount()
        for root_index in range(root_count):
            group_item = self._module_tree.topLevelItem(root_index)
            if group_item.isExpanded():
                keys.add("type:{}".format(group_item.text(0)))
            for child_index in range(group_item.childCount()):
                child = group_item.child(child_index)
                module_def = child.data(0, USER_ROLE)
                if module_def and child.isExpanded():
                    keys.add("module:{}".format(module_def.get("module_name")))
        return keys

    def refresh_module_list(self):
        expanded_keys = self._expanded_keys()
        modules_config = read_all_tagged_modules()
        graph = erm.analyze_module_graph(modules_config)
        self._last_modules = modules_config
        self._last_graph = graph

        self._module_tree.clear()
        status_by_module = {}
        message_by_module = {}
        for module_def in modules_config:
            status, message = validate_module(module_def, graph)
            status_by_module[module_def["module_name"]] = status
            message_by_module[module_def["module_name"]] = message

        build_index = graph.get("build_index", {})
        modules_by_type = {module_type: [] for module_type in MODULE_TYPES}
        for module_def in modules_config:
            modules_by_type.setdefault(module_def.get("module_type", "Unknown"), []).append(module_def)

        ordered_types = list(MODULE_TYPES)
        ordered_types.extend(sorted(
            module_type for module_type in modules_by_type
            if module_type not in MODULE_TYPES
        ))

        for module_type in ordered_types:
            typed_modules = modules_by_type.get(module_type, [])
            typed_modules.sort(key=lambda module: (
                build_index.get(module.get("module_name"), 10 ** 9),
                module.get("module_name", "").lower(),
            ))

            group_item = QtWidgets.QTreeWidgetItem([
                "{} ({})".format(module_type, len(typed_modules)),
                "Module Type",
                "",
                "",
            ])
            font = group_item.font(0)
            font.setBold(True)
            group_item.setFont(0, font)
            if typed_modules:
                group_status = _worst_status([
                    status_by_module[module["module_name"]]
                    for module in typed_modules
                ])
                group_item.setIcon(0, self._status_icon(group_status))
            self._module_tree.addTopLevelItem(group_item)

            for module_def in typed_modules:
                module_name = module_def["module_name"]
                status = status_by_module[module_name]
                message = message_by_module[module_name]
                index = build_index.get(module_name)
                order_text = "--" if index is None else "{:02d}".format(index + 1)
                connection = graph.get("connections", {}).get(module_name)

                if connection:
                    attachment_text = "{} @ {} → {}".format(
                        connection.get("parent_module", "?"),
                        connection.get("parent_bone", "?"),
                        connection.get("child_attach_bone", "?"),
                    )
                else:
                    attachment_text = "Root module"

                module_item = QtWidgets.QTreeWidgetItem([
                    "{}  {}".format(order_text, module_name),
                    module_def.get("module_type", ""),
                    "{} — {}".format(STATUS_LABELS[status], message),
                    attachment_text,
                ])
                module_item.setIcon(0, self._status_icon(status))
                module_item.setData(0, USER_ROLE, module_def)
                module_item.setToolTip(2, message)
                module_item.setForeground(2, QtGui.QColor(STATUS_COLORS[status]))
                group_item.addChild(module_item)

                chain = module_def.get("chain", [])
                items = module_def.get("chain_items", [])
                for joint_index, joint in enumerate(chain):
                    role = ""
                    if joint_index < len(items):
                        role = items[joint_index].get("role", "")
                    endpoint = ""
                    if joint_index == 0:
                        endpoint = "Start bone"
                    if joint_index == len(chain) - 1:
                        endpoint = "End bone" if not endpoint else "Start + End bone"
                    joint_item = QtWidgets.QTreeWidgetItem([
                        "{:02d}  {}".format(joint_index, joint),
                        role,
                        endpoint,
                        "",
                    ])
                    module_item.addChild(joint_item)

                if module_def.get("module_type") == "IKFKSwitch":
                    params = module_def.get("params") or {}
                    module_item.addChild(QtWidgets.QTreeWidgetItem([
                        "FK chain root: {}".format(params.get("fk_chain_root") or "<missing>"),
                        "Reference",
                        "",
                        "",
                    ]))
                    module_item.addChild(QtWidgets.QTreeWidgetItem([
                        "IK chain root: {}".format(params.get("ik_chain_root") or "<missing>"),
                        "Reference",
                        "",
                        "",
                    ]))

                module_item.setExpanded(
                    not expanded_keys or "module:{}".format(module_name) in expanded_keys
                )

            group_item.setExpanded(
                not expanded_keys or "type:{} ({})".format(module_type, len(typed_modules)) in expanded_keys
                or bool(typed_modules)
            )

        header = self._module_tree.header()
        self._module_tree.resizeColumnToContents(0)
        self._module_tree.resizeColumnToContents(1)
        self._module_tree.resizeColumnToContents(2)
        try:
            header.setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        except AttributeError:
            header.setResizeMode(3, QtWidgets.QHeaderView.Stretch)

        self._update_build_order_box(graph)

    def _update_build_order_box(self, graph):
        lines = []
        connection_map = graph.get("connections", {})
        for index, module_name in enumerate(graph.get("build_order", [])):
            connection = connection_map.get(module_name)
            if connection:
                lines.append("{:02d}. {}  ←  {}  ({} → {})".format(
                    index + 1,
                    module_name,
                    connection.get("parent_module", "?"),
                    connection.get("parent_bone", "?"),
                    connection.get("child_attach_bone", "?"),
                ))
            else:
                lines.append("{:02d}. {}  [root module]".format(index + 1, module_name))

        for issue in graph.get("global_issues", []):
            lines.append("{}: {}".format(issue.get("severity", "issue").upper(), issue.get("message", "")))

        self._build_order_box.setPlainText("\n".join(lines))

    def _current_module_def(self):
        item = self._module_tree.currentItem()
        while item is not None:
            module_def = item.data(0, USER_ROLE)
            if module_def:
                return module_def
            item = item.parent()
        return None

    def _select_chain_of_current_item(self, *args):
        module_def = self._current_module_def()
        if not module_def:
            self._warn("Select a module row first.")
            return
        cmds.select(module_def.get("chain", []), replace=True)

    def _load_current_module(self):
        module_def = self._current_module_def()
        if not module_def:
            self._warn("Select a module row first.")
            return
        chain = module_def.get("chain", [])
        if not chain:
            return
        self._module_name_field.setText(module_def.get("module_name", ""))
        self._start_bone_field.setText(chain[0])
        self._end_bone_field.setText(chain[-1])
        cmds.select(chain, replace=True)

    def _untag_current_item(self):
        module_def = self._current_module_def()
        if not module_def:
            self._warn("Select a module row first.")
            return
        untag_module(module_def["module_name"])
        self.refresh_module_list()

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _browse_export_dir(self):
        current = self._export_dir_field.text() or os.path.expanduser("~")
        chosen = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose Export Directory", current
        )
        if chosen:
            self._export_dir_field.setText(chosen)

    def _export(self):
        modules_config = read_all_tagged_modules()
        if not modules_config:
            self._warn("No tagged modules found. Tag at least one module first.")
            return

        graph = erm.analyze_module_graph(modules_config)
        red_items = []
        orange_items = []
        for module_def in modules_config:
            status, message = validate_module(module_def, graph)
            item_text = "{} ({}): {}".format(
                module_def["module_name"], module_def["module_type"], message
            )
            if status == "red":
                red_items.append(item_text)
            elif status == "orange":
                orange_items.append(item_text)

        if red_items:
            proceed = QtWidgets.QMessageBox.warning(
                self,
                "Module Errors Found",
                "These modules have red errors:\n\n{}\n\nExport anyway? The UE5 builder should reject or skip invalid modules.".format(
                    "\n".join(red_items)
                ),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            )
            if proceed != QtWidgets.QMessageBox.Yes:
                return
        elif orange_items:
            proceed = QtWidgets.QMessageBox.question(
                self,
                "Modules Need Review",
                "These modules are orange and should be reviewed:\n\n{}\n\nContinue export?".format(
                    "\n".join(orange_items)
                ),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            )
            if proceed != QtWidgets.QMessageBox.Yes:
                return

        export_dir = self._export_dir_field.text().strip()
        filename = self._filename_field.text().strip()
        rig_name = self._rig_name_field.text().strip()
        if not export_dir or not filename or not rig_name:
            self._warn("Rig Name, Filename, and Export Dir are all required.")
            return

        try:
            fbx_path = erm.export(export_dir, filename, rig_name, modules_config)
        except Exception as exc:
            self._warn("Export failed: {}".format(exc))
            return

        build_order = " → ".join(graph.get("build_order", []))
        QtWidgets.QMessageBox.information(
            self,
            "Export Complete",
            "Exported to:\n{}\n\nUE5 build order:\n{}".format(fbx_path, build_order),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _warn(self, message):
        QtWidgets.QMessageBox.warning(self, "Semantic Rig Tagger", message)


def show_rig_tagger_tool():
    for widget in QtWidgets.QApplication.allWidgets():
        if widget.objectName() == RigTaggerWindow.OBJECT_NAME:
            widget.close()
            widget.deleteLater()

    window = RigTaggerWindow()
    window.show()
    return window


if __name__ == "__main__":
    show_rig_tagger_tool()
