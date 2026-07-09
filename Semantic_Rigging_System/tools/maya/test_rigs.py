"""
Minimal test-rig construction snippets for the Semantic Rigging System.

Run each section independently in Maya's Script Editor (Python tab) to build
a minimal scene that the structural detectors in export_rig_manifest.py can
validate against.  Each snippet is self-contained:
  1. Deletes any pre-existing nodes with the same names.
  2. Builds the rig structure from scratch.
  3. Prints the expected detection result so you can compare with the actual
     output from run_detection_pipeline().

Usage:
    # In Maya Script Editor:
    exec(open(r"E:/Kotsudo/Semantic_Rigging_System/tools/maya/test_rigs.py").read())
    build_fk_chain_rig()
    build_ik_limb_rig()
    build_spline_ik_rig()
    build_ikfk_switch_rig()
    build_squash_stretch_rig()
"""

import maya.cmds as cmds


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _delete_if_exists(*nodes):
    for node in nodes:
        if cmds.objExists(node):
            cmds.delete(node)


def _joint_at(name, pos, parent=None):
    cmds.select(clear=True)
    j = cmds.joint(name=name, position=pos)
    if parent and cmds.objExists(parent):
        cmds.parent(j, parent)
    return j


def _print_expected(label, module_type, chain):
    print('[TestRig] Expected detection: {} -> module_type="{}" chain={}'.format(
        label, module_type, chain
    ))
    print('[TestRig] Run: import export_rig_manifest as m; print(m.run_detection_pipeline())')


# ---------------------------------------------------------------------------
# 1. FKChain  -- plain parent/child joints, no IK, no constraints
# ---------------------------------------------------------------------------

def build_fk_chain_rig():
    """Build a 4-joint FK spine chain.

    Expected detection: FKChain  module_name='spine'
    """
    names = ['spine_01_jnt', 'spine_02_jnt', 'spine_03_jnt', 'spine_04_jnt']
    _delete_if_exists(*names)

    cmds.select(clear=True)
    prev = None
    for i, name in enumerate(names):
        cmds.select(prev or [])
        j = cmds.joint(name=name, position=(0, i * 5, 0))
        prev = j

    cmds.setAttr('{}.preferredAngleY'.format(names[1]), 15.0)
    print('[TestRig] Built FK chain: {}'.format(names))
    _print_expected('spine', 'FKChain', names)


# ---------------------------------------------------------------------------
# 2. IKLimb  -- 3-joint chain + ikRPsolver handle + pole vector locator
# ---------------------------------------------------------------------------

def build_ik_limb_rig():
    """Build a 3-joint IK arm with a pole vector locator.

    Expected detection: IKLimb  module_name='L_arm'
    """
    names = ['L_arm_01_jnt', 'L_arm_02_jnt', 'L_arm_03_jnt']
    pv_loc = 'L_arm_PV_loc'
    handle_name = 'L_arm_ikHandle'

    _delete_if_exists(handle_name, pv_loc, *names)

    cmds.select(clear=True)
    j1 = cmds.joint(name=names[0], position=(5, 10, 0))
    j2 = cmds.joint(name=names[1], position=(5, 5, 1))   # slight Z offset for RP solver
    j3 = cmds.joint(name=names[2], position=(5, 0, 0))
    # Set preferred angle so the RP solver bends correctly.
    cmds.setAttr('{}.preferredAngleZ'.format(j2), -45.0)

    handle, effector = cmds.ikHandle(
        name=handle_name,
        startJoint=j1,
        endEffector=j3,
        solver='ikRPsolver',
    )

    loc = cmds.spaceLocator(name=pv_loc)[0]
    cmds.move(5, 5, -5, loc)
    cmds.poleVectorConstraint(loc, handle)

    print('[TestRig] Built IK limb: {}'.format(names))
    print('[TestRig] IK handle: {}  Pole vector locator: {}'.format(handle, loc))
    _print_expected('L_arm', 'IKLimb', names)


# ---------------------------------------------------------------------------
# 3. SplineIK  -- 5-joint chain + ikSplineSolver + nurbs curve
# ---------------------------------------------------------------------------

def build_spline_ik_rig():
    """Build a 5-joint spine with a spline IK handle (auto-generated curve).

    Expected detection: SplineIK  module_name='spine'
    """
    names = ['spine_01_jnt', 'spine_02_jnt', 'spine_03_jnt',
             'spine_04_jnt', 'spine_05_jnt']
    handle_name = 'spine_splineIkHandle'

    _delete_if_exists(handle_name)
    _delete_if_exists(*names)
    # Also delete any auto-generated curve from a previous run.
    for crv in cmds.ls('curve*') or []:
        if cmds.objectType(crv) in ('nurbsCurve', 'transform'):
            _delete_if_exists(crv)

    cmds.select(clear=True)
    prev = None
    for i, name in enumerate(names):
        cmds.select(prev or [])
        j = cmds.joint(name=name, position=(0, i * 4, 0))
        prev = j

    handle, effector, curve = cmds.ikHandle(
        name=handle_name,
        startJoint=names[0],
        endEffector=names[-1],
        solver='ikSplineSolver',
        createCurve=True,
        numSpans=2,
    )
    print('[TestRig] Built Spline IK: {}  handle={} curve={}'.format(names, handle, curve))
    _print_expected('spine', 'SplineIK', names)


# ---------------------------------------------------------------------------
# 4. IKFKSwitch  -- result chain + IK chain + FK chain + parentConstraints
#                   + a float switch attribute on a control object
# ---------------------------------------------------------------------------

def build_ikfk_switch_rig():
    """Build a minimal IK/FK switch arm with result/ik/fk joint chains.

    Structure:
        L_arm_result_01_jnt .. 03  <- driven by parentConstraint(ik, fk)
        L_arm_ik_01_jnt    .. 03  <- IK chain with ikRPsolver
        L_arm_fk_01_jnt    .. 03  <- FK chain (free rotate)
        L_arm_ctrl (transform)     <- custom float attr "ikfkBlend" 0-1

    The detector looks at L_arm_result_01_jnt..03 and finds the
    parentConstraints with two joint targets -> IKFKSwitch.

    Expected detection: IKFKSwitch  module_name='L_arm_result'
    """
    result = ['L_arm_result_01_jnt', 'L_arm_result_02_jnt', 'L_arm_result_03_jnt']
    ik_ch  = ['L_arm_ik_01_jnt',     'L_arm_ik_02_jnt',     'L_arm_ik_03_jnt']
    fk_ch  = ['L_arm_fk_01_jnt',     'L_arm_fk_02_jnt',     'L_arm_fk_03_jnt']
    ctrl   = 'L_arm_ctrl'
    handle = 'L_arm_ik_ikHandle'

    _delete_if_exists(handle, ctrl, *result, *ik_ch, *fk_ch)

    positions = [(5, 10, 0), (5, 5, 0.5), (5, 0, 0)]

    def _build_chain(names, positions):
        cmds.select(clear=True)
        joints = []
        for name, pos in zip(names, positions):
            j = cmds.joint(name=name, position=pos)
            joints.append(j)
        return joints

    res_joints = _build_chain(result, positions)
    ik_joints  = _build_chain(ik_ch,  positions)
    fk_joints  = _build_chain(fk_ch,  positions)

    # IK handle on ik chain
    cmds.ikHandle(name=handle, startJoint=ik_joints[0],
                  endEffector=ik_joints[-1], solver='ikRPsolver')

    # Control object with the blend attribute.
    ctrl_node = cmds.createNode('transform', name=ctrl)
    cmds.addAttr(ctrl_node, longName='ikfkBlend', attributeType='float',
                 minValue=0.0, maxValue=1.0, defaultValue=0.0, keyable=True)

    # parentConstraint on each result joint: IK target (W0) and FK target (W1).
    # The blend attr drives W0 directly (IK weight = ikfkBlend).
    # FK weight = 1 - ikfkBlend, built via a reverse node.
    rev = cmds.createNode('reverse', name='L_arm_ikfk_reverse')
    cmds.connectAttr('{}.ikfkBlend'.format(ctrl_node), '{}.inputX'.format(rev))

    for res, ik, fk in zip(res_joints, ik_joints, fk_joints):
        con = cmds.parentConstraint(ik, fk, res, maintainOffset=False)[0]
        # Weight aliases: first target = ik (W0), second = fk (W1).
        aliases = cmds.parentConstraint(con, query=True, weightAliasList=True) or []
        if len(aliases) >= 2:
            cmds.connectAttr(
                '{}.ikfkBlend'.format(ctrl_node),
                '{}.{}'.format(con, aliases[0]),
            )
            cmds.connectAttr(
                '{}.outputX'.format(rev),
                '{}.{}'.format(con, aliases[1]),
            )

    print('[TestRig] Built IK/FK switch rig.')
    print('[TestRig] Result chain: {}  IK chain: {}  FK chain: {}'.format(
        result, ik_ch, fk_ch))
    print('[TestRig] Switch control: {}.ikfkBlend'.format(ctrl_node))
    _print_expected('L_arm_result', 'IKFKSwitch', result)


# ---------------------------------------------------------------------------
# 5. SquashStretch  -- 3-joint chain driven by a distanceBetween node
# ---------------------------------------------------------------------------

def build_squash_stretch_rig():
    """Build a 3-joint neck chain with distance-based squash & stretch.

    Structure:
        neck_01_jnt .. neck_03_jnt  <- FK joints
        neck_start_loc / neck_end_loc   <- locators at chain endpoints
        distanceBetween -> multiplyDivide (ratio) -> joint.scaleX (stretch)
        multiplyDivide (inverse sqrt) -> joint.scaleY / scaleZ (volume)

    Expected detection: FKChain (no IK) with squash_stretch params attached.
    """
    names = ['neck_01_jnt', 'neck_02_jnt', 'neck_03_jnt']
    start_loc = 'neck_start_loc'
    end_loc   = 'neck_end_loc'

    _delete_if_exists(start_loc, end_loc, *names)
    for n in cmds.ls('neck_*') or []:
        if cmds.objExists(n):
            _delete_if_exists(n)

    cmds.select(clear=True)
    j1 = cmds.joint(name=names[0], position=(0, 15, 0))
    j2 = cmds.joint(name=names[1], position=(0, 18, 0))
    j3 = cmds.joint(name=names[2], position=(0, 21, 0))

    loc_s = cmds.spaceLocator(name=start_loc)[0]
    loc_e = cmds.spaceLocator(name=end_loc)[0]
    cmds.move(0, 15, 0, loc_s)
    cmds.move(0, 21, 0, loc_e)

    dist = cmds.createNode('distanceBetween', name='neck_distanceBetween')
    cmds.connectAttr('{}.worldPosition[0]'.format(loc_s), '{}.point1'.format(dist))
    cmds.connectAttr('{}.worldPosition[0]'.format(loc_e), '{}.point2'.format(dist))

    rest_len = cmds.getAttr('{}.distance'.format(dist))

    # Stretch ratio: current_length / rest_length -> scaleX
    ratio_md = cmds.createNode('multiplyDivide', name='neck_stretchRatio')
    cmds.setAttr('{}.operation'.format(ratio_md), 2)   # divide
    cmds.connectAttr('{}.distance'.format(dist), '{}.input1X'.format(ratio_md))
    cmds.setAttr('{}.input2X'.format(ratio_md), rest_len)

    # Volume preservation: scaleY/Z = 1 / sqrt(scaleX)  -> power node
    pow_md = cmds.createNode('multiplyDivide', name='neck_volumePow')
    cmds.setAttr('{}.operation'.format(pow_md), 3)   # power
    cmds.connectAttr('{}.outputX'.format(ratio_md), '{}.input1X'.format(pow_md))
    cmds.setAttr('{}.input2X'.format(pow_md), -0.5)  # 1/sqrt

    for jnt in (j1, j2, j3):
        cmds.connectAttr('{}.outputX'.format(ratio_md), '{}.scaleX'.format(jnt))
        cmds.connectAttr('{}.outputX'.format(pow_md),   '{}.scaleY'.format(jnt))
        cmds.connectAttr('{}.outputX'.format(pow_md),   '{}.scaleZ'.format(jnt))

    print('[TestRig] Built squash-stretch neck: {}'.format(names))
    print('[TestRig] Distance node: {}  rest_length={}'.format(dist, rest_len))
    _print_expected('neck (squash_stretch overlay)', 'FKChain + squash_stretch', names)


# ---------------------------------------------------------------------------
# Run all
# ---------------------------------------------------------------------------

def build_all_test_rigs():
    """Build every test rig in a single call (joints will share the scene)."""
    build_fk_chain_rig()
    build_ik_limb_rig()
    build_spline_ik_rig()
    build_ikfk_switch_rig()
    build_squash_stretch_rig()
    print('[TestRig] All test rigs built.')
    print('[TestRig] Validate with:')
    print('  import importlib, export_rig_manifest as m')
    print('  importlib.reload(m)')
    print('  results = m.run_detection_pipeline()')
    print('  for r in results: print(r["module_type"], r["module_name"])')
