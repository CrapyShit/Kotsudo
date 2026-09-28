"""Rebuild Maya constraints with native Control Rig constraint nodes.

The Maya exporter records, per module bone, every constraint that drives it
(``params.constraints``): its kind, the channels/axes it writes, and its
targets with weights and the animator controller each target belongs to.

This module turns that into, per record:

* one control per Maya controller (shared: a controller driving several
  bones -- or used by several modules -- is ONE control), with the Maya name,
  origin, orientation, shape, locked channels and attributes, parented to its
  Maya parent controller when that one exists in the rig;
* a null under the control when the constraint target is a node rigidly
  attached below the controller rather than the controller itself;
* the matching node, with maintain offset:

      parentConstraint -> Parent Constraint   (RigUnit_ParentConstraint)
      pointConstraint  -> Position Constraint (RigUnit_PositionConstraint)
      orientConstraint -> Rotation Constraint (RigUnit_RotationConstraint)
      scaleConstraint  -> Scale Constraint    (RigUnit_ScaleConstraint)

  Maintain offset reproduces Maya exactly at rest: the exported pose is the
  pose Maya's constraints produced, so the offset Unreal measures between
  the bone and its targets' initial transforms is Maya's own offset.

Aim constraints are reported and skipped (no up-vector data is exported yet).
"""

from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)

from . import control_shapes, graph_utils

_UNITS = {
    "parent": ("RigUnit_ParentConstraint",),
    "point": ("RigUnit_PositionConstraint",),
    "orient": ("RigUnit_RotationConstraint",),
    "scale": ("RigUnit_ScaleConstraint",),
}

FULL = ["x", "y", "z"]


def constraint_records(recipe_data):
    records = (recipe_data or {}).get("Constraints") or []
    result = []
    for record in records:
        if not isinstance(record, dict) or not record.get("bone"):
            continue
        targets = [
            t for t in (record.get("targets") or [])
            if isinstance(t, dict) and (t.get("controller") or {}).get("name")
        ]
        if targets:
            result.append(dict(record, targets=targets))
    return result


def needs_constraint_mode(records):
    """True when plain "one FK control per bone" cannot represent the rig.

    That is: any constraint other than a full single-target parent
    constraint, a bone driven by several constraints, or one controller
    driving several bones.
    """
    bones_seen = set()
    controller_bones = {}
    for record in records:
        targets = record.get("targets") or []
        channels = record.get("channels") or {}
        full_parent = (
            record.get("type") == "parent"
            and len(targets) == 1
            and sorted(channels.get("translate") or []) == FULL
            and sorted(channels.get("rotate") or []) == FULL
        )
        if not full_parent or record["bone"] in bones_seen:
            return True
        bones_seen.add(record["bone"])
        for target in targets:
            name = (target.get("controller") or {}).get("name")
            controller_bones.setdefault(name, set()).add(record["bone"])
    return any(len(bones) > 1 for bones in controller_bones.values())


def _pick_unit(kind):
    for name in _UNITS.get(kind, ()):
        unit = getattr(unreal, name, None)
        if unit is not None:
            return unit
    return None


def _insert_array_element(controller, model, array_pin):
    before = graph_utils.pin_exists(model, array_pin)
    if not before:
        return False
    try:
        controller.insert_array_pin(array_pin, -1, "")
        return True
    except Exception:
        try:
            controller.add_array_pin(array_pin, "")
            return True
        except Exception:
            return False


def _set_axes(controller, model, filter_pin, axes):
    """Set a FilterOptionPerAxis pin (bX/bY/bZ) from a list of axis letters."""
    for axis in "XYZ":
        value = "True" if axis.lower() in axes else "False"
        for pin in (f"{filter_pin}.b{axis}", f"{filter_pin}.{axis}"):
            if graph_utils.pin_exists(model, pin):
                graph_utils.set_pin_default(controller, model, pin, value)
                break


class ConstraintBuilder:
    """Builds the controls and constraint nodes of one module."""

    def __init__(self, module, recipe_data, parent_key, module_prefix, default_scale):
        self.module = module
        self.context = module.context
        self.hierarchy = self.context.hierarchy
        self.hierarchy_controller = self.context.hierarchy_controller
        self.controller = self.context.graph_controller
        self.model = self.context.model
        self.recipe_data = recipe_data
        self.parent_key = parent_key
        self.prefix = module_prefix
        self.default_scale = default_scale
        self.controls = []
        self.nodes = []

    # -- controls ---------------------------------------------------------

    def _existing_control(self, maya_name):
        if not maya_name:
            return None
        key = self.context.maya_controls.get(maya_name)
        if key is not None and self.hierarchy.contains(key):
            return key
        key = graph_utils.make_key(unreal.RigElementType.CONTROL, graph_utils.sanitize_name(maya_name))
        return key if self.hierarchy.contains(key) else None

    def control_for(self, record):
        """UE control for a Maya controller record (created once)."""
        maya_name = record.get("name")
        existing = self.context.maya_controls.get(maya_name)
        if existing is not None and self.hierarchy.contains(existing):
            return existing

        parent = self._existing_control(record.get("parent_controller")) or self.parent_key
        anchor = record.get("anchor_bone") or record.get("driven_bone") or self.module.chain[0]
        placement = graph_utils.record_transform(self.hierarchy, record, anchor, label=maya_name)
        name = self.context.control_name(record, f"{self.prefix}_{graph_utils.sanitize_name(maya_name)}")
        color = graph_utils.record_color(record, unreal.LinearColor(1.0, 0.65, 0.1, 1.0))
        shape_name, shape_rotation, shape_scale = control_shapes.resolve_control_shape(
            self.context.rig, self.recipe_data, record,
            graph_utils.get_transform_rotation(placement),
            "Circle_Thick", self.default_scale,
        )
        key = graph_utils.create_control(
            self.hierarchy, self.hierarchy_controller, parent, name,
            graph_utils.transform_to_location(placement), color, shape_scale,
            shape_name=shape_name, shape_rotation=shape_rotation,
            global_transform=placement, locked_channels=record.get("locked_channels"),
        )
        graph_utils.attach_record_attributes(
            self.hierarchy, self.hierarchy_controller, key, record, name,
            graph_utils.transform_to_location(placement), color,
        )
        self.context.maya_controls[maya_name] = key
        self.controls.append(name)
        return key

    def target_item(self, target):
        """(type, name) of the constraint parent for one target entry."""
        control_key = self.control_for(target["controller"])
        sub = target.get("target")
        if not sub:
            return "Control", str(control_key.name)
        placement = graph_utils.record_transform(
            self.hierarchy, sub, sub.get("anchor_bone") or self.module.chain[0],
            label=sub.get("name"),
        )
        null_name = f"{self.prefix}_{graph_utils.sanitize_name(sub.get('name'))}_Tgt"
        created = graph_utils.create_offset_driver(
            self.hierarchy, self.hierarchy_controller, control_key, null_name, placement
        )
        if created:
            return "Null", created
        return "Control", str(control_key.name)

    # -- nodes ------------------------------------------------------------

    def constraint_node(self, index, record, exec_tail, x_origin):
        kind = record.get("type")
        unit = _pick_unit(kind)
        if unit is None:
            graph_utils._log_warning(
                f"{self.module.name}: {kind} constraint '{record.get('constraint')}' on "
                f"'{record['bone']}' has no Control Rig equivalent here; skipped."
            )
            return exec_tail

        node = f"{self.prefix}_{graph_utils.sanitize_name(record['bone'])}_{kind.capitalize()}Con{index:02d}"
        graph_utils.create_unit_node(
            self.controller, self.model, node, unit,
            unreal.Vector2D(x_origin + 520, 160 + index * 260),
        )
        graph_utils.set_key_pin(self.controller, self.model, node, ["Child"], "Bone", record["bone"])
        graph_utils.set_any_pin(self.controller, self.model, node, ["bMaintainOffset", "MaintainOffset"], "True")
        graph_utils.set_any_pin(self.controller, self.model, node, ["Weight"], "1.0")

        channels = record.get("channels") or {}
        if kind == "parent":
            _set_axes(self.controller, self.model, f"{node}.Filter.TranslationFilter", channels.get("translate") or [])
            _set_axes(self.controller, self.model, f"{node}.Filter.RotationFilter", channels.get("rotate") or [])
            _set_axes(self.controller, self.model, f"{node}.Filter.ScaleFilter", [])
        else:
            group = {"point": "translate", "orient": "rotate", "scale": "scale"}[kind]
            _set_axes(self.controller, self.model, f"{node}.Filter", channels.get(group) or [])

        wired = 0
        for target in record["targets"]:
            item_type, item_name = self.target_item(target)
            if not _insert_array_element(self.controller, self.model, f"{node}.Parents"):
                break
            base = f"{node}.Parents.{wired}"
            graph_utils.set_any_pin(self.controller, self.model, base, ["Item.Type"], item_type)
            graph_utils.set_any_pin(self.controller, self.model, base, ["Item.Name"], item_name)
            graph_utils.set_any_pin(self.controller, self.model, base, ["Weight"], str(float(target.get("weight", 1.0))))
            wired += 1
        if wired == 0:
            graph_utils._log_warning(
                f"{self.module.name}: could not wire any target into '{node}' "
                "(Parents pin not found in this engine build)."
            )

        graph_utils.connect_pins(
            self.controller, self.model,
            f"{exec_tail}.ExecuteContext" if graph_utils.pin_exists(self.model, f"{exec_tail}.ExecuteContext") else f"{exec_tail}.Execute",
            f"{node}.ExecuteContext" if graph_utils.pin_exists(self.model, f"{node}.ExecuteContext") else f"{node}.Execute",
        )
        self.nodes.append(node)
        return node

    def build(self, records, exec_tail, x_origin):
        # Controls first, Maya parents before their children, so each control
        # can be parented to its Maya parent controller.
        pending = {}
        for record in records:
            for target in record["targets"]:
                controller_record = target.get("controller") or {}
                pending.setdefault(controller_record.get("name"), controller_record)
        while pending:
            ready = [
                name for name, rec in pending.items()
                if rec.get("parent_controller") not in pending
            ] or list(pending)[:1]   # cycle guard
            for name in ready:
                self.control_for(pending.pop(name))
        for index, record in enumerate(records):
            exec_tail = self.constraint_node(index, record, exec_tail, x_origin)
        return exec_tail
