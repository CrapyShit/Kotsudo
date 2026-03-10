import maya.cmds as cmds

def create_group_hierarchy():
    """
    Creates the base group hierarchy for the rig.
    """

    # Clean start
    if cmds.objExists("ROOT"):
        cmds.warning("ROOT already exists in the scene. Skipping creation.")
        return

    # ROOT
    root = cmds.group(empty=True, name="ROOT")

    # Main groups
    setup_grp = cmds.group(empty=True, name="SETUP", parent=root)
    skeleton_grp = cmds.group(empty=True, name="SKELETON", parent=root)
    geo_grp = cmds.group(empty=True, name="GEO", parent=root)
    util_grp = cmds.group(empty=True, name="UTIL", parent=root)

    # --- SETUP SUBGROUPS ---
    world_orig = cmds.group(empty=True, name="world_orig", parent=setup_grp)
    world_ctrl = cmds.joint(name="world_ctrl", parent=world_orig)

    local_orig = cmds.group(empty=True, name="local_orig", parent=setup_grp)
    local_ctrl = cmds.joint(name="local_ctrl", parent=local_orig)

    spine_orig = cmds.group(empty=True, name="spine_orig", parent=setup_grp)
    for i in range(5):  # spine_ctrlA ... spine_ctrlE
        cmds.joint(name=f"spine_ctrl{chr(65+i)}", parent=spine_orig if i == 0 else f"spine_ctrl{chr(64+i)}")

    arm_L_orig = cmds.group(empty=True, name="arm_L_orig", parent=setup_grp)
    cmds.joint(name="arm_L_fk_ctrl", parent=arm_L_orig)
    cmds.select(arm_L_orig)
    cmds.joint(name="arm_L_ik_ctrl", parent=arm_L_orig)

    head_orig = cmds.group(empty=True, name="head_orig", parent=setup_grp)
    cmds.joint(name="head_ctrl", parent=head_orig)

    # --- SKELETON SUBGROUPS ---
    for name in ["spine_bind", "neck_bind", "head_bind", "arm_L_bind", "arm_R_bind", "leg_L_bind", "leg_R_bind"]:
        cmds.group(empty=True, name=name, parent=skeleton_grp)

    # --- GEO ---
    cmds.group(empty=True, name="body_mesh", parent=geo_grp)

    # --- UTIL ---
    cmds.group(empty=True, name="math_nodes_grp", parent=util_grp)
    cmds.group(empty=True, name="rig_nodes_grp", parent=util_grp)

    cmds.select(clear=True)
    print("✅ Base rig hierarchy created successfully!")

create_group_hierarchy()
