import maya.cmds as cmds


def average_world_position(items):
    """Return average world position of given DAG items or components.
    Falls back to origin if nothing valid is provided.
    """
    if not items:
        return [0.0, 0.0, 0.0]

    total = [0.0, 0.0, 0.0]
    count = 0
    for it in items:
        pos = None
        try:
            pos = cmds.xform(it, q=True, ws=True, t=True)
        except Exception:
            try:
                pos = cmds.pointPosition(it, w=True)
            except Exception:
                pos = None
        if pos is not None:
            total[0] += pos[0]
            total[1] += pos[1]
            total[2] += pos[2]
            count += 1

    if count == 0:
        return [0.0, 0.0, 0.0]
    return [total[0] / count, total[1] / count, total[2] / count]


class LocatorBuilder:
    def __init__(self, localS=(1.0, 1.5, 1.0)):
        self.localS = localS

    def create_locator_at_selection_center(self):
        sel = cmds.ls(sl=True, fl=True) or []
        center_pos = average_world_position(sel)

        locator = cmds.spaceLocator(name='center_LOC#')[0]
        # Set localScale components individually for reliability
        cmds.setAttr(locator + '.localScaleX', self.localS[0])
        cmds.setAttr(locator + '.localScaleY', self.localS[1])
        cmds.setAttr(locator + '.localScaleZ', self.localS[2])
        cmds.xform(locator, ws=True, t=center_pos)
        print('Locator created at:', center_pos, '->', locator)
        return locator


class JointControlBuilder:
    def __init__(self, ctrl_radius=1.0):
        self.ctrl_radius = float(ctrl_radius)

    def ctrlbuild(self, position):
        cmds.select(clear=True)
        basejoint = cmds.joint(name='basejoint#', p=tuple(position), rad=1.0)
        cmds.setAttr(basejoint + '.drawStyle', 2)

        circle = cmds.circle(n='center_CTRL#', nr=(0, 1, 0), r=self.ctrl_radius, ch=False)[0]
        shapes = cmds.listRelatives(circle, s=True, f=True) or []
        if shapes:
            cmds.parent(shapes, basejoint, add=True, shape=True)
        cmds.delete(circle)
        print('Joint+control created at:', position, '->', basejoint)
        return basejoint


# Run
locator = LocatorBuilder().create_locator_at_selection_center()
locpos = cmds.xform(locator, q=True, ws=True, t=True)
JointControlBuilder(ctrl_radius=1.0).ctrlbuild(position=locpos)
