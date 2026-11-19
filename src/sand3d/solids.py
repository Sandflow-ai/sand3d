"""Solids: closed, named meshes, each in its own frame, their faces and edges named.

Generators tag what they create. Faces: `top` / `bottom` caps and `side` walls
of an extrude; `start` / `end` caps of a sweep, a loft or a partial revolve;
revolved horizontal rings are `top` or `bottom` by the way they face. Edges carry
the names of the caps they bound, or `side` (extrude), `rim` (revolve), `seam`
(sweep, loft) where two walls meet at a corner of the profile. Every tag also
exists qualified by the solid's name: `plate.top`.
"""
import bisect
import math
import re

import bmesh
import bpy

from mathutils import Matrix, Vector, geometry

from . import _core
from .profile import EPS, Loop, Path, Placed, Profile, _as_path, arc, circle, poly, rect, superellipse


# ---------------------------------------------------------------- shared pieces

def _placed(profile):
    """(Profile, placement matrix) from a profile, a placed profile or a list of points."""
    if isinstance(profile, Placed):
        return profile.profile, profile.matrix
    if isinstance(profile, Profile):
        return profile, Matrix.Identity(4)
    return poly(profile), Matrix.Identity(4)


def _drawing(profile, refusal):
    """A profile as drawn in its plane: a placement within the plane (x, y, rz, a mirror)
    is part of the drawing. One that leaves the plane — a point off it by more than
    1e-6 mm, or the normal turned — raises `refusal`: a drawing goes on a face or a frame
    through `on=`. A list of points is an outline."""
    if not isinstance(profile, Placed):
        return profile if isinstance(profile, Profile) else poly(profile)
    m = profile.matrix
    off = any(abs((m @ Vector((x, y, 0))).z) > _core.mm(1e-6) for loop in profile.profile.loops for x, y in loop.pts)
    if off or m[2][2] < 1 - 1e-6:
        raise ValueError(refusal)
    from .profile import _flat
    return _flat(profile)


EXTRUDE_ON = ("extrude: the profile is placed out of its plane (moved in z, or turned off it): draw it in its "
              "plane — x, y and rz only — and give the face or frame with on=: "
              "s3d.extrude(name, profile, h, on=plate.face(\"top\"))")




def _in_plane(profile):
    """A placed profile moved within its own plane, as a plain profile (for `revolve`)."""
    profile, m = _placed(profile)
    if m == Matrix.Identity(4):
        return profile
    pts, sharp, loops, _ = profile.mesh()
    moved = [m @ Vector((x, y, 0)) for x, y in pts]
    if any(abs(q.z) > _core.mm(1e-9) for q in moved):
        raise ValueError("revolve: a section must stay in its own plane (move it with x, y, rz only)")
    return Profile([Loop([moved[i].xy for i in loop], [sharp[i] for i in loop]) for loop in loops])


def _frame_matrix(on):
    if on is None:
        return Matrix.Identity(4)
    if isinstance(on, (list, tuple)) and on and all(hasattr(f, "matrix") for f in on):
        raise TypeError("extrude: on is one frame; for one solid per frame, place copies: "
                        "s3d.at(s3d.extrude(...), on=[frames])")
    return Matrix(on.matrix) if hasattr(on, "matrix") else Matrix(on)


def _runs(sharp, loop):
    """Surface index of the wall leaving each point of a loop: walls between two
    corners are one smooth surface."""
    out, run = [], 0
    first = next((k for k, i in enumerate(loop) if sharp[i]), None)
    if first is None:
        return [0] * len(loop)
    out = [0] * len(loop)
    for step in range(len(loop)):
        k = (first + step) % len(loop)
        if step and sharp[loop[k]]:
            run += 1
        out[k] = run
    return out


def _miter(pts, loop, i):
    """Unit outward miter direction at point `loop[i]`, and its stretch 1/cos."""
    a, b, c = (Vector(pts[loop[j % len(loop)]]) for j in (i - 1, i, i + 1))
    d0, d1 = (b - a).normalized(), (c - b).normalized()
    n0, n1 = Vector((d0.y, -d0.x)), Vector((d1.y, -d1.x))
    bis = n0 + n1
    bis = bis.normalized() if bis.length > 1e-9 else n0
    return bis, 1 / max(bis.dot(n0), 0.1)


def _object(builder, matrix, kind, rim=False):
    ob = builder.finish(kind, rim)
    ob.matrix_basis = matrix
    return ob


# ---------------------------------------------------------------- extrude

def extrude(name, profile, h=None, taper=0, twist=0, both=False, h2=None, on=None, until=None):
    """Prism up Z (taper > 0 narrows it upward), or `until` a plane or solid; on a face, by `on`.

    `profile`, drawn in its plane (moved within it only), pushed `h` along its normal
    (+Z): a prism. `taper` draws its walls in — a positive taper narrows the prism from
    its lowest end up, a negative one widens it —
    by that many degrees, `twist` turns it that many degrees on the way; `both`
    centres it on its plane (`h` is the total), `h2` adds a second depth below.
    `on` is the frame it is drawn on: a face (`ob.face("top")`), or any Frame.
    `until`, instead of `h`: up to a frame's plane, or up to the surface of a solid."""
    if until is not None:
        if taper or twist or both:
            raise ValueError("extrude: `until` goes with neither taper, twist nor both")
        return _extrude_until(name, profile, until, h2, on)
    if h is None:
        raise ValueError("extrude: give `h`, or `until`")
    profile = _drawing(profile, EXTRUDE_ON)        # a twist turns about the sketch's origin, as in CAD
    if twist:
        profile = _densified(profile, math.radians(3))
    pts, sharp, loops, tris = profile.mesh()
    lo, hi = (-h / 2, h / 2) if both else (-(h2 or 0), h)
    if hi < lo:
        lo, hi = hi, lo
    layers = max(1, math.ceil(abs(twist) / 3))
    b = _core.Builder(name)
    miters = {i: _miter(pts, loop, k) for loop in loops for k, i in enumerate(loop)}
    rings = []
    for k in range(layers + 1):
        z = lo + (hi - lo) * k / layers
        inset = (z - lo) * math.tan(math.radians(taper))
        turn = math.radians(twist * k / layers)
        c, s = math.cos(turn), math.sin(turn)
        ring = []
        for i, (x, y) in enumerate(pts):
            if inset and i in miters:
                d, stretch = miters[i]
                x, y = x - d.x * inset * stretch, y - d.y * inset * stretch
            ring.append(b.vert((x * c - y * s, x * s + y * c, z)))
        rings.append(ring)
    caps = []
    caps += [b.face([rings[0][i] for i in reversed(t)], -1, ("bottom",)) for t in tris]
    caps += [b.face([rings[-1][i] for i in t], -2, ("top",)) for t in tris]
    surface = 0
    for loop in loops:
        runs = _runs(sharp, loop)
        n = len(loop)
        for k in range(layers):
            lower, upper = rings[k], rings[k + 1]
            for j in range(n):
                i0, i1 = loop[j], loop[(j + 1) % n]
                if twist:  # a twisted wall is not flat: two triangles, one fixed diagonal
                    b.face([lower[i0], lower[i1], upper[i1]], surface + runs[j], ("side",))
                    b.face([lower[i0], upper[i1], upper[i0]], surface + runs[j], ("side",))
                else:
                    b.face([lower[i0], lower[i1], upper[i1], upper[i0]], surface + runs[j], ("side",))
        surface += max(runs) + 1
    b.dissolve(caps)
    return _object(b, _frame_matrix(on) @ Matrix.Identity(4), "side")   # (as it always multiplied: the same bits)


def _extrude_until(name, profile, until, h2, on):
    """A prism whose top is where each point of the profile, pushed along its normal,
    first meets `until`: a plane (exactly), or the surface of solids (sampled: the
    outline is cut finer and points are added inside, so the top follows a curve)."""
    profile = _drawing(profile, EXTRUDE_ON)
    frame = _frame_matrix(on) @ Matrix.Identity(4)
    to_local = frame.inverted()
    if hasattr(until, "matrix") and not hasattr(until, "data"):
        q = to_local @ until.origin
        n = (to_local.to_3x3() @ until.normal).normalized()
        if abs(n.z) < 1e-9:
            raise ValueError("extrude: the `until` plane runs along the extrusion")
        pts, sharp, loops, tris = profile.mesh()
        tops = [((q - Vector((x, y, 0))).dot(n)) / n.z for x, y in pts]
    else:
        mm = _core.in_mm(1.0)   # Blender's BVH pads its boxes in its own units: cast in millimetres
        trees = [_core.mm_tree(ob, to_local @ _core.world(ob))
                 for ob in (until if isinstance(until, (list, tuple)) else [until])]
        lo_, hi_ = profile.bounds()
        size = max(hi_[0] - lo_[0], hi_[1] - lo_[1])
        fine = _densified(profile, size / 24, absolute=True)
        pts, sharp, loops, tris = _with_inside(fine, size / 24)

        def first_hit(x, y, sign):
            """Distance to the first surface met beyond the sketch plane, or None."""
            best = None
            for t in trees:
                origin = Vector((x * mm, y * mm, 0))
                while True:
                    loc, _, _, _ = t.ray_cast(origin, Vector((0, 0, sign)))
                    if loc is None:
                        break
                    travelled = abs(loc.z)
                    if travelled > 1e-6:
                        best = travelled if best is None else min(best, travelled)
                        break
                    origin = loc + Vector((0, 0, sign * 1e-6))
            return best if best is None else best / mm
        ups, sign = [first_hit(x, y, 1) for x, y in pts], 1
        if all(u is None for u in ups):
            ups, sign = [first_hit(x, y, -1) for x, y in pts], -1
        if all(u is None for u in ups):
            raise ValueError(f"extrude: {name!r} never meets `until` along its normal")
        reach = max(u for u in ups if u is not None)
        tops = [sign * (u if u is not None else reach) for u in ups]
    down = all(t <= _core.mm(1e-9) for t in tops)
    if not down and not all(t >= -_core.mm(1e-9) for t in tops):
        raise ValueError("extrude: the `until` surface crosses the sketch plane")
    floor = [(h2 or 0) if down else -(h2 or 0)] * len(pts)
    b = _core.Builder(name)
    low = [b.vert((x, y, z)) for (x, y), z in zip(pts, floor)]
    high = [b.vert((x, y, z)) for (x, y), z in zip(pts, tops)]
    bottom, top = (high, low) if down else (low, high)
    caps = [b.face([bottom[i] for i in reversed(t)], -1, ("bottom",)) for t in tris]
    for t in tris:
        b.face([top[i] for i in t], -2, ("top",))
    surface = 0
    for loop in loops:
        runs = _runs(sharp, loop)
        n_ = len(loop)
        for j in range(n_):
            i0, i1 = loop[j], loop[(j + 1) % n_]
            b.face([bottom[i0], bottom[i1], top[i1]], surface + runs[j], ("side",))
            b.face([bottom[i0], top[i1], top[i0]], surface + runs[j], ("side",))
        surface += max(runs) + 1
    b.dissolve(caps)
    ob = _object(b, frame, "side")
    _merge_flat(ob)
    return ob


def _merge_flat(ob):
    """Merge coplanar neighbours a sampled top or a split wall left as triangles."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.normal_update()
    tags = [lay for lay in bm.faces.layers.bool.values()]
    flat = [e for e in bm.edges if len(e.link_faces) == 2 and e.smooth
            and e.link_faces[0].normal.dot(e.link_faces[1].normal) > 1 - 1e-9
            and all(e.link_faces[0][lay] == e.link_faces[1][lay] for lay in tags)]
    if flat:
        bmesh.ops.dissolve_edges(bm, edges=flat, use_verts=False, use_face_split=False)
    bm.to_mesh(ob.data)
    bm.free()


def _with_inside(profile, spacing):
    """The region triangulated with extra points on a grid inside it."""
    from .profile import _region, _winding
    pts, sharp, loops, _ = profile.mesh()
    (x0, y0), (x1, y1) = profile.bounds()
    inside = []
    nx, ny = int((x1 - x0) / spacing), int((y1 - y0) / spacing)
    outline = [[pts[i] for i in loop] for loop in loops]
    for i in range(1, nx):
        for j in range(1, ny):
            x, y = x0 + i * spacing, y0 + j * spacing
            if sum(_winding(x, y, o) for o in outline) > 0 and min(
                    math.dist((x, y), p) for p in pts) > spacing / 2:
                inside.append((x, y))
    shape = [Loop([pts[i] for i in loop], [sharp[i] for i in loop]) for loop in loops]
    return _region([shape], lambda w: w > 0, extra=inside)


def _densified(profile, step, absolute=False):
    """`profile` with its straight sides cut so that no piece is longer than the arc
    its far end sweeps turning `step` radians: a twisted wall bends along them too."""
    pts, sharp, loops, _ = profile.mesh()
    reach = max(math.hypot(x, y) for x, y in pts)
    piece = step if absolute else max(reach * step, _core.mm(1e-3))
    out = []
    for loop in loops:
        q, f = [], []
        for j, i in enumerate(loop):
            a, b = pts[i], pts[loop[(j + 1) % len(loop)]]
            k = max(1, math.ceil(math.dist(a, b) / piece))
            for t in range(k):
                q.append((a[0] + (b[0] - a[0]) * t / k, a[1] + (b[1] - a[1]) * t / k))
                f.append(sharp[i] if t == 0 else False)
        out.append(Loop(q, f))
    return Profile(out)


# ---------------------------------------------------------------- revolve

def revolve(name, profile, angle=360):
    """X radius, Y height, turned about Z.

    `profile`, drawn with X as the radius and Y as the height, turned about Y,
    which becomes the solid's Z. A list of (r, z) points is a closed outline."""
    profile, placement = _in_plane(profile), Matrix.Identity(4)
    pts, sharp, loops, tris = profile.mesh()
    if min(x for x, _ in pts) < -_core.mm(1e-9):
        raise ValueError("revolve: the profile crosses the axis (X < 0)")
    full = abs(abs(angle) - 360) < 1e-9
    rmax = max(x for x, _ in pts)
    n = _core.segments(rmax, angle)
    steps = n if full else n + 1
    b = _core.Builder(name)
    on_axis = [abs(x) < _core.mm(1e-9) for x, _ in pts]
    pole = {}
    ring = []
    for i, (x, y) in enumerate(pts):
        if on_axis[i]:
            pole[i] = b.vert((0, 0, y))
            ring.append([pole[i]] * steps)
        else:
            ring.append([b.vert((x * math.cos(math.radians(angle * k / n)),
                                 x * math.sin(math.radians(angle * k / n)), y)) for k in range(steps)])
    low, high = min(y for _, y in pts), max(y for _, y in pts)
    b.lengthwise(ring, [(y-low)/(high-low) if high != low else 0 for _, y in pts],
                 [Vector((0,0,y)) for _,y in pts], [y-low for _,y in pts])
    surface = 0
    for loop in loops:
        m = len(loop)
        runs = _runs(sharp, loop)
        for j in range(m):
            i0, i1 = loop[j], loop[(j + 1) % m]
            if on_axis[i0] and on_axis[i1]:
                continue
            (x0, y0), (x1, y1) = pts[i0], pts[i1]
            # the region lies left of travel: a run going +X has it above, so the face looks down
            tags = ("side",)
            if abs(y1 - y0) < 1e-9 * max(_core.mm(1.0), abs(x1 - x0)):
                tags = ("bottom",) if x1 > x0 else ("top",)
            for k in range(n):
                k1 = (k + 1) % steps
                b.face([ring[i0][k], ring[i1][k], ring[i1][k1], ring[i0][k1]][::-1], surface + runs[j], tags)
        surface += max(runs) + 1
    caps = []
    if not full:
        caps += [b.face([ring[i][0] for i in t], -1, ("start",)) for t in tris]
        caps += [b.face([ring[i][n] for i in reversed(t)], -2, ("end",)) for t in tris]
        b.dissolve(caps)
    return _object(b, placement, "rim", rim=True)


# ---------------------------------------------------------------- sweep

def _frames_along(path, frenet):
    """Origin, tangent and the two section axes at each point of a path: rotation
    minimising (double reflection), or Frenet where the path curves."""
    p = [Vector(q) for q in path.points]
    m = len(p)
    closed = path.closed
    seg = [(p[(i + 1) % m] - p[i]) for i in range(m if closed else m - 1)]
    tangents, bends = [], []
    fitted = getattr(path, "_tangents", None)
    for i in range(m):
        if closed:
            d_in, d_out = seg[i - 1], seg[i]
        else:
            d_in = seg[i - 1] if i > 0 else seg[0]
            d_out = seg[i] if i < m - 1 else seg[-1]
        t = d_in.normalized() + d_out.normalized()
        t = t.normalized() if t.length > 1e-9 else d_out.normalized()
        if fitted is not None:
            t = Vector(fitted[i]).normalized()
        tangents.append(t)
        bends.append((t, t) if fitted is not None else (d_in.normalized(), d_out.normalized()))
    r0 = Vector((0, 0, 1)).rotation_difference(tangents[0]) @ Vector((1, 0, 0))
    rs = [r0]
    for i in range(1, m):
        v1 = p[i] - p[i - 1]
        c1 = v1.dot(v1)
        r, t = rs[-1], tangents[i - 1]
        if c1 > _core.mm2(1e-18):
            r = r - (2 / c1) * v1.dot(r) * v1
            t = t - (2 / c1) * v1.dot(t) * v1
        v2 = tangents[i] - t
        c2 = v2.dot(v2)
        if c2 > 1e-18:
            r = r - (2 / c2) * v2.dot(r) * v2
        r = (r - tangents[i] * r.dot(tangents[i])).normalized()
        rs.append(r)
    if frenet:
        for i in range(m):
            a, c = p[i - 1] if (closed or i) else p[i], p[(i + 1) % m] if (closed or i < m - 1) else p[i]
            k = a + c - 2 * p[i]
            k = k - tangents[i] * k.dot(tangents[i])
            if k.length > _core.mm(1e-9):
                rs[i] = k.normalized()
        if not closed and m > 2:
            # an open end has no curvature (its tangent is its segment): what is left
            # of k there is float noise, so the end rings take their neighbour's axis
            for i, j in ((0, 1), (m - 1, m - 2)):
                r = rs[j] - tangents[i] * rs[j].dot(tangents[i])
                if r.length > 1e-9:
                    rs[i] = r.normalized()
    elif closed and m > 2:
        # carry the frame once more round to the start and spread the mismatch
        v1 = p[0] - p[-1]
        c1 = v1.dot(v1)
        r, t = rs[-1], tangents[-1]
        if c1 > _core.mm2(1e-18):
            r = r - (2 / c1) * v1.dot(r) * v1
            t = t - (2 / c1) * v1.dot(t) * v1
        v2 = tangents[0] - t
        if v2.dot(v2) > 1e-18:
            r = r - (2 / v2.dot(v2)) * v2.dot(r) * v2
        r = (r - tangents[0] * r.dot(tangents[0])).normalized()
        gap = math.atan2(tangents[0].dot(r0.cross(r)), r0.dot(r))
        for i in range(m):
            rs[i] = Matrix.Rotation(-gap * i / m, 3, tangents[i]) @ rs[i]
    return p, tangents, rs, bends


def _ring_options(tip, rings):
    tips = (tip, tip) if isinstance(tip, str) else tip
    if not isinstance(tips, (tuple, list)) or len(tips) != 2 or any(t not in ('round', 'sharp', 'flat') for t in tips):
        raise ValueError("tip: use 'round', 'sharp', 'flat', or a (start, end) pair")
    if isinstance(rings, bool) or not isinstance(rings, int) or rings < 0:
        raise ValueError("rings: use a nonnegative integer")
    return tuple(tips)


def _tip_scale(law, u, tips):
    for end, neighbour, tip in ((0, 1, tips[0]), (-1, -2, tips[1])):
        if tip == 'sharp' and all(v == 0 for v in law.values[end]):
            if (u <= law.u[neighbour] if end == 0 else u >= law.u[neighbour]):
                t = (u - law.u[end]) / (law.u[neighbour] - law.u[end])
                values = tuple(v * t for v in law.values[neighbour])
                return values if law.pair else values[0]
    return _soft_scale(law, u)


def _linear_scale(end, u):
    """A numeric end size, scalar or (sx, sy), linearly from one."""
    return tuple(1 + (v - 1) * u for v in end) if isinstance(end, tuple) else 1 + (end - 1) * u


def _law_path(path, laws, scale=1, twist=0, radius=1, smooth=False, tips=("round", "round"), rings=0):
    """Refine the centre line and section laws to the common chord tolerance.

    Smooth paths use C1 Hermite spans through their samples, with analytic
    tangents: inserting a ring beside an old sample must not create a jump
    in its normal. Point paths retain their corners and mitered sections.
    """
    points = [Vector(p) for p in path.points]
    exact = getattr(path, "_at_length", None)
    if exact is not None:
        lengths = path._lengths
    else:
        lengths = [0.0]
        for a, b in zip(points, points[1:]):
            lengths.append(lengths[-1] + (b - a).length)
    total = lengths[-1]
    if total <= _core.mm(1e-9):
        raise ValueError("sweep: a path needs a nonzero length")
    directions = [(b - a) / max(h1 - h0, _core.mm(1e-12))
                  for a, b, h0, h1 in zip(points, points[1:], lengths, lengths[1:])]
    slopes = [directions[0]]
    for i in range(1, len(points) - 1):
        before, after = lengths[i] - lengths[i - 1], lengths[i + 1] - lengths[i]
        slopes.append((directions[i - 1] * after + directions[i] * before)
                      / max(before + after, _core.mm(1e-12)))
    slopes.append(directions[-1])
    samples = {}

    def sample(d):
        if d in samples:
            return samples[d]
        j = min(bisect.bisect_right(lengths, d) - 1, len(points) - 2)
        h = max(lengths[j + 1] - lengths[j], _core.mm(1e-12))
        t = (d - lengths[j]) / h
        if exact is not None:
            q, tangent = exact(d)
        elif smooth:
            delta = points[j + 1] - points[j]
            q = (points[j] + delta * (3*t*t - 2*t**3)
                 + h * slopes[j] * (t**3 - 2*t*t + t) + h * slopes[j + 1] * (t**3 - t*t))
            tangent = (delta / h * (6*t - 6*t*t) + slopes[j] * (3*t*t - 4*t + 1)
                       + slopes[j + 1] * (3*t*t - 2*t))
        else:
            q, tangent = points[j].lerp(points[j + 1], t), directions[j]
        u = d / total
        size = _tip_scale(scale, u, tips) if isinstance(scale, _core.Law) else _linear_scale(scale, u)
        size = size if isinstance(size, tuple) else (size, size)
        angle = twist(u) if isinstance(twist, _core.Law) else twist * u
        samples[d] = q, tangent, size, angle
        return samples[d]

    tolerance = _core.mm(_core.CHORD)
    spots = sorted(set(lengths + [total * k / 64 for k in range(64+1)]
                       + [total * (a + (c - a) * k / 16) for law in laws
                          for a, c in zip(law.u, law.u[1:]) for k in range(16+1)]))
    if isinstance(scale, _core.Law) and _core.FACETS is None:
        required = set(lengths + [total*u for law in laws for u in law.u])
        for end, neighbour, tip in ((0,1,tips[0]),(-1,-2,tips[1])):
            if tip == 'sharp' and all(v == 0 for v in scale.values[end]):
                a,c = sorted((total*scale.u[end],total*scale.u[neighbour]))
                spots = [d for d in spots if not a < d < c or d in required]
    if not laws:
        spots = lengths
    if _core.FACETS is not None:
        spots = sorted(set(lengths + [total * u for law in laws for u in law.u]))
        refined_spots = [spots[0]]
        for a, c in zip(spots, spots[1:]):
            probes = [sample(a + (c-a)*k/64) for k in range(65)]
            paths = [[q + Vector((radius * size[axis], 0, 0)) for q, _, size, _ in probes]
                     for axis in range(2)]
            pieces = max(_core.turn_steps(paths), _core.segments(1, abs(probes[-1][3]-probes[0][3])))
            pieces += rings
            refined_spots += [a + (c-a)*k/pieces for k in range(1, pieces+1)]
        spots = refined_spots
    if rings and _core.FACETS is None:
        knots = sorted(set(lengths + [total * u for law in laws for u in law.u]))
        for a,c in zip(knots,knots[1:]):
            inside = [d for d in spots if a < d < c]
            pieces = len(inside)+rings+1
            spots = [d for d in spots if not a < d < c]
            spots += [a+(c-a)*k/pieces for k in range(1,pieces)]
        spots.sort()
    # Uniform samples and law knots can coincide with an original station up
    # to roundoff. Distinct float32 positions then give a microscopic backwards
    # chord, not a real bend. Merge in the double-precision distance parameter,
    # before evaluating positions/tangents; retain the exact final endpoint.
    # At large placements, a float32 coordinate ULP can exceed the absolute
    # floor. Leave several ULPs between rings so their forward advance survives
    # both centre interpolation and adding the section offsets.
    coordinate = max(abs(c) for p in points for c in p) + radius
    separation = max(_core.mm(1e-4), total * 1e-7, coordinate * 2**-20)
    distinct = [spots[0]]
    for d in spots[1:]:
        if d - distinct[-1] > separation:
            distinct.append(d)
        elif d == total:
            if len(distinct) == 1:
                distinct.append(d)
            else:
                distinct[-1] = d
    spots = distinct
    refined = [spots[0]]

    def refine(a, b, depth=0):
        qa, _, ka, aa = sample(a)
        qb, _, kb, ab = sample(b)
        r = radius * max(*ka, *kb)
        error = r * (1 - math.cos(math.radians(min(abs(ab - aa), 180)) / 2))
        for t in (0.25, 0.5, 0.75):
            q, _, k, angle = sample(a + (b - a) * t)
            # Distance to the meridian chord, not to its parametrised
            # midpoint: sqrt ends need not be sampled below float precision.
            size_error = max(abs((b - a) * radius * (v - x) - (b - a) * t * radius * (y - x))
                             / math.hypot(b - a, radius * (y - x)) for v, x, y in zip(k, ka, kb))
            error = max(error, (q - qa.lerp(qb, t)).length, size_error,
                        r * math.radians(abs(angle - (aa + (ab - aa) * t))))
        if laws and _core.FACETS is None and (error > tolerance or abs(ab - aa) > 15):
            mid = (a + b) / 2
            if depth >= 24 or len(refined) >= 65536 or not a < mid < b:
                raise ValueError("sweep: path laws need too many samples at the chord tolerance")
            refine(a, mid, depth + 1)
            refine(mid, b, depth + 1)
        else:
            refined.append(b)

    for a, b in zip(spots, spots[1:]):
        refine(a, b)
    out, tangents, distances = [], [], []
    for d in refined:
        q, tangent, _, _ = sample(d)
        if out and q == out[-1]:
            tangents[-1] = tangent
            distances[-1] = d
        else:
            out.append(q)
            tangents.append(tangent)
            distances.append(d)
    result = Path(out)
    if smooth:
        result._tangents = tangents
    if exact is not None:
        result._lengths = distances
    return result


def _size_law(law, verb, outlines=1):
    """Only isolated, open-end poles on one outline are supported."""
    if any(v < 0 for row in law.values for v in row):
        raise ValueError(f"{verb}: sizes must be nonnegative")
    zero = [all(v == 0 for v in row) for row in law.values]
    if all(zero):
        raise ValueError(f"{verb}: an all-zero size law has no solid")
    if any(any(v == 0 for v in row) and not z for row, z in zip(law.values, zero)):
        raise ValueError(f"{verb}: partially zero scale pairs are not supported")
    if any(zero[1:-1]):
        raise ValueError(f"{verb}: interior zeros are not supported; only open ends may be poles")
    if any(zero) and outlines != 1:
        raise ValueError(f"{verb}: a pole needs one outline without holes")


def _soft_scale(law, u):
    """Square-root caps, with the value and PCHIP derivative at the joining knot.

    The squared size is a convex mixture of two monotone functions: 2t-t²
    and t**p. Its initial slope is positive (a rounded pole), and its final
    slope is twice the size's prescribed normalised slope. Thus the square
    root joins PCHIP C1 without overshooting the neighbouring size.
    """
    value = law(u)
    out = list(value if law.pair else (value,))
    for end, neighbour in ((0, 1), (-1, -2)):
        if all(v == 0 for v in law.values[end]):
            inside = u <= law.u[neighbour] if end == 0 else u >= law.u[neighbour]
            if inside:
                h = law.u[neighbour] - law.u[end]
                t = min(1.0, max(0.0, (u - law.u[end]) / h))
                for k, target in enumerate(law.values[neighbour]):
                    beta = max(0.0, 2 * h * law.slopes[k][neighbour] / target)
                    power = max(2, math.ceil(beta) + 1)
                    weight = beta / power
                    squared = (1 - weight) * t * (2 - t) + weight * t ** power
                    out[k] = target * math.sqrt(squared)
    return tuple(out) if law.pair else out[0]


def sweep(name, profile, path, scale=1, twist=0, frenet=False, *, tip="round", rings=0):
    """Profile along a path.

    `profile` carried along `path`, square to it: its X and Y turn with the path
    as little as they can (`frenet` makes them follow its curvature). `scale` is its
    size at the end against the start: a number, or a positive (sx, sy) pair,
    linearly from 1 or (1, 1). `twist` is the degrees it turns on the way. A
    closed path makes a ring. Scale and twist also take length laws: [(0, value),
    ..., (1, value)], interpolated by monotone cubics; scale values may be (sx, sy).
    On a zero-ended interval, a monotone square-root cap replaces PCHIP and
    matches its value and slope at the neighbouring knot. An offset profile's
    centre follows the unrounded scale while its outline rounds. Only isolated end
    zeros on one outline without holes are supported: no interior zeros,
    partially zero pairs or all-zero laws. Laws on closed paths are refused;
    numeric scale and twist keep their existing meaning. Law paths are refined
    with their changing size and twist; crossing rings are refused (reduce
    the size or round the path)."""
    path = getattr(path, "_mesh_path", path)
    tips = _ring_options(tip, rings)
    extra = rings
    profile, placement = _placed(profile)
    pts, sharp, loops, tris = profile.mesh()
    local = [placement @ Vector((x, y, 0)) for x, y in pts]
    smooth = isinstance(path, Path) and not any(path.sharp[1:-1])
    path = _as_path(path)
    pair = (isinstance(scale, (list, tuple)) and len(scale) == 2
            and all(isinstance(v, (int, float)) for v in scale))
    if pair:
        if not all(math.isfinite(v) and v > 0 for v in scale):
            raise ValueError("sweep: an end scale pair needs two positive finite ratios")
        scale = tuple(scale)
    scale_law = None if pair or isinstance(scale, (int, float)) else _core.Law(scale, "sweep scale")
    twist_law = None if isinstance(twist, (int, float)) else _core.Law(twist, "sweep twist", pairs=False)
    if scale_law:
        _size_law(scale_law, "sweep scale", len(loops))
        rows = [(u, value if scale_law.pair else value[0]) for u,value in zip(scale_law.u,scale_law.values)]
        for end,neighbour,t in ((0,1,tips[0]),(-1,-2,tips[1])):
            if t == 'flat' and all(v == 0 for v in scale_law.values[end]):
                rows[end] = (rows[end][0],rows[neighbour][1])
        scale_law = _core.Law(rows, 'sweep scale')
    laws = [law for law in (scale_law, twist_law) if law is not None]
    curved_refinement = extra and _core.FACETS is not None and hasattr(path, "_curve_at_length") and not path.closed
    if curved_refinement:
        path._at_length = path._curve_at_length
        path._lengths = path._curve_lengths
    if laws or curved_refinement:
        if path.closed:
            raise ValueError("sweep: laws on closed paths are not supported")
        path = _law_path(path, laws, scale_law or scale, twist_law or twist,
                         max(q.xy.length for q in local), smooth, tips, rings)
    p, tangents, rs, bends = _frames_along(path, frenet)
    if extra and laws and _core.FACETS is not None and any(a.dot(c) < -0.9999 for a,c in bends):
        raise ValueError("sweep: consecutive law rings cross; reduce the size or round the path")
    m = len(p)
    lengths = getattr(path, "_lengths", None)
    if lengths is None:
        lengths = [0.0]
        for i in range(1, m):
            lengths.append(lengths[-1] + (p[i] - p[i - 1]).length)
    total = lengths[-1] + ((p[0] - p[-1]).length if path.closed and laws else 0) or 1.0
    centre = sum(local, Vector()) / len(local) if scale_law else None
    b = _core.Builder(name)
    rings = []
    for i in range(m):
        u = lengths[i] / total
        k = (_tip_scale(scale_law, u, tips) if not path.closed else scale_law(u)) if scale_law else _linear_scale(scale, u)
        kx, ky = k if isinstance(k, tuple) else (k, k)
        raw = scale_law(u) if scale_law else k
        if scale_law and any(tip == 'sharp' and all(v == 0 for v in scale_law.values[end])
                             and (u <= scale_law.u[neighbour] if end == 0 else u >= scale_law.u[neighbour])
                             for end,neighbour,tip in ((0,1,tips[0]),(-1,-2,tips[1]))):
            raw = k
        rawx, rawy = raw if isinstance(raw, tuple) else (raw, raw)
        a = math.radians(twist_law(u) if twist_law else twist * u)
        t, r = tangents[i], rs[i]
        s = t.cross(r)
        d_in, d_out = bends[i]
        bend = d_out - d_in
        bend = bend - t * bend.dot(t)
        cos_half = max(t.dot(d_out), 0.2)
        ring = []
        if scale_law and kx == 0 and ky == 0:
            pole = b.vert(p[i])
            rings.append([pole] * len(local))
            continue
        for q in local:
            if isinstance(k, tuple):
                x = kx * q.x * math.cos(a) - ky * q.y * math.sin(a)
                y = kx * q.x * math.sin(a) + ky * q.y * math.cos(a)
            else:
                x = kx * (q.x * math.cos(a) - q.y * math.sin(a))
                y = ky * (q.x * math.sin(a) + q.y * math.cos(a))
            if scale_law and raw != k:
                # Move an offset profile's centre by the unrounded law, so
                # its radial fan covers the tangent plane at the pole.
                dx, dy = (rawx - kx) * centre.x, (rawy - ky) * centre.y
                x += dx * math.cos(a) - dy * math.sin(a)
                y += dx * math.sin(a) + dy * math.cos(a)
            off = r * x + s * y
            if bend.length > 1e-9:
                bdir = bend.normalized()
                off = off + bdir * off.dot(bdir) * (1 / cos_half - 1)
            ring.append(b.vert(p[i] + off))
        rings.append(ring)
    parameter_total = lengths[-1] + ((p[0]-p[-1]).length if path.closed else 0) or 1.0
    parameters = [d / parameter_total for d in lengths]
    if not laws and extra and not curved_refinement:
        original, original_p = rings, p
        rings, p = [], []
        for i in range(m if path.closed else m-1):
            j = (i+1) % m
            rings.append(original[i])
            p.append(original_p[i])
            for k in range(1, extra+1):
                t = k/(extra+1)
                rings.append([b.vert(a.co.lerp(c.co,t)) for a,c in zip(original[i],original[j])])
                p.append(original_p[i].lerp(original_p[j],t))
        if not path.closed:
            rings.append(original[-1])
            p.append(original_p[-1])
        parameters = [(lengths[i] + ((lengths[j] if j else parameter_total) - lengths[i])*k/(extra+1))/parameter_total
                      for i in range(m if path.closed else m-1)
                      for j in [(i+1)%m] for k in range(extra+1)] + ([] if path.closed else [1.])
        m = len(rings)
    if laws and _core.FACETS is not None:
        crossing = _rings_cross(rings, p)
        _resolve_ring_crossings(rings, p)
        if extra and crossing:
            _clip_ring_slabs(rings, p)
    if laws:
        limit, worst = 1.0, None
        for i, (lower, upper) in enumerate(zip(rings, rings[1:])):
            step = p[i + 1] - p[i]
            forward = ((tangents[i] + tangents[i + 1]).normalized() if smooth and not (extra and _core.FACETS is not None) else step.normalized())
            advance = min((b_.co - a_.co).dot(forward) for a_, b_ in zip(lower, upper))
            if advance < -_core.mm(1e-4):
                centre_step = step.dot(forward)
                factor = max(0.0, centre_step / (centre_step - advance))
                if factor < limit:
                    limit, worst = factor, i
        if worst is not None:
            i = worst
            radius = max((v.co - p[j]).length for j in (i, i + 1) for v in rings[j])
            factor = 0.95 * limit
            u = (lengths[i] + lengths[i + 1]) / (2 * total)
            point = tuple(round(c, 6) for c in (p[i] + p[i + 1]) / 2)
            b.bm.free()
            raise ValueError(f"sweep: consecutive law rings cross near u={u:.6g} at {point}; "
                             f"section radius <= {factor * radius:.6g} {_core.UNIT} "
                             f"(uniform size factor <= {factor:.6g}); otherwise round the path")
    b.lengthwise(rings, parameters, p, [u * parameter_total for u in parameters])
    surface = 0
    spans = m if path.closed else m - 1
    for loop in loops:
        runs = _runs(sharp, loop)
        n = len(loop)
        for i in range(spans):
            lower, upper = rings[i], rings[(i + 1) % m]
            for j in range(n):
                i0, i1 = loop[j], loop[(j + 1) % n]
                b.face([lower[i0], lower[i1], upper[i1], upper[i0]], surface + runs[j], ("side",))
        surface += max(runs) + 1
    if not path.closed:
        caps = [b.face([rings[0][i] for i in reversed(t)], -1, ("start",)) for t in tris]
        caps += [b.face([rings[-1][i] for i in t], -2, ("end",)) for t in tris]
        b.dissolve(caps)
    if laws and extra and _core.FACETS is not None and crossing:
        _check_clipped_rings(b, "sweep: consecutive law rings cross; reduce the size or round the path")
    return _object(b, Matrix.Identity(4), "seam")


def wire(name, path, d, closed=None, fillet=0, *, tip="round", rings=0):
    """Round wire along a path: (x, y, z) points, a spline, an arc, a helix; fillet rounds the corners of
    points, d / 2 at least.

    `d` also takes a length law, on open paths only; zero ends close with
    rounded tips as in sweep, matching PCHIP's slope at the neighbouring knot.
    On a filleted path, laws use exact line-and-arc length and continuous tangents,
    keeping sections circular across arc samples and law knots. Interior zeros and all-zero diameter laws are refused.
    A round wire of diameter `d` along `path` — a pipe, a spring, a rod bent to shape.
    `fillet` rounds the corners of a path given as points to that radius, on the wire's
    centre line, as a tube bender does: one number for all of them, or a list giving
    each point its own (0 leaves it), as `poly` takes it. It raises where it cannot bend:
    too large for a side, under `d / 2` (the tube would fold on itself), at a point where
    the path turns back. A point written twice is one. A stool's leg:
    `wire("leg", [(0, 0, 0), (0, 0, 650), (-250, 0, 650)], 33, fillet=60)`."""
    path = getattr(path, "_mesh_path", path)
    elliptical = (isinstance(d, (tuple, list)) and len(d) == 2
                  and all(isinstance(v, (int, float)) for v in d))
    explicit = not isinstance(rings, (int, bool))
    if explicit:
        try:
            rings = tuple(rings)
        except TypeError:
            raise ValueError('wire: rings must be a count or fractions in (0, 1)') from None
        if any(isinstance(u, bool) or not isinstance(u, (int, float)) or not math.isfinite(u)
               or not 0 < u < 1 for u in rings):
            raise ValueError('wire: rings fractions must be finite and in (0, 1)')
    if explicit and not rings:
        rings, explicit = 0, False
    tips = _ring_options(tip, 0 if explicit else rings)
    if elliptical or explicit:
        return _shaped_wire(name, path, d, closed, fillet, tip, rings)
    point_path = not isinstance(path, (Path, Profile, Placed))
    law = None if isinstance(d, (int, float)) else _core.Law(d, "wire d", pairs=False)
    if law:
        _size_law(law, "wire diameter")
        diameter = max(v[0] for v in law.values)
    else:
        diameter = d
    if fillet:
        if isinstance(path, (Path, Profile, Placed)):
            raise ValueError("wire: fillet rounds the corners of a path given as points, [(x, y, z), ...] — a "
                             "spline, an arc or a helix has none; a profile's are rounded on the profile "
                             "(rect(r=), poly(fillet=))")
        path = _as_path(path)
        is_closed = path.closed if closed is None else closed
        rounded = _filleted(path.points, is_closed, fillet, least=diameter / 2, curve=law is not None)
        path = rounded if isinstance(rounded, Path) else Path(rounded, closed=is_closed)
        if _core.FACETS is not None and law and 'flat' not in tips:
            return _faceted_wire(name, path, law, tip, rings)
        return sweep(name, circle(diameter), path, scale=[(u, v[0] / diameter) for u, v in zip(law.u, law.values)] if law else 1, tip=tip, rings=rings)
    path = _as_path(path)
    if closed is not None:
        path = Path(path.points, closed=closed)
    if law and point_path:
        path.sharp = [True] * len(path.points)
    if _core.FACETS is not None and law and 'flat' not in tips:
        return _faceted_wire(name, path, law, tip, rings)
    return sweep(name, circle(diameter), path, scale=[(u, v[0] / diameter) for u, v in zip(law.u, law.values)] if law else 1, tip=tip, rings=rings)


def _shaped_wire(name, path, d, closed, fillet, tip, rings):
    """Widened wire forms share the path frames and section-law sampler."""
    elliptical = (isinstance(d, (tuple, list)) and len(d) == 2
                  and all(isinstance(v, (int, float)) for v in d))
    explicit = not isinstance(rings, int)
    point_path = not isinstance(path, (Path, Profile, Placed))
    law = None if elliptical or isinstance(d, (int, float)) else _core.Law(d, 'wire d', pairs=False)
    if law:
        _size_law(law, 'wire diameter')
    width, depth = d if elliptical else (max(v[0] for v in law.values) if law else d,)*2
    if any(isinstance(v, bool) or not math.isfinite(v) or v <= 0 for v in (width, depth)):
        raise ValueError('wire: diameters must be positive finite lengths')
    path = _as_path(path)
    if closed is not None:
        path.closed = bool(closed)
    if fillet:
        rounded = _filleted(path.points, path.closed, fillet, least=max(width,depth)/2, curve=True)
        path = rounded if isinstance(rounded, Path) else Path(rounded, closed=path.closed)
    elif point_path:
        path.sharp = [True]*len(path.points)
    profile = superellipse(width, depth) if elliptical else circle(width)
    scale = [(u, v[0]/width) for u,v in zip(law.u,law.values)] if law else 1
    if explicit and path.closed:
        if law:
            raise ValueError('wire: laws on closed paths are not supported')
        points = [Vector(p) for p in path.points]
        lengths = [0.]
        for a,b in zip(points, points[1:]+points[:1]):
            lengths.append(lengths[-1]+(b-a).length)
        us = sorted(set([d/lengths[-1] for d in lengths[:-1]]+list(rings)))
        samples = []
        for u in us:
            distance = u*lengths[-1]
            i = min(len(points)-1, bisect.bisect_right(lengths,distance)-1)
            samples.append(points[i].lerp(points[(i+1)%len(points)],
                           (distance-lengths[i])/(lengths[i+1]-lengths[i])))
        sampled = Path(samples, closed=True)
        return sweep(name, profile, sampled, tip=tip)
    if explicit:
        if hasattr(path, '_curve_at_length'):
            path._at_length = path._curve_at_length
            path._lengths = path._curve_lengths
        elif not hasattr(path, '_at_length'):
            points = [Vector(p) for p in path.points]
            lengths = [0.]
            for a,b in zip(points,points[1:]):
                lengths.append(lengths[-1]+(b-a).length)
            def at_length(distance):
                i = min(len(points)-2, max(0,bisect.bisect_right(lengths,distance)-1))
                step = points[i+1]-points[i]
                return points[i]+step*((distance-lengths[i])/(lengths[i+1]-lengths[i])), step.normalized()
            path._at_length, path._lengths = at_length, lengths
    # A zero twist law inserts required knots without changing the diameter law.
    twist = [(u,0) for u in sorted(set((0.,1.)+tuple(rings)))] if explicit else 0
    return sweep(name, profile, path, scale=scale, twist=twist, tip=tip,
                 rings=0 if explicit else rings)


def _resolve_ring_crossings(rings, centres):
    """Clip overlapping ring offsets to disjoint slabs between their centres.

    Only crossing spans are changed. Midplanes leave a small forward gap;
    clipping moves the inside of a bend rather than reducing its whole radius.
    This is local: distant stretches of a returning path may still overlap.
    """
    for i, (lower, upper) in enumerate(zip(rings, rings[1:])):
        step = centres[i+1] - centres[i]
        if step.length <= _core.mm(1e-9):
            continue
        forward = step.normalized()
        if min((v.co-u.co).dot(forward) for u,v in zip(lower,upper)) >= -_core.mm(1e-4):
            continue
        middle = (centres[i]+centres[i+1])/2
        gap = max(step.length * 1e-5, _core.mm(1e-5))
        for ring, sign in ((lower, -1), (upper, 1)):
            for v in dict.fromkeys(ring):
                distance = (v.co-middle).dot(forward)
                if sign*distance < gap:
                    v.co += forward * (sign*gap-distance)


def _clip_ring_slabs(rings, centres):
    """Project each ring into both neighbouring half-spaces at once.

    Sequential clips can undo the previous clip on a thick bend. The closest
    point satisfying two planes is on one plane or their intersection line.
    First trim against other separating planes whose slabs contain the centre,
    keeping inside strips from reaching through another strip on a tight bend.
    Keep ring identities throughout.
    """
    planes = []
    for a, b in zip(centres, centres[1:]):
        step = b-a
        normal = step.normalized()
        planes.append((normal, (a+b)/2, max(step.length*1e-5, _core.mm(1e-5))))
    for i, ring in enumerate(rings):
        for v in dict.fromkeys(ring):
            for _ in range(128):
                worst = 0.
                for j, (n, o, gap) in enumerate(planes):
                    sign = 1 if j < i else -1
                    if sign*(centres[i]-o).dot(n) < gap:
                        continue
                    excess = gap-sign*(v.co-o).dot(n)
                    if excess > 0:
                        v.co += n*(sign*excess)
                        worst = max(worst,excess)
                if worst <= _core.mm(1e-4):
                    break
        constraints = []
        if i:
            n, o, gap = planes[i-1]
            constraints.append((n, n.dot(o)+gap))
        if i < len(planes):
            n, o, gap = planes[i]
            constraints.append((-n, -n.dot(o)+gap))
        for v in dict.fromkeys(ring):
            point = v.co.copy()
            candidates = []
            if all(n.dot(point) >= d for n,d in constraints):
                continue
            for n,d in constraints:
                q = point+n*(d-n.dot(point))
                if all(m.dot(q) >= e-_core.mm(1e-5) for m,e in constraints):
                    candidates.append(q)
            if len(constraints) == 2:
                (n,d),(m,e) = constraints
                dot = n.dot(m)
                determinant = 1-dot*dot
                if determinant > 1e-8:
                    a, b = d-n.dot(point), e-m.dot(point)
                    candidates.append(point+n*((a-dot*b)/determinant)+m*((b-dot*a)/determinant))
            if candidates:
                v.co = min(candidates, key=lambda q: (q-point).length_squared)


def _rings_cross(rings, centres):
    return any(min((v.co-u.co).dot((b-a).normalized()) for u,v in zip(lower,upper)) < -_core.mm(1e-4)
               for lower,upper,a,b in zip(rings,rings[1:],centres,centres[1:]))


def _check_clipped_rings(builder, message):
    """Do not return an inside fold that clipping could not separate."""
    from mathutils.bvhtree import BVHTree
    bm = builder.bm.copy()
    try:
        bmesh.ops.triangulate(bm, faces=list(bm.faces))
        bm.verts.index_update()
        triangles = [tuple(v.index for v in f.verts) for f in bm.faces]
        tree = BVHTree.FromPolygons([v.co for v in bm.verts], triangles, all_triangles=True)
        pair = next(((i,j) for i,j in tree.overlap(tree)
                     if i < j and not set(triangles[i]) & set(triangles[j])), None)
        crossing = pair is not None
        if crossing and builder.parameters:
            ids = set(triangles[pair[0]]) | set(triangles[pair[1]])
            u = sum(builder.parameters[i] for i in ids)/len(ids)
            message += f" near u={u:.6g}"
    finally:
        bm.free()
    if crossing:
        builder.bm.free()
        raise ValueError(message)


def _faceted_wire(name, path, law, tip="round", rings=0):
    try:
        return _faceted_wire_mesh(name, path, law, tip, rings)
    except ValueError as exc:
        if "rings cross" not in str(exc):
            raise
        # Report a verified working uniform scale, using the same curve and
        # ring rules. Failed trials free their builder before raising.
        low, high = 0., 1.
        for _ in range(16):
            factor = (low+high)/2
            trial = _core.Law([(u,v[0]*factor) for u,v in zip(law.u,law.values)], "wire d", pairs=False)
            try:
                ob = _faceted_wire_mesh(name, path, trial, tip, rings)
            except ValueError:
                high = factor
            else:
                mesh = ob.data
                bpy.data.objects.remove(ob, do_unlink=True)
                if not mesh.users:
                    bpy.data.meshes.remove(mesh)
                low = factor
        low *= .99999
        peak = max(v[0] for v in law.values)
        location = re.search(r"near u=([0-9.e+-]+)",str(exc))
        where = f" near u={location[1]} (diameter <= {law(float(location[1]))*low:.6g} {_core.UNIT})" if location else ""
        raise ValueError(f"wire: consecutive diameter rings cross{where}; largest verified maximum diameter "
                         f"{peak*low:.6g} {_core.UNIT} (uniform diameter factor <= {low:.6g}); "
                         "reduce every diameter or round the path") from None


def _faceted_wire_mesh(name, path, law, tip="round", rings=0):
    extra = rings
    tips = _ring_options(tip, rings)
    """Wire-only angular sampling of diameter meridians; sweep laws stay independent."""
    if path.closed:
        raise ValueError("wire: laws on closed paths are not supported")
    points = [Vector(q) for q in path.points]
    lengths = getattr(path, "_lengths", None)
    if lengths is None:
        lengths = [0.0]
        for a, b in zip(points, points[1:]):
            lengths.append(lengths[-1] + (b - a).length)
    total = lengths[-1]
    if total <= _core.mm(1e-9):
        raise ValueError("wire: a path needs a nonzero length")
    if extra and hasattr(path, "_curve_at_length"):
        path._at_length = path._curve_at_length
        lengths = path._curve_lengths
        total = lengths[-1]
    exact = getattr(path, "_at_length", None)

    def centre(u):
        d = u * total
        if exact is not None:
            return exact(d)[0]
        j = min(max(bisect.bisect_right(lengths, d) - 1, 0), len(points) - 2)
        return points[j].lerp(points[j + 1], (d - lengths[j]) / (lengths[j + 1] - lengths[j]))

    def radius(u):
        return _tip_scale(law, u, tips) / 2

    knots = sorted(set([d / total for d in lengths] + list(law.u)))
    us = [0.0]
    for a, c in zip(knots, knots[1:]):
        # Lift the diameter into a meridian coordinate independent of path orientation.
        probes = [Vector(((a + (c - a) * k / 128) * total,
                          radius(a + (c - a) * k / 128), 0)) for k in range(129)]
        pieces = _core.turn_steps([probes])
        pole = (radius(a) == 0 and tips[0] == "round") or (radius(c) == 0 and tips[1] == "round")
        if pole:
            pieces = max(pieces, _core.segments(1, 90))
        pieces += rings
        for k in range(1, pieces + 1):
            t = k / pieces
            if pole:
                t = math.sin(math.pi / 2 * t) ** 2
            us.append(c if k == pieces else a + (c - a) * t)
    sampled = Path([centre(u) for u in us])
    if exact is not None:
        sampled._tangents = [exact(u * total)[1] for u in us]
    p, tangents, axes, bends = _frames_along(sampled, False)
    folded = next((i for i,(a,c) in enumerate(bends) if a.dot(c) < -0.9999), None)
    if extra and folded is not None:
        raise ValueError(f"wire: consecutive diameter rings cross near u={us[folded]:.6g}; "
                         "reduce the diameter or round the path")
    b = _core.Builder(name)
    rings = []
    n = _core.FACETS
    for u, o, t, r, (din, dout) in zip(us, p, tangents, axes, bends):
        size = radius(u)
        if size == 0:
            rings.append([b.vert(o)] * n)
            continue
        side = t.cross(r)
        bend = dout - din
        bend -= t * bend.dot(t)
        ring = []
        for k in range(n):
            angle = 2 * math.pi * k / n
            off = size * (math.cos(angle) * r + math.sin(angle) * side)
            if bend.length > 1e-9:
                direction = bend.normalized()
                off += direction * off.dot(direction) * (1 / max(t.dot(dout), 0.2) - 1)
            ring.append(b.vert(o + off))
        rings.append(ring)
    b.lengthwise(rings, us, p, [u * total for u in us])
    crossing = _rings_cross(rings, p)
    _resolve_ring_crossings(rings, p)
    if extra and crossing:
        _clip_ring_slabs(rings, p)
    for i, (lower, upper) in enumerate(zip(rings, rings[1:])):
        forward = (p[i + 1] - p[i]).normalized()
        if min((v.co - u.co).dot(forward) for u, v in zip(lower, upper)) < -_core.mm(1e-4):
            b.bm.free()
            raise ValueError(f"wire: consecutive diameter rings cross near u={(us[i]+us[i+1])/2:.6g}; reduce the diameter or round the path")
    for lower, upper in zip(rings, rings[1:]):
        for j in range(n):
            j1 = (j + 1) % n
            b.face([lower[j], lower[j1], upper[j1], upper[j]], 0, ("side",))
    for ring, tag, flip in ((rings[0], "start", True), (rings[-1], "end", False)):
        b.face(list(reversed(ring)) if flip else ring, -1 if flip else -2, (tag,))
    if extra and crossing:
        _check_clipped_rings(b, "wire: consecutive diameter rings cross; reduce the diameter or round the path")
    return _object(b, Matrix.Identity(4), "seam")


def _filleted(points, closed, amount, least=0.0, curve=False):
    """The polyline `points` with each corner turned into an arc of its radius (`amount`: one
    number, or one per point, 0 leaving it), tangent to both sides, in the plane they make.
    A point written twice is one; a radius under `least` (the wire's own), or a corner where
    the path turns back, raises. Turns are read in double precision: `Vector` is single, and
    put a path that doubles back past 180°, which made the setback negative."""
    p = [tuple(float(c) for c in q) + (0.0,) * (3 - len(q)) for q in points]
    if isinstance(amount, (int, float)):
        radii = [float(amount)] * len(p)
    else:
        radii = [float(r) for r in amount]
        if len(radii) != len(p):
            raise ValueError(f"wire: fillet gives {len(radii)} radii for {len(p)} points — one per point, 0 leaving "
                             f"it, or one number for all of them")
    pts, rs = [], []
    for q, r in zip(p, radii):              # a point written twice is one: it keeps the larger radius
        if pts and math.dist(q, pts[-1]) <= _core.mm(EPS):
            rs[-1] = max(rs[-1], r)
        else:
            pts.append(q)
            rs.append(r)
    if closed and len(pts) > 1 and math.dist(pts[-1], pts[0]) <= _core.mm(EPS):
        rs[0] = max(rs[0], rs.pop())
        pts.pop()
    p = [Vector(q) for q in pts]
    m = len(p)

    def said(q):
        return "(" + ", ".join(f"{c:g}" for c in q) + ")"
    corners = {}
    for i in (range(m) if closed else range(1, m - 1)):
        r = rs[i]
        if not r:
            continue
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % m]
        u = [b[k] - a[k] for k in range(3)]
        v = [c[k] - b[k] for k in range(3)]
        cross = math.hypot(u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        turn = math.atan2(cross, sum(u[k] * v[k] for k in range(3)))
        if turn < 1e-6:
            continue
        if turn >= math.pi - 1e-4:
            raise ValueError(f"wire: the path turns back on itself at {said(b)} — a bend turns less than 180°: "
                             f"end the wire there and start another, or give the turn points of its own")
        if r < least - _core.mm(1e-9):
            raise ValueError(f"wire: fillet {r:g} at {said(b)} is tighter than the wire's radius {least:g} (d / 2): a "
                             f"tube bent tighter than its radius folds on itself — give fillet {least:g} or more")
        setback = r * math.tan(turn / 2)
        if not setback >= 0:
            raise ValueError(f"wire: fillet {r:g} at {said(b)} sets the bend back by {setback:g}: a radius is more "
                             f"than 0")
        corners[i] = (setback, r, (p[i] - p[i - 1]).normalized(), (p[(i + 1) % m] - p[i]).normalized(), turn)
    for i in range(m if closed else m - 1):
        j = (i + 1) % m
        used = corners.get(i, (0,))[0] + corners.get(j, (0,))[0]
        length = math.dist(pts[i], pts[j])
        if used > length + _core.mm(1e-9):
            a, b = (tuple(round(c, 6) for c in q) for q in (pts[i], pts[j]))
            raise ValueError(f"wire: fillet too large for the side from {a} to {b} ({used:.4g} > {length:.4g})")
    if curve:
        return _fillet_path(pts, closed, corners)
    out = []
    for i in range(m):
        if i not in corners:
            out.append(p[i])
            continue
        t, r, u, v, turn = corners[i]
        start = p[i] - u * t
        centre = start + (v - u * u.dot(v)).normalized() * r
        axis = u.cross(v).normalized()
        k = _core.segments(r, math.degrees(turn))
        out += [centre + Matrix.Rotation(turn * j / k, 3, axis) @ (start - centre) for j in range(k + 1)]
    kept = [out[0]]
    for q in out[1:]:
        if (q - kept[-1]).length > _core.mm(EPS):
            kept.append(q)
    if closed and len(kept) > 1 and (kept[-1] - kept[0]).length <= _core.mm(EPS):
        kept.pop()
    return [tuple(q) for q in kept]


def _fillet_path(points, closed, corners):
    """Exact line/circle spans for law wires, with physical arc-length samples.

    Re-fitting the sampled arcs changes their curvature and makes a tube's
    admissible diameter depend on where the law adds rings. Keep the analytic
    centre line instead, and carry its distances through to section sizing.
    """
    def unit(v):
        length = math.hypot(*v)
        return tuple(c / length for c in v)

    def cross(a, b):
        return (a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2], a[0]*b[1] - a[1]*b[0])

    arcs = {}
    for i, (setback, radius, _, _, turn) in corners.items():
        a, b, c = points[i - 1], points[i], points[(i + 1) % len(points)]
        u = unit(tuple(y - x for x, y in zip(a, b)))
        v = unit(tuple(y - x for x, y in zip(b, c)))
        dot = sum(x*y for x, y in zip(u, v))
        normal = unit(tuple(y - dot*x for x, y in zip(u, v)))
        start = tuple(x - setback*d for x, d in zip(b, u))
        centre = tuple(x + radius*d for x, d in zip(start, normal))
        radial = tuple(x - y for x, y in zip(start, centre))
        arcs[i] = (start, centre, radial, unit(cross(u, v)), radius, turn)
    current = arcs[0][0] if closed and 0 in arcs else points[0]
    initial = current
    spans, lengths, spots = [], [0.0], [0.0]

    def line_to(end):
        nonlocal current
        length = math.dist(current, end)
        if length > _core.mm(EPS):
            spans.append(("line", current, end))
            lengths.append(lengths[-1] + length)
            spots.append(lengths[-1])
        current = end

    def evaluate(span, distance):
        if span[0] == "line":
            _, a, b = span
            tangent = unit(tuple(y - x for x, y in zip(a, b)))
            return tuple(x + distance*d for x, d in zip(a, tangent)), tangent
        _, centre, radial, axis, radius, turn = span
        angle = min(turn, max(0.0, distance / radius))
        c, t = math.cos(angle), math.sin(angle)
        side = cross(axis, radial)
        parallel = sum(x*y for x, y in zip(axis, radial))
        r = tuple(x*c + y*t + z*parallel*(1-c) for x, y, z in zip(radial, side, axis))
        point = tuple(x + y for x, y in zip(centre, r))
        return point, unit(cross(axis, r))

    for i in range(len(points)):
        if i in arcs:
            start, centre, radial, axis, radius, turn = arcs[i]
            line_to(start)
            span = ("arc", centre, radial, axis, radius, turn)
            spans.append(span)
            before = lengths[-1]
            lengths.append(before + radius * turn)
            count = _core.segments(radius, math.degrees(turn))
            spots.extend(before + radius * turn * j / count for j in range(1, count))
            spots.append(lengths[-1])
            # The outgoing straight line meets the same circle endpoint.
            current = tuple(evaluate(span, radius * turn)[0])
        elif i or not closed:
            line_to(points[i])
    if closed:
        line_to(initial)
    if not spans:
        return Path([initial], closed=closed)

    def at_length(distance):
        j = min(max(bisect.bisect_right(lengths, distance) - 1, 0), len(spans) - 1)
        point, tangent = evaluate(spans[j], distance - lengths[j])
        return Vector(point), Vector(tangent)

    sample_spots = spots[:-1] if closed else spots
    result = Path([at_length(d)[0] for d in sample_spots], closed=closed)
    result._at_length = at_length
    result._lengths = sample_spots
    return result


# ---------------------------------------------------------------- loft

def _resample(pts, sharp, n):
    """A closed outline as `n` points: corners kept and first, spans cut by arc length;
    with no corner, starting where it crosses its local +X."""
    m = len(pts)
    corners = [i for i in range(m) if sharp[i]]
    if not corners:
        cx = sum(x for x, _ in pts) / m
        cy = sum(y for _, y in pts) / m
        start = min(range(m), key=lambda i: (math.atan2(pts[i][1] - cy, pts[i][0] - cx) % (2 * math.pi), i))
        corners = [start]
        smooth = True
    else:
        cx = sum(x for x, _ in pts) / m
        cy = sum(y for _, y in pts) / m
        k = min(range(len(corners)), key=lambda j: (math.atan2(pts[corners[j]][1] - cy, pts[corners[j]][0] - cx)
                                                     % (2 * math.pi), j))
        corners = corners[k:] + corners[:k]
        smooth = False
    spans = []
    for j, c in enumerate(corners):
        nxt = corners[(j + 1) % len(corners)]
        idx = [c]
        while idx[-1] != nxt or len(idx) == 1:
            idx.append((idx[-1] + 1) % m)
            if idx[-1] == nxt:
                break
        spans.append([pts[i] for i in idx])
    lengths = [sum(math.dist(a, b) for a, b in zip(s, s[1:])) for s in spans]
    total = sum(lengths) or 1.0
    shares = [n * l / total for l in lengths]
    counts = [max(1, math.floor(x)) for x in shares]
    for j in sorted(range(len(counts)), key=lambda j: (counts[j] - shares[j], j)):
        if sum(counts) >= n:
            break
        counts[j] += 1
    out, flags = [], []
    for span, length, count in zip(spans, lengths, counts):
        acc = [0.0]
        for a, b in zip(span, span[1:]):
            acc.append(acc[-1] + math.dist(a, b))
        j = 0
        for k in range(count):
            target = length * k / count
            while j < len(span) - 2 and acc[j + 1] < target:
                j += 1
            f = (target - acc[j]) / max(acc[j + 1] - acc[j], _core.mm(1e-12))
            a, b = span[j], span[j + 1]
            out.append((a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])))
            flags.append(k == 0 and not smooth)
    return out, flags


def _arclength(pts, n, closed=False):
    """`n` points along the polyline `pts` by arc length, its end excluded."""
    acc = [0.0]
    for a, b in zip(pts, pts[1:]):
        acc.append(acc[-1] + (b - a).length)
    total = acc[-1]
    out, j = [], 0
    for k in range(n):
        target = total * k / n
        while j < len(pts) - 2 and acc[j + 1] < target:
            j += 1
        seg = acc[j + 1] - acc[j]
        out.append(pts[j].lerp(pts[j + 1], (target - acc[j]) / seg if seg > 0 else 0.0))
    return out


def _start(pts, candidates):
    """The candidate index nearest the local +X ray from the outline's centre."""
    c = sum(pts, Vector((0.0, 0.0))) / len(pts)
    return min(candidates, key=lambda i: ((math.atan2(pts[i].y - c.y, pts[i].x - c.x)) % (2 * math.pi), i))


def _correspond(shapes):
    """The sections as rings of one length whose k-th points belong together.

    As a CAD loft makes its wires compatible: each section is matched to the one
    before by the cyclic shift and the direction that bring their points closest in
    space, so sections that turn are followed, and a half turn too far is not
    (CheckCompatibility in OpenCascade). With the same number of corners in every
    section, corners go to corners and each side gets the same number of points.
    Returns (rings in local coordinates, corner flags)."""
    loops = [[Vector(p) for p in loop.pts] for loop, _ in shapes]
    sharps = [loop.sharp for loop, _ in shapes]
    mats = [m for _, m in shapes]
    target = max(len(p) for p in loops)
    corners = {sum(f) for f in sharps}
    placed = lambda i, q: mats[i] @ Vector((q.x, q.y, 0))  # noqa: E731
    if len(corners) == 1 and next(iter(corners)) > 0:
        c = next(iter(corners))
        sides = []          # per section, its c sides as polylines from one corner to the next (CCW)
        for pts, fl in zip(loops, sharps):
            idx = [i for i, f in enumerate(fl) if f]
            first = _start(pts, idx)
            idx = idx[idx.index(first):] + idx[:idx.index(first)]
            m = len(pts)
            sides.append([[pts[(a + t) % m] for t in range(((b - a) % m or m) + 1)]
                          for a, b in zip(idx, idx[1:] + idx[:1])])
        chosen = [sides[0]]
        for i in range(1, len(sides)):
            prev = [placed(i - 1, side[0]) for side in chosen[-1]]
            best = None
            for reverse in (False, True):
                for shift in range(c):
                    if reverse:
                        cand = [list(reversed(sides[i][(shift - k - 1) % c])) for k in range(c)]
                    else:
                        cand = [sides[i][(shift + k) % c] for k in range(c)]
                    d = sum((placed(i, side[0]) - q).length_squared for side, q in zip(cand, prev))
                    if best is None or d < best[0] - _core.mm2(1e-9):
                        best = (d, cand)
            chosen.append(best[1])
        lengths = [[sum((b - a).length for a, b in zip(side, side[1:])) for side in sec] for sec in chosen]
        counts = [max(1, max(round(target * lens[k] / max(sum(lens), _core.mm(1e-12))) for lens in lengths))
                  for k in range(c)]
        rings = [[q for side, n_ in zip(sec, counts) for q in _arclength(side, n_)] for sec in chosen]
        flags = [t == 0 for n_ in counts for t in range(n_)]
        return rings, flags
    rings = []
    for i, pts in enumerate(loops):
        ring = (list(pts) if _core.FACETS is not None and len(pts) == target
                else _arclength(pts + pts[:1], target))
        start = _start(ring, range(len(ring)))
        ring = ring[start:] + ring[:start]
        if rings:
            prev = [placed(i - 1, q) for q in rings[-1]]
            here = [placed(i, q) for q in ring]
            best = None
            for reverse in (False, True):
                seq = list(reversed(here)) if reverse else here
                order = list(reversed(ring)) if reverse else ring
                for shift in range(target):
                    d = sum((seq[(shift + k) % target] - prev[k]).length_squared for k in range(0, target, 4))
                    if best is None or d < best[0] - _core.mm2(1e-9):
                        best = (d, order[shift:] + order[:shift])
            ring = best[1]
        rings.append(ring)
    return rings, [False] * target


def _cap(ring):
    """Triangles filling a closed 2D outline, as indices into it."""
    edges = [(i, (i + 1) % len(ring)) for i in range(len(ring))]
    _, _, faces, vorig, _, _ = _core.triangulate(ring, edges, 1, EPS)
    tris = []
    for f in faces:
        if all(vorig[v] for v in f):
            t = [vorig[v][0] for v in f]
            (ax, ay), (bx, by), (cx, cy) = (ring[i] for i in t)
            cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
            if abs(cross) > _core.mm2(1e-12):
                tris.append(t if cross > 0 else t[::-1])
    return tris


#: Pieces a loft runs between two sections, on average.
LOFT_STEPS = 6


def _through(values, params, ts, derivative=False):
    """Points at parameters `ts` on the natural cubic spline through `values` at
    `params` — global and C2, as a CAD loft runs (measured against OpenCascade's
    ThruSections on a CAD loft: F@2 % 0.996, against 0.972 for a local Catmull–Rom
    and 0.972 for the interpolating polynomial). `derivative` returns the
    first derivative with respect to the parameter instead of the position."""
    m = len(values)
    h = [params[i + 1] - params[i] for i in range(m - 1)]
    dim = len(values[0])
    second = [[0.0] * dim for _ in range(m)]
    if m > 2:
        for d in range(dim):
            y = [v[d] for v in values]
            a, b, c, r = [0.0] * m, [1.0] * m, [0.0] * m, [0.0] * m
            for i in range(1, m - 1):
                a[i], b[i], c[i] = h[i - 1], 2 * (h[i - 1] + h[i]), h[i]
                r[i] = 6 * ((y[i + 1] - y[i]) / h[i] - (y[i] - y[i - 1]) / h[i - 1])
            for i in range(1, m):
                w = a[i] / b[i - 1]
                b[i] -= w * c[i - 1]
                r[i] -= w * r[i - 1]
            z = [0.0] * m
            z[-1] = r[-1] / b[-1]
            for i in range(m - 2, -1, -1):
                z[i] = (r[i] - c[i] * z[i + 1]) / b[i]
            for i in range(m):
                second[i][d] = z[i]
    out, k = [], 0
    for t in ts:
        while k < m - 2 and t > params[k + 1]:
            k += 1
        t0, t1, hk = params[k], params[k + 1], h[k]
        u, w = (t1 - t) / hk, (t - t0) / hk
        y0, y1 = values[k], values[k + 1]
        s0, s1 = Vector(second[k]), Vector(second[k + 1])
        if derivative:
            out.append((y1 - y0) / hk + ((1 - 3 * u * u) * s0 + (3 * w * w - 1) * s1) * (hk / 6))
        else:
            out.append(y0 * u + y1 * w + ((u ** 3 - u) * s0 + (w ** 3 - w) * s1) * (hk * hk / 6))
    return out


def _loft_through(values, params, ts):
    """Retain natural cubics unless uneven stations make a span overshoot.

    PCHIP bounds every component between its section values. Probe the cubic's
    exact derivative roots so a narrow extremum cannot escape the decision.
    """
    hs = [b-a for a,b in zip(params,params[1:])]
    if max(hs) <= 4*min(hs):
        return _through(values, params, ts)
    slopes = _through(values, params, params, derivative=True)
    unsafe = False
    for i,h in enumerate(hs):
        margin = max((values[i+1]-values[i]).length*.05, _core.mm(1e-4))
        for axis in range(len(values[0])):
            a,b = values[i][axis],values[i+1][axis]
            # Hermite derivative A*t*t+B*t+C in normalised span space.
            c = h*slopes[i][axis]
            d = h*slopes[i+1][axis]
            A,B,C = 6*a-6*b+3*c+3*d, -6*a+6*b-4*c-2*d, c
            roots = []
            if abs(A) < 1e-12:
                if abs(B) > 1e-12:
                    roots = [-C/B]
            elif B*B-4*A*C >= 0:
                root = math.sqrt(B*B-4*A*C)
                roots = [(-B-root)/(2*A),(-B+root)/(2*A)]
            for t in roots:
                if 0 < t < 1:
                    value = a+(b-a)*(3*t*t-2*t**3)+c*(t**3-2*t*t+t)+d*(t**3-t*t)
                    unsafe |= value < min(a,b)-margin or value > max(a,b)+margin
    if not unsafe:
        return _through(values, params, ts)
    normalised = [(p-params[0])/(params[-1]-params[0]) for p in params]
    laws = [_core.Law([(u,v[k]) for u,v in zip(normalised,values)]) for k in range(len(values[0]))]
    return [Vector([law((t-params[0])/(params[-1]-params[0])) for law in laws]) for t in ts]


def _catmull(values, steps, closed):
    """Uniform Catmull–Rom through `values` (Vectors), `steps` pieces per span."""
    m = len(values)
    if m == 2 and not closed:
        return [values[0].lerp(values[1], k / steps) for k in range(steps + 1)]
    out = []
    for i in range(m if closed else m - 1):
        if closed:
            p0, p1, p2, p3 = (values[(i + k) % m] for k in (-1, 0, 1, 2))
        else:
            p0, p1, p2, p3 = (values[max(i - 1, 0)], values[i], values[i + 1], values[min(i + 2, m - 1)])
        for k in range(steps):
            t = k / steps
            out.append(0.5 * (2 * p1 + (p2 - p0) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (3 * p1 - p0 - 3 * p2 + p3) * t ** 3))
    return out if closed else out + [values[-1]]


def _bounded_loft(name, shapes, rings2d, flags, zero, follow, tip="round", extra=0):
    tips = _ring_options(tip, extra)
    """Shape-preserving station fields, with caps confined to the end spans.

    Centres and transported offsets each use PCHIP, so a short end interval
    cannot make the body overshoot. A degree-eight Bezier cap has monotone
    component controls, the neighbouring section's tangent plane at its pole,
    and the same joining derivative as the body. No cap is fitted back into it.
    """
    origins = [mat.to_translation() for _, mat in shapes]
    distances = [0.0]
    for a, b in zip(origins, origins[1:]):
        distances.append(distances[-1] + max((b - a).length, _core.mm(1e-9)))
    params = [d / distances[-1] for d in distances]

    def fields(values):
        return [_core.Law([(u, v[k]) for u, v in zip(params, values)]) for k in range(3)]

    centre_fields = fields(origins)
    offsets, centres = [], []
    n = len(rings2d[0])
    for i, (ring, (_, mat)) in enumerate(zip(rings2d, shapes)):
        if follow:
            tangent = Vector([law.slopes[0][i] for law in centre_fields]).normalized()
            if tangent.length < 1e-9:
                tangent = (origins[min(i + 1, len(origins) - 1)] - origins[max(0, i - 1)]).normalized()
            x = mat.col[0].xyz
            x = (x - tangent * x.dot(tangent)).normalized()
            y = tangent.cross(x)
            placed = [q.x * x + q.y * y for q in ring]
        else:
            placed = [mat.to_3x3() @ Vector((q.x, q.y, 0)) for q in ring]
        mean = sum(placed, Vector()) / n
        centres.append(origins[i] + mean)
        offsets.append([q - mean for q in placed])
    centre_fields = fields(centres)
    point_fields = [fields([ring[k] for ring in offsets]) for k in range(n)]
    controls = {}
    for end, join in ((0, 1), (len(shapes) - 1, len(shapes) - 2)):
        if not zero[end]:
            continue
        h = params[join] - params[end]
        cap = []
        for q, laws in zip(offsets[join], point_fields):
            tangent = Vector([law.slopes[0][join] * h for law in laws])
            # PCHIP limits h*slope/q to [0, 3] on this zero-ended span.
            # These ordered Bezier controls stay between zero and q in
            # every component; their endpoint derivatives are 2q and 2tangent.
            first, last = q / 4, q - tangent / 4
            cap.append([Vector()] + [first.lerp(last, k / 6) for k in range(7)] + [q])
        controls[end] = cap
    bernstein = (1, 8, 28, 56, 70, 56, 28, 8, 1)
    b = _core.Builder(name)
    rings = []
    ring_params = []
    for span in range(len(shapes) - 1):
        end = span if zero[span] else (span + 1 if zero[span + 1] else None)
        if end is None:
            fractions = sorted(set([k / (4 * LOFT_STEPS) for k in range(4 * LOFT_STEPS + 1)]
                                   + [1 / 256, 255 / 256]))
        else:
            fractions = [math.sin(math.pi / 2 * k / 64) ** 2 for k in range(64+1)]
            if end == span + 1:
                fractions = [1 - t for t in reversed(fractions)]
        def evaluate(t):
            u = params[span] + (params[span + 1] - params[span]) * t
            centre = Vector([law(u) for law in centre_fields])
            if end is not None and tips[0 if end == 0 else 1] == 'sharp':
                join = 1 if end == 0 else len(shapes)-2
                amount = t if end == span else 1-t
                return [origins[end].lerp(centres[join] + q, amount) for q in offsets[join]]
            if end is None:
                qs = [Vector([law(u) for law in laws]) for laws in point_fields]
            else:
                s = math.sqrt(t if end == span else 1 - t)
                weights = [c * s**k * (1 - s)**(8 - k) for k, c in enumerate(bernstein)]
                qs = [sum((q * w for q, w in zip(control, weights)), Vector()) for control in controls[end]]
            return [centre + q for q in qs]
        if _core.FACETS is not None:
            if end is not None:
                pieces = _core.segments(1, 90)
                fractions = [math.sin(math.pi / 2 * k / pieces) ** 2 for k in range(pieces + 1)]
                if end == span + 1:
                    fractions = [1 - t for t in reversed(fractions)]
            else:
                probes = [evaluate(k / 64) for k in range(65)]
                pieces = _core.turn_steps([[ring[q] for ring in probes] for q in range(n)])
                fractions = [k / pieces for k in range(pieces + 1)]
        if end is not None and tips[0 if end == 0 else 1] == 'sharp':
            fractions = [0., 1.]
        if extra:
            pieces = len(fractions)-1+extra
            fractions = [k/pieces for k in range(pieces+1)]
        for t in fractions[bool(span):]:
            ring_params.append(span + t)
            if end is not None and ((end == span and t == 0) or (end == span + 1 and t == 1)):
                pole = b.vert(origins[end])
                rings.append([pole] * n)
                continue
            rings.append([b.vert(q) for q in evaluate(t)])
    b.lengthwise(rings, [u / (len(shapes)-1) for u in ring_params])
    runs = _runs(flags, list(range(n)))
    for lower, upper in zip(rings, rings[1:]):
        for j in range(n):
            j1 = (j + 1) % n
            b.face([lower[j], lower[j1], upper[j1], upper[j]], runs[j], ("side",))
    caps = []
    for i, tag, flip in ((0, "start", True), (-1, "end", False)):
        if not zero[i]:
            for tri in _cap(rings2d[i]):
                caps.append(b.face([rings[i][v] for v in (reversed(tri) if flip else tri)], -1 - (i < 0), (tag,)))
    b.dissolve(caps)
    return _object(b, Matrix.Identity(4), "seam")


def loft(name, *sections, follow=False, loop=False, tip="round", rings=0):
    """Through placed sections, capped; loop: a ring.

    A solid through its cross-sections — profiles placed with `at` — smooth between
    them, first to last, its two ends capped: each point runs on a spline through its
    places in the sections, as in a CAD loft. With `follow`, each section is turned
    square to the line through their centres, keeping its X across it. `loop` joins the
    last back to the first: a ring, with no ends. A zero-size end section closes
    on a rounded cap whose tangent matches the continuing body's spline.
    Its pole has the tangent plane of the neighbouring full section (after
    follow's reorientation); the zero section supplies its position only,
    and its rotation is ignored. With poles, centre and section offsets use
    shape-preserving cubics between the original stations; rounding stays in
    the terminal interval, without making the neighbouring body overshoot."""
    _ring_options(tip, rings)
    extra = rings
    if len(sections) < 2:
        raise ValueError("loft needs two sections")
    if loop and len(sections) < 3:
        raise ValueError(f"loft: a ring (loop=True) needs three sections or more, not {len(sections)}")
    for s in sections:
        if isinstance(s, (list, tuple)) and any(isinstance(x, (Profile, Placed)) for x in s):
            raise TypeError("loft: a section is a profile placed with at — s3d.at(profile, on=frame) — not a "
                            "(profile, Frame) pair")
        if hasattr(s, "data") and hasattr(s, "matrix_basis"):
            raise TypeError(f"loft: a section is a profile placed with at, not a solid ({_core.given_name(s)!r})")
    placed = [_placed(s) for s in sections]
    shapes = []
    for prof, mat in placed:
        if len(prof.loops) != 1:
            raise ValueError("loft: each section must be one outline, without holes")
        outline = prof.loops[0]
        if outline.pts and all(q == outline.pts[0] for q in outline.pts):
            mat = mat.copy()
            mat.translation = mat @ Vector((*outline.pts[0], 0))
            outline = Loop([(0, 0)], [False])
        shapes.append((outline, mat))
    zero = [all(x == 0 and y == 0 for x, y in outline.pts) for outline, _ in shapes]
    tips = _ring_options(tip, extra)
    for end,neighbour,t in ((0,1,tips[0]),(-1,-2,tips[1])):
        if t == 'flat' and zero[end]:
            shapes[end] = (shapes[neighbour][0],shapes[end][1])
            zero[end] = False
    if any(zero):
        if loop or any(zero[1:-1]) or all(zero):
            raise ValueError("loft: zero sections belong only at open ends, beside a nonzero section")
        for i in (0, len(shapes) - 1):
            if zero[i]:
                neighbour = shapes[1 if i == 0 else -2][1].copy()
                neighbour.translation = shapes[i][1].translation
                shapes[i] = (shapes[i][0], neighbour)
        compatible = [(shapes[1 if i == 0 else -2][0] if z else outline, mat)
                      for i, ((outline, mat), z) in enumerate(zip(shapes, zero))]
        rings2d, flags = _correspond(compatible)
        for i, z in enumerate(zero):
            if z:
                rings2d[i] = [Vector((0, 0)) for _ in rings2d[i]]
    else:
        rings2d, flags = _correspond(shapes)
    if any(zero):
        return _bounded_loft(name, shapes, rings2d, flags, zero, follow, tip, extra)
    n = len(rings2d[0])
    steps = (max(64, 4 * _core.FACETS) if _core.FACETS is not None
             else (1 if len(sections) == 2 and not loop else LOFT_STEPS))
    base_steps = steps
    if extra:
        steps *= extra + 1
    origins = [mat.to_translation() for _, mat in shapes]
    xs = [mat.to_3x3() @ Vector((1, 0, 0)) for _, mat in shapes]
    ys = [mat.to_3x3() @ Vector((0, 1, 0)) for _, mat in shapes]
    dense_o = _catmull(origins, steps, loop)
    if follow:
        dense_x = _catmull(xs, steps, loop)
        dense_y = _catmull(ys, steps, loop)
        dense_pts = [_catmull([ring[k] for ring in rings2d], steps, loop) for k in range(n)]
    count = len(dense_o)
    b = _core.Builder(name)
    rings = []
    ring_params = [i / steps for i in range(count)]
    if not follow and not loop:  # as a CAD loft: each point on a spline through its places, chord-length
        placed3d = [[mat @ Vector((q.x, q.y, 0)) for q in ring] for ring, (_, mat) in zip(rings2d, shapes)]
        params = [0.0]
        for a, b_ in zip(origins, origins[1:]):
            params.append(params[-1] + max((b_ - a).length, _core.mm(1e-9)))
        mean = params[-1] / (len(params) - 1)
        ts = [params[0]]
        for i in range(len(params) - 1):
            k = 1 if len(sections) == 2 else max(2, round(LOFT_STEPS * (params[i + 1] - params[i]) / mean))
            if _core.FACETS is not None:
                probes = [params[i] + (params[i + 1] - params[i]) * j / 64 for j in range(65)]
                k = _core.turn_steps([_loft_through([sec[q] for sec in placed3d], params, probes) for q in range(n)])
            k += extra
            ts += [params[i] + (params[i+1]-params[i])*j/k for j in range(1,k+1)]
        paths = [_loft_through([sec[k] for sec in placed3d], params, ts) for k in range(n)]
        import bisect
        ring_params = []
        for t in ts:
            span = min(bisect.bisect_right(params, t) - 1, len(params) - 2)
            ring_params.append(span + (t - params[span]) / (params[span + 1] - params[span]))
        count = len(ts)
        rings = [[b.vert(paths[k][i]) for k in range(n)] for i in range(count)]
    elif not follow:
        placed3d = [[mat @ Vector((q.x, q.y, 0)) for q in ring] for ring, (_, mat) in zip(rings2d, shapes)]
        paths = [_catmull([sec[k] for sec in placed3d], steps, loop) for k in range(n)]
        rings = [[b.vert(paths[k][i]) for k in range(n)] for i in range(count)]
    for i in range(count if follow else 0):
        o, x, y = dense_o[i], dense_x[i], dense_y[i]
        if follow:
            if loop:
                t = dense_o[(i + 1) % count] - dense_o[i - 1]
            else:
                t = dense_o[min(i + 1, count - 1)] - dense_o[max(i - 1, 0)]
            t.normalize()
            x = (x - t * x.dot(t)).normalized()
            y = t.cross(x)
        else:
            z = x.cross(y).normalized()
            x = x.normalized()
            y = z.cross(x)
        rings.append([b.vert(o + dense_pts[k][i].x * x + dense_pts[k][i].y * y) for k in range(n)])
    if (_core.FACETS is not None or extra) and (follow or loop):
        # Probe the transported meridians, then keep the original station rings.
        kept = []
        spans = len(sections) if loop else len(sections) - 1
        for span in range(spans):
            indices = [(span * steps + j) % count for j in range(steps + 1)]
            pieces = (_core.turn_steps([[rings[i][q].co for i in indices] for q in range(n)])
                      if _core.FACETS is not None else base_steps)
            pieces += extra
            fractions = [j/pieces for j in range(pieces)]
            kept += [indices[round(t * steps)] for t in fractions]
        if not loop:
            kept.append(count - 1)
        retained = set(kept)
        discarded = [v for i, ring in enumerate(rings) if i not in retained for v in ring]
        rings = [rings[i] for i in kept]
        ring_params = [ring_params[i] for i in kept]
        for v in discarded:
            b.bm.verts.remove(v)
        count = len(rings)
    b.lengthwise(rings, [u / (len(shapes) if loop else len(shapes)-1) for u in ring_params])
    runs = _runs(flags, list(range(n)))
    for i in range(count if loop else count - 1):
        lower, upper = rings[i], rings[(i + 1) % count]
        for j in range(n):
            j1 = (j + 1) % n
            b.face([lower[j], lower[j1], upper[j1], upper[j]], runs[j], ("side",))
    if not loop:
        caps = []
        for ring, k, tag, flip in ((rings2d[0], 0, "start", True), (rings2d[-1], count - 1, "end", False)):
            if zero[0 if k == 0 else -1]:
                continue
            for t in _cap(ring):
                caps.append(b.face([rings[k][v] for v in (reversed(t) if flip else t)], -1 - (k > 0), (tag,)))
        b.dissolve(caps)
    return _object(b, Matrix.Identity(4), "seam")


# ---------------------------------------------------------------- body

#: Sections a body gets along its length besides one at each point its views give.
BODY_SECTIONS = 48
#: How far apart (mm) the two sections of a step in a view are: two points at one y (a windscreen's
#: foot) make a shoulder, a wall a hair long — above single-precision noise at 50 m.
BODY_STEP = 0.05
#: How far back along y (a share of its length) a spline view may overshoot near a point and still
#: be read as drawn: a round nose's spline goes back 21 mm in 1 000; a view drawn there and back, all of it.
SPLINE_BACK = 0.1


def body(name, plan, top, bottom, n=2):
    """Solid along Y from its views, where they draw it: plan (y, width), side top and bottom (y, z) or numbers;
    superellipse sections.

    A solid as a fuselage, a hull, a car or a fish is drawn: along Y, from the first point
    of `plan` to its last, the top view gives its width — `plan`, (y, width) points, the
    full width across as `station` and `superellipse` take it, centred on x = 0 — and the
    side view its top and bottom lines — `top`, `bottom`, (y, z) points, or a number. The
    y and z are where the views draw them: the body is not moved to z = 0. Each section
    across is a `superellipse` of squareness `n`: a number, or (y, n) points (a round
    nose, a boxy cabin). A list of points runs straight between them, a `spline` of them
    smoothly: there is a section at each point a list gives, and where a spline or a
    changing `n` curves the body, 48 more along it. Two points at one y are a step, a
    shoulder: the body runs on from the second.
    A spline that overshoots back a little near a point (a round nose) is read as drawn.
    An end where both views close is a point; any other is a flat cap, `start` at -Y and
    `end` at +Y; the wall is `side`. Laid along X: `at(body(...), rz=90)`."""
    wide, span, steps = _view(plan, "plan", "width")
    if span is None:
        raise ValueError("body: plan is the width seen from above, (y, width) points from one end to the "
                         "other — it says where the body starts and ends, so it is not a number")
    high, top_span, top_steps = _view(top, "top", "z")
    low, bottom_span, bottom_steps = _view(bottom, "bottom", "z")
    square, n_span, n_steps = _view(n, "n", "squareness")
    y0, y1 = span
    reach = _core.mm(1e-6) + 1e-9 * (abs(y0) + abs(y1))
    for what, got in (("top", top_span), ("bottom", bottom_span), ("n", n_span)):
        if got is not None and (got[0] > y0 + reach or got[1] < y1 - reach):
            raise ValueError(f"body: {what} runs from y = {got[0]:g} to {got[1]:g}, the plan from {y0:g} to {y1:g}: "
                             f"each view covers the whole length")
    # straight views and one squareness make a ruled wall between their points: a section at each
    # is exact; a spline or a changing n curves it, and gets sections along the length too (closer
    # at the ends, where a nose turns)
    curved = any(isinstance(v, Path) for v in (plan, top, bottom, n)) or not isinstance(n, (int, float))
    ys = {y0 + (y1 - y0) * (1 - math.cos(math.pi * i / BODY_SECTIONS)) / 2
          for i in range(BODY_SECTIONS + 1)} if curved else {y0, y1}
    if _core.FACETS is not None and curved:
        def meridians(y):
            w, hi, lo = wide(y), high(y), low(y)
            k = square(y)
            if not k > 0:
                raise ValueError(f"body: n must be positive, not {k:g} at y = {y:g}")
            section = superellipse(max(w, _core.mm(1e-9)), max(hi - lo, _core.mm(1e-9)), n=k).loops[0].pts
            return [Vector((x, y, z + (hi + lo) / 2)) for x, z in section]
        probes = [meridians(y0 + (y1 - y0) * k / 128) for k in range(129)]
        pieces = _core.turn_steps([[r[q] for r in probes] for q in range(len(probes[0]))])
        ys = {y0 + (y1 - y0) * k / pieces for k in range(pieces + 1)}
        for view in (plan, top, bottom, n):
            if isinstance(view, Path):
                ys |= {float(q[0]) for q in view.points if y0 <= q[0] <= y1}
    for view in (plan, top, bottom, n):
        if isinstance(view, (list, tuple)):
            ys |= {float(q[0]) for q in view if y0 <= float(q[0]) <= y1}
    # a step is two sections a hair apart: at its y, what the views reach it with; then what they
    # run on with. At an end, a step is that end's section, as wide as the body goes on
    hair, before = _core.mm(BODY_STEP), set()
    for y in sorted(steps | top_steps | bottom_steps | n_steps):
        if y0 + reach < y < y1 - reach:
            after = y + hair if y + hair < y1 - reach else y
            y = y if after > y else y - hair
            ys |= {y, after}
            before.add(y)
    ys = sorted(ys)
    ys = [y for i, y in enumerate(ys) if i == 0 or y - ys[i - 1] > reach]
    tiny = _core.mm(1e-3)
    b = _core.Builder(name)
    rings, caps2d = [], []
    for i, y in enumerate(ys):
        side = y in before or i == len(ys) - 1
        width, z_top, z_bottom, k = wide(y, side), high(y, side), low(y, side), square(y, side)
        if width < -tiny or z_top < z_bottom - tiny:
            raise ValueError(f"body: at y = {y:g} the " + ("plan's width is below 0" if width < -tiny else
                             f"top line (z = {z_top:g}) is under the bottom line (z = {z_bottom:g})"))
        if not k > 0:
            raise ValueError(f"body: n is a squareness, more than 0 (2 round, 4 boxy), not {k:g} at y = {y:g}")
        closes = (width <= tiny, z_top - z_bottom <= tiny)
        if all(closes) and i in (0, len(ys) - 1):
            rings.append([b.vert((0, y, (z_top + z_bottom) / 2))])
            caps2d.append(None)
            continue
        if any(closes):
            where = "an end" if i in (0, len(ys) - 1) else "inside the length"
            raise ValueError(f"body: at y = {y:g}, {where}, the " + ("plan closes but the side view is "
                             f"{z_top - z_bottom:g} high" if closes[0] else f"side view closes but the plan is "
                             f"{width:g} wide") + ": a body closes to a point where both views close, at an end")
        section = superellipse(width, z_top - z_bottom, n=k).loops[0].pts
        centre = (z_top + z_bottom) / 2
        rings.append([b.vert((x, y, centre + z)) for x, z in section])
        caps2d.append(section)
    if len({len(r) for r in rings if len(r) > 1}) > 1:
        raise ValueError("body: its sections came out with different numbers of points")
    for lower, upper in zip(rings, rings[1:]):
        m = max(len(lower), len(upper))
        for k in range(m):
            k1 = (k + 1) % m
            if len(lower) == 1:
                b.face([lower[0], upper[k1], upper[k]], 0, ("side",))
            elif len(upper) == 1:
                b.face([lower[k], lower[k1], upper[0]], 0, ("side",))
            else:
                b.face([lower[k], lower[k1], upper[k1], upper[k]], 0, ("side",))
    caps = []
    for ring, section, tag, surface in ((rings[0], caps2d[0], "start", -1), (rings[-1], caps2d[-1], "end", -2)):
        if section is not None:
            caps += [b.face([ring[v] for v in t], surface, (tag,)) for t in _cap([Vector(q) for q in section])]
    b.dissolve(caps)
    return _object(b, Matrix.Identity(4), "seam")


def _view(value, what, unit):
    """A view as a function of y — from a number, a list of (y, value) points (straight between
    them) or a `spline` of them — the y it runs over (None for a number), and the y where it
    steps: two points at one y. The function reads what the view runs on with at a step, or,
    `before`, what it reaches the step with."""
    if isinstance(value, bool) or value is None:
        raise TypeError(f"body: {what} is (y, {unit}) points, a spline of them, or a number — not {value!r}")
    if isinstance(value, (int, float)):
        return (lambda y, before=False: float(value)), None, set()
    if isinstance(value, (Profile, Placed)):
        raise TypeError(f"body: {what} is (y, {unit}) points or an open spline of them, read along the length — "
                        f"not a closed profile")
    pts = [(float(q[0]), float(q[1])) for q in (value.points if isinstance(value, Path) else value)]
    if len(pts) < 2:
        raise ValueError(f"body: {what} needs two points, (y, {unit}), at least")
    if pts[0][0] > pts[-1][0]:
        pts = pts[::-1]
    if isinstance(value, Path):
        # a spline through points that go one way overshoots back near a point where the view turns
        # steeply (a round nose): its points are read as far as they go on
        kept, back = [pts[0]], 0.0
        for q in pts[1:]:
            if q[0] < kept[-1][0]:
                back = max(back, kept[-1][0] - q[0])
            else:
                kept.append(q)
        if len(kept) < 2 or back > SPLINE_BACK * (kept[-1][0] - kept[0][0]):
            raise ValueError(f"body: {what}'s spline turns back along y by {back:g}: a view's outline goes one way "
                             f"along the length — (y, {unit}) points, never back")
        pts = kept
    if any(q[0] < p[0] - _core.mm(1e-6) for p, q in zip(pts, pts[1:])):
        raise ValueError(f"body: {what} is read along the length: its points go one way along y, as a view's "
                         f"outline does — (y, {unit}), never back")
    ys = [pts[0][0]]
    for q in pts[1:]:
        ys.append(max(q[0], ys[-1]))          # one way along y, within the 1e-6 mm allowed above
    steps = {ys[i] for i in range(len(ys) - 1) if ys[i + 1] - ys[i] <= _core.mm(1e-6) and pts[i][1] != pts[i + 1][1]}

    def at(y, before=False):
        """The view at y: what it runs on with, or, `before`, what it reaches y with."""
        j = bisect.bisect_left(ys, y) if before else bisect.bisect_right(ys, y) - 1
        if before:
            if j == 0:
                return pts[0][1]
            if j == len(ys):
                return pts[-1][1]
            (ya, va), (yb, vb) = (ys[j - 1], pts[j - 1][1]), (ys[j], pts[j][1])
            if y >= yb:
                return vb
        else:
            if j < 0:
                return pts[0][1]
            if j >= len(ys) - 1:
                return pts[-1][1]
            (ya, va), (yb, vb) = (ys[j], pts[j][1]), (ys[j + 1], pts[j + 1][1])
        return va if yb - ya <= 0 else va + (vb - va) * (y - ya) / (yb - ya)
    return at, (ys[0], ys[-1]), steps


# ---------------------------------------------------------------- paths

def helix(d, pitch, h, left=False):
    """Coil path up Z.

    A coil of diameter `d` rising `pitch` a turn up Z, `h` high, from +X: a path."""
    turns = h / pitch
    n = _core.segments(d / 2, 360 * turns)
    sign = -1 if left else 1
    return Path([(d / 2 * math.cos(sign * 2 * math.pi * turns * i / n),
                  d / 2 * math.sin(sign * 2 * math.pi * turns * i / n), h * i / n) for i in range(n + 1)])


def spiral(d, d2, turns, h=0, left=False):
    """Spiral path from diameter d to d2, geometrically, rising h over turns turns.

    Starts on +X at z = 0, anticlockwise about +Z; left mirrors the turning, not
    the rise. h may be negative. Always open, even when its ends meet.
    """
    for name, value in (("d", d), ("d2", d2), ("turns", turns), ("h", h)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise TypeError(f"spiral: {name} is a finite number, not {value!r}")
        if name != "h" and value <= 0:
            raise ValueError(f"spiral: {name} must be more than 0, not {value:g}")
    if not isinstance(left, bool):
        raise TypeError(f"spiral: left is True or False, not {left!r}")
    n = _core.segments(max(d, d2) / 2, 360 * turns)
    # An even number of intervals samples the geometric mean exactly halfway.
    n += n % 2
    sign = -1 if left else 1
    ratio = d2 / d
    log_ratio = math.log(ratio) if 0 < ratio < math.inf else None
    points = []
    for i in range(n + 1):
        t = i / n
        # A ratio keeps exact changes of unit exact. The fallback avoids overflow
        # or underflow when the two finite diameters have an unrepresentable ratio.
        diameter = (d * math.exp(log_ratio * t) if log_ratio is not None else
                    math.exp(math.log(d) * (1 - t) + math.log(d2) * t))
        r = (d if i == 0 else d2 if i == n else diameter) / 2
        theta = sign * 2 * math.pi * turns * t
        points.append((r * math.cos(theta), r * math.sin(theta), h * t))
    return Path(points)


def hull(name, points):
    """Closed convex hull of points, where they are given, with crisp planar faces.

    `points` is an iterable of (x, y, z) coordinates or Frames (their origins),
    in the program's unit and the solid's own frame. Coordinates are not recentered.
    Duplicate and interior points are ignored. Faces have no names; read a face by
    direction, such as ob.face("+Z"). Edges are named "rim".

    At least four distinct, non-coplanar points are required. Degeneracy is checked
    within 1e-6 mm or 1e-7 of the extent, whichever is larger.
    Non-finite coordinates are refused.
    """
    from .frames import Frame

    coords = []
    for point in points:
        try:
            co = tuple(point.origin if isinstance(point, Frame) else point)
            if len(co) != 3 or any(isinstance(c, bool) or not isinstance(c, (int, float))
                                   or not math.isfinite(c) for c in co):
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError("hull: each point is a finite (x, y, z) or a Frame") from None
        coords.append(tuple(float(c) for c in co))
    coords = sorted(set(coords))
    if len(coords) < 4:
        raise ValueError("hull: at least 4 distinct points are required")
    # Work about a nearby origin at unit extent: hull's float tolerances must not
    # depend on the program's unit or on its distance from the origin.
    origin = coords[0]
    extent = max(max(p[i] for p in coords) - min(p[i] for p in coords) for i in range(3))
    qs = [Vector(tuple((c - o) / extent for c, o in zip(p, origin))) for p in coords]
    tolerance = max(_core.mm(1e-6) / extent, 1e-7)
    a = qs[0]
    b = max(qs, key=lambda p: (p - a).length_squared)
    axis = (b - a).normalized()
    c = max(qs, key=lambda p: (p - a).cross(axis).length_squared)
    normal = (c - a).cross(axis)
    if normal.length <= tolerance:
        raise ValueError("hull: points are coplanar or degenerate")
    normal.normalize()
    if max(abs((p - a).dot(normal)) for p in qs) <= tolerance:
        raise ValueError("hull: points are coplanar or degenerate")
    bm = bmesh.new()
    try:
        verts = [bm.verts.new(p) for p in qs]
        source = {v: i for i, v in enumerate(verts)}
        bmesh.ops.convex_hull(bm, input=verts, use_existing_faces=False)
        bm.normal_update()
        if not bm.faces or any(not e.is_manifold for e in bm.edges if e.link_faces):
            raise ValueError("hull: points are coplanar or degenerate")
        # Rebuild from canonical loops, rather than inherit the operator's order.
        loops = []
        for face in bm.faces:
            loop = [source[v] for v in face.verts]
            start = loop.index(min(loop))
            loops.append(tuple(loop[start:] + loop[:start]))
        loops.sort()
    finally:
        bm.free()
    builder = _core.Builder(name)
    used = sorted({i for loop in loops for i in loop})
    verts = {i: builder.vert(coords[i]) for i in used}
    for surface, loop in enumerate(loops):
        builder.face([verts[i] for i in loop], surface, ())
    return builder.finish("rim")


# ---------------------------------------------------------------- primitives

def box(name, w, d, h):
    """On Z = 0, centred in X and Y.

    A box `w` wide (X), `d` deep (Y), `h` high (Z), from Z = 0 up, centred in X and Y:
    `extrude(name, rect(w, d), h)`. Every solid starts at Z = 0; `both=True` on
    `extrude` centres one on Z = 0 too."""
    return extrude(name, rect(w, d), h)


def cylinder(name, d, h):
    """Along Z, from Z = 0.

    A cylinder of diameter `d` and height `h` along Z, from Z = 0 up."""
    ob = extrude(name, circle(d), h)
    from ._coordinates import height_coordinates
    height_coordinates(ob, h)
    return ob


def tube(name, d, d_in, h):
    """Along Z, from Z = 0.

    A cylinder along Z with a hole of diameter `d_in` through it, from Z = 0 up: a
    sleeve, a washer."""
    return extrude(name, circle(d) - circle(d_in), h)


def cone(name, d, h, d2=0):
    """Along Z, from Z = 0.

    A cone along Z, from Z = 0 up: diameter `d` at the bottom, `d2` at the top."""
    pts = [(0, 0), (d / 2, 0), (d2 / 2, h), (0, h)]
    return revolve(name, poly([q for i, q in enumerate(pts) if not (i == 2 and d2 == 0)]))


def sphere(name, d):
    """On Z = 0.

    A sphere of diameter `d` resting on Z = 0, its centre at Z = d / 2."""
    return revolve(name, poly([(0, 0), arc((0, d / 2), d / 2, -90, 90)]))


def wedge(name, w, d, h, top=0):
    """Box narrowed on top.

    A box whose top is only `top` wide (X), from Z = 0 up, centred in X and Y: a
    ramp's profile, `d` deep."""
    shape = poly([(-w / 2, 0), (w / 2, 0), (top / 2, h), (-top / 2, h)])
    ob = extrude(name, shape, d, both=True)
    ob.data.transform(Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1))))   # a quarter turn about X, exact
    return ob


def torus(name, d, d_wire):
    """Ring about Z, on Z = 0.

    A ring about Z resting on Z = 0: `d` is the diameter of the wire's centre line,
    which lies at Z = d_wire / 2."""
    return revolve(name, Placed(circle(d_wire), Matrix.Translation((d / 2, d_wire / 2, 0))))


def dome(name, d, h):
    """Cap on Z = 0.

    A spherical cap `d` across its base and `h` high, its base on Z = 0: a button, a nail head."""
    r = (d * d / 4 + h * h) / (2 * h)
    base = math.degrees(math.atan2(r - h, d / 2))
    return revolve(name, poly([(0, 0), (d / 2, 0), arc((0, h - r), r, base, 90)]))
