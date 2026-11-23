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

from mathutils import Matrix, Vector, geometry

from . import _core
from .profile import (EPS, Loop, Path, Placed, Profile, _as_path, _crossing, _fit, _said, arc, circle, poly, rect,
                      superellipse)


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
    for i in range(m):
        if closed:
            d_in, d_out = seg[i - 1], seg[i]
        else:
            d_in = seg[i - 1] if i > 0 else seg[0]
            d_out = seg[i] if i < m - 1 else seg[-1]
        t = d_in.normalized() + d_out.normalized()
        t = t.normalized() if t.length > 1e-9 else d_out.normalized()
        tangents.append(t)
        bends.append((d_in.normalized(), d_out.normalized()))
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


def sweep(name, profile, path, scale=1, twist=0, frenet=False):
    """Profile along a path.

    `profile` carried along `path`, square to it: its X and Y turn with the path
    as little as they can (`frenet` makes them follow its curvature). `scale` is its
    size at the end against the start, `twist` the degrees it turns on the way. A
    closed path makes a ring."""
    profile, placement = _placed(profile)
    pts, sharp, loops, tris = profile.mesh()
    path = _as_path(path)
    p, tangents, rs, bends = _frames_along(path, frenet)
    m = len(p)
    lengths = [0.0]
    for i in range(1, m):
        lengths.append(lengths[-1] + (p[i] - p[i - 1]).length)
    total = lengths[-1] or 1.0
    local = [placement @ Vector((x, y, 0)) for x, y in pts]
    b = _core.Builder(name)
    rings = []
    for i in range(m):
        u = lengths[i] / total
        k = 1 + (scale - 1) * u
        a = math.radians(twist * u)
        t, r = tangents[i], rs[i]
        s = t.cross(r)
        d_in, d_out = bends[i]
        bend = d_out - d_in
        bend = bend - t * bend.dot(t)
        cos_half = max(t.dot(d_out), 0.2)
        ring = []
        for q in local:
            x = k * (q.x * math.cos(a) - q.y * math.sin(a))
            y = k * (q.x * math.sin(a) + q.y * math.cos(a))
            off = r * x + s * y
            if bend.length > 1e-9:
                bdir = bend.normalized()
                off = off + bdir * off.dot(bdir) * (1 / cos_half - 1)
            ring.append(b.vert(p[i] + off))
        rings.append(ring)
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
    return _object(b, Matrix.Identity(4), "seam")


def wire(name, path, d, closed=None, fillet=0):
    """Round wire along a path: (x, y, z) points, a spline, an arc, a helix; fillet rounds the corners of
    points, d / 2 at least.

    A round wire of diameter `d` along `path` — a pipe, a spring, a rod bent to shape.
    `fillet` rounds the corners of a path given as points to that radius, on the wire's
    centre line, as a tube bender does: one number for all of them, or a list giving
    each point its own (0 leaves it), as `poly` takes it. A fillet too large for a side
    is clamped to the largest that fits, with a warning (strict mode: an error). It raises
    where it cannot bend: under `d / 2` (the tube would fold on itself), at a point where
    the path turns back. A point written twice is one. A stool's leg:
    `wire("leg", [(0, 0, 0), (0, 0, 650), (-250, 0, 650)], 33, fillet=60)`."""
    if fillet:
        if isinstance(path, (Path, Profile, Placed)):
            raise ValueError("wire: fillet rounds the corners of a path given as points, [(x, y, z), ...] — a "
                             "spline, an arc or a helix has none; a profile's are rounded on the profile "
                             "(rect(r=), poly(fillet=))")
        path = _as_path(path)
        path = Path(_filleted(path.points, path.closed if closed is None else closed, fillet, least=d / 2),
                    closed=path.closed if closed is None else closed)
        return sweep(name, circle(d), path)
    path = _as_path(path)
    if closed is not None:
        path = Path(path.points, closed=closed)
    return sweep(name, circle(d), path)


def _filleted(points, closed, amount, least=0.0):
    """The polyline `points` with each corner turned into an arc of its radius (`amount`: one
    number, or one per point, 0 leaving it), tangent to both sides, in the plane they make.
    A point written twice is one; a radius under `least` (the wire's own), or a corner where
    the path turns back, raises; one too large for a side is clamped to the largest that
    fits, with a warning (strict mode raises). Turns are read in double precision: `Vector`
    is single, and put a path that doubles back past 180°, which made the setback negative."""
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
    over = []
    for i in range(m if closed else m - 1):
        j = (i + 1) % m
        used = corners.get(i, (0,))[0] + corners.get(j, (0,))[0]
        length = math.dist(pts[i], pts[j])
        if used > length + _core.mm(1e-9):
            over.append((i, j, used, length))
    if over:
        i, j, used, length = over[0]
        a, b = (tuple(round(c, 6) for c in q) for q in (pts[i], pts[j]))
        error = ValueError(f"wire: fillet too large for the side from {a} to {b} ({used:.4g} > {length:.4g})")
        from .edit import _clamped, _is_strict
        if _is_strict():
            raise error
        minimums = {k: min(t, least * math.tan(turn / 2)) for k, (t, _, _, _, turn) in corners.items()}
        for i, j, _, length in over:
            if minimums.get(i, 0) + minimums.get(j, 0) <= length + _core.mm(1e-9):
                continue
            k = i if i in corners else j
            other = j if k == i else i
            largest = max(0.0, length - minimums.get(other, 0)) / math.tan(corners[k][4] / 2)
            raise ValueError(f"{error}: the largest fillet that fits at {said(pts[k])}, {largest:.4g}, is tighter "
                             f"than the wire's radius {least:g} (d / 2), and a tube bent tighter than its radius "
                             f"folds on itself")
        factors, (i, j, length) = _fit(corners, over, minimums)
        k = max((k for k in (i, j) if k in factors), key=lambda k: corners[k][1])
        r = corners[k][1]
        _clamped(error, f"wire: fillet={r:g} too large for the side of {length:.4g} from {_said(pts[i])} to "
                        f"{_said(pts[j])}; clamped to {r * factors[k]:.4g}")
        for k, fk in factors.items():
            t, rk, u, v, turn = corners[k]
            corners[k] = (t * fk, rk * fk, u, v, turn)
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
        ring = _arclength(pts + pts[:1], target)
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


def _through(values, params, ts):
    """Points at parameters `ts` on the natural cubic spline through `values` at
    `params` — global and C2, as a CAD loft runs (measured against OpenCascade's
    ThruSections on a CAD loft: F@2 % 0.996, against 0.972 for a local Catmull–Rom
    and 0.972 for the interpolating polynomial)."""
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
        out.append(y0 * u + y1 * w + ((u ** 3 - u) * s0 + (w ** 3 - w) * s1) * (hk * hk / 6))
    return out


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


def loft(name, *sections, follow=False, loop=False):
    """Through placed sections, capped; loop: a ring.

    A solid through its cross-sections — profiles placed with `at` — smooth between
    them, first to last, its two ends capped: each point runs on a spline through its
    places in the sections, as in a CAD loft. With `follow`, each section is turned
    square to the line through their centres, keeping its X across it. `loop` joins the
    last back to the first: a ring, with no ends."""
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
    for rank, (prof, mat) in enumerate(placed, 1):
        if len(prof.loops) != 1:
            if prof._outline is not None:   # not holes: poly split an outline that crosses itself
                q = _crossing(prof._outline)
                near = f" near {_said(q)}" if q is not None else ""
                raise ValueError(f"loft: section {rank} crosses itself{near} — poly split its outline into "
                                 f"{len(prof.loops)} pieces, and a section is one outline: move its points so that "
                                 f"its sides do not cross")
            raise ValueError("loft: each section must be one outline, without holes")
        shapes.append((prof.loops[0], mat))
    rings2d, flags = _correspond(shapes)
    n = len(rings2d[0])
    steps = 1 if len(sections) == 2 and not loop else LOFT_STEPS
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
    if not follow and not loop:  # as a CAD loft: each point on a spline through its places, chord-length
        placed3d = [[mat @ Vector((q.x, q.y, 0)) for q in ring] for ring, (_, mat) in zip(rings2d, shapes)]
        params = [0.0]
        for a, b_ in zip(origins, origins[1:]):
            params.append(params[-1] + max((b_ - a).length, _core.mm(1e-9)))
        mean = params[-1] / (len(params) - 1)
        ts = [params[0]]
        for i in range(len(params) - 1):
            k = 1 if len(sections) == 2 else max(2, round(LOFT_STEPS * (params[i + 1] - params[i]) / mean))
            ts += [params[i] + (params[i + 1] - params[i]) * j / k for j in range(1, k + 1)]
        paths = [_through([sec[k] for sec in placed3d], params, ts) for k in range(n)]
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
    runs = _runs(flags, list(range(n)))
    for i in range(count if loop else count - 1):
        lower, upper = rings[i], rings[(i + 1) % count]
        for j in range(n):
            j1 = (j + 1) % n
            b.face([lower[j], lower[j1], upper[j1], upper[j]], runs[j], ("side",))
    if not loop:
        caps = []
        for ring, k, tag, flip in ((rings2d[0], 0, "start", True), (rings2d[-1], count - 1, "end", False)):
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
    return extrude(name, circle(d), h)


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
