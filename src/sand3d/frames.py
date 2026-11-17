"""Frames and placement: where things are built and where they sit.

A frame is an origin and three axes, in the frame of the space an object lives
in (the world, for an object with no parent). `ob.face("top")` is the frame of a
named face, `ob.face("+Z")` of the face furthest along +Z; distributors (`grid`,
`ring`, `along`, `snap`) return lists of frames, which move, turn and offset as
one frame does; `at` puts an object, a profile or a path on one, or a copy on each. Axes follow CadQuery's convention: on a face whose normal is
±Z, X is world +X; on any other, X is Z × normal — so a wall facing -Y has X to
the right and Y up.

A frame read on a part — `ob.face`, `bbox`, an assembly's anchor — remembers the part
(`part`) and where the part stood when it was read, through `.move`, `.turn` and
`.offset`: a joint takes its pivot from it, wherever the part has gone since.
"""
import atexit
import bisect
import math
import re
import random

import bpy
import bmesh
from mathutils import Euler, Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

from . import _core
from .profile import Path, Placed, Profile, _as_path


def _clean(v):
    """A unit vector without the single-precision dust meshes leave on axis-aligned
    normals: a +Z face read as (0, 1e-8, 1) would turn a frame's X anywhere."""
    v = v.normalized()
    v = Vector([0.0 if abs(c) < 1e-6 else c for c in v])
    return v.normalized()


class Frame:
    """A place to build on.

    A place to build on: an `origin`, a `normal` (its Z) and an `up` (its Y);
    without `up`, X is Z × normal (+X when the normal is ±Z)."""

    def __init__(self, origin=(0, 0, 0), normal=(0, 0, 1), up=None):
        for what, v in (("an origin", origin), ("a normal", normal), ("an up", up)):
            if v is not None and len(v) != 3:
                raise ValueError(f"Frame: {what} is (x, y, z), not {tuple(v)}")
        z = _clean(Vector(normal))
        if up is None:
            x = Vector((0, 0, 1)).cross(z)
            x = x.normalized() if x.length > 1e-6 else Vector((1, 0, 0))
            y = z.cross(x)
        else:
            y = _clean(Vector(up))
            y = y - z * y.dot(z)
            if y.length < 1e-9:
                raise ValueError(f"Frame: up {tuple(up)} is along the normal {tuple(normal)}")
            y.normalize()
        self.origin, self.x, self.y, self.z = Vector(origin), y.cross(z), y, z

    #: The part the frame was read on, and the part's placement then (`_basis`, which maps
    #: the part's own space to the one the frame is in; `_seen`, its place in the world):
    #: None for a frame built by hand.
    part = None
    _basis = None
    _seen = None

    @property
    def normal(self):
        return self.z

    def _read_on(self, part, basis, seen=None):
        """This frame, remembered as read on `part` placed by `basis`, in the world at `seen`
        (where the part is now, by default)."""
        self.part, self._basis = part, Matrix(basis)
        self._seen = Matrix(seen) if seen is not None else _core.world(part)
        return self

    def _kept(self, frame):
        """`frame`, made from this one: it remembers the same part."""
        return frame._read_on(self.part, self._basis, self._seen) if self.part is not None else frame

    def _in_part(self):
        """This frame in its part's own space: where it stays when the part moves."""
        return self._basis.inverted() @ self.matrix

    def __iter__(self):
        raise TypeError("a Frame is not a point: use f.origin (f.origin.x, f.origin.y, f.origin.z)")

    @property
    def matrix(self):
        m = Matrix.Identity(4)
        for col, v in enumerate((self.x, self.y, self.z, self.origin)):
            for row in range(3):
                m[row][col] = v[row]
        return m

    def offset(self, d):
        """Along the normal.

        The same frame moved `d` along its normal."""
        return self._kept(Frame(self.origin + self.z * d, self.z, self.y))

    def turn(self, rx=0, ry=0, rz=0):
        """About own axes, degrees.

        The same frame turned about its own X, then Y, then Z, in degrees."""
        r = Euler((math.radians(rx), math.radians(ry), math.radians(rz))).to_matrix()
        axes = self.matrix.to_3x3() @ r
        return self._kept(Frame(self.origin, axes.col[2], axes.col[1]))

    def move(self, x=0, y=0, z=0):
        """Along own axes.

        The same frame moved along its own axes."""
        return self._kept(Frame(self.point(x, y, z), self.z, self.y))

    def point(self, x=0, y=0, z=0):
        """In parent's frame.

        Where (x, y, z) of this frame lies in its parent's."""
        return self.origin + self.x * x + self.y * y + self.z * z

    def __repr__(self):
        r = lambda v: tuple(round(c, 6) + 0.0 for c in v)  # noqa: E731
        return f"Frame(origin={r(self.origin)}, normal={r(self.z)}, up={r(self.y)})"


class Frames(list):
    """Frames, as the distributors give them: the list moves, turns and offsets as one
    frame does, each frame along its own axes — on a ring, X points outward.
    `point` stays a frame's. Sliced, added to frames or repeated, it stays a `Frames`."""

    def offset(self, d):
        return Frames(f.offset(d) for f in self)

    def turn(self, rx=0, ry=0, rz=0):
        return Frames(f.turn(rx, ry, rz) for f in self)

    def move(self, x=0, y=0, z=0):
        return Frames(f.move(x, y, z) for f in self)

    def jitter(self, rx=0, ry=0, rz=0, x=0, y=0, z=0, seed=0):
        """Random turns and moves along own axes, bounded and bell-shaped.

        Each amplitude is nonnegative (degrees or program length units). Independent
        triangular draws use a local generator; moves use the original frame's axes.
        Part memory is kept, as with turn and move.
        """
        amplitudes = (rx, ry, rz, x, y, z)
        if not _finite(*amplitudes) or any(a < 0 for a in amplitudes):
            raise ValueError("jitter: amplitudes must be finite nonnegative numbers")
        rng = _random(seed, "jitter")
        out = Frames()
        for f in self:
            a, b, c, dx, dy, dz = [rng.triangular(-v, v, 0) for v in amplitudes]
            out.append(f.move(dx, dy, dz).turn(a, b, c))
        return out

    def __getitem__(self, i):
        got = super().__getitem__(i)
        return Frames(got) if isinstance(i, slice) else got

    def __add__(self, other):
        joined = list(self) + list(other)
        return Frames(joined) if all(isinstance(f, Frame) for f in joined) else joined

    def __radd__(self, other):
        joined = list(other) + list(self)
        return Frames(joined) if all(isinstance(f, Frame) for f in joined) else joined

    def __mul__(self, n):
        return Frames(list(self) * n)

    __rmul__ = __mul__


def _one(on, verb):
    """`on` as one frame (the origin's if None)."""
    if on is None:
        return Frame()
    if not hasattr(on, "matrix") or isinstance(on, (list, tuple)):
        raise TypeError(f"{verb}: on is one frame, not {type(on).__name__}: a grid or a ring is laid on one plane")
    return on


def _frame_of(matrix):
    return Frame(matrix.to_translation(), matrix.col[2].xyz, matrix.col[1].xyz)


# ---------------------------------------------------------------- the frame of a face

_DIRECTION = re.compile(r"^([+\-<>]?)([xyzXYZ])$")


def face(ob, which):
    """Frame of a named face, or furthest along "+Z".

    The frame of the face of `ob` named `which` ("top", "boss.top", "cut") — the
    largest flat group of faces with that name — or, given a direction ("+Z", "-X"),
    of the face furthest that way. Its origin is the parent's origin projected onto
    the face's plane, as CadQuery places a workplane."""
    if ob.type != "MESH":
        raise ValueError(f"face: {_core.given_name(ob)!r} is a group, not a solid: "
                         'use bbox(group, "+Z") or a part face')
    me = ob.data
    polys = list(me.polygons)
    d = _DIRECTION.match(which)
    if d:
        chosen = _facing(ob, which)
        if not chosen:
            raise ValueError(f"{_core.given_name(ob)} has no face facing {which}")
    else:
        att = me.attributes.get(_core.tag_key(_core.FACE_TAG, which))
        if att is None:
            names = sorted(a.name[len(_core.FACE_TAG):] for a in me.attributes if a.name.startswith(_core.FACE_TAG))
            raise ValueError(_core.unknown(_core.given_name(ob), "face", [which], names))
        tagged = [p for p, v in zip(polys, att.data) if v.value]
        groups = {}
        for p in tagged:
            n = p.normal
            key = (round(n.x, 4) + 0.0, round(n.y, 4) + 0.0, round(n.z, 4) + 0.0,
                   round(_core.in_mm(n.dot(p.center)), 4) + 0.0)
            groups.setdefault(key, []).append(p)
        if not groups:
            raise ValueError(f"{_core.given_name(ob)}: no face carries {which!r} any more")
        chosen = max(groups.values(), key=lambda g: (sum(p.area for p in g), -min(p.index for p in g)))
        total = sum(p.area for p in tagged)
        if len(groups) > 6 and sum(p.area for p in chosen) < 0.5 * total:
            raise ValueError(f"{_core.given_name(ob)}: the faces named {which!r} are not flat")
    normal, point = _plane(me, chosen, ob.matrix_basis)
    if normal is None:
        raise ValueError(f"{_core.given_name(ob)}: the face {which!r} has no area")
    z = Frame((0, 0, 0), normal).z      # its axes cleaned of dust, as the frame will have them
    offset = sum(c * p for c, p in zip(z, point))
    return Frame([c * offset for c in z], normal)._read_on(ob, ob.matrix_basis)


def _facing(ob, which):
    """The faces of `ob` looking the direction `which` ("+Z", "-X", in the space `ob` is in) within
    1°, and furthest that way: what `face` and `shell(open=)` read a direction as. [] if none."""
    d = _DIRECTION.match(which)
    axis = Vector({"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[d.group(2).lower()])
    if d.group(1) in ("-", "<"):
        axis = -axis
    rot = ob.matrix_basis.to_3x3()
    local = (rot.inverted() @ axis).normalized()
    chosen = [p for p in ob.data.polygons if p.normal.dot(local) > math.cos(math.radians(1))]
    if not chosen and ob.data.attributes.get(_core.FACE_TAG + "field") is not None:
        facing = [p for p in ob.data.polygons if p.normal.dot(local) > 0]
        if facing:
            return [max(facing, key=lambda p: (p.center.dot(local), -p.index))]
    if not chosen:
        return []
    far = max(p.center.dot(local) for p in chosen)
    return [p for p in chosen if p.center.dot(local) > far - 1e-6 * max(_core.mm(1.0), abs(far))]


def _plane(me, polys, m):
    """The plane of flat faces, placed by `m`: a normal and a point on it, in double
    precision from the mesh's points; the normal is None if the faces have no area.

    Blender's own normal and centre of an n-gon are single-precision sums: the top of a
    12 mm disc came out at z = 12.0000095, and a part stood on it floated off it.
    The normal is Newell's over every face (so weighted by area), the point the mean of
    their corners."""
    pts, n = [], [0.0, 0.0, 0.0]
    for poly in polys:
        corners = [tuple(me.vertices[i].co) for i in poly.vertices]
        for (x0, y0, z0), (x1, y1, z1) in zip(corners, corners[1:] + corners[:1]):
            n[0] += (y0 - y1) * (z0 + z1)
            n[1] += (z0 - z1) * (x0 + x1)
            n[2] += (x0 - x1) * (y0 + y1)
        pts += corners
    centre = [sum(p[k] for p in pts) / len(pts) for k in range(3)]
    a = [[m[row][col] for col in range(3)] for row in range(3)]
    # a normal goes through the cofactor matrix: the inverse transpose, up to the determinant
    cof = [[a[(r + 1) % 3][(c + 1) % 3] * a[(r + 2) % 3][(c + 2) % 3]
            - a[(r + 1) % 3][(c + 2) % 3] * a[(r + 2) % 3][(c + 1) % 3] for c in range(3)] for r in range(3)]
    det = sum(a[0][c] * cof[0][c] for c in range(3))
    normal = [math.copysign(1.0, det) * sum(cof[r][c] * n[c] for c in range(3)) for r in range(3)]
    size = math.sqrt(sum(c * c for c in normal))
    point = [sum(a[r][c] * centre[c] for c in range(3)) + m[r][3] for r in range(3)]
    return ([c / size for c in normal] if size > 0 else None), point


#: Points of an edge path closer than this (mm) are one: a boolean leaves slivers along its
#: seams, and a step of no length has no direction to sweep along.
EDGE_WELD = 0.02


def edge(ob, which):
    """Path along the edges named which, in the space ob is in: the longest run (as long: the one reaching
    furthest -X, then -Y, -Z), closed if it closes.

    The edges of `ob` named `which` ("top", "cut", a cut tool's name, "plate.top") as a
    path, in the space `ob` is in, as `ob.face` reads a face: the longest run of them, a
    closed path if it closes — for `wire`, `sweep` and `along`: a rolled rim along the
    line a trim left, `s3d.wire("lip", tub.edge("above_rim"), d=56)`. A closed run turns
    anticlockwise seen from +Z (from +Y, from +X if it stands that way), from where it
    crosses its own +X (+Z, +Y); an open one runs toward +X (then +Y, +Z). Edges that fork
    raise: a path follows a line, not a junction."""
    me = ob.data
    att = me.attributes.get(_core.tag_key(_core.EDGE_TAG, which)) if isinstance(which, str) else None
    if att is None or att.domain != "EDGE":
        names = sorted(a.name[len(_core.EDGE_TAG):] for a in me.attributes if a.name.startswith(_core.EDGE_TAG))
        raise ValueError(_core.unknown(_core.given_name(ob), "edge", [str(which)], names))
    links = {}
    for e, flag in zip(me.edges, att.data):
        if flag.value:
            a, b = e.vertices
            links.setdefault(a, []).append(b)
            links.setdefault(b, []).append(a)
    if not links:
        raise ValueError(f"{_core.given_name(ob)}: no edge carries {which!r} any more")
    forks = sorted(v for v, n in links.items() if len(n) > 2)
    if forks:
        raise ValueError(f"{_core.given_name(ob)}: the edges named {which!r} fork at {len(forks)} point(s) — a path "
                         f"follows a line, not a junction: name one loop or one run (a single cut's)")
    m = ob.matrix_basis
    co = {v: m @ me.vertices[v].co for v in links}
    runs, seen = [], set()
    for start in sorted(links, key=lambda v: (len(links[v]) != 1, v)):   # open runs from an end
        if start in seen:
            continue
        run, here = [start], start
        seen.add(start)
        while True:
            nxt = [v for v in links[here] if v not in seen]
            if not nxt:
                break
            here = min(nxt)
            run.append(here)
            seen.add(here)
        closed = len(links[start]) == 2
        pts = [co[run[0]]]
        for v in run[1:]:
            if (co[v] - pts[-1]).length > _core.mm(EDGE_WELD):
                pts.append(co[v])
        if closed and len(pts) > 1 and (pts[-1] - pts[0]).length <= _core.mm(EDGE_WELD):
            pts.pop()
        length = sum((b - a).length for a, b in zip(pts, pts[1:] + (pts[:1] if closed else [])))
        runs.append((length, closed, pts))
    # the longest; of runs as long, the one reaching furthest -X (then -Y, -Z): one answer, whatever the order
    length, closed, pts = max(runs, key=lambda r: (round(_core.in_mm(r[0]), 6),
                                                   tuple(-round(_core.in_mm(c), 6) for c in min(tuple(q) for q in r[2]))))
    if len(pts) < (3 if closed else 2):
        raise ValueError(f"{_core.given_name(ob)}: the edges named {which!r} are too short to make a path")
    return Path([tuple(p) for p in (_loop_order(pts) if closed else _run_order(pts))], closed=closed)


def _loop_order(pts):
    """A closed run anticlockwise about the axis its area faces most (Z, then Y, then X), from
    the point nearest the ray from its centre along that view's first axis."""
    n = Vector()
    for a, b in zip(pts, pts[1:] + pts[:1]):
        n += a.cross(b)
    axis = max((2, 1, 0), key=lambda k: abs(n[k]) + 1e-9 * k)
    if n[axis] < 0:
        pts = pts[::-1]
    u, v = {2: (0, 1), 1: (2, 0), 0: (1, 2)}[axis]
    c = sum(pts, Vector()) / len(pts)
    first = min(range(len(pts)), key=lambda i: (round(math.atan2(pts[i][v] - c[v], pts[i][u] - c[u])
                                                      % (2 * math.pi), 9), i))
    return pts[first:] + pts[:first]


def _run_order(pts):
    """An open run toward +X, then +Y, then +Z."""
    key = [tuple(round(_core.in_mm(c), 6) for c in p) for p in (pts[0], pts[-1])]
    return pts[::-1] if key[1] < key[0] else pts


_SIDES = re.compile(r"[+\-<>]?[xyzXYZ]")


def _sides(which, what):
    """`which` — "+X", "+X-Y", "-Y+X+Z" — as [(axis, ±1)]: one to three different axes,
    a sign on each (a lone axis may go without: "+")."""
    terms = _SIDES.findall(which) if isinstance(which, str) else []
    if (not terms or "".join(terms) != which or len(terms) > 3
            or (len(terms) > 1 and any(t[0] not in "+-<>" for t in terms))
            or len({t[-1].lower() for t in terms}) < len(terms)):
        raise ValueError(f"{what}: {which!r} names no side of a box: a side \"+X\", an edge \"+X-Y\" or a corner "
                         f"\"+X-Y+Z\" — a sign and an axis for each, every axis once")
    return [("xyz".index(t[-1].lower()), -1 if t[0] in "-<" else 1) for t in terms]


def _placed_points(ob):
    """Every mesh point under `ob` (itself included), in the space `ob` is in: the
    placements composed and snapped as `_core.world` does, the points moved in double
    precision."""
    out = []

    def walk(o, m):
        if o.type == "MESH":
            rows = [[m[r][c] for c in range(4)] for r in range(3)]
            co = [0.0] * (3 * len(o.data.vertices))
            o.data.vertices.foreach_get("co", co)
            for i in range(0, len(co), 3):
                x, y, z = co[i], co[i + 1], co[i + 2]
                out.append(tuple(r[0] * x + r[1] * y + r[2] * z + r[3] for r in rows))
        for c in o.children:
            walk(c, _core.snapped(m @ c.matrix_parent_inverse @ c.matrix_basis))
    walk(ob, _core.snapped(Matrix(ob.matrix_basis)))
    return out


def bbox(ob, which):
    """Frame on its bounding box: a side "+X", an edge "+X-Y", a corner "+X-Y+Z".

    A frame on the box that bounds `ob` — a part, a group or an assembly, everything
    under it — in the space it is in, its sides along that space's axes: `"+X"` is the
    centre of the side looking +X, `"+X-Y"` the middle of the edge it shares with the
    side looking -Y, `"+X-Y+Z"` a corner. The frame has the axes of a face looking the
    first way named — its normal that way — and is read on `ob`, as `ob.face` is."""
    from .assembly import Handle
    root = ob.root if isinstance(ob, Handle) else ob
    if not isinstance(root, bpy.types.Object):
        raise TypeError(f"bbox: a part, a group or an assembly is expected, not {type(ob).__name__}")
    sides = _sides(which, "bbox")
    pts = _placed_points(root)
    if not pts:
        raise ValueError(f"bbox: {_core.given_name(root)!r} holds no solid: it has no box")
    lo = [min(p[k] for p in pts) for k in range(3)]
    hi = [max(p[k] for p in pts) for k in range(3)]
    origin = [(lo[k] + hi[k]) / 2 for k in range(3)]
    for axis, sign in sides:
        origin[axis] = hi[axis] if sign > 0 else lo[axis]
    normal = [0.0, 0.0, 0.0]
    normal[sides[0][0]] = float(sides[0][1])
    return Frame(origin, normal)._read_on(root, root.matrix_basis)


def local(ob, x=0, y=0, z=0, rx=0, ry=0, rz=0):
    """Frame at (x, y, z) of its own space, turned (rx, ry, rz) degrees.

    A frame on `ob` — a part, a group or an assembly — at (x, y, z) of `ob`'s own
    space, the one it was built in, turned (rx, ry, rz) degrees as `at` turns: a
    source's joint origin, its xyz and rpy, as written. Like `ob.face` and `bbox`,
    it is in the space `ob` is in and read on `ob`: `at(part, on=…)` puts a part there,
    and a joint on it takes its pivot from it, wherever `ob` has gone since."""
    from .assembly import Handle
    root = ob.root if isinstance(ob, Handle) else ob
    if not isinstance(root, bpy.types.Object):
        raise TypeError(f"local: a part, a group or an assembly is expected, not {type(ob).__name__}: the frame is "
                        f"read on it, at a point of its own space")
    values = dict(zip(KEYS, (x, y, z, rx, ry, rz)))
    for name, v in values.items():
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise TypeError(f"local: {name} is a number, not {v!r}")
    basis = _core.snapped(Matrix(root.matrix_basis))
    return _frame_of(_core.snapped(basis @ _turned(values)))._read_on(root, basis)


def _frame_only(method):
    def refuse(ob, *args, **kwargs):
        raise TypeError(f"{_core.given_name(ob)!r} is a solid: it moves with s3d.transform(ob, x=…, rz=…), or "
                        f"s3d.at(ob, …) places it; .{method}() is a frame's")
    return refuse


bpy.types.Object.face = face
bpy.types.Object.edge = edge
for _method in ("move", "turn", "offset"):
    setattr(bpy.types.Object, _method, _frame_only(_method))
# bpy 4.5 never exits while a Python attribute sits on an RNA type: take them off first.
atexit.register(lambda: [delattr(bpy.types.Object, a) for a in ("face", "edge", "move", "turn", "offset")
                         if hasattr(bpy.types.Object, a)])


# ---------------------------------------------------------------- placing

#: Anchor words and the bounding-box side they pick on each axis.
_ANCHOR_WORDS = {"left": (0, -1), "right": (0, 1), "front": (1, -1), "back": (1, 1),
                 "bottom": (2, -1), "top": (2, 1), "center": None, "centre": None}


def _anchor_point(lo, hi, anchor):
    """The point of the box (lo, hi) an anchor names: "bottom", "top-front", "bottom-left-back"…
    or the directions `bbox` takes: "-Z", "+Y-Z", "+X-Y+Z"."""
    p = (lo + hi) / 2
    if anchor in (None, "origin"):
        return Vector((0, 0, 0))
    if isinstance(anchor, str) and re.fullmatch(r"([+\-<>][xyzXYZ])+|[xyzXYZ]", anchor.strip()):
        for axis, side in _sides(anchor.strip(), f"anchor {anchor!r}"):
            p[axis] = hi[axis] if side > 0 else lo[axis]
        return p
    for word in re.split(r"[-_ ]+", anchor.strip().lower()):
        if word not in _ANCHOR_WORDS:
            raise ValueError(f"anchor {anchor!r}: {word!r} is none of {sorted(_ANCHOR_WORDS)}, and the anchor is "
                             f"no directions either (\"-Z\", \"+Y-Z\", \"+X-Y+Z\")")
        if _ANCHOR_WORDS[word]:
            axis, side = _ANCHOR_WORDS[word]
            p[axis] = hi[axis] if side > 0 else lo[axis]
    return p


def _bounds(ob):
    """(lo, hi) of everything under `ob`, in `ob`'s own frame."""
    pts = []

    def walk(o, m):
        if o.type == "MESH":
            pts.extend(m @ v.co for v in o.data.vertices)
        for c in o.children:
            walk(c, m @ c.matrix_parent_inverse @ c.matrix_basis)
    walk(ob, Matrix.Identity(4))
    if not pts:
        return Vector((0, 0, 0)), Vector((0, 0, 0))
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def _mirror(mirror):
    s = [1.0, 1.0, 1.0]
    for c in (mirror or "").lower():
        if c not in "xyz":
            raise ValueError(f"transform: mirror is among 'x', 'y', 'z' — the coordinates that change sign — not "
                             f"{mirror!r}")
        s["xyz".index(c)] = -1.0
    return Matrix.Diagonal((*s, 1.0))


#: Custom property: the frame, the values and the anchor point `at` last placed an object with.
PLACE = "s3d~place"
KEYS = ("x", "y", "z", "rx", "ry", "rz")


def frames_of(on, verb, param="on"):
    """`on` as a list of frames, for `verb`'s parameter `param`; anything else raises."""
    if not isinstance(on, (list, tuple)) or not on or not all(isinstance(f, Frame) for f in on):
        raise TypeError(f"{verb}: {param} is a frame or a list of frames, as grid(), ring() and along() give")
    return list(on)


def _elements(ob):
    """The things a list stands for, nested lists opened — objects, handles, profiles,
    paths — or None if `ob` is not such a list (a list of points is a path)."""
    from .assembly import Handle
    if not isinstance(ob, (list, tuple)) or not ob:
        return None
    out = []
    for item in ob:
        if isinstance(item, (list, tuple)):
            inner = _elements(item)
            if inner is None:
                return None
            out += inner
        elif isinstance(item, (bpy.types.Object, Handle, Profile, Placed, Path)):
            out.append(item)
        else:
            return None
    return out


def _turned(values):
    v = values
    return Matrix.Translation((v["x"], v["y"], v["z"])) @ Euler(
        (math.radians(v["rx"]), math.radians(v["ry"]), math.radians(v["rz"]))).to_matrix().to_4x4()


def at(ob, x=None, y=None, z=None, rx=None, ry=None, rz=None, on=None, anchor=None, *, scale=None):
    """Place it: set what is given, keep the rest; anchor: "-Z", "+Y-Z"….

    Put `ob` at (x, y, z), turned (rx, ry, rz) degrees, in the frame `on` — or in the
    frame it is in already (its parent's, at first). Only the values given change: the
    others keep what `at` set before (0 at first), and `on` changes the frame, keeping
    them. `anchor` names the point of its bounding box that goes there: directions, as
    `bbox` takes them ("-Z", "+Y-Z", "+X-Y+Z"), or words ("bottom", "top-front",
    "bottom-left-back": top bottom left right front back are +Z -Z -X +X -Y +Y); its own
    origin by default. Returns `ob`: an
    object, a handle, a profile (placed — a loft's section) or a path (moved); each of
    a list. With a list of frames for `on`, `ob` is used up and one copy goes on each
    frame: the list of copies is returned (of placed profiles, for a profile). A mirror
    image is `transform`'s.

    `scale` acts about its own origin before placement and reading the placement
    anchor: a solid takes a number or (sx, sy, sz), a group/handle one positive
    factor, as scale(). With frame lists, a number or numeric axis tuple applies
    to every copy; other sequences give exactly one value per frame. With one/no
    frame, give one value. Profiles/paths do not take scale. Read geometry frames
    after scaling; previously read frames and handle anchors do not rescale."""
    from .assembly import Handle
    given = {k: v for k, v in zip(KEYS, (x, y, z, rx, ry, rz)) if v is not None}
    if isinstance(on, (list, tuple)):
        return _on_frames(ob, frames_of(on, "at"), given, anchor, scale)
    if on is not None and not hasattr(on, "matrix"):
        raise TypeError(f"at: on is a frame or a list of frames, as grid(), ring() and along() give, not {on!r}")
    items = _elements(ob)
    if items is not None:
        if anchor is not None and any(isinstance(i, (bpy.types.Object, Handle)) for i in items):
            raise ValueError("at: anchor on a list of objects: each has its own box — place them one by one")
        return [at(i, x, y, z, rx, ry, rz, on, anchor, scale=scale) for i in items]
    if scale is not None:
        anchor = _scaled(ob, scale, anchor)
    frame = on.matrix if on is not None else None
    if isinstance(ob, Handle):
        at(ob.root, x, y, z, rx, ry, rz, on, anchor)
        return ob
    if isinstance(ob, (Profile, Placed, Path, list, tuple)):
        return _replaced(ob, frame, given)
    return _posed(ob, frame, given, anchor)


def _posed(ob, frame, given, anchor):
    """`ob` placed by what it was placed with, `given` and the rest replacing it. The
    anchor's point is the one found when the anchor was given: moving the part does not
    re-anchor it on a box that grew since — giving `anchor` again does."""
    if not (given or frame is not None or anchor is not None):
        return ob                                   # `at(ob)`: nothing to change
    from .joints import refuse_at
    refuse_at(ob)
    kept_frame, values, kept_anchor, point = _recalled(ob)
    if frame is not None:
        kept_frame = frame
    values.update(given)
    if anchor is not None:
        kept_anchor, point = anchor, _anchor_point(*_bounds(ob), anchor)
    ob.matrix_basis = _pose(kept_frame, values, point)
    _remember(ob, kept_frame, values, kept_anchor, point)
    return ob


def _pose(frame, values, point):
    m = _turned(values)
    if frame is not None:
        m = frame @ m
    return m @ Matrix.Translation(-point)


def _replaced(ob, frame, given):
    """A profile or a path placed again: the frame and values it was placed with, `given`
    replacing them, over what it was placed from. (Not `_pose`: a profile has no anchor,
    and a single call must give the matrix it always gave.)"""
    kept_frame, values, base = _recalled_value(ob)
    if frame is not None:
        kept_frame = frame
    values.update(given)
    full = _turned(values)
    if kept_frame is not None:
        full = kept_frame @ full
    if isinstance(ob, (Profile, Placed)):
        out = Placed(ob.profile if isinstance(ob, Placed) else ob, full @ base)
    else:
        out = Path([tuple(full @ Vector(p)) for p in base.points], closed=base.closed, sharp=base.sharp)
    out._s3d_place = (kept_frame, values, base)
    return out


def _recalled_value(ob):
    """(frame, values, base) a profile or a path was placed with; never placed: no frame,
    values 0, and itself as the base."""
    kept = getattr(ob, "_s3d_place", None)
    if kept is not None:
        frame, values, base = kept
        return frame, dict(values), base
    base = ob.matrix if isinstance(ob, Placed) else (Matrix.Identity(4) if isinstance(ob, Profile) else _as_path(ob))
    return None, dict.fromkeys(KEYS, 0.0), base


def transform(ob, x=0, y=0, z=0, rx=0, ry=0, rz=0, mirror=None):
    """Move it by, as a parent would; its placement, not its mesh.

    Add to where `ob` is: moved by (x, y, z), turned (rx, ry, rz) degrees about its
    parent's origin, `mirror` ("x", "yz"…) its image across those planes of its parent —
    what `at` on a group around it would do. The placement changes, not the mesh; a
    jointed part moves with its pivot, and its mirror image moves as the image of the
    motion. Returns
    `ob`: an object, a handle (its root moves), each of a list, or a new profile or path.
    It moves the frame `ob` is in: a later `at(ob, x=…)` places it in the moved frame,
    `at(ob, on=…)` in a new one."""
    if isinstance(ob, Frame) or isinstance(ob, (list, tuple)) and ob and all(isinstance(f, Frame) for f in ob):
        raise TypeError("transform: a frame moves with its own .move(), .turn() and .offset(), and so does a list "
                        "of frames")
    items = _elements(ob)
    if items is not None:
        _not_nested(items, "transform")
    return _transform(ob, _turned(dict(zip(KEYS, (x, y, z, rx, ry, rz)))) @ _mirror(mirror))


def _not_nested(items, verb):
    """Refuse a list holding a group and one of its own parts: the part would go twice."""
    from .assembly import Handle
    roots = {(i.root if isinstance(i, Handle) else i).as_pointer() for i in items
             if isinstance(i, (bpy.types.Object, Handle))}
    for i in items:
        o = i.root if isinstance(i, Handle) else i
        parent = getattr(o, "parent", None)
        while parent is not None:
            if parent.as_pointer() in roots:
                raise ValueError(f"{verb}: {_core.given_name(o)!r} is inside {_core.given_name(parent)!r}, which "
                                 f"this call moves whole: give one of them")
            parent = parent.parent


def _transform(ob, m):
    from .assembly import Handle
    items = _elements(ob)
    if items is not None:
        return [_transform(i, m) for i in items]
    if isinstance(ob, Handle):
        _transform(ob.root, m)
        return ob
    if isinstance(ob, (Profile, Placed, Path, list, tuple)):
        frame, values, base = _recalled_value(ob)
        if isinstance(ob, (Profile, Placed)):
            prof, inner = (ob.profile, ob.matrix) if isinstance(ob, Placed) else (ob, Matrix.Identity(4))
            out = Placed(prof, m @ inner)
        else:
            path = _as_path(ob)
            out = Path([tuple(m @ Vector(p)) for p in path.points], closed=path.closed, sharp=path.sharp)
        out._s3d_place = (m @ frame if frame is not None else Matrix(m), values, base)   # the frame moves
        return out
    kept = _recalled(ob) if ob.get(PLACE) is not None else None
    ob.matrix_basis = m @ ob.matrix_basis
    from .joints import moved
    moved(ob, m)                         # a jointed part moves with its pivot, at rest as posed
    if kept is not None:                 # the frame `at` placed it in moves with it
        frame, values, anchor, point = kept
        _remember(ob, m @ frame if frame is not None else Matrix(m), values, anchor, point)
    return ob


def _flat16(m):
    return [m[r][c] for r in range(4) for c in range(4)]


def _matrix16(f):
    return Matrix([list(f[4 * r:4 * r + 4]) for r in range(4)])


def _remember(ob, frame, values, anchor, point):
    """Keep on `ob` the frame (None: its parent's), the values, the anchor and the point
    of its box the anchor named, that it was placed with — and the placement Blender
    holds now, to tell later whether something else moved it."""
    ob[PLACE] = {**{k: float(v) for k, v in values.items()}, "anchor": anchor or "",
                 "point": [float(c) for c in point], "frame": [] if frame is None else _flat16(frame),
                 "basis": _flat16(ob.matrix_basis)}


def _recalled(ob):
    """(frame, values, anchor, anchor point) `at` last placed `ob` with. Never
    placed with `at` — or moved since by something else than sand3d — the placement it has
    is its frame, its values 0 (no frame at all for an object at its parent's origin)."""
    kept = ob.get(PLACE)
    if kept is not None:
        kept = kept.to_dict()
        frame = _matrix16(kept["frame"]) if len(kept["frame"]) == 16 else None
        values, anchor, point = {k: kept[k] for k in KEYS}, kept["anchor"] or None, Vector(kept["point"])
        now = Matrix(ob.matrix_basis)
        if _flat16(now) != list(kept.get("basis", [])) or kept.get("mirror"):
            # (a placement 0.x stored with a mirror is taken where it is, mirror and all)
            # moved by something else since (raw bpy): the move goes to the frame, the values stay
            frame = now @ _pose(None, values, point).inverted()
        return frame, values, anchor, point
    frame = Matrix(ob.matrix_basis)
    return (None if frame == Matrix.Identity(4) else frame), dict.fromkeys(KEYS, 0.0), None, Vector((0, 0, 0))


def _scaled(ob, factor, anchor):
    """Scale through the editing verb, then refresh any kept placement anchor."""
    from .assembly import Handle
    from .edit import scale
    root = ob.root if isinstance(ob, Handle) else ob
    scale(ob, factor)
    return _recalled(root)[2] if anchor is None else anchor


def _on_frames(ob, frames, given, anchor, scale=None):
    """`at(ob, on=[frames])`: `ob` used up, a copy on each frame — placed as `at` with one
    frame would place it."""
    from . import _guard
    from .assembly import Handle
    from .edit import _children, _copy, _delete_tree
    factors = [scale] * len(frames)
    if scale is not None and not isinstance(scale, (int, float)):
        if not (isinstance(scale, tuple) and len(scale) == 3
                and all(isinstance(v, (int, float)) for v in scale)):
            factors = list(scale)
            if len(factors) != len(frames):
                raise ValueError(f"at: on has {len(frames)} frames but scale has {len(factors)} values")
    items = _elements(ob)
    if items is not None:
        _not_nested(items, "at")
        return [c for i in items for c in _on_frames(i, frames, given, anchor, scale)]
    if not isinstance(ob, (bpy.types.Object, Handle)):
        if scale is not None:
            _scaled(ob, scale, anchor)
        return [_replaced(ob, f.matrix, given) for f in frames]
    _anchor_point(Vector(), Vector(), anchor)          # a wrong word raises before anything is made
    root = ob.root if isinstance(ob, Handle) else ob
    from .joints import refuse_at
    refuse_at(root)
    children = _children() if root.children else {}
    out = []
    try:
        for f, factor in zip(frames, factors):
            twin = _copy(ob, children)
            out.append(twin)
            placed_anchor = _scaled(twin, factor, anchor) if scale is not None else anchor
            _posed(twin.root if isinstance(twin, Handle) else twin, f.matrix, given, placed_anchor)
    except Exception:
        for twin in out:
            _delete_tree(twin.root if isinstance(twin, Handle) else twin)
        raise
    tree = [root]
    for o in tree:
        tree += children.get(o, [])
    _guard.using_up(tree, root)
    _delete_tree(root)
    return out


# ---------------------------------------------------------------- distributors

def grid(nx, ny=1, px=0, py=0, stagger=False, on=None):
    """On a grid.

    `nx` × `ny` frames `px` and `py` apart, centred on `on` (the origin by default);
    `stagger` shifts every other row by half a pitch."""
    base = _one(on, "grid")
    out = []
    for j in range(ny):
        shift = px / 2 if stagger and j % 2 else 0
        for i in range(nx):
            centre = px / 4 if stagger and ny > 1 else 0
            out.append(base.move((i - (nx - 1) / 2) * px + shift - centre, (j - (ny - 1) / 2) * py))
    return Frames(out)


def ring(n, r, start=0, angle=360, on=None):
    """On a circle.

    `n` frames on a circle of radius `r` round `on`'s normal, from `start` degrees
    (0 on its X): spread over `angle` degrees, evenly round a full turn. Each frame's
    X points outward, so a part placed on it turns with the ring."""
    base = _one(on, "ring")
    step = angle / n if abs(angle - 360) < 1e-9 else (angle / (n - 1) if n > 1 else 0)
    out = []
    for k in range(n):
        a = math.radians(start + step * k)
        radial = base.x * math.cos(a) + base.y * math.sin(a)
        out.append(base._kept(Frame(base.origin + radial * r, base.z, base.z.cross(radial))))
    return Frames(out)


def _finite(*values):
    return all(isinstance(v, (int, float)) and math.isfinite(v) for v in values)


def _random(seed, verb):
    if not isinstance(seed, int):
        raise ValueError(f"{verb}: seed must be an integer")
    return random.Random(seed)


def vary(value, spread, n, seed=0):
    """Values within spread of value, most near it.

    `n` floats: `value` plus a triangular draw in [-spread, spread], mode zero, from a
    local generator seeded by `seed`. `spread` is in the value's own unit, like the
    amounts of `jitter`: `vary(30, 6, n)` gives 24 to 36, `vary(0, 15, n)` -15 to 15
    degrees either way. A size varied by a fifth: `vary(reach, reach / 5, n)`.
    """
    if not _finite(value, spread) or spread < 0:
        raise ValueError("vary: value must be finite and spread finite and nonnegative")
    if not isinstance(n, int) or n < 0:
        raise ValueError("vary: n must be a nonnegative integer")
    rng = _random(seed, "vary")
    return [float(value + rng.triangular(-spread, spread, 0)) for _ in range(n)]


def _path_measure(path):
    pts = [Vector(p) for p in path.points]
    if path.closed:
        pts += pts[:1]
    # Repeated points have no tangent. Removing them leaves arc length unchanged.
    pts = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
    if len(pts) < 2:
        raise ValueError("along: path must have positive length")
    lengths = [0.0]
    for a, b in zip(pts, pts[1:]):
        lengths.append(lengths[-1] + (b - a).length)
    return pts, lengths


def _transport(frame, origin, tangent):
    # Resolve a half-turn about the old X: deterministic even at a reversal.
    if frame.z.dot(tangent) < -1 + 1e-7:
        up = -frame.y
    else:
        up = frame.z.rotation_difference(tangent) @ frame.y
    return frame._kept(Frame(origin, tangent, up))


def _path_frames(pts, lengths, spots, initial=None):
    """Sample in increasing arc length, transporting through every intervening segment."""
    tangents = [(b - a).normalized() for a, b in zip(pts, pts[1:])]
    frames = [Frame(pts[0], tangents[0]) if initial is None
              else _transport(initial, pts[0], tangents[0])]
    for i in range(1, len(tangents)):
        frames.append(_transport(frames[-1], pts[i], tangents[i]))
    out, j = Frames(), 0
    for distance in spots:
        while j < len(tangents) - 1 and lengths[j + 1] < distance:
            j += 1
        u = (distance - lengths[j]) / (lengths[j + 1] - lengths[j])
        out.append(frames[j]._kept(Frame(pts[j].lerp(pts[j + 1], u), tangents[j], frames[j].y)))
    return out


def along(path, pitch=None, count=None, spin=0, span=(0, 1)):
    """Along a path.

    Frames facing its tangent, every pitch or count evenly over span (arc-length
    fractions). A full closed path excludes the repeated endpoint with count.
    Successive frames turn spin degrees more about the tangent. With nonzero spin,
    X is parallel-transported through every path segment; zero keeps the historical
    world-Z reference. Closed paths may retain transport holonomy at their seam.
    """
    if (not isinstance(span, (list, tuple)) or len(span) != 2
            or not _finite(*span) or not 0 <= span[0] <= span[1] <= 1):
        raise ValueError("along: span is two increasing fractions in [0, 1]")
    if not _finite(spin):
        raise ValueError("along: spin must be finite")
    if count is not None and (not isinstance(count, int) or count < 0):
        raise ValueError("along: count must be a nonnegative integer")
    if pitch is not None and (not _finite(pitch) or pitch <= 0):
        raise ValueError("along: pitch must be finite and positive")
    path = _as_path(path)
    pts, lengths = _path_measure(path)
    total = lengths[-1]
    start, end = (v * total for v in span)
    extent = end - start
    if count is not None:
        divisor = count if path.closed and tuple(span) == (0, 1) else max(count - 1, 1)
        spots = [start + extent * k / divisor for k in range(count)]
    elif pitch is not None:
        spots = [start + pitch * k for k in range(int(extent / pitch + 1e-6) + 1)]
    else:
        raise ValueError("along: give a pitch or a count")
    if spin:
        return Frames(f.turn(rz=k * spin) for k, f in enumerate(_path_frames(pts, lengths, spots)))
    out, j = Frames(), 0
    for distance in spots:
        while j < len(pts) - 2 and lengths[j + 1] < distance:
            j += 1
        u = (distance - lengths[j]) / (lengths[j + 1] - lengths[j])
        out.append(Frame(pts[j].lerp(pts[j + 1], u), (pts[j + 1] - pts[j]).normalized()))
    return out


def _surface_parts(targets, verb):
    """Meshes keep their parent space; groups use the group's parent space."""
    from .assembly import Handle
    from ._surface import meshes
    roots = targets if isinstance(targets, (list, tuple)) else [targets]
    out = []
    for root in roots:
        if isinstance(root, Handle):
            root = root.root
        if not isinstance(root, bpy.types.Object):
            raise ValueError(f"{verb}: give a mesh part, group or list of them")
        if root.type == 'MESH':
            out.append((root, root.matrix_basis))
        else:
            parent = _core.world(root.parent) if root.parent else Matrix.Identity(4)
            out.extend((ob, parent.inverted() @ _core.world(ob)) for ob in meshes(root))
    if not out:
        raise ValueError(f"{verb}: group or list has no mesh descendants with surface area")
    return out


def _surface_candidates(parts, rng):
    """Area-weighted triangles in each mesh's parent space, as with snap."""
    triangles, cumulative, area = [], [], 0.0
    for ob, matrix in _surface_parts(parts, "scatter"):
        bm = bmesh.new()
        try:
            bm.from_mesh(ob.data)
            bm.transform(matrix)
            if not bm.faces or any(not e.is_manifold for e in bm.edges):
                raise ValueError("scatter: surface parts must be closed manifold meshes")
            # Preserve the solid's winding (including cavity walls); a reflected
            # placement reverses handedness, so reverse its faces once.
            if matrix.to_3x3().determinant() < 0:
                bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
            # Equal quad diagonals must not choose a different split when the
            # program changes units and float32 rounding breaks the tie.
            bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method='FIXED',
                                  ngon_method='EAR_CLIP')
            bm.normal_update()
            for face in bm.faces:
                a, b, c = [v.co.copy() for v in face.verts]
                weight = (b - a).cross(c - a).length / 2
                if weight > 0:
                    area += weight
                    cumulative.append(area)
                    triangles.append((a, b, c, face.normal.copy()))
        finally:
            bm.free()
    if not area:
        raise ValueError("scatter: parts need a nonzero surface area")

    def candidate():
        a, b, c, normal = triangles[bisect.bisect_right(cumulative, rng.random() * area)]
        u, v = math.sqrt(rng.random()), rng.random()
        return Frame(a * (1 - u) + b * (u * (1 - v)) + c * (u * v), normal)
    return candidate


def _scatter_best(n, candidate, position=lambda f: f.origin):
    points, out, tree, built = [], [], None, 0
    for i in range(n):
        if i and i % 64 == 0:
            tree = KDTree(i)
            for j, p in enumerate(points):
                tree.insert(p, j)
            tree.balance()
            built = i

        def distance(f):
            p = position(f)
            best = tree.find(p)[2] ** 2 if tree is not None else math.inf
            return min([best] + [(p - q).length_squared for q in points[built:]])
        chosen = max((candidate() for _ in range(16)), key=distance)
        points.append(position(chosen))
        out.append(chosen)
    return out


def scatter(n, size, seed=0, surface=False, on=None):
    """Evenly spread radial frames inside an ellipsoid or on its surface.

    A mesh part or list of mesh parts instead of size samples their closed surfaces
    by triangle area, with outward face normals, in each part's parent space (as snap).
    Parts must share a coordinate space. on is refused; surface is implicit. Separate
    parts retain all surfaces, including overlap interiors; join first to sample a union.
    Size otherwise gives three positive diameters in program units, centred on on. Mitchell
    sampling chooses the best of 16 candidates by physical nearest-neighbour distance.
    Surface candidates are uniform in area (ellipsoid Jacobian rejection); volume
    candidates are uniform in volume. Ellipsoid normals are radial, even on its surface.
    At most 4096 frames; a local seeded generator leaves global randomness untouched.
    """
    if not isinstance(n, int) or not 0 <= n <= 4096:
        raise ValueError("scatter: n must be an integer in [0, 4096]")
    if isinstance(size, bpy.types.Object) or (isinstance(size, (list, tuple))
            and (not size or isinstance(size[0], bpy.types.Object))):
        if on is not None:
            raise ValueError("scatter: on is only for ellipsoids; parts already carry placement")
        if not isinstance(surface, bool):
            raise ValueError("scatter: surface must be a boolean")
        parts = size if isinstance(size, (list, tuple)) else [size]
        return Frames(_scatter_best(n, _surface_candidates(parts, _random(seed, "scatter"))))
    if (not isinstance(size, (list, tuple)) or len(size) != 3
            or not _finite(*size) or any(v <= 0 for v in size)):
        raise ValueError("scatter: size must be three finite positive diameters")
    if not isinstance(surface, bool):
        raise ValueError("scatter: surface must be a boolean")
    rng, base = _random(seed, "scatter"), _one(on, "scatter")
    radii = [v / 2 for v in size]

    def candidate():
        while True:
            z, a = rng.uniform(-1, 1), rng.uniform(0, 2 * math.pi)
            r = math.sqrt(max(0, 1 - z * z))
            unit = (r * math.cos(a), r * math.sin(a), z)
            if not surface or rng.random() <= min(radii) * math.sqrt(sum((u / r) ** 2 for u, r in zip(unit, radii))):
                break
        scale = 1 if surface else rng.random() ** (1 / 3)
        return Vector([u * r * scale for u, r in zip(unit, radii)])

    points = _scatter_best(n, candidate, position=lambda p: p)
    out = Frames()
    for p in points:
        normal = base.x * p.x + base.y * p.y + base.z * p.z
        out.append(base._kept(Frame(base.origin + normal, normal)))
    return out


def _ray(direction):
    """A direction of `snap`: a named axis ("+Z", "-X", "Z"…) or a nonzero (x, y, z)."""
    d = _DIRECTION.match(direction) if isinstance(direction, str) else None
    if d:
        v = Vector({"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[d.group(2).lower()])
        return -v if d.group(1) in ("-", "<") else v
    if (isinstance(direction, (tuple, list, Vector)) and len(direction) == 3
            and all(isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in direction)
            and Vector(direction).length > 0):
        return Vector(direction).normalized()
    raise ValueError(f'snap: direction is a named axis ("+Z", "-X"…), a nonzero (x, y, z) or None, '
                     f'not {direction!r}')


def snap(targets, points, direction=None):
    """On a surface.

    Frames on the surface of `targets` (one object or several), one per point or
    frame of `points`: at the nearest spot, or where a line from it running along
    `direction` ("-Z", "+X"… or (x, y, z)) first meets the surface; each frame's normal
    points out of it. Points a line misses are dropped."""
    ray = None if direction is None else _ray(direction)
    size = _core.in_mm(1.0)   # Blender's BVH pads its boxes in its own units, which breaks ties: search in mm
    trees = [_core.mm_tree(ob, matrix) for ob, matrix in _surface_parts(targets, "snap")]
    out = []
    for p in points:
        p = Vector(p.origin if isinstance(p, Frame) else p) * size
        if direction is None:
            found = [t.find_nearest(p) for t in trees]
            loc, normal, _, _ = min((f for f in found if f[0] is not None), key=lambda f: f[3])
        else:
            found = [f for f in (t.ray_cast(p, ray) for t in trees) if f[0] is not None]
            if not found:
                continue
            loc, normal, _, _ = min(found, key=lambda f: f[3])
        out.append(Frame(loc / size, normal))
    return Frames(out)


def phyllotaxis(n, d, h=0, angle=137.508, on=None):
    """Frames on a disc, or facing out from a cylinder when h > 0.

    Each frame turns `angle` degrees from the previous; disc radii spread equal
    areas, cylinder heights spread evenly. Dimensions are in the program's unit.
    """
    if not isinstance(n, int) or n < 0:
        raise ValueError("phyllotaxis: n must be a nonnegative integer")
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (d, h, angle)) or d < 0 or h < 0:
        raise ValueError("phyllotaxis: finite d >= 0, h >= 0 and angle are required")
    base = _one(on, "phyllotaxis")
    out = Frames()
    for k in range(n):
        a = math.radians(k * angle)
        radial = base.x * math.cos(a) + base.y * math.sin(a)
        r = d / 2 if h else d / 2 * math.sqrt((k + 0.5) / n)
        origin = base.origin + radial * r + base.z * (h * (k + 0.5) / n)
        out.append(base._kept(Frame(origin, radial if h else base.z,
                                    base.z if h else base.z.cross(radial))))
    return out


class _Axis:
    """One named axis, with its parent axis (None on the root)."""

    def __init__(self, path, d, level, name, parent):
        self.path, self.d, self.level, self.name, self.parent = path, d, level, name, parent


class _Branches(list):
    """Depth-first axes and the frames at the ends of the leaf axes."""

    def __init__(self):
        super().__init__()
        self.tips = Frames()


def _branch_bend_bound(path, diameter, tip_ratio):
    """Conservative radius * curvature bound on sweep's smooth Hermite spans.

    Speed is bounded below by its projection on the chord; acceleration is
    linear, so its norm is bounded by its two endpoint norms. This bounds the
    whole span, including between the spline samples, without making meshes.
    """
    pts, lengths = _path_measure(path)
    if len(pts) != len(path.points):
        return math.inf
    steps = [b - a for a, b in zip(pts, pts[1:])]
    hs = [b - a for a, b in zip(lengths, lengths[1:])]
    directions = [v / h for v, h in zip(steps, hs)]
    slopes = [directions[0]] + [
        (directions[i - 1] * hs[i] + directions[i] * hs[i - 1]) / (hs[i - 1] + hs[i])
        for i in range(1, len(steps))] + [directions[-1]]
    worst = 0.0
    for i, (v, h) in enumerate(zip(directions, hs)):
        # Velocity in normalised span time: a*t*t + b*t + c.
        c = slopes[i]
        a = -6 * v + 3 * (c + slopes[i + 1])
        b = 6 * v - 4 * c - 2 * slopes[i + 1]
        av, bv, cv = a.dot(v), b.dot(v), c.dot(v)
        speed = min(cv, av + bv + cv)
        if av > 0 and 0 < -bv / (2 * av) < 1:
            speed = min(speed, cv - bv * bv / (4 * av))
        if speed <= 0:
            return math.inf
        acceleration = max(b.length, (2 * a + b).length) / h
        u = lengths[i] / lengths[-1]
        # The zero-tip rounded cap is no larger than sqrt(1-u).
        radius = diameter / 2 * ((1 - u) ** .5 if tip_ratio == 0
                                 else 1 - (1 - tip_ratio) * u)
        worst = max(worst, radius * acceleration / (speed * speed))
    return worst


def branches(length, d, levels=3, children=3, attach=(0.45, 0.9), angle=45,
             azimuth=137.508, length_ratio=0.55, diameter_ratio=0.55,
             tip_ratio=0.15, jitter=0, seed=0, on=None, wander=0, droop=0, *, step=None):
    """Depth-first axes and leaf-tip frames, straight or smoothly curved.

    A root along +Z and levels generations of children. Children attach evenly over `attach` (a lone child at its midpoint). Each axis
    exposes path, diameter law d, level, name and parent; tips are the leaf-end
    frames. Jitter varies lengths, lean angles and azimuth steps by up to its fraction, from a
    local seeded generator. A child's diameter is relative to its parent's
    base diameter, not its diameter at attachment; azimuth restarts at each
    parent. Paths and tips are already in the frame carrying `on`: use
    wire(axis.name, axis.path, axis.d), without applying `on` a second time.
    Wander bounds the random heading turn per each of eight segments (degrees).
    Droop turns toward on's -Z by up to its degrees over the axis; negative rises.
    Mesh rings sample accumulated turn at 3 degrees by default (facets overrides
    the angular count); step gives a positive maximum arc-length spacing.
    Curved axes are spline-smoothed Paths; attachments use their arc length and
    transported tangents. Zero wander and droop retain exact two-point straight axes.
    Curvature radii exceed twice the local section radius, so axes build with
    wire or a matching sweep law.
    Only leaf axes contribute tips. At most 4096 axes and 128 levels.
    """
    if any(not isinstance(v, int) or v < 0 for v in (levels, children)):
        raise ValueError("branches: levels and children must be nonnegative integers")
    if step is not None and (isinstance(step, bool) or not isinstance(step, (int, float)) or not math.isfinite(step) or step <= 0):
        raise ValueError("branches: step must be a positive finite spacing")
    count, generation = 1, 1
    for _ in range(levels):
        generation *= children
        count += generation
        if count > 4096 or levels > 128:
            raise ValueError("branches: at most 4096 axes and 128 levels")
        if generation == 0:
            break
    numbers = (length, d, angle, azimuth, length_ratio, diameter_ratio, tip_ratio, jitter, wander, droop)
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in numbers):
        raise ValueError("branches: parameters must be finite numbers")
    if length <= 0 or d <= 0 or length_ratio <= 0 or diameter_ratio <= 0:
        raise ValueError("branches: lengths, diameters and their ratios must be positive")
    if not 0 <= jitter <= 1 or not 0 <= tip_ratio <= 1 or not isinstance(seed, int):
        raise ValueError("branches: jitter and tip_ratio are in [0, 1]; seed is an integer")
    if (not isinstance(attach, (list, tuple)) or len(attach) != 2
            or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in attach)
            or not 0 <= attach[0] <= attach[1] <= 1):
        raise ValueError("branches: attach is two increasing fractions in [0, 1]")
    if wander < 0:
        raise ValueError("branches: wander must be nonnegative")
    base = _one(on, "branches")
    rng, out = random.Random(seed), _Branches()

    def grow(frame, size, diameter, level, name, parent):
        curved = bool(wander or droop)
        path = Path([frame.origin, frame.point(z=size)])
        if curved:
            from .profile import spline, _centripetal
            # Draw once: retries must not change the seeded child sequence.
            turns = [(rng.uniform(0, 360), rng.uniform(-wander, wander))
                     if wander else (0, 0) for _ in range(8)]
            gravity = -base.z if droop >= 0 else base.z
            for attempt in range(12):
                heading, controls = frame, [frame.origin]
                strength = .5 ** attempt
                for k, (bearing, lean) in enumerate(turns):
                    previous = heading
                    if wander:
                        heading = heading.turn(rz=bearing).turn(ry=lean * strength)
                    if droop:
                        angle_left = heading.z.angle(gravity)
                        turn = min(math.radians(abs(droop) / 8) * strength, angle_left)
                        axis = heading.z.cross(gravity)
                        if axis.length < 1e-7:
                            axis = heading.x
                        rotation = Matrix.Rotation(turn, 3, axis)
                        heading = Frame(heading.origin, rotation @ heading.z, rotation @ heading.y)
                    u = max(0, (k - 1) / 8)
                    radius = diameter / 2 * ((1 - u) ** .5 if tip_ratio == 0
                                             else 1 - (1 - tip_ratio) * u)
                    limit = min(math.pi / 3, size / 8 / (2 * radius))
                    turn = previous.z.angle(heading.z)
                    if turn > limit:
                        normal = previous.z.slerp(heading.z, limit / turn)
                        heading = _transport(heading, heading.origin, normal)
                    heading = heading.offset(size / 8)
                    controls.append(heading.origin)
                candidate = spline(controls)
                if _branch_bend_bound(candidate, diameter, tip_ratio) < .5:
                    path = candidate
                    sampled = Path(_centripetal(controls, False, angular=3, step=step))
                    if _branch_bend_bound(sampled, diameter, tip_ratio) < .5:
                        path._mesh_path = sampled
                    break
            # At extreme size/coordinate ratios float32 can obscure curvature;
            # the original straight path is the deterministic safe fallback.
        pts, lengths = _path_measure(path)
        axis = _Axis(path,
                     [(0, diameter), (1, diameter * tip_ratio)], level, name, parent)
        out.append(axis)
        if level == levels or children == 0:
            out.tips.append(_path_frames(pts, lengths, [lengths[-1]], frame)[0]
                            if curved else frame.offset(size))
            return
        for j in range(children):
            u = attach[0] + (attach[1] - attach[0]) * (j / (children - 1) if children > 1 else 0.5)
            lean = angle * (1 + rng.uniform(-jitter, jitter))
            child_length = size * length_ratio * (1 + rng.uniform(-jitter, jitter))
            bearing = j * azimuth
            if jitter:
                bearing += rng.uniform(-jitter, jitter) * azimuth
            attachment = (_path_frames(pts, lengths, [u * lengths[-1]], frame)[0]
                          if curved else frame.move(z=size * u))
            child = attachment.turn(rz=bearing).turn(ry=lean)
            grow(child, max(child_length, _core.mm(1e-9)), diameter * diameter_ratio,
                 level + 1, f"{name}/{j}", axis)
    grow(base, length, d, 0, "root", None)
    return out
