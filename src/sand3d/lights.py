"""Lights: a point, a spot, a sun or the light of the sky — named objects, placed like any other, that give light."""
import math

import bpy

from . import _core
from .materials import _hex, _linear

#: The kinds, and Blender's name for each. An ambient light has none of Blender's: it is
#: kept as a sun that gives nothing, and `render` makes the sky from what it says.
KINDS = {"point": "POINT", "spot": "SPOT", "sun": "SUN", "ambient": "SUN"}

#: Lumens per watt of white light: what converts Blender's watts and the candela and lux a
#: GLB holds (glTF's KHR_lights_punctual, as Blender's exporter writes it).
LUMENS_PER_WATT = 683.0

#: Where an ambient light keeps what it says, on its light data: [lux, r, g, b of the ground, linear].
AMBIENT = "s3d_ambient"

#: On a solid that casts no shadow: False. A solid that casts one carries nothing.
SHADOW = "s3d_shadow"


def light(name, kind="point", lm=None, lux=None, color="#ffffff", angle=None, blend=0.15, shadow=True, size=0,
          ground=None):
    """Kind: point spot sun ambient; lm lumens (point, spot; 800), lux (sun 3, ambient 1); shines along its own -Z; size, angle: soft shadows.

    A light named `name`, at the origin of its own frame: place it with `at`, hang it in a
    `group` or an `assembly` like a part — the bulb of a lamp belongs to the lamp. It is not
    a solid: it has no faces, and the edits refuse it.

    - "point" shines every way from where it stands, with `lm` lumens: 800 is a household
      bulb, 250 a small lamp.
    - "spot" is a point that shines only inside a cone about its own -Z: `angle`, in
      degrees, is the cone's full opening (above 0, under 180; 45 by default), and `blend`
      (0..1) the share of it, from the edge inwards, over which the light fades. Its `lm` are those of the
      whole point it is cut from: on its axis it is as bright as a point of the same `lm`.
    - "sun" shines along its own -Z from infinitely far, the same everywhere: `lux` is what
      a surface facing it receives. Where it stands does not count, only how it is turned.
    - "ambient" comes from every side, as from an overcast sky: `lux` is what a surface
      facing up receives under it in the open. `color` comes from above and `ground` from
      below (the same colour when `ground` is None): a face turned sideways gets half of
      each. Neither its place nor its turn counts. It is what keeps a shadow from being black.

    A light shines down as built. Turn it with `at`: `rx=90` shines along +Y, `ry=90` along
    -X; on a face's frame (`on=`), whose Z is the face's normal, `rx=180` turns it to shine
    out of the face. `color` is sRGB, "#rrggbb" or (r, g, b) in 0..1.

    `shadow`: whether what stands in its way casts a shadow (False: it shines through
    everything, a fill light). A shadow's edge is sharp unless the light has a width: `size`,
    the diameter of the bulb of a point or a spot, in the program's unit; for a sun `angle`,
    the angle it is seen under, in degrees (the real one: 0.53). An ambient light takes none
    of them: it casts no shadow of its own, and reaches less far into a corner than onto an
    open face.

    `render` shows what the lights light. `export` writes them in a .glb
    (KHR_lights_punctual: a point or a spot in candela, lm / 4π; a sun in lux); the other
    formats carry no light."""
    if not isinstance(name, str) or not name:
        raise TypeError(f"light: a name is expected first, not {name!r}")
    if kind not in KINDS:
        raise ValueError(f"light: kind is {', '.join(repr(k) for k in KINDS)}, not {kind!r}")
    far = kind in ("sun", "ambient")
    given = lux if far else lm
    wrong, right = ("lm", "lux") if far else ("lux", "lm")
    if (lm if far else lux) is not None:
        raise ValueError(f"light: {'an' if kind == 'ambient' else 'a'} {kind} takes {right}, not {wrong}")
    power = _strength(right, {"sun": 3.0, "ambient": 1.0}.get(kind, 800.0) if given is None else given)
    try:
        rgb = _linear(_hex(color))[:3]
        below = None if ground is None else _linear(_hex(ground, "ground"))[:3]
    except ValueError as exc:
        raise ValueError(str(exc).replace("material:", "light:", 1)) from exc
    if kind != "ambient" and ground is not None:
        raise ValueError(f"light: ground is the colour an ambient light sends from below, not a {kind}'s")
    if kind == "spot":
        angle = _strength("angle", 45 if angle is None else angle)
        if not 0 < angle < 180:
            raise ValueError(f"light: angle is the cone's full opening, above 0 and under 180 degrees, not {angle!r}")
        blend = _strength("blend", blend)
        if blend > 1:
            raise ValueError(f"light: blend is a share of the cone, 0..1, not {blend!r}")
    if not isinstance(shadow, bool):
        raise ValueError(f"light: shadow is True or False, not {shadow!r}")
    size = _strength("size", size)
    if kind == "ambient" and (size or not shadow or angle is not None):
        raise ValueError("light: an ambient light comes from every side: it takes no shadow, size or angle")
    if kind == "sun":
        if size:
            raise ValueError("light: a sun is infinitely far and has no size: `angle` is how wide it is seen")
        angle = _strength("angle", 0 if angle is None else angle)
        if angle >= 180:
            raise ValueError(f"light: a sun's angle is how wide it is seen, under 180 degrees, not {angle!r}")
    data = bpy.data.lights.new(name, KINDS[kind])    # nothing is made before everything is checked
    data.color = rgb
    if kind == "ambient":
        data.energy = 0.0                            # as a sun it gives nothing: `render` makes the sky
        data[AMBIENT] = [power, *(rgb if below is None else below)]
        return _core.link(bpy.data.objects.new(name, data))
    data.energy = power / LUMENS_PER_WATT            # watts, or watts per square metre for a sun
    data.use_shadow = shadow
    if kind == "sun":
        data.angle = math.radians(angle)
    else:
        data.shadow_soft_size = size / 2
    if kind == "spot":
        data.spot_size = math.radians(angle)
        data.spot_blend = blend
    return _core.link(bpy.data.objects.new(name, data))


def _strength(what, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"light: {what} is a number of 0 or more, not {value!r}")
    return float(value)


def shadow(ob, cast=True):
    """Whether a part casts a shadow.

    `cast=False`: light goes through `ob` as if it were not there, while it is still seen
    and still lit — the ceiling and the walls of a room lit from outside, a pane, a
    backdrop. `cast=True` puts its shadow back. A group, an assembly or a list tells each
    of its solids; a light is told by `light(shadow=)`. The choice follows the part
    through later edits and copies. It shows in `render`; no export format has a word
    for it."""
    from ._surface import meshes
    if not isinstance(cast, bool):
        raise ValueError(f"shadow: cast is True or False, not {cast!r}")
    parts = meshes(ob)
    if not parts:
        raise TypeError("shadow: a part, a group, an assembly or a list of them is expected")
    for part in parts:
        if cast:
            part.pop(SHADOW, None)
        else:
            part[SHADOW] = False
    return ob


def lit(root):
    """Whether `root`'s tree holds a light."""
    return any(ob.type == "LIGHT" for ob in [root, *root.children_recursive])


def ambient(ob):
    """What an ambient light says, (lux, linear colour from above, linear colour from below); None for any other
    object."""
    said = ob.data.get(AMBIENT) if ob.type == "LIGHT" else None
    return None if said is None else (float(said[0]), tuple(ob.data.color), tuple(float(c) for c in said[1:4]))
