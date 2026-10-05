"""Clean layout of the generated Control Rig graph.

After every module is built, each module's nodes are laid out on their own
(left to right along their wiring, no overlaps) and framed by a comment box
named after the module, and the boxes are stacked in build order. Nodes keep
every link; only positions change.

The layout maths (``layered_layout``, ``pack_groups``) is plain Python so it
can be tested outside Unreal. ``arrange`` is the Unreal side: it measures the
nodes, moves them and draws the boxes.

Node sizes are estimated (title length, visible pin rows): the editor only
knows real sizes once a node has been drawn. Estimates are rounded up and
the gaps are generous, so an estimate a little short never makes nodes touch.
"""

from typing import Any, cast

try:
    import unreal  # type: ignore
except ImportError:
    unreal = cast(Any, None)

# Layout spacing (graph units).
COLUMN_GAP = 140         # between columns of nodes inside a box
ROW_GAP = 60             # between nodes stacked in one column
BOX_PADDING = 60         # box border around its nodes
BOX_TITLE = 90           # room for the box title above the nodes
BOX_GAP = 220            # between boxes
MAX_STACK_HEIGHT = 9000  # boxes stack downwards, then start a new column

# Size estimate.
PIN_ROW = 26
NODE_HEADER = 56
CHAR_WIDTH = 8
MIN_WIDTH = 240
MAX_WIDTH = 560

BOX_PREFIX = "RB_Box_"   # comment node names (removed with the other RB_ nodes)
BOX_TAG = "[RB] "        # comment text tag, to find boxes even without our name

TYPE_COLORS = {
    "SplineIK": (0.10, 0.30, 0.65, 0.55),
    "IKFKSwitch": (0.70, 0.38, 0.05, 0.55),
    "IKLimb": (0.45, 0.20, 0.65, 0.55),
    "FKChain": (0.08, 0.50, 0.40, 0.55),
    "Start": (0.30, 0.30, 0.30, 0.55),
    "Shared": (0.60, 0.55, 0.10, 0.55),
}


# ---------------------------------------------------------------------------
# Layout maths (no Unreal)
# ---------------------------------------------------------------------------

def estimate_size(title, rows, longest_label):
    """(width, height) for a node with ``rows`` visible pin rows."""
    width = max(len(title or "") * CHAR_WIDTH + 90, longest_label * CHAR_WIDTH + 190)
    width = max(MIN_WIDTH, min(MAX_WIDTH, width))
    return float(width), float(NODE_HEADER + max(1, rows) * PIN_ROW)


def layered_layout(nodes, edges):
    """Positions for one group of nodes.

    ``nodes``: ordered [(name, (width, height))] -- creation order.
    ``edges``: [(source_name, target_name)] (data and execution links).
    Returns ({name: (x, y)}, (width, height)) relative to the group's corner.

    Columns follow the wiring: a node sits one column right of everything
    that feeds it. A node that only feeds others is then pulled right, next
    to its first consumer, so getters sit beside the node they feed instead
    of far left. Inside a column, nodes keep the order of the nodes feeding
    them (fewer crossing wires).
    """
    names = [n for n, _ in nodes]
    size = dict(nodes)
    order = {n: i for i, n in enumerate(names)}
    succ = {n: [] for n in names}
    pred = {n: [] for n in names}
    for a, b in edges:
        if a in succ and b in succ and a != b and b not in succ[a]:
            succ[a].append(b)
            pred[b].append(a)

    # Topological order (Kahn); a cycle cannot happen in a rig graph, but
    # any leftover node is appended in creation order rather than lost.
    indegree = {n: len(pred[n]) for n in names}
    ready = [n for n in names if indegree[n] == 0]
    topo = []
    while ready:
        ready.sort(key=lambda n: order[n])
        node = ready.pop(0)
        topo.append(node)
        for nxt in succ[node]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
    topo += [n for n in names if n not in topo]

    layer = {}
    for node in topo:
        layer[node] = max((layer[p] + 1 for p in pred[node] if p in layer), default=0)
    for node in reversed(topo):
        if succ[node]:
            layer[node] = max(layer[node], min(layer[s] for s in succ[node]) - 1)

    columns = {}
    for node in names:
        columns.setdefault(layer[node], []).append(node)
    positions = {}
    x = 0.0
    total_height = 0.0
    previous_rank = {}
    for index in sorted(columns):
        column = columns[index]

        def rank(node):
            feeders = [previous_rank[p] for p in pred[node] if p in previous_rank]
            return (sum(feeders) / len(feeders) if feeders else float("inf"), order[node])

        column.sort(key=rank)
        y = 0.0
        for row, node in enumerate(column):
            positions[node] = (x, y)
            previous_rank[node] = row + 1000 * index
            y += size[node][1] + ROW_GAP
        total_height = max(total_height, y - ROW_GAP)
        x += max(size[n][0] for n in column) + COLUMN_GAP
    return positions, (max(0.0, x - COLUMN_GAP), total_height)


def pack_groups(group_sizes, origin=(0.0, 0.0)):
    """Box corners for groups of the given (width, height), in order.

    Boxes stack downwards; past MAX_STACK_HEIGHT a new column starts to the
    right of the widest box so far. Returns [(x, y)] per group.
    """
    corners = []
    x, y = origin
    column_width = 0.0
    for width, height in group_sizes:
        if y > origin[1] and y + height > origin[1] + MAX_STACK_HEIGHT:
            x += column_width + BOX_GAP
            y = origin[1]
            column_width = 0.0
        corners.append((x, y))
        y += height + BOX_GAP
        column_width = max(column_width, width)
    return corners


def box_size(content_size):
    """Box (width, height) around content of the given size."""
    return content_size[0] + 2 * BOX_PADDING, content_size[1] + 2 * BOX_PADDING + BOX_TITLE


# ---------------------------------------------------------------------------
# Unreal side
# ---------------------------------------------------------------------------

def node_names(model):
    """Graph node names in creation order."""
    try:
        return [str(n.get_name()) for n in (model.get_nodes() or [])]
    except Exception:
        return []


def _call(obj, method, *args):
    fn = getattr(obj, method, None)
    if fn is None:
        return None
    try:
        return fn(*args)
    except Exception:
        return None


def _is_comment(node):
    comment_type = getattr(unreal, "RigVMCommentNode", None)
    return comment_type is not None and isinstance(node, comment_type)


def _visible_rows(pin):
    """Rows a pin takes on the node (its sub-pins too when expanded)."""
    direction = str(_call(pin, "get_direction") or "").upper()
    if "HIDDEN" in direction:
        return 0, 0
    label = str(_call(pin, "get_display_name") or _call(pin, "get_name") or "")
    rows, longest = 1, len(label)
    if _call(pin, "is_expanded"):
        for sub in _call(pin, "get_sub_pins") or []:
            sub_rows, sub_longest = _visible_rows(sub)
            rows += sub_rows
            longest = max(longest, sub_longest + 2)
    return rows, longest


def _measure(node):
    title = str(_call(node, "get_node_title") or _call(node, "get_name") or "")
    rows, longest = 0, 0
    for pin in _call(node, "get_pins") or []:
        pin_rows, pin_longest = _visible_rows(pin)
        rows += pin_rows
        longest = max(longest, pin_longest)
    width, height = estimate_size(title, rows, longest)
    actual = _call(node, "get_size")
    try:
        if actual is not None and actual.x > 1 and actual.y > 1:
            width, height = max(width, float(actual.x)), max(height, float(actual.y))
    except Exception:
        pass
    return width, height


def _links(model):
    edges = []
    for link in _call(model, "get_links") or []:
        source = _call(link, "get_source_pin")
        target = _call(link, "get_target_pin")
        a = _call(_call(source, "get_node"), "get_name") if source else None
        b = _call(_call(target, "get_node"), "get_name") if target else None
        if a and b:
            edges.append((str(a), str(b)))
    return edges


def _remove_old_boxes(controller, model):
    for node in list(_call(model, "get_nodes") or []):
        if not _is_comment(node):
            continue
        name = str(node.get_name())
        text = str(_call(node, "get_comment_text") or "")
        if name.startswith(BOX_PREFIX) or text.startswith(BOX_TAG):
            if _call(controller, "remove_node_by_name", name, False) is None:
                _call(controller, "remove_node", node, False)


def _move(controller, name, x, y):
    position = unreal.Vector2D(float(x), float(y))
    for args in ((name, position, False, False, False), (name, position, False), (name, position)):
        fn = getattr(controller, "set_node_position_by_name", None)
        if fn is None:
            return False
        try:
            fn(*args)
            return True
        except TypeError:
            continue
        except Exception:
            return False
    return False


def _add_box(controller, label, kind, x, y, width, height):
    text = f"{BOX_TAG}{label}"
    name = f"{BOX_PREFIX}{''.join(c if c.isalnum() else '_' for c in label)}"
    color = unreal.LinearColor(*TYPE_COLORS.get(kind, TYPE_COLORS["Shared"]))
    position, size = unreal.Vector2D(float(x), float(y)), unreal.Vector2D(float(width), float(height))
    fn = getattr(controller, "add_comment_node", None)
    if fn is None:
        return None
    node = None
    for call in (
        lambda: fn(text, position, size, color, name, False, False),
        lambda: fn(comment_text=text, position=position, size=size, color=color, node_name=name,
                   setup_undo_redo=False),
        lambda: fn(text, position, size, color, False, False),
        lambda: fn(text, position, size, color),
    ):
        try:
            node = call()
            break
        except Exception:
            continue
    if node is not None:
        # Bigger title text when this engine build allows it (cosmetic).
        node_name = str(_call(node, "get_name") or name)
        for args in ((node_name, text, 28, False, False, False, False), (node_name, text, 28, False, False)):
            if _call(controller, "set_comment_text_by_name", *args) is not None:
                break
    return node


def arrange(controller, model, groups, log=print):
    """Lay out ``groups`` and frame each in a named box.

    ``groups``: [(label, kind, [node names])] in build order; kind picks the
    box colour (module type, "Start", "Shared"). Nodes not in any group are
    left where they are. Never raises: a layout problem must not cost a build.
    """
    try:
        _remove_old_boxes(controller, model)
        nodes = {str(n.get_name()): n for n in (_call(model, "get_nodes") or []) if not _is_comment(n)}
        edges = _links(model)
        plans = []
        for label, kind, members in groups:
            members = [m for m in members if m in nodes]
            if not members:
                continue
            member_set = set(members)
            inner = [(a, b) for a, b in edges if a in member_set and b in member_set]
            positions, content = layered_layout([(m, _measure(nodes[m])) for m in members], inner)
            plans.append((label, kind, positions, content))
        corners = pack_groups([box_size(content) for _, _, _, content in plans])
        moved = 0
        for (label, kind, positions, content), (bx, by) in zip(plans, corners):
            for name, (x, y) in positions.items():
                if _move(controller, name, bx + BOX_PADDING + x, by + BOX_PADDING + BOX_TITLE + y):
                    moved += 1
            width, height = box_size(content)
            _add_box(controller, label, kind, bx, by, width, height)
        log(f"[RigBuilder] Graph laid out: {moved} node(s) in {len(plans)} named box(es).")
    except Exception as exc:
        log(f"[RigBuilder] Graph layout skipped ({type(exc).__name__}: {exc}); the rig is unaffected.")
