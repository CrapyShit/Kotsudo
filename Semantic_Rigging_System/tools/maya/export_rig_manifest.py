"""
Maya export script for the Semantic Rigging System.

Workflow:
  1. Run the script in Maya's Script Editor (Python tab) with your rig open.
  2. The script will:
     a. Scan all joints via structural detection (no name-based guessing).
        Group chains from the scene hierarchy, then run the priority-ordered
        detector pipeline: IKFKSwitch > SplineIK > IKLimb > FKChain.
        SquashStretch is additive and attaches params to existing modules.
     b. Write the compact JSON manifest onto the root joint's
        rig_manifest_json attribute.
     c. Restore the bind pose and export FBX.
  3. Import FBX into UE5.  The manifest travels as root-bone metadata and
     is read automatically by run_rig_builder.py.

Detection principle: all module type decisions come from Maya node types,
connections, and constraint queries -- never from joint/control names.
"""

import json
import os
import re

import maya.cmds as cmds
import maya.mel as mel

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ROOT_JOINT_NAME = "root"
MANIFEST_ATTR = "rig_manifest_json"
MANIFEST_SCHEMA_VERSION = 3

# Tracks scriptJob IDs installed by register_auto_update()
_AUTO_UPDATE_JOBS = []


# ---------------------------------------------------------------------------
# Joint naming convention (used for grouping only, not for type detection)
# ---------------------------------------------------------------------------
# Pattern: {side}_{part}_{index:02d}_jnt
#   side  : L or R  (omit for center joints)
#   part  : any lowercase token(s), e.g.  arm, leg, spine, arm_switch, tail
#   index : zero-padded int, e.g.  01, 02
# Examples:  L_arm_01_jnt  R_leg_02_jnt  spine_01_jnt  L_arm_switch_01_jnt

_JOINT_RE = re.compile(r'^(?:(L|R)_)?(.+?)_(\d+)_jnt$', re.IGNORECASE)


def _parse_joint_name(joint_name):
    """Return (side, part, index) for a convention-named joint, or None."""
    m = _JOINT_RE.match(joint_name.split('|')[-1])
    if not m:
        return None
    side = (m.group(1) or '').upper()
    part = m.group(2).lower()
    index = int(m.group(3))
    return side, part, index


def _chain_roles(length):
    """Return role strings [Start, Mid*, End] for a chain of given length."""
    if length == 1:
        return ['Start']
    if length == 2:
        return ['Start', 'End']
    return ['Start'] + ['Mid'] * (length - 2) + ['End']


def _full_dag_path(node):
    """Return the full DAG path for a node to avoid short-name collisions."""
    try:
        paths = cmds.ls(node, long=True) or []
        return paths[0] if paths else node
    except Exception:
        return node


# ---------------------------------------------------------------------------
# Low-level scene query helpers
# ---------------------------------------------------------------------------

def find_ik_handle_for_start_joint(start_joint):
    """Return the first ikHandle whose startJoint is *start_joint*, or None."""
    for handle in cmds.ls(type='ikHandle') or []:
        conns = cmds.listConnections(
            '{}.startJoint'.format(handle), source=True, destination=False
        ) or []
        if start_joint in conns or _full_dag_path(start_joint) in conns:
            return handle
    return None


def _ik_handle_end_joint(ik_handle):
    """Return the end-effector joint of an ikHandle, or None."""
    effectors = cmds.listConnections(
        '{}.endEffector'.format(ik_handle), source=True, destination=False
    ) or []
    for eff in effectors:
        joints = cmds.listConnections(
            '{}.translateX'.format(eff), source=True, destination=False, type='joint'
        ) or []
        if joints:
            return joints[0]
    # Alternative: query via ikHandle -q -endEffector
    try:
        eff = cmds.ikHandle(ik_handle, query=True, endEffector=True)
        joints = cmds.listConnections(
            '{}.translateX'.format(eff), source=True, destination=False, type='joint'
        ) or []
        if joints:
            return joints[0]
    except Exception:
        pass
    return None


def _ik_solver_type(ik_handle):
    """Return the solver string for an ikHandle (e.g. 'ikRPsolver')."""
    try:
        solver_nodes = cmds.listConnections(
            '{}.ikSolver'.format(ik_handle), source=True, destination=False
        ) or []
        if solver_nodes:
            return solver_nodes[0]
        return cmds.getAttr('{}.ikSolver'.format(ik_handle))
    except Exception:
        return ''


def _get_pole_vector_node(ik_handle):
    """Return the transform driving the pole vector of *ik_handle*, or None."""
    if not ik_handle:
        return None
    constraints = cmds.listConnections(
        ik_handle, type='poleVectorConstraint', source=False, destination=True
    ) or []
    for constraint in constraints:
        indices = cmds.getAttr('{}.target'.format(constraint), multiIndices=True) or []
        for idx in indices:
            conns = cmds.listConnections(
                '{}.target[{}].targetTranslate'.format(constraint, idx),
                source=True, destination=False, plugs=False,
            ) or []
            if conns:
                return conns[0]
    return None


def get_world_position(node_name):
    """Return [x, y, z] world-space position, rounded to 4 dp."""
    pos = cmds.xform(node_name, query=True, worldSpace=True, translation=True)
    return [round(v, 4) for v in pos]


def get_pole_vector_world_position(ik_handle):
    """Return world-space [x, y, z] of the pole vector target, or None."""
    node = _get_pole_vector_node(ik_handle)
    return get_world_position(node) if node else None


def _round_vector(values, precision=6):
    """Return a JSON-safe rounded 3D vector."""
    if values is None:
        return None
    return [round(float(values[0]), precision), round(float(values[1]), precision), round(float(values[2]), precision)]


def _vector_dot_list(lhs, rhs):
    return sum(float(a) * float(b) for a, b in zip(lhs, rhs))


def _vector_length_list(value):
    return _vector_dot_list(value, value) ** 0.5


def _vector_normalize_list(value, fallback=None):
    length = _vector_length_list(value)
    if length < 1e-8:
        return list(fallback or [1.0, 0.0, 0.0])
    return [float(component) / length for component in value]


def _signed_primary_axis(chain):
    """Return the signed dominant local translation axis of the first segment.

    Keeping the sign is essential for mirrored limbs: a right leg authored with
    a negative local X child translation must export [-1, 0, 0], not merely "X".
    """
    if len(chain) < 2:
        return [1.0, 0.0, 0.0]
    try:
        translation = cmds.getAttr('{}.translate'.format(chain[1]))[0]
        values = [float(translation[0]), float(translation[1]), float(translation[2])]
    except Exception:
        values = [1.0, 0.0, 0.0]

    index = max(range(3), key=lambda idx: abs(values[idx]))
    sign = -1.0 if values[index] < 0.0 else 1.0
    result = [0.0, 0.0, 0.0]
    result[index] = sign
    return result


def _world_point_to_node_local(world_position, node):
    """Convert a Maya world-space point into *node* local coordinates."""
    if not world_position or not node or not cmds.objExists(node):
        return None
    try:
        import maya.api.OpenMaya as om2
        world_matrix = om2.MMatrix(cmds.xform(node, query=True, worldSpace=True, matrix=True))
        local_point = om2.MPoint(
            float(world_position[0]),
            float(world_position[1]),
            float(world_position[2]),
            1.0,
        ) * world_matrix.inverse()
        return _round_vector([local_point.x, local_point.y, local_point.z])
    except Exception:
        return None


def _secondary_axis_from_pole(chain, pole_world_position, primary_axis):
    """Derive a signed local secondary axis pointing toward the Maya PV."""
    secondary = None
    if chain and pole_world_position:
        local_pole = _world_point_to_node_local(pole_world_position, chain[0])
        if local_pole:
            projection = _vector_dot_list(local_pole, primary_axis)
            secondary = [
                local_pole[i] - primary_axis[i] * projection
                for i in range(3)
            ]
            if _vector_length_list(secondary) < 1e-6:
                secondary = None

    if secondary is None:
        # Stable orthogonal fallback: choose the cardinal axis least aligned
        # with the primary axis, then remove any residual projection.
        candidates = ([0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0])
        candidate = min(candidates, key=lambda axis: abs(_vector_dot_list(axis, primary_axis)))
        projection = _vector_dot_list(candidate, primary_axis)
        secondary = [candidate[i] - primary_axis[i] * projection for i in range(3)]

    return _round_vector(_vector_normalize_list(secondary, fallback=[0.0, 1.0, 0.0]))


def _short_node_name(node):
    return node.split('|')[-1] if node else node


def _has_controller_shape(node):
    if not node or not cmds.objExists(node):
        return False
    try:
        shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
        return any(cmds.nodeType(shape) in ('nurbsCurve', 'bezierCurve') for shape in shapes)
    except Exception:
        return False


def _nearest_controller_transform(node):
    """Walk up the DAG and return the first transform carrying a curve shape."""
    if not node or not cmds.objExists(node):
        return None
    current = _full_dag_path(node)
    visited = set()
    while current and current not in visited:
        visited.add(current)
        try:
            if cmds.nodeType(current) == 'transform' and _has_controller_shape(current):
                return current
        except Exception:
            pass
        parents = cmds.listRelatives(current, parent=True, fullPath=True) or []
        current = parents[0] if parents else None
    return None


def _constraints_connected_to(node, constraint_types):
    result = set()
    for constraint_type in constraint_types:
        try:
            result.update(cmds.listConnections(node, type=constraint_type) or [])
        except Exception:
            pass
    return sorted(result)


def _find_ik_effector_controller(ik_handle):
    """Find the animator-facing transform moving an IK handle."""
    if not ik_handle or not cmds.objExists(ik_handle):
        return None

    parents = cmds.listRelatives(ik_handle, parent=True, fullPath=True) or []
    if parents:
        controller = _nearest_controller_transform(parents[0])
        if controller:
            return controller

    for constraint in _constraints_connected_to(
        ik_handle, ('parentConstraint', 'pointConstraint', 'orientConstraint')
    ):
        for target in _constraint_targets(constraint):
            controller = _nearest_controller_transform(target)
            if controller:
                return controller
            if cmds.objExists(target) and cmds.objectType(target, isAType='transform'):
                return _full_dag_path(target)

    # Last practical fallback: inspect incoming translate/rotate plugs.
    for attribute in ('translate', 'rotate'):
        try:
            plugs = cmds.listConnections(
                '{}.{}'.format(ik_handle, attribute),
                source=True, destination=False, plugs=True,
            ) or []
        except Exception:
            plugs = []
        for plug in plugs:
            source_node = plug.split('.', 1)[0]
            controller = _nearest_controller_transform(source_node)
            if controller:
                return controller
    return None


def _controller_display_color(node):
    shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
    for shape in shapes:
        try:
            if not cmds.getAttr('{}.overrideEnabled'.format(shape)):
                continue
            if cmds.attributeQuery('overrideRGBColors', node=shape, exists=True) and cmds.getAttr(
                '{}.overrideRGBColors'.format(shape)
            ):
                color = cmds.getAttr('{}.overrideColorRGB'.format(shape))[0]
                return _round_vector(color)
            index = int(cmds.getAttr('{}.overrideColor'.format(shape)))
            if index:
                rgb = cmds.colorIndex(index, query=True)
                if rgb:
                    return _round_vector(rgb)
        except Exception:
            continue
    return None


def _locked_channels(node):
    result = []
    for channel in ('tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz'):
        try:
            if cmds.getAttr('{}.{}'.format(node, channel), lock=True):
                result.append(channel)
        except Exception:
            pass
    return result


def _query_transform_snapshot(node, role, module_name, driven_bone, anchor_bone, source_node=None):
    """Capture compact controller data and a bone-local reconstruction offset."""
    if not node or not cmds.objExists(node):
        return None

    node = _full_dag_path(node)
    driven_bone = _full_dag_path(driven_bone) if driven_bone else None
    anchor_bone = _full_dag_path(anchor_bone or driven_bone) if (anchor_bone or driven_bone) else None

    try:
        world_translation = cmds.xform(node, query=True, worldSpace=True, translation=True)
    except Exception:
        return None

    def _query_vector(**kwargs):
        try:
            return _round_vector(cmds.xform(node, query=True, **kwargs))
        except Exception:
            return None

    parents = cmds.listRelatives(node, parent=True, fullPath=True) or []
    shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
    try:
        rotate_order = cmds.xform(node, query=True, rotateOrder=True)
    except Exception:
        rotate_order = None

    return {
        'name': _short_node_name(node),
        'dag_path': node,
        'node_type': cmds.nodeType(node),
        'role': role,
        'module_name': module_name,
        'driven_bone': _short_node_name(driven_bone),
        'anchor_bone': _short_node_name(anchor_bone),
        'source_node': _short_node_name(source_node),
        'parent': _short_node_name(parents[0]) if parents else None,
        'bone_local_position': _world_point_to_node_local(world_translation, anchor_bone),
        'world_transform': {
            'translation': _round_vector(world_translation),
            'rotation': _query_vector(worldSpace=True, rotation=True),
            'scale': _query_vector(worldSpace=True, scale=True),
        },
        'local_transform': {
            'translation': _query_vector(objectSpace=True, translation=True),
            'rotation': _query_vector(objectSpace=True, rotation=True),
            'scale': _query_vector(objectSpace=True, scale=True),
        },
        'rotate_order': rotate_order,
        'shape_types': sorted(set(cmds.nodeType(shape) for shape in shapes)),
        'display_color': _controller_display_color(node),
        'locked_channels': _locked_channels(node),
    }


def _bone_driver_controllers(joint):
    """Return curve controls directly targeting a joint through constraints."""
    controllers = []
    constraints = _constraints_connected_to(
        joint, ('parentConstraint', 'orientConstraint', 'pointConstraint', 'scaleConstraint')
    )
    for constraint in constraints:
        for target in _constraint_targets(constraint):
            controller = _nearest_controller_transform(target)
            if controller and controller not in controllers:
                controllers.append(controller)
    return controllers


def collect_bone_controller_manifest(modules_config):
    """Build bone -> controller snapshots stored once on the root manifest."""
    by_bone = {}
    seen = set()

    def _append(bone, snapshot):
        if not snapshot:
            return
        bone_name = _short_node_name(bone)
        key = (bone_name, snapshot.get('name'), snapshot.get('role'), snapshot.get('module_name'))
        if key in seen:
            return
        seen.add(key)
        by_bone.setdefault(bone_name, []).append(snapshot)

    for module in modules_config or []:
        chain = list(module.get('chain') or [])
        if not chain:
            continue
        module_name = module.get('module_name') or ''

        # Generic FK/direct drivers.
        for bone in chain:
            for controller in _bone_driver_controllers(bone):
                _append(
                    bone,
                    _query_transform_snapshot(
                        controller, 'bone_driver', module_name,
                        driven_bone=bone, anchor_bone=bone,
                    ),
                )

        # IK-specific controls are not necessarily connected to the joints
        # themselves, so capture them explicitly through the ikHandle.
        if module.get('module_type') == 'IKLimb':
            ik_handle = find_ik_handle_for_start_joint(chain[0])
            if not ik_handle:
                continue

            effector_controller = _find_ik_effector_controller(ik_handle)
            effector_node = effector_controller or ik_handle
            _append(
                chain[-1],
                _query_transform_snapshot(
                    effector_node, 'ik_effector', module_name,
                    driven_bone=chain[-1], anchor_bone=chain[-1],
                    source_node=ik_handle,
                ),
            )

            pole_node = _get_pole_vector_node(ik_handle)
            if pole_node and len(chain) >= 2:
                _append(
                    chain[1],
                    _query_transform_snapshot(
                        pole_node, 'pole_vector', module_name,
                        driven_bone=chain[1], anchor_bone=chain[1],
                        source_node=ik_handle,
                    ),
                )

    for records in by_bone.values():
        records.sort(key=lambda item: (item.get('module_name') or '', item.get('role') or '', item.get('name') or ''))
    return dict(sorted(by_bone.items()))


def _joints_driven_by_constraint(joint, constraint_types):
    """Return constraint nodes of given types that have *joint* as their target."""
    result = []
    for ct in constraint_types:
        conns = cmds.listConnections(joint, type=ct, source=False, destination=True) or []
        result.extend(conns)
    return list(set(result))


def _constraint_targets(constraint):
    """Return all target transform nodes driving *constraint*."""
    targets = []
    indices = cmds.getAttr('{}.target'.format(constraint), multiIndices=True) or []
    for idx in indices:
        conns = cmds.listConnections(
            '{}.target[{}].targetTranslate'.format(constraint, idx),
            source=True, destination=False, plugs=False,
        ) or []
        targets.extend(conns)
        # Also check targetRotate for orient constraints. Not every
        # constraint type exposes targetRotate as a connectable point
        # (poleVectorConstraint notably doesn't -- it only drives
        # targetTranslate), and querying it there can raise instead of
        # just returning nothing, depending on Maya version. Guard it.
        try:
            conns2 = cmds.listConnections(
                '{}.target[{}].targetRotate'.format(constraint, idx),
                source=True, destination=False, plugs=False,
            ) or []
        except (ValueError, RuntimeError):
            conns2 = []
        targets.extend(conns2)
    return list(set(targets))


def _upstream_float_control_attr(node, attr):
    """
    Walk upstream connections from node.attr to find the first float/enum
    attribute on a transform/control that is NOT a blend/constraint/math node.
    Returns (node_name, attr_name) or (None, None).
    """
    visited = set()
    queue = [(node, attr)]
    passthrough_types = {
        'blendColors', 'pairBlend', 'parentConstraint', 'orientConstraint',
        'pointConstraint', 'blendTwoAttr', 'unitConversion', 'condition',
    }
    while queue:
        n, a = queue.pop(0)
        key = '{}.{}'.format(n, a)
        if key in visited:
            continue
        visited.add(key)
        upstreams = cmds.listConnections(
            key, source=True, destination=False, plugs=True
        ) or []
        for plug in upstreams:
            parts = plug.split('.')
            src_node = parts[0]
            src_attr = '.'.join(parts[1:])
            node_type = cmds.nodeType(src_node)
            if node_type in passthrough_types:
                queue.append((src_node, src_attr))
            elif node_type == 'transform' or cmds.objectType(src_node, isAType='transform'):
                return src_node, src_attr
    return None, None


# ---------------------------------------------------------------------------
# Structural detector 1: IKFKSwitch (composite -- must run first)
# ---------------------------------------------------------------------------

def _constraint_drives_joint(constraint, joint):
    """True if *constraint*'s own output (constraintTranslate/constraintRotate)
    is connected to *joint*'s translate/rotate -- i.e. *joint* is the
    DRIVEN/bind object of this constraint, not one of its target drivers.

    This is the only unambiguous way to tell the three IKFKSwitch chains
    apart. A plain listConnections() in either direction is NOT enough:
    Maya commonly wires pivot/jointOrient compensation attributes
    (constraintRotatePivot, constraintJointOrient, etc.) FROM the bind
    joint back INTO the constraint as auxiliary inputs, so the bind joint
    shows up connected to the constraint in the same "destination"
    direction as the actual IK/FK target-driver joints do. Without this
    check, detect_ikfk_switch() below matches on all three chains
    independently instead of only the true bind chain.
    """
    for out_attr in ('constraintTranslate', 'constraintRotate'):
        plug = '{}.{}'.format(constraint, out_attr)
        # poleVectorConstraint inherits from pointConstraint in Maya's node
        # type hierarchy, so the type='pointConstraint' filter in the caller
        # also matches poleVectorConstraint nodes -- which have no
        # constraintRotate attribute at all (they only ever drive
        # translation). Same class of issue as the earlier targetRotate fix:
        # check the attribute exists before querying it, since Maya raises
        # instead of just returning nothing for a genuinely absent attribute.
        if not cmds.attributeQuery(out_attr, node=constraint, exists=True):
            continue
        conns = cmds.listConnections(
            plug, source=False, destination=True, plugs=False
        ) or []
        if joint in conns:
            return True
    return False


def detect_ikfk_switch(chain):
    """
    Structural detection of an IK/FK switch on a joint chain.

    Signal: every joint in *chain* (or a subset ending at the third joint) has
    at least one parentConstraint / orientConstraint / pointConstraint / pairBlend
    / blendColors node with exactly two targets traceable back to two distinct
    upstream joint chains (the IK and FK chains).

    Returns a module dict or None.
    """
    if len(chain) < 2:
        return None

    # Examine up to 3 joints to confirm the pattern (avoid expensive full-chain scan).
    sample = chain[:min(3, len(chain))]
    blend_details = []

    for jnt in sample:
        # --- parentConstraint / orientConstraint / pointConstraint ---
        for ct in ('parentConstraint', 'orientConstraint', 'pointConstraint'):
            constraints = cmds.listConnections(
                jnt, type=ct, source=False, destination=True
            ) or []
            for con in constraints:
                if not _constraint_drives_joint(con, jnt):
                    # jnt is a target/driver of this constraint (the IK or FK
                    # chain), not the joint it actually drives -- skip. Only
                    # the true bind chain should produce a module here.
                    continue
                targets = _constraint_targets(con)
                if len(targets) >= 2:
                    # Confirm targets come from joints (not controls/locators alone)
                    tgt_joints = [
                        t for t in targets
                        if cmds.objectType(t, isAType='joint')
                    ]
                    if len(tgt_joints) >= 2:
                        # Find the blend attribute driving the constraint weights.
                        # Exclude compound paths like 'target.targetWeight' (no array
                        # index) which cause ValueError in cmds.listConnections.
                        weight_attrs = [
                            wa for wa in (cmds.listAttr(con, string='*W*') or [])
                            if '.' not in wa
                        ]
                        switch_ctrl, switch_attr = None, None
                        for wa in weight_attrs[:2]:
                            sc, sa = _upstream_float_control_attr(con, wa)
                            if sc:
                                switch_ctrl, switch_attr = sc, sa
                                break
                        blend_details.append({
                            'blend_node_type': 'constraint',
                            'blend_node': con,
                            'switch_control': switch_ctrl,
                            'switch_attr': switch_attr,
                            'ik_chain_root': tgt_joints[0],
                            'fk_chain_root': tgt_joints[1],
                        })

        # --- pairBlend ---
        pb_nodes = cmds.listConnections(jnt, type='pairBlend', source=True) or []
        for pb in pb_nodes:
            # pairBlend.weight drives the blend -- find the upstream switch attr.
            sc, sa = _upstream_float_control_attr(pb, 'weight')
            blend_details.append({
                'blend_node_type': 'pairBlend',
                'blend_node': pb,
                'switch_control': sc,
                'switch_attr': sa,
            })

        # --- blendColors ---
        bc_nodes = cmds.listConnections(jnt, type='blendColors', source=True) or []
        for bc in bc_nodes:
            sc, sa = _upstream_float_control_attr(bc, 'blender')
            blend_details.append({
                'blend_node_type': 'blendColors',
                'blend_node': bc,
                'switch_control': sc,
                'switch_attr': sa,
            })

    if not blend_details:
        return None

    # Pick the first complete blend record.
    best = next((d for d in blend_details if d.get('switch_control')), blend_details[0])

    # Attempt to read the current default value of the switch attribute.
    default_value = 0.0
    if best.get('switch_control') and best.get('switch_attr'):
        try:
            default_value = float(cmds.getAttr(
                '{}.{}'.format(best['switch_control'], best['switch_attr'])
            ))
        except Exception:
            pass

    roles = _chain_roles(len(chain))
    return {
        'module_type': 'IKFKSwitch',
        'module_name': _derive_module_name(chain[0]),
        'chain': [_full_dag_path(j) for j in chain],
        'chain_items': [
            {'bone_name': _full_dag_path(b), 'role': r}
            for b, r in zip(chain, roles)
        ],
        'params': {
            'blend_node_type': best.get('blend_node_type'),
            'blend_node': best.get('blend_node'),
            'switch_control': best.get('switch_control'),
            'switch_attr': best.get('switch_attr'),
            'default_value': default_value,
            # Roots of the internal IK and FK sub-chains so the pipeline can
            # claim (exclude) them from further detection passes.
            'ik_chain_root': best.get('ik_chain_root'),
            'fk_chain_root': best.get('fk_chain_root'),
        },
    }


# ---------------------------------------------------------------------------
# Structural detector 2: SplineIK
# ---------------------------------------------------------------------------

def detect_spline_ik(chain):
    """
    Structural detection of a Spline IK setup on a joint chain.

    Signal: an ikHandle with solver == ikSplineSolver whose startJoint is
    the first joint in *chain*.

    Returns a module dict or None.
    """
    if not chain:
        return None

    ik_handle = find_ik_handle_for_start_joint(chain[0])
    if not ik_handle:
        return None

    solver = _ik_solver_type(ik_handle)
    if 'spline' not in solver.lower() and 'Spline' not in solver:
        return None

    # Driving curve
    curve = None
    curve_degree = None
    cv_count = None
    try:
        curve = cmds.ikHandle(ik_handle, query=True, curve=True)
        if curve:
            curve_degree = cmds.getAttr('{}.degree'.format(curve))
            cv_count = cmds.getAttr('{}.spans'.format(curve)) + curve_degree
    except Exception:
        pass

    # Advanced twist detection
    twist_mode = 'none'
    try:
        twist_enabled = cmds.getAttr('{}.dTwistControlEnable'.format(ik_handle))
        if twist_enabled:
            up_axis = cmds.getAttr('{}.dWorldUpAxis'.format(ik_handle))
            end_obj = cmds.listConnections(
                '{}.dWorldUpVectorEnd'.format(ik_handle), source=True
            ) or []
            twist_mode = 'object' if end_obj else ('axis' if up_axis is not None else 'linear')
    except Exception:
        pass

    # Stretch detection: curveInfo.arcLength -> joint.translateX chain
    stretch_enabled = False
    if curve:
        curve_infos = cmds.listConnections(curve, type='curveInfo') or []
        for ci in curve_infos:
            driven = cmds.listConnections(
                '{}.arcLength'.format(ci), source=False, destination=True
            ) or []
            if driven:
                stretch_enabled = True
                break

    roles = _chain_roles(len(chain))
    return {
        'module_type': 'SplineIK',
        'module_name': _derive_module_name(chain[0]),
        'chain': [_full_dag_path(j) for j in chain],
        'chain_items': [
            {'bone_name': _full_dag_path(b), 'role': r}
            for b, r in zip(chain, roles)
        ],
        'params': {
            'joint_count': len(chain),
            'curve': curve,
            'curve_degree': curve_degree,
            'cv_count': cv_count,
            'twist_mode': twist_mode,
            'stretch_enabled': stretch_enabled,
            'ik_handle': ik_handle,
        },
    }


# ---------------------------------------------------------------------------
# Structural detector 3: IKLimb
# ---------------------------------------------------------------------------

def detect_ik_limb(chain):
    """
    Structural detection of a two-bone (RP/SC) IK limb.

    Signal: an ikHandle whose solver is ikRPsolver or ikSCsolver and whose
    startJoint is chain[0]. Explicitly excluded: ikSplineSolver (-> SplineIK).

    IMPORTANT: *chain* is a candidate from an unbroken parent-child joint
    walk, which has no idea where the ikHandle's solver actually stops. A
    common rig pattern -- IK leg (3 joints) with a separate FK toe chain
    hanging off the ankle with no branch in between -- means the candidate
    chain can extend well past the ikHandle's real end joint. This function
    truncates to the ikHandle's own solved joint list (queried directly from
    Maya, not inferred) and returns whatever trailing joints were cut off so
    the caller can feed them back through detection as their own chain,
    instead of them being silently absorbed into this IK module or dropped.

    Returns (module_dict_or_None, leftover_tail_chain_or_None).
    """
    if len(chain) < 2:
        return None, None

    ik_handle = find_ik_handle_for_start_joint(chain[0])
    if not ik_handle:
        return None, None

    solver = _ik_solver_type(ik_handle)
    solver_lower = solver.lower()
    if 'spline' in solver_lower:
        return None, None  # Belongs to SplineIK
    if 'rp' not in solver_lower and 'sc' not in solver_lower and solver_lower:
        # Unknown solver -- still treat as IKLimb if it is not spline.
        pass

    # Truncate to the joints the ikHandle actually solves, queried directly
    # from Maya rather than inferred from the candidate chain's shape.
    solved_joints = None
    try:
        solved_joints = cmds.ikHandle(ik_handle, query=True, jointList=True) or None
    except Exception:
        pass

    leftover_tail = None
    if solved_joints:
        # jointList returns root..mid joints but NOT the end effector's own
        # joint (Maya quirk) -- the end joint is chain[len(solved_joints)]
        # relative to our candidate chain, provided the candidate actually
        # starts at the same joint (it does, by construction).
        end_index = len(solved_joints)  # inclusive index of the real end joint
        if end_index < len(chain) - 1:
            leftover_tail = chain[end_index + 1:]
            chain = chain[:end_index + 1]
        elif end_index >= len(chain):
            # Defensive: jointList reported more joints than our candidate
            # chain has (shouldn't normally happen) -- trust our own chain
            # instead of over-truncating.
            pass

    pv_node = _get_pole_vector_node(ik_handle)
    pv_pos = get_world_position(pv_node) if pv_node else None

    # Signed local axes are exported as vectors so mirrored limbs retain their
    # true forward direction instead of both collapsing to the same +X default.
    primary_axis = _signed_primary_axis(chain)
    secondary_axis = _secondary_axis_from_pole(chain, pv_pos, primary_axis)
    pv_anchor_bone = chain[1] if len(chain) >= 2 else chain[0]
    pv_local_position = _world_point_to_node_local(pv_pos, pv_anchor_bone) if pv_pos else None

    # Preferred angle per joint
    preferred_angles = {}
    for jnt in chain:
        try:
            pa = cmds.getAttr('{}.preferredAngle'.format(jnt))
            preferred_angles[jnt] = list(pa[0]) if pa else [0.0, 0.0, 0.0]
        except Exception:
            preferred_angles[jnt] = [0.0, 0.0, 0.0]

    roles = _chain_roles(len(chain))
    result = {
        'module_type': 'IKLimb',
        'module_name': _derive_module_name(chain[0]),
        'chain': [_full_dag_path(j) for j in chain],
        'chain_items': [
            {'bone_name': _full_dag_path(b), 'role': r}
            for b, r in zip(chain, roles)
        ],
        'params': {
            'primary_axis': primary_axis,
            'secondary_axis': secondary_axis,
            'pole_vector_world_position': pv_pos,
            'pole_vector_local_position': pv_local_position,
            'pole_vector_anchor_bone': _short_node_name(pv_anchor_bone),
            'pole_vector_node': pv_node,
            'ik_handle': ik_handle,
            'solver': solver,
            'preferred_angles': preferred_angles,
            'default_ikfk': 1.0,
        },
    }
    # Preserve legacy recipe field used by UE5 IKModule.
    if pv_pos:
        result['recipe'] = {'pole_vector_world_position': pv_pos}
    return result, leftover_tail


# ---------------------------------------------------------------------------
# Structural detector 4: FKChain (catch-all)
# ---------------------------------------------------------------------------

def detect_fk_chain(chain):
    """
    Structural detection of a plain FK chain.

    A chain is FK when:
    - No ikHandle has any joint in the chain as startJoint.
    - No parentConstraint/orientConstraint with multiple targets on each joint
      (that pattern belongs to IKFKSwitch).
    - No scaleConstraint / pointOnCurveInfo driving the joints (SplineIK
      stretch patterns).

    Returns a module dict or None.
    """
    if not chain:
        return None

    for jnt in chain:
        if find_ik_handle_for_start_joint(jnt):
            return None
        poci = cmds.listConnections(jnt, type='pointOnCurveInfo', source=True) or []
        if poci:
            return None

    # Preferred angle and rotate order per joint
    joint_params = []
    for jnt in chain:
        try:
            ro = cmds.getAttr('{}.rotateOrder'.format(jnt))
            pa = cmds.getAttr('{}.preferredAngle'.format(jnt))
            joint_params.append({
                'joint': _full_dag_path(jnt),
                'rotate_order': ro,
                'preferred_angle': list(pa[0]) if pa else [0.0, 0.0, 0.0],
            })
        except Exception:
            joint_params.append({'joint': _full_dag_path(jnt)})

    roles = _chain_roles(len(chain))
    return {
        'module_type': 'FKChain',
        'module_name': _derive_module_name(chain[0]),
        'chain': [_full_dag_path(j) for j in chain],
        'chain_items': [
            {'bone_name': _full_dag_path(b), 'role': r}
            for b, r in zip(chain, roles)
        ],
        'params': {
            'joint_count': len(chain),
            'joint_params': joint_params,
        },
    }


# ---------------------------------------------------------------------------
# Additive detector 5: SquashStretch (attaches params, does not own joints)
# ---------------------------------------------------------------------------

def detect_squash_stretch(chain):
    """
    Structural detection of a squash-and-stretch setup on *chain*.

    Checks for two patterns:
    1. Curve-arc-length driven: curveInfo.arcLength -> multiplyDivide -> joint.scaleX
    2. Distance-based: distanceBetween -> multiplyDivide -> joint.scaleX (or translateX)

    Returns a params dict (not a full module dict) or None.
    Volume preservation is flagged when the inverse scale feeds the perpendicular axes.
    """
    if not chain:
        return None

    driver_type = None
    rest_length = None
    stretch_axis = None
    volume_preservation = False
    min_max_clamp = False

    for jnt in chain:
        # --- Pattern 1: curveInfo arc-length ---
        for scale_attr in ('scaleX', 'scaleY', 'scaleZ', 'translateX'):
            upstream = cmds.listConnections(
                '{}.{}'.format(jnt, scale_attr), source=True, destination=False
            ) or []
            for node in upstream:
                nt = cmds.nodeType(node)
                if nt == 'multiplyDivide':
                    inputs = cmds.listConnections(
                        node, source=True, destination=False
                    ) or []
                    for inp in inputs:
                        if cmds.nodeType(inp) == 'curveInfo':
                            driver_type = 'curve_arc_length'
                            stretch_axis = scale_attr[-1]
                            try:
                                rest_length = cmds.getAttr('{}.arcLength'.format(inp))
                            except Exception:
                                pass
                        elif cmds.nodeType(inp) == 'distanceBetween':
                            driver_type = 'distance'
                            stretch_axis = scale_attr[-1]
                            try:
                                rest_length = cmds.getAttr('{}.distance'.format(inp))
                            except Exception:
                                pass
                if nt == 'clamp':
                    min_max_clamp = True

        if driver_type:
            break

    if not driver_type:
        # --- Pattern 2: distanceBetween on a locator attached to chain ends ---
        dist_nodes = []
        for jnt in (chain[0], chain[-1]):
            conns = cmds.listConnections(jnt, type='distanceBetween') or []
            dist_nodes.extend(conns)
        if dist_nodes:
            driver_type = 'distance'
            try:
                rest_length = cmds.getAttr('{}.distance'.format(dist_nodes[0]))
            except Exception:
                pass
            stretch_axis = 'X'

    if not driver_type:
        return None

    # Volume preservation: check if a perpendicular scale axis is inversely driven.
    perp_axes = [a for a in ('X', 'Y', 'Z') if a != stretch_axis]
    for jnt in chain[:2]:
        for ax in perp_axes:
            ups = cmds.listConnections(
                '{}.scale{}'.format(jnt, ax), source=True, destination=False
            ) or []
            for node in ups:
                if cmds.nodeType(node) in ('multiplyDivide', 'expression'):
                    volume_preservation = True
                    break

    return {
        'driver_type': driver_type,
        'rest_length': rest_length,
        'stretch_axis': stretch_axis,
        'volume_preservation': volume_preservation,
        'min_max_clamp': min_max_clamp,
    }


# ---------------------------------------------------------------------------
# Module name helper
# ---------------------------------------------------------------------------

def _derive_module_name(joint):
    """Derive a human-readable module name from the first joint in a chain.

    Uses the naming convention if present ({side}_{part}_{index}_jnt),
    otherwise falls back to the short joint name stripped of its _jnt suffix.
    """
    short = joint.split('|')[-1]
    parsed = _parse_joint_name(short)
    if parsed:
        side, part, _ = parsed
        return '{}_{}'.format(side, part) if side else part
    return re.sub(r'_\d+_jnt$', '', short, flags=re.IGNORECASE) or short


# ---------------------------------------------------------------------------
# Chain extraction from scene hierarchy
# ---------------------------------------------------------------------------

def _collect_chains_from_root(root_joint):
    """
    Recursively collect every linear joint chain descending from *root_joint*.

    A "chain" is a sequence of joints with no branching -- when a joint has
    multiple joint children, the chain ends there and new chains start for
    each child.  Single-joint leaf nodes are still returned as 1-element chains.

    Returns a list of lists: [[j1, j2, j3], [j4, j5], ...]
    """
    chains = []

    def _walk(current, current_chain):
        children = cmds.listRelatives(current, children=True, type='joint') or []
        current_chain.append(current)
        if len(children) == 0:
            chains.append(list(current_chain))
        elif len(children) == 1:
            _walk(children[0], current_chain)
        else:
            # Branch: close current chain and start fresh for each child.
            chains.append(list(current_chain))
            for child in children:
                _walk(child, [])

    _walk(root_joint, [])
    return chains


def _get_scene_root_joints():
    """Return all joints in the scene that have no joint parent (scene roots)."""
    roots = []
    for jnt in cmds.ls(type='joint') or []:
        parents = cmds.listRelatives(jnt, parent=True, type='joint') or []
        if not parents:
            roots.append(jnt)
    return roots


# ---------------------------------------------------------------------------
# Detection pipeline orchestrator
# ---------------------------------------------------------------------------

def run_detection_pipeline(root_joint=None):
    """
    Run the full structural detection pipeline for all joint chains.

    Priority order (joints are marked as claimed to avoid double-detection):
      1. IKFKSwitch  (composite -- sees both FK and IK chains)
      2. SplineIK
      3. IKLimb
      4. FKChain    (catch-all)
      5. SquashStretch (additive -- attaches params, does not claim joints)

    Args:
        root_joint: Optional joint name to scope detection. If None,
                    defaults to ROOT_JOINT_NAME (the actual exported game
                    skeleton's root) when it exists in the scene, falling
                    back to a full scene-wide scan only if it doesn't.

                    This matters because a Maya scene can contain joints
                    that are NOT part of the exported skeleton at all --
                    e.g. helper joints parented under a NURBS control curve
                    hierarchy (RootCtrl|...|SomeCtrl|HelperJoint) used to
                    skin/drive a Spline IK curve from an animator control.
                    Those joints have no joint parent, so a scene-wide scan
                    picks them up as their own chain roots and happily
                    classifies them as real modules -- but they were never
                    exported to the Skeletal Mesh (only descendants of the
                    real skeleton root are), so the UE5 builder correctly
                    reports "Bone not found" for them. Scoping to
                    ROOT_JOINT_NAME by default keeps detection to only the
                    joints that will actually exist on the UE5 side.

    Returns:
        List of module dicts ready for build_manifest().
    """
    if root_joint:
        root_joints = [root_joint]
    elif cmds.objExists(ROOT_JOINT_NAME) and cmds.nodeType(ROOT_JOINT_NAME) == 'joint':
        root_joints = [ROOT_JOINT_NAME]
    else:
        root_joints = _get_scene_root_joints()
        # Remove the manifest root if it has no rig children.
        root_joints = [
            r for r in root_joints
            if r != ROOT_JOINT_NAME or len(
                cmds.listRelatives(r, children=True, type='joint') or []
            ) > 0
        ]

    # Gather all chains from the scene.
    all_chains = []
    for rj in root_joints:
        all_chains.extend(_collect_chains_from_root(rj))

    # Filter out single-joint chains that are the manifest root itself.
    all_chains = [c for c in all_chains if not (len(c) == 1 and c[0] == ROOT_JOINT_NAME)]

    claimed = set()   # joints already assigned to a module
    modules = []

    def _is_unclaimed(chain):
        return not any(j in claimed for j in chain)

    def _claim(chain):
        claimed.update(chain)

    # --- Pass 1: IKFKSwitch ---
    for chain in all_chains:
        if not _is_unclaimed(chain):
            continue
        result = detect_ikfk_switch(chain)
        if result:
            _claim(chain)
            modules.append(result)
            # Also claim the internal IK and FK sub-chains so they are not
            # independently detected as IKLimb / FKChain and written into the
            # manifest.  Their joints do not exist in the exported FBX skeleton.
            for root_key in ('ik_chain_root', 'fk_chain_root'):
                sub_root = (result.get('params') or {}).get(root_key)
                if sub_root and cmds.objExists(sub_root):
                    sub_chain = _collect_chains_from_root(sub_root)
                    for sc in sub_chain:
                        _claim(sc)

    # --- Pass 2: SplineIK ---
    for chain in all_chains:
        if not _is_unclaimed(chain):
            continue
        result = detect_spline_ik(chain)
        if result:
            _claim(chain)
            modules.append(result)

    # --- Pass 3: IKLimb ---
    for chain in all_chains:
        if not _is_unclaimed(chain):
            continue
        result, leftover_tail = detect_ik_limb(chain)
        if result:
            # Only claim the joints actually used by the IK module -- not
            # the original candidate chain, which may have extended past
            # the ikHandle's real end joint (e.g. an FK toe chain hanging
            # off the ankle with no branch point in between).
            used_chain = chain[:len(chain) - len(leftover_tail)] if leftover_tail else chain
            _claim(used_chain)
            modules.append(result)
            if leftover_tail:
                # Feed the trailing joints back into detection as their own
                # candidate chain (e.g. Toe_FK_1/Toe_FK_2) rather than
                # silently dropping them. Pass 4 below will pick them up.
                all_chains.append(leftover_tail)
                print('[RigManifest] {} extends past its IK solver -- '
                      're-queuing leftover joints as a separate chain: {}'.format(
                          chain[0], leftover_tail))

    # --- Pass 4: FKChain (catch-all) ---
    for chain in all_chains:
        if not _is_unclaimed(chain):
            continue
        result = detect_fk_chain(chain)
        if result:
            _claim(chain)
            modules.append(result)

    # --- Pass 5: SquashStretch (additive) ---
    for mod in modules:
        ss = detect_squash_stretch(mod.get('chain', []))
        if ss:
            mod.setdefault('params', {})['squash_stretch'] = ss

    if modules:
        print('[RigManifest] Detection pipeline found {} module(s): {}'.format(
            len(modules),
            ', '.join('{} ({})'.format(m['module_name'], m['module_type']) for m in modules),
        ))
    else:
        print('[RigManifest] Detection pipeline: no modules found. '
              'Check that joints follow the {side}_{part}_{index:02d}_jnt convention '
              'or call run_detection_pipeline(root_joint="your_root").')

    return modules


def auto_discover_modules():
    """Entry point used by export() and register_auto_update().

    Delegates entirely to run_detection_pipeline() -- structural detection
    only, no name-based type guessing.
    """
    return run_detection_pipeline()


# ---------------------------------------------------------------------------
# Scene helpers
# ---------------------------------------------------------------------------

def collect_visible_mesh_transforms():
    """Return transform nodes for every non-intermediate mesh in the scene."""
    mesh_transforms = []
    for mesh in cmds.ls(type="mesh") or []:
        if cmds.getAttr("{}.intermediateObject".format(mesh)):
            continue
        parents = cmds.listRelatives(mesh, parent=True) or []
        if parents and parents[0] not in mesh_transforms:
            mesh_transforms.append(parents[0])
    return mesh_transforms


# ---------------------------------------------------------------------------
# Manifest building / module dependency graph
# ---------------------------------------------------------------------------

def _short_joint_name(node):
    """Return the UE-compatible bone name without Maya DAG path prefixes."""
    return str(node).split("|")[-1]


def _canonical_joint(node):
    """Return a stable full DAG path for comparisons inside Maya."""
    try:
        matches = cmds.ls(node, long=True) or []
        return matches[0] if matches else str(node)
    except Exception:
        return str(node)


def _joint_parent(node):
    """Return the full-path joint parent of *node*, or None."""
    try:
        parents = cmds.listRelatives(
            node, parent=True, type="joint", fullPath=True
        ) or []
        return parents[0] if parents else None
    except Exception:
        return None


def _append_graph_issue(module_issues, module_name, severity, message):
    module_issues.setdefault(module_name, []).append({
        "severity": severity,
        "message": message,
    })


# Per module type, which control corresponds to roughly the root / middle /
# tip of that module's own chain. Used to pick a control near WHERE the
# child actually attaches, not just a fixed default regardless of position --
# confirmed necessary from a real build where a leg attaching near a spine's
# ROOT and a head attaching near its TIP both got the same fixed
# "spline_tip_ctrl" default, yanking the leg control up to the wrong end.
#
# IKLimb has no root-only control (only an effector at the tip and,
# for 3-bone chains, a pole vector roughly at the middle) -- "effector" is
# used for both root and tip since it's the only control that always
# exists, but this means a module attaching near an IKLimb's OWN root bone
# currently has no truly correct control to attach to. Flagging this as a
# real architecture gap, not silently papered over: IKLimb would need a
# root-position control added to fully support this.
_POSITION_ATTACH_POINTS_BY_TYPE = {
    "SplineIK": {"root": "spline_root_ctrl", "mid": "spline_mid_ctrl", "tip": "spline_tip_ctrl"},
    "FKChain": {"root": "fk_root_ctrl", "mid": "fk_mid_ctrl", "tip": "fk_tip_ctrl"},
    "IKFKSwitch": {"root": "fk_root_ctrl", "mid": "fk_mid_ctrl", "tip": "fk_tip_ctrl"},
    "IKLimb": {"root": "effector", "mid": "pole_vector", "tip": "effector"},
}

_DEFAULT_ATTACH_POINT_BY_MODULE_TYPE = {
    "FKChain": "fk_tip_ctrl",
    "IKLimb": "effector",
    "IKFKSwitch": "ik_effector",
    "SplineIK": "spline_tip_ctrl",
}


def _attach_point_for_bone_position(parent_module_name, parent_bone, modules_config):
    """Resolve an attach point based on WHERE parent_bone sits in the parent
    module's own chain (near the root, middle, or tip), instead of always
    using a single fixed default regardless of position.
    """
    parent_mod = next(
        (mod for mod in modules_config if mod.get("module_name") == parent_module_name), None
    )
    if not parent_mod:
        return "fk_tip_ctrl"

    parent_type = parent_mod.get("module_type")
    chain = [_short_joint_name(bone) for bone in (parent_mod.get("chain") or [])]
    position_map = _POSITION_ATTACH_POINTS_BY_TYPE.get(parent_type)
    fallback = _DEFAULT_ATTACH_POINT_BY_MODULE_TYPE.get(parent_type, "fk_tip_ctrl")

    if not position_map or not chain:
        return fallback

    try:
        index = chain.index(_short_joint_name(parent_bone))
    except ValueError:
        return fallback

    if len(chain) == 1:
        position = "root"
    else:
        ratio = index / (len(chain) - 1)
        position = "root" if ratio < 0.34 else "tip" if ratio > 0.66 else "mid"

    return position_map.get(position, fallback)


def analyze_module_graph(modules_config):
    """Analyze inter-module attachment and calculate a deterministic UE5 order.

    The closest ancestor joint owned by another tagged module becomes the
    parent connection. A stable topological sort then guarantees that every
    parent module is constructed before its children.

    Returns a JSON-serializable dictionary containing:
      - connections: child module -> attachment metadata
      - build_order: parent-before-child module names
      - build_index / depth: convenient lookup tables
      - module_issues / global_issues: green/orange/red validation support
      - valid: False when a red graph error exists
    """
    modules_config = list(modules_config or [])
    module_issues = {}
    global_issues = []

    names = [mod.get("module_name", "") for mod in modules_config]
    original_index = {}
    for index, name in enumerate(names):
        if name and name not in original_index:
            original_index[name] = index

    # Duplicate module names make dependency references ambiguous.
    seen_names = set()
    duplicate_names = set()
    for name in names:
        if not name:
            continue
        if name in seen_names:
            duplicate_names.add(name)
        seen_names.add(name)
    for name in sorted(duplicate_names):
        message = "duplicate module name '{}'".format(name)
        global_issues.append({"severity": "red", "message": message})
        _append_graph_issue(module_issues, name, "red", message)

    # A skeleton joint should normally be owned by exactly one output module.
    bone_to_modules = {}
    bone_display_name = {}
    for mod in modules_config:
        module_name = mod.get("module_name", "")
        for bone in mod.get("chain", []) or []:
            key = _canonical_joint(bone)
            bone_to_modules.setdefault(key, []).append(module_name)
            bone_display_name[key] = _short_joint_name(bone)

    for bone_key, owners in bone_to_modules.items():
        unique_owners = sorted(set(owner for owner in owners if owner))
        if len(unique_owners) <= 1:
            continue
        message = "bone '{}' is shared by modules {}".format(
            bone_display_name.get(bone_key, _short_joint_name(bone_key)),
            ", ".join(unique_owners),
        )
        global_issues.append({"severity": "red", "message": message})
        for owner in unique_owners:
            _append_graph_issue(module_issues, owner, "red", message)

    connections = {}
    root_modules = []

    for mod in modules_config:
        module_name = mod.get("module_name", "")
        chain = list(mod.get("chain", []) or [])
        if not module_name or not chain:
            if module_name:
                _append_graph_issue(module_issues, module_name, "red", "module has an empty chain")
            continue

        start_bone = chain[0]
        parent = _joint_parent(start_bone)
        skipped_ancestors = []
        connection = None

        while parent:
            parent_key = _canonical_joint(parent)
            owners = sorted(set(
                owner for owner in bone_to_modules.get(parent_key, [])
                if owner and owner != module_name
            ))

            if len(owners) == 1:
                connection = {
                    "parent_module": owners[0],
                    # Resolved from WHERE parent (the bone) sits in the
                    # parent module's own chain -- not a fixed per-type
                    # default. "root"/"tip"/"mid" bone names are still never
                    # used directly here; those map to bones, not controls,
                    # and can never resolve through
                    # RigContext.get_parent_control_key.
                    "parent_attach_point": _attach_point_for_bone_position(
                        owners[0], parent, modules_config
                    ),
                    # New explicit semantic attachment data for the future UE5.6 builder.
                    "parent_bone": _short_joint_name(parent),
                    "child_attach_bone": _short_joint_name(start_bone),
                    "relationship": "maya_joint_hierarchy",
                    "skipped_ancestor_bones": [
                        _short_joint_name(item) for item in skipped_ancestors
                    ],
                }
                break

            if len(owners) > 1:
                message = "ambiguous parent bone '{}' belongs to {}".format(
                    _short_joint_name(parent), ", ".join(owners)
                )
                _append_graph_issue(module_issues, module_name, "red", message)
                break

            skipped_ancestors.append(parent)
            parent = _joint_parent(parent)

        if connection:
            connections[module_name] = connection
        else:
            root_modules.append(module_name)
            # A single untagged skeleton root is expected. A deeper untagged
            # joint region means the module can still build, but attachment is
            # not semantically certain, so expose it as orange in the tool.
            meaningful = [
                item for item in skipped_ancestors
                if _short_joint_name(item) != ROOT_JOINT_NAME
            ]
            if meaningful:
                _append_graph_issue(
                    module_issues,
                    module_name,
                    "orange",
                    "no parent module found above '{}'; untagged ancestors: {}".format(
                        _short_joint_name(start_bone),
                        ", ".join(_short_joint_name(item) for item in meaningful),
                    ),
                )

    # Parent-before-child topological sort. Siblings are stable and
    # deterministic by original module order, then name.
    unique_names = []
    for name in names:
        if name and name not in unique_names:
            unique_names.append(name)

    children = {name: [] for name in unique_names}
    indegree = {name: 0 for name in unique_names}
    for child_name, connection in connections.items():
        parent_name = connection.get("parent_module")
        if child_name not in indegree or parent_name not in indegree:
            continue
        children[parent_name].append(child_name)
        indegree[child_name] += 1

    sort_key = lambda name: (original_index.get(name, 10 ** 9), name.lower())
    queue = sorted([name for name in unique_names if indegree[name] == 0], key=sort_key)
    build_order = []

    while queue:
        current = queue.pop(0)
        build_order.append(current)
        for child in sorted(children.get(current, []), key=sort_key):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
                queue.sort(key=sort_key)

    cyclic_modules = [name for name in unique_names if name not in build_order]
    if cyclic_modules:
        message = "cyclic module dependency: {}".format(
            " -> ".join(sorted(cyclic_modules))
        )
        global_issues.append({"severity": "red", "message": message})
        for name in cyclic_modules:
            _append_graph_issue(module_issues, name, "red", message)
        # Keep the manifest deterministic even when invalid, so the UI can
        # display and diagnose it instead of crashing.
        build_order.extend(sorted(cyclic_modules, key=sort_key))

    build_index = {name: index for index, name in enumerate(build_order)}
    depth = {}
    for name in build_order:
        parent_name = (connections.get(name) or {}).get("parent_module")
        depth[name] = depth.get(parent_name, -1) + 1 if parent_name else 0

    has_red = any(
        issue.get("severity") == "red"
        for issues in module_issues.values()
        for issue in issues
    ) or any(issue.get("severity") == "red" for issue in global_issues)

    return {
        "valid": not has_red,
        "connections": connections,
        "root_modules": root_modules,
        "build_order": build_order,
        "build_index": build_index,
        "depth": depth,
        "module_issues": module_issues,
        "global_issues": global_issues,
    }


def _detect_connections(modules_config):
    """Compatibility wrapper returning child -> parent module names."""
    analysis = analyze_module_graph(modules_config)
    return {
        child: data.get("parent_module")
        for child, data in analysis.get("connections", {}).items()
    }


def _merge_scene_detected_module_data(module):
    """Reattach structural Maya data to the clean tagger module definition.

    The tagger intentionally stores only ownership/endpoints on joints. This
    enrichment step restores per-instance solver information immediately before
    JSON creation, so the manifest remains clean while no IK data is lost.
    """
    enriched = dict(module)
    enriched['chain'] = list(module.get('chain') or [])
    enriched['chain_items'] = [dict(item) for item in (module.get('chain_items') or [])]

    detected = None
    if enriched.get('module_type') == 'IKLimb' and enriched['chain']:
        detected, _ = detect_ik_limb(list(enriched['chain']))

    if detected:
        merged_params = dict(detected.get('params') or {})
        merged_params.update(enriched.get('params') or {})
        if merged_params:
            enriched['params'] = merged_params

        merged_recipe = dict(detected.get('recipe') or {})
        merged_recipe.update(enriched.get('recipe') or {})
        if merged_recipe:
            enriched['recipe'] = merged_recipe

    return enriched


def build_manifest(rig_name, modules_config):
    """Build a schema-v3 manifest with modules and bone-linked controllers."""
    modules_config = [
        _merge_scene_detected_module_data(module)
        for module in (modules_config or [])
    ]
    graph = analyze_module_graph(modules_config)
    build_index = graph.get("build_index", {})

    indexed_modules = list(enumerate(modules_config))
    indexed_modules.sort(key=lambda pair: (
        build_index.get(pair[1].get("module_name"), 10 ** 9),
        pair[0],
    ))

    modules = []
    for _, mod in indexed_modules:
        raw_chain = list(mod.get("chain", []) or [])
        chain = [_short_joint_name(bone) for bone in raw_chain]

        raw_chain_items = list(mod.get("chain_items", []) or [])
        if raw_chain_items:
            chain_items = []
            for item in raw_chain_items:
                copied = dict(item)
                copied["bone_name"] = _short_joint_name(copied.get("bone_name", ""))
                chain_items.append(copied)
        else:
            roles = _chain_roles(len(chain))
            chain_items = [
                {"bone_name": bone, "role": role}
                for bone, role in zip(chain, roles)
            ]

        module_name = mod["module_name"]
        module_def = {
            "module_type": mod["module_type"],
            "module_name": module_name,
            "chain": chain,
            "chain_items": chain_items,
            "start_bone": _short_joint_name(mod.get("start_bone") or (raw_chain[0] if raw_chain else "")),
            "end_bone": _short_joint_name(mod.get("end_bone") or (raw_chain[-1] if raw_chain else "")),
            "build_order": build_index.get(module_name),
            "build_depth": graph.get("depth", {}).get(module_name, 0),
            "depends_on": [],
        }

        if mod.get("params"):
            module_def["params"] = mod["params"]

        connection = graph.get("connections", {}).get(module_name)
        if connection:
            module_def["connections"] = dict(connection)
            module_def["depends_on"] = [connection.get("parent_module")]

        # Preserve legacy "recipe" field for IKLimb so the UE5 IKModule can
        # read pole_vector_world_position without touching the params dict.
        if mod.get("recipe"):
            module_def["recipe"] = mod["recipe"]
        elif mod["module_type"] == "IKLimb":
            pv = (mod.get("params") or {}).get("pole_vector_world_position")
            if pv:
                module_def["recipe"] = {"pole_vector_world_position": pv}

        modules.append(module_def)

    serializable_connections = {
        name: dict(data) for name, data in graph.get("connections", {}).items()
    }
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "rig_name": rig_name,
        "module_build_order": list(graph.get("build_order", [])),
        "module_graph": {
            "valid": graph.get("valid", True),
            "root_modules": list(graph.get("root_modules", [])),
            "connections": serializable_connections,
            "issues": list(graph.get("global_issues", [])),
            "module_issues": dict(graph.get("module_issues", {})),
        },
        "bone_controllers": collect_bone_controller_manifest(modules_config),
        "modules": modules,
    }


# ---------------------------------------------------------------------------
# Root joint manifest attribute
# ---------------------------------------------------------------------------

def write_manifest_to_joint(joint_name, json_str):
    """
    Write the compact manifest JSON onto an existing joint's rig_manifest_json
    attribute.  This never creates joints or changes the scene hierarchy --
    it only adds the attribute (first run) and updates its value (every run).

    Raises RuntimeError if joint_name does not exist in the scene.
    """
    if not cmds.objExists(joint_name):
        raise RuntimeError(
            "Root joint '{}' does not exist in the scene. "
            "Set ROOT_JOINT_NAME to the name of your existing root joint.".format(joint_name)
        )

    if not cmds.attributeQuery(MANIFEST_ATTR, node=joint_name, exists=True):
        cmds.addAttr(
            joint_name,
            longName=MANIFEST_ATTR,
            dataType="string",
            storable=True,
        )

    cmds.setAttr("{}.{}".format(joint_name, MANIFEST_ATTR), json_str, type="string")
    print("[RigManifest] Manifest written to '{}.{}'.".format(joint_name, MANIFEST_ATTR))


# ---------------------------------------------------------------------------
# Manifest update and auto-update
# ---------------------------------------------------------------------------

def update_manifest(rig_name, modules_config):
    """
    Rebuild the manifest from modules_config and write it to the root joint.
    Does NOT export FBX -- use this for iterative updates during rigging.
    """
    manifest = build_manifest(rig_name, modules_config)
    compact_json = json.dumps(manifest, separators=(",", ":"))
    write_manifest_to_joint(ROOT_JOINT_NAME, compact_json)
    print("[RigManifest] Manifest updated.")


def deregister_auto_update():
    """Kill all scriptJobs previously registered by register_auto_update()."""
    global _AUTO_UPDATE_JOBS
    killed = 0
    for job_id in _AUTO_UPDATE_JOBS:
        try:
            if cmds.scriptJob(exists=job_id):
                cmds.scriptJob(kill=job_id, force=True)
                killed += 1
        except Exception:
            pass
    _AUTO_UPDATE_JOBS = []
    if killed:
        print("[RigManifest] Deregistered {} auto-update job(s).".format(killed))


def register_auto_update(rig_name, modules_config):
    """
    Install Maya scriptJobs that call update_manifest() automatically when
    relevant scene changes occur:
      - Scene opened or read from disk (SceneOpened, PostSceneRead).
      - Any IK pole vector control is translated.

    Safe to call multiple times -- cancels previous jobs before registering new ones.
    Call deregister_auto_update() to stop watching.
    """
    deregister_auto_update()

    def _callback(*args):
        try:
            update_manifest(rig_name, modules_config)
        except Exception as exc:
            print("[RigManifest] Auto-update failed: {}".format(exc))

    # Scene file events
    for event_name in ("SceneOpened", "PostSceneRead"):
        _AUTO_UPDATE_JOBS.append(
            cmds.scriptJob(event=[event_name, _callback], protected=False)
        )

    # Per-module: watch each IK pole vector control's translate
    for mod in modules_config:
        if mod["module_type"] != "IKLimb":
            continue
        chain = mod.get("chain", [])
        if len(chain) < 3:
            continue
        ik_handle = find_ik_handle_for_start_joint(chain[0])
        pv_node = _get_pole_vector_node(ik_handle)
        if not pv_node or not cmds.objExists(pv_node):
            continue
        _AUTO_UPDATE_JOBS.append(
            cmds.scriptJob(
                attributeChange=["{}.translate".format(pv_node), _callback],
                protected=False,
            )
        )
        print("[RigManifest] Watching pole vector '{}' on module '{}'.".format(
            pv_node, mod["module_name"]
        ))

    print("[RigManifest] Auto-update active ({} job(s)). Call deregister_auto_update() to stop.".format(
        len(_AUTO_UPDATE_JOBS)
    ))


# ---------------------------------------------------------------------------
# FBX export
# ---------------------------------------------------------------------------

def _restore_bind_pose(modules_config):
    """Attempt to restore the skeleton to its bind pose before export."""
    joints = [bone for mod in modules_config for bone in mod.get("chain", [])]
    try:
        cmds.dagPose(joints, restore=True, bindPose=True)
        print("[RigManifest] Bind pose restored.")
    except Exception as exc:
        print("[RigManifest] Could not restore bind pose ({}). Exporting current pose.".format(exc))


def export_fbx(fbx_path, export_nodes):
    """Configure the Maya FBX exporter and export selected nodes."""
    cmds.select(export_nodes, replace=True)

    mel.eval("FBXResetExport")
    mel.eval("FBXExportSmoothingGroups -v true")
    mel.eval("FBXExportHardEdges -v false")
    mel.eval("FBXExportTangents -v false")
    mel.eval("FBXExportSmoothMesh -v true")
    mel.eval("FBXExportInputConnections -v false")
    mel.eval("FBXExportShapes -v true")
    mel.eval("FBXExportSkins -v true")
    mel.eval("FBXExportSkeletonDefinitions -v true")
    mel.eval("FBXExportConstraints -v false")
    mel.eval("FBXExportCameras -v false")
    mel.eval("FBXExportLights -v false")
    mel.eval("FBXExportEmbeddedTextures -v false")
    mel.eval("FBXExportBakeComplexAnimation -v false")
    mel.eval("FBXExportUpAxis y")
    mel.eval("FBXExportFileVersion -v FBX201800")
    mel.eval('FBXExport -f "{}" -s'.format(fbx_path.replace("\\", "/")))

    cmds.select(clear=True)
    print("[RigManifest] FBX exported: {}".format(fbx_path))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def export(export_dir, filename_base, rig_name, modules_config):
    """
    Full export pipeline:
      1. Build the manifest from modules_config + scene-detected data.
      2. Create/update the root joint with the manifest attribute.
      3. Restore the bind pose, then export FBX (root joint + meshes).

    Args:
        export_dir (str):      Absolute path to the output folder (created if absent).
        filename_base (str):   Base name for the .fbx file.
        rig_name (str):        Identifier stored inside the manifest.
        modules_config (list): Explicit module definitions (see RIG_MODULES below).

    Returns:
        str: Path to the exported FBX file.
    """
    os.makedirs(export_dir, exist_ok=True)
    fbx_path = os.path.join(export_dir, "{}.fbx".format(filename_base))

    manifest = build_manifest(rig_name, modules_config)
    compact_json = json.dumps(manifest, separators=(",", ":"))
    write_manifest_to_joint(ROOT_JOINT_NAME, compact_json)

    _restore_bind_pose(modules_config)

    mesh_transforms = collect_visible_mesh_transforms()
    export_nodes = [ROOT_JOINT_NAME] + mesh_transforms

    export_fbx(fbx_path, export_nodes)

    print("[RigManifest] Export complete -> {}".format(fbx_path))
    return fbx_path


# ---------------------------------------------------------------------------
# Configuration -- edit only EXPORT_DIR, FILENAME, and RIG_NAME.
# RIG_MODULES is built automatically from joints named {side}_{part}_{index:02d}_jnt
# (e.g. L_leg_01_jnt, R_arm_02_jnt, spine_01_jnt).
# You can override RIG_MODULES with an explicit list if needed.
#
# This block now only runs when the file is executed directly (e.g. from the
# Script Editor), not on `import export_rig_manifest`. rig_tagger_tool.py
# imports this module purely for its helper functions (build_manifest,
# export, find_ik_handle_for_start_joint, etc.) and must not trigger the old
# auto-discovery export as a side effect of that import.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    EXPORT_DIR = r"C:\Users\jeanf\Desktop\DataAsset test\Export"
    FILENAME = "MultiModule"
    RIG_NAME = "MultiModule"

    RIG_MODULES = auto_discover_modules()

    export(EXPORT_DIR, FILENAME, RIG_NAME, RIG_MODULES)
    register_auto_update(RIG_NAME, RIG_MODULES)