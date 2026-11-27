"""Procedural textures: patterns that tile, put together, baked into a material's maps.

A `pattern` is a function of the surface, in program units: noise, fibres, creases, plates, bubbles,
waves. Patterns add, multiply and mix like numbers. A `texture` is what they do to a surface
over one tile: a height, a colour, a roughness. `material(texture=)` wears it; at the scale
`unwrap` gave the part, so a tile of 60 mm covers 60 mm of the part, in whatever part.

Everything is numpy, seeded and periodic: the same maps in every run, and no seam between tiles.
"""
from contextlib import contextmanager
from functools import lru_cache
import json
import math

import bpy
import numpy as np

from . import _core
from .implicit import _mix

#: The patterns, and the range of their values.
KINDS = ("perlin", "ridged", "turbulence", "cells", "creases", "strands", "bubbles", "waves", "plates")


class Pattern:
    """What `pattern` returns: a value at every point of a surface. `+ - * /` with numbers and
    other patterns; `abs`, `min`, `max`, `clip`, `levels`, `warp`. Called with x, y (z is not
    read), its value there, on the plane and not tiled: what `displace(noise=)` takes."""

    def __init__(self, spec):
        self.spec = spec

    def _with(self, op, other, swap=False):
        if isinstance(other, Pattern):
            other = other.spec
        elif isinstance(other, bool) or not isinstance(other, (int, float)) or not math.isfinite(other):
            return NotImplemented
        else:
            other = float(other)
        return Pattern([op, other, self.spec] if swap else [op, self.spec, other])

    def __add__(self, other):
        return self._with("+", other)

    def __radd__(self, other):
        return self._with("+", other, True)

    def __sub__(self, other):
        return self._with("-", other)

    def __rsub__(self, other):
        return self._with("-", other, True)

    def __mul__(self, other):
        return self._with("*", other)

    def __rmul__(self, other):
        return self._with("*", other, True)

    def __truediv__(self, other):
        return self._with("/", other)

    def __neg__(self):
        return self._with("*", -1)

    def __abs__(self):
        return Pattern(["abs", self.spec])

    def max(self, other):
        """The greater of the two, at each point."""
        return self._with("max", other)

    def min(self, other):
        """The lesser of the two, at each point."""
        return self._with("min", other)

    def clip(self, low=0, high=1):
        """Held between `low` and `high`."""
        return self.max(low).min(high)

    def levels(self, low, high):
        """0 up to `low`, 1 from `high`, smooth between: what a pattern picks out."""
        if not low < high:
            raise ValueError(f"levels: low={low!r} is not under high={high!r}")
        return Pattern(["levels", self.spec, float(low), float(high)])

    def warp(self, other, amount):
        """Read at points pushed about by `other`, up to `amount` (a length)."""
        if not isinstance(other, Pattern):
            raise TypeError("warp: a pattern is expected")
        return Pattern(["warp", self.spec, other.spec, float(amount)])

    def __call__(self, x, y, z=0):
        out = evaluate(self.spec, np.asarray(x, float), np.asarray(y, float), None)
        return out if np.ndim(x) or np.ndim(y) else float(out)


class Texture:
    """What `texture` returns: what `material(texture=)` takes."""

    def __init__(self, spec):
        self.spec = spec


def _pair(verb, name, value):
    pair = value if isinstance(value, (tuple, list)) else (value, value)
    if len(pair) != 2 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0
                             for v in pair):
        raise ValueError(f"{verb}: {name}={value!r} is neither a length nor a pair of lengths")
    return [float(v) for v in pair]


def pattern(kind, size, octaves=1, seed=0, density=None, spread=180):
    """A tileable pattern: perlin ridged turbulence cells creases strands bubbles waves plates.

    `size` is how far its features are apart, in program units; a pair sets it along U and
    along V (a brushed metal is perlin of size (60, 0.2)). `octaves` adds as many finer copies,
    each half the size and half the strength. The same `seed`, the same pattern.

    - "perlin", "ridged", "turbulence", "cells": the noises of `displace`, in -1..1;
    - "creases": flat facets at all angles meeting in sharp folds, a crumpled sheet, in -1..1;
    - "strands": short fibres, 0 between them, 1 on them; `size` is (length, width), `density`
      how many in a square of their length (3), `spread` the angle they lie within, about U;
    - "bubbles": domes in staggered rows, 0 between them, 1 on top; `density` is the share of
      the pitch a bubble takes (0.85);
    - "waves": a cosine along U, in -1..1;
    - "plates": cells split by straight cracks, 0 on a crack, rising to 1 a quarter of a cell
      inside: bark, dried mud, cracked paint."""
    if kind not in KINDS:
        raise ValueError(f"pattern: {kind!r} is none of {KINDS}")
    pair = _pair("pattern", "size", size)
    if isinstance(octaves, bool) or not isinstance(octaves, int) or not 1 <= octaves <= 10:
        raise ValueError("pattern: octaves must be a whole number from 1 to 10")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("pattern: seed must be an integer")
    default = {"strands": 3, "bubbles": 0.85}.get(kind)
    if density is not None and default is None:
        raise ValueError(f"pattern: density goes with strands and bubbles, not {kind!r}")
    density = default if density is None else density
    if kind == "bubbles" and not 0 < density <= 1 or kind == "strands" and not 1 <= density <= 32:
        raise ValueError(f"pattern: density={density!r} is out of range for {kind!r}")
    return Pattern([kind, *pair, octaves, seed, float(density or 0), float(spread)])


def texture(tile, height=None, color=None, roughness=None, px=512, flow=None):
    """What patterns do to a surface, over one `tile` (a length, or a pair along U and V).

    `height` is a pattern of heights, in program units: it turns the light as relief does,
    and moves no point. `color` is (pattern, "#low", …, "#high"): the colours of the values
    0 to 1 of the pattern, evenly spaced. `roughness` is (pattern, low, high), its values at
    0 and 1. `px` is the side of the maps. Worn with `material(texture=)`, on parts `unwrap`
    has been called on; the maps go in the GLB, other formats keep the material's colour.

    `flow` sets the texture moving: (along U, along V) in program units a second, or one
    number along V. The GLB loops it, a whole number of tiles a loop, so it runs without a
    seam: each speed is rounded to close the loop. Running water, drifting clouds, lava."""
    from .materials import _hex
    pair = _pair("texture", "tile", tile)
    spec = {"tile": pair, "px": px}
    if isinstance(px, bool) or not isinstance(px, int) or not 16 <= px <= 4096:
        raise ValueError("texture: px must be a whole number from 16 to 4096")
    if height is not None:
        if not isinstance(height, Pattern):
            raise TypeError("texture: height is a pattern, times a length")
        spec["height"] = height.spec
    if color is not None:
        if not isinstance(color, (tuple, list)) or len(color) < 3 or not isinstance(color[0], Pattern):
            raise TypeError('texture: color is (pattern, "#low", …, "#high")')
        spec["color"] = [color[0].spec, *(_hex(c, "color") for c in color[1:])]
    if roughness is not None:
        if (not isinstance(roughness, (tuple, list)) or len(roughness) != 3 or not isinstance(roughness[0], Pattern)
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1 for v in roughness[1:])):
            raise TypeError("texture: roughness is (pattern, low, high), low and high from 0 to 1")
        spec["roughness"] = [roughness[0].spec, float(roughness[1]), float(roughness[2])]
    if len(spec) == 2:
        raise ValueError("texture: give a height, a color or a roughness")
    if flow is not None:
        spec["flow"] = _flow(flow)
    return Texture(json.loads(json.dumps(spec)))


def _flow(flow):
    pair = (0, flow) if isinstance(flow, (int, float)) and not isinstance(flow, bool) else flow
    if (not isinstance(pair, (tuple, list)) or len(pair) != 2
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in pair)):
        raise ValueError(f"texture: flow={flow!r} is neither a speed nor a pair of speeds")
    if not any(pair):
        raise ValueError("texture: flow must move along U or V")
    return [float(v) for v in pair]


#: The frame rate a flowing texture's loop is counted in.
FPS = 24


def loop(spec, frames=None):
    """How a flowing texture loops: (frames, tiles along U, tiles along V), whole numbers.

    By default the loop lasts as long as the slowest axis takes to cross one tile, rounded to
    a frame; given `frames`, it lasts that long. In that time each axis crosses a whole
    number of tiles, at least one where it moves."""
    tile, flow = spec["tile"], spec["flow"]
    if frames is None:
        crossing = max(t / abs(f) for t, f in zip(tile, flow) if f)
        frames = max(1, round(crossing * FPS))
    tiles = [0 if not f else int(math.copysign(max(1, round(abs(f) * frames / FPS / t)), f))
             for t, f in zip(tile, flow)]
    return frames, *tiles


# ---------------------------------------------------------------- values

def _hash(i, j, seed):
    with np.errstate(over="ignore"):
        h = np.asarray(i, np.int64).astype(np.uint32) * np.uint32(1597334677)
        h = h ^ np.asarray(j, np.int64).astype(np.uint32) * np.uint32(3812015801)
    return _mix(h, seed)


def _unit(i, j, seed):
    """A number in 0..1 for a cell."""
    return _hash(i, j, seed).astype(np.float64) / 4294967296


def _wrap(i, n):
    return i if n is None else np.mod(i, n)


def _grid(u, v, size, period):
    """Points in cells of `size`, and how many cells the period has: a whole number."""
    if period is None:
        return u / size[0], v / size[1], (None, None), (1.0, 1.0)
    n = [max(1, round(p / s)) for p, s in zip(period, size)]
    return u * n[0] / period[0], v * n[1] / period[1], n, tuple(p / (k * s) for p, k, s in zip(period, n, size))


def _perlin(x, y, n, seed):
    i, j = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    fx, fy = x - i, y - j
    wx, wy = (f * f * f * (f * (f * 6 - 15) + 10) for f in (fx, fy))
    out = np.zeros(np.broadcast(x, y).shape)
    for a in (0, 1):
        for b in (0, 1):
            angle = 2 * np.pi * _unit(_wrap(i + a, n[0]), _wrap(j + b, n[1]), seed)
            dot = np.cos(angle) * (fx - a) + np.sin(angle) * (fy - b)
            out += (wx if a else 1 - wx) * (wy if b else 1 - wy) * dot
    return np.clip(out * math.sqrt(2), -1, 1)


def _cells(x, y, n, seed):
    i, j = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    best = np.full(np.broadcast(x, y).shape, np.inf)
    for a in (-1, 0, 1):
        for b in (-1, 0, 1):
            ci, cj = _wrap(i + a, n[0]), _wrap(j + b, n[1])
            dx = i + a + _unit(ci, cj, seed + 1) - x
            dy = j + b + _unit(ci, cj, seed + 2) - y
            best = np.minimum(best, dx * dx + dy * dy)
    return 1 - 2 * np.minimum(1, np.sqrt(best))


def _plates(x, y, n, seed):
    """The gap between the nearest and the second nearest cell point: 0 where two cells meet."""
    i, j = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    first = np.full(np.broadcast(x, y).shape, np.inf)
    second = np.full(first.shape, np.inf)
    for a in (-2, -1, 0, 1, 2):
        for b in (-2, -1, 0, 1, 2):
            ci, cj = _wrap(i + a, n[0]), _wrap(j + b, n[1])
            dx = i + a + _unit(ci, cj, seed + 1) - x
            dy = j + b + _unit(ci, cj, seed + 2) - y
            d = np.sqrt(dx * dx + dy * dy)
            second = np.where(d < first, first, np.minimum(second, d))
            first = np.minimum(first, d)
    return np.clip((second - first) / 0.5, 0, 1)


def _creases(x, y, n, seed):
    """The upper envelope of tilted facets, one a cell."""
    i, j = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    best = np.full(np.broadcast(x, y).shape, -np.inf)
    for a in (-2, -1, 0, 1, 2):
        for b in (-2, -1, 0, 1, 2):
            ci, cj = _wrap(i + a, n[0]), _wrap(j + b, n[1])
            dx = x - (i + a + _unit(ci, cj, seed + 1))
            dy = y - (j + b + _unit(ci, cj, seed + 2))
            tilt, way = 1.1 * np.sqrt(_unit(ci, cj, seed + 3)), 2 * np.pi * _unit(ci, cj, seed + 4)
            rise = 0.5 * _unit(ci, cj, seed + 5)
            best = np.maximum(best, rise + tilt * (np.cos(way) * dx + np.sin(way) * dy) - 0.55 * (dx * dx + dy * dy))
    return np.clip(1.6 * (best - 0.45), -1, 1)


def _strands(u, v, size, period, seed, density, spread):
    length, width = size
    x, y, n, ratio = _grid(u, v, (length, length), period)
    i, j = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    out = np.zeros(np.broadcast(x, y).shape)
    half = 0.5 * width / length
    for a in (-1, 0, 1):
        for b in (-1, 0, 1):
            ci, cj = _wrap(i + a, n[0]), _wrap(j + b, n[1])
            for k in range(int(round(density))):
                s = seed + 17 * k
                dx = x - (i + a + _unit(ci, cj, s + 1))
                dy = y - (j + b + _unit(ci, cj, s + 2))
                way = np.radians(spread) * (_unit(ci, cj, s + 3) - 0.5)
                bend = 1.2 * (_unit(ci, cj, s + 6) - 0.5)
                long = 0.25 + 0.25 * _unit(ci, cj, s + 4)
                along = np.cos(way) * dx + np.sin(way) * dy
                across = -np.sin(way) * dx + np.cos(way) * dy + bend * (along * along)
                gone = np.maximum(np.abs(along) - long, 0)
                d = np.sqrt(across * across + gone * gone) / half
                out = np.maximum(out, np.clip(1.5 - d, 0, 1) * (0.4 + 0.6 * _unit(ci, cj, s + 5)))
    return out


def _bubbles(u, v, size, period, density):
    pitch = size
    x, y, _, _ = _grid(u, v, (pitch[0], pitch[1] * math.sqrt(3)), period)
    best = np.full(np.broadcast(x, y).shape, np.inf)
    for shift in ((0.25, 0.25), (0.75, 0.75)):
        dx, dy = x - shift[0], y - shift[1]
        dx, dy = dx - np.round(dx), (dy - np.round(dy)) * math.sqrt(3)
        best = np.minimum(best, dx * dx + dy * dy)
    r = np.sqrt(best) / (0.5 * density)
    return np.sqrt(np.clip(1 - np.clip(r, 0, 1) ** 3, 0, 1))


def evaluate(spec, u, v, period):
    """A pattern's values at points (u, v); `period` (along U, along V) makes it repeat."""
    if isinstance(spec, (int, float)):
        return np.full(np.broadcast(u, v).shape, float(spec))
    op = spec[0]
    if op in ("+", "-", "*", "/", "max", "min"):
        a, b = (evaluate(s, u, v, period) for s in spec[1:])
        return {"+": np.add, "-": np.subtract, "*": np.multiply, "/": np.divide,
                "max": np.maximum, "min": np.minimum}[op](a, b)
    if op == "abs":
        return np.abs(evaluate(spec[1], u, v, period))
    if op == "levels":
        t = np.clip((evaluate(spec[1], u, v, period) - spec[2]) / (spec[3] - spec[2]), 0, 1)
        return t * t * (3 - 2 * t)
    if op == "warp":
        reach = spec[3]
        far = (0.37 * period[0], 0.61 * period[1]) if period else (91 * reach, 73 * reach)
        du = evaluate(spec[2], u, v, period)
        dv = evaluate(spec[2], u + far[0], v + far[1], period)
        return evaluate(spec[1], u + reach * du, v + reach * dv, period)
    kind, size, octaves, seed, density, spread = spec[0], spec[1:3], spec[3], spec[4], spec[5], spec[6]
    total, weight = 0.0, 0.0
    for o in range(octaves):
        k, s = 0.5 ** o, seed + 101 * o
        small = [x * k for x in size]
        if kind == "strands":
            value = _strands(u, v, small, period, s, density, spread)
        elif kind == "bubbles":
            value = _bubbles(u, v, small, period, density)
        else:
            x, y, n, _ = _grid(u, v, small, period)
            if kind == "waves":
                value = np.cos(2 * np.pi * x) + 0.0 * y
            elif kind == "cells":
                value = _cells(x, y, n, s)
            elif kind == "plates":
                value = _plates(x, y, n, s)
            elif kind == "creases":
                value = _creases(x, y, n, s)
            else:
                value = _perlin(x, y, n, s)
                value = 1 - 2 * np.abs(value) if kind == "ridged" else 2 * np.abs(value) - 1 if kind == "turbulence" else value
        total, weight = total + k * value, weight + k
    return total / weight


# ---------------------------------------------------------------- maps

def maps(spec):
    """The maps of a texture: {"color", "roughness", "normal"}, uint8, the first row at V = 0."""
    tile, px = spec["tile"], spec["px"]
    u = (np.arange(px) + 0.5) / px * tile[0]
    v = (np.arange(px) + 0.5) / px * tile[1]
    u, v = np.meshgrid(u, v)
    out = {}
    if "color" in spec:
        values = np.clip(evaluate(spec["color"][0], u, v, tile), 0, 1)
        stops = np.array([[int(c[k:k + 2], 16) for k in (1, 3, 5)] for c in spec["color"][1:]], float)
        at = values * (len(stops) - 1)
        low = np.minimum(at.astype(int), len(stops) - 2)
        t = (at - low)[..., None]
        out["color"] = np.round(stops[low] * (1 - t) + stops[low + 1] * t).astype(np.uint8)
    if "roughness" in spec:
        values = np.clip(evaluate(spec["roughness"][0], u, v, tile), 0, 1)
        low, high = spec["roughness"][1:]
        grey = np.round(255 * (low + (high - low) * values)).astype(np.uint8)
        white = np.full_like(grey, 255)                      # glTF reads G, and multiplies the metalness by B
        out["roughness"] = np.stack((white, grey, white), axis=2)
    if "height" in spec:
        h = evaluate(spec["height"], u, v, tile)
        dx = (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)) * px / (2 * tile[0])
        dy = (np.roll(h, -1, axis=0) - np.roll(h, 1, axis=0)) * px / (2 * tile[1])
        n = np.stack((-dx, -dy, np.ones_like(h)), axis=2)
        n /= np.sqrt((n * n).sum(axis=2, keepdims=True))
        out["normal"] = np.round(127.5 + 127.5 * n).astype(np.uint8)
    return out


@lru_cache(maxsize=256)
def _mean(key):
    spec = json.loads(key)
    small = maps({"tile": spec["tile"], "px": 64, "color": spec["color"]})["color"]
    return "#" + "".join(f"{int(round(c)):02x}" for c in small.reshape(-1, 3).mean(axis=0))


def mean_color(spec):
    """The colour a texture has from afar, "#rrggbb" — or None where it sets none."""
    return _mean(json.dumps(spec, sort_keys=True)) if "color" in spec else None


def _image(spec, name):
    """The Blender image of one map, made once per texture."""
    source = {"normal": "height"}.get(name, name)
    spec = {k: v for k, v in spec.items() if k in ("tile", "px", source)}
    key = json.dumps([name, spec], sort_keys=True)
    for image in bpy.data.images:
        if image.get("s3d~map") == key:
            return image
    data = maps(spec)[name]
    px = spec["px"]
    image = bpy.data.images.new(f"{name} map", px, px, alpha=False)
    image.colorspace_settings.name = "sRGB" if name == "color" else "Non-Color"
    flat = np.ones((px, px, 4), np.float32)
    flat[..., :3] = data / np.float32(255)
    image.pixels.foreach_set(flat.ravel())
    image.update()
    image["s3d~map"] = key
    return image


def dress(mat, spec, side):
    """Put a texture's maps on a material, at the scale of an atlas `side` across."""
    tree = mat.node_tree
    bsdf = tree.nodes["Principled BSDF"]
    coords = tree.nodes.new("ShaderNodeTexCoord")
    place = tree.nodes.new("ShaderNodeMapping")
    place.name, place.label = "Tile", repr(side)
    place.inputs["Scale"].default_value = (side / spec["tile"][0], side / spec["tile"][1], 1)
    tree.links.new(coords.outputs["UV"], place.inputs["Vector"])

    def node(name):
        n = tree.nodes.new("ShaderNodeTexImage")
        n.name = name
        n.image = _image(spec, name)
        tree.links.new(place.outputs["Vector"], n.inputs["Vector"])
        return n
    if "color" in spec:
        tree.links.new(node("color").outputs["Color"], bsdf.inputs["Base Color"])
    if "roughness" in spec:
        split = tree.nodes.new("ShaderNodeSeparateColor")
        tree.links.new(node("roughness").outputs["Color"], split.inputs["Color"])
        tree.links.new(split.outputs["Green"], bsdf.inputs["Roughness"])
    if "height" in spec:
        bend = tree.nodes.new("ShaderNodeNormalMap")
        tree.links.new(node("normal").outputs["Color"], bend.inputs["Color"])
        tree.links.new(bend.outputs["Normal"], bsdf.inputs["Normal"])


@contextmanager
def flowing(moving):
    """Slide the textures of `moving`, [(material, texture spec)], while a GLB is written, and
    give the exporter's settings for it. All share one loop, the longest of theirs, so the GLB
    holds one animation that runs without a seam; afterwards the materials are as they were."""
    moving = [(m, spec) for m, spec in moving if "flow" in spec and m.node_tree.nodes.get("Tile")]
    if not moving:
        yield {}
        return
    frames = max(loop(spec)[0] for _, spec in moving)
    edit = bpy.context.preferences.edit
    was = edit.keyframe_new_interpolation_type
    edit.keyframe_new_interpolation_type = "LINEAR"
    try:
        for mat, spec in moving:
            _, along_u, along_v = loop(spec, frames)
            where = mat.node_tree.nodes["Tile"].inputs["Location"]
            for frame, share in ((0, 0.0), (frames, 1.0)):
                where.default_value = (-along_u * share, -along_v * share, 0)  # the picture moves with the flow
                where.keyframe_insert("default_value", frame=frame)
            where.default_value = (0, 0, 0)
            held = mat.node_tree.animation_data
            action = held.action
            action.name = f"flow {mat.name}"
            track = held.nla_tracks.new()
            track.name = "flow"                          # one name: the GLB merges them in one animation
            track.strips.new("flow", 0, action)
            held.action = None
    finally:
        edit.keyframe_new_interpolation_type = was
    try:
        yield dict(export_animation_mode="NLA_TRACKS", export_pointer_animation=True)
    finally:
        for mat, _ in moving:
            held = mat.node_tree.animation_data
            for track in list(held.nla_tracks):
                action = track.strips[0].action if track.strips else None
                held.nla_tracks.remove(track)
                if action is not None and action.users == 0:
                    bpy.data.actions.remove(action)
            mat.node_tree.animation_data_clear()


# ---------------------------------------------------------------- decals

#: Object property: a sheet `decal` made, which keeps its own UVs. Image property: the digest of its file.
DECAL, PICTURE = "s3d~decal", "s3d~picture"


def _picture(path):
    """The Blender image of a file, packed, once per content: (image, digest)."""
    import hashlib
    import os
    path = os.fspath(path)
    try:
        with open(path, "rb") as file:
            digest = hashlib.sha1(file.read()).hexdigest()[:16]
    except OSError as error:
        raise ValueError(f"decal: cannot read the image {path!r}: {error.strerror}") from None
    for image in bpy.data.images:
        if image.get(PICTURE) == digest:
            return image, digest
    try:
        image = bpy.data.images.load(path, check_existing=False)
        size = tuple(image.size)
    except RuntimeError:
        size = (0, 0)
    if 0 in size:
        raise ValueError(f"decal: {path!r} is not an image Blender reads")
    image.name = os.path.splitext(os.path.basename(path))[0]
    image.pack()
    image[PICTURE] = digest
    return image, digest


def decal(name, image, w, h=None, roughness=0.5):
    """A printed sheet: an image file (PNG, JPEG) on a flat rectangle, where its alpha lets it show.

    `w` across, `h` up (the image's own proportions by default), centred, on Z = 0, facing +Z:
    place it on a face, a hair above it, `at(label, on=part.face("+X"), y=40, z=0.1)`, or `lay`
    it on a curved one. It has no thickness and its own UVs, which `unwrap` leaves alone; the
    image goes into the GLB."""
    for key, value in (("w", w), ("h", h)):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                  or not math.isfinite(value) or value <= 0):
            raise ValueError(f"decal: {key}={value!r} is not a length over 0")
    if isinstance(roughness, bool) or not isinstance(roughness, (int, float)) or not 0 <= roughness <= 1:
        raise ValueError(f"decal: roughness={roughness!r} is not a number between 0 and 1")
    picture, digest = _picture(image)
    if h is None:
        h = w * picture.size[1] / picture.size[0]
    from . import materials
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(-w / 2, -h / 2, 0), (w / 2, -h / 2, 0), (w / 2, h / 2, 0), (-w / 2, h / 2, 0)], [], [(0, 1, 2, 3)])
    layer = mesh.uv_layers.new(name="UVMap")
    layer.data.foreach_set("uv", [0, 0, 1, 0, 1, 1, 0, 1])
    for key in (_core.tag_key(_core.FACE_TAG, "top"), _core.tag_key(_core.FACE_TAG, f"{name}.top")):
        mesh.attributes.new(key, "BOOLEAN", "FACE").data[0].value = True
    ob = _core.new_mesh_object(name, mesh)
    ob[_core.NAME] = name
    ob[DECAL] = True
    values = np.empty(4 * picture.size[0] * picture.size[1], np.float32)
    picture.pixels.foreach_get(values)
    values = values.reshape(-1, 4)
    weight = values[:, 3].astype(float)
    mean = (values[:, :3] * weight[:, None]).sum(axis=0) / max(weight.sum(), 1e-9)
    color = "#" + "".join(f"{int(round(255 * min(max(float(c), 0), 1))):02x}" for c in mean)
    ob[materials.TAG] = json.dumps({"kind": "plastic", "color": color, "roughness": float(roughness),
                                    "picture": digest}, sort_keys=True)
    _core.dressed = True
    return ob


def print_on(mat, digest):
    """Put a decal's image, and its alpha if it has one, on its material."""
    picture = next((i for i in bpy.data.images if i.get(PICTURE) == digest), None)
    if picture is None:
        return
    tree = mat.node_tree
    bsdf = tree.nodes["Principled BSDF"]
    node = tree.nodes.new("ShaderNodeTexImage")
    node.name, node.image, node.extension = "picture", picture, "CLIP"
    tree.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
    if picture.depth == 32:
        tree.links.new(node.outputs["Alpha"], bsdf.inputs["Alpha"])
        mat.surface_render_method = "BLENDED"


def atlas_side(ob):
    """How many program units the atlas of a part is across, or None for a part not unwrapped."""
    from .uvs import REPORT
    if REPORT not in ob or not ob.data.uv_layers:
        return None
    return json.loads(ob[REPORT])["side_mm"] / _core.in_mm(1.0)
