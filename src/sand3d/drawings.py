"""Drawings: what is drawn on a surface — tiles, stripes, a wood grain — and repeats over it."""
import hashlib
import json
import math
from fractions import Fraction

import bpy
import numpy as np

from .materials import _hex, _linear

#: The UV layer a drawn material reads: the part's own coordinates, in periods of its drawing.
LAYER = "s3d_drawing"

#: Dots along one period, at least and at most: fine enough for the thinnest line, small enough to carry.
DOTS = (16, 1024)


class Drawing:
    """A drawing that repeats: `material(ob, kind, color=tiles(...))` draws it on every face of `ob`.

    It lies in each face's own plane: on a face that looks up or down, u is the part's X and v its Y; on any
    other, u runs level along the face (to the right of someone facing it) and v is the part's Z. A face
    that tilts or curves is drawn from the side it looks to most, so the drawing stretches there.
    `period`, in the program's unit, is the (u, v) step it repeats by; `color` is its mean colour, what a
    reader that takes one colour for a surface is given."""

    def __init__(self, spec):
        self.spec = spec

    def __repr__(self):
        said = ", ".join(f"{k}={v!r}" for k, v in self.spec.items() if k != "draw")
        return f"{self.spec['draw']}({said})"

    @property
    def period(self):
        return _PERIOD[self.spec["draw"]](self.spec)

    def image(self):
        """One period as sRGB values in 0..1, shape (rows, columns, 3): row 0 at v = 0, column 0 at u = 0."""
        return _IMAGE[self.spec["draw"]](self.spec)

    @property
    def color(self):
        linear = _to_linear(self.image()).reshape(-1, 3).mean(0)
        return "#" + "".join(f"{round(255 * float(c)):02x}" for c in _to_srgb(linear))

    @property
    def key(self):
        return hashlib.sha1(json.dumps(self.spec, sort_keys=True).encode()).hexdigest()[:12]


def tiles(w, d=None, joint=2, color="#d9d4c7", joint_color="#8c877b", shift=0):
    """Tiles w by d (square when d is None) with a joint between them; shift: each row slid by that share of a tile.

    A drawing for `material(ob, kind, color=tiles(...))`: rectangles `w` along u and `d` along v, in `color`,
    parted by a joint `joint` wide in `joint_color`, lengths in the program's unit. `shift`, 0 to under 1,
    slides each row along u by that share of a tile's step: 0 is a grid (floor tiles, a mesh, a
    chequered cloth with a wide joint), 0.5 the bond of bricks and of floor boards (`w` long, `d` narrow).
    The share is kept to eighths. A joint of 0 leaves one plain colour."""
    w, d = _length("tiles", "w", w), _length("tiles", "d", w if d is None else d)
    joint = _length("tiles", "joint", joint, zero=True)
    if isinstance(shift, bool) or not isinstance(shift, (int, float)) or not 0 <= shift < 1:
        raise ValueError(f"tiles: shift is the share of a tile each row slides by, 0 to under 1, not {shift!r}")
    slid = Fraction(shift).limit_denominator(8)
    return Drawing({"draw": "tiles", "w": w, "d": d, "joint": joint, "color": _colour("tiles", "color", color),
                    "joint_color": _colour("tiles", "joint_color", joint_color),
                    "shift": [slid.numerator, slid.denominator]})


def stripes(pitch, color="#ffffff", other="#1f3a5f", share=0.5, along="v"):
    """Bands of two colours, one pair every pitch; share: how much of it the first takes; along: the way they run.

    A drawing for `material(ob, kind, color=stripes(...))`: a band of `color` then one of `other`, the pair
    `pitch` wide in the program's unit, `color` taking the share `share` of it (above 0, under 1). `along`
    is the way the bands run: "v" (up a wall, along Y on a floor; they follow one another along u) or "u"
    (level on a wall, along X on a floor)."""
    pitch = _length("stripes", "pitch", pitch)
    if isinstance(share, bool) or not isinstance(share, (int, float)) or not 0 < share < 1:
        raise ValueError(f"stripes: share is how much of a pair the first colour takes, above 0 and under 1, "
                         f"not {share!r}")
    return Drawing({"draw": "stripes", "pitch": pitch, "color": _colour("stripes", "color", color),
                    "other": _colour("stripes", "other", other), "share": float(share),
                    "along": _along("stripes", along)})


def grain(color="#a0522d", pitch=12, depth=0.3, along="u", seed=0):
    """A wood grain: streaks about pitch apart running along u or v, lighter and darker than color by depth.

    A drawing for `material(ob, kind, color=grain(...))`: long uneven streaks, about `pitch` apart in the
    program's unit, that waver a little as they run `along` ("u": level on a wall, along X on a top; "v":
    up a wall, along Y on a top). `depth`, 0 to 1, is how far the streaks stray from `color`, darker and
    lighter: their mean is `color`. `seed` picks another board. It repeats every 16 pitches across and 64 along."""
    pitch = _length("grain", "pitch", pitch)
    if isinstance(depth, bool) or not isinstance(depth, (int, float)) or not 0 <= depth <= 1:
        raise ValueError(f"grain: depth is how far the streaks stray from the colour, 0 to 1, not {depth!r}")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError(f"grain: seed is a whole number of 0 or more, not {seed!r}")
    return Drawing({"draw": "grain", "pitch": pitch, "color": _colour("grain", "color", color),
                    "depth": float(depth), "along": _along("grain", along), "seed": seed})


# --- one period of each drawing ---------------------------------------------------------------------------------


def _tiles_period(s):
    return s["w"] + s["joint"], (s["d"] + s["joint"]) * s["shift"][1]


def _tiles_image(s):
    step_u, step_v, rows = s["w"] + s["joint"], s["d"] + s["joint"], s["shift"][1]
    dot = min(s["joint"] / 2, min(s["w"], s["d"]) / 8) if s["joint"] else min(step_u, step_v)
    columns, lines = _dots(step_u, dot), _dots(step_v * rows, dot)
    u, v = _grid(columns, lines, step_u, step_v * rows, fine=4)
    row = np.floor(v / step_v)
    along = np.mod(u - row * step_u * s["shift"][0] / s["shift"][1], step_u)
    joint = (along < s["joint"]) | (np.mod(v, step_v) < s["joint"])
    return _mixed(joint.astype(float), s["color"], s["joint_color"], fine=4)


def _stripes_period(s):
    return s["pitch"], s["pitch"]


def _stripes_image(s):
    columns = _dots(s["pitch"], s["pitch"] * min(s["share"], 1 - s["share"]) / 4)
    u, _ = _grid(columns, 1, s["pitch"], s["pitch"], fine=4)
    drawn = _mixed((u >= s["share"] * s["pitch"]).astype(float), s["color"], s["other"], fine=4)
    return drawn if s["along"] == "v" else drawn.transpose(1, 0, 2)


def _grain_period(s):
    across, length = 16 * s["pitch"], 64 * s["pitch"]
    return (length, across) if s["along"] == "u" else (across, length)


def _grain_image(s):
    rng = np.random.default_rng(s["seed"])
    across, length = np.meshgrid(np.arange(256) / 256, np.arange(256) / 256, indexing="ij")
    waver = sum(a * np.sin(2 * math.pi * (k * length + p)) for k, a, p in
                zip((1, 2, 3), (0.003, 0.0015, 0.001), rng.random(3)))       # a streak strays a twentieth of a pitch
    streak = np.zeros_like(across)
    for turns in (5, 8, 11, 16, 23, 32):                      # per period: about one streak a pitch
        streak += rng.uniform(0.4, 1) * np.sin(2 * math.pi * (turns * (across + waver) + rng.random()))
    streak /= np.abs(streak).max()
    base = _to_linear(np.array(_rgb(s["color"])))
    light = 1 - s["depth"] * streak[..., None] * np.where(streak[..., None] > 0, 1, .5)
    drawn = _to_srgb(np.clip(base * light / light.mean(), 0, 1))      # lighter and darker about the colour: its mean
    return drawn if s["along"] == "u" else drawn.transpose(1, 0, 2)


_PERIOD = {"tiles": _tiles_period, "stripes": _stripes_period, "grain": _grain_period}
_IMAGE = {"tiles": _tiles_image, "stripes": _stripes_image, "grain": _grain_image}


def _dots(period, dot):
    return int(min(max(math.ceil(period / dot), DOTS[0]), DOTS[1]))


def _grid(columns, lines, period_u, period_v, fine):
    """(u, v) at the centre of each of `fine` x `fine` samples of every dot, shape (lines x fine, columns x fine)."""
    u = (np.arange(columns * fine) + .5) / (columns * fine) * period_u
    v = (np.arange(lines * fine) + .5) / (lines * fine) * period_v
    return np.meshgrid(u, v)


def _mixed(share, first, second, fine):
    """`second` where share is 1 and `first` where it is 0, as light mixes, each dot the mean of its samples."""
    a, b = _to_linear(np.array(_rgb(first))), _to_linear(np.array(_rgb(second)))
    linear = a + share[..., None] * (b - a)
    lines, columns = share.shape[0] // fine, share.shape[1] // fine
    return _to_srgb(linear.reshape(lines, fine, columns, fine, 3).mean((1, 3)))


def _rgb(colour):
    return [int(colour[k:k + 2], 16) / 255 for k in (1, 3, 5)]


def _to_linear(c):
    return np.where(c <= .04045, c / 12.92, ((c + .055) / 1.055) ** 2.4)


def _to_srgb(c):
    return np.where(c <= .0031308, c * 12.92, 1.055 * np.clip(c, 0, None) ** (1 / 2.4) - .055)


def _length(verb, name, value, zero=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            or value < 0 or (value == 0 and not zero)):
        raise ValueError(f"{verb}: {name} is a length {'of 0 or more' if zero else 'above 0'}, not {value!r}")
    return float(value)


def _colour(verb, name, value):
    try:
        return _hex(value, name)
    except ValueError as exc:
        raise ValueError(str(exc).replace("material:", f"{verb}:", 1)) from exc


def _along(verb, value):
    if value not in ("u", "v"):
        raise ValueError(f'{verb}: along is "u" or "v", the way it runs on a face, not {value!r}')
    return value


# --- on a part ----------------------------------------------------------------------------------------------------


def picture(drawing):
    """The Blender image of one period, made once for each drawing."""
    name = f"s3d drawing {drawing.key}"
    image = bpy.data.images.get(name)
    if image is None:
        drawn = drawing.image()
        lines, columns = drawn.shape[:2]
        image = bpy.data.images.new(name, columns, lines, alpha=False)
        rgba = np.ones((lines, columns, 4), dtype=np.float32)
        rgba[..., :3] = drawn
        image.pixels.foreach_set(rgba.ravel())
        image.pack()                                   # carried in the file: an export finds it
    return image


def wrap(mesh, drawing):
    """Write where each corner of `mesh` falls in the drawing, in periods: the layer its material reads."""
    period_u, period_v = drawing.period
    corners = len(mesh.loops)
    layer = mesh.uv_layers.get(LAYER) or mesh.uv_layers.new(name=LAYER, do_init=False)
    if not corners:
        return
    index = np.empty(corners, dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", index)
    places = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", places)
    x, y, z = places.reshape(-1, 3)[index].T
    normals = np.empty(len(mesh.polygons) * 3, dtype=np.float64)
    mesh.polygons.foreach_get("normal", normals)
    sizes = np.empty(len(mesh.polygons), dtype=np.int32)
    starts = np.empty(len(mesh.polygons), dtype=np.int32)
    mesh.polygons.foreach_get("loop_total", sizes)
    mesh.polygons.foreach_get("loop_start", starts)
    within = np.arange(corners) - np.repeat(np.cumsum(sizes) - sizes, sizes)    # a corner's rank in its face
    looks = np.empty((corners, 3))
    looks[np.repeat(starts, sizes) + within] = np.repeat(normals.reshape(-1, 3), sizes, axis=0)
    most = np.abs(looks).argmax(1)                      # the side each face looks to most
    sign = np.sign(looks[np.arange(corners), most])
    u = np.where(most == 2, x, np.where(most == 1, -sign * x, sign * y))   # level, to the right of who faces it
    v = np.where(most == 2, y, z)
    uv = np.stack((u / period_u, v / period_v), axis=1).astype(np.float32)
    layer.data.foreach_set("uv", uv.ravel())
    layer.active_render = True
    mesh.uv_layers.active = layer
