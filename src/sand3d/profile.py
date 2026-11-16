"""Profiles — the closed 2D regions solids are made from — and paths, the curves they follow.

A profile lies in its own XY plane, in the program's unit. Its outer loops run
anticlockwise and its holes clockwise. Every point records whether the outline
turns sharply there: the edges a solid grows from those points are its real
edges, the ones `fillet` and `chamfer` reach by name; the others only facet a
curve. `p + q` is the union of two profiles, `p - q` the first minus the second.
"""
import math

import bpy
from mathutils import Vector, geometry

from . import _core, _guard

#: Two points closer than this (mm, so `_core.mm(EPS)` in the program's unit) are one point.
EPS = 1e-6


# ---------------------------------------------------------------- the two types

class Loop:
    """One closed outline: points, and whether the outline turns sharply at each."""

    __slots__ = ("pts", "sharp")

    def __init__(self, pts, sharp):
        self.pts = [(float(x), float(y)) for x, y in pts]
        self.sharp = [bool(s) for s in sharp]

    def area(self):
        p = self.pts
        return 0.5 * sum(p[i - 1][0] * p[i][1] - p[i][0] * p[i - 1][1] for i in range(len(p)))

    def reversed(self):
        return Loop(self.pts[::-1], self.sharp[::-1])


class Profile:
    """A closed 2D region: what `extrude`, `revolve`, `sweep` and `loft` take."""

    def __init__(self, loops):
        self.loops = [loop if loop.area() >= 0 or len(loops) > 1 else loop.reversed() for loop in loops]
        self._mesh = None

    def __add__(self, other):
        return _boolean(self, _flat(other), lambda a, b: a or b)

    def __sub__(self, other):
        return _boolean(self, _flat(other), lambda a, b: a and not b)

    def area(self):
        return sum(loop.area() for loop in self.loops)

    def bounds(self):
        xs = [x for loop in self.loops for x, _ in loop.pts]
        ys = [y for loop in self.loops for _, y in loop.pts]
        return (min(xs), min(ys)), (max(xs), max(ys))

    def mesh(self):
        """The region triangulated: (points, sharp flags, loops as index lists, triangles).
        Cached; every solid built from this profile shares the same points."""
        if self._mesh is None:
            self._mesh = _region([self.loops], lambda w: w > 0)
        return self._mesh

    def __repr__(self):
        return f"Profile({len(self.loops)} loops, area {self.area():.6g})"


class Path:
    """A curve in space: points in order, open or `closed`. Profiles' outer loops,
    `arc`, `helix`, `spline` and plain lists of points are all paths."""

    def __init__(self, points, closed=False, sharp=None):
        self.points = [tuple(float(c) for c in (*p, 0.0)[:3]) if len(p) == 2 else tuple(map(float, p))
                       for p in points]
        self.closed = closed
        n = len(self.points)
        self.sharp = list(sharp) if sharp is not None else [i in (0, n - 1) and not closed for i in range(n)]

    def __getattribute__(self, name):
        return _read(self, name)

    def __iter__(self):
        return iter(self.points)

    def __len__(self):
        return len(self.points)

    def __getitem__(self, i):
        return self.points[i]

    def __del__(self, freed=_guard.freed):
        freed(self)


def _read(value, name):
    """An attribute of a path or a placed profile: reading a public one is a use (`_guard`)."""
    state = object.__getattribute__(value, "__dict__")
    if name[0] != "_" and state.get("_s3d_used") is False:
        state["_s3d_used"] = True
    return object.__getattribute__(value, name)


class Arc(Path):
    """An arc of a circle (or an ellipse), as a path and as a run of `poly`."""

    def __init__(self, center, r, start, end):
        cx, cy, cz = (*center, 0.0)[:3] if len(center) == 2 else center
        rx, ry = (r, r) if isinstance(r, (int, float)) else r
        n = _core.segments(max(abs(rx), abs(ry)), end - start)
        pts = [(cx + rx * math.cos(math.radians(start + (end - start) * i / n)),
                cy + ry * math.sin(math.radians(start + (end - start) * i / n)), cz) for i in range(n + 1)]
        closed = abs(abs(end - start) - 360) < 1e-9
        super().__init__(pts[:-1] if closed else pts, closed=closed)
        self.radii, self.angles, self.n = (rx, ry), (start, end), n

    def tangent(self, i):
        """Direction of travel at the i-th point."""
        (rx, ry), (start, end) = self.radii, self.angles
        a = math.radians(start + (end - start) * i / self.n)
        t = Vector((-rx * math.sin(a), ry * math.cos(a))) * (1 if end > start else -1)
        return t.normalized()


class _Through:
    """An arc of `poly` from the previous point, through `through`, to `to`."""

    def __init__(self, through, to):
        self.through, self.to = tuple(map(float, through)), tuple(map(float, to))


class _Tangent:
    """An arc of `poly` leaving the previous point tangent to the outline, ending at `to`."""

    def __init__(self, to):
        self.to = tuple(map(float, to))


class Placed:
    """A profile set in space by `at`: what `loft` takes as a section; `extrude` and
    `pocket` take it moved within its own plane only, the plane going in `on=`."""

    def __init__(self, profile, matrix):
        self.profile, self.matrix = profile, matrix

    def __getattribute__(self, name):
        return _read(self, name)

    def mesh(self):
        return self.profile.mesh()

    def __del__(self, freed=_guard.freed):
        freed(self)

    def __add__(self, other):
        return _flat(self) + other

    def __sub__(self, other):
        return _flat(self) - other


def _flat(p):
    """A profile; a placed one moved within its own plane (x, y, rz, mirror) becomes one."""
    if not isinstance(p, Placed):
        return p
    m = p.matrix
    moved = [(m @ Vector((x, y, 0))) for loop in p.profile.loops for x, y in loop.pts]
    if any(abs(q.z) > _core.mm(1e-6) for q in moved) or abs(abs(m.to_3x3().determinant()) - 1) > 1e-5:
        raise ValueError("a profile combined with + or - can only be moved within its plane")
    loops, k = [], 0
    for loop in p.profile.loops:
        pts = [moved[k + i].xy[:] for i in range(len(loop.pts))]
        k += len(loop.pts)
        loops.append(Loop(pts, loop.sharp) if m.to_3x3().determinant() > 0 else Loop(pts, loop.sharp).reversed())
    return Profile(loops)


def _as_path(path):
    """A Path from a Path, a Profile (its first outer loop, closed) or a list of points."""
    if isinstance(path, Path):
        return path
    if isinstance(path, Profile):
        loop = path.loops[0]
        return Path(loop.pts, closed=True, sharp=loop.sharp)
    return Path(list(path))



def _flat_point(q, verb, lift):
    """Refuse a point off the XY plane: a profile is drawn flat, and its z would be dropped."""
    if len(q) > 2 and abs(q[2]) > _core.mm(EPS):
        point = "(" + ", ".join(f"{float(c):g}" for c in q) + ")"
        raise ValueError(f"{verb}: the point {point} is off the plane of the profile (z = {float(q[2]):g}), and a "
                         f"profile is flat: {lift}")


POLY_LIFT = ("draw it in x and y and lift it with s3d.at(profile, z=...); a path in space is the list of points "
             "itself: s3d.wire(name, points, d)")
SPLINE_LIFT = ("a closed curve in space is s3d.spline(points, loop=True); a profile at a height, "
               "s3d.at(s3d.spline(points_in_x_y, closed=True), z=...)")

# ---------------------------------------------------------------- the region engine

def _winding(x, y, pts):
    w = 0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        if y0 <= y:
            if y1 > y and (x1 - x0) * (y - y0) - (x - x0) * (y1 - y0) > 0:
                w += 1
        elif y1 <= y and (x1 - x0) * (y - y0) - (x - x0) * (y1 - y0) < 0:
            w -= 1
    return w


def _region(loopsets, keep, extra=()):
    """The region where `keep(*windings)` holds, one winding number per loop set.

    Blender's constrained Delaunay triangulation splits the plane along every
    loop, crossings included; each triangle is kept or not by the winding numbers
    of its centroid, and the kept triangles' boundary is the region's outline.
    Returns (points, sharp, loops as index lists, triangles).
    """
    verts, sharp, edges, owner = [], [], [], []
    for s, loops in enumerate(loopsets):
        for loop in loops:
            base = len(verts)
            verts += loop.pts
            sharp += loop.sharp
            n = len(loop.pts)
            edges += [(base + i, base + (i + 1) % n) for i in range(n)]
    verts += list(extra)
    sharp += [False] * len(extra)
    out = _core.triangulate(verts, edges, 0, EPS)
    ov, ofaces, vorig = out[0], out[2], out[3]
    sets = [[loop.pts for loop in loops] for loops in loopsets]
    tris = []
    for f in ofaces:
        a, b, c = f
        pa, pb, pc = ov[a], ov[b], ov[c]
        cross = (pb[0] - pa[0]) * (pc[1] - pa[1]) - (pb[1] - pa[1]) * (pc[0] - pa[0])
        if abs(cross) < _core.mm2(1e-12):
            continue
        x, y = (pa[0] + pb[0] + pc[0]) / 3, (pa[1] + pb[1] + pc[1]) / 3
        if keep(*[sum(_winding(x, y, pts) for pts in s) for s in sets]):
            tris.append((a, b, c) if cross > 0 else (a, c, b))
    edge_set = {(t[i], t[(i + 1) % 3]) for t in tris for i in range(3)}
    outgoing = {}
    for a, b in sorted(edge_set):
        if (b, a) not in edge_set:
            outgoing.setdefault(a, []).append(b)
    loops = []
    while outgoing:
        start = min(outgoing)
        loop, v = [], start
        while True:
            loop.append(v)
            nxt = outgoing[v].pop(0)
            if not outgoing[v]:
                del outgoing[v]
            v = nxt
            if v == start:
                break
        first = min(range(len(loop)), key=lambda i: (min(vorig[loop[i]], default=len(verts)), i))
        loops.append(loop[first:] + loop[:first])
    used = sorted({v for loop in loops for v in loop} | {v for t in tris for v in t})
    index = {v: i for i, v in enumerate(used)}
    pts = [(ov[v][0], ov[v][1]) for v in used]
    flags = [any(sharp[o] for o in vorig[v]) if vorig[v] else True for v in used]
    for loop in loops:  # a point the outline runs straight through is no corner, whatever made it
        for i, v in enumerate(loop):
            a, b, c = ov[loop[i - 1]], ov[v], ov[loop[(i + 1) % len(loop)]]
            u, w = b - a, c - b
            if u.length and w.length and u.normalized().dot(w.normalized()) > 1 - 1e-9:
                flags[index[v]] = False
    return (pts, flags, [[index[v] for v in loop] for loop in loops],
            [tuple(index[v] for v in t) for t in tris])


def _from_region(region):
    pts, flags, loops, _ = region
    profile = Profile([Loop([pts[i] for i in loop], [flags[i] for i in loop]) for loop in loops])
    profile._mesh = region
    return profile


def _boolean(p, q, keep):
    return _from_region(_region([p.loops, q.loops], lambda a, b: keep(a > 0, b > 0)))


def _clean(pts, sharp):
    """Without repeated consecutive points, nor a last point repeating the first."""
    out, flags = [], []
    for p, s in zip(pts, sharp):
        if out and math.dist(out[-1], p) < _core.mm(EPS):
            flags[-1] = flags[-1] or s
            continue
        out.append(p)
        flags.append(s)
    while len(out) > 1 and math.dist(out[0], out[-1]) < _core.mm(EPS):
        out.pop()
        flags[0] = flags[0] or flags.pop()
    return out, flags


def _simple(pts):
    """Whether a closed polyline crosses itself (checked up to 400 points)."""
    n = len(pts)
    if n > 400:
        return True
    for i in range(n):
        a, b = Vector(pts[i]), Vector(pts[(i + 1) % n])
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            c, d = Vector(pts[j]), Vector(pts[(j + 1) % n])
            if geometry.intersect_line_line_2d(a, b, c, d) is not None:
                return False
    return True


def _single(pts, sharp):
    """A one-loop profile, its crossings resolved if it has any."""
    pts, sharp = _clean(pts, sharp)
    if len(pts) < 3:
        raise ValueError("a profile needs at least three distinct points")
    loop = Loop(pts, sharp)
    if loop.area() < 0:
        loop = loop.reversed()
    if _simple(loop.pts):
        return Profile([loop])
    return _from_region(_region([[loop]], lambda w: w != 0))


# ---------------------------------------------------------------- shapes

def circle(d):
    """Centred.

    A circle of diameter `d`, centred."""
    return ellipse(d, d)


def ellipse(w, d):
    """Centred.

    An ellipse `w` wide (X) and `d` deep (Y), centred."""
    arc_ = Arc((0, 0), (w / 2, d / 2), 0, 360)
    return Profile([Loop([p[:2] for p in arc_.points], [False] * len(arc_))])


def rect(w, d, r=0, chamfer=0):
    """Centred; corners rounded or cut.

    A rectangle `w` wide (X) and `d` deep (Y), centred; its corners rounded by
    `r` or cut by `chamfer`."""
    return poly([(-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2)], fillet=r, chamfer=chamfer)


def slot(l, d):
    """Round-ended slot along X.

    A slot `l` long overall (X) and `d` wide, its ends round, centred."""
    if l <= d:
        return circle(d)
    c = (l - d) / 2
    return poly([arc((c, 0), d / 2, -90, 90), arc((-c, 0), d / 2, 90, 270)])


def polygon(n, d):
    """Regular polygon, corner on +X.

    A regular polygon of `n` sides, its corners on a circle of diameter `d`, one on +X."""
    return poly([(d / 2 * math.cos(2 * math.pi * k / n), d / 2 * math.sin(2 * math.pi * k / n)) for k in range(n)])


#: Fewest points a superellipse gets: its corners are tight when n is large, and a loft
#: through it is pressed (`dent`) and sat on (`snap`) — 96 matched the chair (programs/scores.md).
SUPERELLIPSE_SIDES = 96


def superellipse(w, d, n=2, taper=0):
    """Ellipse (n=2) to box (n=4); taper narrows its +Y side, an egg.

    A section between an ellipse and a rectangle: `n` 2 an ellipse, 4 a box with
    round corners, 1.5 a diamond; `taper` narrows its +Y side by that fraction."""
    if w == 0 and d == 0:
        return Profile([Loop([(0, 0)], [False])])
    sides = (_core.segments(max(w, d) / 2) if _core.FACETS is not None
             else max(SUPERELLIPSE_SIDES, _core.segments(max(w, d) / 2)))
    dense = []
    for k in range(256):
        t = 2 * math.pi * k / 256
        c, s = math.cos(t), math.sin(t)
        dense.append((w / 2 * math.copysign(abs(c) ** (2 / n), c), d / 2 * math.copysign(abs(s) ** (2 / n), s)))
    lengths = [0.0]
    for a, b in zip(dense, dense[1:] + dense[:1]):
        lengths.append(lengths[-1] + math.dist(a, b))
    pts, j = [], 0
    for k in range(sides):
        target = lengths[-1] * k / sides
        while lengths[j + 1] < target:
            j += 1
        f = (target - lengths[j]) / max(lengths[j + 1] - lengths[j], _core.mm(1e-12))
        a, b = dense[j], dense[(j + 1) % 256]
        u, v = a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])
        pts.append((u * (1 - taper * 2 * v / d), v))
    return Profile([Loop(pts, [False] * sides)])


def station(z, w, d, x=0, y=0, n=2, taper=0):
    """Loft section at height z; n and taper as superellipse.

    A `superellipse` `w` wide and `d` deep, squareness `n`, its +Y side narrowed by
    `taper` (an egg), placed at height `z` centred on (x, y):
    `at(superellipse(w, d, n=n, taper=taper), x=x, y=y, z=z)`. A loft is a list of them:
    `loft(name, *[station(z, w, d) for z, w, d in rows])`."""
    from .frames import at
    out = at(superellipse(w, d, n=n, taper=taper), x=x, y=y, z=z)
    return out


# ---------------------------------------------------------------- outlines from points

def arc(center=(0, 0), r=1, start=0, end=360, *, through=None, to=None):
    """Arc from start to end, anticlockwise if end > start: a path, or a poly run.

    An arc round `center`, radius `r` (or `(rx, ry)` for an ellipse), from `start`
    to `end` degrees — anticlockwise when `end > start`, clockwise when `end < start` —
    a path, or a run of `poly`.
    Inside `poly`, `arc(through=p, to=q)` is the arc from the previous point through p to q."""
    if through is not None or to is not None:
        if _guard.given("arc", ("center", "r", "start", "end"), inside=()):
            raise ValueError("arc: either center, r, start and end, or through and to (inside poly), not both")
        if through is None or to is None:
            raise ValueError("arc: through and to go together, inside poly: arc(through=(x, y), to=(x, y))")
        return _Through(through, to)
    return Arc(center, r, start, end)


def tangent_arc(to):
    """Poly run: arc leaving tangent.

    Inside `poly`: an arc leaving the previous point tangent to the outline, ending at `to`."""
    return _Tangent(to)


def spline(pts, closed=False, tangents=None, loop=False):
    """Smooth curve; closed: a profile; loop: a ring path.

    A smooth curve through `pts` (2D or 3D): a profile when `closed`, else a path,
    which `poly` also takes as a run of its outline. `tangents=(start, end)` gives an
    open curve the direction it leaves its first point and reaches its last, as a CAD
    fitted spline has them; either may be None, and only the direction counts.
    `loop` joins the last point back to the first, smoothly: a closed path, flat or in
    space — a rim, a hoop, an O-ring for `wire`, `sweep` or `along`."""
    pts = [tuple(map(float, p)) for p in pts]
    if loop:
        if closed:
            raise ValueError("spline: closed=True is a flat profile, loop=True a closed path — one or the other")
        if tangents is not None:
            raise ValueError("spline: a loop has no ends to give a tangent")
        if len(pts) < 3:
            raise ValueError(f"spline: a loop needs three points or more, not {len(pts)}")
        return Path(_centripetal(pts, True), closed=True)
    if tangents is not None and closed:
        raise ValueError("a closed spline has no ends to give a tangent")
    if tangents is not None and len(tangents) != 2:
        raise ValueError(f"spline: tangents is (start, end), the directions at its two ends, not {len(tangents)} "
                         f"directions")
    start, end = tangents if tangents is not None else (None, None)
    if closed:
        for p in pts:
            _flat_point(p, "spline", SPLINE_LIFT)
    record = []
    dense = _centripetal(pts, closed, tangents=(start, end), _record=record)
    if closed:
        return _single([p[:2] for p in dense], [False] * len(dense))
    path = Path(dense)
    if _core.FACETS is not None:
        _spline_curve(path, record)
    return path


def _phantom(end, inner, tangent):
    """The point beyond `end` that makes the curve's tangent there `tangent`.

    Without one, the curve continues its chord. With one: the chord `inner -> end`
    reflected about the tangent's direction, which keeps the centripetal knots
    equal on both sides of `end`, and there the Catmull-Rom tangent is the mean of
    the two chords — the tangent's direction exactly."""
    if tangent is None:
        return 2 * end - inner
    chord = end - inner
    t = Vector((*map(float, tangent), 0.0)[:3])
    if t.length < 1e-12:
        raise ValueError("a spline tangent must not be zero")
    t.normalize()
    along = chord.dot(t)
    if along <= 1e-9 * max(chord.length, _core.mm(1.0)):
        raise ValueError("a spline end tangent must point along the curve, not back across it")
    return end + 2 * along * t - chord


def _centripetal(pts, closed, steps=12, tangents=(None, None), _record=None):
    """Centripetal Catmull–Rom through `pts`, `steps` pieces per span: no loops, no overshoot."""
    m = len(pts)
    if m < 2:
        raise ValueError("a spline needs two points")
    vs = [Vector((*p, 0.0)[:3]) if len(p) == 2 else Vector(p) for p in pts]
    dim = len(pts[0])
    if closed:
        ext = [vs[-1]] + vs + vs[:2]
    else:
        start, end = tangents
        # The start is walked backwards: its tangent is reversed with it.
        back = None if start is None else [-float(c) for c in start]
        ext = [_phantom(vs[0], vs[1], back)] + vs + [_phantom(vs[-1], vs[-2], end)]
    out = []
    for i in range(m if closed else m - 1):
        p0, p1, p2, p3 = ext[i:i + 4]
        t0 = 0.0
        t1 = t0 + max((p1 - p0).length, _core.mm(1e-9)) ** 0.5
        t2 = t1 + max((p2 - p1).length, _core.mm(1e-9)) ** 0.5
        t3 = t2 + max((p3 - p2).length, _core.mm(1e-9)) ** 0.5
        def evaluate(u, divisor=1, p0=p0, p1=p1, p2=p2, p3=p3, t0=t0, t1=t1, t2=t2, t3=t3):
            t = t1 + (t2 - t1) * u / divisor
            a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
            a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
            a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
            b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
            b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
            c = (t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2
            return c
        pieces = steps
        if _core.FACETS is not None:
            pieces = _core.turn_steps([[evaluate(k, 64) for k in range(65)]])
        if _record is not None:
            _record.append((evaluate, pieces))
        out.extend(tuple(evaluate(k, pieces))[:dim] for k in range(pieces))
    if not closed:
        out.append(tuple(vs[-1])[:dim])
    return out


def _spline_curve(path, record):
    """Arc-length lookup retaining the original cubic, independently of facets."""
    import bisect
    lengths, parameters = [0.], [0.]
    previous = record[0][0](0)
    for i,(evaluate,_) in enumerate(record):
        for j in range(1,257):
            point = evaluate(j/256)
            lengths.append(lengths[-1]+(point-previous).length)
            parameters.append(i+j/256)
            previous = point
    def distance(t):
        k = min(int(t*256),len(lengths)-2)
        return lengths[k]+(lengths[k+1]-lengths[k])*(t*256-k)
    def at_length(d):
        k = min(max(bisect.bisect_right(lengths,d)-1,0),len(lengths)-2)
        t = parameters[k]+(parameters[k+1]-parameters[k])*(d-lengths[k])/max(lengths[k+1]-lengths[k],1e-12)
        i = min(int(t),len(record)-1)
        u = t-i
        evaluate = record[i][0]
        tangent = (evaluate(min(1.,u+1e-4))-evaluate(max(0.,u-1e-4))).normalized()
        return evaluate(u),tangent
    path._curve_lengths = [distance(i+j/pieces) for i,(_,pieces) in enumerate(record) for j in range(pieces)]+[lengths[-1]]
    path._curve_at_length = at_length


def _circle_through(a, b, c):
    """Centre of the circle through three 2D points."""
    (ax, ay), (bx, by), (cx, cy) = a, b, c
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < _core.mm2(1e-12):
        raise ValueError(f"arc through {b} from {a} to {c}: the three points are in line")
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    return ux, uy


def _arc_points(center, p0, p1, ccw):
    """Points from p0 to p1 round `center`, p0 excluded, p1 included."""
    cx, cy = center
    r = math.dist(center, p0)
    a0 = math.atan2(p0[1] - cy, p0[0] - cx)
    a1 = math.atan2(p1[1] - cy, p1[0] - cx)
    sweep = (a1 - a0) % (2 * math.pi) if ccw else -((a0 - a1) % (2 * math.pi))
    if abs(sweep) < 1e-12:
        sweep = 2 * math.pi if ccw else -2 * math.pi
    n = _core.segments(r, math.degrees(sweep))
    return [(cx + r * math.cos(a0 + sweep * i / n), cy + r * math.sin(a0 + sweep * i / n)) for i in range(1, n + 1)]


def _tangent(center, p, ccw):
    """Direction of travel at `p` on a circle round `center`."""
    rx, ry = p[0] - center[0], p[1] - center[1]
    t = Vector((-ry, rx) if ccw else (ry, -rx))
    return t.normalized() if t.length else None


class _Node:
    """A point of `poly`'s outline while it is being drawn."""

    __slots__ = ("x", "y", "src", "tin", "tout", "line_out", "inner", "exact")

    def __init__(self, x, y, src=None, tin=None, tout=None, inner=False, exact=True):
        self.x, self.y, self.src = x, y, src
        self.tin, self.tout = tin, tout       # exact tangents where a curve meets the point
        self.line_out = False                 # the piece to the next point is a drawn straight line
        self.inner = inner                    # inside a curved run: never a corner
        self.exact = exact                    # tangents exact (arcs) or read off chords (splines)


def _outline(pts, verb, lift):
    """The points of an outline drawn through `pts` — (x, y) points, `arc(...)`,
    `tangent_arc(to)` and open `spline(...)` runs — as `_Node`s, first to last, not closed:
    what `poly` closes and `stroke` thickens."""
    nodes = []

    def add(node, line_in):
        if nodes and math.dist((nodes[-1].x, nodes[-1].y), (node.x, node.y)) < _core.mm(EPS):
            last = nodes[-1]
            last.tout = node.tout
            last.inner = last.inner and node.inner
            last.src = last.src if last.src is not None else node.src
            return
        if nodes:
            nodes[-1].line_out = line_in
        nodes.append(node)

    def heading():
        last = nodes[-1]
        if last.tout is not None:
            return last.tout
        if last.tin is not None:
            return last.tin
        if len(nodes) < 2:
            raise ValueError("tangent_arc needs a line or an arc before it")
        return Vector((last.x - nodes[-2].x, last.y - nodes[-2].y)).normalized()

    def circular(center, start, end, ccw):
        run = _arc_points(center, start, end, ccw)
        nodes[-1].tout = _tangent(center, start, ccw)
        for i, q in enumerate(run):
            last = i == len(run) - 1
            add(_Node(q[0], q[1], tin=_tangent(center, q, ccw), inner=not last), False)

    for k, item in enumerate(pts):
        for q in ((item.through, item.to) if isinstance(item, _Through) else (item.to,) if isinstance(item, _Tangent)
                  else item.points if isinstance(item, Path) else (item,)):
            _flat_point(q, verb, lift)
        if isinstance(item, _Through):
            if not nodes:
                raise ValueError("arc(through=, to=) needs a point before it")
            start = (nodes[-1].x, nodes[-1].y)
            ccw = ((item.through[0] - start[0]) * (item.to[1] - start[1])
                   - (item.through[1] - start[1]) * (item.to[0] - start[0])) > 0
            circular(_circle_through(start, item.through, item.to), start, item.to, ccw)
        elif isinstance(item, _Tangent):
            if not nodes:
                raise ValueError("tangent_arc needs a point before it")
            start = Vector((nodes[-1].x, nodes[-1].y))
            d = heading()
            n = Vector((-d.y, d.x))
            chord = Vector(item.to) - start
            denom = 2 * n.dot(chord)
            if abs(denom) < _core.mm(1e-12):
                add(_Node(*item.to), True)
                continue
            r = chord.length_squared / denom
            circular(tuple(start + n * r), tuple(start), item.to, r > 0)
        elif isinstance(item, Arc):
            run = [q[:2] for q in item.points]
            add(_Node(*run[0], tout=item.tangent(0)), True)
            for i, q in enumerate(run[1:], 1):
                last = i == len(run) - 1
                add(_Node(*q, tin=item.tangent(i) if last else None, inner=not last), False)
        elif isinstance(item, Path):
            run = [q[:2] for q in item.points]
            add(_Node(*run[0], exact=False), True)
            for i, q in enumerate(run[1:], 1):
                add(_Node(*q, inner=i < len(run) - 1, exact=False), False)
        else:
            add(_Node(float(item[0]), float(item[1]), src=k), True)
    return nodes


def poly(pts, fillet=0, chamfer=0):
    """Outline through points, arcs, splines.

    A closed outline through `pts`: (x, y) points joined by straight lines, with
    `arc(...)`, `tangent_arc(to)` or an open `spline(...)` among them for curved runs.
    `fillet` rounds and `chamfer` cuts the corners between two straight lines — one
    number for all of them, or a list giving each point its own (0 leaves it)."""
    nodes = _outline(pts, "poly", POLY_LIFT)
    if len(nodes) > 1 and math.dist((nodes[0].x, nodes[0].y), (nodes[-1].x, nodes[-1].y)) < _core.mm(EPS):
        last = nodes.pop()
        nodes[0].tin = last.tin
        nodes[0].inner = nodes[0].inner and last.inner
        nodes[-1].line_out = nodes[-1].line_out
    else:
        nodes[-1].line_out = True
    m = len(nodes)
    sharp = []
    for i, node in enumerate(nodes):
        prev, nxt = nodes[i - 1], nodes[(i + 1) % m]
        tin = node.tin if node.tin is not None else Vector((node.x - prev.x, node.y - prev.y))
        tout = node.tout if node.tout is not None else Vector((nxt.x - node.x, nxt.y - node.y))
        if node.inner or tin.length == 0 or tout.length == 0:
            sharp.append(False)
            continue
        limit = 1.0 if node.exact and prev.exact else 12.0
        sharp.append(tin.normalized().dot(tout.normalized()) < math.cos(math.radians(limit)))
    pts2 = [(n.x, n.y) for n in nodes]
    lines = [n.line_out for n in nodes]
    src = [n.src for n in nodes]
    pts2, sharp, lines, src = _corners(pts2, sharp, lines, src, fillet, "fillet")
    pts2, sharp, lines, src = _corners(pts2, sharp, lines, src, chamfer, "chamfer")
    return _single(pts2, sharp)


def _corners(pts, sharp, lines, src, amount, kind):
    """Round (`fillet`) or cut (`chamfer`) the drawn corners between two straight lines."""
    if not amount:
        return pts, sharp, lines, src
    m = len(pts)
    trims = {}
    for i in range(m):
        value = amount if isinstance(amount, (int, float)) else (
            amount[src[i]] if src[i] is not None and src[i] < len(amount) else 0)
        if not value or not sharp[i] or not (lines[i - 1] and lines[i]):
            continue
        p = Vector(pts[i])
        u = (p - Vector(pts[i - 1])).normalized()
        v = (Vector(pts[(i + 1) % m]) - p).normalized()
        turn = math.acos(max(-1.0, min(1.0, u.dot(v))))
        if turn < 1e-6:
            continue
        trims[i] = (value * math.tan(turn / 2) if kind == "fillet" else value, value, u, v)
    for i in range(m):
        j = (i + 1) % m
        used = trims.get(i, (0,))[0] + trims.get(j, (0,))[0]
        length = math.dist(pts[i], pts[j])
        if used > length + _core.mm(1e-9):
            raise ValueError(f"{kind} too large for the side from {pts[i]} to {pts[j]} ({used:.4g} > {length:.4g})")
    out = ([], [], [], [])

    def put(p, s, line, k=None):
        for lst, val in zip(out, (p, s, line, k)):
            lst.append(val)

    for i in range(m):
        if i not in trims:
            put(pts[i], sharp[i], lines[i], src[i])
            continue
        t, value, u, v = trims[i]
        p = Vector(pts[i])
        a, b = p - u * t, p + v * t
        if kind == "chamfer":
            put(tuple(a), True, True)
            put(tuple(b), True, lines[i])
            continue
        left = u.x * v.y - u.y * v.x > 0
        center = a + (Vector((-u.y, u.x)) if left else Vector((u.y, -u.x))) * value
        put(tuple(a), False, False)
        run = _arc_points(tuple(center), tuple(a), tuple(b), left)
        for k, q in enumerate(run):
            put(q, False, lines[i] if k == len(run) - 1 else False)
    return out


# ---------------------------------------------------------------- operations on profiles

def offset(p, t):
    """Grown by `t`.

    `p` grown by `t` all round (shrunk if `t` < 0); grown corners come out round."""
    if isinstance(p, Placed):
        out = Placed(offset(p.profile, t), p.matrix.copy())
        return out
    loops = []
    for loop in p.loops:
        pts, n = loop.pts, len(loop.pts)
        out, flags = [], []
        for i in range(n):
            a, b, c = Vector(pts[i - 1]), Vector(pts[i]), Vector(pts[(i + 1) % n])
            d0, d1 = (b - a).normalized(), (c - b).normalized()
            # the region lies left of travel, round holes too: away from it is the right
            n0, n1 = Vector((d0.y, -d0.x)), Vector((d1.y, -d1.x))
            cross = d0.x * d1.y - d0.y * d1.x
            if loop.sharp[i] and abs(cross) > 1e-9 and (cross > 0) == (t > 0) and n0.dot(n1) < 0.9999:
                out.append(tuple(b + n0 * t))
                flags.append(False)
                for q in _arc_points(tuple(b), tuple(b + n0 * t), tuple(b + n1 * t), cross > 0):
                    out.append(q)
                    flags.append(False)
                continue
            bis = n0 + n1
            bis = bis.normalized() if bis.length > 1e-9 else n0
            out.append(tuple(b + bis * (t / max(bis.dot(n0), 0.1))))
            flags.append(loop.sharp[i])
        loops.append(Loop(*_clean(out, flags)))
    out = _from_region(_region([loops], lambda w: w > 0))
    return out


STROKE_LIFT = "a stroke is drawn flat, in x and y: place the profile it makes with s3d.at(profile, ...)"


def stroke(path, t):
    """A band t wide along an open path, centred on it: a closed outline.

    The outline of `path` drawn with a pen `t` wide: `t / 2` on each side of it, its ends
    square, its corners mitred and sharp (a bent plate's edges are real edges), to extrude
    or revolve — a mudguard round a wheel, `stroke(arc((0, 0), 480, 180, 40), 18)`, a
    bracket, a strap, a wall drawn on its centre line. `path` is an open path: a `spline`,
    an `arc`, or (x, y) points with `arc(...)`, `tangent_arc(to)` and `spline(...)` runs
    among them, as `poly` takes them. A closed outline is a profile: `offset` grows it."""
    if isinstance(path, (Profile, Placed)) or (isinstance(path, Path) and path.closed):
        raise ValueError("stroke: the path is closed — a closed outline is a profile already: s3d.offset(p, t) "
                         "grows it, s3d.offset(p, t) - p is a band round it")
    if not t > 0:
        raise ValueError(f"stroke: t is the band's width, more than 0, not {t!r}")
    nodes = _outline([path] if isinstance(path, Path) else list(path), "stroke", STROKE_LIFT)
    pts = [Vector((n.x, n.y)) for n in nodes]
    m = len(pts)
    if m < 2:
        raise ValueError("stroke: a path needs two distinct points")
    if (pts[0] - pts[-1]).length < _core.mm(EPS):
        raise ValueError("stroke: the path ends where it starts — a closed outline is a profile already: "
                         "s3d.offset(p, t) grows it")
    left, right, sharp = [], [], []
    for i in range(m):
        d_in = (pts[i] - pts[i - 1]).normalized() if i else None
        d_out = (pts[i + 1] - pts[i]).normalized() if i < m - 1 else None
        if d_in is None:          # an end is square to the path: to an arc's own tangent there
            d_in = d_out = nodes[0].tout.normalized() if nodes[0].tout is not None else d_out
        elif d_out is None:
            d_in = d_out = nodes[-1].tin.normalized() if nodes[-1].tin is not None else d_in
        n0, n1 = Vector((-d_in.y, d_in.x)), Vector((-d_out.y, d_out.x))
        bis = n0 + n1
        bis = bis.normalized() if bis.length > 1e-9 else n0
        reach = t / 2 / max(bis.dot(n0), 0.1)           # mitred, as offset's corners
        left.append(tuple(pts[i] + bis * reach))
        right.append(tuple(pts[i] - bis * reach))
        node, prev = nodes[i], nodes[i - 1]
        if i in (0, m - 1):
            sharp.append(True)
        elif node.inner:
            sharp.append(False)
        else:
            tin = node.tin if node.tin is not None else pts[i] - pts[i - 1]
            tout = node.tout if node.tout is not None else pts[i + 1] - pts[i]
            limit = 1.0 if node.exact and prev.exact else 12.0
            sharp.append(tin.normalized().dot(tout.normalized()) < math.cos(math.radians(limit)))
    loop = Loop(*_clean(left + right[::-1], sharp + sharp[::-1]))
    if loop.area() < 0:
        loop = loop.reversed()
    region = _region([[loop]], lambda w: w != 0)
    pieces = Profile([Loop([region[0][i] for i in lp], [region[1][i] for i in lp]) for lp in region[2]])
    # a band that crosses itself covers some of the plane twice: its signed area is more than
    # the region's (the region's points come back in single precision: 1e-6 of it is noise)
    if len(region[2]) != 1 or abs(pieces.area() - loop.area()) > 1e-6 * loop.area():
        raise ValueError(f"stroke: the band {t:g} wide crosses itself — the path turns tighter than t / 2 = "
                         f"{t / 2:g}, or crosses itself: draw it apart, or thinner")
    return _from_region(region)


def wrap(*profiles):
    """Convex outline round profiles.

    The convex outline round `profiles` — profiles placed in their plane, as `at` moves
    them, and points (x, y); a list is worth its elements: a belt round its wheels, a link
    round its two bosses, a cam round its lobes. A point keeps its corner; where the
    outline leaves a curve it runs on tangent. A belt t thick round its wheels:
    `w = wrap(*wheels)`, then `offset(w, t) - w`."""
    marks = {}
    for x, y, corner in _wrapped(profiles):
        marks[(x, y)] = marks.get((x, y), False) or corner
    pts = sorted(marks)
    if len(pts) < 3:
        raise ValueError("wrap: give profiles or points that span an area: three points at least, not in a line")

    def chain(seq):
        out = []
        for q in seq:
            while len(out) > 1 and ((out[-1][0] - out[-2][0]) * (q[1] - out[-2][1])
                                    - (out[-1][1] - out[-2][1]) * (q[0] - out[-2][0])) <= 0:
                out.pop()
            out.append(q)
        return out[:-1]
    hull = chain(pts) + chain(pts[::-1])       # anticlockwise, points in line dropped
    if len(hull) < 3:
        raise ValueError("wrap: the profiles and points given lie in a line: they wrap no area")
    return _single(hull, [marks[q] for q in hull])


def _wrapped(items):
    """(x, y, corner) of every point of the profiles and points `items`, lists opened."""
    for item in items:
        if isinstance(item, (Profile, Placed)):
            for loop in _flat(item).loops:
                yield from ((x, y, s) for (x, y), s in zip(loop.pts, loop.sharp))
        elif isinstance(item, (list, tuple)) and item and isinstance(item[0], (int, float)):
            _flat_point(item, "wrap", "points to wrap are (x, y), in the plane of the profiles")
            yield float(item[0]), float(item[1]), True
        elif isinstance(item, (list, tuple)):
            yield from _wrapped(item)
        else:
            raise TypeError(f"wrap: wraps profiles and (x, y) points, not {type(item).__name__}")


def mirror(p, flip="x"):
    """Plus its image, `flip` negated.

    `p` and its mirror image, as one profile: draw half an outline and get the whole.
    `flip` is the coordinate that changes sign — "x" (x → -x, the default) or "y", as
    in `transform(mirror=)`. For a solid's image: `s3d.transform(s3d.copy(ob), mirror="x")`."""
    if isinstance(p, bpy.types.Object) or hasattr(p, "root"):
        raise TypeError("mirror: for a solid, s3d.transform(s3d.copy(ob), mirror=\"x\") — its image across the "
                        "plane x = 0 of its parent")
    if not isinstance(flip, str) or flip.lower() not in ("x", "y"):
        raise ValueError(f"mirror: flip is \"x\" or \"y\", the coordinate that changes sign, not {flip!r}")
    p = _flat(p)                       # a profile moved within its plane is mirrored where it is
    fx, fy = (-1, 1) if flip.lower() == "x" else (1, -1)
    flipped = [Loop([(fx * x, fy * y) for x, y in loop.pts], loop.sharp).reversed() for loop in p.loops]
    return _from_region(_region([p.loops, flipped], lambda a, b: a > 0 or b > 0))


def text(s, size, font=None):
    """Centred outline.

    The outline of the text `s`, letters `size` high (the font's em), centred on its
    ink. `font` is the path of a .ttf/.otf file; Blender's own font otherwise."""
    curve = bpy.data.curves.new("_text", "FONT")
    curve.body = s
    curve.size = size
    curve.resolution_u = 6
    if font:
        curve.font = bpy.data.fonts.load(str(font), check_existing=True)
    ob = bpy.data.objects.new("_text", curve)
    try:
        mesh = _core.evaluated_mesh(ob)
    finally:
        bpy.data.curves.remove(curve)
    co = [(v.co.x, v.co.y) for v in mesh.vertices]
    directed = set()
    for poly_ in mesh.polygons:
        vs = list(poly_.vertices)
        if poly_.normal.z < 0:
            vs = vs[::-1]
        directed |= {(vs[i], vs[(i + 1) % len(vs)]) for i in range(len(vs))}
    bpy.data.meshes.remove(mesh)
    outgoing = {}
    for a, b in sorted(directed):
        if (b, a) not in directed:
            outgoing.setdefault(a, []).append(b)
    if not outgoing:
        raise ValueError(f"text {s!r} has no outline")
    loops = []
    while outgoing:
        start = min(outgoing)
        loop, v = [], start
        while True:
            loop.append(v)
            nxt = outgoing[v].pop(0)
            if not outgoing[v]:
                del outgoing[v]
            v = nxt
            if v == start:
                break
        loops.append(loop)
    xs = [co[v][0] for loop in loops for v in loop]
    ys = [co[v][1] for loop in loops for v in loop]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    shape = []
    for loop in loops:
        pts = [(co[v][0] - cx, co[v][1] - cy) for v in loop]
        sharp = []
        for i in range(len(pts)):
            u = Vector(pts[i]) - Vector(pts[i - 1])
            w = Vector(pts[(i + 1) % len(pts)]) - Vector(pts[i])
            sharp.append(u.length == 0 or w.length == 0 or u.normalized().dot(w.normalized()) < math.cos(math.radians(30)))
        shape.append(Loop(*_clean(pts, sharp)))
    return _from_region(_region([shape], lambda w: w > 0))
