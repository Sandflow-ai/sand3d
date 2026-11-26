"""Bodies: flesh laid on joints as one smooth surface, skinned to bones, posed.

A body is not carved out of solids: it is the level surface of a field. `stack`, `limb`,
`lobe` and `spindle` are its pieces — a trunk as a stack of stations, a limb swept through
its joints, a skull, a foot — each a field, no mesh; `fuse` joins them by a smooth union,
wide where two pieces should flow into each other (a shoulder, a hip), narrow elsewhere, so
an arm lying against a flank stays an arm; `flesh` makes the surface.

`rig` binds that surface to bones: each vertex follows the bones of the pieces it was made
of, passing from one bone to the next across a `band` at their joint. `posture` turns the
bones and the skin follows; where a posture pushes one part into another, or under the
floor, the skin is pressed back to meet it half-way. `detail` adds a fitted layer of
offsets to the surface at rest: the bones carry it with the rest.

Build a body in a pose where nothing touches but the joints (arms away from the flanks,
legs apart): a surface fused where an arm lies on a flank tears into a web when posed.
"""
import math

import bpy
import numpy as np
from . import _core

#: Custom property holding a body's key in `_BODIES` (what `flesh` kept of it).
KEY = "s3d_body"
_BODIES = {}
#: Grid samples a body may take, and the points of a limb's curve tried against one block of them.
MAX_GRID, BLOCK = 12_000_000, 40_000


# ------------------------------------------------------------------ small tools
def _point(p, verb, what):
    if hasattr(p, "origin"):
        p = p.origin
    try:
        q = tuple(float(c) for c in p)
    except (TypeError, ValueError):
        q = ()
    if len(q) != 3 or not all(math.isfinite(c) for c in q):
        raise ValueError(f"{verb}: {what} is a point (x, y, z), a joint of a skeleton or a frame, not {p!r}")
    return np.array(q)


def _positive(x, verb, what):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x <= 0:
        raise ValueError(f"{verb}: {what} is a positive length, not {x!r}")
    return float(x)


def _rows(rows, verb, what, width, names):
    try:
        out = np.array([[float(c) for c in r] for r in rows], dtype=np.float64)
    except (TypeError, ValueError):
        out = np.empty((0, 0))
    if out.ndim != 2 or out.shape[1] != width or len(out) < 2 or not np.all(np.isfinite(out)):
        raise ValueError(f"{verb}: {what} are at least two rows ({names}), numbers")
    if np.any(np.diff(out[:, 0]) <= 0):
        raise ValueError(f"{verb}: {what} go in order, their first number growing")
    return out


def _name(name, verb):
    if not isinstance(name, str) or not name:
        raise ValueError(f"{verb}: its first argument is the piece's name, a string, not {name!r}")
    return name


def _unit(v):
    return v / np.linalg.norm(v)


def _direction(d, verb, what):
    if isinstance(d, str):
        v = np.zeros(3)
        s = d.replace(" ", "")
        if not s or len(s) % 2:
            s = "?"
        for i in range(0, len(s), 2):
            if s[i] not in "+-" or s[i + 1].lower() not in "xyz":
                raise ValueError(f"{verb}: {what} is a direction, \"+Z\", \"-X+Z\" or (x, y, z), not {d!r}")
            v["xyz".index(s[i + 1].lower())] += 1 if s[i] == "+" else -1
    else:
        v = _point(d, verb, what)
    if np.linalg.norm(v) < 1e-12:
        raise ValueError(f"{verb}: {what} is a direction, not the null vector")
    return _unit(v)


def _pchip(x, y):
    """The monotone cubic through (x, y) (Fritsch–Carlson, as scipy's PchipInterpolator): a function of t."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    h = np.diff(x)
    m = np.diff(y) / h
    n = len(x)
    if n == 2:
        d = np.array([m[0], m[0]])
    else:
        d = np.zeros(n)
        flat = (np.sign(m[1:]) != np.sign(m[:-1])) | (m[1:] == 0) | (m[:-1] == 0)
        w1, w2 = 2 * h[1:] + h[:-1], h[1:] + 2 * h[:-1]
        with np.errstate(divide="ignore", invalid="ignore"):
            mean = (w1 / m[:-1] + w2 / m[1:]) / (w1 + w2)
        d[1:-1] = np.where(flat, 0.0, 1.0 / np.where(flat, 1.0, mean))

        def edge(h0, h1, m0, m1):
            e = ((2 * h0 + h1) * m0 - h0 * m1) / (h0 + h1)
            if np.sign(e) != np.sign(m0):
                return 0.0
            if np.sign(m0) != np.sign(m1) and abs(e) > 3 * abs(m0):
                return 3 * m0
            return e
        d[0], d[-1] = edge(h[0], h[1], m[0], m[1]), edge(h[-1], h[-2], m[-1], m[-2])

    def at(t):
        t = np.asarray(t, float)
        i = np.clip(np.searchsorted(x, t, side="right") - 1, 0, n - 2)
        s = (t - x[i]) / h[i]
        return ((2 * s ** 3 - 3 * s ** 2 + 1) * y[i] + (s ** 3 - 2 * s ** 2 + s) * h[i] * d[i]
                + (-2 * s ** 3 + 3 * s ** 2) * y[i + 1] + (s ** 3 - s ** 2) * h[i] * d[i + 1])
    return at


def _smin(a, b, k):
    """The smooth union of two fields: their minimum, rounded over where they are within k of each other."""
    k = np.maximum(k, 1e-6)
    h = np.maximum(k - np.abs(a - b), 0) / k
    return np.minimum(a, b) - h * h * k / 4


def _smax(a, b, k):
    return -_smin(-a, -b, k)


# ------------------------------------------------------------------ the pieces: fields, no mesh
class Piece:
    """A piece of flesh: a field, negative inside. Made by `stack`, `limb`, `lobe`, `spindle` and `fuse`."""

    def __init__(self, name, value, box, steep=False, parts=()):
        self.name, self._value, self.box, self.steep, self.parts = name, value, box, steep, tuple(parts)

    def __repr__(self):
        return f"<{type(self).__name__} {self.name!r}>"

    def leaves(self):
        if not self.parts:
            return [self]
        return [leaf for p in self.parts for leaf in p.leaves()]


def _pieces(pieces, verb):
    out = []
    for p in pieces:
        if isinstance(p, (list, tuple)):
            out += _pieces(p, verb)
        elif isinstance(p, Piece):
            out.append(p)
        else:
            raise ValueError(f"{verb}: takes pieces of flesh (stack, limb, lobe, spindle, fuse), not {p!r}"
                             + (": a solid is a mesh already — sculpt it, or blend it" if hasattr(p, "data") else ""))
    return out


def stack(name, stations, cap=None):
    """A mass as a stack of sections along Z: rows (z, width, depth, y, n, taper), rounded at both ends.

    The trunk of a body, read off it at a few heights: at each `z` its `width` along X and
    `depth` along Y, the section centred at `y`, a superellipse of exponent `n` (2 an ellipse,
    4 nearly a box), `taper` narrowing its +Y side (as `station`). Between the rows every
    number follows a smooth monotone curve: no ring where a row falls. `cap` rounds the two
    ends over that far (the first and last row's z are where it stops; 14 mm if not given).
    A piece of flesh, no mesh: `fuse` it with others, `flesh` makes the surface."""
    name = _name(name, "stack")
    rows = _rows(stations, "stack", "stations", 6, "z, width, depth, y, n, taper")
    if np.any(rows[:, 1:3] <= 0) or np.any(rows[:, 4] < 1):
        raise ValueError("stack: a station's width and depth are positive, and its n at least 1")
    cap = _core.mm(14.0) if cap is None else _positive(cap, "stack", "cap")
    z0, z1 = rows[0, 0], rows[-1, 0]
    curves = [_pchip(rows[:, 0], rows[:, k]) for k in range(1, 6)]
    thin, least = _core.mm(2.0), _core.mm(1.0)

    def value(X, Y, Z):
        zc = np.clip(Z, z0, z1)
        w, d, yc, n, taper = (c(zc) for c in curves)
        w, d = np.maximum(w, thin), np.maximum(d, thin)
        v = Y - yc
        a = np.maximum(w / 2 * (1 - taper * 2 * np.clip(v, -d / 2, d / 2) / d), least)
        s = (np.abs(X / a) ** n + np.abs(v / (d / 2)) ** n) ** (1 / n)
        f = (s - 1) * np.sqrt(a * d / 2)                 # a smooth scale (a min() kinks where a and d / 2 cross)
        return _smax(_smax(f, z0 - Z, cap), Z - z1, cap)

    half = np.array([rows[:, 1].max() * 0.8, rows[:, 2].max() * 0.8, 0.0])
    y = rows[:, 3]
    box = (np.array([-half[0], y.min() - half[1], z0]), np.array([half[0], y.max() + half[1], z1]))
    return Piece(name, value, box, steep=True)


def _catmull(points, n_per=40):
    """A centripetal Catmull–Rom curve through the points (its ends extended straight)."""
    P = [2 * points[0] - points[1]] + list(points) + [2 * points[-1] - points[-2]]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        t0 = 0.0
        t1 = t0 + math.sqrt(np.linalg.norm(p1 - p0))
        t2 = t1 + math.sqrt(np.linalg.norm(p2 - p1))
        t3 = t2 + math.sqrt(np.linalg.norm(p3 - p2))
        for t in np.linspace(t1, t2, n_per, endpoint=False):
            a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
            a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
            a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
            b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
            b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
            out.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
    out.append(points[-1])
    return np.array(out)


def _resample(C, ds):
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(C, axis=0), axis=1))]
    u = np.arange(0, s[-1], ds)
    return np.stack([np.interp(u, s, C[:, k]) for k in range(3)], 1)


def _frames(C, up):
    """Rotation-minimising frames along C: tangent, x (= y × t), y (as near up as the start allows)."""
    T = np.gradient(C, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    y = up - (up @ T[0]) * T[0]
    Y = [y / np.linalg.norm(y)]
    for i in range(1, len(C)):
        y = Y[-1] - (Y[-1] @ T[i]) * T[i]
        Y.append(y / np.linalg.norm(y))
    Y = np.array(Y)
    return T, np.cross(Y, T), Y


def limb(name, joints, sections, up="+Y"):
    """A limb swept through its joints: rows (distance along it, half-width, half-depth), round at both ends.

    An arm from the shoulder through the elbow and the wrist to the fingers, a leg from the hip
    through the knee to the ankle: one piece along a smooth curve through `joints` (points,
    joints of a `skeleton`, frames), not a tube per bone — no ring at a joint. `sections`
    give its elliptical section at distances along the curve from the first joint, in the
    program's unit: its half-depth toward `up` ("+Y", (x, y, z): carried along the curve
    without twisting), its half-width across. Between rows the section changes linearly;
    before the first and after the last it keeps theirs. A piece of flesh, no mesh."""
    name = _name(name, "limb")
    if not isinstance(joints, (list, tuple)) or len(joints) < 2:
        raise ValueError("limb: joints are the two points or more it runs through, in order")
    pts = [_point(p, "limb", f"joint {i}") for i, p in enumerate(joints)]
    if any(np.linalg.norm(b - a) < _core.mm(1e-3) for a, b in zip(pts, pts[1:])):
        raise ValueError("limb: two joints in a row are the same place")
    rows = _rows(sections, "limb", "sections", 3, "distance along, half-width, half-depth")
    if np.any(rows[:, 1:] <= 0):
        raise ValueError("limb: a section's half-width and half-depth are positive")
    upv = _direction(up, "limb", "up")
    ds = _core.mm(1.0)
    C = _resample(_catmull(pts), ds)
    if abs(upv @ _unit(C[1] - C[0])) > 0.999:
        raise ValueError(f"limb: up {up!r} runs along the limb at its start: give a direction across it")
    T, Xv, Yv = _frames(C, upv)
    reach = rows[:, 1:].max()
    margin = reach + _core.mm(45.0)
    lo, hi = C.min(0) - margin, C.max(0) + margin
    cc = (C * C).sum(1)
    step = 6
    coarse = np.arange(0, len(C), step)

    def value(X, Y, Z):
        shape = X.shape
        P = np.stack([np.ravel(X), np.ravel(Y), np.ravel(Z)], 1)
        out = np.empty(len(P))
        close = np.all((P >= lo) & (P <= hi), axis=1)
        for start in range(0, len(P), BLOCK):
            p = P[start:start + BLOCK]
            near = close[start:start + BLOCK]
            i = np.empty(len(p), dtype=np.int64)
            if near.any():                                            # the nearest point of the curve, exactly
                i[near] = np.argmin(cc[None, :] - 2 * p[near] @ C.T, axis=1)
            if not near.all():                                        # far from it: among a few, then round the best
                q = p[~near]
                j = coarse[np.argmin(cc[None, coarse] - 2 * q @ C[coarse].T, axis=1)]
                cand = np.clip(j[:, None] + np.arange(-step, step + 1)[None, :], 0, len(C) - 1)
                d = cc[cand] - 2 * np.einsum("nj,nkj->nk", q, C[cand])
                i[~near] = cand[np.arange(len(q)), np.argmin(d, axis=1)]
            u = i * ds
            a, b = np.interp(u, rows[:, 0], rows[:, 1]), np.interp(u, rows[:, 0], rows[:, 2])
            off = p - C[i]
            px, py, pt = (off * Xv[i]).sum(1), (off * Yv[i]).sum(1), (off * T[i]).sum(1)
            beyond = np.where((i == 0) | (i == len(C) - 1), np.abs(pt), 0.0)
            rc = np.minimum(a, b)
            out[start:start + BLOCK] = (np.sqrt((px / a) ** 2 + (py / b) ** 2 + (beyond / rc) ** 2) - 1) * rc
        return out.reshape(shape)

    return Piece(name, value, (C.min(0) - reach, C.max(0) + reach), steep=True)


def lobe(name, centre, radii):
    """A rounded mass: an ellipsoid at centre, its radii along X, Y, Z (one number: a ball).

    A skull, a muzzle, the cap of a shoulder round its joint — `centre` a point, a joint of a
    `skeleton` or a frame. A ball centred on a joint turns in place when the joint turns: the
    limb below it moves, the shoulder stays round. A piece of flesh, no mesh."""
    name = _name(name, "lobe")
    c = _point(centre, "lobe", "centre")
    if isinstance(radii, (int, float)) and not isinstance(radii, bool):
        radii = (radii,) * 3
    try:
        r = np.array([_positive(x, "lobe", "a radius") for x in radii])
    except TypeError:
        r = np.empty(0)
    if len(r) != 3:
        raise ValueError(f"lobe: radii are one radius, or three along X, Y, Z, not {radii!r}")

    def value(X, Y, Z):
        q = [(X - c[0]) / r[0], (Y - c[1]) / r[1], (Z - c[2]) / r[2]]
        k0 = np.sqrt(q[0] ** 2 + q[1] ** 2 + q[2] ** 2)
        k1 = np.sqrt((q[0] / r[0]) ** 2 + (q[1] / r[1]) ** 2 + (q[2] / r[2]) ** 2)
        return k0 * (k0 - 1) / np.maximum(k1, 1e-9)

    return Piece(name, value, (c - r, c + r))


def spindle(name, a, b, sections, up="+Z"):
    """A straight tapered piece from a to b: rows (share along, half-width, half-depth, n), round at both ends.

    A foot from the heel to the toes, a hand: its section at shares of the way from `a` to `b`
    (0 at a, 1 at b) — half-depth toward `up`, half-width across, a superellipse of exponent
    `n` — smooth between rows; beyond the first and last it rounds off. A piece of flesh."""
    name = _name(name, "spindle")
    a, b = _point(a, "spindle", "a"), _point(b, "spindle", "b")
    length = np.linalg.norm(b - a)
    if length < _core.mm(1e-3):
        raise ValueError("spindle: a and b are the same place")
    rows = _rows(sections, "spindle", "sections", 4, "share along, half-width, half-depth, n")
    if np.any(rows[:, 1:3] <= 0) or np.any(rows[:, 3] < 1):
        raise ValueError("spindle: a section's half-width and half-depth are positive, and its n at least 1")
    t = (b - a) / length
    upv = _direction(up, "spindle", "up")
    if abs(upv @ t) > 0.999:
        raise ValueError(f"spindle: up {up!r} runs along it: give a direction across it")
    yv = _unit(upv - (upv @ t) * t)
    xv = np.cross(yv, t)
    u = rows[:, 0] * length
    curves = [_pchip(u, rows[:, k]) for k in (1, 2, 3)]

    def value(X, Y, Z):
        P = np.stack([X - a[0], Y - a[1], Z - a[2]], -1)
        s_ax, px, py = P @ t, P @ xv, P @ yv
        ra, rb, n = (c(np.clip(s_ax, u[0], u[-1])) for c in curves)
        beyond = np.where(s_ax < u[0], u[0] - s_ax, np.where(s_ax > u[-1], s_ax - u[-1], 0.0))
        rc = np.minimum(ra, rb)
        s = (np.abs(px / ra) ** n + np.abs(py / rb) ** n) ** (1 / n)
        return (np.sqrt(s ** 2 + (beyond / rc) ** 2) - 1) * rc

    reach = rows[:, 1:3].max()
    ends = np.array([a + u[0] * t, a + u[-1] * t])
    return Piece(name, value, (ends.min(0) - reach, ends.max(0) + reach), steep=True)


def fuse(*pieces, r, wide=None):
    """Pieces joined by a smooth union of radius r; wide=(point, r, near, far): wider round a joint.

    The pieces flow into each other where they meet within `r`: a crease `r` across is
    rounded over, and nothing else moves — pieces further apart than `r` stay apart, an arm
    beside a flank stays an arm. Round a joint the flesh should flow wider: `wide=(joint, r2,
    near, far)` makes the radius `r2` within `near` of that point, falling back to `r` at
    `far`: `fuse(body, arm, r=3, wide=(bones.shoulder, 14, 37, 67))`. Several pieces are joined
    in the order given. The result is a piece: fuse it further, or `flesh` it."""
    parts = _pieces(pieces, "fuse")
    if len(parts) < 2:
        raise ValueError("fuse: takes two pieces or more")
    r = _positive(r, "fuse", "r")
    if wide is not None:
        if not isinstance(wide, (list, tuple)) or len(wide) != 4:
            raise ValueError("fuse: wide is (point, r, near, far): the radius r within near of the point, back to "
                             "the plain r at far")
        centre = _point(wide[0], "fuse", "wide's point")
        r2, near, far = (_positive(x, "fuse", f"wide's {w}") for x, w in zip(wide[1:], ("r", "near", "far")))
        if far <= near:
            raise ValueError("fuse: wide's far is beyond its near")

    def value(X, Y, Z, fields=None):
        vals = fields if fields is not None else [p._value(X, Y, Z) for p in parts]
        k = r
        if wide is not None:
            d = np.sqrt((X - centre[0]) ** 2 + (Y - centre[1]) ** 2 + (Z - centre[2]) ** 2)
            k = r + (r2 - r) * np.clip(1 - (d - near) / (far - near), 0, 1)
        out = vals[0]
        for v in vals[1:]:
            out = _smin(out, v, k)
        return out

    box = (np.min([p.box[0] for p in parts], 0), np.max([p.box[1] for p in parts], 0))
    return Piece("+".join(p.name for p in parts), value, box, parts=parts)


# ------------------------------------------------------------------ the surface
class _Grid:
    """A piece's field kept on the part of the body's grid where it matters; `far` elsewhere."""

    def __init__(self, axes, f, keep, far, box=None):
        inside = np.argwhere(f < keep)
        lo, hi = inside.min(0), inside.max(0) + 1
        if box is not None:                            # never beyond the piece's own box (and keep round it)
            b0 = [np.searchsorted(axes[k], box[0][k] - keep, side="right") - 1 for k in range(3)]
            b1 = [np.searchsorted(axes[k], box[1][k] + keep, side="left") + 1 for k in range(3)]
            lo = np.maximum(lo, np.maximum(b0, 0))
            hi = np.maximum(np.minimum(hi, b1), lo + 2)
        self.lo = np.array([axes[k][lo[k]] for k in range(3)])
        self.h = float(axes[0][1] - axes[0][0])
        self.f = np.ascontiguousarray(f[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]], dtype=np.float32)
        self.far = far

    def __call__(self, P):
        """The field at points P (n, 3), trilinear; `far` outside what was kept."""
        g = (P - self.lo) / self.h
        n = np.array(self.f.shape)
        ok = np.all((g >= 0) & (g <= n - 1), axis=1)
        out = np.full(len(P), self.far)
        g = g[ok]
        i = np.minimum(np.floor(g).astype(np.int64), n - 2)
        t = g - i
        f = self.f
        acc = np.zeros(len(g))
        for dx in (0, 1):
            for dy in (0, 1):
                for dz in (0, 1):
                    w = ((t[:, 0] if dx else 1 - t[:, 0]) * (t[:, 1] if dy else 1 - t[:, 1])
                         * (t[:, 2] if dz else 1 - t[:, 2]))
                    acc += w * f[i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz]
        out[ok] = acc
        return out


class _Body:
    def __init__(self):
        self.axes = self.pieces = self.base = self.rest = self.faces = self.graph = self.rig = None
        self.true = {}


class _Graph:
    """The mesh's vertices and their neighbours: averages over them, without a sparse matrix."""

    def __init__(self, faces, n):
        e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
        key = np.unique(np.concatenate([e[:, 0] * n + e[:, 1], e[:, 1] * n + e[:, 0]]))
        self.n, self.src, self.dst = n, key // n, key % n
        self.deg = np.maximum(np.bincount(self.src, minlength=n), 1).astype(np.float64)
        self.d2 = self.edge = 1.0

    def measure(self, v):
        """Read the mesh's grain on positions v: smoothing is asked for in lengths, not in passes."""
        d = np.linalg.norm(v[self.src] - v[self.dst], axis=1)
        self.edge = float(d.mean())
        self.d2 = float((np.bincount(self.src, weights=d * d, minlength=self.n) / self.deg).mean())

    def passes(self, sigma):
        """How many passes of `x ← (x + its neighbours' mean) / 2` spread x over about sigma."""
        return max(1, round(2 * sigma * sigma / self.d2))

    def rings(self, distance):
        return max(1, round(distance / self.edge))

    def total(self, x):
        """Each vertex's sum of x over its neighbours (x per vertex, one column or several)."""
        if x.ndim == 1:
            return np.bincount(self.src, weights=x[self.dst], minlength=self.n)
        return np.stack([np.bincount(self.src, weights=x[self.dst, k], minlength=self.n) for k in range(x.shape[1])], 1)

    def mean(self, x):
        return self.total(x) / (self.deg if x.ndim == 1 else self.deg[:, None])

    def within(self, mask):
        """The same, for the vertices of mask only: (their indices, a function x → their neighbours' mean)."""
        rows = np.flatnonzero(mask)
        slot = np.full(self.n, -1)
        slot[rows] = np.arange(len(rows))
        keep = mask[self.src]
        src, dst = slot[self.src[keep]], self.dst[keep]
        deg = self.deg[rows]

        starts = np.flatnonzero(np.r_[True, np.diff(src) > 0])            # src is sorted: one run per row

        def mean(x):
            return np.add.reduceat(x[dst], starts, axis=0) / deg[:, None]
        return rows, mean


def _blur(f, sigma):
    """A Gaussian blur of sigma grid steps, the field mirrored at its edges (as scipy's gaussian_filter)."""
    radius = int(4.0 * sigma + 0.5)
    x = np.arange(-radius, radius + 1)
    k = np.exp(-0.5 * (x / sigma) ** 2)
    k /= k.sum()
    for axis in range(3):
        pad = [(0, 0)] * 3
        pad[axis] = (radius, radius)
        g = np.pad(f, pad, mode="symmetric")
        out = np.zeros_like(f)
        n = f.shape[axis]
        for j, w in enumerate(k):
            sl = [slice(None)] * 3
            sl[axis] = slice(j, j + n)
            out += w * g[tuple(sl)]
        f = out
    return f


#: How the commonest sign patterns of a cube's corners are cut into triangles by Lewiner et al.'s marching cubes
#: tables (those scikit-image uses), read off a surface it made: pattern -> triangles, three cube edges each, an
#: edge a hex digit (its index among the cube's twelve, corners numbered x + 2 y + 4 z, edges by lower then upper
#: corner). Only patterns with no ambiguous face: the surface's lines on the cube's faces are then the same
#: whatever the table, and only the diagonals inside a polygon are a choice. A body's mesh is the same, vertex for
#: vertex and edge for edge, as one made with those tables: its skin weights are smoothed along its edges.
_AS_LEWINER = {
    1: "012", 2: "043", 3: "124143", 4: "156", 5: "052256", 7: "246354456", 8: "375", 10: "047075", 11: "127175247",
    12: "136376", 13: "032237276", 14: "046061476", 15: "246476", 16: "298", 17: "019098", 19: "193394498",
    21: "058569598", 23: "354458568698", 31: "469476498", 32: "48a", 34: "08338a", 35: "12818a1a3", 42: "08558778a",
    43: "12717528a2a7", 47: "27628778a", 48: "29a2a4", 49: "01a0a419a", 50: "02329339a", 51: "19a1a3",
    55: "35939a569", 59: "17519a1a7", 63: "69779a", 64: "6b9", 68: "15b1b9", 69: "05b0b22b9", 76: "13937b3b9",
    77: "03909237b3b9", 79: "24727b2b9", 80: "2686b8", 81: "01606b0b8", 84: "1581825b8", 85: "05b0b8",
    87: "3544585b8", 93: "03b0b837b", 95: "47b4b8", 112: "26446a6ba", 113: "01416a1a46ba", 115: "16a1a36ba",
    117: "05b0a40ba", 119: "35a5ba", 127: "7ba", 128: "7ab", 136: "3a55ab", 138: "04a0ab0b5", 140: "13a1a66ab",
    142: "04114a1a66ab", 143: "2464a66ab", 160: "48b4b7", 162: "08b0b33b7", 168: "34548558b", 170: "08b0b5",
    171: "12818558b", 174: "06108b0b6", 175: "28668b", 176: "27429b2b7", 178: "02909339b3b7", 179: "19339b3b7",
    186: "02b0b529b", 187: "19b1b5", 191: "69b", 192: "6797a9", 196: "15717a1a9", 200: "3953a9596", 204: "13a1a9",
    205: "0322393a9", 206: "04a0a11a9", 207: "24a2a9", 208: "2672787a8", 212: "15717227a2a8", 213: "0585787a8",
    220: "13a1821a8", 221: "0383a8", 223: "4a8", 224: "467489496", 232: "345485586689", 234: "085589596",
    236: "139349489", 238: "089091", 239: "289", 240: "264467", 241: "016064467", 242: "023267273", 243: "163367",
    244: "157172274", 245: "057074", 247: "357", 248: "264345465", 250: "025265", 251: "165", 252: "134142",
    253: "034", 254: "021",
}


def _cube_cases():
    """Marching cubes' cases, derived: for each of the 256 sign patterns of a cube's corners, its triangles as
    triples of cube edges. On each face the surface's segments join the crossed edges (a face crossed four times
    cuts off its inside corners, each alone: the two cubes sharing the face agree, so the surface is closed); the
    segments chain into loops, each loop a fan of triangles, facing from inside to outside."""
    corner = np.array([[c & 1, (c >> 1) & 1, (c >> 2) & 1] for c in range(8)], dtype=float)
    edges = [(a, b) for a in range(8) for b in range(a + 1, 8) if bin(a ^ b).count("1") == 1]
    edge_id = {e: i for i, e in enumerate(edges)}
    faces = []
    for d in range(3):
        u, w = [k for k in range(3) if k != d]
        for side in (0, 1):
            ring = [(0, 0), (1, 0), (1, 1), (0, 1)]
            faces.append([sum(((side if k == d else (a if k == u else b)) << k) for k in range(3)) for a, b in ring])
    table = []
    for mask in range(256):
        inside = [(mask >> c) & 1 for c in range(8)]
        link = {}
        for ring in faces:
            cut = [k for k in range(4) if inside[ring[k]] != inside[ring[(k + 1) % 4]]]
            ids = [edge_id[tuple(sorted((ring[k], ring[(k + 1) % 4])))] for k in cut]
            if len(ids) == 2:
                pairs = [(ids[0], ids[1])]
            elif len(ids) == 4:                         # corners alternate: cut off each inside corner
                first = 0 if inside[ring[1]] else 1     # edges k and k + 1 meet at corner k + 1
                pairs = [(ids[first], ids[first + 1]), (ids[(first + 2) % 4], ids[(first + 3) % 4])]
            else:
                pairs = []
            for a, b in pairs:
                link.setdefault(a, []).append(b)
                link.setdefault(b, []).append(a)
        mid = {i: (corner[a] + corner[b]) / 2 for (a, b), i in edge_id.items()}
        tris, seen = [], set()
        for start in sorted(link):
            if start in seen:
                continue
            loop, prev, cur = [start], None, start
            while True:
                seen.add(cur)
                nxt = [x for x in link[cur] if x != prev] or link[cur]
                nxt = nxt[0] if nxt[0] != prev or len(link[cur]) < 2 else nxt[-1]
                if nxt == start:
                    break
                prev, cur = cur, nxt
                loop.append(cur)
            pts = np.array([mid[i] for i in loop])
            normal = sum(np.cross(pts[k], pts[(k + 1) % len(pts)]) for k in range(len(pts)))
            out = 0.0
            for i in loop:
                a, b = edges[i]
                out += normal @ ((corner[b] - corner[a]) * (1 if inside[a] else -1))
            if out < 0:
                loop = loop[::-1]
            tris += [(loop[0], loop[k], loop[k + 1]) for k in range(1, len(loop) - 1)]
        if mask in _AS_LEWINER:
            digits = [int(c, 16) for c in _AS_LEWINER[mask]]
            given = [tuple(digits[k:k + 3]) for k in range(0, len(digits), 3)]
            if sorted(e for t in given for e in t) != sorted(e for t in tris for e in t) and \
                    {e for t in given for e in t} != {e for t in tris for e in t}:
                raise AssertionError(f"marching cubes: pattern {mask} of the table does not cut the cube's edges")
            tris = given
        table.append(tris)
    most = max(len(t) for t in table)
    count = np.array([len(t) for t in table])
    tri = np.zeros((256, most, 3), dtype=np.int64)
    for m, t in enumerate(table):
        if t:
            tri[m, :len(t)] = t
    return np.array(edges), count, tri


_EDGES, _COUNT, _TRI = _cube_cases()


def _surface(f, axes):
    """The zero surface of field f on the grid (marching cubes): vertices where the grid's edges cross it, the
    largest closed piece, facing out."""
    nx, ny, nz = f.shape
    inside = f < 0
    mask = np.zeros((nx - 1, ny - 1, nz - 1), dtype=np.uint8)
    for c in range(8):
        dx, dy, dz = c & 1, (c >> 1) & 1, (c >> 2) & 1
        mask |= inside[dx:nx - 1 + dx, dy:ny - 1 + dy, dz:nz - 1 + dz].astype(np.uint8) << np.uint8(c)
    cells = np.argwhere((mask != 0) & (mask != 255))
    case = mask[cells[:, 0], cells[:, 1], cells[:, 2]]
    node = lambda ijk: (ijk[:, 0] * ny + ijk[:, 1]) * nz + ijk[:, 2]
    off = np.array([[c & 1, (c >> 1) & 1, (c >> 2) & 1] for c in range(8)])
    axis = np.array([int(np.log2(a ^ b)) for a, b in _EDGES])
    keys = []
    for t in range(_TRI.shape[1]):
        k = np.flatnonzero(_COUNT[case] > t)
        e = _TRI[case[k], t]                                         # (cells, 3) cube edges
        base = node((cells[k][:, None, :] + off[_EDGES[e, 0]]).reshape(-1, 3)).reshape(-1, 3)
        keys.append(base * 3 + axis[e])                              # a grid edge: its lower node and its axis
    keys = np.concatenate(keys)
    used, inv = np.unique(keys, return_inverse=True)
    faces = inv.reshape(-1, 3)
    a, ax = used // 3, used % 3
    step = np.array([ny * nz, nz, 1])[ax]
    fa, fb = f.ravel()[a], f.ravel()[a + step]
    t = fa / (fa - fb)
    ijk = np.stack([a // (ny * nz), a // nz % ny, a % nz], 1).astype(np.float64)
    ijk[np.arange(len(a)), ax] += t
    h = float(axes[0][1] - axes[0][0])
    v = np.array([axes[k][0] for k in range(3)]) + ijk * h
    faces = faces[(faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])]
    # the largest connected piece
    label = np.arange(len(v))
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    while True:
        low = np.minimum(label[e[:, 0]], label[e[:, 1]])
        new = label.copy()
        np.minimum.at(new, e[:, 0], low)
        np.minimum.at(new, e[:, 1], low)
        new = new[new]
        if np.array_equal(new, label):
            break
        label = new
    big = np.bincount(label).argmax()
    faces = faces[label[faces[:, 0]] == big]
    keep = np.unique(faces)
    remap = np.full(len(v), -1)
    remap[keep] = np.arange(len(keep))
    v, faces = v[keep], remap[faces]
    if np.einsum("ij,ij->i", v[faces[:, 0]], np.cross(v[faces[:, 1]], v[faces[:, 2]])).sum() < 0:
        faces = faces[:, ::-1]
    return v, faces


def _body(ob, verb):
    key = ob.get(KEY) if hasattr(ob, "get") and hasattr(ob, "data") else None
    if key is None or key not in _BODIES:
        raise ValueError(f"{verb}: takes a body made by flesh, not {ob!r}")
    return _BODIES[key]


def flesh(name, *pieces, cell=None, soften=None, box=None, crisp=None):
    """The surface of fused pieces: one closed smooth mesh, cell its grain, soften its smoothing.

    The body's surface where the pieces' field crosses zero, on a grid of `cell` (1.5 mm if
    not given): detail under two or three cells is lost. `soften` blurs the field that far
    before the surface is taken (2 mm if not given): the last creases between pieces go,
    and so does anything that fine. Several pieces are fused with r = 3 mm; `fuse` them
    yourself to choose. `box=((x0, y0, z0), (x1, y1, z1))` fixes the grid's extent (else the
    pieces' own, with a margin). `crisp=[(point, near, far), ...]` leaves the field as it is
    within `near` of a point, softened in full only from `far` on: fingers a few cells apart
    stay apart, where the softening would close the gaps between them. The faces are named `flesh`; the mesh is in the pieces'
    own coordinates. `rig` skins it, `posture` moves it, `detail` adds a fitted layer."""
    name = _name(name, "flesh")
    parts = _pieces(pieces, "flesh")
    if not parts:
        raise ValueError("flesh: takes the pieces to make flesh of: stack, limb, lobe, spindle, fuse")
    whole = parts[0] if len(parts) == 1 else fuse(*parts, r=_core.mm(3.0))
    leaves = whole.leaves()
    names = [p.name for p in leaves]
    if len(set(names)) != len(names):
        twice = sorted({n for n in names if names.count(n) > 1})
        raise ValueError(f"flesh: two pieces are named {twice[0]!r}: rig tells them apart by name")
    cell = _core.mm(1.5) if cell is None else _positive(cell, "flesh", "cell")
    soften = _core.mm(2.0) if soften is None else (0.0 if soften == 0 else _positive(soften, "flesh", "soften"))
    if box is None:
        margin = 6 * cell + 2 * soften
        lo, hi = whole.box[0] - margin, whole.box[1] + margin
    else:
        try:
            lo, hi = _point(box[0], "flesh", "box's first corner"), _point(box[1], "flesh", "box's second corner")
        except (TypeError, IndexError):
            raise ValueError("flesh: box is ((x0, y0, z0), (x1, y1, z1)), the grid's two corners") from None
        if np.any(hi - lo < 4 * cell):
            raise ValueError("flesh: box is too small for the cell: four cells at least each way")
    axes = [np.arange(lo[k], hi[k] + cell / 2, cell) for k in range(3)]
    if math.prod(len(a) for a in axes) > MAX_GRID:
        raise ValueError(f"flesh: a cell of {cell:g} over {tuple(np.round(hi - lo, 1))} takes "
                         f"{math.prod(len(a) for a in axes):,} grid samples, more than {MAX_GRID:,}: give a larger cell")
    X, Y, Z = np.meshgrid(*axes, indexing="ij")
    fields = {}

    def evaluate(p):
        if p.parts:
            return p._value(X, Y, Z, fields=[evaluate(q) for q in p.parts])
        f = p._value(X, Y, Z)
        if p.steep:                                    # made a distance, to first order: f / |grad f|
            g = np.gradient(f, cell)
            g = np.sqrt(g[0] ** 2 + g[1] ** 2 + g[2] ** 2)
            # far from a limb its field jumps where the nearest point of its curve changes: there the difference is
            # no slope, and dividing by it would bring a far point near the piece (a hand's piece claiming a foot)
            f = f / np.where(g > 4.0, 1.0, np.maximum(g, 1e-3))
        fields[p.name] = f.astype(np.float32)
        return fields[p.name]

    f = np.asarray(evaluate(whole), dtype=np.float64)
    spots = []
    for spot in crisp or []:
        if not isinstance(spot, (list, tuple)) or len(spot) != 3:
            raise ValueError("flesh: crisp is [(point, near, far), ...]: no softening within near of the point, all "
                             "of it from far on")
        centre = _point(spot[0], "flesh", "a crisp point")
        near, far = _positive(spot[1], "flesh", "crisp's near"), _positive(spot[2], "flesh", "crisp's far")
        if far <= near:
            raise ValueError("flesh: crisp's far is beyond its near")
        spots.append((centre, near, far))
    if soften:
        soft = _blur(f, soften / cell)
        if spots:
            keep = np.zeros(f.shape)
            for centre, near, far in spots:
                d = np.sqrt((X - centre[0]) ** 2 + (Y - centre[1]) ** 2 + (Z - centre[2]) ** 2)
                t = np.clip((far - d) / (far - near), 0, 1)
                keep = np.maximum(keep, t * t * (3 - 2 * t))
            soft += keep * (f - soft)
        f = soft
    del X, Y, Z
    if not (f < 0).any():
        raise ValueError("flesh: the pieces are thinner than the grid: nothing is inside — give a smaller cell")
    edge = np.concatenate([f[[0, -1]].ravel(), f[:, [0, -1]].ravel(), f[:, :, [0, -1]].ravel()])
    if (edge < 0).any():
        raise ValueError("flesh: the pieces reach beyond the box: give a larger one")
    verts, faces = _surface(f, axes)
    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(len(verts))
    mesh.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    mesh.loops.add(faces.size)
    mesh.loops.foreach_set("vertex_index", faces.astype(np.int32).ravel())
    mesh.polygons.add(len(faces))
    mesh.polygons.foreach_set("loop_start", np.arange(len(faces), dtype=np.int32) * 3)
    mesh.polygons.foreach_set("loop_total", np.full(len(faces), 3, dtype=np.int32))
    mesh.polygons.foreach_set("use_smooth", np.ones(len(faces), dtype=bool))
    mesh.update()
    sharp = mesh.attributes.get("sharp_face")            # bpy versions differ in whether an all-smooth mesh has it
    if sharp is not None:
        mesh.attributes.remove(sharp)
    for tag in ("flesh", f"{name}.flesh"):
        attr = mesh.attributes.new(_core.FACE_TAG + tag, "BOOLEAN", "FACE")
        attr.data.foreach_set("value", np.ones(len(faces), dtype=bool))
    ob = _core.link(bpy.data.objects.new(name, mesh))
    ob[_core.NAME] = name
    body = _Body()
    body.axes = axes
    far = _core.mm(50.0)
    boxes = {p.name: p.box for p in leaves}
    body.pieces = {k: _Grid(axes, g, _core.mm(30.0), far, boxes[k]) for k, g in fields.items()}
    body.base = verts.astype(np.float32).astype(np.float64)   # the flesh as made (as the mesh holds it): what rig weighs
    body.rest = body.base.copy()                              # with its detail: what posture moves
    body.faces = faces.astype(np.int64)
    body.graph = _Graph(body.faces, len(body.rest))
    body.graph.measure(body.base)
    key = max(_BODIES, default=0) + 1
    _BODIES[key] = body
    ob[KEY] = key
    return ob


# ------------------------------------------------------------------ bones and skin
class Band:
    """Where the skin passes from one bone of a chain to the next. Made by `band`."""

    def __init__(self, bone, lo, hi, normal, carry, twist):
        self.bone, self.lo, self.hi, self.normal, self.carry, self.twist = bone, lo, hi, normal, carry, twist


class Chain:
    """The bones a group of pieces follows, in order. Made by `chain`."""

    def __init__(self, pieces, first, bands, whole, share):
        self.pieces, self.first, self.bands, self.whole, self.share = pieces, first, bands, whole, share

    @property
    def bones(self):
        return [self.first] + [b.bone for b in self.bands]


def band(bone, lo, hi, normal=None, carry=(0, 1), twist=None):
    """In a chain: the skin passes to bone between lo and hi of its joint, measured along the limb.

    The skin of a chain follows the bone before up to `lo` and `bone` from `hi` on, shared
    smoothly between: distances from `bone`'s head joint, along `normal` — by default the
    direction halfway between the bone before and this one (the first band of a chain:
    this bone's own direction), so the band lies square across the joint. `band("forearm",
    -12, 12)` passes at the elbow over 24 mm; `band("upperarm", -48, -14)` gives the whole
    shoulder to the arm. For a trunk give `normal="+Z"`: the bands are heights.

    `carry=(a, b)`: the stretch of the chain's first piece that `bone` holds against the
    other parts when a posture presses them together, in shares of the bone's length (a hand
    whose fingers reach past its bone's end: (0, 1.4); a thigh, clear of the hip: (0.2, 1)).
    `twist=(bone2, a, b)`: `bone2` — a bone with the same joints — follows this one without
    its twist about its own axis, and the skin passes from it to `bone` between shares a
    and b of the length: a thigh turned out does not wring the hip."""
    if not isinstance(bone, str):
        raise ValueError(f"band: its first argument is the bone's name, not {bone!r}")
    for x, what in ((lo, "lo"), (hi, "hi")):
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
            raise ValueError(f"band: {what} is a distance from the bone's joint, not {x!r}")
    if hi <= lo:
        raise ValueError(f"band: hi ({hi:g}) is beyond lo ({lo:g})")
    n = None if normal is None else _direction(normal, "band", "normal")
    if carry is not None and (not isinstance(carry, (list, tuple)) or len(carry) != 2 or carry[1] <= carry[0]):
        raise ValueError(f"band: carry is (a, b), two shares of the bone's length in order, or None, not {carry!r}")
    if twist is not None and (not isinstance(twist, (list, tuple)) or len(twist) != 3 or not isinstance(twist[0], str)
                              or twist[2] <= twist[1]):
        raise ValueError(f"band: twist is (bone, a, b): the bone without the twist, and two shares in order, not {twist!r}")
    return Band(bone, float(lo), float(hi), n, None if carry is None else (float(carry[0]), float(carry[1])), twist)


def chain(pieces, first, *bands, whole=None, share=None):
    """The bones a group of pieces follows: the first, then a band for each next one.

    `chain(["arm", "cap"], "clavicle", band("upperarm", -48, -14), band("forearm", -12, 12),
    band("hand", -9, 9))`: the skin of the pieces named — a vertex belongs to the pieces it
    lies on — follows `first` up to the first band, then each band's bone in turn. A group
    with one bone has no band: `chain(["cranium", "muzzle"], "head")`.

    `whole={piece: bone}`: a piece held entire by one bone when parts press together (a
    shoulder's cap by the upper arm, a foot by its bone); the first piece is held in
    stretches, by each band's `carry`. `share=[(bone, of, joint, amount, near, far)]`:
    `bone` takes `amount` of `of`'s skin within `near` of the joint, none beyond `far` — a
    clavicle lifting the trunk's skin round its shoulder."""
    if isinstance(pieces, str):
        pieces = [pieces]
    if not isinstance(pieces, (list, tuple)) or not pieces or not all(isinstance(p, str) for p in pieces):
        raise ValueError("chain: its first argument is the names of the pieces that follow these bones")
    if not isinstance(first, str):
        raise ValueError(f"chain: its second argument is the first bone's name, not {first!r}")
    if not all(isinstance(b, Band) for b in bands):
        raise ValueError("chain: after the first bone come bands, band(bone, lo, hi)")
    whole = dict(whole or {})
    share = [tuple(x) for x in (share or [])]
    for x in share:
        if len(x) != 6:
            raise ValueError("chain: a share is (bone, of, joint, amount, near, far)")
    return Chain(list(pieces), first, list(bands), whole, share)


def _smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def _normals(v, f):
    fn = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    nv = np.zeros_like(v)
    for k in range(3):
        nv[:, 0] += np.bincount(f[:, k], weights=fn[:, 0], minlength=len(v))
        nv[:, 1] += np.bincount(f[:, k], weights=fn[:, 1], minlength=len(v))
        nv[:, 2] += np.bincount(f[:, k], weights=fn[:, 2], minlength=len(v))
    return nv / np.maximum(np.linalg.norm(nv, axis=1, keepdims=True), 1e-12)


class _Rig:
    pass


def rig(ob, joints, bones, *chains, linear=None, smooth=None, seam=None):
    """Bind a body to bones: bones={name: (joint, joint, parent)}, then a chain for each group of pieces.

    `joints` are a `skeleton`'s; each bone runs from its first joint to its second and hangs
    on `parent` (None for the root, first in the list; parents before their children). Every
    piece of the body is in one chain: a vertex follows the chains of the pieces it lies on,
    and within a chain the bone its `band`s give it. The weights are then smoothed over the
    surface, over about `smooth` (3.5 mm if not given).

    `linear=[(bones, bones)]`: where the skin is shared between the two sets (a trunk's bones
    and an arm's: the armpit, the front and back of the shoulder) it is blended linearly —
    it stretches across as an armpit's skin does — instead of with dual quaternions, which
    keep volume everywhere else but swing such a seam out into a ball when the arm rises;
    its weights are smoothed further, over about `seam[0]`, within `seam[1]` of it ((22, 36.5)
    mm if not given).
    Nothing moves: `posture` does. Returns the body."""
    body = _body(ob, "rig")
    if not isinstance(bones, dict) or not bones:
        raise ValueError("rig: bones are {name: (joint, joint, parent)}, the root first with parent None")
    names = list(bones)
    index = {n: i for i, n in enumerate(names)}
    heads, tails, parent = [], [], []
    for n, spec in bones.items():
        if not isinstance(spec, (list, tuple)) or len(spec) != 3:
            raise ValueError(f"rig: bone {n!r} is (joint, joint, parent), not {spec!r}")
        for j in spec[:2]:
            if j not in joints:
                raise ValueError(f"rig: bone {n!r} runs to a joint {j!r} the skeleton does not have; joints: "
                                 f"{', '.join(sorted(joints))}")
        if spec[2] is not None and (spec[2] not in index or index[spec[2]] >= index[n]):
            raise ValueError(f"rig: bone {n!r} hangs on {spec[2]!r}, which must be a bone listed before it")
        heads.append(_point(joints[spec[0]], "rig", f"joint {spec[0]!r}"))
        tails.append(_point(joints[spec[1]], "rig", f"joint {spec[1]!r}"))
        parent.append(-1 if spec[2] is None else index[spec[2]])
    if parent[0] != -1 or parent.count(-1) != 1:
        raise ValueError("rig: one bone is the root, the first, with parent None")
    heads, tails = np.array(heads), np.array(tails)
    if not chains or not all(isinstance(c, Chain) for c in chains):
        raise ValueError("rig: after the bones come chains, chain(pieces, first bone, band(...), ...)")
    known = set(body.pieces)
    claimed = [p for c in chains for p in c.pieces]
    for p in claimed:
        if p not in known:
            raise ValueError(f"rig: a chain names a piece {p!r} the body does not have; pieces: {', '.join(sorted(known))}")
    if len(set(claimed)) != len(claimed) or set(claimed) != known:
        missing = sorted(known - set(claimed))
        raise ValueError("rig: every piece is in one chain" + (f"; not in any: {', '.join(missing)}" if missing else
                                                               "; one is in two"))

    def bone(n, where):
        if n not in index:
            raise ValueError(f"rig: {where} names a bone {n!r} that is not one; bones: {', '.join(names)}")
        return index[n]

    v, f, graph = body.base, body.faces, body.graph
    nv = _normals(v, f)
    eps, scale = _core.mm(0.5), _core.mm(2.5)
    dist, facing = {}, {}
    for k, grid in body.pieces.items():
        dist[k] = grid(v)
        gr = np.stack([grid(v + e) - grid(v - e) for e in np.eye(3) * eps], 1)
        gr /= np.maximum(np.linalg.norm(gr, axis=1, keepdims=True), 1e-9)
        facing[k] = np.clip(np.einsum("ij,ij->i", nv, gr), 0, 1)
    memb = [np.max([np.exp(-np.maximum(dist[p], 0) / scale) * facing[p] ** 2 for p in c.pieces], 0) for c in chains]
    tot = sum(memb)
    near = np.argmin([np.min([dist[p] for p in c.pieces], 0) for c in chains], 0)
    memb = [np.where(tot > 1e-6, m / np.maximum(tot, 1e-12), (near == i).astype(float)) for i, m in enumerate(memb)]
    W = np.zeros((len(v), len(names)))
    twists, proxies = [], []
    for c, m in zip(chains, memb):
        ids = [bone(n, "a chain") for n in c.bones]
        cuts = []
        for k, b in enumerate(c.bands):
            i = ids[k + 1]
            d = _unit(tails[i] - heads[i])
            if b.normal is not None:
                n = b.normal
            elif k == 0:
                n = d
            else:
                n = _unit(_unit(tails[ids[k]] - heads[ids[k]]) + d)
            cuts.append(_smoothstep(b.lo, b.hi, (v - heads[i]) @ n))
        w = {}
        run = np.ones(len(v))
        for k, i in enumerate(ids):
            w[i] = run * (1 - cuts[k]) if k < len(cuts) else run
            if k < len(cuts):
                run = run * cuts[k]
        for (to, of, joint, amount, lo, hi) in c.share:
            a, b = bone(to, "a share"), bone(of, "a share")
            if b not in w:
                raise ValueError(f"rig: a share takes from {of!r}, which is not a bone of that chain")
            take = amount * _smoothstep(hi, lo, np.linalg.norm(v - _point(joint, "rig", "a share's joint"), axis=1))
            w[a] = w.get(a, 0) + take * w[b]
            w[b] = w[b] * (1 - take)
        for k, b in enumerate(c.bands):
            if b.twist is not None:
                i, j = ids[k + 1], bone(b.twist[0], "a twist")
                tw = _smoothstep(b.twist[1], b.twist[2], (v - heads[i]) @ _unit(tails[i] - heads[i])
                                 / np.linalg.norm(tails[i] - heads[i]))
                w[j] = w.get(j, 0) + w[i] * (1 - tw)
                w[i] = w[i] * tw
                twists.append((i, j))
        for i, x in w.items():
            W[:, i] += m * x
        # what each bone holds of the chain's pieces when parts press together (posture)
        main = c.pieces[0]
        if c.bands and all(b.normal is not None for b in c.bands):      # a trunk: stretches between the joints
            for k, i in enumerate(ids):
                n = c.bands[min(k, len(c.bands) - 1)].normal
                lo = -np.inf if k == 0 else heads[i] @ n
                hi = np.inf if k == len(ids) - 1 else heads[ids[k + 1]] @ n
                proxies.append((main, i, ("along", n, lo, hi)))
        elif c.bands:
            for k, b in enumerate(c.bands):
                if b.carry is not None and main not in c.whole:
                    proxies.append((main, ids[k + 1], ("share",) + b.carry))
        elif main not in c.whole:
            proxies.append((main, ids[0], None))
        for p, n in c.whole.items():
            if p not in c.pieces:
                raise ValueError(f"rig: whole names a piece {p!r} that is not in its chain")
            proxies.append((p, bone(n, "whole"), None))
        for p in c.pieces[1:]:
            if p not in c.whole:
                proxies.append((p, ids[-1], None))
    smooth = _core.mm(3.467) if smooth is None else _positive(smooth, "rig", "smooth")
    if seam is None:
        seam = (_core.mm(21.93), _core.mm(36.53))
    elif not isinstance(seam, (list, tuple)) or len(seam) != 2:
        raise ValueError("rig: seam is (distance its weights are smoothed over, how far from it), two lengths")
    for _ in range(graph.passes(smooth)):
        W = 0.5 * W + 0.5 * graph.mean(W)

    def top4(W):
        order = np.argsort(-W, 1)[:, :4]
        w4 = np.take_along_axis(W, order, 1)
        return order, w4 / np.maximum(w4.sum(1, keepdims=True), 1e-12)

    def seams(order, w4):
        """How much each vertex is shared between the two sets of a `linear` pair."""
        Wn = np.zeros_like(W)
        np.put_along_axis(Wn, order, w4, 1)
        lin = np.zeros(len(v))
        for a, b in pairs:
            lin = np.maximum(lin, np.minimum(Wn[:, a].sum(1), Wn[:, b].sum(1)))
        lin = np.clip(5 * lin, 0, 1)
        for _ in range(graph.passes(_core.mm(1.899))):
            lin = 0.5 * lin + 0.5 * graph.mean(lin)
        return lin

    pairs = []
    for pair in linear or []:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError("rig: linear is [(bones, bones)]: two sets of bone names whose shared skin is blended linearly")
        pairs.append(tuple([bone(n, "linear") for n in ([side] if isinstance(side, str) else side)] for side in pair))
    order, w4 = top4(W)
    lin = seams(order, w4)
    if pairs:
        # that seam opens wide when the limb rises: its weights smoothed further, or their noise shows as streaks
        zone = (lin > 0.02).astype(float)
        for _ in range(graph.rings(_positive(seam[1], "rig", "seam's reach"))):
            zone = np.maximum(zone, graph.mean(zone))
        rows, mean = graph.within(zone > 0)
        for _ in range(graph.passes(_positive(seam[0], "rig", "seam's smoothing"))):
            W[rows] = 0.5 * W[rows] + 0.5 * mean(W)
        order, w4 = top4(W)
        lin = seams(order, w4)
    r = _Rig()
    r.names, r.index, r.parent, r.heads, r.tails = names, index, parent, heads, tails
    r.order, r.w4, r.dq = order, w4, 1 - np.clip(1.5 * lin, 0, 1)
    r.twists, r.proxies = twists, proxies
    n = len(names)
    D = np.full((n, n), 99)
    for i in range(n):
        D[i, i] = 0
        if parent[i] >= 0:
            D[i, parent[i]] = D[parent[i], i] = 1
    for i, j in twists:
        D[i, j] = D[j, i] = 0
    for k in range(n):
        D = np.minimum(D, D[:, k:k + 1] + D[k:k + 1, :])
    r.near = D <= 1
    body.rig = r
    body.true = {}
    return ob


# ------------------------------------------------------------------ postures
def _rotation(axis, degrees):
    a = _unit(np.asarray(axis, float))
    t = math.radians(degrees)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(t) * K + (1 - math.cos(t)) * K @ K


def _swing(a, b):
    """The shortest rotation taking direction a to direction b."""
    a, b = _unit(a), _unit(b)
    v, c = np.cross(a, b), a @ b
    if np.linalg.norm(v) < 1e-9:
        return np.eye(3)
    return _rotation(v, math.degrees(math.acos(max(-1.0, min(1.0, c)))))


def _quat(R):
    """A rotation matrix as a quaternion (x, y, z, w)."""
    t = np.trace(R)
    if t > 0:
        s = math.sqrt(t + 1) * 2
        q = [(R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s, s / 4]
    else:
        i = int(np.argmax(np.diag(R)))
        j, k = (i + 1) % 3, (i + 2) % 3
        s = math.sqrt(1 + R[i, i] - R[j, j] - R[k, k]) * 2
        q = [0, 0, 0, (R[k, j] - R[j, k]) / s]
        q[i], q[j], q[k] = s / 4, (R[j, i] + R[i, j]) / s, (R[k, i] + R[i, k]) / s
    return np.array(q)


def _qmul(a, b):
    ax, ay, az, aw = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    bx, by, bz, bw = b[..., 0], b[..., 1], b[..., 2], b[..., 3]
    return np.stack([aw * bx + bw * ax + ay * bz - az * by, aw * by + bw * ay + az * bx - ax * bz,
                     aw * bz + bw * az + ax * by - ay * bx, aw * bw - ax * bx - ay * by - az * bz], -1)


def _qmat(q):
    """Quaternions (n, 4) as rotation matrices (n, 3, 3)."""
    x, y, z, w = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    return np.stack([np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], 1),
                     np.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], 1),
                     np.stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], 1)], 1)


def _world(r, aim, turn, root):
    """Each bone's world rotation and world head under a posture."""
    n = len(r.names)
    R = [None] * n
    for i in range(n):
        P = R[r.parent[i]] if r.parent[i] >= 0 else np.eye(3)
        if i in aim:
            R[i] = _swing(P @ (r.tails[i] - r.heads[i]), aim[i]) @ P
        else:
            R[i] = P @ turn.get(i, np.eye(3))
    for i, j in r.twists:                      # the bone without its twist: swing = full · twist⁻¹, about its own axis
        P = R[r.parent[i]] if r.parent[i] >= 0 else np.eye(3)
        q = _quat(P.T @ R[i])
        a = _unit(r.tails[i] - r.heads[i])
        tw = np.r_[(q[:3] @ a) * a, q[3]]
        tw = tw / np.linalg.norm(tw) if np.linalg.norm(tw) > 1e-9 else np.array([0, 0, 0, 1.0])
        inv = tw * np.array([-1, -1, -1, 1.0])
        R[j] = (R[r.parent[j]] if r.parent[j] >= 0 else np.eye(3)) @ _qmat(_qmul(q, inv)[None])[0]
    pos = [None] * n
    for i in range(n):
        p = r.parent[i]
        pos[i] = r.heads[i] + root if p < 0 else pos[p] + R[p] @ (r.heads[i] - r.heads[p])
    return R, pos


def _skin(v, r, R, pos):
    """The skin at rest positions v under the bones' rotations R and heads pos: dual quaternions, mixed with
    the linear blend where the rig says so. Also each vertex's linear map rest → posed."""
    n = len(r.names)
    real = np.array([_quat(R[i]) for i in range(n)])
    dual = np.zeros((n, 4))
    shift = np.zeros((n, 3))
    for i in range(n):
        shift[i] = pos[i] - R[i] @ r.heads[i]
        dual[i] = 0.5 * _qmul(np.r_[shift[i], 0.0], real[i])
    q, d = real[r.order], dual[r.order]
    sg = np.where(np.einsum("nkj,nj->nk", q, q[:, 0]) < 0, -1.0, 1.0)
    br, bd = np.einsum("nk,nkj->nj", r.w4 * sg, q), np.einsum("nk,nkj->nj", r.w4 * sg, d)
    ln = np.linalg.norm(br, axis=1, keepdims=True)
    br, bd = br / ln, bd / ln
    a, s_ = br[:, :3], br[:, 3:]
    out = v + 2 * np.cross(a, np.cross(a, v) + s_ * v) + 2 * (s_ * bd[:, :3] - bd[:, 3:] * a + np.cross(a, bd[:, :3]))
    Rm = np.array(R)
    lp = np.zeros_like(v)
    for k in range(r.order.shape[1]):
        lp += r.w4[:, k:k + 1] * (np.einsum("nij,nj->ni", Rm[r.order[:, k]], v) + shift[r.order[:, k]])
    dq = r.dq[:, None]
    M = dq[:, :, None] * _qmat(br) + (1 - dq[:, :, None]) * np.einsum("nk,nkij->nij", r.w4, Rm[r.order])
    return dq * out + (1 - dq) * lp, M


def _nearest2(feature, reach):
    """Squared distance, in grid steps, from every sample to the nearest sample of `feature` (up to reach)."""
    d = np.where(feature, 0.0, 1e12).astype(np.float32)
    for axis in range(3):
        n = d.shape[axis]
        out = d.copy()
        for k in range(1, min(reach, n - 1) + 1):
            lo, hi = [slice(None)] * 3, [slice(None)] * 3
            lo[axis], hi[axis] = slice(0, n - k), slice(k, n)
            lo, hi = tuple(lo), tuple(hi)
            np.minimum(out[lo], d[hi] + k * k, out=out[lo])
            np.minimum(out[hi], d[lo] + k * k, out=out[hi])
        d = out
    return d


def _true(body, name):
    """A piece's signed Euclidean distance (its own field is one only near its surface), kept."""
    if name not in body.true:
        g = body.pieces[name]
        inside = np.pad(g.f < 0, 3, constant_values=False)
        d_in = np.sqrt(_nearest2(~inside, max(inside.shape)))        # inside: to the nearest sample outside
        d_out = np.sqrt(np.minimum(_nearest2(inside, 6), 36.0))      # outside: to the nearest inside, near it only
        t = _Grid.__new__(_Grid)
        t.h, t.far = g.h, g.far
        t.lo = g.lo - 3 * g.h
        t.f = (np.where(inside, -d_in, d_out) * g.h).astype(np.float32)
        body.true[name] = t
    return body.true[name]


def _press(body, R, pos, floor, share=0.5):
    """The offsets, at rest, that press the posed skin out of the parts it went into (and up onto the floor)."""
    r, v0, graph = body.rig, body.rest, body.graph
    h = float(body.axes[0][1] - body.axes[0][0])
    base, M = _skin(v0, r, R, pos)
    Wn = np.zeros((len(v0), len(r.names)))
    np.put_along_axis(Wn, r.order, r.w4, 1)
    want = np.zeros_like(v0)
    for piece, b, span in r.proxies:
        sdf = _true(body, piece)
        t = np.clip((0.5 - Wn[:, r.near[b]].sum(1)) / 0.45, 0, 1)        # how free of that bone each vertex is
        fac = t * t * (3 - 2 * t)
        idx = np.flatnonzero(fac > 0)
        q = (base[idx] - pos[b]) @ R[b] + r.heads[b]                     # back to rest through this bone
        if span is not None:
            if span[0] == "along":
                x = q @ span[1]
                ok = (x >= span[2]) & (x < span[3])
            else:
                hd, tl = r.heads[b], r.tails[b]
                u = (q - hd) @ (tl - hd) / ((tl - hd) @ (tl - hd))
                ok = (u >= span[1]) & (u <= span[2])
            idx, q = idx[ok], q[ok]
        s = sdf(q)
        inside = s < -_core.mm(0.2)
        if not inside.any():
            continue
        idx, q, s = idx[inside], q[inside], s[inside]
        depth = np.maximum(-(s - np.minimum(sdf(v0[idx]), 0)), 0) * fac[idx]   # (not what the rest pose has)
        g = np.stack([sdf(q + e) - sdf(q - e) for e in np.eye(3) * h], 1)
        g /= np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-9)
        mv = (share * depth)[:, None] * (g @ R[b].T)                     # out of that piece, in the world
        big = np.linalg.norm(mv, axis=1) > np.linalg.norm(want[idx], axis=1)
        want[idx[big]] = mv[big]
    hit = np.linalg.norm(want, axis=1) > _core.mm(0.05)
    count = np.maximum(graph.total(hit.astype(float)), 1)
    for _ in range(graph.passes(_core.mm(1.55))):                        # the pushes agree with their neighbours',
        want = np.where(hit[:, None], 0.5 * want + 0.5 * graph.total(want) / count[:, None], want)
    off = want.copy()
    for _ in range(graph.passes(_core.mm(3.101))):                       # and fade out round the contact (no ridge)
        off = 0.5 * off + 0.5 * graph.mean(off)
        off[hit] = want[hit]
    if floor is not None:                                                # the floor is hard
        up = np.maximum(floor - (base + off)[:, 2], 0)
        for _ in range(graph.passes(_core.mm(1.899))):
            up = np.maximum(up, 0.5 * up + 0.5 * graph.mean(up))
        off[:, 2] += up
    rest = np.einsum("nij,nj->ni", np.linalg.inv(M + 1e-3 * np.eye(3)), off)
    tiny = _core.mm(1e-9)
    lim = 2.5 * np.linalg.norm(off, axis=1, keepdims=True) + tiny        # (a near-flat map would throw it far)
    return rest * np.minimum(1, lim / np.maximum(np.linalg.norm(rest, axis=1, keepdims=True), tiny))


def posture(ob, aim=None, turn=None, root=(0, 0, 0), press=True, floor=None):
    """Pose a rigged body: aim={bone: direction}, turn={bone: [(axis, degrees), ...]}, root its move.

    From the rest pose, never from the last posture. `aim` points a bone along a direction of
    the world ("+X", (x, y, z)), swung the shortest way from where its parent carries it: an
    arm raised, `aim={"upperarm_R": (0.35, -0.1, 0.93)}`. `turn` turns a bone on its joint
    from its rest position, in its parent's frame as the body stands at rest: rotations about
    "x", "y", "z" or an axis (x, y, z), in degrees, the first in the list applied last (as a
    matrix product) — a joint's angles in the order anatomy names them: a hip spread 45°,
    flexed 100°, turned out 92° is `[("z", 45), ("x", -100), ("z", 92)]`, a knee `[("x",
    80)]`; angles keep a knee bending as a knee does, which a direction does not. Children
    follow their parents; `root` moves the whole body (to sit it down).

    `press`: where the posture pushes one part into another (an arm into the neck, a shin
    into the other), the skin of both is pressed back to meet half-way, fading out round the
    contact, as flesh squashes; `floor=z` is a hard floor at that height (a seat flattens on
    it). `press=False` leaves the parts through one another. Returns the body."""
    body = _body(ob, "posture")
    r = body.rig
    if r is None:
        raise ValueError("posture: the body has no bones yet: rig it first")
    aims, turns = {}, {}
    for n, d in (aim or {}).items():
        if n not in r.index:
            raise ValueError(f"posture: aim names a bone {n!r} that is not one; bones: {', '.join(r.names)}")
        aims[r.index[n]] = _direction(d, "posture", f"aim of {n!r}")
    for n, steps in (turn or {}).items():
        if n not in r.index:
            raise ValueError(f"posture: turn names a bone {n!r} that is not one; bones: {', '.join(r.names)}")
        if n in (aim or {}):
            raise ValueError(f"posture: {n!r} is both aimed and turned: give one")
        if isinstance(steps, tuple) and len(steps) == 2 and not isinstance(steps[0], tuple):
            steps = [steps]
        m = np.eye(3)
        for step in steps:
            try:
                axis, deg = step
                axis = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[axis.lower()] if isinstance(axis, str) else axis
                m = m @ _rotation(_point(axis, "posture", "a turn's axis"), float(deg))
            except (TypeError, ValueError, KeyError):
                raise ValueError(f"posture: a turn of {n!r} is (axis, degrees), the axis \"x\", \"y\", \"z\" or "
                                 f"(x, y, z), not {step!r}") from None
        turns[r.index[n]] = m
    twisted = {j for _, j in r.twists}
    for i in list(aims) + list(turns):
        if i in twisted:
            raise ValueError(f"posture: {r.names[i]!r} follows another bone without its twist: pose that one")
    root = _point(root, "posture", "root")
    if floor is not None and (isinstance(floor, bool) or not isinstance(floor, (int, float))):
        raise ValueError(f"posture: floor is a height, not {floor!r}")
    R, pos = _world(r, aims, turns, root)
    rest = body.rest
    if press:
        rest = rest + _press(body, R, pos, floor)
    posed, _ = _skin(rest, r, R, pos)
    ob.data.vertices.foreach_set("co", posed.astype(np.float32).ravel())
    ob.data.update()
    return ob


def detail(ob, offsets):
    """Add a fitted layer to a body's surface at rest: an offset (x, y, z) per vertex, or a .npy file of them.

    What flesh cannot say — a face, fingers, the muscles' relief — fitted on the body's
    surface from a scan or a sculpture, kept as one offset per vertex of the mesh `flesh`
    made (the same program makes the same mesh, vertex for vertex: the layer is fitted once
    and stays valid while the flesh's pieces, cell and box do not change). The bones carry
    it: `rig` weighs the flesh as made, with or without it, and `posture` moves the detailed
    surface. Calling it again replaces the layer. Returns the body."""
    body = _body(ob, "detail")
    if isinstance(offsets, (str, bytes)) or hasattr(offsets, "__fspath__"):
        try:
            arr = np.load(offsets, allow_pickle=False)
        except (OSError, ValueError) as exc:
            raise ValueError(f"detail: cannot read {offsets!r} as a .npy array: {exc}") from None
    else:
        arr = np.asarray(offsets)
    try:
        arr = np.asarray(arr, dtype=np.float64)
    except (TypeError, ValueError):
        arr = np.empty(0)
    if arr.shape != body.base.shape or not np.all(np.isfinite(arr)):
        raise ValueError(f"detail: the layer is one offset (x, y, z) per vertex of the body — {len(body.base):,} of "
                         f"them — not an array of shape {arr.shape}: it was fitted on another mesh (other pieces, "
                         f"cell or box)")
    body.rest = body.base + arr
    ob.data.vertices.foreach_set("co", body.rest.astype(np.float32).ravel())
    ob.data.update()
    return ob
