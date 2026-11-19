"""Lights: a point, a spot, a sun or the sky — named objects, placed like any other, in physical units.

A point or a spot gives lumens, a sun or the sky lux: what a light gives, never what a
picture of it shows, which is the exposure of whoever renders it. Blender keeps a light's
power in watts, and the glTF exporter turns them back at 683 lumens a watt; the sky has no
light object in Blender, so an ambient light is a sun that gives nothing there. Each light's
data holds what the program said of it (`SAID`): its kind, its power and its colour, which every
export reads, and writes in its own words or leaves out.
"""
import math
import os
import sys
import warnings

import bpy

from . import _core
from .materials import _hex, _linear

#: The kinds, and Blender's type for each.
KINDS = {"point": "POINT", "spot": "SPOT", "sun": "SUN", "ambient": "SUN"}

#: What a light gives when the program says nothing: a household bulb, the midday sun, an overcast sky.
POWER = {"point": 800.0, "spot": 800.0, "sun": 100_000.0, "ambient": 10_000.0}

#: How wide a bulb is when the program says nothing, in millimetres: a household bulb's glass, a spot's LED.
SIZE = {"point": 60.0, "spot": 30.0}

#: Lumens per watt: Blender's watts from the lumens and lux of a program, as glTF's exporter reads them back.
LUMENS_PER_WATT = 683.0

#: On a light's data, what the program said, in units no reader has to convert: "kind"; "power", lm or lux;
#: "color", "#rrggbb" (sRGB); "shadow"; a point's or a spot's "size", in metres; a sun's "angle", in degrees.
#: Blender's watts and linear colours are single precision: 100 000 lux read back from them is 100 000.002.
#: The GLB carries it whole, in each light's extras.
SAID = "s3d_light"


def light(name, kind="point", lm=None, lux=None, color="#ffffff", angle=None, blend=None, shadow=True, size=None):
    """Kind: point spot sun ambient; lm lumens (point, spot; 800), lux (sun 100 000, ambient 10 000); shines along its own -Z

    A light named `name`, at the origin of its own frame: place it with `at`, hang it in a
    `group` or an `assembly` like a part — the bulb of a lamp belongs to the lamp. It is not
    a solid: it has no faces, no extent in a `bbox`, and the edits refuse it.

    - "point" shines every way from where it stands, with `lm` lumens: 800 is a household
      bulb, 250 a small lamp.
    - "spot" is a point that shines only inside a cone about its own -Z: `angle`, in
      degrees, is the cone's full opening (above 0, under 180; 45 by default), and `blend`
      (0..1, 0.15 by default) the share of it, from the edge inwards, over which the light
      fades. Its `lm` are those of the whole point it is cut from: on its axis it is as
      bright as a point of the same `lm`.
    - "sun" shines along its own -Z from infinitely far, the same everywhere: `lux` is what
      a surface facing it receives — 100 000 at noon on a clear day. Where it stands does
      not count, only how it is turned. `angle` is how wide it is seen, in degrees: 0.53,
      the real sun's, by default; 0 for a shadow with a sharp edge.
    - "ambient" is the sky, the same from every side: `lux` is what a surface facing up
      receives from it in the open — 10 000 under an overcast sky. Neither its place nor
      its turn counts, and it casts no shadow.

    A light shines down as built. Turn it with `at`: `rx=90` shines along +Y, `ry=90` along
    -X; on a face's frame (`on=`), whose Z is the face's normal, `rx=180` turns it to shine
    out of the face. `color` is sRGB, "#rrggbb" or (r, g, b) in 0..1.

    `size` is the diameter of the bulb of a point or a spot, in the program's unit — 60 mm,
    a household bulb, for a point and 30 mm for a spot by default: what stands in its way
    casts a shadow with a soft edge, as a real lamp does; 0 makes it a point, and the edge
    sharp. `shadow=False` makes a fill light, which shines through everything.

    `export` writes the lights in what each format has words for: a .glb a point or a spot
    in candela (lm / 4π) and a sun in lux (KHR_lights_punctual), its size and its shadow
    switch in the light's extras (`s3d_light`), and no ambient light; a .usda all of them
    (UsdLux); an .ifc a point or a spot as a light fixture, in lumens. A light a format has
    no word for is left out, with a warning."""
    if not isinstance(name, str) or not name:
        raise TypeError(f"light: a name is expected first, not {name!r}")
    if kind not in KINDS:
        raise ValueError(f"light: kind is {', '.join(repr(k) for k in KINDS)}, not {kind!r}")
    far = kind in ("sun", "ambient")
    unit, other = ("lux", "lm") if far else ("lm", "lux")
    if (lm if far else lux) is not None:
        article = "an" if kind == "ambient" else "a"
        raise ValueError(f"light: {article} {kind} light is given in {unit}, not {other}")
    power = _number(unit, POWER[kind] if (lux if far else lm) is None else (lux if far else lm))
    try:
        srgb = _hex(color)
    except ValueError as exc:
        raise ValueError(str(exc).replace("material:", "light:", 1)) from exc
    if not isinstance(shadow, bool):
        raise ValueError(f"light: shadow is True or False, not {shadow!r}")
    size = _number("size", _core.mm(SIZE.get(kind, 0.0)) if size is None else size)
    if kind != "spot" and blend is not None:
        raise ValueError(f"light: blend is the soft edge of a spot's cone, not of a {kind} light")
    if kind in ("point", "ambient") and angle is not None:
        raise ValueError(f"light: angle is a spot's cone or a sun's width, not a {kind} light's")
    if kind == "ambient" and (size or not shadow):
        raise ValueError("light: an ambient light comes from every side and casts no shadow: it takes no size "
                         "and no shadow")
    if kind == "sun" and size:
        raise ValueError("light: a sun is infinitely far and has no size: `angle` is how wide it is seen")
    if kind == "spot":
        angle = _number("angle", 45 if angle is None else angle)
        if not 0 < angle < 180:
            raise ValueError(f"light: a spot's angle is its cone's full opening, above 0 and under 180 degrees, "
                             f"not {angle!r}")
        blend = _number("blend", 0.15 if blend is None else blend)
        if blend > 1:
            raise ValueError(f"light: blend is a share of the cone, 0..1, not {blend!r}")
    if kind == "sun":
        angle = _number("angle", 0.53 if angle is None else angle)
        if angle >= 180:
            raise ValueError(f"light: a sun's angle is how wide it is seen, under 180 degrees, not {angle!r}")

    data = bpy.data.lights.new(name, KINDS[kind])    # nothing is made before everything is checked
    data.color = _linear(srgb)[:3]
    data.use_shadow = shadow
    data[SAID] = {"kind": kind, "power": power, "color": srgb, "shadow": shadow,
                  **({"size": size * _core.MM / 1000} if kind in SIZE else {}),
                  **({"angle": angle} if kind == "sun" else {})}
    if kind == "ambient":
        data.energy = 0.0                            # Blender has no sky: as a sun, the sky gives nothing there
    else:
        data.energy = power / LUMENS_PER_WATT        # watts, or watts per square metre for a sun
    if kind == "sun":
        data.angle = math.radians(angle)
    elif kind != "ambient":
        data.shadow_soft_size = size / 2
    if kind == "spot":
        data.spot_size = math.radians(angle)
        data.spot_blend = blend
    ob = _core.link(bpy.data.objects.new(name, data))
    ob[_core.NAME] = name
    return ob


def _number(what, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"light: {what} is a number of 0 or more, not {value!r}")
    return float(value)


def lights(obs):
    """The lights among `obs`, in their order."""
    return [ob for ob in obs if ob.type == "LIGHT"]


def kind(ob):
    """What a light object is: "point", "spot", "sun" or "ambient"."""
    return ob.data[SAID]["kind"]


def power(ob):
    """A point's or a spot's lumens, a sun's or an ambient light's lux."""
    return float(ob.data[SAID]["power"])


def color(ob):
    """A light's colour as the program gave it: "#rrggbb", sRGB."""
    return ob.data[SAID]["color"]


def left_out(obs, path, why):
    """Warn, at the program's line, that the lights `obs` are not in the file at `path`: `why`."""
    names = sorted({_core.given_name(ob) for ob in obs})
    if not names:
        return
    here, frame, level = os.path.dirname(__file__), sys._getframe(1), 2
    while frame is not None and frame.f_code.co_filename.startswith(here):
        frame, level = frame.f_back, level + 1
    said = ", ".join(repr(n) for n in names)
    warnings.warn(f"export: {os.path.basename(str(path))} leaves out {said}: {why}", stacklevel=level)
