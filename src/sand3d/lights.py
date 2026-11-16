"""Lights: a point, a spot or a sun — named objects, placed like any other, that give light."""
import math

import bpy

from . import _core
from .materials import _hex, _linear

#: The kinds, and Blender's name for each.
KINDS = {"point": "POINT", "spot": "SPOT", "sun": "SUN"}

#: Lumens per watt of white light: what converts Blender's watts and the candela and lux a
#: GLB holds (glTF's KHR_lights_punctual, as Blender's exporter writes it).
LUMENS_PER_WATT = 683.0


def light(name, kind="point", lm=None, lux=None, color="#ffffff", angle=45, blend=0.15):
    """Kind: point spot sun; lm lumens (point, spot; 800 by default), lux (sun; 3 by default); shines along its own -Z.

    A light named `name`, at the origin of its own frame: place it with `at`, hang it in a
    `group` or an `assembly` like a part — the bulb of a lamp belongs to the lamp. It is not
    a solid: it has no faces, and the edits refuse it.

    - "point" shines every way from where it stands, with `lm` lumens: 800 is a household
      bulb, 250 a small lamp.
    - "spot" is a point that shines only inside a cone about its own -Z: `angle`, in
      degrees, is the cone's full opening (above 0, under 180), and `blend` (0..1) the share
      of it, from the edge inwards, over which the light fades. Its `lm` are those of the
      whole point it is cut from: on its axis it is as bright as a point of the same `lm`.
    - "sun" shines along its own -Z from infinitely far, the same everywhere: `lux` is what
      a surface facing it receives. Where it stands does not count, only how it is turned.

    A light shines down as built. Turn it with `at`: `rx=90` shines along +Y, `ry=90` along
    -X; on a face's frame (`on=`), whose Z is the face's normal, `rx=180` turns it to shine
    out of the face. `color` is sRGB, "#rrggbb" or (r, g, b) in 0..1.

    `export` writes lights in a .glb (KHR_lights_punctual: a point or a spot in candela,
    lm / 4π; a sun in lux); the other formats carry no light."""
    if not isinstance(name, str) or not name:
        raise TypeError(f"light: a name is expected first, not {name!r}")
    if kind not in KINDS:
        raise ValueError(f"light: kind is {', '.join(repr(k) for k in KINDS)}, not {kind!r}")
    given = lux if kind == "sun" else lm
    wrong, right = ("lm", "lux") if kind == "sun" else ("lux", "lm")
    if (lm if kind == "sun" else lux) is not None:
        raise ValueError(f"light: a {kind} takes {right}, not {wrong}")
    power = _strength(right, (3.0 if kind == "sun" else 800.0) if given is None else given)
    try:
        rgb = _linear(_hex(color))[:3]
    except ValueError as exc:
        raise ValueError(str(exc).replace("material:", "light:", 1)) from exc
    if kind == "spot":
        angle = _strength("angle", angle)
        if not 0 < angle < 180:
            raise ValueError(f"light: angle is the cone's full opening, above 0 and under 180 degrees, not {angle!r}")
        blend = _strength("blend", blend)
        if blend > 1:
            raise ValueError(f"light: blend is a share of the cone, 0..1, not {blend!r}")
    data = bpy.data.lights.new(name, KINDS[kind])    # nothing is made before everything is checked
    data.energy = power / LUMENS_PER_WATT            # watts, or watts per square metre for a sun
    data.color = rgb
    if kind == "spot":
        data.spot_size = math.radians(angle)
        data.spot_blend = blend
    return _core.link(bpy.data.objects.new(name, data))


def _strength(what, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"light: {what} is a number of 0 or more, not {value!r}")
    return float(value)


def lit(root):
    """Whether `root`'s tree holds a light."""
    return any(ob.type == "LIGHT" for ob in [root, *root.children_recursive])
