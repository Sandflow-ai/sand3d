"""Anatomy: a body built as an artist builds it — joints first, muscles laid between them.

`skeleton` names the joints of a body once (a shoulder, an elbow, a wrist…), measured or
chosen; `muscle` lays a spindle between two of them, thick in its belly and rounded at its
ends, flattened toward a side and bulging off its line — placed by the two points it joins,
never by a rotation. Muscles are solids: `blend` fuses them with their neighbours, `clay`
remakes the whole as one even surface, and the sculpting verbs work on it.
"""
import math

from mathutils import Vector

from . import _core
from .frames import Frame, at
from .sculpt import _direction, _radius

#: Sections a muscle is lofted through, poles included, and segments round each.
MUSCLE_STATIONS, MUSCLE_FACETS = 11, 32


class Skeleton(dict):
    """Joints by name: `bones.elbow`, `bones["elbow"]`, points of the space it is given in."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"skeleton: no joint {name!r}; joints: {', '.join(sorted(self))}") from None

    def mirrored(self, axis="x"):
        """The same joints, their image across the plane through the origin square to `axis`."""
        k = "xyz".index(axis.lower().lstrip("+-"))
        out = Skeleton()
        for name, p in self.items():
            q = Vector(p)
            q[k] = -q[k]
            out[name] = q
        return out


def _point(p, verb, what):
    if hasattr(p, "origin"):
        return Vector(p.origin)
    if isinstance(p, (tuple, list, Vector)) and len(p) == 3:
        return Vector(p)
    raise ValueError(f"{verb}: {what} is a point (x, y, z), a joint of a skeleton or a frame, not {p!r}")


def skeleton(**joints):
    """Joints by name, (x, y, z) or frames: where a body's muscles attach.

    `skeleton(shoulder=(88, 0, 35), elbow=(100, -17, -42), wrist=(58, -76, -106))`: each
    joint a point of the space the body is built in, or a frame (its origin). Read them as
    `bones.elbow`; `bones.mirrored("x")` gives the other side's. Muscles go between them."""
    if not joints:
        raise ValueError("skeleton: name its joints, skeleton(shoulder=(x, y, z), elbow=(x, y, z), ...)")
    return Skeleton({name: _point(p, "skeleton", f"joint {name!r}") for name, p in joints.items()})


def muscle(name, a, b, belly, flat=1.0, side=None, peak=0.5, bow=0.0):
    """A spindle from a to b, belly thick at its widest; flat < 1 flattens it toward side.

    A muscle between the two places it attaches, `a` and `b` — points, joints of a
    `skeleton`, frames: thick `belly` at its widest, `peak` of the way along (0.5 the
    middle), rounded off to nothing at both ends. `flat` < 1 flattens its section toward
    `side` — a direction square to it, "+Y", "-X+Z" or (x, y, z), the way its face turns:
    a pectoral lies flat on the chest, `flat=0.4, side="-Y"`. `bow` pushes its belly that far
    toward `side`, off the line between its ends: a biceps standing off the bone. Placed by
    its two ends, never by a rotation; its spine runs from a to b (`spot`)."""
    a, b = _point(a, "muscle", "a"), _point(b, "muscle", "b")
    length = (b - a).length
    if length <= _core.mm(1e-3):
        raise ValueError("muscle: a and b are the same place: a muscle runs between two")
    belly = _radius(belly, "muscle", "belly")
    for what, v, lo, hi in (("flat", flat, 0, 1), ("peak", peak, 0, 1)):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo < v <= hi:
            raise ValueError(f"muscle: {what} is a share above {lo} and at most {hi}, not {v!r}")
    if peak >= 1:
        raise ValueError("muscle: peak is where the belly is along it, between 0 and 1, not 1")
    axis = (b - a) / length
    up = _direction(side, "muscle") if side is not None else None
    if up is not None and abs(up.dot(axis)) > 0.999:
        raise ValueError(f"muscle: side {side!r} runs along the muscle: it is a direction square to it")
    gamma = math.log(0.5) / math.log(peak)
    sections = []
    from .profile import station
    for i in range(MUSCLE_STATIONS):
        u = i / (MUSCLE_STATIONS - 1)
        swell = math.sin(math.pi * u ** gamma)
        k = swell ** 0.7 if 0 < i < MUSCLE_STATIONS - 1 else 0.0
        sections.append(station(u * length, belly * k, belly * flat * k, y=bow * swell))
    from .assembly import facets
    from .solids import loft
    with facets(MUSCLE_FACETS):          # a muscle is fused and remade as clay: a light mesh is enough
        ob = loft(name, *sections)
    _core.keep_spine(ob, [(0, 0, 0), (0, 0, length)])     # its spine is the line between its ends
    return at(ob, on=Frame(a, normal=axis, up=up))
