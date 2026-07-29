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

    Uses cmds.isConnected() for the actual test rather than comparing name
    strings from two separate listConnections() calls -- string comparison
    is fragile to Maya returning different valid representations of the
    same node (short name vs DAG path, namespace prefixes, disambiguation
    suffixes) depending on which query produced it, and a mismatch there
    silently makes this always return False, rejecting the correct bind
    chain along with the incorrect ones. isConnected() checks plug
    identity directly, with no name-matching involved.
    """
    for out_attr, in_attr in (('constraintTranslate', 'translate'), ('constraintRotate', 'rotate')):
        # poleVectorConstraint inherits from pointConstraint in Maya's node
        # type hierarchy, so the type='pointConstraint' filter in the caller
        # also matches poleVectorConstraint nodes -- which have no
        # constraintRotate attribute at all (they only ever drive
        # translation). Check the attribute exists before querying it.
        if not cmds.attributeQuery(out_attr, node=constraint, exists=True):
            continue

        out_plug = '{}.{}'.format(constraint, out_attr)
        in_plug = '{}.{}'.format(joint, in_attr)

        try:
            if cmds.isConnected(out_plug, in_plug):
                return True
        except Exception:
            pass

        # Fall back to per-channel connections. Standard cmds.parentConstraint
        # output normally connects at the compound level in one link, but a
        # hand-built or axis-skipping setup can connect X/Y/Z individually
        # instead -- isConnected on the compound plugs would miss that.
        for axis in ('X', 'Y', 'Z'):
            try:
                if cmds.isConnected('{}{}'.format(out_plug, axis), '{}{}'.format(in_plug, axis)):
                    return True
            except Exception:
                continue

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

    # Primary axis: the axis with the largest local translation on chain[1]
    primary_axis = 'X'
    try:
        tx = abs(cmds.getAttr('{}.translateX'.format(chain[1])))
        ty = abs(cmds.getAttr('{}.translateY'.format(chain[1])))
        tz = abs(cmds.getAttr('{}.translateZ'.format(chain[1])))
        primary_axis = ['X', 'Y', 'Z'][[tx, ty, tz].index(max(tx, ty, tz))]
    except Exception:
        pass

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
            'pole_vector_world_position': pv_pos,
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

    # --- Pass 2/3: ikHandle-driven modules (SplineIK, IKLimb), authoritative ---
    #
    # Previously these used the same all_chains candidates as everything
    # else, which are generated by walking the joint hierarchy and splitting
    # at every branch point. That heuristic silently breaks whenever an
    # ikHandle's real start joint IS a branch point -- e.g. a spine joint
    # that is simultaneously "the last joint before the leg branches off"
    # and "the first joint of the spine's own Spline IK solve". The
    # branch-walker never offers that joint as chain[0] to anything (it only
    # ever starts fresh candidates at a branch point's CHILDREN), so
    # find_ik_handle_for_start_joint(chain[0]) can never match, and the
    # module silently falls through to FKChain no matter how correctly the
    # ikHandle itself is set up in Maya.
    #
    # Fixed by reading ikHandle-driven chains directly from Maya instead of
    # inferring them from hierarchy branching: iterate every real ikHandle,
    # query its actual start joint / solved joint list / end joint, and
    # build the chain from that data. This is correct regardless of what
    # else happens to branch off at the start or end joint.
    for ik_handle in cmds.ls(type='ikHandle') or []:
        start_conns = cmds.listConnections(
            '{}.startJoint'.format(ik_handle), source=True, destination=False
        ) or []
        if not start_conns:
            continue
        start_joint = start_conns[0]

        try:
            solved_joints = cmds.ikHandle(ik_handle, query=True, jointList=True) or []
        except Exception:
            solved_joints = []
        if not solved_joints:
            continue

        # jointList returns start..penultimate joint, excluding the actual
        # end/effector joint (a Maya quirk). The end joint is NOT reliably
        # the effector's DAG parent -- confirmed against real scene data
        # where an ikHandle's own effector was parented under the SECOND
        # joint of a 3-joint chain, not the third/true end joint, which
        # would have silently truncated the chain by one joint. Instead,
        # take the single unbroken joint child after jointList's last
        # entry -- correct for the overwhelmingly common case of a
        # straight (non-branching) IK chain.
        end_joint = None
        children = cmds.listRelatives(solved_joints[-1], children=True, type='joint') or []
        if len(children) == 1:
            end_joint = children[0]
        else:
            # Ambiguous (0 or 2+ children right at the last solved joint) --
            # fall back to the effector-connection heuristic as a last
            # resort, otherwise skip and let the Pass 3.5 safety net below
            # (proven correct for non-branch-point cases) handle it.
            end_joint = _ik_handle_end_joint(ik_handle)
        if not end_joint:
            continue

        full_chain = solved_joints + [end_joint]
        if not _is_unclaimed(full_chain):
            continue

        solver = _ik_solver_type(ik_handle)
        if 'spline' in solver.lower():
            result = detect_spline_ik(full_chain)
            if result:
                _claim(full_chain)
                modules.append(result)
        else:
            result, _leftover = detect_ik_limb(full_chain)
            if result:
                _claim(full_chain)
                modules.append(result)

        # Whatever joints continue unbroken past this ikHandle's real end
        # joint (e.g. an FK toe chain hanging off the ankle) are not part
        # of this module -- feed them back into detection as their own
        # candidate chain(s) instead of silently dropping them.
        if result:
            trailing_children = cmds.listRelatives(end_joint, children=True, type='joint') or []
            for child in trailing_children:
                if child in full_chain:
                    continue
                for tail_chain in _collect_chains_from_root(child):
                    all_chains.append(tail_chain)

    # --- Pass 3.5: SplineIK / IKLimb fallback for anything the ikHandle
    #     pass above didn't cover (e.g. ikHandle query failed for some
    #     reason) -- same heuristic as before, kept as a safety net. ---
    for chain in all_chains:
        if not _is_unclaimed(chain):
            continue
        result = detect_spline_ik(chain)
        if result:
            _claim(chain)
            modules.append(result)

    for chain in all_chains:
        if not _is_unclaimed(chain):
            continue
        result, leftover_tail = detect_ik_limb(chain)
        if result:
            used_chain = chain[:len(chain) - len(leftover_tail)] if leftover_tail else chain
            _claim(used_chain)
            modules.append(result)
            if leftover_tail:
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
# Manifest building
# ---------------------------------------------------------------------------

def _detect_connections(modules_config):
    """
    Walk the Maya joint hierarchy to detect which module's root joint sits
    inside another module's chain.  Returns {child_module_name: parent_module_name}.
    """
    joint_to_module = {}
    for mod in modules_config:
        for bone in mod.get("chain", []):
            joint_to_module[bone] = mod["module_name"]

    connections = {}
    for mod in modules_config:
        chain = mod.get("chain", [])
        if not chain:
            continue
        parents = cmds.listRelatives(chain[0], parent=True, type="joint") or []
        visited = set()
        while parents:
            parent = parents[0]
            if parent in visited:
                break
            visited.add(parent)
            if parent in joint_to_module:
                parent_module = joint_to_module[parent]
                if parent_module != mod["module_name"]:
                    connections[mod["module_name"]] = parent_module
                    break
            parents = cmds.listRelatives(parent, parent=True, type="joint") or []

    return connections


def build_manifest(rig_name, modules_config):
    """
    Build the manifest dict from modules_config, augmented with
    scene-detected inter-module connections.

    modules_config items may come from run_detection_pipeline() (which already
    embeds params) or from a hand-authored list.
    """
    connections = _detect_connections(modules_config)
    modules = []

    for mod in modules_config:
        module_def = {
            "module_type": mod["module_type"],
            "module_name": mod["module_name"],
            "chain": list(mod.get("chain", [])),
            "chain_items": list(mod.get("chain_items", [])),
        }

        if mod.get("params"):
            module_def["params"] = mod["params"]

        parent_module = connections.get(mod["module_name"])
        if parent_module:
            module_def["connections"] = {
                "parent_module": parent_module,
                "parent_attach_point": "root",
            }

        # Preserve legacy "recipe" field for IKLimb so the UE5 IKModule can
        # read pole_vector_world_position without touching the params dict.
        if mod.get("recipe"):
            module_def["recipe"] = mod["recipe"]
        elif mod["module_type"] == "IKLimb":
            pv = (mod.get("params") or {}).get("pole_vector_world_position")
            if pv:
                module_def["recipe"] = {"pole_vector_world_position": pv}

        modules.append(module_def)

    return {"rig_name": rig_name, "modules": modules}


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
# ---------------------------------------------------------------------------
EXPORT_DIR = r"C:\Users\jeanf\Desktop\DataAsset test\Export"
FILENAME = "MultiModule"
RIG_NAME = "MultiModule"

RIG_MODULES = auto_discover_modules()

export(EXPORT_DIR, FILENAME, RIG_NAME, RIG_MODULES)
register_auto_update(RIG_NAME, RIG_MODULES)