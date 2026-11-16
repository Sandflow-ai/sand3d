"""A spur gear with involute teeth."""
import math

from .. import _core
from ..profile import circle, poly
from ..solids import extrude


def _inv(a):
    return math.tan(a) - a


def gear(name, teeth, module, width, bore=0, angle=20):
    """Involute spur gear.

    A spur gear of `teeth` involute teeth, `module` of pitch diameter per tooth,
    `width` thick along Z from Z = 0 up; `bore` a hole through it, `angle` the pressure
    angle in degrees."""
    a = math.radians(angle)
    r = module * teeth / 2
    rb, ra, rf = r * math.cos(a), r + module, max(r - 1.25 * module, 0.1 * r)
    half = math.pi / (2 * teeth) + _inv(a)          # half a tooth's angle at the base circle

    def flank(rho):
        return half - _inv(math.acos(min(1.0, rb / rho)))

    steps = _core.resolution_count(6)
    start = max(rb, rf)
    radii = [start + (ra - start) * k / steps for k in range(steps + 1)]
    pts = []
    for k in range(teeth):
        c = 2 * math.pi * k / teeth
        right = [(rho, c - flank(rho)) for rho in radii]
        left = [(rho, c + flank(rho)) for rho in reversed(radii)]
        root = []
        if rf < rb:
            root = [(rf, c - flank(rb))]
        tooth = root + right + [(ra, c)] + left + ([(rf, c + flank(rb))] if rf < rb else [])
        pts += [(rho * math.cos(t), rho * math.sin(t)) for rho, t in tooth]
    profile = poly(pts)
    if bore:
        profile = profile - circle(bore)
    return extrude(name, profile, width)
