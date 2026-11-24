"""Edits: verbs that change a solid in place and return it.

Booleans are Blender's EXACT solver, one evaluation for any number of tools, run
on temporary copies in the target's own mesh space — the result never depends on
the depsgraph's state, the active object or the selection. Tools are consumed.

Names after a boolean: the edges where the operands meet are `cut`, plus the
name each tool was given (`hole`, `pocket`, `boss`…), plus `<target>.cut`, plus
the plain cap names of the faces they bound (a hole's mouth on the top is `top`
too). Plain names say where an edge is; qualified ones (`plate.top`) who made it. The
faces a cutting tool leaves behind are `cut` too; the tool's own plain names
(`top`, `side`) are dropped so they cannot be mistaken for the target's, and its
qualified ones (`slot.side`) are kept. An edge left lying flat between two
coplanar faces loses its names.
"""
import bisect
import contextlib
import contextvars
import math
import numbers
import os
import random
import sys
import warnings
from copy import deepcopy

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector
from mathutils import noise as fields
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

from . import _core, _guard
from .frames import _DIRECTION, Frame, frames_of
from .joints import refuse_using_up
from .profile import Path, Placed, Profile, poly
from .solids import _cap, _drawing, extrude, revolve

OPERAND = "s3d~operand"
#: Custom property marking an object `merge` made: its shells may overlap.
MERGED = "s3d~merged"
FLAT = math.cos(math.radians(0.5))
#: Points of an EXACT result that are distinct in exact arithmetic but round to (nearly)
#: the same float leave invisible cracks; closer than this (mm) they are one point.
WELD = 1e-5


# ---------------------------------------------------------------- the boolean engine

def _tool_mesh(tool, rel, strip):
    """A copy of `tool`'s mesh in the target's space, its plain names dropped if `strip`."""
    me = tool.data.copy()
    me.transform(rel)
    if rel.to_3x3().determinant() < 0:
        me.flip_normals()
    if strip:
        names = [a.name for a in me.attributes]  # by name: removing one invalidates the others (bpy 4.5)
        for name in names:
            for prefix in (_core.FACE_TAG, _core.EDGE_TAG):
                if name.startswith(prefix) and "." not in name[len(prefix):]:
                    me.attributes.remove(me.attributes[name])
                    break
    return me


def _evaluate(base_mesh, tool_meshes, operation, self_intersect=False):
    """Run one EXACT boolean on temporary objects; the evaluated mesh."""
    coll = bpy.data.collections.new("_s3d_tools")
    base = bpy.data.objects.new("_s3d_base", base_mesh)
    tools = []
    for me in tool_meshes:
        t = bpy.data.objects.new("_s3d_tool", me)
        coll.objects.link(t)
        tools.append(t)
    mod = base.modifiers.new("boolean", "BOOLEAN")
    mod.operation, mod.solver = operation, "EXACT"
    mod.use_self = self_intersect
    if len(tools) == 1:
        mod.operand_type, mod.object = "OBJECT", tools[0]
    else:
        mod.operand_type, mod.collection = "COLLECTION", coll
    try:
        result = _core.evaluated_mesh(base, collection=coll, preserve_all_data_layers=True)
    finally:
        bpy.data.batch_remove([me for me in {base_mesh, *tool_meshes} if me.users == 0])
    return result


def _solve(base_mesh, tool_meshes, operation, self_intersect):
    """The EXACT result as a bmesh, in a fixed order, its cracks welded."""
    result = _evaluate(base_mesh, tool_meshes, operation, self_intersect)
    bm = bmesh.new()
    bm.from_mesh(result)
    bpy.data.meshes.remove(result)
    _sort_mesh(bm)                       # the modifier's edges come in an order set by the thread count
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=_core.mm(WELD))
    bmesh.ops.dissolve_degenerate(bm, dist=_core.mm(WELD), edges=bm.edges)
    _drop_duplicates(bm)
    _drop_tessellation_duplicates(bm)
    return bm


def _drop_duplicates(bm):
    """Keep one of the faces on the same points: the solver leaves some where two
    joined solids cross, back to back. The first is kept and takes the others' names.
    `Mesh.validate()` — which the glTF exporter runs — would drop them anyway, and under
    bpy 4.5 it writes into the arrays a mesh shares with its copies."""
    bm.verts.index_update()
    seen, extra = {}, []
    for f in bm.faces:
        key = tuple(sorted(v.index for v in f.verts))
        if key in seen:
            extra.append((seen[key], f))
        else:
            seen[key] = f
    if not extra:
        return
    tags = [lay for lay in bm.faces.layers.bool.values() if lay.name.startswith(_core.FACE_TAG)]
    for kept, f in extra:
        for lay in tags:
            if f[lay]:
                kept[lay] = True
    bmesh.ops.delete(bm, geom=[f for _, f in extra], context="FACES_ONLY")


def _operands(ob, tools, strip):
    """`ob`'s mesh and the tools' meshes in `ob`'s frame, each face marked with its operand."""
    to_local = _core.world(ob).inverted()
    base_mesh = ob.data.copy()
    from ._coordinates import NAMES
    coordinates = any(NAMES[0] in part.data.attributes for part in (ob,*tools))
    def missing(mesh):
        if coordinates:
            for name in NAMES:
                if name not in mesh.attributes:
                    attr = mesh.attributes.new(name, 'FLOAT', 'POINT')
                    attr.data.foreach_set('value', [float('nan')]*len(mesh.vertices))
    missing(base_mesh)
    base_mesh.attributes.new(OPERAND, "INT", "FACE")
    tool_meshes = []
    for k, tool in enumerate(tools, 1):
        rel = to_local @ _core.world(tool)
        me = _tool_mesh(tool, rel, strip)
        missing(me)
        att = me.attributes.new(OPERAND, "INT", "FACE")
        att.data.foreach_set("value", [k] * len(me.polygons))
        reach = max(abs(c) for m in (_core.world(ob), _core.world(tool)) for c in m.translation)
        _settle(base_mesh, me, reach)
        tool_meshes.append(me)
    return base_mesh, tool_meshes


def _noise(x):
    """Four steps of single precision at the size of `x`."""
    return math.ldexp(1.0, math.frexp(x)[1] - 22) if x else 0.0


def _settle(base_mesh, me, reach):
    """Put each coordinate of the tool mesh `me` on the target's, where the target has
    exactly one within float noise of it: `WELD`, or four steps of single precision at
    the size of the coordinate, or of the placements (`reach`) it went through.

    Meshes and placements are single precision. A post standing on a plate lands a step
    or two off the plate's top in its space, and the solver sees that sliver: the holes
    the posts print in the top come back linked by zero-width bridges, which the weld
    breaks. On the target's coordinate, the contact is exactly flush. Where the
    target has several values that close (a revolve's 3e-15 where cos 90° is 0), the
    tool is left alone."""
    co = [0.0] * (3 * len(base_mesh.vertices))
    base_mesh.vertices.foreach_get("co", co)
    planes = [sorted(set(co[axis::3])) for axis in range(3)]
    floor = max(_core.mm(WELD), _noise(reach))
    co = [0.0] * (3 * len(me.vertices))
    me.vertices.foreach_get("co", co)
    moved = False
    for i, c in enumerate(co):
        values = planes[i % 3]
        near = max(floor, _noise(c))
        lo, hi = bisect.bisect_left(values, c - near), bisect.bisect_right(values, c + near)
        if hi - lo == 1 and values[lo] != c:
            co[i] = values[lo]
            moved = True
    if moved:
        me.vertices.foreach_set("co", co)
        me.update()


def _extent(meshes):
    """(lo, hi) corners of the box round every vertex of `meshes`."""
    lo, hi = [math.inf] * 3, [-math.inf] * 3
    for me in meshes:
        co = [0.0] * (3 * len(me.vertices))
        me.vertices.foreach_get("co", co)
        for axis in range(3):
            if co:
                lo[axis] = min(lo[axis], min(co[axis::3]))
                hi[axis] = max(hi[axis], max(co[axis::3]))
    return lo, hi


class _Operands:
    """The meshes of one boolean, and the box its result must stay in: the target's (the
    target's and the tools' for a union). A tool that is exactly an earlier one of the
    same call — a symmetric rib turned by 180° in a ring of eight — adds nothing, and two
    coincident solids break the solver: it is left out (`same`: its number -> the earlier
    one's), and its name goes on the earlier one's edges."""

    def __init__(self, ob, tools, operation, strip):
        self.base, meshes, self.operation = *_operands(ob, tools, strip), operation
        self.box = _extent([self.base] + (meshes if operation == "UNION" else []))
        self.tools_box = _extent(meshes) if operation in {"DIFFERENCE", "INTERSECT"} else None
        self.tools, self.same, kept = [], {}, {}
        for k, (tool, me) in enumerate(zip(tools, meshes), 1):
            shape = _Shape(me)
            first = next((j for j, other in kept.get(shape.key, ()) if other.same(shape)), None)
            if first is not None:
                self.same[k] = first
                bpy.data.meshes.remove(me)
            else:
                kept.setdefault(shape.key, []).append((k, shape))
                self.tools.append(me)

    def check(self, bm, verb, name):
        """Raise if `bm` reaches outside the box: a boolean must not hand back something
        else than the part, as the drill instead of the plate. A result left open by
        a sliver the solver could not close is the part, nearly whole: it is returned."""
        move = "clear of the part or into it" if self.operation == "DIFFERENCE" else "into the part"
        hint = (f"a tool grazes the part (tangent to a face, or flush along a line), or a solid crosses itself — move "
                f"the tool {move}, and fuse overlapping solids with s3d.join first")
        lo, hi = self.box
        pad = _core.mm(1e-3) + 1e-6 * max(hi[k] - lo[k] for k in range(3))
        got = [(min(v.co[k] for v in bm.verts), max(v.co[k] for v in bm.verts)) for k in range(3)] if bm.verts else []
        for axis, (low, high) in enumerate(got):
            for value in (low, high):
                if not lo[axis] - pad <= value <= hi[axis] + pad:
                    where = f"{'xyz'[axis]} = {value:.6g}, beyond {lo[axis]:.6g} .. {hi[axis]:.6g}"
                    raise ValueError(f"{verb}: the result on {name!r} reaches outside the target and its tools "
                                     f"({where}): {hint}")


class _Shape:
    """A tool mesh as a solid to compare: two are the same if they have as many points and
    faces, and each point and face of one is on the other's, within `WELD` or the
    single-precision noise of their size."""

    def __init__(self, me):
        self.me = me
        co = [0.0] * (3 * len(me.vertices))
        me.vertices.foreach_get("co", co)
        n = max(len(me.vertices), 1)
        self.centre = Vector([sum(co[i::3]) / n for i in range(3)])
        self.key = (len(me.vertices), len(me.polygons))
        self.near = max(_core.mm(WELD), _noise(max((abs(c) for c in co), default=0.0)))
        self.tree = None

    def same(self, other):
        if (self.centre - other.centre).length > self.near:
            return False
        if self.tree is None:
            self.tree = KDTree(len(self.me.vertices))
            for v in self.me.vertices:
                self.tree.insert(v.co, v.index)
            self.tree.balance()
        to = []
        for v in other.me.vertices:
            _, i, d = self.tree.find(v.co)
            if d > max(self.near, other.near):
                return False
            to.append(i)
        faces = {frozenset(p.vertices) for p in self.me.polygons}
        return all(frozenset(to[i] for i in p.vertices) in faces for p in other.me.polygons)


class NothingCut(ValueError):
    """A cut, a hole or a pocket whose tools all miss the part, or only touch it."""


def _nothing_cut(message, name, part, tools):
    """NothingCut, keeping for a pocket pattern the part's name and the boxes, in the scene's frame."""
    error = NothingCut(message)
    error._missed = (name, part, tools)
    return error


class MissedCut(UserWarning):
    """The warning a missed cut, hole or pocket gives outside strict mode: the part is left as it was."""


class ClampedRadius(UserWarning):
    """The warning a corner radius too large for its side gives outside strict mode — `rect(r=)`,
    `poly(fillet=)`, `wire(fillet=)`: it is clamped to the largest that fits."""


_STRICT = contextvars.ContextVar("sand3d_strict", default=None)   # None: SAND3D_STRICT decides


_YES, _NO = ("1", "true", "yes", "on"), ("", "0", "false", "no", "off")


def _is_strict():
    if _STRICT.get() is not None:
        return _STRICT.get()
    value = os.environ.get("SAND3D_STRICT", "")
    if value.strip().lower() in _YES:
        return True
    if value.strip().lower() in _NO:
        return False
    raise ValueError(f"SAND3D_STRICT={value!r}: give 1, true, yes or on for strict mode; 0, false, no, off or "
                     f"nothing for warnings")


@contextlib.contextmanager
def strict(on=True):
    """Within the block, a cut, a hole or a pocket whose tools all miss the part raises
    NothingCut (on) or warns with MissedCut and leaves the part as it was (off); a corner
    radius too large for its side (`rect(r=)`, `poly(fillet=)`, `wire(fillet=)`) raises
    ValueError (on) or warns with ClampedRadius and is clamped to the largest that fits (off).
    A missed projection or a carrier without a surface in lay raises (on) or gives
    LayWarning (off). Exceeding reach always raises ValueError.

    Outside any block, SAND3D_STRICT in the environment decides: 1, true, yes or on make
    it raise; 0, false, no, off or nothing make it warn, as a boolean that misses does in
    Blender or in a CAD kernel; any other value is an error. Strict mode is for checking
    programs, a dataset's for instance: a tool in the wrong place is the
    commonest silent mistake, and a warning lets the program go on to a wrong object."""
    token = _STRICT.set(on)     # a context variable: blocks interleaved by asyncio each keep their own
    try:
        yield
    finally:
        _STRICT.reset(token)


def _in_library(frame):
    name = frame.f_globals.get("__name__") or ""
    return name == "sand3d" or name.startswith("sand3d.")


def _warn(message, category):
    """Warn at the program's line: the first caller outside the library, however deep
    the verb that warns is called within it — told by its module, not its file."""
    frame, level = sys._getframe(1), 2
    while frame.f_back is not None and _in_library(frame):
        frame, level = frame.f_back, level + 1
    warnings.warn(message, category, stacklevel=level)


def _missed(error):
    """A missed cut: raise it in strict mode, else warn and let the program go on."""
    if _is_strict():
        raise error
    _warn(str(error), MissedCut)


def _box_in_scene(ob, box):
    """`box`, in `ob`'s frame, as the box it fills in the scene — where the program placed it."""
    m = _core.world(ob)
    lo, hi = box
    corners = [m @ Vector((x, y, z)) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
    return tuple(min(c[k] for c in corners) for k in range(3)), tuple(max(c[k] for c in corners) for k in range(3))


def _box_text(box):
    return "(" + ", ".join(f"{v:.6g}" for v in box[0]) + ") .. (" + ", ".join(f"{v:.6g}" for v in box[1]) + ")"


def _clamped(error, message):
    """A corner radius too large for its side: raise `error` in strict mode, else warn
    with `message` at the program's line and let the verb clamp it."""
    if _is_strict():
        raise error
    _warn(message, ClampedRadius)


def _boxes(ob, operands):
    """The part's box and the tools', as text, in the scene."""
    return [_box_text(_box_in_scene(ob, box)) for box in (operands.box, operands.tools_box)]


def _boolean(ob, tools, operation, strip, self_intersect=False, verb="boolean", aimed=False):
    """`ob` combined with `tools` (consumed) by `operation`; names written as the module says.
    An operand `merge` made may hold overlapping shells: the boolean fuses them first. A
    result that is no solid the operands can give raises; the tools are used up anyway."""
    name = _core.given_name(ob)
    consumed = list(tools)
    self_intersect = self_intersect or any(o.get(MERGED) for o in (ob, *tools))
    operands = _Operands(ob, tools, operation, strip)
    bm = _solve(operands.base, operands.tools, operation, self_intersect)
    if operation == "UNION" and not bm.faces and not self_intersect:
        # a union of solids is never empty: the exact solver gave up on an operand that
        # crosses itself (a wire swept round a corner tighter than its radius), which
        # the self-intersecting solver takes
        bm.free()
        self_intersect = True
        operands = _Operands(ob, tools, operation, strip)
        bm = _solve(operands.base, operands.tools, operation, self_intersect)
    if operation == "UNION" and not bm.faces:
        bm.free()
        names = ", ".join(repr(_core.given_name(t)) for t in tools)
        for tool in consumed:
            delete(tool)
        raise ValueError(f"{verb}: fusing {names} into {name!r} gives nothing — the solver could not read them as "
                         f"solids: a solid that crosses itself, or one that is not closed")
    if operation == "DIFFERENCE" and not bm.faces:
        bm.free()
        for tool in consumed:
            delete(tool)
        raise ValueError(f"{verb}: the tools take all of {name!r} away — nothing would be left")
    empty_intersection = None
    if operation == "INTERSECT" and not bm.faces:
        names = ", ".join(repr(_core.given_name(t)) for t in tools)
        part, tools_at = _boxes(ob, operands)
        empty_intersection = (f"{verb}: {name!r} and {names} share nothing — they miss each other, or only touch "
                              f"(their boxes {part}; {tools_at}); returning an empty mesh")
    if operation == "DIFFERENCE":
        # a tool that leaves no face took no volume out: it only touched, and printed its
        # footprint on the face it stands on, in slivers a later bevel clamps to nothing
        layer = bm.faces.layers.int[OPERAND]
        used = {f[layer] for f in bm.faces}
        used |= {k for k, first in operands.same.items() if first in used}
        removing = [t for k, t in enumerate(tools, 1) if k in used]
        if len(removing) < len(tools):
            bm.free()
            tools = removing
            if not tools:
                for tool in consumed:
                    delete(tool)
                if aimed:   # a tool in the wrong place is the commonest silent mistake: say so
                    part, tools_at = (_box_in_scene(ob, box) for box in (operands.box, operands.tools_box))
                    _missed(_nothing_cut(f"{verb}: no tool cuts into {name!r} — they miss it, or only touch it (its "
                                       f"box {_box_text(part)}; the tools' {_box_text(tools_at)})",
                                       name, part, tools_at))
                return ob
            operands = _Operands(ob, tools, operation, strip)
            bm = _solve(operands.base, operands.tools, operation, self_intersect)
    try:
        operands.check(bm, verb, name)
    except ValueError:
        bm.free()
        for tool in consumed:
            delete(tool)
        raise
    tool_names = [{_core.given_name(tool)} for tool in tools]
    for k, first in operands.same.items():          # a tool left out names its twin's edges
        tool_names[first - 1].add(_core.given_name(tools[k - 1]))
    layer = bm.faces.layers.int[OPERAND]
    bm.faces.index_update()
    bm.edges.index_update()
    operand = [f[layer] for f in bm.faces]
    face_add = {}
    if strip:
        face_add = {f.index: {"cut", f"{name}.cut"} for f in bm.faces if operand[f.index] > 0}
    caps = [lay for lay in bm.faces.layers.bool.values()
            if lay.name.startswith(_core.FACE_TAG) and _is_cap(lay.name[len(_core.FACE_TAG):])]
    edge_add = {}
    for e in bm.edges:
        ids = {operand[f.index] for f in e.link_faces}
        if len(ids) > 1:
            # plain cap names say what an edge bounds; qualified ones keep saying who made it
            bounds = {lay.name[len(_core.FACE_TAG):] for f in e.link_faces for lay in caps
                      if f[lay] and "." not in lay.name[len(_core.FACE_TAG):]}
            edge_add[e.index] = {"cut", f"{name}.cut"} | set().union(*(tool_names[i - 1] for i in ids if i > 0)) \
                | bounds
    from ._coordinates import NAMES
    if all(NAMES[0] in part.data.attributes for part in (ob,*tools)):
        from ._surface import _surface, _project
        # Sources already share the target frame; keep the full operand numbering.
        source_meshes = [ob.data.copy()] + [_tool_mesh(tool, _core.world(ob).inverted() @ _core.world(tool), strip) for tool in tools]
        try:
            _project(bm, [_surface(mesh) for mesh in source_meshes], layer)
        finally:
            for mesh in source_meshes:
                bpy.data.meshes.remove(mesh)
    bm.faces.layers.int.remove(layer)
    _core.add_tags(bm, face_add, edge_add)
    _flatten_names(bm)
    from ._coordinates import NAMES
    incomplete = any(NAMES[0] not in part.data.attributes for part in (ob,*tools))
    if incomplete:
        for label in NAMES:
            layer = bm.verts.layers.float.get(label)
            if layer is not None:
                bm.verts.layers.float.remove(layer)
    _replace_mesh(ob, bm)
    if MERGED in ob:
        del ob[MERGED]
    for tool in consumed:
        delete(tool)
    if empty_intersection is not None:
        warnings.warn(empty_intersection, stacklevel=4)
    return ob


def _flatten_names(bm):
    """Untag the named edges that now lie flat between two coplanar faces."""
    layers = [lay for lay in bm.edges.layers.bool.values() if lay.name.startswith(_core.EDGE_TAG)]
    for e in bm.edges:
        if len(e.link_faces) == 2 and e.link_faces[0].normal.dot(e.link_faces[1].normal) > FLAT:
            if any(e[lay] for lay in layers):
                for lay in layers:
                    e[lay] = False
                e.smooth = True


def _replace_mesh(ob, bm, *, keep_shading=False):
    """`bm` as `ob`'s mesh. Normals are not recomputed: a boolean's are right, and a
    void inside a shell must keep facing in."""
    old = ob.data
    mesh = bpy.data.meshes.new(old.name)
    bm.to_mesh(mesh)
    bm.free()
    ob.data = mesh
    _core.hook_objects.append(ob)
    if old.users == 0:
        bpy.data.meshes.remove(old)
    mesh.name = _core.given_name(ob)
    if not keep_shading:
        _core.shade_mesh(ob)


# ---------------------------------------------------------------- booleans

def cut(ob, *tools):
    """Subtract tools.

    `ob` with every tool taken out of it, in one boolean; a list of tools is worth its
    tools. To repeat a tool, place copies with `at(tool, on=[frames])`. The tools are
    used up."""
    tools = _flat(tools)
    _solids("cut", ob, *tools)
    refuse_using_up(tools, "cut")
    _guard.using_up(tools, ob)
    return _boolean(ob, tools, "DIFFERENCE", strip=True, verb="cut", aimed=True) if tools else ob


def join(ob, *others):
    """Fuse others in; ob's material wins: group keeps each its own.

    `ob` and `others` fused into one solid, `ob`'s name kept; a list is worth its
    solids. The others are used up, and so are their materials: the solid wears `ob`'s.
    Parts of different materials that touch are a `group`, each keeping its own."""
    others = _flat(others)
    _solids("join", ob, *others)
    refuse_using_up(others, "join")
    _materials_lost(ob, others)
    _guard.using_up(others, ob)
    return _boolean(ob, others, "UNION", strip=False, verb="join") if others else ob


def _materials_lost(ob, others, verb="join"):
    """Warn when `join` (or `blend`) uses up a solid wearing another material than `ob`: the
    result wears one material, `ob`'s, and the others' are gone from the export."""
    from .materials import _name, _nearest
    base = _nearest(ob)
    lost = {}
    for other in others:
        tag = _nearest(other)
        if tag is not None and tag != base:
            parts = lost.setdefault(_name(tag), [])
            if _core.given_name(other) not in parts:
                parts.append(_core.given_name(other))
    if not lost:
        return
    line = f" (line {_guard.calls[0][1]})" if _guard.calls else ""
    keeps = f"keeps its {_name(base)!r}" if base is not None else "wears no material"
    which = "; ".join(f"{name!r} on {', '.join(map(repr, parts))}" for name, parts in sorted(lost.items()))
    warnings.warn(f"{verb}{line}: {_core.given_name(ob)!r} {keeps}, and the parts {verb}ed into it lose theirs: "
                  f"{which} — to keep each part its material, s3d.group(name, ...) them instead of {verb}ing",
                  stacklevel=4)


def intersect(ob, tool):
    """Keep the common part.

    What `ob` and `tool` share. If they share nothing, `ob` becomes an empty mesh
    and a warning identifies both objects. The tool is used up."""
    _solids("intersect", ob, tool)
    refuse_using_up([tool], "intersect")
    _guard.using_up([tool], ob)
    return _boolean(ob, [tool], "INTERSECT", strip=False, verb="intersect")


def seat(host, part):
    """Take out of host the volume part fills, as it sits at rest; part untouched.

    `host` with the volume it shares with `part` taken out — what a lens leaves in its
    rim, a knob in its console — as they sit at rest, every joint at 0, whatever the
    pose: `part` (a solid, a group or an assembly) is left as it is, and may move (a
    knob turning in its seat, a drawer sliding along its runners). Raises if they do not
    share any volume. Returns `host`."""
    from .assembly import Handle
    from .joints import Kinematics
    root = part.root if isinstance(part, Handle) else part
    _solids("seat", host)
    if not isinstance(root, bpy.types.Object):
        raise TypeError(f"seat: the part is a solid, a group or an assembly, not {type(part).__name__}")
    if root == host:
        raise ValueError(f"seat: {_core.given_name(host)!r} is both the host and the part")
    meshes = [o for o in [root, *root.children_recursive] if o.type == "MESH"]
    if host in meshes:
        raise ValueError(f"seat: {_core.given_name(host)!r} is inside the part {_core.given_name(root)!r}")
    if not meshes:
        raise ValueError(f"seat: {_core.given_name(root)!r} holds no solid")
    k = Kinematics()
    to_host = _core.world(host) @ k.rest_world(host).inverted()     # the part where it sits at rest, by the host
    tools = []
    for ob in meshes:
        tool = _core.link(bpy.data.objects.new(_core.given_name(ob), ob.data.copy()))
        tool[_core.NAME] = _core.given_name(ob)
        tool.matrix_basis = _core.snapped(to_host @ k.rest_world(ob))
        tools.append(tool)
    try:
        with strict():      # a part that shares no volume with its host has nothing to seat: always an error
            return _boolean(host, tools, "DIFFERENCE", strip=True, verb="seat", aimed=True)
    except NothingCut:
        raise ValueError(f"seat: {_core.given_name(root)!r} shares no volume with {_core.given_name(host)!r} at "
                         f"rest — they miss each other, or only touch: there is nothing to seat") from None


def _half_space(ob, frame, below):
    """A box filling the side of `frame` (in `ob`'s parent's frame) away from what is kept."""
    corners = [ob.matrix_basis @ Vector(c) for c in _bbox(ob)]
    reach = 4 * (max((a - b).length for a in corners for b in corners) + (frame.origin - corners[0]).length
                 + _core.mm(1))
    tool = box_tool(reach, below)
    tool.matrix_basis = frame.matrix
    tool.parent = ob.parent
    return tool


def box_tool(reach, below):
    """A cube `reach` wide on one side of its XY plane: above if not `below`."""
    b = _core.Builder("split")
    v = [b.vert((x * reach, y * reach, (z - 1 if below else z) * reach))
         for z in (0, 1) for y in (-1, 1) for x in (-1, 1)]
    for f in ((0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (1, 3, 7, 5), (3, 2, 6, 7), (2, 0, 4, 6)):
        b.face([v[i] for i in f], 0, ("side",))
    return b.finish("side")


def _bbox(ob):
    vs = [v.co for v in ob.data.vertices]
    lo = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    hi = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    return [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]


def split(ob, frame, keep="above"):
    """By a frame's plane.

    `ob` cut by the plane of `frame`: keep the part `"above"` it (on its normal's
    side) or `"below"`; `"both"` returns the two, the second a new solid."""
    _solids("split", ob)
    if keep == "both":
        other = _twin(ob)
        return split(ob, frame, "above"), split(other, frame, "below")
    if keep not in ("above", "below"):
        raise ValueError(f"split: keep is 'above', 'below' or 'both', not {keep!r}")
    return _boolean(ob, [_half_space(ob, frame, below=keep == "above")], "DIFFERENCE", strip=True, verb="split")


def _solids(verb, *obs):
    """Refuse what is not a solid, saying what it is and what to do with it."""
    for ob in obs:
        if isinstance(ob, bpy.types.Object) and ob.type == "MESH":
            continue
        if isinstance(ob, bpy.types.Object) and ob.type == "EMPTY":
            raise TypeError(f"{verb}: {_core.given_name(ob)!r} is a group, not a solid: give its parts, or join them "
                            f"into one first")
        if isinstance(ob, bpy.types.Object):
            raise TypeError(f"{verb}: {_core.given_name(ob)!r} is a {ob.type.lower()} object, not a solid")
        if isinstance(ob, (Profile, Placed)):
            raise TypeError(f"{verb}: a profile is not a solid: extrude it first, s3d.extrude(name, profile, h)")
        if isinstance(ob, Path):
            raise TypeError(f"{verb}: a path is not a solid: s3d.wire(name, path, d) or s3d.sweep(name, profile, path)")
        raise TypeError(f"{verb}: a solid is expected, not {type(ob).__name__}")


def _flat(items):
    """Objects from objects and lists of them, in order: a list of objects is worth its
    elements; a handle stands for its root."""
    from .assembly import Handle
    out = []
    for item in items:
        if isinstance(item, (list, tuple)):
            out += _flat(item)
        else:
            out.append(item.root if isinstance(item, Handle) else item)
    return out


def _delete_tree(ob):
    """Remove `ob` and everything under it, children before parents."""
    children = _children()
    parts = []
    def walk(part):
        for child in children.get(part, ()):
            walk(child)
        parts.append(part)
    walk(ob)
    delete(parts)


def delete(ob):
    """Remove it.

    Remove `ob` from the scene; an object a verb used up is gone already."""
    parts, seen = [], set()
    def collect(part):
        if isinstance(part, (list, tuple)):
            for child in part:
                collect(child)
        elif not _guard.removed(part) and part not in seen:
            seen.add(part)
            parts.append(part)
    collect(ob)
    data = set()
    for part in parts:
        _guard.deleting(part)
        if part.type in ("MESH", "LIGHT"):
            data.add(part.data)
    bpy.data.batch_remove(parts)
    bpy.data.batch_remove([block for block in data if block.users == 0])


# ---------------------------------------------------------------- holes and pockets

def _frames(ob, on):
    """Frames from a frame, a point or a list of either — a point (x, y) facing up from
    `ob`'s top, (x, y, z) facing up where it is — each set where its axis enters `ob`
    from the side the normal points to (`_entry`)."""
    if on is None:
        on = (0, 0)
    if isinstance(on, Frame):
        on = [on]
    elif on and isinstance(on[0], (int, float)):
        on = [on]
    top = max((ob.matrix_basis @ v.co).z for v in ob.data.vertices) if any(
        not isinstance(a, Frame) and len(a) == 2 for a in on) else 0.0
    frames = [a if isinstance(a, Frame) else Frame((a[0], a[1], top) if len(a) == 2 else tuple(a)) for a in on]
    tree = _core.mm_tree(ob, ob.matrix_basis)
    return [_entry(ob, tree, f) for f in frames]


def _entry(ob, tree, frame):
    """`frame` moved along its normal to where its axis enters `ob` from the side the
    normal points to. On a face facing that way, it stays as it is. Inside the part, it
    goes up to the face the axis leaves by; in the air, down to the first face it meets.
    The meeting point is worked out on that face's plane, in double precision. An axis
    that misses the part leaves the frame where it is."""
    from .frames import _plane
    size = _core.in_mm(1.0)
    o, n = frame.origin, frame.z
    near = tree.find_nearest(o * size)
    tol = max(WELD, _noise(max(abs(c) for c in o * size)))
    if near[0] is not None and near[3] <= tol and near[1].dot(n) > 0:
        return frame                                        # on a face looking its way
    up = tree.ray_cast(o * size + n * (2 * tol), n)         # from just past a face looking away, if on one
    hit = up if up[0] is not None and up[1].dot(n) > 0 else None   # inside: the face the axis leaves by
    if hit is None:
        down = tree.ray_cast(o * size, -n)
        hit = down if down[0] is not None and down[1].dot(n) > 0 else None
    if hit is None:
        return frame
    loc, _, index, _ = hit
    normal, point = _plane(ob.data, [ob.data.polygons[index]], ob.matrix_basis)
    along = sum(a * b for a, b in zip(normal, n)) if normal is not None else 0.0
    if abs(along) < 1e-9:                                   # a sliver: the hit itself will do
        return Frame(tuple(c / size for c in loc), n, frame.y)
    t = sum(a * (p - q) for a, p, q in zip(normal, point, o)) / along   # o + n·t lies on the face's plane
    return Frame(tuple(oc + nc * t for oc, nc in zip(o, n)), n, frame.y)


def _reach(ob, frame):
    corners = [ob.matrix_basis @ c for c in _bbox(ob)]
    span = max((a - b).length for a in corners for b in corners) + (frame.origin - corners[0]).length
    return 2 * span + _core.mm(1)


def _place_tool(tool, ob, frame):
    tool.matrix_basis = frame.matrix
    tool.parent = ob.parent
    return tool


def hole(ob, d, on=(0, 0), depth=None, cbore=None, csk=None):
    """On frames or points: through, or `depth` deep.

    Round holes of diameter `d` into `ob`, one per frame or point of `on`: each starts
    where its axis enters the part, from the side the frame's normal points to (a point
    (x, y) faces down onto the part), and runs right through, or `depth` deep.
    `cbore=(D, depth)` adds a counterbore, `csk=(D, angle)` a countersink. Mouth edges
    are named `hole`."""
    _solids("hole", ob)
    if cbore and not (hasattr(cbore, "__len__") and len(cbore) == 2):
        raise TypeError(f"hole: cbore is (diameter, depth), not {cbore!r}")
    if csk and not isinstance(csk, (int, float)) and not (hasattr(csk, "__len__") and len(csk) == 2):
        raise TypeError(f"hole: csk is a diameter, or (diameter, angle), not {csk!r}")
    frames = _frames(ob, on)
    tools = []
    for frame in frames:
        reach = _reach(ob, frame)
        over = max(_core.mm(0.01), 0.01 * d) if depth is not None else reach   # a through hole: both ways
        bottom = -(depth if depth is not None else reach)
        pts = [(0, over)]
        big, angle = ((csk, 90) if isinstance(csk, (int, float)) else csk) if csk else (0, 90)
        if cbore and cbore[0] > d:
            big, cdepth = cbore
            pts += [(big / 2, over), (big / 2, -cdepth), (d / 2, -cdepth)]
        elif csk and big > d:  # a countersink no wider than the hole leaves a plain hole
            fall = (big - d) / 2 / math.tan(math.radians(angle) / 2)
            pts += [(big / 2 + over * math.tan(math.radians(angle) / 2), over), (d / 2, -fall)]
        else:
            pts += [(d / 2, over)]
        pts += [(d / 2, bottom), (0, bottom)]
        tools.append(_place_tool(revolve("hole", poly(pts)), ob, frame))
    return _boolean(ob, tools, "DIFFERENCE", strip=True, verb="hole", aimed=True)


def pocket(ob, profile, depth=None, on=None):
    """Profile cut in from a face.

    `profile`, drawn in the face's plane (moved within it only), cut into `ob` from the
    frame `on` (by default the surface over `ob`'s
    origin, facing up, where a hole on (0, 0) would start),
    `depth` deep against its normal, or right through; with a list of frames, once on
    each. Floor and walls are named `pocket.bottom`, `pocket.side`."""
    _solids("pocket", ob)
    if isinstance(profile, (list, tuple)) and any(isinstance(p, (Profile, Placed)) for p in profile):
        raise TypeError("pocket: one profile per pocket; to repeat it, give on=[frames]")
    if isinstance(on, (list, tuple)):
        frames, missed = frames_of(on, "pocket"), []
        for f in frames:                      # one after the other, as the loop it replaces
            try:
                with strict():
                    pocket(ob, profile, depth, f)
            except NothingCut as error:       # one frame off an irregular part: dropped, as a hole's
                missed.append(error)
        if len(missed) == len(frames):
            if len(frames) == 1:
                _missed(missed[0])
            else:
                name, part, _ = missed[0]._missed
                tools = (tuple(min(e._missed[2][0][k] for e in missed) for k in range(3)),
                         tuple(max(e._missed[2][1][k] for e in missed) for k in range(3)))
                _missed(_nothing_cut(f"pocket: none of the {len(frames)} frames cuts into {name!r} — the pockets "
                                     f"miss it, or only touch it (its box {_box_text(part)}; the pockets' "
                                     f"{_box_text(tools)})", name, part, tools))
        return ob
    profile = _drawing(profile, "pocket: the profile is placed out of the face's plane: draw it in its plane — "
                                "x, y and rz only — and give the face or frames with on=: s3d.pocket(ob, profile, "
                                "depth, on=…)")
    frame = on if on is not None else _frames(ob, (0, 0))[0]
    if isinstance(frame, Placed):
        raise ValueError("pocket: place the profile with `on`, not `at`")
    over = _core.mm(0.01)
    reach = depth if depth is not None else _reach(ob, frame)
    tool = extrude("pocket", profile, -reach, h2=-over)
    return _boolean(ob, [_place_tool(tool, ob, frame)], "DIFFERENCE", strip=True, verb="pocket", aimed=True)


# ---------------------------------------------------------------- edges: fillet, chamfer, soften

def _names(edges):
    if edges is None or edges == "all":
        return None
    return edges.split() if isinstance(edges, str) else list(edges)


def _named_edges(ob, bm, edges):
    """The edges of `bm` carrying any of the names in `edges` ("all" or None: every named edge)."""
    names = _names(edges)
    layers = {lay.name[len(_core.EDGE_TAG):]: lay for lay in bm.edges.layers.bool.values()
              if lay.name.startswith(_core.EDGE_TAG)}
    if names is None:
        chosen = list(layers.values())
    else:
        missing = [n for n in names if _core.stored(_core.EDGE_TAG, n) not in layers]
        if missing:
            raise ValueError(_core.unknown(_core.given_name(ob), "edge", missing, sorted(layers)))
        chosen = [layers[_core.stored(_core.EDGE_TAG, n)] for n in names]
    found = [e for e in bm.edges if any(e[lay] for lay in chosen)]
    if not found:
        raise ValueError(f"{_core.given_name(ob)}: no edge carries {edges!r} any more")
    return found


def _is_cap(tag):
    return tag.split(".")[-1] in _core.CAPS


def _retag(bm, new_faces, kind, name):
    """After a bevel: the new faces lose what they inherited and take `kind` alone — a
    bevel face is part of neither face it cuts; every edge touching them loses what it
    inherited and, if it is still a real edge, takes `kind` and the cap names of its
    faces. Real: where a new face meets an old one at more than 10°, or two chamfer
    faces meet at more than 40° (a mitre, not a facet of a rounded rim)."""
    bm.faces.index_update()
    bm.edges.index_update()
    bm.faces.ensure_lookup_table()
    bm.normal_update()
    new = {f.index for f in new_faces if f.is_valid}
    face_layers = {lay.name[len(_core.FACE_TAG):]: lay for lay in bm.faces.layers.bool.values()
                   if lay.name.startswith(_core.FACE_TAG)}
    edge_layers = [lay for lay in bm.edges.layers.bool.values() if lay.name.startswith(_core.EDGE_TAG)]
    caps = {t: lay for t, lay in face_layers.items() if _is_cap(t)}
    for i in new:  # Blender copied one neighbour's names, picked by which way the edge runs
        for lay in face_layers.values():
            bm.faces[i][lay] = False
    face_add = {i: {kind, f"{name}.{kind}"} for i in new}
    edge_add = {}
    for e in bm.edges:
        faces = list(e.link_faces)
        if not any(f.index in new for f in faces):
            continue
        for lay in edge_layers:
            e[lay] = False
        e.smooth = True
        inside = all(f.index in new for f in faces)  # between two new faces: a facet, or a mitre
        limit = math.cos(math.radians(40 if kind == "chamfer" else 180)) if inside else math.cos(math.radians(10))
        if len(faces) == 2 and faces[0].normal.dot(faces[1].normal) < limit:
            edge_add[e.index] = {kind, f"{name}.{kind}"} | {t for t, lay in caps.items()
                                                           if any(f[lay] for f in faces)}
    _core.add_tags(bm, face_add, edge_add)
    return sorted(new)


def _bevel(ob, edges, offset, segments, kind, radius=False, verb=None):
    """Bevel the chosen edges by `offset` along each face; with `radius`, `offset` is a
    fillet radius and each edge is set back r·tan(φ/2) for its own bend φ — a true
    radius on a shallow edge as on a square one (edges are bevelled in groups of
    equal bend).

    A loop whose bend changes along it — the cap of a loft of superellipses — falls in
    many groups, and bevelled a group at a time its pieces overlap: the solid comes back
    open, or closed by slivers the export's single precision folds open. Then every
    chosen edge is also bevelled in one operation, each at its own setback
    (`_bevel_weighted`), and that is kept if it is cleaner — fewer open edges, or as many
    and fewer slivers. A bevel that still leaves the solid more open than it was raises."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.normal_update()
    chosen = _named_edges(ob, bm, edges) if not callable(edges) else edges(bm)
    groups, picks = {}, []
    for e in chosen:
        if radius and len(e.link_faces) == 2:
            bend = e.link_faces[0].normal.angle(e.link_faces[1].normal, math.pi / 2)
            setback = round(_core.in_mm(offset * math.tan(min(bend, math.radians(179)) / 2)), 6) / _core.MM
        else:
            setback = offset
        groups.setdefault(setback, []).append(e)
        picks.append((e.index, setback))
    before = (_open_edges(bm), _slivers(bm))
    result = _bevel_groups(ob, bm, _close_setbacks(groups), segments, kind)
    first = (_open_edges(result[0]), _slivers(result[0]))
    if first[0] <= before[0] and first[1] <= before[1]:
        return result
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    again = _bevel_weighted(ob, bm, picks, segments, kind)
    if (_open_edges(again[0]), _slivers(again[0])) < first:
        result[0].free()
        result = again
    else:
        again[0].free()
    if _open_edges(result[0]) > before[0]:
        result[0].free()
        raise ValueError(f"{verb or kind}: {offset:g} on the edges {edges if not callable(edges) else 'sharp'!r} of "
                         f"{_core.given_name(ob)!r} would leave the solid open — it does not fit them: give less, or "
                         f"round the edges in separate calls")
    return result


def _open_edges(bm):
    """How many edges of `bm` do not have exactly two faces: 0 for a closed solid."""
    return sum(1 for e in bm.edges if len(e.link_faces) != 2)


#: An edge shorter than this (mm) is a sliver: a metre-scale export in single precision
#: puts its two ends on one point, and the solid opens there.
SLIVER = 1e-3


def _slivers(bm):
    """How many edges of `bm` are slivers (`SLIVER`)."""
    return sum(1 for e in bm.edges if e.calc_length() < _core.mm(SLIVER))


def _bevel_groups(ob, bm, groups, segments, kind):
    """Bevel each group of edges of `bm` at its setback, the largest first, and weld and
    name what that made: (bm, the new faces)."""
    faces = []
    size = _core.in_mm(1.0)   # Blender's bevel has tolerances of its own, in its units: run it in millimetres
    if size != 1.0:
        bmesh.ops.scale(bm, vec=(size, size, size), verts=bm.verts)
    for setback in sorted(groups, reverse=True):
        geom = [e for e in groups[setback] if e.is_valid]
        if not geom or setback <= 0:
            continue
        out = bmesh.ops.bevel(bm, geom=geom, offset=setback * size, offset_type="OFFSET", segments=segments,
                              profile=0.5, affect="EDGES", clamp_overlap=True, loop_slide=True)
        faces += out["faces"]
    if size != 1.0:
        bmesh.ops.scale(bm, vec=(1 / size,) * 3, verts=bm.verts)
    return _settle_bevel(ob, bm, faces, kind)


def _bevel_weighted(ob, bm, picks, segments, kind):
    """Bevel every picked edge [(index, setback)] of `bm` in one operation, each at
    its own setback, and weld and name what that made: (bm, the new faces). Frees `bm`.

    `bmesh.ops.bevel` takes one offset; Blender's bevel modifier scales its width by an edge
    weight, so every setback is the largest times its share. Its new faces are told apart by
    the material index it gives them; a solid under construction has none of its own
    (`materials.resolve` sets them at export)."""
    if not picks or max(s for _, s in picks) <= 0:
        return _settle_bevel(ob, bm, [], kind)
    size = _core.in_mm(1.0)
    top = max(s for _, s in picks)
    me = bpy.data.meshes.new("_s3d_bevel")
    bm.to_mesh(me)
    bm.free()
    if size != 1.0:
        me.transform(Matrix.Scale(size, 4))
    weight = me.attributes.new("s3d~weight", "FLOAT", "EDGE")
    for i, s in picks:
        weight.data[i].value = s / top
    for p in me.polygons:
        p.material_index = 0
    me.materials.append(None)
    me.materials.append(None)
    temp = bpy.data.objects.new("_s3d_bevel", me)
    mod = temp.modifiers.new("bevel", "BEVEL")
    mod.limit_method, mod.edge_weight, mod.affect = "WEIGHT", "s3d~weight", "EDGES"
    mod.width, mod.offset_type, mod.segments, mod.profile = top * size, "OFFSET", segments, 0.5
    mod.use_clamp_overlap, mod.loop_slide, mod.material = True, True, 1
    try:
        result = _core.evaluated_mesh(temp, preserve_all_data_layers=True)
    finally:
        bpy.data.meshes.remove(me)
    out = bmesh.new()
    out.from_mesh(result)
    bpy.data.meshes.remove(result)
    if size != 1.0:
        bmesh.ops.scale(out, vec=(1 / size,) * 3, verts=out.verts)
    lay = out.edges.layers.float.get("s3d~weight")
    if lay is not None:
        out.edges.layers.float.remove(lay)
    out.faces.ensure_lookup_table()
    faces = [f for f in out.faces if f.material_index == 1]
    for f in out.faces:
        f.material_index = 0
    return _settle_bevel(ob, out, faces, kind)


def _settle_bevel(ob, bm, faces, kind):
    """Weld what a bevel made on `bm` — `faces`, the new ones — and name it: (bm, the new faces)."""
    bm.faces.index_update()
    made = {f.index for f in faces if f.is_valid}
    mark = bm.faces.layers.int.new("s3d~bevel")   # a new layer drops every Python reference: by index
    bm.faces.ensure_lookup_table()
    for i in made:
        bm.faces[i][mark] = 1
    _sort_mesh(bm)   # the welds below collapse in the order they are given, which bevel leaves to the run
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=_core.mm(WELD))   # a bevel clamped to nothing leaves
    bmesh.ops.dissolve_degenerate(bm, dist=_core.mm(WELD), edges=bm.edges)  # zero-width strips: weld them away
    bm.faces.index_update()
    made = [f.index for f in bm.faces if f[mark]]
    bm.faces.layers.int.remove(mark)              # and so does removing it: by index again
    bm.faces.ensure_lookup_table()
    new = _retag(bm, [bm.faces[i] for i in made], kind, _core.given_name(ob))
    bm.faces.ensure_lookup_table()
    return bm, [bm.faces[i] for i in new]


def _close_setbacks(groups):
    """Groups of edges whose setbacks are within 1 % of each other as one, at their mean
    setback: a loop whose faces a boolean split bends by 18.50° here and 18.53° there,
    and bevelled a piece at a time, each piece clamps the next to nothing."""
    runs = []
    for setback in sorted(groups, reverse=True):
        if runs and runs[-1][0] - setback <= 0.01 * runs[-1][0]:
            runs[-1].append(setback)
        else:
            runs.append([setback])
    merged = {}
    for run in runs:
        edges = [e for s in run for e in groups[s]]
        merged[run[0] if len(run) == 1 else sum(s * len(groups[s]) for s in run) / len(edges)] = edges
    return merged


def _sort_mesh(bm):
    """Vertices by position, edges and faces by their vertices: bevel and the boolean modifier
    make them in an order that changes with the run or the machine's thread count. Only
    where nothing holds an element: sorting moves them."""
    def by(seq, rows, dtype, width=None):
        if len(rows) == 0:
            return
        if width is None or all(len(row) == width for row in rows):
            values = np.asarray(rows, dtype=dtype)
        else:
            # A polygon's vertex list sorts before any longer list with that prefix.
            # Keep very wide, mostly empty matrices out of the allocation path.
            if width > 32:
                order = sorted(range(len(rows)), key=rows.__getitem__)
                values = None
            else:
                values = np.full((len(rows), width), -1, dtype=dtype)
                for i, row in enumerate(rows):
                    values[i, :len(row)] = row
        if values is not None:
            if dtype == np.float64 and not np.isfinite(values).all():
                order = sorted(range(len(rows)), key=rows.__getitem__)
            else:
                # lexsort is stable: coincident elements retain their original order.
                order = np.lexsort(values[:, ::-1].T)
        ranks = np.empty(len(rows), dtype=np.intp)
        ranks[order] = np.arange(len(rows))
        rank = dict(zip(seq, map(int, ranks)))
        seq.sort(key=rank.__getitem__)
        seq.index_update()
    by(bm.verts, [tuple(v.co) for v in bm.verts], np.float64)
    edge_keys = np.fromiter((v.index for e in bm.edges for v in e.verts),
                            dtype=np.int32, count=2 * len(bm.edges)).reshape(-1, 2)
    edge_keys.sort(axis=1)
    by(bm.edges, edge_keys, np.int32)
    rows = [[v.index for v in f.verts] for f in bm.faces]
    by(bm.faces, rows, np.int32, max(map(len, rows), default=0))


def fillet(ob, r, edges="all"):
    """Round named edges.

    Round the edges named `edges` ("top", "top side", ["hole", "cut"]; "all": every
    named edge) to radius `r`. Where it does not fit, the radius is clamped; a radius
    that would leave the solid open raises."""
    _solids("fillet", ob)
    bm, _ = _bevel(ob, edges, r, max(2, _core.segments(r, 90)), "fillet", radius=True, verb="fillet")
    _sort_mesh(bm)
    _replace_mesh(ob, bm)
    return ob


def chamfer(ob, d, edges="all", d2=None, angle=None):
    """Bevel named edges.

    Cut the edges named `edges` by `d` on both faces; or `d` on the face the edge is
    named after (`top` for a top edge) and `d2` on the other — or the other at `angle`
    degrees from it."""
    _solids("chamfer", ob)
    if angle is not None:
        if not 1 <= angle < 90:
            raise ValueError(f"chamfer: angle is the face angle in degrees, from 1 up to 90, not {angle:.4g}"
                             + (" — radians? give degrees" if 0 < angle < 1 else ""))
        d2 = d * math.tan(math.radians(angle))
    base = d if d2 is None else min(d, d2)   # cut equal first, as far as both faces allow
    bm, faces = _bevel(ob, edges, base, 1, "chamfer", verb="chamfer")
    if d2 is not None and (abs(d2 - base) > _core.mm(1e-9) or abs(d - base) > _core.mm(1e-9)):
        _stretch(bm, faces, base, d, d2)
    _sort_mesh(bm)
    _replace_mesh(ob, bm)
    return ob


def _stretch(bm, strip, base, d, d2):
    """Move the rails of an equal chamfer cut `base` deep: the one on the face the edge
    is named after to `d` off the edge it replaced, the other to `d2` — each within its
    own face, square to the rail, away from the edge."""
    caps = [lay for lay in bm.faces.layers.bool.values()
            if lay.name.startswith(_core.FACE_TAG) and _is_cap(lay.name[len(_core.FACE_TAG):])]
    strip = [f for f in strip if f.is_valid and len(f.verts) == 4]
    chamfer_faces = set(strip)
    bm.normal_update()
    moves = {}
    for f in strip:
        side = {v: any(g[lay] for g in v.link_faces if g not in chamfer_faces for lay in caps) for v in f.verts}
        on_cap = [v for v in f.verts if side[v]]
        off_cap = [v for v in f.verts if not side[v]]
        if len(on_cap) != 2 or len(off_cap) != 2:
            continue
        for rail, other, target in ((off_cap, on_cap, d2), (on_cap, off_cap, d)):
            if abs(target - base) < _core.mm(1e-12):
                continue
            along = rail[1].co - rail[0].co
            if along.length < _core.mm(1e-12):
                continue
            t = along.normalized()
            edge = next((e for e in rail[0].link_edges if e.other_vert(rail[0]) is rail[1]), None)
            faces = [g for g in edge.link_faces if g is not f] if edge else []
            if not faces:
                continue
            n = faces[0].normal
            for v in rail:
                partner = min(other, key=lambda o: (o.co - v.co).length)
                u = v.co - partner.co
                u = u - n * u.dot(n)
                u = u - t * u.dot(t)
                if u.length > _core.mm(1e-12):
                    moves.setdefault(v, []).append(v.co + u.normalized() * (target - base))
    for v, targets in moves.items():
        v.co = sum(targets, Vector()) / len(targets)


def soften(ob, r, angle=30):
    """Round all sharp edges.

    Round every edge whose faces meet at more than `angle` degrees to radius `r` — a
    whole object eased, the way a moulded or worn part is."""
    _solids("soften", ob)
    limit = math.radians(angle)

    def sharp(bm):
        bm.normal_update()
        return [e for e in bm.edges if len(e.link_faces) == 2
                and e.link_faces[0].normal.angle(e.link_faces[1].normal, 0) > limit]
    bm, _ = _bevel(ob, sharp, r, max(2, _core.segments(r, 90)), "fillet", radius=True, verb="soften")
    _sort_mesh(bm)
    _replace_mesh(ob, bm)
    return ob


# ---------------------------------------------------------------- shell

def _named_faces(ob, names):
    layers = {a.name[len(_core.FACE_TAG):]: a for a in ob.data.attributes if a.name.startswith(_core.FACE_TAG)}
    missing = [n for n in names if _core.stored(_core.FACE_TAG, n) not in layers]
    if missing:
        raise ValueError(_core.unknown(_core.given_name(ob), "face", missing, sorted(layers)))
    return {i for n in names for i, d in enumerate(layers[_core.stored(_core.FACE_TAG, n)].data) if d.value}


#: How a curved side is opened, said by `shell` when it is asked to open one by direction.
CUT_FLAT = ("a curved side is opened by cutting it flat first: s3d.split(ob, frame) or s3d.cut(ob, tool), then "
            "shell(ob, t, open=\"cut\") (or the tool's name)")
#: A crease, in degrees: two faces meeting at more (`_retag`'s rule for a real edge).
CREASE = 10
#: Where the faces a direction picks run on smoothly into others, they are a face only if they
#: are this many times the area of the faces they run on into: a flat top blending into a fillet
#: is; the one or two facets at the top of a superellipse (96 of them round) are not.
FACE_SPAN = 4


def _facets(ob, picked):
    """Whether the faces `picked` of `ob` (indices, flat, looking one way) are facets of a curved
    side rather than a face: they run on into the faces round them without a crease
    (`CREASE`), and are not much larger than those (`FACE_SPAN`)."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    limit = math.radians(CREASE)
    smooth = set()
    for i in picked:
        f = bm.faces[i]
        for e in f.edges:
            for g in e.link_faces:
                if g.index not in picked and f.normal.angle(g.normal, math.pi) < limit:
                    smooth.add(g.index)
    area = sum(bm.faces[i].calc_area() for i in picked)
    around = sum(bm.faces[i].calc_area() for i in smooth)
    bm.free()
    return bool(smooth) and area < FACE_SPAN * around


def shell(ob, t, open=None):
    """Hollow; open named faces, or the flat faces looking "+Y", "-X +X".

    Hollow `ob`, leaving walls `t` thick inside its surface; the faces `open` gives are
    taken away: by name ("top", ["top", "start"]), or by the way they look ("+Y",
    "-X +X"), as `ob.face` reads a direction — the flat face furthest that way. Names
    and directions mix ("top -Y"). A curved side has no such face, even where its facets
    look that way: it is refused, and opened by cutting it flat first. Without `open`, a
    closed void."""
    from .frames import _DIRECTION, _facing
    _solids("shell", ob)
    terms = _names(open) or []
    ways = [w for w in terms if _DIRECTION.match(w)]
    names = [w for w in terms if not _DIRECTION.match(w)]
    opened = _named_faces(ob, names) if names else set()
    for way in ways:
        found = _facing(ob, way)
        if not found:
            raise ValueError(f"shell: {_core.given_name(ob)!r} has no flat face looking {way} to open — {CUT_FLAT}")
        if _facets(ob, {p.index for p in found}):
            raise ValueError(f"shell: {_core.given_name(ob)!r} has no flat face looking {way}: the faces furthest "
                             f"that way are facets of a curved side, a strip and not a face — a face its maker "
                             f"named opens by its name (open=\"top\"); {CUT_FLAT}")
        opened |= {p.index for p in found}
    me = ob.data
    normals = [p.normal.copy() for p in me.polygons]
    planes = {v.index: [] for v in me.vertices}
    for p in me.polygons:
        for v in p.vertices:
            planes[v].append((normals[p.index], 1.0 if p.index in opened else -1.0))
    inner = bmesh.new()
    bverts = []
    for v in me.vertices:
        bverts.append(inner.verts.new(v.co + _offset(planes[v.index], t)))
    for p in me.polygons:
        inner.faces.new([bverts[i] for i in p.vertices])
    tool_mesh = bpy.data.meshes.new("shell")
    inner.to_mesh(tool_mesh)
    inner.free()
    tool = _core.link(bpy.data.objects.new("shell", tool_mesh))
    tool[_core.NAME] = "shell"
    tool.matrix_basis, tool.parent = ob.matrix_basis, ob.parent
    return _boolean(ob, [tool], "DIFFERENCE", strip=True, self_intersect=True, verb="shell")


def _offset(planes, t):
    """The move that puts a vertex `t` inside every distinct face plane it touches (or
    `t` outside those marked +1): least squares over the planes, even thickness.

    Solved in double precision — `Matrix` is float32, and the planes of a smooth surface
    leave the system ill-conditioned (two planes 3.6° apart: 1e6), which float32 turns
    to noise. A direction the planes barely pin down (under `_WEAK` of the strongest:
    the edge two planes share, the slack of near-parallel faces) is left alone: the
    vertex stays put along it, instead of sliding sideways to satisfy a hair of
    disagreement between the normals."""
    distinct = []
    for n, s in planes:
        if all(n.dot(m) < 0.9999 or s != r for m, r in distinct):
            distinct.append((n, s))
    if len(distinct) == 1:
        n, s = distinct[0]
        return n * (s * t)
    a = [[0.0] * 3 for _ in range(3)]
    b = [0.0] * 3
    for n, s in distinct:
        for i in range(3):
            b[i] += n[i] * (s * t)
            for j in range(3):
                a[i][j] += n[i] * n[j]
    w, v = _eigen3(a)
    x = [0.0] * 3
    for k in range(3):
        if w[k] >= _WEAK * max(w):
            c = sum(v[i][k] * b[i] for i in range(3)) / w[k]
            for i in range(3):
                x[i] += v[i][k] * c
    return Vector(x)


_WEAK = 0.03


def _eigen3(a):
    """Eigenvalues and eigenvectors (the columns of `v`) of the symmetric 3x3 `a`, by
    Jacobi rotations in double precision: deterministic, and exact for equal values
    (a corner of three square planes has three)."""
    a = [row[:] for row in a]
    v = [[float(i == j) for j in range(3)] for i in range(3)]
    for _ in range(16):
        if abs(a[0][1]) + abs(a[0][2]) + abs(a[1][2]) <= 1e-15 * (a[0][0] + a[1][1] + a[2][2]):
            break
        for p, q in ((0, 1), (0, 2), (1, 2)):
            if a[p][q] == 0.0:
                continue
            theta = (a[q][q] - a[p][p]) / (2.0 * a[p][q])
            tan = math.copysign(1.0, theta) / (abs(theta) + math.sqrt(theta * theta + 1.0))
            c = 1.0 / math.sqrt(tan * tan + 1.0)
            s = tan * c
            for k in range(3):
                a[k][p], a[k][q] = c * a[k][p] - s * a[k][q], s * a[k][p] + c * a[k][q]
            for k in range(3):
                a[p][k], a[q][k] = c * a[p][k] - s * a[q][k], s * a[p][k] + c * a[q][k]
            for k in range(3):
                v[k][p], v[k][q] = c * v[k][p] - s * v[k][q], s * v[k][p] + c * v[k][q]
    return [a[0][0], a[1][1], a[2][2]], v


# ---------------------------------------------------------------- whole objects

def copy(ob, name=None):
    """Copy with joints. A string names a single object. Lists copy in order and accept only a dict to rename parts and joints.

    A {old: new} dict applies across all copied trees. Every key must match.
    A joint between list elements connects their copies in the result."""
    from .assembly import Handle
    from .joints import remap
    if isinstance(ob, (list, tuple)):
        if isinstance(name, str):
            raise TypeError("copy: use a name dict for a list of parts")
        roots = _flat(ob)
        children, twins = _children(), {}
        names = _names_held(roots, children, name) if name is not None else None
        copies = [_copy(root, children, twins, names) for root in roots]
        remap(twins)
        return copies
    if name is None:
        return _copy(ob)
    root = ob.root if isinstance(ob, Handle) else ob
    children = _children() if root.children else {}
    return _copy(ob, children, names=_names_held([root], children, name))


def _copy(ob, children=None, seen=None, names=None):
    """Copy one tree and collect its objects for joint remapping across roots."""
    from .assembly import Handle
    root = ob.root if isinstance(ob, Handle) else ob
    twins = _copy_tree(root, children)
    if names is not None:
        _renamed(twins, *names)
    if seen is not None:
        seen.update(twins)
    if not isinstance(ob, Handle):
        return twins[root]
    memo = {id(o): twins.get(o, o) for o in _ids(vars(ob))}   # an object anchor becomes its twin
    handle = object.__new__(type(ob))
    handle.__dict__.update(deepcopy(vars(ob), memo))
    return handle


def _names_held(roots, children, name):
    """`copy`'s `name`, read against the roots before it is copied: ({original: its
    copy's name}, {joint name: its copy's}) — a string names the root; a dict names every
    object whose given name is a key, and every joint named so. A name held by nothing,
    or one that is no string, is refused, and no copy is made."""
    from . import joints
    if isinstance(name, str):
        return {roots[0]: _checked_name(name)}, {}
    if not isinstance(name, dict):
        raise TypeError(f"copy: name is the copy's name, a string, or {{old: new}} for what it holds, "
                        f"not {name!r}")
    objects, named_joints, taken = {}, {}, set()
    tree = list(roots)
    for ob in tree:
        tree += children.get(ob, [])
        given = _core.given_name(ob)
        if given in name:
            objects[ob] = _checked_name(name[given])
            taken.add(given)
        for j in joints.joints_of(ob):
            if j["name"] in name:
                named_joints[j["name"]] = _checked_name(name[j["name"]])
                taken.add(j["name"])
    left = [k for k in name if k not in taken]
    if left:
        held = ", ".join(repr(k) for k in left)
        raise ValueError(f"copy: name {held}: the copy holds no part, group or joint so named")
    return objects, named_joints


def _renamed(twins, objects, named_joints):
    """The copies ({original: twin}) named as `_names_held` read it."""
    from . import joints
    for original, twin in twins.items():
        if original in objects:
            _rename(twin, objects[original])
    if named_joints:
        for twin in twins.values():
            js = joints.joints_of(twin)
            if any(j["name"] in named_joints for j in js):
                for j in js:
                    j["name"] = named_joints.get(j["name"], j["name"])
                joints._write(twin, js)


def _checked_name(new):
    if not isinstance(new, str) or not new:
        raise TypeError(f"copy: a name is a string, not {new!r}")
    return new


def _rename(ob, new):
    """`ob` named `new`: its given name, and Blender's, which the GLB's nodes carry; its
    mesh too, which the GLB's meshes carry."""
    ob[_core.NAME] = _checked_name(new)
    ob.name = new
    if ob.data is not None:
        _core.own_mesh(ob).name = new


def _twin(ob):
    """A new object like `ob` — placement, custom properties, a shared mesh until edited —
    in the scene, under the same parent."""
    twin = ob.copy()
    if ob.data is not None and ob.type != "MESH":
        twin.data = ob.data.copy()
    twin[_core.NAME] = _core.given_name(ob)   # a group has none; the copy's own name is suffixed
    return _core.link(twin)


def _children():
    """{parent: [children]} over the scene, in one pass."""
    out = {}
    for o in bpy.data.objects:
        if o.parent is not None:
            out.setdefault(o.parent, []).append(o)
    return out


def _copy_tree(root, children=None):
    """`root` and everything under it as new objects: {original: copy}."""
    if children is None:
        children = _children() if root.children else {}
    twins = {}

    def walk(ob, parent):
        twins[ob] = twin = _twin(ob)
        twin.parent = parent
        for child in children.get(ob, ()):
            walk(child, twin)
    walk(root, root.parent)
    from .joints import remap
    remap(twins)                         # a joint inside the copy hangs on the copy of its parent
    return twins


def _ids(value, seen=None):
    """The Blender objects reachable from an anchor, through containers and attributes."""
    seen = set() if seen is None else seen
    if id(value) in seen:
        return []
    seen.add(id(value))
    if isinstance(value, bpy.types.ID):
        return [value]
    if isinstance(value, dict):
        items = list(value.values())
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    elif hasattr(value, "__dict__") and not isinstance(value, type):
        items = list(vars(value).values())
    else:
        return []
    return [i for item in items for i in _ids(item, seen)]


def merge(*obs):
    """No boolean.

    One object holding the meshes of `obs`, untouched — no boolean: parts that
    touch stay separate shells. The first object's name is kept; the others are used up.
    A boolean on it later fuses its shells first."""
    from ._surface import meshes as mesh_parts
    roots = _flat(obs)
    containers = list(dict.fromkeys(o for root in roots for o in [root, *root.children_recursive] if o.type != "MESH"))
    obs = mesh_parts(roots)
    first, others = obs[0], obs[1:]
    refuse_using_up(others, "merge")
    _guard.using_up(others, first)
    to_local = _core.world(first).inverted()
    meshes = [(first.data, Matrix.Identity(4))] + [(o.data, to_local @ _core.world(o)) for o in others]
    bm = _concat(meshes)
    _replace_mesh(first, bm, keep_shading=True)
    first[_core.MERGED_SHADING] = True
    if others:
        first[MERGED] = True
    for o in others:
        delete(o)
    for o in reversed(containers):
        delete(o)
    return first


def _mesh_array(elements, prop, width=1, dtype=np.int32):
    values = np.empty(len(elements) * width, dtype=dtype)
    elements.foreach_get(prop, values)
    if dtype == np.float32:
        # Reading RNA scalars through Python quiets signaling NaNs. Match that
        # conversion while preserving their payload, sign, and all finite bits.
        bits = values.view(np.uint32)
        bits[np.isnan(values)] |= np.uint32(0x00400000)
    return values.reshape(-1, width) if width != 1 else values


def _mesh_geometry(parts):
    """Coordinates and polygon loops in input order, with reflected rings reversed."""
    coordinates, vertices, sizes = [], [], []
    base = 0
    for me, matrix in parts:
        # Keep mathutils' single-precision multiply and addition order.
        coordinates.extend(matrix @ v.co for v in me.vertices)
        ring = _mesh_array(me.loops, "vertex_index")
        count = _mesh_array(me.polygons, "loop_total")
        if matrix.to_3x3().determinant() < 0:
            starts = np.repeat(np.cumsum(count) - count, count)
            ring = ring[2 * starts + np.repeat(count, count) - 1 - np.arange(len(ring))]
        vertices.append(ring + base)
        sizes.append(count)
        base += len(me.vertices)
    return (np.asarray(coordinates, dtype=np.float32).reshape(-1, 3),
            np.concatenate(vertices), np.concatenate(sizes))


def _concat(meshes):
    """The meshes, each moved by its matrix, as one bmesh; tag attributes kept."""
    co, rings, counts = _mesh_geometry(meshes)
    starts = np.cumsum(counts, dtype=np.int32) - counts
    # BM_face_create_verts creates the closing edge first, then the ring's edges.
    previous = np.arange(len(rings)) - 1
    previous[starts] = starts + counts - 1
    pairs = np.column_stack((rings[previous], rings))
    keys = np.sort(pairs, axis=1)
    unique, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    order = np.argsort(first)
    rank = np.empty(len(order), dtype=np.int32)
    rank[order] = np.arange(len(order))
    edges = pairs[first[order]]
    mesh = bpy.data.meshes.new("_s3d_concat")
    try:
        mesh.vertices.add(len(co))
        mesh.vertices.foreach_set("co", co.ravel())
        mesh.edges.add(len(edges))
        mesh.edges.foreach_set("vertices", edges.ravel())
        mesh.loops.add(len(rings))
        mesh.loops.foreach_set("vertex_index", rings)
        # A loop uses its outgoing edge, rather than its incoming edge.
        following = np.arange(len(rings)) + 1
        following[starts + counts - 1] = starts
        mesh.loops.foreach_set("edge_index", rank[inverse[following]])
        mesh.polygons.add(len(counts))
        mesh.polygons.foreach_set("loop_start", starts)
        mesh.polygons.foreach_set("loop_total", counts)
        supported = {"FLOAT": ("value", 1, np.float32), "INT": ("value", 1, np.int32),
                     "BOOLEAN": ("value", 1, np.bool_), "FLOAT_VECTOR": ("vector", 3, np.float32)}
        point = {}
        face = {}
        face_tags, edge_tags = set(), set()
        for me, _ in meshes:
            for a in me.attributes:
                if a.domain == "POINT" and a.data_type == "FLOAT":
                    point.setdefault(a.name, "FLOAT")
                if a.domain == "FACE" and a.data_type in supported and not a.name.startswith(_core.FACE_TAG):
                    face[a.name] = a.data_type
                if a.name.startswith(_core.FACE_TAG) and np.any(_mesh_array(a.data, "value", dtype=np.bool_)):
                    face_tags.add(a.name)
                if a.name.startswith(_core.EDGE_TAG) and np.any(_mesh_array(a.data, "value", dtype=np.bool_)):
                    edge_tags.add(a.name)
        def attribute(name, kind, domain, values):
            prop, width, dtype = supported[kind]
            a = mesh.attributes.get(name)
            if a is None:
                a = mesh.attributes.new(name, kind, domain)
            a.data.foreach_set(prop, np.asarray(values, dtype=dtype).ravel())

        def concatenate(name, kind, domain, default=0):
            prop, width, dtype = supported[kind]
            arrays = []
            for me, _ in meshes:
                a = me.attributes.get(name)
                n = len(me.vertices) if domain == "POINT" else len(me.polygons)
                arrays.append(_mesh_array(a.data, prop, width, dtype) if a is not None else
                              np.full((n, width) if width != 1 else n, default, dtype=dtype))
            return np.concatenate(arrays)

        for name, kind in point.items():
            attribute(name, kind, "POINT", concatenate(name, kind, "POINT", float("nan")))
        for name in sorted(face_tags):
            attribute(name, "BOOLEAN", "FACE", concatenate(name, "BOOLEAN", "FACE"))
        # Map source edge indices to the edges that face creation retained.
        source_keys, sharp = [], []
        base = 0
        for me, _ in meshes:
            source_keys.append(np.sort(_mesh_array(me.edges, "vertices", 2) + base, axis=1))
            sharp.append(_mesh_array(me.edges, "use_edge_sharp", dtype=np.bool_))
            base += len(me.vertices)
        source_keys = np.concatenate(source_keys)
        stride = max(len(co), 1)
        encoded = unique[:, 0].astype(np.int64) * stride + unique[:, 1]
        source = source_keys[:, 0].astype(np.int64) * stride + source_keys[:, 1]
        found = np.searchsorted(encoded, source)
        valid = found < len(encoded)
        valid[valid] &= encoded[found[valid]] == source[valid]
        target = np.zeros(len(source), dtype=np.int32)
        target[valid] = rank[found[valid]]
        edge_sharp = np.zeros(len(edges), dtype=np.bool_)
        edge_sharp[target[valid]] = np.concatenate(sharp)[valid]
        for name in sorted(edge_tags):
            values = np.concatenate([_mesh_array(me.attributes[name].data, "value", dtype=np.bool_)
                                     if name in me.attributes else np.zeros(len(me.edges), dtype=np.bool_)
                                     for me, _ in meshes])
            out = np.zeros(len(edges), dtype=np.bool_)
            out[target[valid]] = values[valid]
            if np.any(out):
                attribute(name, "BOOLEAN", "EDGE", out)
                edge_sharp |= out
        for name, kind in face.items():
            attribute(name, kind, "FACE", concatenate(name, kind, "FACE"))
        smooth = np.concatenate([_mesh_array(me.polygons, "use_smooth", dtype=np.bool_) for me, _ in meshes])
        mesh.polygons.foreach_set("use_smooth", smooth)
        mesh.edges.foreach_set("use_edge_sharp", edge_sharp)
        # Reserved face attributes used to be custom bmesh layers, not flags.
        aliases = {}
        for name in (".select_poly", ".hide_poly", "material_index"):
            if name in face:
                a = mesh.attributes[name]
                a.name = "_s3d_concat_" + name
                aliases[name] = a.name
        bm = bmesh.new()
        for name in point:
            bm.verts.layers.float.new(name)
        for name in sorted(face_tags):
            bm.faces.layers.bool.new(name)
        for name in sorted(edge_tags):
            if name in mesh.attributes:
                bm.edges.layers.bool.new(name)
        layers = {"FLOAT": "float", "INT": "int", "BOOLEAN": "bool", "FLOAT_VECTOR": "float_vector"}
        for name, kind in face.items():
            getattr(bm.faces.layers, layers[kind]).new(name)
        bm.from_mesh(mesh)
        if aliases:
            for elements in (bm.verts, bm.edges, bm.faces):
                for element in elements:
                    element.select = False
                    element.hide = False
        for name, alias in aliases.items():
            collection = getattr(bm.faces.layers, layers[face[name]])
            source, target_layer = collection[alias], collection[name]
            for polygon in bm.faces:
                polygon[target_layer] = polygon[source]
            collection.remove(source)
        bm.normal_update()
        return bm
    finally:
        bpy.data.meshes.remove(mesh)


def scale(ob, s):
    """About its origin; a group or an assembly whole, by one factor s > 0.

    `ob`'s mesh scaled about its own origin: one factor, or (sx, sy, sz). A group or an
    assembly (its handle) scales whole about its own origin, in place, by one factor
    `s` > 0: every point under it goes from p to s·p of its space — each mesh, and
    where each part sits — while it stays where it is in its parent, its parts keep
    their turns, materials, shading and faces, and a later `at` on a part keeps the
    scaled place. Frames and anchors already read — a handle's included, numbers as
    they are — do not follow: read `bbox`, faces and `local` again, or rebuild the
    anchors, after scaling. Not on a group with joints in it, on it or across it."""
    from .assembly import Handle
    if isinstance(ob, Handle) or isinstance(ob, bpy.types.Object) and ob.type == "EMPTY":
        _scale_tree(ob, s)
        return ob
    _solids("scale", ob)
    sx, sy, sz = (s, s, s) if isinstance(s, (int, float)) else s
    _core.own_mesh(ob)
    ob.data.transform(Matrix.Diagonal((sx, sy, sz, 1)))
    if sx * sy * sz < 0:
        ob.data.flip_normals()
    _core.shade_mesh(ob)
    return ob


def _group_factor(s, name):
    """The one factor a group scales by, or what to write instead."""
    if isinstance(s, bool) or not isinstance(s, numbers.Real) and not isinstance(s, (list, tuple, Vector)):
        raise TypeError(f"scale: {name!r} is a group: it scales by one number s > 0, not {s!r}")
    if not isinstance(s, numbers.Real):
        raise ValueError(f"scale: {name!r} is a group: it scales by one factor, not {tuple(s)} — a different factor "
                         f"per axis would shear its turned parts. Scale each solid with s3d.scale(part, (sx, sy, sz)), "
                         f"or give the size to the function that builds the group")
    s = float(s)
    if not math.isfinite(s):
        raise ValueError(f"scale: {name!r} scales by a finite number, not {s}")
    if s == 0:
        raise ValueError(f"scale: {name!r} scaled by 0 would shrink to a point: give a factor s > 0, or s3d.delete it")
    if s < 0:
        raise ValueError(f"scale: {name!r} is a group: it scales by s > 0, not {s:g} — a mirror image is "
                         f"s3d.transform({_guard._code(name)}, mirror=\"xyz\") then s3d.scale({_guard._code(name)}, {-s:g})")
    return s


def _scale_refusal(root, tree):
    """Why the tree under `root` cannot scale, joint-wise, or None. The kinematic tree is
    apart from the scene's: what hangs on, or follows, a part of the group is checked over
    the whole scene."""
    from . import joints
    name = _core.given_name(root)
    for o in tree:
        found = joints.joints_of(o)
        if found:
            return (f"scale: {_core.given_name(o)!r} moves by its joint {found[0]['name']!r}: scaling {name!r} would "
                    f"move its pivot and its range with it — scale {name!r} before declaring its joints, or build it "
                    f"at its size")
        if o.type not in ("MESH", "EMPTY"):
            return f"scale: {_core.given_name(o)!r} under {name!r} is a {o.type.lower()} object, not a solid or a group"
    carrier = joints.body(root.parent)
    if carrier is not None:
        return (f"scale: {name!r} is carried by {_core.given_name(carrier)!r}, which moves by its joint "
                f"{joints.joints_of(carrier)[0]['name']!r}: scale {name!r} before it goes into the mechanism, or "
                f"build it at its size")
    inside = {o.as_pointer() for o in tree}
    for o in joints.everything():
        if o.as_pointer() in inside:
            continue
        held = [(k, o[k]) for k in o.keys() if k == joints.PARENT or k.startswith(joints.FOLLOWS)]
        for key, other in held:
            if other is not None and not _guard.removed(other) and other.as_pointer() in inside:
                how = "hangs on" if key == joints.PARENT else "follows"
                return (f"scale: {_core.given_name(o)!r} {how} {_core.given_name(other)!r}, inside {name!r}, by its "
                        f"joint {joints.joints_of(o)[0]['name']!r}: scaling {name!r} would move the pivot out from "
                        f"under it — scale {name!r} before declaring that joint, or build it at its size")
    return None


def _scale_tree(ob, s):
    """`scale` on a group or a handle: a uniform similarity about the root's origin, baked.
    Each mesh's own coordinates are multiplied by s; under the root, each placement's
    translation — and its parent inverse's — too, which is the placement conjugated by
    the scale: turns, and any scale Blender holds, stay. The root keeps its placement.
    What `at` remembers of each part is conjugated the same way, so a later `at` keeps
    the scaled place. Everything is checked before anything changes."""
    from . import joints
    from .assembly import Handle
    from .frames import PLACE, _recalled, _remember
    root = ob.root if isinstance(ob, Handle) else ob
    if not isinstance(root, bpy.types.Object):
        raise TypeError(f"scale: a handle's root is an object, not {type(root).__name__}")
    name = _core.given_name(root)
    s = _group_factor(s, name)
    children = _children() if root.children else {}
    tree = [root]
    for o in tree:
        tree += children.get(o, [])
    refusal = _scale_refusal(root, tree)
    if refusal:
        raise ValueError(refusal)

    inside = {o.as_pointer() for o in tree}
    outside = {u.data.as_pointer() for u in bpy.data.objects
               if u.type == "MESH" and u.as_pointer() not in inside}
    meshes = {}
    for o in tree:
        if o.type != "MESH":
            continue
        if o.data.as_pointer() in outside:
            o.data = o.data.copy()            # a mesh shared with a part outside: this one gets its own
        meshes.setdefault(o.data.as_pointer(), o.data)
    kept = {o: _recalled(o) for o in tree[1:] if o.get(PLACE) is not None}   # before the placements change
    for o in tree[1:]:
        o.location = o.location * s
        o.delta_location = o.delta_location * s
        inverse = Matrix(o.matrix_parent_inverse)
        inverse.translation = inverse.translation * s
        o.matrix_parent_inverse = inverse
    for o, (frame, values, anchor, point) in kept.items():
        if frame is not None:
            frame = Matrix(frame)
            frame.translation = frame.translation * s
        values = {k: v * s if k in ("x", "y", "z") else v for k, v in values.items()}
        _remember(o, frame, values, anchor, point * s)
    for me in meshes.values():
        me.transform(Matrix.Scale(s, 4))
        me.update()
    joints.placed_again(root)                 # a part placed on a frame read on a part sits there as scaled


# ---------------------------------------------------------------- upholstery

def dent(ob, points, r, depth, *, coords="local"):
    """Press hollows at points.

    Press the surface in at each of `points`: a round hollow of radius `r`, `depth` deep
    at its centre — how upholstery is buttoned. Points and frame origins are in the
    mesh's local space by default. coords="parent" reads them in the space `ob` is in,
    as `snap` and `scatter(ob)` give them, wherever `ob` has been placed."""
    _solids("dent", ob)
    if coords not in ("local", "parent"):
        raise ValueError('dent: coords is "local" or "parent"')
    centres = [Vector(p.origin if isinstance(p, Frame) else p) for p in points]
    if coords == "parent":
        own = ob.matrix_basis.inverted()
        centres = [own @ p for p in centres]
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    vertices = None
    for c in centres:
        if vertices is None:
            vertices = _vertex_tree(bm)
        if _densify(bm, c, r, vertices=vertices):
            vertices = None
    bm.normal_update()
    tree = KDTree(len(bm.verts))
    for v in bm.verts:
        tree.insert(v.co, v.index)
    tree.balance()
    moves = {}
    for c in centres:
        for co, index, dist in tree.find_range(c, r):
            moves[index] = moves.get(index, 0) + depth * (1 - (dist / r) ** 2) ** 2
    bm.verts.ensure_lookup_table()
    for index, push in moves.items():
        v = bm.verts[index]
        v.co -= v.normal * push
    _core.own_mesh(ob)
    bm.to_mesh(ob.data)
    bm.free()
    _core.shade_mesh(ob)
    return ob


def _vertex_tree(bm):
    tree = KDTree(len(bm.verts))
    for i, v in enumerate(bm.verts):
        tree.insert(v.co, i)
    tree.balance()
    return tree


def _densify(bm, c, r, cuts=4, *, vertices=None):
    """Give the surface round `c` vertices to press: where none lies within r/`cuts` of
    it (a flat face meshed as one n-gon has none), cut the faces within `r` of it by
    planes r/`cuts` apart, both ways across the nearest face's normal."""
    if vertices is None:
        vertices = _vertex_tree(bm)
    radius = r / cuts
    # KDTree uses float distances. Widen only the candidate search, then retain
    # the original Vector subtraction and strict predicate at the boundary.
    margin = max(radius, *(abs(x) for x in c)) * 1e-6
    if any((co - c).length < radius for co, index, distance in vertices.find_range(c, radius + margin)):
        return False
    bm.faces.ensure_lookup_table()
    tree = BVHTree.FromBMesh(bm)
    near = tree.find_nearest_range(c, r)
    if not near:
        return
    n = min(near, key=lambda hit: (hit[3], hit[2]))[1]
    u = n.orthogonal().normalized()
    for axis in (u, n.cross(u).normalized()):
        for k in range(-cuts + 1, cuts):
            faces = {bm.faces[hit[2]] for hit in near}
            geom = list(faces) + list({e for f in faces for e in f.edges}) + list({v for f in faces for v in f.verts})
            bmesh.ops.bisect_plane(bm, geom=geom, dist=_core.mm(WELD), plane_co=c + axis * (k * r / cuts), plane_no=axis)
            bm.faces.ensure_lookup_table()
            near = BVHTree.FromBMesh(bm).find_nearest_range(c, r)
    return True


# ---------------------------------------------------------------- organic surfaces: blend, displace

#: The most faces `blend` builds: its voxels are r / 5, and a voxel remesh gives about one face
#: per voxel² of surface, three times over (a ball 100 across at r = 2 takes ~200 000, in seconds).
BLEND_FACES = 600_000
#: How far, in voxels, a blend may stand beyond its parts' box: a closing never grows a shape past
#: it, and the voxels round it off by less than this.
BLEND_REACH = 1.5


def _number(verb, what, value, positive=False):
    """`value` as a float, or a clear error: a number, more than 0 if `positive`."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise TypeError(f"{verb}: {what} is a number, not {value!r}")
    if positive and value <= 0:
        raise ValueError(f"{verb}: {what} is a length, more than 0, not {value:g}")
    return float(value)


def _soup(parts):
    """One mesh holding the faces of every (mesh, matrix), moved by it and facing out."""
    co, rings, counts = _mesh_geometry(parts)
    mesh = bpy.data.meshes.new("_s3d_blend")
    mesh.vertices.add(len(co))
    mesh.vertices.foreach_set("co", co.ravel())
    mesh.loops.add(len(rings))
    mesh.loops.foreach_set("vertex_index", rings)
    mesh.polygons.add(len(counts))
    mesh.polygons.foreach_set("loop_start", np.cumsum(counts, dtype=np.int32) - counts)
    mesh.polygons.foreach_set("loop_total", counts)
    # Match from_pydata's default shading and Blender's inferred edge order.
    mesh.shade_flat()
    if len(counts):
        mesh.update(calc_edges=True, calc_edges_loose=False)
    return mesh


def _closing(mesh, r, voxel):
    """The morphological closing of the solid `mesh` by a ball of radius `r`, with modifiers
    only: voxel-remesh the union, push every point out by r along its normal, remesh (which
    resolves where the pushed surface crosses itself), pull it back by r, remesh. The pull is
    the exact offset wherever the surface bends less than 1 / r, which the push guarantees.
    Remesh and Displace give the same mesh in every run and under bpy 4.5 and 5.x."""
    holder = bpy.data.objects.new("_s3d_blend", mesh)
    try:
        def remesh():
            mod = holder.modifiers.new("remesh", "REMESH")
            mod.mode, mod.voxel_size, mod.adaptivity = "VOXEL", voxel, 0.0
        remesh()
        for d in (r, -r):
            mod = holder.modifiers.new("offset", "DISPLACE")
            mod.direction, mod.mid_level, mod.strength = "NORMAL", 0.0, d
            remesh()
        result = _core.evaluated_mesh(holder)
    finally:
        bpy.data.meshes.remove(mesh)
    bm = bmesh.new()
    bm.from_mesh(result)
    bpy.data.meshes.remove(result)
    return bm


def _facet_surface(bm):
    """Collapse a reconstructed surface toward equilateral triangles of target edge.

    Keep the fine voxel closing (and its thin-part guards); only simplify the result.
    Explicit input topology such as hull points is never decimated.
    """
    extent = _span([c for v in bm.verts for c in v.co])
    target = _core.surface_edge([hi-lo for lo, hi in zip(*extent)])
    triangles = sum(len(f.verts)-2 for f in bm.faces)
    budget = max(4, math.ceil(4 * sum(f.calc_area() for f in bm.faces) / (math.sqrt(3)*target**2)))
    if triangles <= budget:
        return bm
    mesh = bpy.data.meshes.new('_s3d_facets')
    bm.to_mesh(mesh)
    holder = bpy.data.objects.new('_s3d_facets', mesh)
    try:
        mod = holder.modifiers.new('facets', 'DECIMATE')
        mod.ratio, mod.use_collapse_triangulate = budget / triangles, True
        result = _core.evaluated_mesh(holder)
        coarse = bmesh.new()
        coarse.from_mesh(result)
        bpy.data.meshes.remove(result)
        if not coarse.faces or any(not e.is_manifold for e in coarse.edges):
            coarse.free()
            return bm
        bm.free()
        return coarse
    finally:
        bpy.data.meshes.remove(mesh)


def _span(co):
    """(lo, hi) corners of the box round flat coordinates `co`, or None if there are none."""
    if not len(co):
        return None
    values = np.asarray(co, dtype=np.float64).reshape(-1, 3)
    if np.isnan(values).any():
        return [min(co[a::3]) for a in range(3)], [max(co[a::3]) for a in range(3)]
    # argmin/argmax keep the first equal value, including the sign of zero.
    axes = np.arange(3)
    return values[values.argmin(axis=0), axes].tolist(), values[values.argmax(axis=0), axes].tolist()


def _thinnest(parts, size):
    """(the thinnest side, in millimetres, of a part's box in its own space, its name), over
    every (part, its placement in the blend's space); None if no part has a vertex."""
    found = None
    for part, matrix in parts:
        co = [0.0] * (3 * len(part.data.vertices))
        part.data.vertices.foreach_get("co", co)
        box = _span(co)
        if box is None:
            continue
        m = matrix.to_3x3()
        side = min((hi - lo) * m.col[a].length * size for a, (lo, hi) in enumerate(zip(*box)))
        if found is None or side < found[0]:
            found = (side, _core.given_name(part))
    return found


def blend(ob, *others, r, step=None):
    """Fuse others in, creases filled to about radius r on voxels of r / 5; its faces are all blend.

    `ob` with `others` fused in, and the creases where surfaces meet — between the parts, or
    within one — rounded over: a limb grows out of a trunk, a pad out of a palm. It is the
    closing of the union by a ball of radius `r` (what a ball of radius r rolling over the
    outside cannot reach is filled in), approximated on voxels of r / 5: a crease is filled
    to a radius of about r, not an exact fillet; convex shapes are kept, to a voxel; a gap
    between parts narrower than about 2 r closes, but only where the voxels resolve it —
    expect a voxel of error on any of these. Blend the massive parts first with a large r,
    then the fine ones with a smaller r. With no others, `ob`'s own creases are filled.

    Like `join`: the others are used up, and `ob` keeps its name, its frame, its placement
    and its material (the others' are lost). The result is a new smooth surface: every face
    is named `blend` (and `<ob>.blend`), whatever names the parts had, and no edge is named;
    reach it by direction (`ob.face("+Z")`) or by frame. The cost is fixed by r: a blend
    that would take more than 600 000 faces (about the parts' surface / (r / 5)²) raises —
    give a larger r, or blend smaller groups of parts and join the results. The voxels must
    hold every part: one whose box, in its own space, is thinner than 2 r (ten voxels) is
    refused — under that, the voxels swell or shrink it — and so is a result that would
    stand more than 1.5 voxels beyond the parts' box (a closing never grows past it): give
    a smaller r, or join the thin part after the blend. Nothing is used up when it raises."""
    others = _flat(others)
    _solids("blend", ob, *others)
    r = _number("blend", "r", r, positive=True)
    refuse_using_up(others, "blend")
    name = _core.given_name(ob)
    size = _core.in_mm(1.0)             # remesh in millimetres: the voxels do not depend on the unit
    to_mm = Matrix.Scale(size, 4)
    to_local = _core.world(ob).inverted()
    r_mm = r * size
    voxel = r_mm / 5 if step is None else size * _number("blend", "step", step, positive=True)
    thinnest = _thinnest([(ob, Matrix.Identity(4))] + [(o, to_local @ _core.world(o)) for o in others], size)
    if thinnest is not None and thinnest[0] < 2 * r_mm * (1 - 1e-9):
        raise ValueError(f"blend: {thinnest[1]!r} is {thinnest[0] / size:.3g} thick, under 2 r = {2 * r:g}: the "
                         f"voxels (r / 5) do not hold it — give an r of {thinnest[0] / size / 2:.3g} or less, or join "
                         f"it after the blend")
    mesh = _soup([(ob.data, to_mm)] + [(o.data, to_mm @ to_local @ _core.world(o)) for o in others])
    area = sum(p.area for p in mesh.polygons)
    if area / voxel ** 2 > BLEND_FACES:
        bpy.data.meshes.remove(mesh)
        raise ValueError(f"blend: r = {r:g} on {name!r} would take about {area / voxel ** 2:,.0f} faces (voxels of "
                         f"r / 5 over its surface), more than {BLEND_FACES:,}: give a larger r, or blend smaller "
                         f"groups of parts and join the results")
    co = [0.0] * (3 * len(mesh.vertices))
    mesh.vertices.foreach_get("co", co)
    before = _span(co)
    bm = _closing(mesh, r_mm, voxel)
    after = _span([c for v in bm.verts for c in v.co])
    if after is None:
        bm.free()
        raise ValueError(f"blend: nothing is left of {name!r} — its parts are thinner than the voxel "
                         f"({voxel / size:.3g}, r / 5): give a smaller r")
    beyond = max(max(b_lo - a_lo for a_lo, b_lo in zip(after[0], before[0])),
                 max(a_hi - b_hi for a_hi, b_hi in zip(after[1], before[1])))
    if beyond > BLEND_REACH * voxel:
        bm.free()
        raise ValueError(f"blend: the voxels (r / 5 = {voxel / size:.3g}) do not resolve {name!r}: the result would "
                         f"stand {beyond / size:.3g} beyond its parts — give a smaller r")
    if _core.FACETS is not None:
        bm = _facet_surface(bm)
    _materials_lost(ob, others, "blend")
    _guard.using_up(others, ob)
    for o in others:
        delete(o)
    if size != 1.0:
        bmesh.ops.scale(bm, vec=(1 / size,) * 3, verts=bm.verts)
    for domain in (bm.faces, bm.edges):
        for lay in list(domain.layers.bool.values()):
            if lay.name.startswith((_core.FACE_TAG, _core.EDGE_TAG)):
                domain.layers.bool.remove(lay)
    _sort_mesh(bm)
    _core.write_tags(bm, name, [{"blend"}] * len(bm.faces), [None] * len(bm.edges))
    _replace_mesh(ob, bm)
    if MERGED in ob:
        del ob[MERGED]
    return ob


#: The noises `displace` knows.
NOISES = ("perlin", "cells", "ridged", "turbulence")
#: The most faces `displace` adds to a part by refining it: past it, `size` is too small for
#: the part. A part already that dense — what `blend` makes — is displaced as it is.
DISPLACE_FACES = 500_000


def _refine(bm, size, name, selection=None):
    """Cut `bm` into triangles with no edge longer than about size / 4, in one pass: a
    surface whose every point has a vertex near it, whatever its faces were (a box's top is
    one face).

    Every convex face of more than three sides is fanned about its centre — no tie for a
    triangulation to break differently in another unit —, every concave one filled with
    triangles inside its outline (`_fill_concave`). Then each edge is cut into
    ceil(4 length / size) equal pieces, and each triangle filled again from its cut sides
    and rows of points inside it (`_rows`), as many and as dense as its own size asks: the
    faces added follow the surface's area, not how the part was cut. Faces and edges keep
    their names; the new edges inside a face have none. Raises, before cutting anything,
    when the cuts would add more than `DISPLACE_FACES`."""
    chosen = [f for f in bm.faces if selection is None or f[selection]]
    many = [f for f in chosen if len(f.verts) > 3]
    concave = [f for f in many if not _convex(f)]
    bmesh.ops.poke(bm, faces=[f for f in many if _convex(f)])
    _fill_concave(bm, concave)
    longest = size / 4 * (1 + 1e-5)     # an edge of exactly `longest` (a power of two of a side) stays whole in any unit
    bm.verts.index_update()
    bm.edges.index_update()
    cuts = {}
    # A factor-two margin covers float32 edge lengths versus the double
    # lengths in _rows. Restrict the shortcut to normal squared float32
    # magnitudes, so underflow cannot make a long edge look short.
    already_fine = 1e-15 <= longest <= 1e15
    for e in bm.edges:
        if selection is not None and not any(f[selection] for f in e.link_faces):
            continue
        length = e.calc_length()
        cuts[e] = max(1, math.ceil(length / longest)) if math.isfinite(length) else 1
        already_fine = already_fine and length <= longest / 2
    if already_fine:
        return
    from ._coordinates import NAMES
    # Edge splits and poke interpolate vertex data in BMesh. Interior row
    # points created below need their construction labels supplied explicitly
    # on the whole-surface path. The selected-face path already interpolates.
    layers = []
    if selection is None:
        layers = [layer for name in NAMES if (layer := bm.verts.layers.float.get(name)) is not None]
    plans, added = [], 0
    faces = [f for f in bm.faces if selection is None or f[selection]]
    for k, f in enumerate(faces):
        corners = list(f.verts)
        sides = [cuts[loop.edge] for loop in f.loops]
        rows = _rows(corners, sides, longest, layers) if len(corners) == 3 else []
        inside = sum(n - 1 for *_, n in rows)
        boundary = sum(sides)
        if boundary == len(corners) and not inside:
            continue
        added += 2 * inside + boundary - 3   # a polygon of B sides with I points inside: 2 I + B - 2 triangles
        if added > DISPLACE_FACES:           # the rest at two triangles per longest² of area, without counting
            added += round(sum(2 * g.calc_area() for g in faces[k + 1:]) / longest ** 2)
            raise ValueError(f"displace: features {size:g} across on {name!r} would add about {added:,} faces, "
                             f"more than {DISPLACE_FACES:,}: give a larger size")
        plans.append((f, corners, [tuple(p + (q - p) * j / n for p, q in zip(start, stop))
                                   for start, stop, n in rows for j in range(1, n)]))
    for e in sorted((e for e, n in cuts.items() if n > 1), key=lambda e: e.index):
        n = cuts[e]
        a, b = sorted(e.verts, key=lambda v: v.index)
        start, stop = tuple(a.co), tuple(b.co)      # in double precision: a point of a flat side stays on it
        edge, here = e, a
        for k in range(1, n):
            _, v = bmesh.utils.edge_split(edge, here, 1 / (n - k + 1))
            v.co = [(p * (n - k) + q * k) / n for p, q in zip(start, stop)]
            edge = next(x for x in v.link_edges if x.other_vert(v) != here)
            here = v
    slivers = [face for face, corners, inside in plans
               if not _fill(bm, face, corners, inside, interpolate=selection is not None, layers=layers)]
    if slivers:                         # one operator for all: each call walks the whole mesh
        bmesh.ops.triangulate(bm, faces=slivers, quad_method="BEAUTY", ngon_method="BEAUTY")


def _rows(corners, sides, longest, layers=()):
    """The rows of points to add inside a triangle whose sides will be cut in `sides`
    pieces, as (start, stop, pieces): rows parallel to its most cut side (the first of
    them), as many as its height over that side asks, each cut as its own length asks —
    about one point per longest² of area, however long and thin the triangle. The points
    are the row's inner cuts. In double precision. Any construction labels are
    appended to each endpoint and interpolated with the same weights."""
    k = 0 if sides[0] >= sides[1] and sides[0] >= sides[2] else (1 if sides[1] >= sides[2] else 2)
    a, b, c = (tuple(corners[(k + i) % 3].co) for i in range(3))
    ab = [q - p for p, q in zip(a, b)]
    base = math.sqrt(sum(x * x for x in ab))
    # Every row is shorter than the base. With at most one piece it has no
    # interior point, whatever the height; omit these empty rows altogether.
    if base <= longest:
        return []
    ac = [q - p for p, q in zip(a, c)]
    cross = (ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0])
    if not base or not all(math.isfinite(x) for x in cross):
        return []
    height = math.sqrt(sum(x * x for x in cross)) / base
    count = max(1, math.ceil(height / longest))
    if layers:
        a, b, c = (co + tuple(corners[(k + i) % 3][layer] for layer in layers)
                   for i, co in enumerate((a, b, c)))
    rows = []
    for r in range(1, count):
        t = r / count
        rows.append(([p + (q - p) * t for p, q in zip(a, c)], [p + (q - p) * t for p, q in zip(b, c)],
                     max(1, math.ceil(base * (1 - t) / longest))))
    return rows


def _fill(bm, face, corners, inside, interpolate=False, layers=()):
    """Replace the triangle `face` — its sides already cut, `corners` its three corners — by
    triangles through its side points and the points `inside` it, by the constrained
    Delaunay triangulation caps use (in millimetres). False, the face left as it is, for a
    sliver the triangulation cannot fill whole: it is cut from its side points alone."""
    if len(corners) != 3:
        return False
    a, b, c = (v.co.copy() for v in corners)
    normal = (b - a).cross(c - a)
    loop = list(face.verts)
    points = [Vector(p[:3]) for p in inside]
    tris = None
    if normal.length > 0:
        normal.normalize()
        u = normal.orthogonal().normalized()
        w = normal.cross(u)
        flat = [(p.dot(u), p.dot(w)) for p in [v.co for v in loop] + points]
        tris = _triangles(flat, len(loop))
    if not tris:
        return False
    verts = list(loop)
    for p, sample in zip(points, inside):
        v = bm.verts.new(p)
        if interpolate:
            v.copy_from_face_interp(face)
        for layer, value in zip(layers, sample[3:]):
            v[layer] = value
        verts.append(v)
    for t in tris:
        bm.faces.new([verts[i] for i in t], face)
    bm.faces.remove(face)
    return True


def _triangles(flat, boundary):
    """Triangles, anticlockwise, of the 2D points `flat` inside the outline of their first
    `boundary` points; None unless they cover it whole, every point used as given."""
    edges = [(i, (i + 1) % boundary) for i in range(boundary)]
    _, _, faces, orig, _, _ = _core.triangulate(flat, edges, 1, 1e-6)
    tris = []
    area = 0.0
    for f in faces:
        if not all(len(orig[v]) == 1 for v in f):
            return None
        t = [orig[v][0] for v in f]
        (ax, ay), (bx, by), (cx, cy) = (flat[i] for i in t)
        cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        tris.append(t if cross > 0 else t[::-1])
        area += abs(cross) / 2
    outline = sum(flat[i][0] * flat[(i + 1) % boundary][1] - flat[(i + 1) % boundary][0] * flat[i][1]
                  for i in range(boundary)) / 2
    used = {i for t in tris for i in t}
    if len(used) != len(flat) or abs(area - abs(outline)) > 1e-6 * max(abs(outline), 1e-30):
        return None
    return tris


def _convex(face):
    """Whether no corner of `face` turns back against its normal: its centre sees its whole
    outline, and a fan about it stays inside."""
    vs = [v.co for v in face.verts]
    n = face.normal
    size = max((v - vs[0]).length for v in vs)
    return all((vs[i] - vs[i - 1]).cross(vs[(i + 1) % len(vs)] - vs[i]).dot(n) >= -1e-9 * size * size
               for i in range(len(vs)))


def _fill_concave(bm, faces):
    """Replace each face of `faces` by triangles inside its outline: its corners laid flat
    across its normal, then the constrained Delaunay triangulation every cap uses, which
    runs in millimetres — the same triangles in any unit. Each triangle keeps the face's names."""
    for face in faces:
        n = face.normal
        u = n.orthogonal().normalized()
        w = n.cross(u)
        verts = list(face.verts)
        tris = _cap([(v.co.dot(u), v.co.dot(w)) for v in verts])
        if not tris:
            continue
        for t in tris:
            bm.faces.new([verts[i] for i in t], face)
        bm.faces.remove(face)


def _field(kind, octaves, seed):
    """The noise as a function of a point (in units of the feature size), in [-1, 1]: each
    octave at twice the frequency and half the weight of the one before, the field offset by
    `seed`."""
    rng = random.Random(seed)
    shifts = [Vector([rng.uniform(-128, 128) for _ in range(3)]) for _ in range(octaves)]
    weights = [0.5 ** k for k in range(octaves)]
    total = sum(weights)
    if kind == "ridged":
        return lambda q: 2 * fields.ridged_multi_fractal(q + shifts[0], 1.0, 2.0, octaves, 1.0, 1.0,
                                                         noise_basis="PERLIN_NEW") / total - 1
    if kind == "turbulence":
        return lambda q: 2 * fields.turbulence(q + shifts[0], octaves, True, noise_basis="PERLIN_NEW",
                                               amplitude_scale=0.5, frequency_scale=2.0) / total - 1
    if kind == "cells":
        def one(q):     # each cell a bump, its borders grooves: 1 at a feature point, -1 a unit away
            return 1 - 2 * min(fields.voronoi(q, distance_metric="DISTANCE")[0][0], 1.0)
    else:
        def one(q):
            return fields.noise(q, noise_basis="PERLIN_NEW")
    return lambda q: sum(w * one(q * 2 ** k + s) for k, (w, s) in enumerate(zip(weights, shifts))) / total


def _push(direction):
    """The direction of `displace`: "normal", "radial", or a constant vector."""
    if direction in ("normal", "radial"):
        return direction
    d = _DIRECTION.match(direction) if isinstance(direction, str) else None
    if d:
        v = Vector({"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[d.group(2).lower()])
        return -v if d.group(1) in ("-", "<") else v
    if (isinstance(direction, (tuple, list, Vector)) and len(direction) == 3
            and all(isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in direction)
            and Vector(direction).length > 0 and all(math.isfinite(c) for c in Vector(direction).normalized())):
        return Vector(direction).normalized()
    raise ValueError(f"displace: direction is \"normal\", \"radial\" (from the part's origin), a direction "
                     f"(\"+Z\", \"-X\"…) or (x, y, z), not {direction!r}")


def _path_coordinates(bm):
    """Read interpolated construction labels, never search the deformed geometry."""
    from ._coordinates import NAMES
    layers = [bm.verts.layers.float.get(n) for n in NAMES]
    if any(layer is None for layer in layers):
        raise ValueError('displace: coords="path" needs construction coordinates')
    data = np.array([[v[layer] for layer in layers] for v in bm.verts], dtype=np.float64)
    if not np.all(np.isfinite(data)):
        raise ValueError('displace: construction coordinates are undefined on some vertices')
    return np.column_stack((data[:,0],np.degrees(np.arctan2(data[:,2],data[:,1])),np.hypot(data[:,1],data[:,2])))


def _displace_selection(ob, faces):
    """Resolve construction names or the same directional patch as face()."""
    from .frames import _facing
    terms = [faces] if isinstance(faces, str) else faces
    if not isinstance(terms, (list, tuple)) or not all(isinstance(t, str) for t in terms):
        raise TypeError("displace: faces is a face name, direction, or list of names")
    names = [t for t in terms if not _DIRECTION.match(t)]
    picked = _named_faces(ob, names)
    for term in terms:
        if _DIRECTION.match(term):
            patch = _facing(ob, term)
            if not patch:
                raise ValueError(f"displace: {_core.given_name(ob)!r} has no face facing {term}")
            picked.update(p.index for p in patch)
    return picked


def _displace_border(bm, selection, size):
    """Euclidean distance to the selected patch boundary, with zero slope at both ends.

    Shared edges may gain vertices during refinement; none of their points move.
    Process one segment at a time so memory stays linear in the vertex count.
    """
    vertices = list(bm.verts)
    points = np.array([tuple(v.co) for v in vertices], dtype=np.float64)
    distance2 = np.full(len(vertices), np.inf)
    boundary = set()
    for edge in bm.edges:
        inside = sum(bool(f[selection]) for f in edge.link_faces)
        if inside and (inside < len(edge.link_faces) or len(edge.link_faces) == 1):
            boundary.update(edge.verts)
            a, b = (np.array(v.co, dtype=np.float64) for v in edge.verts)
            delta = b - a
            length2 = delta @ delta
            t = np.clip((points - a) @ delta / length2, 0, 1) if length2 else np.zeros(len(points))
            offsets = points - (a + t[:, None] * delta)
            distance2 = np.minimum(distance2, np.sum(offsets * offsets, axis=1))
    t = np.minimum(np.sqrt(distance2) / size, 1)
    weights = t * t * (3 - 2 * t)
    return {v: float(w) if v not in boundary and any(f[selection] for f in v.link_faces) else 0.0
            for v, w in zip(vertices, weights)}


def displace(ob, amount, size, noise="perlin", octaves=1, seed=0, direction="normal", fade=None, *, faces=None, coords="local", step=None):
    """Push the surface out and in by up to amount, features size across: noise perlin cells ridged
    turbulence or a callable; direction normal, radial or "+Z"…; fade along own Z.

    A callable receives float64 arrays (x, y, z) in local program units, or
    (s, angle_degrees, radius) with coords="path" on a wire or sweep.
    Return a same-shaped finite real ndarray in [-1, 1]. Values multiply
    amount directly without centring. Keep octaves=1 and seed=0; compose
    noise inside the callback. Size controls refinement only. Path coordinates
    read vertex construction labels with parallel-transported angular axes;
    they follow copies, joins, merges and deformations without reprojection.

    `ob`'s surface pushed out and in by up to `amount`, its features about `size` across:
    bark, rock, coral, a hammered finish. `amount` and `size` are lengths.

    A named noise is a field fixed to the part: its own frame, its origin at the part's origin,
    so it moves with the part. It is read at every vertex at the point / `size`, shifted by
    `seed` (an integer: the same seed, the same field, in every run). Each noise gives a
    value between -1 and 1:

    - "perlin": gradient noise, soft hills and hollows;
    - "cells": 1 at the feature points of a Worley field, -1 a feature size from the nearest:
      a bump per cell, grooves at the borders (scales, cobbles);
    - "ridged": ridged multifractal, sharp crests where Perlin noise crosses zero;
    - "turbulence": the sum of |Perlin|, soft swells and creased hollows.

    `octaves` n sums n layers, the k-th (from 0) at 2^k the frequency and 1 / 2^k the
    weight, divided by the sum of the weights: still between -1 and 1. The values are then
    centred on the surface: their average (by area, and by the fade's weight) is taken off,
    and they are divided by 1 + |that average|, so the part keeps about its volume and no
    point moves more than `amount`. A vertex moves by `amount` × its value × the fade's
    weight, along `direction`: "normal", its normal (the mean of its faces'); "radial",
    the line from the part's origin through it (a vertex at the origin stays); a direction
    "+X" … "-Z", or any (x, y, z) but (0, 0, 0), in the part's own space, the same for every
    vertex. `fade=(z0, z1)`: the weight is 1 at z0 on the part's own Z and 0 at z1, linear
    between, 1 beyond z0 and 0 beyond z1, either above the other — a trunk rough above its
    root.

    step=None keeps automatic refinement; step > 0 sets the maximum edge length
    independently of feature size; step=0 keeps existing vertices.
    Auto targets max(size / 4, D / 128), D the largest local box dimension (past 500 000
    faces, it raises: give a larger step), then every vertex
    moves. Faces and edges keep their names, but a face it moved is flat no more: read the
    frames a part needs (`ob.face("top")`) before displacing it.
    Fixed facets(n) bounds refinement by π D / n, D the largest local box dimension;
    existing fine edges remain. Explicit step takes precedence.
    step=0 moves existing vertices only, retaining their order and attributes.
    faces=None keeps the whole-surface behavior. A name, list of names or face()
    direction restricts displacement and refinement to those faces. Their boundary
    stays fixed, with a smoothstep transition over size in local Euclidean distance.
    Shared edges gain collinear vertices, but unselected faces are not triangulated."""
    if step is not None:
        step = _number("displace", "step", step)
        if step < 0:
            raise ValueError("displace: step must be nonnegative")
    refine = step != 0
    _solids("displace", ob)
    amount = _number("displace", "amount", amount)
    size = _number("displace", "size", size, positive=True)
    custom = callable(noise)
    if coords not in ("local", "path"):
        raise ValueError('displace: coords is "local" or "path"')
    if coords == "path":
        if not custom:
            raise ValueError('displace: coords="path" requires callable noise')
        if ".s3d_s" not in ob.data.attributes:
            raise ValueError('displace: coords="path" needs a wire or sweep; displace before join or deform')
    if custom and (octaves != 1 or seed != 0):
        raise ValueError("displace: callable noise requires octaves=1 and seed=0; compose noise inside the function")
    if not custom and noise not in NOISES:
        raise ValueError(f"displace: noise is {', '.join(repr(n) for n in NOISES[:-1])} or {NOISES[-1]!r}, "
                         f"not {noise!r}")
    if isinstance(octaves, bool) or not isinstance(octaves, int) or octaves < 1:
        raise ValueError(f"displace: octaves is a whole number, 1 or more, not {octaves!r}")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError(f"displace: seed is an integer, not {seed!r}")
    push = _push(direction)
    if fade is not None:
        if (not isinstance(fade, (tuple, list)) or len(fade) != 2
                or any(isinstance(z, bool) or not isinstance(z, (int, float)) for z in fade)):
            raise TypeError(f"displace: fade is (z0, z1), full effect at z0 and none at z1, not {fade!r}")
        if not all(math.isfinite(z) for z in fade):
            raise ValueError(f"displace: fade runs between two finite heights, not {fade[0]:g} and {fade[1]:g}")
        if fade[0] == fade[1]:
            raise ValueError(f"displace: fade runs between two different heights, not {fade[0]:g} and {fade[1]:g}")
    picked = _displace_selection(ob, faces) if faces is not None else None
    if picked == set():
        return ob
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    selection = None
    if picked is not None:
        selection = bm.faces.layers.int.new(".displace_selection")
        for f in bm.faces:
            f[selection] = int(f.index in picked)
    try:
        if refine:
            extent = _span([c for v in bm.verts for c in v.co])
            diameter = max(hi-lo for lo, hi in zip(*extent))
            refinement_size = 4 * step if step is not None else max(size, 4 * diameter / 128)
            if step is None and _core.FACETS is not None:
                extent = _span([c for v in bm.verts for c in v.co])
                target = _core.surface_edge([hi-lo for lo, hi in zip(*extent)])
                refinement_size = max(refinement_size, 4 * target)
            _refine(bm, refinement_size, _core.given_name(ob), selection)
    except ValueError:
        bm.free()
        raise
    bm.normal_update()
    border = _displace_border(bm, selection, size) if selection is not None else None
    if selection is not None:
        bm.faces.layers.int.remove(selection)
    values = None
    if custom:
        try:
            points = np.array([tuple(v.co) for v in bm.verts], dtype=np.float64)
            if coords == "path":
                points = _path_coordinates(bm)
            values = noise(*points.T)
            if not isinstance(values, np.ndarray) or values.shape != (len(points),):
                raise ValueError("displace: callable must return an ndarray with the input shape")
            if values.dtype.kind not in "fiu" or not np.all(np.isfinite(values)):
                raise ValueError("displace: callable values must be finite real numbers")
            values = values.astype(np.float64, copy=False)
            if np.any(np.abs(values) > 1):
                raise ValueError("displace: callable values must lie in [-1, 1]")
        except BaseException:
            bm.free()
            raise
    else:
        field = _field(noise, octaves, seed)

    def weight(z):
        if fade is None:
            return 1.0
        z0, z1 = fade
        return min(max((z - z1) / (z0 - z1), 0.0), 1.0)
    samples = []
    for i, v in enumerate(bm.verts):
        w = weight(v.co.z)
        if border is not None:
            w *= border[v]
        if w and amount:
            area = 0.0 if custom else sum(f.calc_area() / len(f.verts) for f in v.link_faces)
            samples.append((v, w, area, float(values[i]) if custom else field(v.co / size)))
    total = sum(w * a for _, w, a, _ in samples)
    mean = sum(w * a * value for _, w, a, value in samples) / total if total else 0.0
    if custom:
        mean = 0.0
    moves = []
    for v, w, _, value in samples:
        d = v.normal if push == "normal" else (v.co.normalized() if push == "radial" else push)
        moves.append((v, d * (amount * w * (value - mean) / (1 + abs(mean)))))
    for v, step in moves:
        v.co += step
    if refine:
        _sort_mesh(bm)
    _replace_mesh(ob, bm)
    return ob


# ---------------------------------------------------------------- own-frame deformers

def _deform_axis(verb, axis):
    if not isinstance(axis, str) or axis not in ("+X", "-X", "+Y", "-Y", "+Z", "-Z"):
        raise ValueError(f'{verb}: axis is a signed direction ("+Y", "-X"…), not {axis!r}')
    return Vector(tuple((1 if axis[0] == "+" else -1) if c == axis[1] else 0 for c in "XYZ"))


def _deform_parts(ob, verb):
    """Meshes and their placements in the root's own frame, including nested groups."""
    from .assembly import Handle
    root = ob.root if isinstance(ob, Handle) else ob
    if not isinstance(root, bpy.types.Object) or root.type not in ("MESH", "EMPTY"):
        _solids(verb, root)
    children = _children()
    parts = []

    def walk(part, matrix):
        if part.type == "MESH":
            parts.append((part, matrix))
        for child in children.get(part, []):
            walk(child, matrix @ child.matrix_parent_inverse @ child.matrix_basis)
    walk(root, Matrix.Identity(4))
    return parts


def _deform(ob, value, axis, verb, toward=None, step=None):
    if step is not None:
        step = _number(verb, "step", step)
        if step < 0:
            raise ValueError(f"{verb}: step must be nonnegative")
    a = _deform_axis(verb, axis)
    b = _deform_axis(verb, toward) if verb == "bend" else None
    if b is not None and a.dot(b):
        raise ValueError(f"bend: toward {toward!r} must be perpendicular to axis {axis!r}")
    value = _number(verb, "s" if verb == "taper" else "angle", value)
    if verb == "taper" and value <= 0:
        raise ValueError(f"taper: s is a ratio, more than 0, not {value:g}")
    parts = _deform_parts(ob, verb)
    us = [(matrix @ v.co).dot(a) for part, matrix in parts for v in part.data.vertices]
    lo, hi = (min(us), max(us)) if us else (0, 0)
    span = hi - lo
    if span == 0:
        raise ValueError(f"{verb}: no extent along axis {axis!r}")
    if value == (1 if verb == "taper" else 0):
        return ob
    k = math.radians(value) / span if verb != "taper" else 0
    for part, matrix in parts:
        inverse = matrix.inverted()
        bm = bmesh.new()
        bm.from_mesh(part.data)
        bm.transform(matrix)
        bm.normal_update()
        if verb != "taper":
            # Cut through the faces too, not just their rims. Each new face inherits
            # its parent's names. Fixed planes make the refinement independent of units.
            bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method="FIXED", ngon_method="EAR_CLIP")
            pieces = _core.segments(1, abs(value)) if _core.FACETS is not None else max(4, math.ceil(abs(value) / 3))
            if step is not None:
                pieces = max(1, math.ceil(span / step)) if step else 1
            for i in range(1, pieces):
                bmesh.ops.bisect_plane(bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
                                       dist=span * 1e-8, plane_co=a * (lo + span * i / pieces), plane_no=a)
            bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method="FIXED", ngon_method="EAR_CLIP")
        for v in bm.verts:
            u = v.co.dot(a)
            if verb == "bend":
                z = v.co.dot(b)
                theta = k * u
                # 2 sin²(theta/2) avoids cancellation at small angles.
                v.co += a * ((1 / k - z) * math.sin(theta) - u) + b * (
                    2 * math.sin(theta / 2) ** 2 / k + z * (math.cos(theta) - 1))
            else:
                p = v.co - a * u
                t = (u - lo) / span
                if verb == "twist":
                    theta = math.radians(value) * t
                    v.co = a * u + p * math.cos(theta) + a.cross(p) * math.sin(theta)
                else:
                    v.co = a * u + p * (1 + (value - 1) * t)
        bm.transform(inverse)
        bm.normal_update()
        _core.own_mesh(part)
        bm.to_mesh(part.data)
        bm.free()
        part.data.update()
        _core.shade_mesh(part)
    return ob


def bend(ob, angle, axis="+Y", toward="+Z", *, step=None):
    """Curl along its own axis toward a perpendicular direction, angle in degrees.

    The neutral axis passes through the origin; a point at signed distance u turns
    by angle * u / L, where L is the axis extent. Negative u curls the other way;
    angles beyond 180 degrees are allowed. Zero leaves the mesh unchanged.
    Faces keep their maker's names, refined faces their parent's. Refinement cuts
    through faces in at least four slices, at most 3 degrees each; a fixed facet count sets
    the pieces by the bend angle. Normals are updated after the edit.
    On a group, its children bend together in its frame, with one shared extent.
    Name, placement and materials stay; read any flat face frames before bending.
    """
    return _deform(ob, angle, axis, "bend", toward, step=step)


def twist(ob, angle, axis="+Y", *, step=None):
    """Turn sections about its own axis, right handed, angle in degrees at the far end.

    The end at the least signed coordinate stays fixed. Faces keep their maker's
    names; refinement and groups work as in bend. Zero leaves the mesh unchanged.
    """
    return _deform(ob, angle, axis, "twist", step=step)


def taper(ob, s, axis="+Y"):
    """Scale sections across its own axis, from 1 at the near end to ratio s > 0.

    Not extrude(taper=), which takes degrees, nor superellipse(taper=), a narrowing
    fraction. No refinement is needed. Faces keep their names; a group uses one
    shared extent in its own frame. s = 1 leaves the mesh unchanged.
    """
    return _deform(ob, s, axis, "taper")


def _drop_tessellation_duplicates(bm):
    """Expose overlapping ngon triangles before exporters triangulate them.

    An exact boolean can leave two distinct concave polygons sharing a triangle.
    Mesh validation only detects this after tessellation; leave ordinary faces alone.
    """
    probe = bpy.data.meshes.new('tessellation')
    try:
        bm.to_mesh(probe)
        if _core.MM != 1:
            probe.transform(Matrix.Scale(_core.MM, 4))
        probe.calc_loop_triangles()
        seen, affected = {}, set()
        for t in probe.loop_triangles:
            key = tuple(sorted(t.vertices))
            if key in seen:
                affected.update((seen[key], t.polygon_index))
            else:
                seen[key] = t.polygon_index
        if affected:
            bm.faces.ensure_lookup_table()
            # Blender tessellation has absolute tolerances: decide in millimetres,
            # then restore the exact input positions, including in power-of-two units.
            positions = [(v, v.co.copy()) for v in bm.verts] if _core.MM != 1 else []
            try:
                for v, co in positions:
                    v.co = co*_core.MM
                bmesh.ops.triangulate(bm, faces=[bm.faces[i] for i in sorted(affected)])
            finally:
                for v, co in positions:
                    v.co = co
            bm.verts.index_update()
            groups = {}
            for f in bm.faces:
                groups.setdefault(tuple(sorted(v.index for v in f.verts)), []).append(f)
            duplicates = [f for group in groups.values() if len(group)>1 for f in group]
            if duplicates:
                bmesh.ops.delete(bm, geom=duplicates, context='FACES_ONLY')
            loose = [e for e in bm.edges if not e.link_faces]
            if loose:
                bmesh.ops.delete(bm, geom=loose, context='EDGES')
    finally:
        bpy.data.meshes.remove(probe)


class LayWarning(UserWarning):
    """A missed vertical projection or a seating that could not be applied."""


class _LayFailure(ValueError):
    """Abort the whole seating before writing any mesh."""


def _warn_lay(error):
    if _is_strict():
        raise error
    _warn(str(error), LayWarning)


def lay(ob, over, reach=None, *, step=None):
    """Seat a placed part on a surface: every point keeps its height above the part's own
    Z = 0 plane, measured from the surface of `over` under it.

    A flat piece built on Z = 0 and placed on a frame of the carrier follows the carrier
    after it: its base lies on the skin, what was below stays buried, what was above
    stands as proud. Hits move points along the part's own Z; a face
    stays flat between its points, so give a long piece points along its length. A group
    is laid in its own frame. When a ray misses, use the nearest surface point and warn.
    This fallback can move points laterally.

    A positive step subdivides faces before seating until every edge is at most that length;
    0 leaves the topology. reach bounds the travel from the base plane to the surface;
    None has no limit. Exceeding reach raises ValueError and leaves all the pieces and
    their topology unchanged.
    Projection and tessellation use the parts' own frames, so a common translation and
    rotation do not change the result in the piece's frame.
    """
    try:
        return _lay(ob, over, reach, step=step)
    except _LayFailure as error:
        _warn_lay(error)
        return ob


def _lay_roots(ob):
    if isinstance(ob, (list, tuple)):
        for item in ob:
            yield from _lay_roots(item)
    else:
        yield ob


def _lay_refine(bm, matrix, back, step, name):
    bm.transform(matrix)
    bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method='FIXED', ngon_method='EAR_CLIP')
    while not all(e.calc_length() <= step*(1+1e-6) for e in bm.edges):
        edges = list(bm.edges)
        if len(bm.faces)+8*len(edges) > 500000:
            raise ValueError(f'lay: step on {name!r} would exceed 500000 faces')
        bmesh.ops.subdivide_edges(bm, edges=edges, cuts=1, use_grid_fill=True)
        bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method='FIXED', ngon_method='EAR_CLIP')
    bm.transform(back)
    bm.normal_update()


@contextlib.contextmanager
def _lay_carrier_mesh(carrier, inverse, size):
    # Tessellate in the carrier's frame: a common rotation must not change
    # the diagonal picked for a nonplanar face.
    bm = bmesh.new()
    try:
        bm.from_mesh(carrier.data)
        bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method='FIXED', ngon_method='EAR_CLIP')
        bm.transform(inverse @ _core.world(carrier))
        if size != 1:
            bmesh.ops.scale(bm, vec=(size,)*3, verts=list(bm.verts))
        yield bm
    finally:
        bm.free()


def _lay_hit(base, cast, up, size, trees):
    ray = (base + up * cast) * size
    hits = [h for h in (t.ray_cast(ray, -up) for t in trees) if h[0] is not None]
    return min(hits, key=lambda h: h[3])[0] / size if hits else None


def _lay(ob, over, reach=None, *, step=None):
    from .assembly import Handle
    from ._surface import meshes
    roots = list(_lay_roots(ob))
    if not roots:
        return ob
    step = 0 if step is None else _number('lay', 'step', step)
    if step < 0:
        raise ValueError('lay: step must be nonnegative')
    if reach is not None:
        reach = _number('lay', 'reach', reach)
        if reach < 0:
            raise ValueError('lay: reach must be nonnegative')
    carriers = meshes(over)
    if not carriers:
        raise TypeError("lay: over must contain mesh parts")
    surfaces = [c for c in carriers if len(c.data.polygons)]
    carrier_names = ", ".join(repr(_core.given_name(c)) for c in carriers)
    if not surfaces:
        raise _LayFailure(f"lay: carrier {carrier_names} has no faces")
    size = _core.in_mm(1.0)
    up = Vector((0, 0, 1))
    # Retain each refinement in a detached BMesh. Keep the projected positions
    # separately, so a successful write follows the same mesh conversion as before.
    staged = {}
    with contextlib.ExitStack() as cleanup:
        for target in roots:
            parts = _deform_parts(target, "lay")
            root = target.root if isinstance(target, Handle) else target
            if any(part in carriers for part, _ in parts):
                raise ValueError("lay: a part cannot be laid on itself")
            inverse = _core.world(root).inverted()
            prepared = []
            for part, matrix in parts:
                back = matrix.inverted()
                bm, coords = staged.get(part, (None, None))
                if step:
                    if bm is None:
                        bm = bmesh.new()
                        cleanup.callback(bm.free)
                        bm.from_mesh(part.data)
                    if coords is not None:
                        for vert, co in zip(bm.verts, coords):
                            vert.co = co
                    _lay_refine(bm, matrix, back, step, _core.given_name(part))
                    coords = [v.co for v in bm.verts]
                elif coords is None:
                    coords = [v.co for v in part.data.vertices]
                prepared.append((part, bm, back, [matrix @ co for co in coords]))
            if not any(points for _, _, _, points in prepared):
                continue
            carrier_points = [inverse @ _core.world(c) @ v.co for c in carriers for v in c.data.vertices]
            cast = max(max(p.length for p in carrier_points),
                       max(p.length for _, _, _, points in prepared for p in points)) + _core.mm(1e-3)
            trees = []
            for carrier in surfaces:
                with _lay_carrier_mesh(carrier, inverse, size) as bm:
                    trees.append(BVHTree.FromBMesh(bm))
            for part, bm, back, points in prepared:
                positions = []
                misses = 0
                for p in points:
                    height = p.dot(up)
                    base = p - up * height
                    spot = _lay_hit(base, cast, up, size, trees)
                    if spot is None:
                        misses += 1
                        hits = [h for h in (t.find_nearest(base * size) for t in trees) if h[0] is not None]
                        if not hits:
                            raise _LayFailure(f"lay: carrier {carrier_names} has no nearest surface point")
                        spot = min(hits, key=lambda h: h[3])[0] / size
                    distance = (spot-base).length
                    if reach is not None and distance > reach + _core.mm(1e-6):
                        name = _core.given_name(part)
                        raise ValueError(f'lay: {name!r} needs distance {distance:g}, beyond reach {reach:g}')
                    positions.append(back @ (spot + up * height))
                if misses:
                    name = _core.given_name(part)
                    _warn_lay(_LayFailure(f"lay: {name!r}: {misses} point(s) miss carrier {carrier_names} "
                                          "along Z; using nearest surface points"))
                staged[part] = bm, positions
        for part, (bm, positions) in staged.items():
            mesh = _core.own_mesh(part)
            if bm is not None:
                bm.to_mesh(mesh)
            for v, co in zip(mesh.vertices, positions):
                v.co = co
            mesh.update()
            _core.shade_mesh(part)
    return ob
