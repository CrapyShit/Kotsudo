from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)

from .. import graph_utils
from .rig_module import RigModule

# ---------------------------------------------------------------------------
# Unit discovery
#
# NOTE: an earlier version of this module looked up a
# "/ControlRigSpline/SplineFunctionLibrary/SplineFunctionLibrary" asset and
# called a function named "SplineIK" on it. That asset/function does not
# exist in stock Control Rig -- it silently failed to load every time,
# meaning the "native" path was never actually taken and every build fell
# through to the distributed-FK fallback below. Control Rig's real spline
# pipeline is two native nodes, confirmed against Epic's own documentation
# and the UE5 Python API reference:
#
#   1. "Spline From Points"          -> builds a spline from an array of
#                                        translation points (data-only node,
#                                        no exec pin)
#   2. "Fit Chain on Spline Curve"   -> RigUnit_FitChainToSplineCurveItemArray
#                                        (confirmed class name+properties),
#                                        aligns a bone chain to that spline
#                                        (mutable node, has an exec pin)
#
# This module now builds that real two-node pipeline. The class name for
# node #1 is NOT confirmed against the Python API docs (Epic's page for it
# didn't resolve), so it's discovered defensively the same way the rest of
# this file already discovers ambiguous units, with a documented candidate
# list and a broad dir(unreal) scan as a last resort.
# ---------------------------------------------------------------------------

_SPLINE_FROM_POINTS_CANDIDATES = [
    "RigUnit_SplineFromPoints",
    "RigUnit_ControlRigSplineFromPoints",
    "RigUnit_MakeSplineFromPoints",
]

# Confirmed via Epic's UE5 Python API reference (RigUnit_FitChainToSplineCurve
# / RigUnit_FitChainToSplineCurveItemArray docs). Prefer the ItemArray variant
# since it takes a plain Array[RigElementKey] for `items`, matching this
# module's data (a flat chain of bone names) -- the non-ItemArray variant
# wants an FRigElementKeyCollection, which needs an extra conversion node.
_FIT_CHAIN_CANDIDATES = [
    "RigUnit_FitChainToSplineCurveItemArray",
    "RigUnit_FitChainToSplineCurve",
]


def _pick_spline_from_points_unit():
    """Return the "Spline From Points" unit struct, or None for the FK fallback."""
    for module_name in ("ControlRig", "ControlRigDeveloper", "ControlRigSpline"):
        try:
            unreal.load_module(module_name)
        except Exception:
            pass

    for candidate in _SPLINE_FROM_POINTS_CANDIDATES:
        if hasattr(unreal, candidate):
            return getattr(unreal, candidate)

    # Broad scan: any RigUnit_ containing both "Spline" and "Points", that
    # isn't the "Set Spline Points" mutator (different node, mutates an
    # existing spline rather than building one).
    for attr in dir(unreal):
        if (attr.startswith("RigUnit_") and "Spline" in attr and "Points" in attr
                and "Set" not in attr):
            if hasattr(unreal, "log"):
                unreal.log(f"[SplineIKModule] Using Spline-From-Points unit from broad scan: {attr}.")
            return getattr(unreal, attr)

    return None


def _pick_fit_chain_unit():
    """Return the "Fit Chain on Spline Curve" unit struct, or None for the FK fallback."""
    for candidate in _FIT_CHAIN_CANDIDATES:
        if hasattr(unreal, candidate):
            return getattr(unreal, candidate)
    return None


# ---------------------------------------------------------------------------
# Arc-length curve helpers (control placement along the chain -- unchanged,
# this logic was already correct and is independent of which solver node
# ends up consuming the resulting positions)
# ---------------------------------------------------------------------------

def _compute_arc_lengths(positions):
    """Return cumulative arc-length list (same length as *positions*, starts at 0)."""
    arc = [0.0]
    for i in range(1, len(positions)):
        seg = graph_utils.vector_sub(positions[i], positions[i - 1])
        arc.append(arc[-1] + graph_utils.vector_length(seg))
    return arc


def _sample_arc_position(positions, arc_lengths, target_dist):
    """Linearly interpolate a world position at *target_dist* along the arc."""
    target_dist = max(0.0, min(arc_lengths[-1], target_dist))
    for i in range(1, len(arc_lengths)):
        if arc_lengths[i] >= target_dist - 1e-6:
            t_local = (
                (target_dist - arc_lengths[i - 1]) / (arc_lengths[i] - arc_lengths[i - 1])
                if arc_lengths[i] > arc_lengths[i - 1]
                else 0.0
            )
            a = positions[i - 1]
            b = positions[i]
            return graph_utils.vector_add(
                a, graph_utils.vector_scale(graph_utils.vector_sub(b, a), t_local)
            )
    return positions[-1]


# ---------------------------------------------------------------------------
# Array-pin helpers
# ---------------------------------------------------------------------------

def _find_pin_among(model, node_name, candidates):
    """Return the first candidate sub-pin path that exists on the node, or None."""
    for candidate in candidates:
        if graph_utils.pin_exists(model, f"{node_name}.{candidate}"):
            return candidate
    return None


def _insert_array_pin(controller, node_name, array_subpin):
    """Append one element to an array pin. Returns True on success."""
    full_pin = f"{node_name}.{array_subpin}"
    try:
        controller.insert_array_pin(full_pin, -1, "")
        return True
    except Exception:
        return False


def _populate_key_array(controller, model, node_name, array_pin, element_type, names):
    """Populate an array of RigElementKey entries (Type + Name) on a node."""
    if not graph_utils.pin_exists(model, f"{node_name}.{array_pin}"):
        return False
    for i, name in enumerate(names):
        _insert_array_pin(controller, node_name, array_pin)
        base = f"{node_name}.{array_pin}.{i}"
        if graph_utils.pin_exists(model, f"{base}.Type"):
            controller.set_pin_default_value(f"{base}.Type", element_type, True)
        if graph_utils.pin_exists(model, f"{base}.Name"):
            controller.set_pin_default_value(f"{base}.Name", name, True)
    return True


def _populate_vector_array_from_pins(controller, model, node_name, array_pin, source_pins):
    """Populate an array-of-Vector pin by CONNECTING each element to a live
    source pin (e.g. a control's Transform.Translation output), rather than
    setting a static default. This is what "Points" on Spline From Points
    needs -- the points must track the controls live in the viewport, not
    be frozen at build time.
    """
    if not graph_utils.pin_exists(model, f"{node_name}.{array_pin}"):
        return False
    for i, source_pin in enumerate(source_pins):
        _insert_array_pin(controller, node_name, array_pin)
        target_pin = f"{node_name}.{array_pin}.{i}"
        graph_utils.connect_pins(controller, model, source_pin, target_pin)
    return True


_AXIS_VECTORS = {
    "X": (1.0, 0.0, 0.0), "-X": (-1.0, 0.0, 0.0),
    "Y": (0.0, 1.0, 0.0), "-Y": (0.0, -1.0, 0.0),
    "Z": (0.0, 0.0, 1.0), "-Z": (0.0, 0.0, -1.0),
}


def _axis_string_to_vector_str(axis_name, default="X"):
    """Convert an "X"/"-Y"/"Z" style axis string into a UE Vector literal
    string suitable for set_pin_default_value on a Vector pin.
    """
    key = str(axis_name or default).upper()
    x, y, z = _AXIS_VECTORS.get(key, _AXIS_VECTORS[default])
    return f"(X={x},Y={y},Z={z})"


def _pick_get_length_of_spline_unit():
    """Return the "Get Length Of Spline" unit struct, or None if unavailable."""
    for candidate in ("RigUnit_GetLengthOfSpline", "RigUnit_SplineLength", "RigUnit_GetSplineLength"):
        if hasattr(unreal, candidate):
            return getattr(unreal, candidate)
    for attr in dir(unreal):
        if attr.startswith("RigUnit_") and "Spline" in attr and "Length" in attr:
            if hasattr(unreal, "log"):
                unreal.log(f"[SplineIKModule] Using Get-Length-Of-Spline unit from broad scan: {attr}.")
            return getattr(unreal, attr)
    return None


def _pick_math_unit(candidates):
    for candidate in candidates:
        if hasattr(unreal, candidate):
            return getattr(unreal, candidate)
    return None


def _perpendicular_axes(primary_axis):
    """Return the two axis letters NOT used as the primary (bone-length) axis."""
    key = str(primary_axis or "X").upper().lstrip("-")
    return [axis for axis in ("X", "Y", "Z") if axis != key]


# ---------------------------------------------------------------------------
# Distributed-FK fallback (used when neither native spline unit is available)
# ---------------------------------------------------------------------------

def _build_fallback_distributed_fk(
    controller, model, module_prefix, context, chain, controls, x_origin, forwards_solve
):
    """Drive the bone chain from the spline controls without native spline nodes.

    Per-bone strategy (fixes mesh morphing caused by identity-rotation controls):
      1. ``RigUnit_GetTransform`` (bInitial=True) -- captures the bone's bind-pose
         global rotation so it is never overwritten.
      2. ``RigUnit_MathVectorLerp`` -- interpolates ONLY the world-space position
         between the two bracketing spline controls.
      3. ``RigUnit_SetTransform`` -- applies the lerped position to
         ``Value.Translation`` and pipes the initial rotation into
         ``Value.Rotation``, leaving scale at its default (1,1,1).

    This keeps skinning intact on meshes with non-trivial joint orientations.
    """
    num_controls = len(controls)
    num_bones = len(chain)
    nodes = []

    # Discover optional units (graceful degradation if absent).
    vector_lerp_unit = None
    for candidate in ("RigUnit_MathVectorLerp", "RigUnit_MathVectorInterpolate", "RigUnit_MathVectorMix"):
        if hasattr(unreal, candidate):
            vector_lerp_unit = getattr(unreal, candidate)
            break

    get_transform_unit = None
    for candidate in ("RigUnit_GetTransform", "RigUnit_GetBoneTransform"):
        if hasattr(unreal, candidate):
            get_transform_unit = getattr(unreal, candidate)
            break

    # One GetControlTransform node per spline control.
    get_ctrl_nodes = []
    for i, ctrl_name in enumerate(controls):
        node_name = f"{module_prefix}_GetSpCtrl{i:02d}"
        graph_utils.create_unit_node(
            controller, model, node_name,
            unreal.RigUnit_GetControlTransform,
            unreal.Vector2D(x_origin, 80 + i * 160),
        )
        graph_utils.set_pin_default(controller, model, f"{node_name}.Control", ctrl_name)
        graph_utils.set_pin_default(controller, model, f"{node_name}.Space", "GlobalSpace")
        get_ctrl_nodes.append(node_name)
        nodes.append(node_name)

    prev_exec = context.get_exec_tail() or forwards_solve

    for bi, bone_name in enumerate(chain):
        t = bi / (num_bones - 1) if num_bones > 1 else 0.0
        ctrl_lo = max(0, min(num_controls - 2, int(t * (num_controls - 1))))
        ctrl_hi = ctrl_lo + 1
        local_alpha = round(t * (num_controls - 1) - ctrl_lo, 6)
        safe_bone = graph_utils.sanitize_name(bone_name)
        col = x_origin + 400

        # --- 1. Initial bone transform (bind-pose rotation) ---
        get_init_node = None
        if get_transform_unit is not None:
            get_init_node = f"{module_prefix}_{safe_bone}_GetInitTx"
            graph_utils.create_unit_node(
                controller, model, get_init_node, get_transform_unit,
                unreal.Vector2D(col, 80 + bi * 220),
            )
            graph_utils.set_key_pin(controller, model, get_init_node,
                ["Item", "Bone", "Child"], "Bone", bone_name)
            graph_utils.set_any_pin(controller, model, get_init_node, ["Space"], "GlobalSpace")
            graph_utils.set_any_pin(controller, model, get_init_node,
                ["bInitial", "Initial", "initial"], "True")
            nodes.append(get_init_node)

        # --- 2. Lerp translations between the two bracketing controls ---
        pos_pin = None
        if vector_lerp_unit is not None:
            lerp_node = f"{module_prefix}_{safe_bone}_PosLerp"
            graph_utils.create_unit_node(
                controller, model, lerp_node, vector_lerp_unit,
                unreal.Vector2D(col + 280, 80 + bi * 220),
            )
            # Connect translation sub-pins from GetControlTransform nodes.
            graph_utils.connect_pins(controller, model,
                f"{get_ctrl_nodes[ctrl_lo]}.Transform.Translation", f"{lerp_node}.A")
            graph_utils.connect_pins(controller, model,
                f"{get_ctrl_nodes[ctrl_hi]}.Transform.Translation", f"{lerp_node}.B")
            graph_utils.set_any_pin(controller, model, lerp_node,
                ["T", "Alpha", "Ratio", "W"], str(local_alpha))
            nodes.append(lerp_node)
            result_sub = _find_pin_among(model, lerp_node, ["Result", "Value", "ReturnValue"])
            pos_pin = f"{lerp_node}.{result_sub}" if result_sub else None
        else:
            # No lerp unit: snap to nearest control's translation.
            nearest = max(0, min(num_controls - 1, round(t * (num_controls - 1))))
            pos_pin = f"{get_ctrl_nodes[nearest]}.Transform.Translation"

        # --- 3. SetTransform: translation from lerp, rotation from bind pose ---
        set_node = f"{module_prefix}_{safe_bone}_SetSpIK"
        graph_utils.create_unit_node(
            controller, model, set_node, unreal.RigUnit_SetTransform,
            unreal.Vector2D(col + 580, 80 + bi * 220),
        )
        graph_utils.set_key_pin(controller, model, set_node,
            ["Item", "Bone", "Child"], "Bone", bone_name)
        graph_utils.set_any_pin(controller, model, set_node, ["Space"], "GlobalSpace")
        graph_utils.set_any_pin(controller, model, set_node, ["Initial"], "False")
        graph_utils.set_any_pin(controller, model, set_node, ["Weight"], "1.0")
        graph_utils.set_any_pin(controller, model, set_node,
            ["bPropagateToChildren", "PropagateToChildren", "propagate_to_children"], "False")

        # Connect position (translation only -- do NOT connect the full transform).
        if pos_pin:
            if not graph_utils.connect_pins(controller, model, pos_pin, f"{set_node}.Value.Translation"):
                graph_utils.connect_pins(controller, model, pos_pin, f"{set_node}.Transform.Translation")

        # Connect bind-pose rotation to preserve skin-friendly joint orientation.
        if get_init_node:
            for rot_out in ("Transform.Rotation", "GlobalTransform.Rotation", "Result.Rotation"):
                if graph_utils.pin_exists(model, f"{get_init_node}.{rot_out}"):
                    if not graph_utils.connect_pins(controller, model,
                            f"{get_init_node}.{rot_out}", f"{set_node}.Value.Rotation"):
                        graph_utils.connect_pins(controller, model,
                            f"{get_init_node}.{rot_out}", f"{set_node}.Transform.Rotation")
                    break

        # Wire execution.
        source_exec = (
            f"{prev_exec}.ExecuteContext"
            if graph_utils.pin_exists(model, f"{prev_exec}.ExecuteContext")
            else f"{prev_exec}.Execute"
        )
        target_exec = (
            f"{set_node}.ExecuteContext"
            if graph_utils.pin_exists(model, f"{set_node}.ExecuteContext")
            else f"{set_node}.Execute"
        )
        graph_utils.connect_pins(controller, model, source_exec, target_exec)
        prev_exec = set_node
        nodes.append(set_node)

    return nodes, prev_exec


# ---------------------------------------------------------------------------
# Module
# ---------------------------------------------------------------------------

class SplineIKModule(RigModule):
    """Spline IK module for long bone chains (spine, tail, tentacle, etc.).

    Distributes *NumControls* controls evenly along the chain using arc-length
    parameterisation, feeds their live translations into a native "Spline
    From Points" node, then fits the bone chain to the resulting spline with
    a native "Fit Chain on Spline Curve" node (``RigUnit_FitChainToSplineCurveItemArray``).

    If neither native unit is available in this engine build (ControlRig
    Spline features not present), falls back to a distributed-FK
    approximation that lerps bone positions between bracketing controls
    while preserving bind-pose rotations.

    Recipe fields
    -------------
    NumControls : int  (default 4)
        Number of spline control points. Must be >= 2 (Control Rig itself
        requires >= 4 points to build a spline; if NumControls < 4 the
        native path will fail its own validation and this module falls
        back to distributed-FK automatically).
    ControlScale : float  (default 1.0)
        Uniform scale multiplier for all control shapes.
    StretchEnabled : bool  (default True)
        Whether the chain should stretch/compress to fully reach the
        spline's length (Alignment = Stretched) or hold bone lengths fixed
        and only bend (Alignment = Front).
    PrimaryAxis : str  (default "X")
        The major axis of each bone that runs along the spline direction.
        One of "X", "Y", "Z", "-X", "-Y", "-Z".
    UsePoleVector : bool  (default False)
        If true, creates an additional pole-vector control and wires the
        chain's SecondaryAxis + PoleVectorPosition to it, giving explicit
        roll/twist-plane control matching a Maya-style up-vector setup.
        If false, SecondaryAxis is left at (0,0,0), which disables
        secondary-axis alignment per the node's own documented behavior.
    SecondaryAxis : str  (default "Y")
        Only used when UsePoleVector is true -- the minor/up axis aligned
        toward the pole vector control.
    SamplingPrecision : int  (default 16, clamped to 64 by the node itself)
        Number of samples used when fitting the chain to the curve.
    SquashEnabled : bool  (default False)
        If true, adds volume-preserving perpendicular-axis scaling on top
        of Fit Chain's length stretching -- bones get thinner as the
        spline stretches longer than rest length, thicker as it compresses
        shorter. This is the piece Control Rig has no native node for
        (Maya riggers normally hand-build it from curveInfo.arcLength);
        requires a "Get Length Of Spline" unit in this engine build, and
        is skipped with a log message if that unit isn't found. Native
        path only -- not applied in the distributed-FK fallback.
    SquashAmount : float 0..1  (default 1.0)
        Blends between no squash (0.0) and full volume-preserving squash
        (1.0). Only relevant when SquashEnabled is true.

    Attach points
    -------------
    root              – first bone in the chain
    tip               – last bone in the chain
    spline_root_ctrl  – first spline control (index 0)
    spline_tip_ctrl   – last spline control (index N-1)
    spline_mid_ctrl   – middle spline control (index N//2)
    pole_vector_ctrl  – pole vector control (only present if UsePoleVector)
    """

    module_type = "SplineIK"

    @classmethod
    def describe_contract(cls):
        return {
            "module_type": cls.module_type,
            "chain": {
                "min_length": 5,
                "max_length": None,
                "exact_length": None,
                "roles": [],
            },
            "required_metadata": ["ModuleType", "ModuleName"],
            "required_recipe_fields": ["NumControls"],
            "attachment_points": [
                "root", "tip",
                "spline_root_ctrl", "spline_tip_ctrl", "spline_mid_ctrl",
            ],
            "build_products": ["controls", "nodes", "attach_points"],
        }

    def validate(self):
        if len(self.chain) < 5:
            raise RuntimeError(
                f"SplineIK module '{self.name}' requires at least 5 bones, "
                f"got {len(self.chain)}."
            )
        if not self.context:
            raise RuntimeError(
                f"SplineIK module '{self.name}' requires a valid rig context."
            )

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self):
        self.validate()

        if self.logger:
            self.logger.push(f"[SplineIKModule] Building {self.name}")

        recipe_data = self.read_recipe()
        hierarchy = self.context.hierarchy
        hierarchy_controller = self.context.hierarchy_controller
        controller = self.context.graph_controller
        model = self.context.model
        forwards_solve = graph_utils.find_forwards_solve_node_name(model)

        if not forwards_solve:
            raise RuntimeError("No Forwards Solve node found in the Control Rig graph.")

        num_controls = max(2, int(recipe_data.get("NumControls") or 4))
        module_prefix = graph_utils.sanitize_name(self.name)
        scale_multiplier = float(recipe_data.get("ControlScale") or 1.0)
        control_scale = graph_utils.compute_chain_scale(
            hierarchy, self.chain, fraction=0.35, multiplier=scale_multiplier
        )
        stretch_enabled = bool(recipe_data.get("StretchEnabled", True))
        primary_axis = recipe_data.get("PrimaryAxis") or "X"
        use_pole_vector = bool(recipe_data.get("UsePoleVector", False))
        secondary_axis = recipe_data.get("SecondaryAxis") or "Y"
        sampling_precision = int(recipe_data.get("SamplingPrecision") or 16)
        squash_enabled = bool(recipe_data.get("SquashEnabled", False))
        squash_amount = max(0.0, min(1.0, float(recipe_data.get("SquashAmount") or 1.0)))

        parent_key = (
            self.context.get_parent_control_key(self.parent_module_name, self.parent_attach_point)
            or graph_utils.get_world_parent_key(hierarchy, hierarchy_controller)
        )

        # ------------------------------------------------------------------
        # 1. Compute arc-length-distributed control positions along the chain
        # ------------------------------------------------------------------
        chain_positions = [
            graph_utils.get_bone_global_position(hierarchy, bone)
            for bone in self.chain
        ]
        arc_lengths = _compute_arc_lengths(chain_positions)
        total_arc = arc_lengths[-1]

        ctrl_positions = []
        for i in range(num_controls):
            t = i / (num_controls - 1) if num_controls > 1 else 0.0
            ctrl_positions.append(
                _sample_arc_position(chain_positions, arc_lengths, t * total_arc)
            )

        # ------------------------------------------------------------------
        # 2. Create hierarchy controls
        # ------------------------------------------------------------------
        controls = []
        attach_points = {
            "root": self.chain[0],
            "tip": self.chain[-1],
        }

        for i, position in enumerate(ctrl_positions):
            ctrl_name = f"{module_prefix}_SplineCtrl{i:02d}_CTRL"
            graph_utils.create_control(
                hierarchy,
                hierarchy_controller,
                parent_key,
                ctrl_name,
                position,
                unreal.LinearColor(0.2, 0.8, 1.0, 1.0),
                (control_scale, control_scale, control_scale),
                shape_name="Circle_Thick",
            )
            controls.append(ctrl_name)

            if i == 0:
                attach_points["spline_root_ctrl"] = ctrl_name
            if i == num_controls - 1:
                attach_points["spline_tip_ctrl"] = ctrl_name
            if i == num_controls // 2:
                attach_points["spline_mid_ctrl"] = ctrl_name

        # Optional pole-vector control, offset from the chain midpoint.
        pole_ctrl = None
        if use_pole_vector:
            mid_pos = ctrl_positions[num_controls // 2]
            axis_vec = _AXIS_VECTORS.get(str(secondary_axis).upper(), _AXIS_VECTORS["Y"])
            offset = graph_utils.vector_scale(axis_vec, max(total_arc * 0.5, 1.0))
            pole_pos = graph_utils.vector_add(mid_pos, offset)
            pole_ctrl = f"{module_prefix}_PoleVector_CTRL"
            graph_utils.create_control(
                hierarchy, hierarchy_controller,
                parent_key, pole_ctrl, pole_pos,
                unreal.LinearColor(1.0, 0.9, 0.1, 1.0),
                (control_scale * 0.6, control_scale * 0.6, control_scale * 0.6),
                shape_name="Diamond_Thick",
            )
            attach_points["pole_vector_ctrl"] = pole_ctrl

        # ------------------------------------------------------------------
        # 3. Build graph nodes
        # ------------------------------------------------------------------
        x_origin = self.context.claim_module_column()
        spline_points_node = f"{module_prefix}_SplineFromPoints"
        fit_chain_node = f"{module_prefix}_FitChainToSpline"
        native_built = False
        all_nodes = []
        primary_node = None

        spline_points_unit = _pick_spline_from_points_unit()
        fit_chain_unit = _pick_fit_chain_unit()

        if spline_points_unit is not None and fit_chain_unit is not None and num_controls >= 4:
            # ----- Node 1: Spline From Points (data-only, no exec pin) -----
            graph_utils.create_unit_node(
                controller, model, spline_points_node, spline_points_unit,
                unreal.Vector2D(x_origin, 100),
            )

            get_ctrl_nodes = []
            for i, ctrl_name in enumerate(controls):
                get_node = f"{module_prefix}_GetSpCtrl{i:02d}"
                graph_utils.create_unit_node(
                    controller, model, get_node,
                    unreal.RigUnit_GetControlTransform,
                    unreal.Vector2D(x_origin - 350, 80 + i * 140),
                )
                graph_utils.set_pin_default(controller, model, f"{get_node}.Control", ctrl_name)
                graph_utils.set_pin_default(controller, model, f"{get_node}.Space", "GlobalSpace")
                get_ctrl_nodes.append(get_node)
                all_nodes.append(get_node)

            points_pin = _find_pin_among(model, spline_points_node, ["Points"])
            if points_pin:
                source_pins = [f"{n}.Transform.Translation" for n in get_ctrl_nodes]
                _populate_vector_array_from_pins(
                    controller, model, spline_points_node, points_pin, source_pins
                )

            graph_utils.set_any_pin(
                controller, model, spline_points_node, ["SplineMode", "Mode"], "Bspline"
            )
            # SamplesPerSegment on Spline From Points is overridden by
            # SamplingPrecision on Fit Chain -- leave at a reasonable
            # default rather than duplicating the same knob twice.
            graph_utils.set_any_pin(
                controller, model, spline_points_node, ["SamplesPerSegment"], "16"
            )

            all_nodes.append(spline_points_node)

            # ----- Node 2: Fit Chain on Spline Curve (mutable, exec chain) -----
            graph_utils.create_unit_node(
                controller, model, fit_chain_node, fit_chain_unit,
                unreal.Vector2D(x_origin + 400, 100),
            )

            _populate_key_array(
                controller, model, fit_chain_node, "Items", "Bone", self.chain
            )

            spline_out = _find_pin_among(model, spline_points_node, ["Spline"])
            if spline_out:
                graph_utils.connect_pins(
                    controller, model,
                    f"{spline_points_node}.{spline_out}",
                    f"{fit_chain_node}.Spline",
                )

            graph_utils.set_any_pin(
                controller, model, fit_chain_node, ["Alignment"],
                "Stretched" if stretch_enabled else "Front",
            )
            graph_utils.set_any_pin(
                controller, model, fit_chain_node, ["PrimaryAxis"],
                _axis_string_to_vector_str(primary_axis, "X"),
            )

            if use_pole_vector and pole_ctrl:
                get_pole_node = f"{module_prefix}_GetPoleVec"
                graph_utils.create_unit_node(
                    controller, model, get_pole_node,
                    unreal.RigUnit_GetControlTransform,
                    unreal.Vector2D(x_origin, 300),
                )
                graph_utils.set_pin_default(controller, model, f"{get_pole_node}.Control", pole_ctrl)
                graph_utils.set_pin_default(controller, model, f"{get_pole_node}.Space", "GlobalSpace")
                all_nodes.append(get_pole_node)

                graph_utils.set_any_pin(
                    controller, model, fit_chain_node, ["SecondaryAxis"],
                    _axis_string_to_vector_str(secondary_axis, "Y"),
                )
                graph_utils.connect_pins(
                    controller, model,
                    f"{get_pole_node}.Transform.Translation",
                    f"{fit_chain_node}.PoleVectorPosition",
                )
            else:
                # (0,0,0) explicitly disables secondary-axis alignment per
                # the node's documented behavior.
                graph_utils.set_any_pin(
                    controller, model, fit_chain_node, ["SecondaryAxis"], "(X=0,Y=0,Z=0)"
                )

            graph_utils.set_any_pin(controller, model, fit_chain_node, ["Minimum"], "0.0")
            graph_utils.set_any_pin(controller, model, fit_chain_node, ["Maximum"], "1.0")
            graph_utils.set_any_pin(
                controller, model, fit_chain_node, ["SamplingPrecision"],
                str(min(64, max(1, sampling_precision))),
            )
            graph_utils.set_any_pin(controller, model, fit_chain_node, ["Weight"], "1.0")
            graph_utils.set_any_pin(
                controller, model, fit_chain_node,
                ["PropagateToChildren", "bPropagateToChildren"], "True"
            )

            exec_tail = self.context.get_exec_tail() or forwards_solve
            source_exec = (
                f"{exec_tail}.ExecuteContext"
                if graph_utils.pin_exists(model, f"{exec_tail}.ExecuteContext")
                else f"{exec_tail}.Execute"
            )
            target_exec = (
                f"{fit_chain_node}.ExecuteContext"
                if graph_utils.pin_exists(model, f"{fit_chain_node}.ExecuteContext")
                else f"{fit_chain_node}.Execute"
            )
            graph_utils.connect_pins(controller, model, source_exec, target_exec)
            self.context.set_exec_tail(fit_chain_node)
            all_nodes.append(fit_chain_node)
            primary_node = fit_chain_node
            native_built = True

            # ------------------------------------------------------------
            # Squash: volume-preserving perpendicular-axis scale, layered
            # on top of Fit Chain's output. Fit Chain's "Stretched"
            # alignment already handles bone LENGTH (translation) matching
            # the curve -- this adds the missing THICKNESS compensation
            # (Maya riggers normally build this by hand from
            # curveInfo.arcLength; there is no built-in Control Rig
            # equivalent). squash_factor = (currentLength/restLength)^-0.5,
            # blended toward 1.0 (no squash) by SquashAmount.
            # ------------------------------------------------------------
            if squash_enabled:
                squash_factor_pin = self._build_squash_factor_network(
                    controller, model, module_prefix, spline_points_node,
                    total_arc, squash_amount, x_origin,
                )
                if squash_factor_pin:
                    squash_nodes, last_exec = self._apply_squash_to_chain(
                        controller, model, module_prefix, self.chain,
                        primary_axis, squash_factor_pin, x_origin,
                        exec_start=fit_chain_node,
                    )
                    all_nodes.extend(squash_nodes)
                    self.context.set_exec_tail(last_exec)
                    primary_node = last_exec
                elif self.logger:
                    self.logger.log(
                        "[SplineIKModule] SquashEnabled=True but no "
                        "Get-Length-Of-Spline unit was found in this engine "
                        "build -- squash skipped, stretch still applied."
                    )

        if not native_built:
            # ----- Fallback: distributed-FK (native spline units unavailable,
            #       or NumControls < 4, which Control Rig's own spline
            #       system requires) -----
            if self.logger:
                reason = (
                    "NumControls must be >= 4 for native Control Rig splines"
                    if num_controls < 4
                    else "native Spline From Points / Fit Chain on Spline Curve units unavailable in this engine build"
                )
                self.logger.log(f"[SplineIKModule] Using distributed-FK fallback -- {reason}.")
            all_nodes, last_exec = _build_fallback_distributed_fk(
                controller, model, module_prefix, self.context,
                self.chain, controls, x_origin, forwards_solve,
            )
            self.context.set_exec_tail(last_exec)
            primary_node = last_exec

        if self.logger:
            self.logger.pop()

        return self.build_result(
            controls=controls + ([pole_ctrl] if pole_ctrl else []),
            nodes=all_nodes,
            attach_points=attach_points,
            outputs={
                "spline_ik_node": primary_node,
                "spline_controls": list(controls),
                "driven_bones": list(self.chain),
                "num_controls": num_controls,
                "native": native_built,
            },
            recipe_data=recipe_data,
            metadata={
                "num_controls": num_controls,
                "control_scale": recipe_data.get("ControlScale"),
                "stretch_enabled": stretch_enabled,
                "squash_enabled": squash_enabled,
                "squash_amount": squash_amount,
                "primary_axis": primary_axis,
                "use_pole_vector": use_pole_vector,
            },
        )

    # ------------------------------------------------------------------
    # Squash / stretch volume preservation
    # ------------------------------------------------------------------

    def _build_squash_factor_network(
        self, controller, model, module_prefix, spline_points_node,
        rest_length, squash_amount, x_origin,
    ):
        """Build the shared scalar math chain producing a single squash
        factor for the whole chain this frame:

            ratio  = GetLengthOfSpline(spline) / rest_length
            squash = ratio ^ -0.5                (Pow, falls back to 1/Sqrt)
            result = Lerp(1.0, squash, squash_amount)

        Returns the output pin path, or None if Get-Length-Of-Spline isn't
        available in this engine build (squash is skipped entirely in that
        case -- stretch via Fit Chain's Alignment pin is unaffected).
        """
        length_unit = _pick_get_length_of_spline_unit()
        if length_unit is None:
            return None

        col = x_origin + 1200

        length_node = f"{module_prefix}_SplineLength"
        graph_utils.create_unit_node(
            controller, model, length_node, length_unit, unreal.Vector2D(col, 400),
        )
        spline_out = _find_pin_among(model, spline_points_node, ["Spline"])
        if spline_out:
            graph_utils.connect_pins(
                controller, model, f"{spline_points_node}.{spline_out}", f"{length_node}.Spline"
            )
        length_out = _find_pin_among(model, length_node, ["Length", "ReturnValue", "Result"])
        if not length_out:
            return None

        divide_unit = _pick_math_unit(["RigUnit_MathFloatDivide", "RigVMFunction_MathFloatDivide"])
        if divide_unit is None:
            return None
        ratio_node = f"{module_prefix}_SquashRatio"
        graph_utils.create_unit_node(
            controller, model, ratio_node, divide_unit, unreal.Vector2D(col + 260, 400),
        )
        graph_utils.connect_pins(controller, model, f"{length_node}.{length_out}", f"{ratio_node}.A")
        graph_utils.set_any_pin(controller, model, ratio_node, ["B"], str(max(rest_length, 0.0001)))
        ratio_out = _find_pin_among(model, ratio_node, ["Result", "ReturnValue"]) or "Result"

        # squash = ratio ^ -0.5, preferring a direct Pow node; falls back to
        # 1 / Sqrt(ratio) if this engine build has no float Pow unit.
        squash_pin = None
        pow_unit = _pick_math_unit(["RigUnit_MathFloatPow", "RigUnit_MathFloatPower"])
        if pow_unit is not None:
            pow_node = f"{module_prefix}_SquashPow"
            graph_utils.create_unit_node(
                controller, model, pow_node, pow_unit, unreal.Vector2D(col + 520, 400),
            )
            graph_utils.connect_pins(controller, model, f"{ratio_node}.{ratio_out}", f"{pow_node}.Base")
            graph_utils.set_any_pin(controller, model, pow_node, ["Exponent"], "-0.5")
            pow_out = _find_pin_among(model, pow_node, ["Result", "ReturnValue"]) or "Result"
            squash_pin = f"{pow_node}.{pow_out}"
        else:
            sqrt_unit = _pick_math_unit(["RigUnit_MathFloatSqrt"])
            if sqrt_unit is None or divide_unit is None:
                return None
            sqrt_node = f"{module_prefix}_SquashSqrt"
            graph_utils.create_unit_node(
                controller, model, sqrt_node, sqrt_unit, unreal.Vector2D(col + 520, 400),
            )
            graph_utils.connect_pins(controller, model, f"{ratio_node}.{ratio_out}", f"{sqrt_node}.Value")
            sqrt_out = _find_pin_among(model, sqrt_node, ["Result", "ReturnValue"]) or "Result"

            inv_node = f"{module_prefix}_SquashInvert"
            graph_utils.create_unit_node(
                controller, model, inv_node, divide_unit, unreal.Vector2D(col + 780, 400),
            )
            graph_utils.set_any_pin(controller, model, inv_node, ["A"], "1.0")
            graph_utils.connect_pins(controller, model, f"{sqrt_node}.{sqrt_out}", f"{inv_node}.B")
            squash_pin = f"{inv_node}.{ratio_out}"

        lerp_unit = _pick_math_unit(["RigUnit_MathFloatLerp", "RigVMFunction_MathFloatLerp"])
        if lerp_unit is None:
            return squash_pin

        lerp_node = f"{module_prefix}_SquashBlend"
        graph_utils.create_unit_node(
            controller, model, lerp_node, lerp_unit, unreal.Vector2D(col + 1040, 400),
        )
        graph_utils.set_any_pin(controller, model, lerp_node, ["A"], "1.0")
        graph_utils.connect_pins(controller, model, squash_pin, f"{lerp_node}.B")
        graph_utils.set_any_pin(controller, model, lerp_node, ["T", "Alpha"], str(squash_amount))
        lerp_out = _find_pin_among(model, lerp_node, ["Result", "ReturnValue"]) or "Result"
        return f"{lerp_node}.{lerp_out}"

    def _apply_squash_to_chain(
        self, controller, model, module_prefix, chain, primary_axis,
        squash_factor_pin, x_origin, exec_start,
    ):
        """Per bone: read the pose Fit Chain just wrote, multiply the two
        perpendicular scale axes by squash_factor_pin, write it back.
        Translation/rotation/primary-axis scale pass through unchanged.
        """
        get_transform_unit = _pick_math_unit(["RigUnit_GetTransform", "RigUnit_GetBoneTransform"])
        mul_unit = _pick_math_unit(["RigUnit_MathFloatMultiply", "RigUnit_MathFloatMul"])
        if get_transform_unit is None or mul_unit is None:
            if self.logger:
                self.logger.log(
                    "[SplineIKModule] Squash skipped: no GetTransform/FloatMultiply "
                    "unit found in this engine build."
                )
            return [], exec_start

        perp_axes = _perpendicular_axes(primary_axis)
        nodes = []
        exec_tail = exec_start
        col = x_origin + 1800

        for i, bone_name in enumerate(chain):
            safe_bone = graph_utils.sanitize_name(bone_name)
            row = 80 + i * 160

            get_node = f"{module_prefix}_{safe_bone}_GetPostFit"
            graph_utils.create_unit_node(
                controller, model, get_node, get_transform_unit, unreal.Vector2D(col, row),
            )
            graph_utils.set_key_pin(controller, model, get_node, ["Item", "Bone", "Child"], "Bone", bone_name)
            graph_utils.set_any_pin(controller, model, get_node, ["Space"], "GlobalSpace")
            graph_utils.set_any_pin(controller, model, get_node, ["Initial", "bInitial"], "False")
            nodes.append(get_node)

            set_node = f"{module_prefix}_{safe_bone}_SetSquash"
            graph_utils.create_unit_node(
                controller, model, set_node, unreal.RigUnit_SetTransform,
                unreal.Vector2D(col + 500, row),
            )
            graph_utils.set_key_pin(controller, model, set_node, ["Item", "Bone", "Child"], "Bone", bone_name)
            graph_utils.set_any_pin(controller, model, set_node, ["Space"], "GlobalSpace")
            graph_utils.set_any_pin(controller, model, set_node, ["Initial"], "False")
            graph_utils.set_any_pin(controller, model, set_node, ["Weight"], "1.0")
            graph_utils.set_any_pin(controller, model, set_node,
                ["bPropagateToChildren", "PropagateToChildren"], "False")

            value_prefix = "Value" if graph_utils.pin_exists(model, f"{set_node}.Value.Translation") else "Transform"

            # Pass translation and rotation through unchanged.
            graph_utils.connect_pins(controller, model,
                f"{get_node}.Transform.Translation", f"{set_node}.{value_prefix}.Translation")
            graph_utils.connect_pins(controller, model,
                f"{get_node}.Transform.Rotation", f"{set_node}.{value_prefix}.Rotation")
            # Primary axis keeps whatever scale Fit Chain already computed.
            primary_letter = str(primary_axis or "X").upper().lstrip("-")
            graph_utils.connect_pins(controller, model,
                f"{get_node}.Transform.Scale3D.{primary_letter}",
                f"{set_node}.{value_prefix}.Scale3D.{primary_letter}")

            # Perpendicular axes: multiply existing scale by squash_factor.
            for axis in perp_axes:
                mul_node = f"{module_prefix}_{safe_bone}_Squash{axis}"
                graph_utils.create_unit_node(
                    controller, model, mul_node, mul_unit,
                    unreal.Vector2D(col + 250, row + (10 if axis == perp_axes[0] else 40)),
                )
                graph_utils.connect_pins(controller, model,
                    f"{get_node}.Transform.Scale3D.{axis}", f"{mul_node}.A")
                graph_utils.connect_pins(controller, model, squash_factor_pin, f"{mul_node}.B")
                mul_out = _find_pin_among(model, mul_node, ["Result", "ReturnValue"]) or "Result"
                graph_utils.connect_pins(controller, model,
                    f"{mul_node}.{mul_out}", f"{set_node}.{value_prefix}.Scale3D.{axis}")
                nodes.append(mul_node)

            graph_utils.connect_pins(controller, model,
                f"{exec_tail}.ExecuteContext" if graph_utils.pin_exists(model, f"{exec_tail}.ExecuteContext") else f"{exec_tail}.Execute",
                f"{set_node}.ExecuteContext" if graph_utils.pin_exists(model, f"{set_node}.ExecuteContext") else f"{set_node}.Execute",
            )
            exec_tail = set_node
            nodes.append(set_node)

        return nodes, exec_tail

    # ------------------------------------------------------------------
    # Recipe
    # ------------------------------------------------------------------

    def read_recipe(self):
        recipe_fields = {
            "ModuleType": None,
            "NumControls": 4,
            "ControlScale": 1.0,
            "StretchEnabled": True,
            "PrimaryAxis": "X",
            "UsePoleVector": False,
            "SecondaryAxis": "Y",
            "SamplingPrecision": 16,
            "SquashEnabled": False,
            "SquashAmount": 1.0,
        }
        fallback_names = {
            "ModuleType": ["module_type"],
            "NumControls": ["num_controls", "numcontrols", "ControlCount", "control_count"],
            "ControlScale": ["control_scale", "controlscale"],
            "StretchEnabled": ["stretch_enabled", "stretch", "Stretch"],
            "PrimaryAxis": ["primary_axis", "primaryaxis"],
            "UsePoleVector": ["use_pole_vector", "pole_vector", "PoleVector"],
            "SecondaryAxis": ["secondary_axis", "secondaryaxis"],
            "SamplingPrecision": ["sampling_precision", "samplingprecision"],
            "SquashEnabled": ["squash_enabled", "squash", "Squash", "volume_preservation"],
            "SquashAmount": ["squash_amount", "squashamount"],
        }
        return self.resolve_recipe_fields(recipe_fields, fallback_names=fallback_names)