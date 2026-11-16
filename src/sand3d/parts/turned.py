"""Turned surfaces whose radius varies round and along them: a knurled grip, a thread."""
import math

from .. import _core
from ..solids import _cap, _object


def _lathe(name, radius, h, around, along):
    """A closed solid along Z, from 0 to `h`: `around` × `along` points on a grid whose
    distance from the axis is `radius(angle, z)`; flat ends."""
    b = _core.Builder(name)
    rings = []
    for j in range(along + 1):
        z = h * j / along
        ring = []
        for i in range(around):
            t = 2 * math.pi * i / around
            r = radius(t, z)
            ring.append(b.vert((r * math.cos(t), r * math.sin(t), z)))
        rings.append(ring)
    for j in range(along):
        lower, upper = rings[j], rings[j + 1]
        for i in range(around):
            i1 = (i + 1) % around
            b.face([lower[i], lower[i1], upper[i1]], 0, ("side",))
            b.face([lower[i], upper[i1], upper[i]], 0, ("side",))
    flat = [(v.co.x, v.co.y) for v in rings[0]]
    caps = [b.face([rings[0][i] for i in reversed(t)], -1, ("bottom",)) for t in _cap(flat)]
    flat = [(v.co.x, v.co.y) for v in rings[-1]]
    caps += [b.face([rings[-1][i] for i in t], -2, ("top",)) for t in _cap(flat)]
    b.dissolve(caps)
    return _object(b, __import__("mathutils").Matrix.Identity(4), "side")


def _triangle(f):
    """1 at whole numbers, 0 half-way between: a V wave."""
    return abs(2 * (f - math.floor(f)) - 1)


def thread(name, d, length, pitch, left=False):
    """Threaded rod.

    A threaded rod: diameter `d` over the crests, `length` along Z from 0, the 60°
    ISO V-thread of `pitch`; `left` for a left-hand thread."""
    depth = 0.6134 * pitch
    sign = -1 if left else 1

    def radius(t, z):
        return d / 2 - depth * _triangle(z / pitch - sign * t / (2 * math.pi))
    around = 32
    along = max(8, math.ceil(length / pitch * 8))
    return _lathe(name, radius, length, around, along)


def knurl(name, d, h, pitch=None, straight=False):
    """Knurled grip; pitch 1 mm by default.

    A knurled grip, diameter `d` over the teeth, `h` long along Z from 0: diamond
    teeth `pitch` apart (two 30° helices crossing), or straight ridges. `pitch` is in
    the program's unit, as every length; left out, it is 1 mm whatever the unit."""
    if pitch is None:
        pitch = _core.mm(1.0)
        if pitch >= d:
            raise ValueError(f"knurl: the diameter {d} is not above the default pitch of 1 mm: give a smaller pitch")
    if pitch >= d:
        raise ValueError(f"knurl: pitch {pitch} is not smaller than the diameter {d} — in a unit other than "
                         f"mm, give the pitch in it")
    # the counts from millimetres: a pitch of 1 mm is 0.1 in cm, which no float holds exactly
    dm, hm, pm = _core.in_mm(d), _core.in_mm(h), _core.in_mm(pitch)
    teeth = max(6, round(math.pi * dm / pm))
    depth = 0.5 * pitch

    if straight:
        def radius(t, z):
            return d / 2 - depth * _triangle(teeth * t / (2 * math.pi))
        return _lathe(name, radius, h, 4 * teeth, max(1, round(hm / pm)))
    lead = math.pi * d / math.tan(math.radians(30)) / teeth   # axial advance per tooth along a helix

    def radius(t, z):
        u = teeth * t / (2 * math.pi) + z / lead
        v = teeth * t / (2 * math.pi) - z / lead
        return d / 2 - depth * max(_triangle(u), _triangle(v))
    return _lathe(name, radius, h, 4 * teeth, max(4, math.ceil(4 * hm / _core.in_mm(lead))))
