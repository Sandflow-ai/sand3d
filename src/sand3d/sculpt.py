"""Sculpting: a solid's surface moved by places on it, never by its vertices.

Every solid has a spine, its own axis: the line `body` runs along, the path of `sweep`
and `wire`, the centres of `loft`'s sections; for any other solid, the longest side of
its own box, through its centre. A place is `spot(ob, u, side)`: `u` from 0 at the
spine's start to 1 at its end, by length, and a side, a direction. The verbs here move
the surface round a frame (a spot, or any frame or point) and fade to nothing at `r`;
where the surface has too few vertices to bend, they add some first. The names of faces
and edges stay where they were.
"""
import math

import bmesh
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree

from . import _core
from .frames import Frame, _sides
from .profile import Path, Placed, Profile, _as_path

#: Passes of edge splitting a verb may make to give the surface vertices to move.
REFINE_PASSES = 8
#: Vertices a solid may reach by refining: past it, the verb says so instead of running on.
MAX_VERTS = 400_000
#: The shortest edge a refinement asks for, in millimetres.
MIN_STEP = 0.05
#: Vertices across a falloff's radius: the edges round a moved place are cut to `r / FINE`.
FINE = 6
#: Points a spine is resampled to, to measure along it.
SPINE_SAMPLES = 128
#: Within this many degrees of the spine, a side runs along it: to the tip.
ALONG = 10
#: How far each pass of `relax` takes a point toward the mean of the surface round it.
PULL = 0.8
#: The places `describe` reads along the spine.
CARD = (0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1)


# ---------------------------------------------------------------- the spine

def spine(ob):
    """`ob`'s spine: points of its own space from u = 0 to u = 1."""
    flat = ob.get(_core.SPINE)
    if flat:
        return [Vector(flat[i:i + 3]) for i in range(0, len(flat), 3)]
    co = [0.0] * (3 * len(ob.data.vertices))
    ob.data.vertices.foreach_get("co", co)
    if not co:
        raise ValueError(f"{_core.given_name(ob)!r} has no surface: it has no spine")
    lo = [min(co[k::3]) for k in range(3)]
    hi = [max(co[k::3]) for k in range(3)]
    size = [hi[k] - lo[k] for k in range(3)]
    tie = 1e-6 * max(size) + _core.mm(1e-9)
    axis = max((2, 1, 0), key=lambda k: size[k] + (3 - k) * tie / 4)   # a tie goes to Z, then Y
    centre = [(lo[k] + hi[k]) / 2 for k in range(3)]
    start, end = list(centre), list(centre)
    start[axis], end[axis] = lo[axis], hi[axis]
    return [Vector(start), Vector(end)]


def _lengths(pts):
    out = [0.0]
    for a, b in zip(pts, pts[1:]):
        out.append(out[-1] + (b - a).length)
    return out


def _at(pts, u):
    """The point and the unit tangent at `u` of the polyline `pts`, by length."""
    if len(pts) < 2 or _lengths(pts)[-1] <= 0:
        return Vector(pts[0]), Vector((0, 0, 1))
    lengths = _lengths(pts)
    s = min(max(u, 0.0), 1.0) * lengths[-1]
    for i in range(len(pts) - 1):
        if s <= lengths[i + 1] or i == len(pts) - 2:
            span = lengths[i + 1] - lengths[i]
            if span <= 0:
                continue
            t = min(max((s - lengths[i]) / span, 0.0), 1.0)
            return pts[i].lerp(pts[i + 1], t), (pts[i + 1] - pts[i]).normalized()
    return Vector(pts[-1]), (pts[-1] - pts[-2]).normalized()


def _resampled(pts, n=SPINE_SAMPLES):
    return [_at(pts, i / n)[0] for i in range(n + 1)]


def _u_of(name, u, verb):
    if isinstance(u, bool) or not isinstance(u, (int, float)) or not 0 <= u <= 1:
        raise ValueError(f"{verb}: {name} runs along the spine from 0 (its start) to 1 (its end), not {u!r}")
    return float(u)


# ---------------------------------------------------------------- frames and places

def _direction(which, verb, what="side"):
    """A direction in the space an object is in: "+Z", "-X+Z" (as `bbox` names sides), or (x, y, z)."""
    if isinstance(which, str):
        d = Vector((0, 0, 0))
        for axis, sign in _sides(which, f"{verb}: {what}"):
            d[axis] = sign
        return d.normalized()
    if isinstance(which, (tuple, list, Vector)) and len(which) == 3 and Vector(which).length > 0:
        return Vector(which).normalized()
    raise ValueError(f"{verb}: {what} is a direction, \"+Z\" or \"-X+Z\" as bbox names sides, or (x, y, z), "
                     f"not {which!r}")


def _own(ob):
    """From the space `ob` is in to its own: for points, and for directions."""
    m = ob.matrix_basis.inverted()
    return m, m.to_3x3()


def _tree(bm):
    """A BVH of `bm` in millimetres (as `snap` searches), and the factor to go there."""
    from mathutils.bvhtree import BVHTree
    size = _core.in_mm(1.0)
    copy = bm.copy()
    if size != 1.0:
        bmesh.ops.scale(copy, vec=(size,) * 3, verts=copy.verts)
    tree = BVHTree.FromBMesh(copy)
    copy.free()
    return tree, size


def spot(ob, u, side=None):
    """Frame on its spine at u (0 start, 1 end); with side ("+Z", "-X+Z"), on its surface that way.

    `u` runs along `ob`'s spine by length, 0 at its start, 1 at its end: the line `body`
    runs along (-Y to +Y), the path of `sweep` and `wire`, the centres of `loft`'s
    sections; for any other solid, the longest side of its own box, through its centre,
    from - to +. Without `side`, the frame is on the spine, its Z along it. With a side —
    a direction in the space `ob` is in, as `bbox` names them ("-Z", "+X+Z"), or (x, y, z) —
    it is where the surface is met going that way from the spine, square to it, the
    frame's Z that way: a place on the belly, the back, a flank. A side along the spine
    ("+Y" on a body at u = 1) meets its tip. Read on `ob`, as `ob.face` is: `at` puts a
    part there, and the sculpting verbs take it as their `on`."""
    from .edit import _solids
    _solids("spot", ob)
    u = _u_of("u", u, "spot")
    m = ob.matrix_basis
    p, t = _at(spine(ob), u)
    if side is None:
        frame = Frame(m @ p, m.to_3x3() @ t)._read_on(ob, m)
        frame._s3d_spine = (ob.as_pointer(), u)       # a band round the spine, to the verbs here
        return frame
    _, rot = _own(ob)
    d = (rot @ _direction(side, "spot")).normalized()
    if abs(d.dot(t)) < math.cos(math.radians(ALONG)):
        d = (d - t * d.dot(t)).normalized()
        if u in (0, 1):            # an end of the spine lies on a cap: look from just inside it
            p = p + t * (_lengths(spine(ob))[-1] * 1e-4 * (1 if u == 0 else -1))
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    tree, size = _tree(bm)
    bm.free()
    hit = tree.ray_cast(p * size, d)
    loc = hit[0] if hit[0] is not None else tree.find_nearest(p * size)[0]
    if loc is None:
        raise ValueError(f"spot: {_core.given_name(ob)!r} has no surface")
    return Frame(m @ (loc / size), m.to_3x3() @ d)._read_on(ob, m)


def _centres(ob, on, verb, required=True):
    """`on` — a frame, a point (x, y, z), or a list of them, in the space `ob` is in — as
    [(point, direction or None, u or None)] in `ob`'s own space: u for a spot on the spine."""
    if on is None:
        if required:
            raise ValueError(f"{verb}: on is where: a frame (s3d.spot(ob, u, side), ob.face, bbox), a point "
                             f"(x, y, z), or a list of them")
        return []
    items = list(on) if isinstance(on, (list, tuple)) and on and not isinstance(on[0], (int, float)) else [on]
    to_own, rot = _own(ob)
    out = []
    for item in items:
        if isinstance(item, Frame):
            mark = getattr(item, "_s3d_spine", None)
            u = mark[1] if mark and mark[0] == ob.as_pointer() else None
            out.append((to_own @ item.origin, (rot @ item.z).normalized(), u))
        elif isinstance(item, (tuple, list, Vector)) and len(item) == 3 and all(
                isinstance(c, (int, float)) and not isinstance(c, bool) for c in item):
            out.append((to_own @ Vector(item), None, None))
        else:
            raise TypeError(f"{verb}: on is a frame, a point (x, y, z) or a list of them, not {item!r}")
    return out


def _radius(r, verb, name="r"):
    if isinstance(r, bool) or not isinstance(r, (int, float)) or r <= 0:
        raise ValueError(f"{verb}: {name} is how far the change reaches, a length above 0, not {r!r}")
    return float(r)


def _number(x, verb, name):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise TypeError(f"{verb}: {name} is a number, not {x!r}")
    return float(x)


# ---------------------------------------------------------------- the surface

def _open(ob, verb):
    from .edit import _solids
    _solids(verb, ob)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    return bm


def _close(ob, bm):
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()
    return ob


def _seg_dist(c, a, b):
    ab = b - a
    k = ab.length_squared
    t = 0.0 if k <= 0 else min(max((c - a).dot(ab) / k, 0.0), 1.0)
    return (a + ab * t - c).length


def _near_edges(bm, near, radius):
    """The edges with an end within `radius` (and half the longest edge) of a point of `near`."""
    longest = max((e.calc_length() for e in bm.edges), default=0.0)
    tree = _kd([v.co for v in bm.verts])
    bm.verts.ensure_lookup_table()
    found = {i for c in near for _, i, _ in tree.find_range(c, radius + longest)}
    bm.edges.index_update()
    return sorted({e for i in found for e in bm.verts[i].link_edges}, key=lambda e: e.index)   # an order that never varies


def _refine(bm, reach, step, verb, near=None, radius=0.0):
    """Cut, until none is left, every edge longer than `step` that `reach(a, b)` says the
    change reaches; the faces round them are made triangles first, which split cleanly.
    A cut face keeps its names, as a cut edge does. `near`: points the change lies within
    `radius` of — only the edges round them are read, not the whole surface."""
    step = max(step, _core.mm(MIN_STEP))
    for i in range(REFINE_PASSES):
        edges = bm.edges if near is None else _near_edges(bm, near, radius)
        long = [e for e in edges if e.calc_length() > step and reach(e.verts[0].co, e.verts[1].co)]
        if not long:
            return
        if len(bm.verts) + 3 * len(long) > MAX_VERTS:
            raise ValueError(f"{verb}: refining the surface to {_core.in_mm(step):g} mm edges would pass "
                             f"{MAX_VERTS} vertices: give a larger r, or work on a smaller part")
        if i == 0:
            faces = sorted({f for e in long for f in e.link_faces if len(f.verts) > 3}, key=lambda f: f.index)
            if faces:
                bmesh.ops.triangulate(bm, faces=faces)
                bm.edges.index_update()
                edges = bm.edges if near is None else _near_edges(bm, near, radius)
                long = [e for e in edges if e.calc_length() > step and reach(e.verts[0].co, e.verts[1].co)]
        bmesh.ops.subdivide_edges(bm, edges=long, cuts=1, use_grid_fill=True)
        bm.verts.index_update()
        bm.edges.index_update()
        bm.faces.index_update()


def _ball(centres, r):
    return lambda a, b: any(_seg_dist(c, a, b) < r for c in centres)


class _Reach:
    """Where a change at `places` reaches, `r` round each: a ball round a point of the
    surface, and round a place on the spine (`spot(ob, u)`) the band of the surface whose
    nearest point of the spine is within `r` of it along the spine."""

    def __init__(self, ob, places, r):
        self.r, self.balls = r, [c for c, _, u in places if u is None]
        self.bands = []
        if len(self.balls) < len(places):
            axis = _resampled(spine(ob), 4 * SPINE_SAMPLES)
            self.along = _lengths(axis)
            self.axis = _kd(axis)
            self.bands = [self.along[-1] * u for _, _, u in places if u is not None]

    def s(self, co):
        return self.along[self.axis.find(co)[1]]

    def touches(self, a, b):
        if any(_seg_dist(c, a, b) < self.r for c in self.balls):
            return True
        if self.bands:
            ss = [self.s(a), self.s(b), self.s((a + b) / 2)]
            return any(min(ss) - self.r < c < max(ss) + self.r for c in self.bands)
        return False

    def weights(self, bm):
        """{vertex index: weight}, summed over the places, at most 1."""
        out = {}
        if self.balls:
            tree = _kd([v.co for v in bm.verts])
            for c in self.balls:
                for _, i, d in tree.find_range(c, self.r):
                    out[i] = out.get(i, 0.0) + _weight(d, self.r)
        if self.bands:
            for v in bm.verts:
                s = self.s(v.co)
                w = sum(_weight(abs(s - c), self.r) for c in self.bands)
                if w > 0:
                    out[v.index] = out.get(v.index, 0.0) + w
        return {i: min(1.0, w) for i, w in sorted(out.items()) if w > 0}


def _reached(ob, bm, places, r, verb):
    """The surface refined where the change reaches, and {vertex index: weight}."""
    reach = _Reach(ob, places, r)
    near = reach.balls if reach.balls and not reach.bands else None     # a band runs round the whole spine
    _refine(bm, reach.touches, r / FINE, verb, near=near, radius=r)
    bm.verts.ensure_lookup_table()
    return reach.weights(bm)


def _weight(d, r):
    """1 at the centre, 0 at r, flat at both: (1 - (d/r)²)²."""
    if d >= r:
        return 0.0
    t = d / r
    return (1 - t * t) ** 2


def _kd(points):
    tree = KDTree(len(points))
    for i, p in enumerate(points):
        tree.insert(p, i)
    tree.balance()
    return tree


# ---------------------------------------------------------------- the verbs

def grab(ob, move, r, on):
    """Pull the surface round on by move (x, y, z), fading to nothing at r.

    Every point of `ob`'s surface within `r` of `on` (a frame — `spot(ob, u, side)` —
    a point, or a list of them, in the space `ob` is in) moves by `move`, an (x, y, z)
    in that space: all of it at the centre, less and less away from it, nothing at `r`;
    on a spot on the spine (`spot(ob, u)`), the whole ring there, `r` along the spine
    each way. A snout drawn out, a cheek pushed up, a back arched, a silhouette
    corrected where it is wrong."""
    move = Vector([_number(c, "grab", "move") for c in move]) if isinstance(move, (tuple, list, Vector)) \
        and len(move) == 3 else None
    if move is None:
        raise ValueError("grab: move is how far it pulls, (x, y, z) in the space the solid is in")
    r = _radius(r, "grab")
    centres = _centres(ob, on, "grab")
    _, rot = _own(ob)
    shift = rot @ move
    bm = _open(ob, "grab")
    for i, w in _reached(ob, bm, centres, r, "grab").items():
        bm.verts[i].co += shift * w
    return _close(ob, bm)


def inflate(ob, by, r=None, on=None):
    """Swell the surface round on along its normals, by at the centre, nothing at r (by < 0 hollows); no on: all.

    The surface moves along its normals by `by`, out (or in, below 0): with `on` (a frame,
    a point, or a list of them), by all of `by` there and less away from it, nothing at
    `r` — a belly, cheeks, a muscle; on a spot on the spine (`spot(ob, u)`), all round
    it, `r` along the spine each way. Without `on`, the whole surface by `by`: a body
    made fuller or leaner."""
    by = _number(by, "inflate", "by")
    centres = _centres(ob, on, "inflate", required=False)
    bm = _open(ob, "inflate")
    if centres:
        moves = list(_reached(ob, bm, centres, _radius(r, "inflate"), "inflate").items())
        bm.normal_update()
    else:
        bm.normal_update()
        bm.verts.ensure_lookup_table()
        moves = [(v.index, 1.0) for v in bm.verts]
    normals = {i: Vector(bm.verts[i].normal) for i, _ in moves}
    for i, w in moves:
        bm.verts[i].co += normals[i] * by * w
    return _close(ob, bm)


def pinch(ob, by, r, on):
    """Draw the surface round on toward the spine, by at the centre, nothing at r (by < 0 swells it).

    The surface round `on` moves toward `ob`'s spine (its own axis, as `spot` reads it)
    by `by` at the centre, less away from it, nothing at `r`, never past the axis: a
    waist, a neck, a wrist, a joint. On a spot on the spine (`spot(ob, u)`) it is the
    whole ring there, `r` along the spine each way; below 0 it swells it."""
    by = _number(by, "pinch", "by")
    r = _radius(r, "pinch")
    centres = _centres(ob, on, "pinch")
    axis = _resampled(spine(ob), 4 * SPINE_SAMPLES)
    axis_tree = _kd(axis)
    bm = _open(ob, "pinch")
    for i, w in _reached(ob, bm, centres, r, "pinch").items():
        v = bm.verts[i]
        target, _, dist = axis_tree.find(v.co)
        if dist <= 0:
            continue
        step = by * w
        if step > 0:
            step = min(step, 0.95 * dist)
        v.co += (target - v.co).normalized() * step
    return _close(ob, bm)


def relax(ob, r=None, on=None, passes=3):
    """Even out bumps and seams round on, nothing at r; no on: all of it.

    Each point moves, along its normal, most of the way to the mean of the surface round
    it, `r / 4` across; `passes` times. Bumps and folds that narrow even out, the seam a
    `join` leaves turns into a fillet, the shape at large stays. With `on` (a frame, a point, a list of them), fully there, nothing at
    `r`: where a limb meets a body. Without `on`, everywhere, `r` a tenth of its size
    unless given."""
    if isinstance(passes, bool) or not isinstance(passes, int) or passes < 1:
        raise ValueError(f"relax: passes is a whole number above 0, not {passes!r}")
    centres = _centres(ob, on, "relax", required=False)
    bm = _open(ob, "relax")
    if centres:
        r = _radius(r, "relax")
        weights = _reached(ob, bm, centres, r, "relax")
    else:
        if r is None:
            lo = [min(v.co[k] for v in bm.verts) for k in range(3)]
            hi = [max(v.co[k] for v in bm.verts) for k in range(3)]
            r = Vector([hi[k] - lo[k] for k in range(3)]).length / 10
        r = _radius(r, "relax")
        _refine(bm, lambda a, b: True, r / FINE, "relax")
        bm.verts.ensure_lookup_table()
        weights = {v.index: 1.0 for v in bm.verts}
    h = r / 4
    for _ in range(passes):
        bm.normal_update()
        co = [Vector(v.co) for v in bm.verts]
        normal = [Vector(v.normal) for v in bm.verts]
        area = [sum(f.calc_area() / len(f.verts) for f in v.link_faces) for v in bm.verts]
        tree = _kd(co)
        moved = {}
        for i, w in weights.items():
            total, mean = 0.0, Vector()
            for q, j, d in tree.find_range(co[i], h):
                if normal[j].dot(normal[i]) <= 0:      # the other side of a thin part
                    continue
                k = area[j] * math.exp(-2 * (d / h) ** 2)
                total += k
                mean += q * k
            if total > 0:
                shift = mean / total - co[i]
                moved[i] = co[i] + normal[i] * shift.dot(normal[i]) * PULL * w
        for i, c in moved.items():
            bm.verts[i].co = c
    return _close(ob, bm)


def crease(ob, path, depth, r):
    """Press a fold depth deep along a path over the surface, r wide (depth < 0: a ridge).

    `path` runs over `ob`'s surface: frames (`spot`s) or points, in the space `ob` is in,
    joined by a smooth curve, or a path (`spline`), each point taken to the surface
    nearest it. The surface is pressed in along it, `depth` deep on the line and nothing
    at `r` from it, sharp at the line: a fold, a wrinkle, the line between two muscles,
    a lip. Below 0, a ridge."""
    depth = _number(depth, "crease", "depth")
    r = _radius(r, "crease")
    if isinstance(path, (Path, Profile, Placed)):
        to_own, _ = _own(ob)
        line = [to_own @ Vector(q) for q in _as_path(path).points]
    else:
        if not isinstance(path, (list, tuple)) or len(path) < 2:
            raise ValueError("crease: path is two places or more on the surface (spots or points), or a path")
        line = [c for c, _, _ in _centres(ob, list(path), "crease")]
        if len(line) > 2:
            from .profile import spline
            line = [Vector(q) for q in spline([tuple(c) for c in line]).points]
    bm = _open(ob, "crease")
    tree, size = _tree(bm)
    line = [tree.find_nearest(c * size)[0] / size for c in line]
    dense = _resampled(line, max(8, int(_lengths(line)[-1] / (r / 4)) + 1))
    probes = dense[::2] + [dense[-1]]
    _refine(bm, lambda a, b: any(_seg_dist(c, a, b) < r for c in probes), r / 4, "crease", near=probes, radius=r)
    bm.normal_update()
    bm.verts.ensure_lookup_table()
    fine = _resampled(line, max(16, int(_lengths(line)[-1] / (r / 16)) + 1))
    line_tree = _kd(fine)
    vtree = _kd([v.co for v in bm.verts])
    seen = {i for c in fine for _, i, _ in vtree.find_range(c, r)}
    normals = {i: Vector(bm.verts[i].normal) for i in seen}
    for i in sorted(seen):
        v = bm.verts[i]
        _, _, d = line_tree.find(v.co)
        if d < r:
            t = d / r
            v.co -= normals[i] * depth * (1 - t) ** 2
    return _close(ob, bm)


def _signed(loops, x, y):
    """Distance from (x, y) to the outline of `loops`, above 0 inside."""
    inside, best = False, math.inf
    for pts in loops:
        n = len(pts)
        for k in range(n):
            (x0, y0), (x1, y1) = pts[k], pts[(k + 1) % n]
            if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
                inside = not inside
            dx, dy = x1 - x0, y1 - y0
            k2 = dx * dx + dy * dy
            t = 0.0 if k2 <= 0 else min(max(((x - x0) * dx + (y - y0) * dy) / k2, 0.0), 1.0)
            best = min(best, math.hypot(x0 + t * dx - x, y0 + t * dy - y))
    return best if inside else -best


def stamp(ob, profile, depth, on, soft=None):
    """Raise a profile's shape depth high on the surface at each frame of on (depth < 0 sinks it).

    `profile` (a `circle`, a `rect`, a `poly`…) is laid on each frame of `on` — spots,
    `snap` frames, a list of them — square to the frame's Z, and the surface under it
    raised `depth` along its normals, softly at its outline over `soft` (a quarter of its
    size by default): one call for a row of scales, warts, veins' knots, nostrils, the
    pads of a paw. Only the surface facing the frame's way is stamped."""
    depth = _number(depth, "stamp", "depth")
    if isinstance(profile, Placed):
        raise TypeError("stamp: the profile is laid on each frame of on: give it unplaced, s3d.circle(8)")
    if not isinstance(profile, Profile):
        raise TypeError(f"stamp: profile is a profile, s3d.circle(8) or s3d.rect(6, 3), not {type(profile).__name__}")
    loops = [[(float(x), float(y)) for x, y in loop.pts] for loop in profile.loops]
    xs = [x for loop in loops for x, _ in loop]
    ys = [y for loop in loops for _, y in loop]
    extent = max(max(xs) - min(xs), max(ys) - min(ys))
    soft = extent / 4 if soft is None else _radius(soft, "stamp", "soft")
    reach = math.hypot(max(abs(c) for c in xs), max(abs(c) for c in ys)) + soft
    frames = on if isinstance(on, (list, tuple)) else [on]
    if not frames or not all(isinstance(f, Frame) for f in frames):
        raise TypeError("stamp: on is a frame or a list of frames: spots (s3d.spot(ob, u, side)) or s3d.snap(...)")
    to_own, rot = _own(ob)
    placed = []
    for f in frames:
        o = to_own @ f.origin
        z = (rot @ f.z).normalized()
        x = rot @ f.x
        x = (x - z * x.dot(z)).normalized()
        placed.append((o, x, z.cross(x), z))
    bm = _open(ob, "stamp")
    _refine(bm, _ball([o for o, *_ in placed], reach), min(soft / 2, extent / FINE), "stamp")
    bm.normal_update()
    bm.verts.ensure_lookup_table()
    lift = {}
    vtree = _kd([v.co for v in bm.verts])
    for o, x, y, z in placed:
        for co, i, _ in vtree.find_range(o, reach):
            v = bm.verts[i]
            if v.normal.dot(z) < 0.3:
                continue
            rel = co - o
            if abs(rel.dot(z)) > reach:
                continue
            sd = _signed(loops, rel.dot(x), rel.dot(y))
            t = min(max(0.5 + sd / soft, 0.0), 1.0)
            w = t * t * (3 - 2 * t)
            if w > 0:
                lift[i] = max(lift.get(i, 0.0), w)
    normals = {i: Vector(bm.verts[i].normal) for i in lift}
    for i in sorted(lift):
        bm.verts[i].co += normals[i] * depth * lift[i]
    return _close(ob, bm)


# ---------------------------------------------------------------- clay

#: `clay`'s detail when none is given: this share of the diagonal of the mass's box.
CLAY_DETAIL = 1 / 150
#: Faces `clay` may make: past them, it asks for a larger `detail`.
CLAY_FACES = 600_000


def clay(ob, *others, detail=None):
    """Remake as one even closed surface, others fused in, edges about detail long.

    `ob`, and `others` fused into it, remade as clay: one closed surface of even faces
    about `detail` across (the diagonal of their box / 150 unless given), as a
    sculptor's remesh makes it. Where the parts overlapped they are one mass, with no
    seam left inside, and every sculpting verb finds surface to move everywhere, not
    only where a solid's sections fell. `ob` keeps its name, placement, material and
    spine; a list is worth its solids, and the others are used up. Faces and edges
    lose their names."""
    import bpy

    from . import _guard
    from .edit import MERGED, _flat, _replace_mesh, _solids, _sort_mesh, delete
    from .joints import refuse_using_up
    others = _flat(others)
    _solids("clay", ob, *others)
    refuse_using_up(others, "clay")
    if any(o == ob for o in others) or len({o.as_pointer() for o in others}) < len(others):
        raise ValueError("clay: a solid is given twice")
    _guard.using_up(others, ob)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    own = _core.world(ob).inverted()
    for other in others:          # each in `ob`'s own space, appended: the remesh fuses them
        part = bmesh.new()
        part.from_mesh(other.data)
        bmesh.ops.transform(part, matrix=own @ _core.world(other), verts=part.verts)
        held = bpy.data.meshes.new("s3d~clay-part")
        part.to_mesh(held)
        part.free()
        bm.from_mesh(held)
        bpy.data.meshes.remove(held)
    if not bm.verts:
        bm.free()
        raise ValueError(f"clay: {_core.given_name(ob)!r} has no surface")
    lo = [min(v.co[k] for v in bm.verts) for k in range(3)]
    hi = [max(v.co[k] for v in bm.verts) for k in range(3)]
    if detail is None:
        detail = Vector([hi[k] - lo[k] for k in range(3)]).length * CLAY_DETAIL
    detail = _radius(detail, "clay", "detail")
    area = sum(f.calc_area() for f in bm.faces)
    if area / detail ** 2 > CLAY_FACES:
        bm.free()
        least = math.sqrt(area / CLAY_FACES)
        raise ValueError(f"clay: at {_core.in_mm(detail):g} mm the clay would hold some {int(area / detail ** 2)} "
                         f"faces, past {CLAY_FACES}: give a detail of {_core.in_mm(least):.2g} mm or more")
    # in millimetres, whatever the program's unit: the voxels then fall the same way, and a
    # program in another unit builds the same clay to scale
    size = _core.in_mm(1.0)
    bmesh.ops.scale(bm, vec=(size,) * 3, verts=bm.verts)
    mesh = bpy.data.meshes.new("s3d~clay")
    bm.to_mesh(mesh)
    bm.free()
    tmp = bpy.data.objects.new("s3d~clay", mesh)
    remesh = tmp.modifiers.new("clay", "REMESH")
    remesh.mode = "VOXEL"
    remesh.voxel_size = detail * size
    remesh.adaptivity = 0.0
    made = _core.evaluated_mesh(tmp)
    out = bmesh.new()
    out.from_mesh(made)
    bpy.data.meshes.remove(made)
    bpy.data.meshes.remove(mesh)
    bmesh.ops.scale(out, vec=(1 / size,) * 3, verts=out.verts)
    if not out.faces:
        out.free()
        raise ValueError(f"clay: at {_core.in_mm(detail):g} mm nothing of {_core.given_name(ob)!r} is left: "
                         f"give a smaller detail")
    for f in out.faces:
        f.smooth = True
        f.material_index = 0
    bmesh.ops.recalc_face_normals(out, faces=out.faces)
    _sort_mesh(out)
    materials = list(ob.data.materials)
    _replace_mesh(ob, out)
    for m in materials:
        ob.data.materials.append(m)
    if MERGED in ob:              # its overlapping shells are one now
        del ob[MERGED]
    for other in others:
        delete(other)
    return ob


# ---------------------------------------------------------------- reading it back

def _side_axes(t):
    """The two axes of own space most square to `t`, X before Y before Z."""
    order = sorted(range(3), key=lambda k: (round(abs(t[k]), 3), k))
    return sorted(order[:2])


def _fmt(x):
    x = _core.in_mm(x)
    return f"{x:.0f}" if abs(x) >= 10 else f"{x:.1f}".rstrip("0").rstrip(".") or "0"


def describe(ob):
    """Its size, spine, and how far the surface is from the spine along it, as text: to compare with a target.

    A card of `ob` in millimetres: its own box, where its spine runs, and at u = 0,
    0.1 … 1 along it how far the surface is from the spine each way across — the two
    directions of its own space most square to the spine — and where the spine is.
    What `spot` reads, written down: read it against a target's measures to see where a
    `grab`, an `inflate` or a `pinch` is due, and at which u."""
    from .edit import _solids
    _solids("describe", ob)
    pts = spine(ob)
    dense = _resampled(pts)
    co = [0.0] * (3 * len(ob.data.vertices))
    ob.data.vertices.foreach_get("co", co)
    lo = [min(co[k::3]) for k in range(3)]
    hi = [max(co[k::3]) for k in range(3)]
    name = _core.given_name(ob)
    names = "xyz"
    start, end = pts[0], pts[-1]
    chord = end - start
    main = max(range(3), key=lambda k: abs(chord[k])) if chord.length > 0 else 2
    run = f"{'+' if chord[main] >= 0 else '-'}{names[main].upper()}"
    lines = [f"{name}: {' x '.join(_fmt(hi[k] - lo[k]) for k in range(3))} mm (x y z); spine {run}, "
             f"{_fmt(_lengths(dense)[-1])} long, u 0 at ({', '.join(_fmt(c) for c in start)}) "
             f"to u 1 at ({', '.join(_fmt(c) for c in end)})"]
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    tree, size = _tree(bm)
    bm.free()
    rows = {}
    for u in CARD:
        p, t = _at(dense, u)
        for k in _side_axes(t):
            for sign in (1, -1):
                d = Vector((0, 0, 0))
                d[k] = sign
                d = (d - t * d.dot(t)).normalized()
                hit = tree.ray_cast(p * size, d)
                gap = (hit[3] / size) if hit[0] is not None else 0.0
                rows.setdefault(f"{'+' if sign > 0 else '-'}{names[k]}", []).append(_fmt(gap))
        for k in range(3):
            rows.setdefault(f"spine {names[k]}", []).append(_fmt(p[k]))
    gaps = [k for k in rows if not k.startswith("spine")]
    moving = [k for k in rows if k.startswith("spine") and len(set(rows[k])) > 1]
    width = max(len(k) for k in gaps + moving) + 1
    cell = max(4, max(len(v) for k in gaps + moving for v in rows[k]) + 1)
    lines.append("u".ljust(width) + "".join(f"{u:g}".rjust(cell) for u in CARD))
    lines.append("how far the surface is from the spine, each way across:")
    lines += [k.ljust(width) + "".join(v.rjust(cell) for v in rows[k]) for k in gaps]
    if moving:
        lines.append("where the spine is:")
        lines += [k.ljust(width) + "".join(v.rjust(cell) for v in rows[k]) for k in moving]
    return "\n".join(lines)
