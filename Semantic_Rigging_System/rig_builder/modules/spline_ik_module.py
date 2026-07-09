from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)

from .. import graph_utils
from .rig_module import RigModule

# ---------------------------------------------------------------------------
# Unit discovery
# ---------------------------------------------------------------------------

# Explicit candidates checked before broad scan (in priority order).
_SPLINE_IK_UNIT_CANDIDATES = [
    "RigUnit_FitChainToSpline",       # ControlRigSpline plugin UE5.x – preferred
    "RigUnit_SplineIKChain",          # older / alternative variants
    "RigUnit_SplineIKChainPerItem",
    "RigUnit_SplineIK",
    "RigUnit_ControlRigSplineIK",
]

# For the broad scan: keywords that identify chain-solver units, in priority order.
# Pure utility nodes (ClosestParameter, DrawControl, TransformFrom …) are excluded.
_SPLINE_CHAIN_KEYWORDS = ["FitChain", "SplineIKChain", "SplineChain", "IKSpline", "ChainToSpline"]
_SPLINE_CHAIN_EXCLUDES = [
    "ClosestParameter", "DrawControl", "TangentFrom",
    "TransformFrom", "SplineBase", "FromPoints", "FromTransforms",
]


def _pick_spline_ik_unit():
    """Return the best available spline-chain-solver unit, or None for the FK fallback."""
    for module_name in ("ControlRig", "ControlRigDeveloper", "ControlRigSpline"):
        try:
            unreal.load_module(module_name)
        except Exception:
            pass

    # Direct lookup first (fastest, most explicit).
    for candidate in _SPLINE_IK_UNIT_CANDIDATES:
        if hasattr(unreal, candidate):
            return getattr(unreal, candidate)

    # Broad scan: prefer chain-solver keywords, skip utility-only nodes.
    all_spline = [
        attr for attr in dir(unreal)
        if attr.startswith("RigUnit_") and "Spline" in attr
        and not any(ex in attr for ex in _SPLINE_CHAIN_EXCLUDES)
    ]
    for keyword in _SPLINE_CHAIN_KEYWORDS:
        for attr in all_spline:
            if keyword in attr:
                if hasattr(unreal, "log"):
                    unreal.log(f"[SplineIKModule] Using spline chain unit from broad scan: {attr}.")
                return getattr(unreal, attr)

    if hasattr(unreal, "log_warning"):
        unreal.log_warning(
            "[SplineIKModule] No spline chain solver found. "
            "Go to Edit -> Plugins, search 'Control Rig Spline', enable and restart. "
            "Using distributed-FK fallback."
        )
    return None


# ---------------------------------------------------------------------------
# Arc-length curve helpers
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
    """Append one element to an array pin. Returns the new index or None on failure."""
    full_pin = f"{node_name}.{array_subpin}"
    try:
        return controller.insert_array_pin(full_pin, -1, "")
    except Exception:
        return None


def _populate_items_array(controller, model, node_name, bone_names):
    """Populate the Items (driven-bone chain) array on the SplineIK node.

    Tries multiple pin-name layouts that exist across UE5 releases:
    - ``Items``           – plain ``TArray<FRigElementKey>``
    - ``Items.Keys``      – ``FRigElementKeyCollection`` wrapper
    - ``Chain``           – alternative pin name used in some variants
    """
    items_pin = _find_pin_among(model, node_name, ["Items", "Items.Keys", "Chain"])
    if not items_pin:
        return  # Best-effort; node may auto-populate from hierarchy in some builds.

    for i, bone_name in enumerate(bone_names):
        _insert_array_pin(controller, node_name, items_pin)
        base = f"{node_name}.{items_pin}.{i}"
        # Type pin
        for type_sub in ["Type", "type"]:
            pin = f"{base}.{type_sub}"
            if graph_utils.pin_exists(model, pin):
                controller.set_pin_default_value(pin, "Bone", True)
                break
        # Name pin
        for name_sub in ["Name", "name"]:
            pin = f"{base}.{name_sub}"
            if graph_utils.pin_exists(model, pin):
                controller.set_pin_default_value(pin, bone_name, True)
                break


def _populate_controls_array(controller, model, node_name, ctrl_names):
    """Populate the Controls (spline-point) array on the SplineIK node.

    Each element maps a control to a normalised T position (0..1) along the
    spline.  Supports these per-element layouts:

    - ``Controls[i].Control.Type / Name`` + ``Controls[i].T``
      (standard FRigUnit_SplineIKChain_Control struct)
    - ``Controls[i].Type / Name`` + ``Controls[i].T``
      (flat variant in some builds)
    - ``ControlPoints[i]`` / ``Anchors[i]`` alternative root pin names
    """
    controls_pin = _find_pin_among(model, node_name, ["Controls", "ControlPoints", "Anchors"])
    if not controls_pin:
        return

    num = len(ctrl_names)

    for i, ctrl_name in enumerate(ctrl_names):
        _insert_array_pin(controller, node_name, controls_pin)
        t_value = round(i / (num - 1) if num > 1 else 0.0, 4)
        base = f"{node_name}.{controls_pin}.{i}"

        # --- Control RigElementKey ---
        # Try "nested" layout: Controls[i].Control.Type / .Name
        nested_type = f"{base}.Control.Type"
        nested_name = f"{base}.Control.Name"
        if graph_utils.pin_exists(model, nested_type):
            controller.set_pin_default_value(nested_type, "Control", True)
            controller.set_pin_default_value(nested_name, ctrl_name, True)
        else:
            # Try "flat" layout: Controls[i].Type / .Name
            for type_sub in ["Type", "type"]:
                pin = f"{base}.{type_sub}"
                if graph_utils.pin_exists(model, pin):
                    controller.set_pin_default_value(pin, "Control", True)
                    break
            for name_sub in ["Name", "name"]:
                pin = f"{base}.{name_sub}"
                if graph_utils.pin_exists(model, pin):
                    controller.set_pin_default_value(pin, ctrl_name, True)
                    break

        # --- T (normalised position along spline) ---
        for t_sub in ["T", "Ratio", "Alpha", "Position", "t"]:
            pin = f"{base}.{t_sub}"
            if graph_utils.pin_exists(model, pin):
                controller.set_pin_default_value(pin, str(t_value), True)
                break


# ---------------------------------------------------------------------------
# SplineFunctionLibrary node helpers
# ---------------------------------------------------------------------------

_SPLINE_LIBRARY_PATH = "/ControlRigSpline/SplineFunctionLibrary/SplineFunctionLibrary"
_SPLINE_FUNCTION_NAME = "SplineIK"


def _get_spline_function_header():
    """Return the RigVMGraphFunctionHeader for the SplineIK library function, or None."""
    try:
        library = unreal.EditorAssetLibrary.load_asset(_SPLINE_LIBRARY_PATH)
        if library is None:
            return None

        # UE5.x: ControlRigBlueprint.get_local_function_library() -> URigVMFunctionLibrary
        fn_lib = None
        if hasattr(library, "get_local_function_library"):
            fn_lib = library.get_local_function_library()

        if fn_lib is not None:
            if hasattr(fn_lib, "find_function"):
                header = fn_lib.find_function(_SPLINE_FUNCTION_NAME)
                if header is not None:
                    return header
            for lister in ("get_functions", "get_local_functions"):
                if hasattr(fn_lib, lister):
                    for fn in (getattr(fn_lib, lister)() or []):
                        fn_name = fn.get_name() if hasattr(fn, "get_name") else str(fn)
                        if _SPLINE_FUNCTION_NAME in fn_name:
                            return fn

        # Direct fallback on the blueprint itself
        if hasattr(library, "find_function"):
            return library.find_function(_SPLINE_FUNCTION_NAME)

    except Exception as exc:
        if hasattr(unreal, "log_warning"):
            unreal.log_warning(f"[SplineIKModule] Could not load spline function header: {exc}")
    return None


def _populate_key_array(controller, model, node_name, array_pin, element_type, names):
    """Populate an array of RigElementKey entries (Type + Name) on a node."""
    if not graph_utils.pin_exists(model, f"{node_name}.{array_pin}"):
        return
    for i, name in enumerate(names):
        _insert_array_pin(controller, node_name, array_pin)
        base = f"{node_name}.{array_pin}.{i}"
        if graph_utils.pin_exists(model, f"{base}.Type"):
            controller.set_pin_default_value(f"{base}.Type", element_type, True)
        if graph_utils.pin_exists(model, f"{base}.Name"):
            controller.set_pin_default_value(f"{base}.Name", name, True)


# ---------------------------------------------------------------------------
# Distributed-FK fallback (used when RigUnit_SplineIKChain is unavailable)
# ---------------------------------------------------------------------------

def _build_fallback_distributed_fk(
    controller, model, module_prefix, context, chain, controls, x_origin, forwards_solve
):
    """Drive the bone chain from the spline controls without a SplineIK node.

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
    parameterisation, wires them into a ``RigUnit_SplineIKChain`` node, and
    exposes standard attach points so other modules can parent to this one.

    Recipe fields
    -------------
    NumControls : int  (default 4)
        Number of spline control points.  Must be >= 2.
    ControlScale : float  (default 1.0)
        Uniform scale multiplier for all control shapes.

    Attach points
    -------------
    root              – first bone in the chain
    tip               – last bone in the chain
    spline_root_ctrl  – first spline control (index 0)
    spline_tip_ctrl   – last spline control (index N-1)
    spline_mid_ctrl   – middle spline control (index N//2)
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

        # ------------------------------------------------------------------
        # 3. Build graph node
        # ------------------------------------------------------------------
        x_origin = self.context.claim_module_column()
        spline_node_name = f"{module_prefix}_SplineIK"
        native_built = False
        all_nodes = []
        primary_node = None

        # ----- Primary: SplineIK from SplineFunctionLibrary (one node, Controls + Bones) -----
        header = _get_spline_function_header()
        if header is not None and hasattr(controller, "add_function_reference_node"):
            try:
                controller.add_function_reference_node(
                    header, unreal.Vector2D(x_origin, 200), spline_node_name
                )
            except Exception as exc:
                if self.logger:
                    self.logger.log(
                        f"[SplineIKModule] add_function_reference_node failed: {exc}"
                    )
                header = None

        if header is not None and model.find_node(spline_node_name):
            _populate_key_array(
                controller, model, spline_node_name, "Controls", "Control", controls
            )
            _populate_key_array(
                controller, model, spline_node_name, "Bones", "Bone", self.chain
            )
            graph_utils.set_any_pin(
                controller, model, spline_node_name, ["Stretch", "bStretch", "stretch"], "False"
            )

            exec_tail = self.context.get_exec_tail() or forwards_solve
            source_exec = (
                f"{exec_tail}.ExecuteContext"
                if graph_utils.pin_exists(model, f"{exec_tail}.ExecuteContext")
                else f"{exec_tail}.Execute"
            )
            target_exec = (
                f"{spline_node_name}.ExecuteContext"
                if graph_utils.pin_exists(model, f"{spline_node_name}.ExecuteContext")
                else f"{spline_node_name}.Execute"
            )
            graph_utils.connect_pins(controller, model, source_exec, target_exec)
            self.context.set_exec_tail(spline_node_name)
            all_nodes = [spline_node_name]
            primary_node = spline_node_name
            native_built = True

        if not native_built:
            # ----- Fallback: distributed-FK (ControlRigSpline plugin unavailable) -----
            if self.logger:
                self.logger.log(
                    "[SplineIKModule] SplineFunctionLibrary node unavailable — "
                    "using distributed-FK fallback. "
                    "Enable the ControlRigSpline plugin for native spline IK."
                )
            all_nodes, last_exec = _build_fallback_distributed_fk(
                controller, model, module_prefix, self.context,
                self.chain, controls, x_origin, forwards_solve,
            )
            self.context.set_exec_tail(last_exec)
            primary_node = last_exec

        if self.logger:
            self.logger.pop()

        return self.build_result(
            controls=controls,
            nodes=all_nodes,
            attach_points=attach_points,
            outputs={
                "spline_ik_node": primary_node,
                "spline_controls": list(controls),
                "driven_bones": list(self.chain),
                "num_controls": num_controls,
            },
            recipe_data=recipe_data,
            metadata={
                "num_controls": num_controls,
                "control_scale": recipe_data.get("ControlScale"),
            },
        )

    # ------------------------------------------------------------------
    # Recipe
    # ------------------------------------------------------------------

    def read_recipe(self):
        recipe_fields = {
            "ModuleType": None,
            "NumControls": 4,
            "ControlScale": 1.0,
        }
        fallback_names = {
            "ModuleType": ["module_type"],
            "NumControls": ["num_controls", "numcontrols", "ControlCount", "control_count"],
            "ControlScale": ["control_scale", "controlscale"],
        }
        return self.resolve_recipe_fields(recipe_fields, fallback_names=fallback_names)
