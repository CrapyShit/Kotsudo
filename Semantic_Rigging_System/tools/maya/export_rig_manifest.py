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

import importlib
import json
import os
import re
import sys

import maya.cmds as cmds
import maya.mel as mel

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ROOT_JOINT_NAME = "root"
MANIFEST_ATTR = "rig_manifest_json"
# 6: world mapping (X, Z, Y) fixed, joint-local offsets, per-chain axes,
#    parent_controllers / parent_space_bone, schema + units blocks.
MANIFEST_SCHEMA_VERSION = 6

# Bypass flags for constraint detection (useful when a bone has constraints
# for specific rigging reasons but shouldn't be analyzed for module detection)
ATTR_SKIP_CONSTRAINT_DETECTION = "rigTag_skipConstraintDetection"

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
        # Query only joints to avoid matching meshes/transforms with same short name.
        paths = cmds.ls(node, long=True, type="joint") or []
        if paths:
            return paths[0]
        # Non-joint (e.g. a transform controller): resolve only when unambiguous.
        paths = cmds.ls(node, long=True) or []
        return paths[0] if len(paths) == 1 else node
    except Exception:
        return node


def _should_skip_constraint_detection(joint):
    """Check if this joint should skip constraint analysis.
    
    Useful for bones with point/orient/parent constraints for specific
    rigging reasons (e.g., secondary joint control) that shouldn't trigger
    IKFKSwitch or other structural detection.
    
    To skip a joint, add this attribute in Maya:
        cmds.setAttr("joint_name.rigTag_skipConstraintDetection", True)
    """
    if not joint or not cmds.objExists(joint):
        return False
    try:
        if cmds.attributeQuery(ATTR_SKIP_CONSTRAINT_DETECTION, node=joint, exists=True):
            return bool(cmds.getAttr(f"{joint}.{ATTR_SKIP_CONSTRAINT_DETECTION}"))
    except Exception:
        pass
    return False


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
    """Return the animator-facing pole-vector target for *ik_handle*.

    Maya wires a poleVectorConstraint *into* ``ikHandle.poleVector``. The old
    implementation searched only downstream from the handle, which misses the
    normal Maya connection direction and produced null PV data in the manifest.

    Query the explicit poleVector plugs first, then both connection directions
    as a compatibility fallback. ``cmds.poleVectorConstraint(..., targetList)``
    is preferred over manually reading target[] plugs because it returns the
    actual constrained target transform even when utility nodes are present.
    """
    if not ik_handle or not cmds.objExists(ik_handle):
        return None

    constraints = []
    seen = set()

    def _append_constraints(nodes):
        for node in nodes or []:
            try:
                if cmds.nodeType(node) != 'poleVectorConstraint':
                    continue
            except Exception:
                continue
            if node not in seen:
                seen.add(node)
                constraints.append(node)

    for plug_name in ('poleVector', 'poleVectorX', 'poleVectorY', 'poleVectorZ'):
        plug = '{}.{}'.format(ik_handle, plug_name)
        if not cmds.objExists(plug):
            continue
        try:
            _append_constraints(cmds.listConnections(
                plug, source=True, destination=False, type='poleVectorConstraint'
            ))
        except Exception:
            pass

    for source, destination in ((True, False), (False, True)):
        try:
            _append_constraints(cmds.listConnections(
                ik_handle,
                source=source,
                destination=destination,
                type='poleVectorConstraint',
            ))
        except Exception:
            pass

    for constraint in constraints:
        targets = []
        try:
            targets = cmds.poleVectorConstraint(
                constraint, query=True, targetList=True
            ) or []
        except Exception:
            pass

        if not targets:
            try:
                targets = _constraint_targets(constraint)
            except Exception:
                targets = []

        for target in targets:
            controller = _nearest_controller_transform(target)
            if controller:
                return controller
            if cmds.objExists(target):
                return _full_dag_path(target)

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


def _maya_linear_to_centimeters_scale():
    """Return the current Maya linear-unit scale relative to Unreal centimeters."""
    try:
        unit = str(cmds.currentUnit(query=True, linear=True) or 'cm').lower()
    except Exception:
        unit = 'cm'
    return {
        'mm': 0.1,
        'millimeter': 0.1,
        'millimeters': 0.1,
        'cm': 1.0,
        'centimeter': 1.0,
        'centimeters': 1.0,
        'm': 100.0,
        'meter': 100.0,
        'meters': 100.0,
        'in': 2.54,
        'inch': 2.54,
        'inches': 2.54,
        'ft': 30.48,
        'foot': 30.48,
        'feet': 30.48,
        'yd': 91.44,
        'yard': 91.44,
        'yards': 91.44,
    }.get(unit, 1.0)


def _maya_up_axis():
    try:
        return str(cmds.upAxis(query=True, axis=True) or 'y').lower()
    except Exception:
        return 'y'


def _maya_vector_to_unreal(values, apply_unit_scale=False):
    """Convert Maya numeric metadata into Unreal's coordinate convention.

    Raw FBX metadata is not axis-converted by Unreal's importer even though
    skeleton transforms are, so this mirrors what the importer does: convert
    the scene to Z-up (a +90 degree turn about X for Y-up files), then flip Y
    to go from right- to left-handed. For Maya's usual Y-up system that is
    ``(X, Y, Z) -> (X, Z, Y)``; Z-up scenes use ``(X, Y, Z) -> (X, -Y, Z)``.

    Both mappings are reflections (determinant -1), as a right-to-left-handed
    conversion must be. An earlier (X, -Z, Y) mapping was a pure rotation and
    mirrored every front/back offset -- invisible on a skeleton lying in the
    X/Z plane, but it put pole vectors in front of the character instead of
    behind. Points additionally convert Maya units to Unreal centimeters.
    """
    if values is None:
        return None
    x, y, z = [float(values[0]), float(values[1]), float(values[2])]
    if _maya_up_axis() == 'z':
        converted = [x, -y, z]
    else:
        converted = [x, z, y]
    if apply_unit_scale:
        scale = _maya_linear_to_centimeters_scale()
        converted = [component * scale for component in converted]
    return _round_vector(converted)


def _coordinate_system_manifest():
    try:
        linear_unit = str(cmds.currentUnit(query=True, linear=True) or 'cm')
    except Exception:
        linear_unit = 'cm'
    up_axis = _maya_up_axis()
    return {
        'source_application': 'Maya',
        'source_up_axis': up_axis.upper(),
        'source_handedness': 'RightHanded',
        'source_linear_unit': linear_unit,
        'target_application': 'UnrealEngine',
        'target_up_axis': 'Z',
        'target_handedness': 'LeftHanded',
        'target_linear_unit': 'cm',
        'vector_mapping': 'X,-Y,Z' if up_axis == 'z' else 'X,Z,Y',
        # Joint-local vectors (offset_local, reference_local, axes *_unreal):
        # the importer keeps joint frames and mirrors them to left-handed.
        'joint_local_mapping': 'X,-Y,Z',
    }


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
    """A Maya world-space point on *node*'s local axes (Maya UI units).

    See _joint_local_unreal for why the matrix translation is not used
    (internal cm vs UI units).
    """
    if not world_position or not node or not cmds.objExists(node):
        return None
    try:
        matrix = cmds.xform(node, query=True, worldSpace=True, matrix=True)
        origin = cmds.xform(node, query=True, worldSpace=True, translation=True)
        delta = [float(world_position[i]) - float(origin[i]) for i in range(3)]
        local = []
        for row in range(3):
            axis = [matrix[row * 4 + i] for i in range(3)]
            length = sum(c * c for c in axis) ** 0.5 or 1.0
            local.append(sum(delta[i] * axis[i] for i in range(3)) / length)
        return _round_vector(local)
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
        # NURBS surfaces (sphere/cube style controls) count as controllers
        # too; ignoring them made an IK handle's controller resolve to an
        # unrelated ancestor (the pole vector) instead.
        return any(
            cmds.nodeType(shape) in ('nurbsCurve', 'bezierCurve', 'nurbsSurface')
            for shape in shapes
        )
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
            # Any DAG transform counts, joints included: many rigs (this one
            # too) use joints carrying a curve shape as animator controls.
            if cmds.objectType(current, isAType='transform') and _has_controller_shape(current):
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

    pole = _get_pole_vector_node(ik_handle)
    pole = _full_dag_path(pole) if pole else None
    for constraint in _constraints_connected_to(
        ik_handle, ('parentConstraint', 'pointConstraint', 'orientConstraint')
    ):
        # poleVectorConstraint IS-A pointConstraint in Maya's type tree: its
        # target is the pole vector, never the effector.
        if cmds.nodeType(constraint) == 'poleVectorConstraint':
            continue
        for target in _constraint_targets(constraint):
            if pole and _full_dag_path(target) == pole:
                continue
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


# ---------------------------------------------------------------------------
# Controller shapes and custom attributes
# ---------------------------------------------------------------------------
#
# Shapes are exported as polylines in WORLD orientation, centred on the
# controller origin, already mapped to Unreal axes and centimetres. World
# orientation (not the controller's own object space) is used because the UE
# control's frame is the bone frame, which the Maya controller's frame need
# not match; Unreal cancels its own control rotation to reproduce the shape.
# Identical shapes are stored once in the top-level "control_shapes" table.

_SHAPE_REGISTRY = {}
_SHAPE_RAW = {}          # shape_id -> strands in raw Maya axes (cm), for the shapes FBX
_SHAPE_SAMPLES_PER_SPAN = 6
_SHAPE_MAX_POINTS = 240
SHAPE_MESH_PREFIX = 'RB_'          # node/asset name: RB_<shape_id>
SHAPE_TUBE_RADIUS_RATIO = 0.012    # tube radius as a fraction of the shape's diagonal
SHAPE_TUBE_MIN_RADIUS = 0.15       # cm


def _reset_shape_registry():
    _SHAPE_REGISTRY.clear()
    _SHAPE_RAW.clear()


def _curve_strands(shape_path, origin_world):
    """Sample one nurbsCurve into a strand of Unreal-space points.

    Returns {'points': [[x, y, z], ...], 'closed': bool}. Degree-1 curves keep
    their CVs (the corners); smoother curves are sampled per span.
    """
    import maya.api.OpenMaya as om2

    selection = om2.MSelectionList()
    selection.add(shape_path)
    fn = om2.MFnNurbsCurve(selection.getDagPath(0))
    closed = fn.form != om2.MFnNurbsCurve.kOpen

    world_points = []
    if fn.degree == 1:
        for point in fn.cvPositions(om2.MSpace.kWorld):
            world_points.append((point.x, point.y, point.z))
    else:
        start, end = fn.knotDomain
        count = max(fn.numSpans * _SHAPE_SAMPLES_PER_SPAN, 8) + 1
        for index in range(count):
            point = fn.getPointAtParam(start + (end - start) * index / float(count - 1), om2.MSpace.kWorld)
            world_points.append((point.x, point.y, point.z))

    cleaned = []
    for point in world_points:
        if cleaned and max(abs(point[i] - cleaned[-1][i]) for i in range(3)) < 1e-6:
            continue
        cleaned.append(point)
    if len(cleaned) > _SHAPE_MAX_POINTS:
        step = len(cleaned) / float(_SHAPE_MAX_POINTS)
        cleaned = [cleaned[int(i * step)] for i in range(_SHAPE_MAX_POINTS)]

    # OpenMaya always works in internal units (centimetres), whereas cmds.xform
    # -- the source of ``origin_world`` -- uses the scene's UI unit. Bring the
    # origin to centimetres so both sides of the subtraction agree; no further
    # unit scaling is applied to the result.
    to_cm = _maya_linear_to_centimeters_scale()
    origin_cm = [c * to_cm for c in origin_world]
    relative = [[point[i] - origin_cm[i] for i in range(3)] for point in cleaned]
    points = [_maya_vector_to_unreal(vector, apply_unit_scale=False) for vector in relative]
    return {
        'points': [[round(c, 3) for c in p] for p in points],
        'closed': bool(closed),
        # Raw Maya axes: the shapes FBX is converted by Unreal's importer with
        # the same rules as the skeleton, so no axis mapping of our own is used.
        'raw': [[round(c, 4) for c in vector] for vector in relative],
    }


def _classify_shape_kind(node):
    """Coarse geometric kind of a controller, from its OBJECT-space curve data.

    Used by Unreal as a fallback when a custom mesh cannot be built: it maps the
    kind to a built-in library shape and scales it to the measured extents.
    Returns {'kind', 'extents_object' (full size on object x/y/z, cm),
    'planar_axis'} plus the object axes in Unreal world directions, so the
    fallback can be oriented.
    """
    import maya.api.OpenMaya as om2

    shapes = [
        s for s in (cmds.listRelatives(node, shapes=True, fullPath=True) or [])
        if cmds.nodeType(s) == 'nurbsCurve'
    ]
    if not shapes:
        return None

    object_points = []
    strand_infos = []
    for shape in shapes:
        selection = om2.MSelectionList()
        selection.add(shape)
        fn = om2.MFnNurbsCurve(selection.getDagPath(0))
        cvs = [(p.x, p.y, p.z) for p in fn.cvPositions(om2.MSpace.kObject)]
        object_points.extend(cvs)
        strand_infos.append({'degree': fn.degree, 'cvs': len(cvs), 'closed': fn.form != om2.MFnNurbsCurve.kOpen})
    if not object_points:
        return None

    # OpenMaya values are already centimetres (internal units): no scaling.
    mins = [min(p[i] for p in object_points) for i in range(3)]
    maxs = [max(p[i] for p in object_points) for i in range(3)]
    extents = [(maxs[i] - mins[i]) for i in range(3)]
    biggest = max(extents) or 1e-6
    planar_axis = None
    for index, axis in enumerate('xyz'):
        if extents[index] < biggest * 0.1:
            planar_axis = axis
            break

    kind = 'other'
    if planar_axis and all(info['closed'] or info['cvs'] >= 5 for info in strand_infos) and len(strand_infos) == 1:
        plane = [i for i, a in enumerate('xyz') if a != planar_axis]
        center = [(mins[i] + maxs[i]) * 0.5 for i in plane]
        radii = [
            ((p[plane[0]] - center[0]) ** 2 + (p[plane[1]] - center[1]) ** 2) ** 0.5
            for p in object_points
        ]
        mean = sum(radii) / len(radii)
        spread = (sum((r - mean) ** 2 for r in radii) / len(radii)) ** 0.5
        info = strand_infos[0]
        if info['degree'] >= 2 and mean > 1e-9 and spread / mean < 0.12:
            kind = 'circle'
        elif info['degree'] == 1 and info['cvs'] in (4, 5):
            kind = 'rectangle'
    elif not planar_axis and all(info['degree'] == 1 for info in strand_infos):
        kind = 'box'
    elif not planar_axis and len(strand_infos) >= 3 and all(info['degree'] >= 2 for info in strand_infos):
        kind = 'sphere'

    world_matrix = om2.MMatrix(cmds.xform(node, query=True, worldSpace=True, matrix=True))
    axes = []
    for row in range(3):
        vector = [world_matrix[row * 4 + 0], world_matrix[row * 4 + 1], world_matrix[row * 4 + 2]]
        length = sum(c * c for c in vector) ** 0.5 or 1.0
        axes.append(_maya_vector_to_unreal([c / length for c in vector], apply_unit_scale=False))
    return {
        'kind': kind,
        'planar_axis': planar_axis,
        'extents_object': [round(e, 3) for e in extents],
        'object_axes_unreal': axes,
    }


def _register_controller_shape(node, origin_world):
    """Extract a controller's curve shape and return its shape id, or None."""
    import hashlib

    shapes = [
        s for s in (cmds.listRelatives(node, shapes=True, fullPath=True) or [])
        if cmds.nodeType(s) == 'nurbsCurve'
        and not cmds.getAttr('{}.intermediateObject'.format(s))
    ]
    if not shapes:
        return None

    full = [_curve_strands(shape, origin_world) for shape in shapes]
    full = [strand for strand in full if len(strand['points']) >= 2]
    if not full:
        return None
    strands = [{'points': s['points'], 'closed': s['closed']} for s in full]

    payload = json.dumps(strands, separators=(',', ':'), sort_keys=True)
    shape_id = hashlib.md5(payload.encode('utf-8')).hexdigest()[:12]
    _SHAPE_RAW.setdefault(shape_id, [{'raw': s['raw'], 'closed': s['closed']} for s in full])
    if shape_id not in _SHAPE_REGISTRY:
        try:
            descriptor = _classify_shape_kind(node)
        except Exception:
            descriptor = None
        _SHAPE_REGISTRY[shape_id] = {'strands': strands, 'descriptor': descriptor}
    return shape_id


_ATTRIBUTE_TYPES = {
    'double': 'float', 'float': 'float', 'doubleLinear': 'float', 'doubleAngle': 'float',
    'long': 'int', 'short': 'int', 'byte': 'int', 'enum': 'enum', 'bool': 'bool',
}
_ATTRIBUTE_SKIP_PREFIXES = ('rigTag_',)
_ATTRIBUTE_SKIP_NAMES = {'rig_manifest_json', 'filmboxTypeID', 'lockInfluenceWeights', 'gpuBlockPolicy'}


def _controller_attributes(node):
    """Return the user-defined, animator-facing attributes of a controller.

    These are the "settings" a rig exposes on a control (IK/FK switch, blend
    amounts, toggles). Each entry has type, current value, range and, for
    enums, the labels in index order.
    """
    result = []
    for attr in cmds.listAttr(node, userDefined=True) or []:
        if '.' in attr or attr.startswith(_ATTRIBUTE_SKIP_PREFIXES) or attr in _ATTRIBUTE_SKIP_NAMES:
            continue
        plug = '{}.{}'.format(node, attr)
        try:
            maya_type = cmds.getAttr(plug, type=True)
            kind = _ATTRIBUTE_TYPES.get(maya_type)
            if kind is None:
                continue
            keyable = bool(cmds.getAttr(plug, keyable=True))
            channel_box = bool(cmds.getAttr(plug, channelBox=True))
            if not (keyable or channel_box):
                continue
            entry = {
                'name': attr,
                'type': kind,
                'value': float(cmds.getAttr(plug)),
                'keyable': keyable,
            }
            default = cmds.addAttr(plug, query=True, defaultValue=True)
            entry['default'] = float(default) if default is not None else entry['value']
            if cmds.attributeQuery(attr, node=node, minExists=True):
                entry['min'] = float(cmds.attributeQuery(attr, node=node, minimum=True)[0])
            if cmds.attributeQuery(attr, node=node, maxExists=True):
                entry['max'] = float(cmds.attributeQuery(attr, node=node, maximum=True)[0])
            if kind == 'enum':
                labels = cmds.attributeQuery(attr, node=node, listEnum=True) or []
                entry['enum_names'] = labels[0].split(':') if labels else []
                entry.setdefault('min', 0.0)
                entry.setdefault('max', float(max(len(entry['enum_names']) - 1, 0)))
            elif kind == 'bool':
                entry.setdefault('min', 0.0)
                entry.setdefault('max', 1.0)
            result.append(entry)
        except Exception:
            continue
    return result


def _safe_call(function, *args):
    try:
        return function(*args)
    except Exception:
        return None


def _world_axes_unreal(node):
    """A node's world orientation as Unreal axes [X, Y, Z] (unit vectors).

    Converted the way the FBX importer converts a joint: the rotation is
    conjugated by the axis mapping P, so UE X = P(Maya X), UE Y = P(Maya Z),
    UE Z = P(Maya Y) for Y-up scenes (P swaps two axes, so the Maya Y/Z axes
    swap roles too). The result is a proper right-handed basis, directly
    usable as a Control Rig rotation.
    """
    matrix = cmds.xform(node, query=True, worldSpace=True, matrix=True)
    axes = []
    for row in range(3):
        vector = [matrix[row * 4 + i] for i in range(3)]
        length = sum(c * c for c in vector) ** 0.5 or 1.0
        axes.append(_maya_vector_to_unreal([c / length for c in vector], apply_unit_scale=False))
    if _maya_up_axis() == 'z':
        return [axes[0], axes[1], axes[2]]
    return [axes[0], axes[2], axes[1]]


def _world_size_unreal(node):
    """World bounding-box size of a controller in Unreal axes / cm, or None."""
    if not _has_controller_shape(node):
        return None
    try:
        box = cmds.exactWorldBoundingBox(node)
    except Exception:
        return None
    size = _maya_vector_to_unreal([box[i + 3] - box[i] for i in range(3)], apply_unit_scale=True)
    return [abs(c) for c in size]


def _parent_controller(node):
    """Nearest animator controller above ``node`` (short name), or None."""
    parents = cmds.listRelatives(node, parent=True, fullPath=True) or []
    if not parents:
        return None
    controller = _nearest_controller_transform(parents[0])
    return _short_node_name(controller) if controller else None


_DRIVEN_ATTRS = (
    'translate', 'rotate', 'scale', 'offsetParentMatrix',
    'translateX', 'translateY', 'translateZ',
    'rotateX', 'rotateY', 'rotateZ',
)


def _space_drivers(node):
    """What replaces a transform's parent space, or None if nothing does.

    Only a CONSTRAINT (or a matrix wired into offsetParentMatrix) moves a
    group into another object's space. Everything else feeding its channels
    -- driven keys, multiply/plus nodes fed by custom attributes such as a
    settings control's "Petal_Rotation", time-keyed curves -- is a LOCAL
    offset: the group still lives in its Maya parent's space.

    Returns None (static or locally offset), else the list of transforms the
    space comes from (constraint targets; empty when unknown, e.g. a matrix
    network).
    """
    drivers = None
    for attribute in _DRIVEN_ATTRS:
        if not cmds.attributeQuery(attribute.split('.')[0], node=node, exists=True):
            continue
        sources = cmds.listConnections(
            '{}.{}'.format(node, attribute), source=True, destination=False,
            skipConversionNodes=True,
        ) or []
        for source in sources:
            if cmds.objectType(source, isAType='constraint'):
                drivers = drivers if drivers is not None else []
                for target in _constraint_targets(source):
                    if (target not in drivers and target != _short_node_name(node)
                            and cmds.objectType(target, isAType='transform')):
                        drivers.append(target)
            elif attribute == 'offsetParentMatrix':
                drivers = drivers if drivers is not None else []
    return drivers


def _constraint_targets(constraint):
    """The transforms a constraint follows -- what feeds each target's
    parent matrix. Weight inputs (an IK/FK switch wired to target weights)
    are also connected under .target and must not count as targets."""
    targets = []
    for index in cmds.getAttr('{}.target'.format(constraint), multiIndices=True) or []:
        for plug in ('targetParentMatrix', 'targetTranslate', 'targetRotate'):
            sources = cmds.listConnections(
                '{}.target[{}].{}'.format(constraint, index, plug), source=True, destination=False
            ) or []
            if sources:
                if sources[0] not in targets:
                    targets.append(sources[0])
                break
    return targets


def _weight_source(constraint, index):
    """What drives one constraint target's weight: {'value': w}, or
    {'control', 'attr', 'invert'} for a control attribute used directly or
    through a reverse node (the usual IK/FK blend). None when unsupported."""
    plug = '{}.target[{}].targetWeight'.format(constraint, index)
    sources = cmds.listConnections(plug, source=True, destination=False, plugs=True,
                                   skipConversionNodes=True) or []
    if not sources:
        return {'value': float(cmds.getAttr(plug))}
    node, attr = sources[0].split('.', 1)
    if cmds.nodeType(node) == 'reverse':
        axis = attr[-1].upper() if attr[-1].upper() in 'XYZ' else 'X'
        inputs = cmds.listConnections('{}.input{}'.format(node, axis), source=True, destination=False,
                                      plugs=True, skipConversionNodes=True) or []
        if inputs:
            source_node, source_attr = inputs[0].split('.', 1)
            if cmds.objectType(source_node, isAType='transform'):
                return {'control': _short_node_name(source_node), 'attr': source_attr, 'invert': True}
        return None
    if cmds.objectType(node, isAType='transform'):
        return {'control': _short_node_name(node), 'attr': attr, 'invert': False}
    return None


def _parent_space_blend(node):
    """The constraint that replaces a controller's parent space, as a blend.

    Walks up like _parent_space; at the first constraint-driven group (before
    any controller) returns {'kind': 'parent', 'targets': [{'controller',
    'weight'}]} -- e.g. a foot FK group parent-constrained to the IK and FK
    foot controls, weighted by the IK/FK switch and its reverse. None when
    the space is not a fully describable parentConstraint.
    """
    current = (cmds.listRelatives(node, parent=True, fullPath=True) or [None])[0]
    while current:
        if cmds.objectType(current, isAType='transform') and _has_controller_shape(current):
            return None
        constraints = sorted({
            source for attribute in _DRIVEN_ATTRS
            if cmds.attributeQuery(attribute, node=current, exists=True)
            for source in (cmds.listConnections('{}.{}'.format(current, attribute), source=True,
                                                destination=False, skipConversionNodes=True) or [])
            if cmds.objectType(source, isAType='constraint')
        })
        if constraints:
            constraint = constraints[0]
            if len(constraints) != 1 or cmds.nodeType(constraint) != 'parentConstraint':
                return None
            targets = []
            for index in cmds.getAttr('{}.target'.format(constraint), multiIndices=True) or []:
                sources = cmds.listConnections('{}.target[{}].targetParentMatrix'.format(constraint, index),
                                               source=True, destination=False) or []
                weight = _weight_source(constraint, index)
                if not sources or weight is None:
                    return None
                controller = _nearest_controller_transform(sources[0]) or sources[0]
                targets.append({'controller': _short_node_name(controller), 'weight': weight})
            return {'kind': 'parent', 'targets': targets} if targets else None
        current = (cmds.listRelatives(current, parent=True, fullPath=True) or [None])[0]
    return None


def _is_driven_space(node):
    """True when a constraint or matrix input replaces the node's space."""
    return _space_drivers(node) is not None


def _parent_space(node):
    """Where a controller really hangs in Maya.

    Returns (parent_controllers, driven_bone):

    * parent_controllers -- the controller ancestors reachable through STATIC
      groups, nearest first. Unreal parents the control to the first of them
      it has built (exactly Maya's hierarchy).
    * driven_bone -- set when a driven group sits between the controller and
      its first controller ancestor (e.g. a foot FK group parent-constrained
      between the IK and FK controls, weighted by the IK/FK switch). The Maya
      parent is then not the real driver; the group effectively follows a
      skeleton bone: the exported joint nearest to the constraint TARGETS
      (e.g. the ankle, where both the IK control and the last FK control
      sit), not to the group itself -- the group usually sits on the very
      bone the controller drives. Unreal follows that bone's final transform.

    Groups offset by attribute networks (driven keys, math nodes) are not
    spaces and are walked through like static groups.
    """
    controllers = []
    current = (cmds.listRelatives(node, parent=True, fullPath=True) or [None])[0]
    while current:
        if cmds.objectType(current, isAType='transform') and _has_controller_shape(current):
            controllers.append(_short_node_name(current))
        else:
            drivers = _space_drivers(current)
            if drivers is not None:
                if not controllers:
                    points = [_target_point(target) for target in drivers] or [
                        cmds.xform(current, query=True, worldSpace=True, rotatePivot=True)]
                    centre = [sum(p[i] for p in points) / len(points) for i in range(3)]
                    return controllers, _nearest_exported_joint(centre)
                break
        current = (cmds.listRelatives(current, parent=True, fullPath=True) or [None])[0]
    return controllers, None


def _exported_joints():
    root = cmds.ls(ROOT_JOINT_NAME, long=True, type='joint') or []
    if not root:
        return []
    return root + (cmds.listRelatives(root[0], allDescendents=True, type='joint', fullPath=True) or [])


def _is_module_joint(joint):
    """True for joints a tagged module owns (rebuilt in Unreal)."""
    try:
        return bool(cmds.attributeQuery('rigTag_moduleName', node=joint, exists=True)
                    and cmds.getAttr('{}.rigTag_moduleName'.format(joint)))
    except Exception:
        return False


def _nearest_exported_joint(world_point):
    """Exported joint nearest to a point; module joints win ties (within 0.1
    unit) over helper chains sitting at the same place -- a blended limb's
    FK/IK duplicate joints are exported but not rebuilt, so a space following
    one of them would never move in Unreal."""
    ranked = []
    for joint in _exported_joints():
        position = _world_translation(joint)
        distance = sum((position[i] - world_point[i]) ** 2 for i in range(3)) ** 0.5
        ranked.append((distance, joint))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0])
    nearest = ranked[0][0]
    for distance, joint in ranked:
        if distance > nearest + 0.1:
            break
        if _is_module_joint(joint):
            return _short_node_name(joint)
    return _short_node_name(ranked[0][1])


def _target_point(node):
    """Where a constraint target sits: a joint's position, else its pivot."""
    if cmds.objectType(node, isAType='joint'):
        return _world_translation(node)
    return cmds.xform(node, query=True, worldSpace=True, rotatePivot=True)


def _joint_local_unreal(world_point, joint):
    """A world point in ``joint``'s local frame, in Unreal's joint convention.

    The FBX importer keeps joint-local frames and only mirrors them to go
    left-handed, so a local vector (x, y, z) in Maya is (x, -y, z) on the
    imported bone (e.g. a Maya spine running along +Y runs along -Y in UE).
    No world axis conversion is involved -- this is the joint-relative
    storage the schema asks for. Centimetres.

    Units: ``xform -matrix`` returns its translation in Maya's INTERNAL unit
    (always cm) while ``xform -translation/-rotatePivot`` answer in the UI
    unit (m, dm, ...). Mixing them put every point hundreds of units off in
    metre scenes. So only the matrix's axis rows are used here (unit-free
    once normalised); the joint position comes from the same query family as
    ``world_point``, and the result is world length expressed on the joint's
    axes -- what the imported bone measures, whatever scale its parents carry.
    """
    matrix = cmds.xform(joint, query=True, worldSpace=True, matrix=True)
    origin = _world_translation(joint)
    delta = [float(world_point[i]) - float(origin[i]) for i in range(3)]
    local = []
    for row in range(3):
        axis = [matrix[row * 4 + i] for i in range(3)]
        length = sum(c * c for c in axis) ** 0.5 or 1.0
        local.append(sum(delta[i] * axis[i] for i in range(3)) / length)
    scale = _maya_linear_to_centimeters_scale()
    return _round_vector([local[0] * scale, -local[1] * scale, local[2] * scale])


def _local_offset_fields(world_point, anchor, neighbour):
    """offset_local / reference_local for a point anchored on a joint."""
    fields = {'offset_local': _joint_local_unreal(world_point, anchor)}
    if neighbour and cmds.objExists(neighbour):
        fields['reference_local'] = {
            'bone': _short_node_name(neighbour),
            'vector': _joint_local_unreal(_world_translation(neighbour), anchor),
        }
    return fields


def _controller_origin_world(node):
    """Return (world_point, source) for where an animator perceives a control.

    The transform's rotate pivot is what the animator rotates around, and is
    correct for controls whose pivot was moved onto the joint (or whose curve
    CVs were frozen around a pivot), and for custom pivots far from the
    curve. Only a frozen control whose pivot was left at the world origin
    while the curve sits elsewhere uses the bounding-box centre instead.
    """
    pivot = cmds.xform(node, query=True, worldSpace=True, rotatePivot=True)
    # Only nodes that actually carry geometry have a meaningful bounding box.
    # A joint (or empty transform) used as a controller has none: its box
    # collapses to the world origin, which would drag the control to the
    # ground, so its pivot is the origin.
    if not _has_controller_shape(node):
        return pivot, 'rotate_pivot'
    try:
        box = cmds.exactWorldBoundingBox(node)  # xmin, ymin, zmin, xmax, ymax, zmax
    except Exception:
        return pivot, 'rotate_pivot'

    center = [(box[i] + box[i + 3]) * 0.5 for i in range(3)]
    half = [(box[i + 3] - box[i]) * 0.5 for i in range(3)]
    margin = max(max(half) * 0.25, 1e-4)
    pivot_outside = any(
        pivot[i] < box[i] - margin or pivot[i] > box[i + 3] + margin for i in range(3)
    )
    # A pivot far from the curve is usually DELIBERATE (a petal control drawn
    # at the petal tip but pivoting at the head centre). Only the frozen-
    # control signature -- pivot left at the world origin while the curve
    # sits elsewhere -- means "no meaningful pivot"; then the shape centre is
    # the origin the animator perceives.
    pivot_at_world_origin = all(abs(c) <= 1e-4 for c in pivot)
    if pivot_outside and pivot_at_world_origin:
        return center, 'bounding_box_center'
    return pivot, 'rotate_pivot'


def _query_transform_snapshot(node, role, module_name, driven_bone, anchor_bone,
                              source_node=None, reference_bone=None):
    """Capture compact controller data and a bone-local reconstruction offset.

    Besides the raw transform, the snapshot records the controller's ORIGIN as
    a displacement from its anchor bone, already mapped to Unreal axes and
    centimetres (``offset_from_anchor_unreal``). A displacement carries no
    absolute position, so it is immune to any root/offset/scale differences
    between the Maya scene and the imported skeleton: Unreal re-adds it to the
    anchor bone's own imported position. ``reference`` (anchor -> neighbouring
    bone, same mapping) lets Unreal verify that the axis/unit mapping agrees
    with the imported skeleton before trusting the offset.
    """
    if not node or not cmds.objExists(node):
        return None

    node = _full_dag_path(node)
    driven_bone = _full_dag_path(driven_bone) if driven_bone else None
    anchor_bone = _full_dag_path(anchor_bone or driven_bone) if (anchor_bone or driven_bone) else None

    try:
        world_translation = cmds.xform(node, query=True, worldSpace=True, translation=True)
    except Exception:
        return None

    origin_world, origin_source = world_translation, 'transform_origin'
    try:
        origin_world, origin_source = _controller_origin_world(node)
    except Exception:
        pass

    shape_id = None
    try:
        shape_id = _register_controller_shape(node, origin_world)
    except Exception as exc:
        print('[RigManifest] Could not export shape of {}: {}'.format(node, exc))
    attributes = []
    try:
        attributes = _controller_attributes(node)
    except Exception:
        pass

    offset_from_anchor = None
    reference = None
    local_fields = {}
    if anchor_bone and cmds.objExists(anchor_bone):
        try:
            local_fields = _local_offset_fields(origin_world, anchor_bone, reference_bone)
        except Exception:
            local_fields = {}
        try:
            anchor_world = cmds.xform(anchor_bone, query=True, worldSpace=True, translation=True)
            offset_from_anchor = _maya_vector_to_unreal(
                [origin_world[i] - anchor_world[i] for i in range(3)], apply_unit_scale=True
            )
            if reference_bone and cmds.objExists(reference_bone):
                reference_world = cmds.xform(reference_bone, query=True, worldSpace=True, translation=True)
                reference = {
                    'bone': _short_node_name(reference_bone),
                    'unreal_vector': _maya_vector_to_unreal(
                        [reference_world[i] - anchor_world[i] for i in range(3)],
                        apply_unit_scale=True,
                    ),
                }
        except Exception:
            offset_from_anchor = None
            reference = None

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

    parent_controllers, parent_space_bone, parent_space_blend = [], None, None
    try:
        parent_controllers, parent_space_bone = _parent_space(node)
        if parent_space_bone:
            parent_space_blend = _parent_space_blend(node)
    except Exception:
        pass

    return dict(local_fields, **{
        'parent_space_blend': parent_space_blend,
        'name': _short_node_name(node),
        'dag_path': node,
        'node_type': cmds.nodeType(node),
        'role': role,
        'module_name': module_name,
        'driven_bone': _short_node_name(driven_bone),
        'anchor_bone': _short_node_name(anchor_bone),
        'source_node': _short_node_name(source_node),
        'parent': _short_node_name(parents[0]) if parents else None,
        'origin_source': origin_source,
        'world_axes_unreal': _safe_call(_world_axes_unreal, node),
        'size_unreal': _safe_call(_world_size_unreal, node),
        'parent_controller': _safe_call(_parent_controller, node),
        'parent_controllers': parent_controllers,
        'parent_space_bone': parent_space_bone,
        'shape_id': shape_id,
        'attributes': attributes,
        'offset_from_anchor_unreal': offset_from_anchor,
        'reference': reference,
        'bone_local_position': _world_point_to_node_local(world_translation, anchor_bone),
        'unreal_world_position': _maya_vector_to_unreal(
            world_translation, apply_unit_scale=True
        ),
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
    })


def _bone_driver_controllers(joint):
    """Return curve controls directly targeting a joint through constraints."""
    # Skip if this joint is marked to bypass constraint detection.
    if _should_skip_constraint_detection(joint):
        return []
    
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

        def _neighbour(index):
            """Bone used to cross-check axis/unit mapping (next, else previous)."""
            if len(chain) < 2:
                return None
            return chain[index + 1] if index < len(chain) - 1 else chain[index - 1]

        module_params = module.get('params') or {}
        is_ikfk = module.get('module_type') == 'IKFKSwitch'

        # Generic FK/direct drivers on the module's own bones.
        for index, bone in enumerate(chain):
            if is_ikfk:
                break  # handled below through the FK chain
            for controller in _bone_driver_controllers(bone):
                _append(
                    bone,
                    _query_transform_snapshot(
                        controller, 'bone_driver', module_name,
                        driven_bone=bone, anchor_bone=bone,
                        reference_bone=_neighbour(index),
                    ),
                )

        # IKFKSwitch: the result chain is blended from separate FK and IK
        # chains, so the animator controls hang off THOSE joints. Map each FK
        # joint's driver onto the result-chain bone at the same index.
        if is_ikfk:
            fk_root = module_params.get('fk_chain_root')
            if fk_root and cmds.objExists(fk_root):
                fk_chains = _collect_chains_from_root(fk_root)
                fk_joints = max(fk_chains, key=len) if fk_chains else []
                for index, fk_joint in enumerate(fk_joints[:len(chain)]):
                    for controller in _bone_driver_controllers(fk_joint):
                        snapshot = _query_transform_snapshot(
                            controller, 'bone_driver', module_name,
                            driven_bone=chain[index], anchor_bone=chain[index],
                            source_node=fk_joint, reference_bone=_neighbour(index),
                        )
                        _append(chain[index], snapshot)

        # IK-specific controls are not necessarily connected to the joints
        # themselves, so capture them explicitly through the ikHandle. For an
        # IKFKSwitch the handle lives on the separate IK chain.
        if module.get('module_type') == 'IKLimb' or is_ikfk:
            ik_start = module_params.get('ik_chain_root') if is_ikfk else chain[0]
            ik_handle = find_ik_handle_for_start_joint(ik_start) if ik_start else None
            if not ik_handle:
                continue

            effector_controller = _find_ik_effector_controller(ik_handle)
            effector_node = effector_controller or ik_handle
            effector_snapshot = _query_transform_snapshot(
                effector_node, 'ik_effector', module_name,
                driven_bone=chain[-1], anchor_bone=chain[-1],
                source_node=ik_handle, reference_bone=_neighbour(len(chain) - 1),
            )
            # No ue_control_name: Unreal names controls after the Maya
            # controller ('name') and falls back to a semantic name only when
            # that Maya name is taken twice.
            _append(chain[-1], effector_snapshot)

            pole_node = _get_pole_vector_node(ik_handle)
            if pole_node and len(chain) >= 2:
                pole_snapshot = _query_transform_snapshot(
                    pole_node, 'pole_vector', module_name,
                    driven_bone=chain[1], anchor_bone=chain[1],
                    source_node=ik_handle, reference_bone=_neighbour(1),
                )
                _append(chain[1], pole_snapshot)

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
    """Return all target transform nodes driving *constraint*.
    
    Carefully guards both targetTranslate and targetRotate queries because
    different constraint types expose different attributes:
    - parentConstraint: has both targetTranslate and targetRotate
    - orientConstraint: only targetRotate
    - pointConstraint: only targetTranslate
    - poleVectorConstraint: only targetTranslate
    
    Querying a missing attribute can raise RuntimeError/ValueError depending
    on Maya version, so both are wrapped in try-except.
    """
    targets = []
    indices = cmds.getAttr('{}.target'.format(constraint), multiIndices=True) or []
    for idx in indices:
        # Guard targetTranslate: not all constraints have this (e.g., orientConstraint).
        try:
            conns = cmds.listConnections(
                '{}.target[{}].targetTranslate'.format(constraint, idx),
                source=True, destination=False, plugs=False,
            ) or []
            targets.extend(conns)
        except (ValueError, RuntimeError, AttributeError):
            pass
        
        # Guard targetRotate: not all constraints have this (e.g., pointConstraint).
        try:
            conns2 = cmds.listConnections(
                '{}.target[{}].targetRotate'.format(constraint, idx),
                source=True, destination=False, plugs=False,
            ) or []
            targets.extend(conns2)
        except (ValueError, RuntimeError, AttributeError):
            pass
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


def _ik_end_joint(handle):
    """The joint an ikHandle's end effector follows (the chain's end joint)."""
    try:
        effector = cmds.ikHandle(handle, query=True, endEffector=True)
    except Exception:
        return None
    sources = cmds.listConnections('{}.translateX'.format(effector), source=True,
                                   destination=False, type='joint') or []
    return sources[0] if sources else None


def root_local_blend(module):
    """True when the limb's ROOT joint takes its values as LOCAL channels
    (pairBlend / blendColors from separate IK and FK chains), so it rides on
    its parent joint; False when a constraint places it in world space."""
    chain = list(module.get('chain') or [])
    if not chain or not cmds.objExists(chain[0]):
        return False
    for attribute in ('translate', 'rotate', 'translateX', 'rotateX'):
        for source in cmds.listConnections('{}.{}'.format(chain[0], attribute), source=True,
                                           destination=False, skipConversionNodes=True) or []:
            kind = cmds.nodeType(source)
            if kind in ('pairBlend', 'blendColors', 'blendTwoAttr', 'animBlendNodeAdditiveRotation'):
                return True
            if cmds.objectType(source, isAType='constraint'):
                return False
    return False


def ik_end_orient(module):
    """True when the IK chain's END joint is oriented by the rig (an orient or
    parent constraint on it -- typically to the IK control), False when only
    the solver sets it. An IK solver alone never rotates the end joint with
    the IK control; Unreal must copy that behaviour, not assume either way.
    """
    ik_root = (module.get('params') or {}).get('ik_chain_root')
    handle = _ik_handle_for_joint(ik_root) if ik_root and cmds.objExists(ik_root) else None
    end = _ik_end_joint(handle) if handle else None
    if not end:
        return False
    for kind in ('orientConstraint', 'parentConstraint'):
        if cmds.listConnections(end, type=kind, source=True, destination=False):
            return True
    return False


def _ik_handle_for_joint(joint):
    """The ikHandle whose solved chain contains ``joint`` (start..end), or None."""
    short = _short_node_name(_full_dag_path(joint))
    parent = (cmds.listRelatives(joint, parent=True) or [None])[0]
    for handle in cmds.ls(type='ikHandle') or []:
        try:
            joints = [_short_node_name(j) for j in (cmds.ikHandle(handle, query=True, jointList=True) or [])]
        except Exception:
            continue
        if short in joints or (parent and _short_node_name(parent) == (joints[-1] if joints else None)):
            return handle
    return None


def _joint_depth_below(joint, ancestor):
    depth, current = 0, _full_dag_path(joint)
    target = _short_node_name(_full_dag_path(ancestor))
    while current and _short_node_name(current) != target:
        parents = cmds.listRelatives(current, parent=True, fullPath=True) or []
        current = parents[0] if parents else None
        depth += 1
    return depth if current else None


def _ancestor_at(joint, levels):
    current = _full_dag_path(joint)
    for _ in range(levels):
        parents = cmds.listRelatives(current, parent=True, fullPath=True) or []
        if not parents:
            return None
        current = parents[0]
    return current


def identify_ik_fk_roots(target_a, target_b):
    """Tell the IK source chain from the FK one by the ikHandle driving it.

    Constraint target order is arbitrary (it is whatever order the rigger
    picked the targets in); the chain an ikHandle solves is the IK chain by
    definition. Returns (ik_root, fk_root) as full paths, or (None, None) when
    exactly one of the two targets is not IK-driven.
    """
    handles = [_ik_handle_for_joint(t) for t in (target_a, target_b)]
    if bool(handles[0]) == bool(handles[1]):
        return None, None
    ik_target, fk_target, handle = (
        (target_a, target_b, handles[0]) if handles[0] else (target_b, target_a, handles[1])
    )
    ik_root = _full_dag_path(cmds.ikHandle(handle, query=True, startJoint=True))
    depth = _joint_depth_below(ik_target, ik_root)
    fk_root = _ancestor_at(fk_target, depth) if depth is not None else None
    return ik_root, fk_root


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
    # Skip joints marked to bypass constraint detection.
    sample = [j for j in chain[:min(3, len(chain))] if not _should_skip_constraint_detection(j)]
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
                        ik_root, fk_root = identify_ik_fk_roots(tgt_joints[0], tgt_joints[1])
                        if not ik_root:
                            print('[RigManifest] IK/FK on {}: cannot tell the IK chain by its '
                                  'ikHandle; falling back to constraint target order.'.format(jnt))
                            ik_root, fk_root = tgt_joints[0], tgt_joints[1]
                        blend_details.append({
                            'blend_node_type': 'constraint',
                            'blend_node': con,
                            'switch_control': switch_ctrl,
                            'switch_attr': switch_attr,
                            'ik_chain_root': ik_root,
                            'fk_chain_root': fk_root,
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
    if 'rp' in solver_lower and not pv_node:
        print(
            "[RigManifest] Warning: no pole-vector target was found for IK handle "
            "'{}' (module '{}'). The UE reconstruction will have to infer the "
            "bend plane from the reference pose.".format(
                ik_handle, _derive_module_name(chain[0])
            )
        )

    # Signed local axes are exported as vectors so mirrored limbs retain their
    # true forward direction instead of both collapsing to the same +X default.
    primary_axis = _signed_primary_axis(chain)
    secondary_axis = _secondary_axis_from_pole(chain, pv_pos, primary_axis)
    unreal_primary_axis = _maya_vector_to_unreal(primary_axis, apply_unit_scale=False)
    unreal_secondary_axis = _maya_vector_to_unreal(secondary_axis, apply_unit_scale=False)
    pv_unreal_world_position = _maya_vector_to_unreal(
        pv_pos, apply_unit_scale=True
    ) if pv_pos else None
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
            'unreal_primary_axis': unreal_primary_axis,
            'unreal_secondary_axis': unreal_secondary_axis,
            'pole_vector_world_position': pv_pos,
            'pole_vector_unreal_world_position': pv_unreal_world_position,
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
    # Full DAG paths throughout: short names are ambiguous when several nodes
    # share a name, and cmds.select() then fails with "More than one object
    # matches name".
    for mesh in cmds.ls(type="mesh", long=True) or []:
        if cmds.getAttr("{}.intermediateObject".format(mesh)):
            continue
        parents = cmds.listRelatives(mesh, parent=True, fullPath=True) or []
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
        # Query only joints to avoid matching meshes/transforms with same short name.
        matches = cmds.ls(node, long=True, type="joint") or []
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


def _world_translation(node):
    return cmds.xform(node, query=True, worldSpace=True, translation=True)


def _nearest_chain_bone(chain, world_point):
    """Chain bone closest to a world point, plus a neighbouring bone."""
    best_index, best_distance = 0, None
    for index, bone in enumerate(chain):
        position = _world_translation(bone)
        distance = sum((position[i] - world_point[i]) ** 2 for i in range(3))
        if best_distance is None or distance < best_distance:
            best_index, best_distance = index, distance
    neighbour = None
    if len(chain) > 1:
        neighbour = chain[best_index + 1] if best_index < len(chain) - 1 else chain[best_index - 1]
    return chain[best_index], neighbour


def _snapshot_for_chain(node, role, module_name, chain):
    """Controller snapshot anchored on the chain bone nearest to it."""
    try:
        origin, _source = _controller_origin_world(node)
    except Exception:
        origin = _world_translation(node)
    anchor, neighbour = _nearest_chain_bone(chain, origin)
    return _query_transform_snapshot(
        node, role, module_name, driven_bone=anchor, anchor_bone=anchor,
        reference_bone=neighbour,
    )


def _point_offset_record(chain, world_point):
    """Anchor-relative Unreal-space description of an arbitrary world point."""
    anchor, neighbour = _nearest_chain_bone(chain, world_point)
    anchor_world = _world_translation(anchor)
    record = {
        'anchor_bone': _short_node_name(anchor),
        **_local_offset_fields(world_point, anchor, neighbour),
        'offset_from_anchor_unreal': _maya_vector_to_unreal(
            [world_point[i] - anchor_world[i] for i in range(3)], apply_unit_scale=True
        ),
    }
    if neighbour:
        neighbour_world = _world_translation(neighbour)
        record['reference'] = {
            'bone': _short_node_name(neighbour),
            'unreal_vector': _maya_vector_to_unreal(
                [neighbour_world[i] - anchor_world[i] for i in range(3)], apply_unit_scale=True
            ),
        }
    return record


def _spline_curve_shape(ik_handle):
    try:
        curve = cmds.ikHandle(ik_handle, query=True, curve=True)
    except Exception:
        curve = None
    if not curve:
        return None
    curve = curve[0] if isinstance(curve, (list, tuple)) else curve
    if cmds.nodeType(curve) == 'nurbsCurve':
        return curve
    shapes = cmds.listRelatives(curve, shapes=True, noIntermediate=True, fullPath=True) or []
    return shapes[0] if shapes else None


def _spline_cv_influences(curve_shape, cv_count):
    """Return (influence_nodes, weights[cv][influence]) driving a spline curve.

    Handles the two usual set-ups: a skinCluster whose influences are the
    controls (or joints under them), and clusters (one handle per control).
    """
    history = cmds.listHistory(curve_shape) or []
    skins = cmds.ls(history, type='skinCluster')
    if skins:
        skin = skins[0]
        influences = cmds.skinCluster(skin, query=True, influence=True) or []
        weights = []
        for cv in range(cv_count):
            values = cmds.skinPercent(skin, '{}.cv[{}]'.format(curve_shape, cv), query=True, value=True)
            weights.append([float(v) for v in values])
        return influences, weights

    clusters = cmds.ls(history, type='cluster')
    if clusters:
        influences, per_cluster = [], []
        for cluster in clusters:
            handle = (cmds.listConnections('{}.matrix'.format(cluster), source=True, destination=False) or [None])[0]
            if not handle:
                continue
            influences.append(handle)
            column = []
            for cv in range(cv_count):
                try:
                    values = cmds.percent(cluster, '{}.cv[{}]'.format(curve_shape, cv), query=True, value=True)
                    column.append(float(values[0]) if values else 0.0)
                except Exception:
                    column.append(0.0)
            per_cluster.append(column)
        weights = [[per_cluster[j][cv] for j in range(len(influences))] for cv in range(cv_count)]
        return influences, weights
    return [], []


def _spline_ik_export(module):
    """Everything needed to rebuild a Maya spline IK's controls in Unreal.

    The exact controllers that drive the curve (not evenly spaced stand-ins),
    the curve's CVs, and the per-CV influence weights, so Unreal can drive its
    spline points from the same controllers at the same places.
    """
    chain = list(module.get('chain') or [])
    if not chain:
        return None
    ik_handle = find_ik_handle_for_start_joint(chain[0])
    if not ik_handle:
        return None
    curve_shape = _spline_curve_shape(ik_handle)
    if not curve_shape:
        return None

    degree = int(cmds.getAttr('{}.degree'.format(curve_shape)))
    cv_count = int(cmds.getAttr('{}.spans'.format(curve_shape))) + degree
    influences, weights = _spline_cv_influences(curve_shape, cv_count)
    module_name = module.get('module_name') or ''

    # Collapse influences to the animator-facing controllers (a joint under a
    # control counts for that control) and merge their weight columns.
    # The influence itself is what moves the curve, so its position is the
    # spline control's position. Its shape and attributes come from the
    # animator control it sits under (a joint has neither).
    controls, columns, holders = [], [], {}
    for column_index, influence in enumerate(influences):
        control = _full_dag_path(influence)
        holders[control] = _nearest_controller_transform(influence)
        if control in controls:
            target = columns[controls.index(control)]
        else:
            controls.append(control)
            target = [0.0] * cv_count
            columns.append(target)
        for cv in range(cv_count):
            target[cv] += weights[cv][column_index]

    # Order controls along the curve by their weighted mean CV index.
    def _centre(column):
        total = sum(column)
        return sum(i * w for i, w in enumerate(column)) / total if total > 1e-9 else 1e9

    order = sorted(range(len(controls)), key=lambda i: _centre(columns[i]))
    records = []
    for rank, index in enumerate(order):
        snapshot = _snapshot_for_chain(controls[index], 'spline_control', module_name, chain)
        if snapshot:
            # Named after the animator control the influence sits under
            # (e.g. Pelvis_IKctrl), which is what the animator knows.
            holder = holders.get(controls[index])
            snapshot['ue_control_name'] = _short_node_name(holder or controls[index])
            snapshot['semantic_name'] = '{}_SplineCtrl{:02d}_CTRL'.format(module_name, rank)
            if holder and not snapshot.get('shape_id'):
                try:
                    origin, _source = _controller_origin_world(controls[index])
                    snapshot['shape_id'] = _register_controller_shape(holder, origin)
                    snapshot['attributes'] = _controller_attributes(holder)
                    snapshot['shape_source'] = _short_node_name(holder)
                except Exception:
                    pass
            if holder:
                # The UE control stands for the holder: take its hierarchy,
                # orientation and locks, not the influence joint's.
                try:
                    snapshot['parent_controllers'], snapshot['parent_space_bone'] = _parent_space(holder)
                    snapshot['world_axes_unreal'] = _world_axes_unreal(holder)
                    snapshot['locked_channels'] = _locked_channels(holder)
                except Exception:
                    pass
        records.append(snapshot)

    cvs = []
    for cv in range(cv_count):
        point = cmds.pointPosition('{}.cv[{}]'.format(curve_shape, cv), world=True)
        entry = _point_offset_record(chain, point)
        entry['weights'] = [round(columns[i][cv], 4) for i in order]
        cvs.append(entry)

    if not records or any(r is None for r in records):
        return None
    return {
        'ik_handle': _short_node_name(ik_handle),
        'curve': _short_node_name(curve_shape),
        'degree': degree,
        'cv_count': cv_count,
        'controls': records,
        'cvs': cvs,
    }


def _enum_index(names, prefix):
    for index, name in enumerate(names or []):
        if str(name).strip().lower().startswith(prefix):
            return index
    return None


def _switch_ik_value_from_blend(blend_node, blend_type, ik_root):
    """Fallback polarity: which attribute value fully selects the IK chain."""
    if not blend_node or not ik_root or not cmds.objExists(ik_root):
        return None
    ik_joints = set(cmds.listRelatives(ik_root, allDescendents=True, type='joint') or [])
    ik_joints.add(_short_node_name(ik_root))
    try:
        if blend_type == 'pairBlend':
            # weight 0 -> input 1, weight 1 -> input 2.
            source = cmds.listConnections('{}.inTranslate1'.format(blend_node), source=True, destination=False) or \
                cmds.listConnections('{}.inRotate1'.format(blend_node), source=True, destination=False) or []
            if source:
                return 0.0 if _short_node_name(source[0]) in ik_joints else 1.0
        elif blend_type == 'blendColors':
            # blender 1 -> color 1, blender 0 -> color 2.
            source = cmds.listConnections('{}.color1'.format(blend_node), source=True, destination=False) or []
            if source:
                return 1.0 if _short_node_name(source[0]) in ik_joints else 0.0
    except Exception:
        pass
    return None


def _ikfk_switch_export(module):
    """Find the IK/FK switch control + attribute of an IKFKSwitch module.

    Returns a params dict fragment (empty when no switch is found): the
    controller snapshot (position, shape, attributes), the driving attribute,
    which attribute value means "fully IK"/"fully FK", and the current value
    expressed as an IK weight.
    """
    chain = list(module.get('chain') or [])
    if len(chain) < 2:
        return {}
    try:
        detected = detect_ikfk_switch(chain)
    except Exception:
        detected = None
    if not detected:
        return {}
    found = detected.get('params') or {}
    control, attribute = found.get('switch_control'), found.get('switch_attr')
    if not control or not attribute or not cmds.objExists(control):
        return {}

    module_name = module.get('module_name') or ''
    ik_root = (module.get('params') or {}).get('ik_chain_root') or found.get('ik_chain_root')
    info = next((a for a in _controller_attributes(control) if a['name'] == attribute), None)
    if info is None:
        try:
            info = {'name': attribute, 'type': 'float', 'value': float(cmds.getAttr('{}.{}'.format(control, attribute))),
                    'min': 0.0, 'max': 1.0, 'default': 0.0, 'keyable': True}
        except Exception:
            return {}

    ik_value = fk_value = None
    if info.get('type') == 'enum':
        ik_value = _enum_index(info.get('enum_names'), 'ik')
        fk_value = _enum_index(info.get('enum_names'), 'fk')
    if ik_value is None:
        ik_value = _switch_ik_value_from_blend(
            found.get('blend_node'), found.get('blend_node_type'), ik_root
        )
    if ik_value is None:
        ik_value = float(info.get('max', 1.0))
    lo, hi = float(info.get('min', 0.0)), float(info.get('max', 1.0))
    if fk_value is None:
        fk_value = lo if abs(ik_value - hi) < 1e-6 else hi
    ik_value, fk_value = float(ik_value), float(fk_value)

    span = ik_value - fk_value
    weight = (float(info.get('value', 0.0)) - fk_value) / span if abs(span) > 1e-9 else 0.0
    weight = max(0.0, min(1.0, weight))

    snapshot = _snapshot_for_chain(control, 'settings', module_name, chain)
    if not snapshot:
        return {}
    return {
        'switch': {
            'control': snapshot,
            'attribute': attribute,
            'attribute_info': info,
            'ik_value': ik_value,
            'fk_value': fk_value,
            'default_ik_weight': round(weight, 4),
        },
        'switch_control': _short_node_name(control),
        'switch_attr': attribute,
        'blend_node_type': found.get('blend_node_type'),
        'blend_node': _short_node_name(found.get('blend_node')),
        'default_value': round(weight, 4),
    }


# ---------------------------------------------------------------------------
# Constraint-driven bones
#
# Many rigs drive a bone channel by channel: a point constraint for position
# only, an orient constraint for rotation only, several controllers blended by
# weights, one controller feeding several bones (the petals: pedal_ctrl_01
# point-constrains Purple1 and orient-constrains Purple2). A plain FK "one
# control per bone" rebuild cannot represent that. Every Maya constraint that
# drives a module bone is therefore exported as-is and rebuilt in Unreal with
# the equivalent native Control Rig constraint node.
# ---------------------------------------------------------------------------

_CONSTRAINT_KINDS = {
    'parentConstraint': ('parent', ('translate', 'rotate')),
    'pointConstraint': ('point', ('translate',)),
    'orientConstraint': ('orient', ('rotate',)),
    'scaleConstraint': ('scale', ('scale',)),
    'aimConstraint': ('aim', ('rotate',)),
}


def _driven_axes(constraint, joint, attribute):
    """Axes ('x','y','z') of joint.<attribute> fed by ``constraint``."""
    target = _short_node_name(constraint)
    axes = []
    for axis in 'XYZ':
        sources = cmds.listConnections(
            '{}.{}{}'.format(joint, attribute, axis), source=True, destination=False
        ) or []
        if target in {_short_node_name(s) for s in sources}:
            axes.append(axis.lower())
    if not axes:
        sources = cmds.listConnections(
            '{}.{}'.format(joint, attribute), source=True, destination=False
        ) or []
        if target in {_short_node_name(s) for s in sources}:
            axes = ['x', 'y', 'z']
    return axes


def _maya_axes_to_unreal(axes):
    """Map Maya axis letters to Unreal ones (Y-up: y<->z)."""
    if _maya_up_axis() == 'z':
        return sorted(axes)
    swap = {'x': 'x', 'y': 'z', 'z': 'y'}
    return sorted(swap[a] for a in axes)


def _constraint_record(constraint, joint, module_name, chain):
    node_type = cmds.nodeType(constraint)
    if node_type not in _CONSTRAINT_KINDS:
        return None
    kind, attributes = _CONSTRAINT_KINDS[node_type]
    channels = {}
    for attribute in attributes:
        axes = _driven_axes(constraint, joint, attribute)
        if axes:
            channels[attribute] = _maya_axes_to_unreal(axes)
    if not channels:
        return None     # joint is a target of this constraint, not driven by it

    command = getattr(cmds, node_type)
    target_nodes = command(constraint, query=True, targetList=True) or []
    weight_attrs = command(constraint, query=True, weightAliasList=True) or []
    targets = []
    for index, target in enumerate(target_nodes):
        weight = 1.0
        if index < len(weight_attrs):
            try:
                weight = float(cmds.getAttr('{}.{}'.format(constraint, weight_attrs[index])))
            except Exception:
                pass
        target_path = _full_dag_path(target)
        controller = _nearest_controller_transform(target_path) or target_path
        snapshot = _snapshot_for_chain(controller, 'constraint_driver', module_name, chain)
        if not snapshot:
            print('[RigManifest] {}: target {} of {} could not be captured; skipped.'.format(
                module_name, target, constraint))
            continue
        entry = {
            'weight': weight,
            'controller': snapshot,
            'target': None,
        }
        if _short_node_name(controller) != _short_node_name(target_path):
            # The constraint follows a node rigidly attached under the
            # controller: rebuilt as a null under the control.
            entry['target'] = dict(
                _point_offset_record(chain, _world_translation(target_path)),
                name=_short_node_name(target_path),
                world_axes_unreal=_safe_call(_world_axes_unreal, target_path),
            )
        targets.append(entry)
    if not targets:
        return None
    return {
        'bone': _short_node_name(joint),
        'constraint': _short_node_name(constraint),
        'type': kind,
        'channels': channels,
        'targets': targets,
    }


def _bone_constraints_export(module):
    """Every constraint driving the bones of a module, in chain order."""
    chain = list(module.get('chain') or [])
    module_name = module.get('module_name') or ''
    records = []
    for joint in chain:
        if _should_skip_constraint_detection(joint):
            continue
        constraints = set()
        for node_type in _CONSTRAINT_KINDS:
            constraints.update(cmds.listConnections(joint, type=node_type, source=True) or [])
        for constraint in sorted(constraints):
            # poleVectorConstraint is a pointConstraint subtype; never a bone driver.
            if cmds.nodeType(constraint) not in _CONSTRAINT_KINDS:
                continue
            try:
                record = _constraint_record(constraint, joint, module_name, chain)
            except Exception as exc:
                print('[RigManifest] Could not export constraint {} on {}: {}'.format(
                    constraint, joint, exc))
                record = None
            if record:
                records.append(record)
    return records


_AXIS_LABELS = (
    ('+X', (1.0, 0.0, 0.0)), ('-X', (-1.0, 0.0, 0.0)),
    ('+Y', (0.0, 1.0, 0.0)), ('-Y', (0.0, -1.0, 0.0)),
    ('+Z', (0.0, 0.0, 1.0)), ('-Z', (0.0, 0.0, -1.0)),
)


def _axis_label(vector, min_alignment=0.8):
    length = sum(c * c for c in vector) ** 0.5
    if length < 1e-9:
        return None
    unit = [c / length for c in vector]
    label, dot = max(((name, sum(a * b for a, b in zip(unit, axis))) for name, axis in _AXIS_LABELS),
                     key=lambda item: item[1])
    return label if dot >= min_alignment else None


def _mirror_label_to_unreal(label):
    """Maya joint-local axis label -> Unreal joint-local label (Y mirrored)."""
    if not label:
        return None
    if label[1] == 'Y':
        return ('-' if label[0] == '+' else '+') + 'Y'
    return label


def _chain_axes(chain):
    """Per-chain axis convention: aim axis and bend (up) axis.

    aim_axis: the local axis of each joint pointing at the next one
    (majority over the chain). up_axis: the local axis of the first joint
    pointing toward the bend (the mid joint's side of the start->end line),
    i.e. where a pole vector goes; None for straight or 2-joint chains. Both
    as Maya labels and as Unreal labels (joint-local Y mirrored).
    """
    if len(chain) < 2:
        return None
    votes = {}
    for parent, child in zip(chain[:-1], chain[1:]):
        local = _joint_local_unreal(_world_translation(child), parent)
        maya_local = [local[0], -local[1], local[2]]
        label = _axis_label(maya_local)
        if label:
            votes[label] = votes.get(label, 0) + 1
    aim = max(votes, key=votes.get) if votes else None

    up = None
    if len(chain) >= 3:
        p0, p1, p2 = (_world_translation(j) for j in chain[:3])
        line = [p2[i] - p0[i] for i in range(3)]
        length_sq = sum(c * c for c in line)
        if length_sq > 1e-12:
            t = sum((p1[i] - p0[i]) * line[i] for i in range(3)) / length_sq
            foot = [p0[i] + t * line[i] for i in range(3)]   # mid joint projected on the line
            local_bend = _joint_local_unreal(p1, chain[0])
            local_foot = _joint_local_unreal(foot, chain[0])
            direction = [local_bend[i] - local_foot[i] for i in range(3)]
            if sum(c * c for c in direction) > 1e-6:
                up = _axis_label([direction[0], -direction[1], direction[2]])
    return {
        'aim_axis': aim,
        'up_axis': up,
        'aim_axis_unreal': _mirror_label_to_unreal(aim),
        'up_axis_unreal': _mirror_label_to_unreal(up),
    }


def _verify_ikfk_roots(module):
    """Make params.ik_chain_root the chain an ikHandle actually solves.

    Tagged roots are trusted only when they agree with the scene; a swapped
    pair is corrected (and reported) rather than silently exported.
    """
    params = module.setdefault('params', {})
    ik_root, fk_root = params.get('ik_chain_root'), params.get('fk_chain_root')
    if not ik_root or not fk_root or not cmds.objExists(ik_root) or not cmds.objExists(fk_root):
        return
    ik_driven = bool(_ik_handle_for_joint(ik_root))
    fk_driven = bool(_ik_handle_for_joint(fk_root))
    if fk_driven and not ik_driven:
        print('[RigManifest] {}: ik_chain_root/fk_chain_root were swapped (ikHandle drives {}); '
              'corrected.'.format(module.get('module_name'), fk_root))
        params['ik_chain_root'], params['fk_chain_root'] = fk_root, ik_root
    elif not ik_driven:
        print('[RigManifest] {}: no ikHandle drives ik_chain_root {}; check the tags.'.format(
            module.get('module_name'), ik_root))


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

    extra = {}
    try:
        if enriched.get('module_type') == 'IKFKSwitch':
            _verify_ikfk_roots(enriched)
            extra = _ikfk_switch_export(enriched)
            extra['ik_end_orient'] = ik_end_orient(enriched)
            extra['root_local_blend'] = root_local_blend(enriched)
        elif enriched.get('module_type') == 'SplineIK':
            spline = _spline_ik_export(enriched)
            extra = {'spline': spline} if spline else {}
            # Constraints layered on the spline chain (e.g. the top joint
            # orient-constrained to the chest control) are part of its behaviour.
            constraints = _bone_constraints_export(enriched)
            if constraints:
                extra['constraints'] = constraints
        elif enriched.get('module_type') == 'FKChain':
            constraints = _bone_constraints_export(enriched)
            extra = {'constraints': constraints} if constraints else {}
    except Exception as exc:
        print('[RigManifest] Could not export system data for {}: {}'.format(
            enriched.get('module_name'), exc))
    if extra:
        # Scene-derived data replaces the tagger's placeholders (its switch
        # fields are None and default_value is a blind 0.0); every other
        # explicit tagger value (ik/fk chain roots, ...) is kept.
        merged = {k: v for k, v in (enriched.get('params') or {}).items() if v is not None}
        merged.update(extra)
        enriched['params'] = merged

    return enriched


def build_manifest(rig_name, modules_config):
    """Build a schema-v5 manifest: modules, bone-linked controllers, shapes."""
    _reset_shape_registry()
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
        axes = _safe_call(_chain_axes, [_full_dag_path(b) for b in raw_chain])
        if axes:
            module_def["axes"] = axes

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
    try:
        scene = cmds.file(query=True, sceneName=True) or ""
        dcc_version = cmds.about(version=True)
    except Exception:
        scene, dcc_version = "", ""
    return {
        "schema": "kotsudo.rig",
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "rig_name": rig_name,
        "source": {
            "dcc": "maya",
            "dcc_version": dcc_version,
            "scene": os.path.basename(scene),
            "exporter": "export_rig_manifest.py",
        },
        # Every value named *_unreal, offset_local, size_unreal and the shape
        # points is already in Unreal centimetres; rotations are axes or
        # degrees. Source units are kept for reference only.
        "units": {"linear": "cm", "angular": "deg"},
        "coordinate_system": _coordinate_system_manifest(),
        "module_build_order": list(graph.get("build_order", [])),
        "module_graph": {
            "valid": graph.get("valid", True),
            "root_modules": list(graph.get("root_modules", [])),
            "connections": serializable_connections,
            "issues": list(graph.get("global_issues", [])),
            "module_issues": dict(graph.get("module_issues", {})),
        },
        "bone_controllers": collect_bone_controller_manifest(modules_config),
        "control_shapes": dict(_SHAPE_REGISTRY),
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


_FBX_MODEL_NAME_RE = re.compile(rb"([\x20-\x7e]+)\x00\x01Model")


def read_fbx_model_names(fbx_path):
    """Return every Model (transform/joint/mesh) name stored in a binary FBX."""
    with open(fbx_path, "rb") as handle:
        data = handle.read()
    if not data.startswith(b"Kaydara FBX Binary"):
        raise RuntimeError("Cannot verify '{}': not a binary FBX.".format(fbx_path))
    return [m.decode("ascii") for m in _FBX_MODEL_NAME_RE.findall(data)]


def verify_exported_fbx(fbx_path, manifest):
    """Read the written FBX back and check it against the manifest.

    Catches, at export time, everything that would otherwise surface in
    Unreal as "Bone 'X' was not found": duplicate node names (FBX cannot keep
    two nodes with one name) and manifest bones missing from the file.
    Raises RuntimeError listing every problem found.
    """
    names = read_fbx_model_names(fbx_path)
    counts = {}
    for name in names:
        counts[name] = counts.get(name, 0) + 1

    problems = []
    duplicates = sorted(n for n, c in counts.items() if c > 1)
    if duplicates:
        problems.append(
            "Duplicate node names in FBX (rename one of each pair): "
            + ", ".join(duplicates)
        )

    missing = []
    for module in manifest.get("modules", []):
        for bone in module.get("chain", []) or []:
            if bone not in counts and bone not in missing:
                missing.append(bone)
    if missing:
        problems.append("Manifest bones missing from FBX: " + ", ".join(missing))

    if problems:
        raise RuntimeError(
            "FBX verification failed for '{}':\n  {}".format(fbx_path, "\n  ".join(problems))
        )
    print("[RigManifest] FBX verified: {} nodes, all manifest bones present, no duplicates."
          .format(len(names)))


def _manifest_schema_module():
    """rig_builder.manifest_schema, shared with the Unreal builder."""
    import sys
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    import importlib
    from rig_builder import manifest_schema
    return importlib.reload(manifest_schema)


def validate_manifest_or_raise(manifest):
    """Validate against schema/kotsudo_manifest.schema.json before anything is written."""
    errors, warnings = _manifest_schema_module().validate_manifest(manifest)
    for warning in warnings:
        print("[RigManifest] Manifest warning: {}".format(warning))
    if errors:
        raise RuntimeError(
            "Manifest failed validation ({} error(s)); nothing was exported:\n  {}".format(
                len(errors), "\n  ".join(errors[:25]))
        )
    print("[RigManifest] Manifest valid (schema v{}, {} warning(s)).".format(
        manifest.get("schema_version"), len(warnings)))


def _tube_mesh_data(strands, radius):
    """Square-section tube around each polyline. Returns (points, counts, connects)."""
    points, counts, connects = [], [], []

    def _norm(v):
        length = (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) ** 0.5
        return [c / length for c in v] if length > 1e-9 else [0.0, 0.0, 0.0]

    def _cross(a, b):
        return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]

    for strand in strands:
        line = [list(p) for p in strand['raw']]
        if strand.get('closed') and len(line) > 2 and line[0] != line[-1]:
            line.append(list(line[0]))
        for a, b in zip(line[:-1], line[1:]):
            direction = _norm([b[i] - a[i] for i in range(3)])
            if direction == [0.0, 0.0, 0.0]:
                continue
            helper = [0.0, 1.0, 0.0] if abs(direction[1]) < 0.9 else [1.0, 0.0, 0.0]
            side = _norm(_cross(direction, helper))
            up = _cross(direction, side)
            corners = [(1, 1), (-1, 1), (-1, -1), (1, -1)]
            base = len(points)
            for end in (a, b):
                for su, uu in corners:
                    points.append([
                        end[i] + radius * (su * side[i] + uu * up[i]) for i in range(3)
                    ])
            for k in range(4):
                k2 = (k + 1) % 4
                counts.append(4)
                connects.extend([base + k, base + k2, base + 4 + k2, base + 4 + k])
    return points, counts, connects


def _create_shape_mesh(shape_id, strands):
    """Create the poly tube mesh for one shape in Maya; return its transform."""
    import maya.api.OpenMaya as om2

    flat = [p for s in strands for p in s['raw']]
    lows = [min(p[i] for p in flat) for i in range(3)]
    highs = [max(p[i] for p in flat) for i in range(3)]
    diagonal = sum((highs[i] - lows[i]) ** 2 for i in range(3)) ** 0.5
    radius = max(diagonal * SHAPE_TUBE_RADIUS_RATIO, SHAPE_TUBE_MIN_RADIUS)

    points, counts, connects = _tube_mesh_data(strands, radius)
    if not counts:
        return None
    point_array = om2.MPointArray([om2.MPoint(*p) for p in points])
    transform = om2.MFnMesh().create(point_array, om2.MIntArray(counts), om2.MIntArray(connects))
    dag = om2.MFnDagNode(transform)
    name = cmds.rename(dag.fullPathName(), SHAPE_MESH_PREFIX + shape_id)
    try:
        cmds.sets(name, edit=True, forceElement='initialShadingGroup')
    except Exception:
        pass
    return name


def export_control_shapes_fbx(shapes_dir):
    """Export each controller shape as its own FBX: <shapes_dir>/RB_<shape_id>.fbx.

    One file per shape, because Unreal's Interchange importer merges every mesh
    of an FBX into a single static mesh by default -- a multi-mesh file comes
    back as one asset named after the file. The mesh is a tube around the
    Maya curve, centred on the controller origin, world-oriented, Maya axes:
    the importer converts it exactly like the skeleton. The temporary meshes
    are deleted afterwards. Returns the shape ids exported.
    """
    if not _SHAPE_RAW:
        return []
    if not os.path.isdir(shapes_dir):
        os.makedirs(shapes_dir)
    exported = []
    for shape_id, strands in sorted(_SHAPE_RAW.items()):
        node = None
        path = os.path.join(shapes_dir, SHAPE_MESH_PREFIX + shape_id + '.fbx')
        try:
            node = _create_shape_mesh(shape_id, strands)
            if not node:
                continue
            export_fbx(path, [node])
            if SHAPE_MESH_PREFIX + shape_id not in read_fbx_model_names(path):
                raise RuntimeError('mesh missing from the written file')
            exported.append(shape_id)
        except Exception as exc:
            print('[RigManifest] Could not export shape {}: {}'.format(shape_id, exc))
        finally:
            if node and cmds.objExists(node):
                cmds.delete(node)
    print('[RigManifest] Control shapes exported: {}/{} -> {}'.format(
        len(exported), len(_SHAPE_RAW), shapes_dir))
    return exported


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
    validate_manifest_or_raise(manifest)
    shapes_dir = os.path.join(export_dir, "{}_shapes".format(filename_base))
    if _SHAPE_RAW:
        # Unreal finds this folder (RB_<shape_id>.fbx files) next to the rig FBX.
        manifest["shapes_dir"] = os.path.basename(shapes_dir)
    manifest["poses_file"] = "{}.poses.json".format(filename_base)
    compact_json = json.dumps(manifest, separators=(",", ":"))
    write_manifest_to_joint(ROOT_JOINT_NAME, compact_json)

    _restore_bind_pose(modules_config)

    mesh_transforms = collect_visible_mesh_transforms()
    root_matches = cmds.ls(ROOT_JOINT_NAME, long=True, type="joint") or []
    root_node = root_matches[0] if root_matches else ROOT_JOINT_NAME
    export_nodes = [root_node] + [m for m in mesh_transforms if m != root_node]

    # A mesh transform sharing a short name with a joint (e.g. mesh "Head" and
    # joint "Head") collides in the FBX: the skeleton then lacks the bone the
    # manifest refers to ("Bone 'Head' was not found"). Temporarily rename the
    # clashing meshes for the export, then restore their original names.
    joint_paths = cmds.listRelatives(
        root_node, allDescendents=True, fullPath=True, type="joint"
    ) or []
    joint_paths.append(root_node)
    joint_names = {_short_joint_name(j) for j in joint_paths}

    duplicate_joints = sorted(
        n for n in joint_names
        if sum(1 for j in joint_paths if _short_joint_name(j) == n) > 1
    )
    if duplicate_joints:
        raise RuntimeError(
            "Duplicate joint names under '{}': {}".format(root_node, ", ".join(duplicate_joints))
        )

    renamed = []  # (uuid, original short name)
    taken = set(joint_names) | {_short_joint_name(m) for m in mesh_transforms}
    try:
        for i, mesh in enumerate(list(export_nodes)):
            if mesh == root_node:
                continue
            short = _short_joint_name(mesh)
            if short not in joint_names and sum(
                1 for m in mesh_transforms if _short_joint_name(m) == short
            ) <= 1:
                continue
            new_name = short + "_Mesh"
            while new_name in taken:
                new_name += "_"
            taken.add(new_name)
            uuid = cmds.ls(mesh, uuid=True)[0]
            new_path = cmds.rename(mesh, new_name)
            renamed.append((uuid, short))
            export_nodes[i] = cmds.ls(uuid, long=True)[0] if new_path else new_path
            print("[RigManifest] Renamed '{}' -> '{}' for export.".format(short, new_name))

        export_fbx(fbx_path, export_nodes)
    finally:
        for uuid, original in renamed:
            nodes = cmds.ls(uuid, long=True) or []
            if nodes:
                cmds.rename(nodes[0], original)

    verify_exported_fbx(fbx_path, manifest)

    # Controller shapes travel as mesh-only FBXs (tube meshes built from the
    # Maya curves). A failure here must not lose the rig export.
    if _SHAPE_RAW:
        try:
            export_control_shapes_fbx(shapes_dir)
        except Exception as exc:
            print("[RigManifest] Shapes FBX export failed ({}). The rig FBX is unaffected; "
                  "Unreal will use built-in shapes.".format(exc))

    # Test poses for the pose-match harness (scene is at bind pose here).
    # A failure is reported but never loses the rig export.
    try:
        # Sibling module: importable whether this file was loaded from the repo
        # (tools/maya on sys.path) or by path.
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        # Python caches each folder's file list: a module file added after
        # Maya started is invisible to import until the cache is dropped.
        importlib.invalidate_caches()
        import export_test_poses
        importlib.reload(export_test_poses)
        export_test_poses.export_test_poses(
            os.path.join(export_dir, manifest["poses_file"]), manifest
        )
    except Exception as exc:
        import traceback
        traceback.print_exc()
        cmds.warning("[RigManifest] Test-pose export failed ({}: {}); the harness will have "
                     "nothing to replay. Traceback in the Script Editor.".format(type(exc).__name__, exc))

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