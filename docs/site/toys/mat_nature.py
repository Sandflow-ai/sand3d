import math

import sand3d as s3d


def p(kind, size, octaves=1, seed=0, **extra):
    return s3d.pattern(kind, size, octaves=octaves, seed=seed, **extra)


def grain(seed, rings_apart, wobble, bend):
    """Growth rings along V, bent by a noise stretched along the grain, and fibres."""
    rings = p("waves", rings_apart).warp(p("perlin", (wobble, 4 * wobble), 3, seed), bend)
    fibres = p("perlin", (0.4, 18), 3, seed + 1)
    return rings, fibres


def woods():
    oak_rings, oak_fibres = grain(4, 7, 25, 9)
    knots = p("cells", 70, seed=6).levels(0.6, 0.95)
    pine_rings, pine_fibres = grain(20, 9, 40, 6)
    resin = p("cells", 60, seed=22).levels(0.7, 0.95)
    walnut_rings, walnut_fibres = grain(30, 5, 15, 14)
    birch_rings, birch_fibres = grain(40, 3, 50, 3)
    return {
        "oak": ("oak", {}, s3d.texture(
            (60, 140), height=0.03 * oak_rings + 0.03 * oak_fibres - 0.1 * knots,
            color=(0.55 + 0.18 * oak_rings + 0.22 * oak_fibres - 0.5 * knots,
                   "#4a2e18", "#7d5030", "#a8774a", "#c99a68"),
            roughness=(0.5 + 0.5 * oak_fibres, 0.5, 0.75))),
        "pine": ("pine", {}, s3d.texture(
            (60, 140), height=0.04 * pine_rings + 0.02 * pine_fibres,
            color=(0.6 + 0.3 * pine_rings + 0.1 * pine_fibres - 0.6 * resin,
                   "#6b3a14", "#b9773a", "#e2b77c", "#f2d7a6"),
            roughness=(0.5 + 0.5 * pine_fibres - resin, 0.35, 0.7))),
        "walnut": ("walnut", {}, s3d.texture(
            (60, 140), height=0.02 * walnut_rings + 0.03 * walnut_fibres,
            color=(0.5 + 0.2 * walnut_rings + 0.25 * walnut_fibres,
                   "#24140c", "#432819", "#634029", "#82593a"),
            roughness=(0.5 + 0.5 * walnut_fibres, 0.35, 0.55))),
        "birch": ("birch", {}, s3d.texture(
            (60, 140), height=0.01 * birch_rings + 0.02 * birch_fibres,
            color=(0.55 + 0.1 * birch_rings + 0.25 * birch_fibres,
                   "#b89466", "#d4b48a", "#e6cfa8", "#f1e2c4"),
            roughness=(0.5 + 0.5 * birch_fibres, 0.5, 0.7))),
    }


def barks():
    furrows = p("ridged", (9, 60), 3, 50).warp(p("perlin", (30, 80), 2, 51), 5)
    plates = p("plates", (11, 26), 1, 60).warp(p("perlin", 12, 3, 61), 1.5)
    flakes = p("turbulence", (5, 3), 3, 62)
    shade = p("perlin", (20, 30), 2, 63)
    lenticels = p("strands", (14, 1.2), seed=70, density=2, spread=8)
    scars = p("perlin", (60, 25), 3, 71).levels(0.35, 0.6)
    peel = p("perlin", (40, 12), 3, 72)
    mottle = p("perlin", 30, 4, 80)
    lichen = p("cells", 12, 2, 81).levels(0.3, 0.8) * p("perlin", 50, 2, 82).levels(0.2, 0.6)
    return {
        "oak bark": ("bark", {}, s3d.texture(
            (60, 120), height=3 * furrows,
            color=(0.5 + 0.4 * furrows + 0.1 * mottle, "#1f1914", "#3d3229", "#62574b", "#857b6c"),
            roughness=(furrows.levels(-1, 1), 0.95, 0.8))),
        "pine bark": ("bark", {}, s3d.texture(
            (60, 120), height=2.5 * plates.levels(0, 0.6) + 0.5 * flakes,
            color=(plates.levels(0.03, 0.4) * (0.5 + 0.3 * shade + 0.25 * flakes),
                   "#140d09", "#5a2c18", "#8f4a28", "#b5703f", "#9a8676"),
            roughness=(plates.levels(0, 0.3), 1.0, 0.8))),
        "birch bark": ("birch", dict(roughness=0.6), s3d.texture(
            (60, 120), height=-0.3 * lenticels - 0.6 * scars + 0.1 * peel,
            color=(0.85 + 0.12 * peel - 0.9 * lenticels - 0.9 * scars,
                   "#1c1a18", "#5e5a54", "#d9d4c8", "#f3f0e8"),
            roughness=(lenticels + scars, 0.55, 0.9))),
        "beech bark": ("bark", {}, s3d.texture(
            (60, 120), height=0.15 * mottle + 0.2 * lichen,
            color=(0.45 + 0.35 * mottle + 0.4 * lichen, "#3e403f", "#5f625f", "#81847f", "#8f9a68"),
            roughness=(0.5 + 0.5 * mottle, 0.6, 0.8))),
    }


def stones():
    joints = p("cells", 26, 2, 8)
    cracks = p("ridged", 45, 2, 9).levels(0.7, 0.95)
    blotch = p("perlin", 35, 4, 7)
    grit = p("turbulence", 2.5, 3, 10)
    speckle = p("cells", 1.6, 2, 90)
    layers = p("perlin", (300, 6), 3, 91).warp(p("perlin", 60, 2, 92), 3)
    moss = p("perlin", 40, 4, 94).levels(0.0, 0.35)
    fuzz = p("turbulence", 1.5, 3, 95)
    return {
        "rock": ("rock", {}, s3d.texture(
            80, height=0.8 * joints + 0.15 * grit - 0.8 * cracks,
            color=(0.5 + 0.5 * blotch + 0.15 * joints + 0.12 * grit - 0.5 * cracks,
                   "#2f2c29", "#55514b", "#7d786e", "#a39d90"),
            roughness=(0.5 + 0.5 * grit, 0.75, 0.95))),
        "granite": ("rock", dict(roughness=0.6), s3d.texture(
            40, height=0.08 * speckle + 0.05 * grit,
            color=(0.5 + 0.5 * speckle + 0.15 * blotch,
                   "#1d1c1e", "#7a7372", "#c9a9a0", "#e9e1dc"),
            roughness=(0.5 + 0.5 * speckle, 0.35, 0.7))),
        "sandstone": ("rock", {}, s3d.texture(
            80, height=0.6 * layers + 0.1 * grit,
            color=(0.5 + 0.4 * layers + 0.1 * grit, "#7a5a3a", "#a88158", "#c9a77c", "#e0c9a0"),
            roughness=(0.5 + 0.5 * grit, 0.85, 0.98))),
        "mossy rock": ("rock", {}, s3d.texture(
            80, height=0.6 * joints - 0.6 * cracks + 0.5 * moss * (0.6 + 0.4 * fuzz),
            color=(0.45 * (0.5 + 0.5 * blotch) * (1 - moss) + moss * (0.75 + 0.25 * fuzz),
                   "#3a3934", "#6f6c63", "#4f6a2a", "#7d9a3c"),
            roughness=(moss, 0.85, 1.0))),
    }


def crystals():
    facets = p("creases", 14, 2, 11)
    glow = p("perlin", 25, 2, 12)
    frost = p("cells", 9, seed=13).levels(0.4, 0.9)
    veils = p("perlin", (8, 40), 3, 14).levels(0.2, 0.7)
    flaws = p("cells", 18, 2, 15).levels(0.5, 0.95)
    return {
        "amethyst": ("glass", dict(transmission=0.85, ior=1.54), s3d.texture(
            40, height=0.25 * facets,
            color=(0.5 + 0.5 * glow, "#4b2a8c", "#8a5cd6", "#d2b8ff"),
            roughness=(frost, 0.02, 0.35))),
        "quartz": ("glass", dict(transmission=0.95, ior=1.54), s3d.texture(
            40, height=0.2 * facets,
            color=(veils, "#e9eef2", "#ffffff"),
            roughness=(veils, 0.0, 0.45))),
        "emerald": ("glass", dict(transmission=0.8, ior=1.58), s3d.texture(
            40, height=0.2 * facets,
            color=(0.6 + 0.4 * glow - 0.6 * flaws, "#0b3d24", "#17824a", "#5fd08e"),
            roughness=(flaws, 0.02, 0.3))),
        "citrine": ("glass", dict(transmission=0.85, ior=1.54), s3d.texture(
            40, height=0.25 * facets,
            color=(0.5 + 0.5 * glow, "#a4470c", "#e8901f", "#ffd36b"),
            roughness=(frost, 0.02, 0.3))),
    }


def plank(name, k):
    return s3d.fillet(s3d.box(name, 50, 90, 22), 2)


def trunk(name, k):
    return s3d.cylinder(name, 56, 80)


def boulder(name, k):
    points = []
    for i in range(40):
        z = 1 - 2 * (i + 0.5) / 40
        turn = i * math.pi * (3 - math.sqrt(5))
        r = 36 + 6 * math.sin(3.1 * i + k) * math.cos(1.7 * i + 2 * k)
        flat = math.sqrt(1 - z * z)
        points.append((r * flat * math.cos(turn), r * flat * math.sin(turn) * 0.85, 20 * (1 + z)))
    return s3d.hull(name, points)


def crystal(name, k):
    points = []
    for i in range(6):
        a = math.pi / 3 * i
        points.append((16 * math.cos(a), 16 * math.sin(a), 0))
        points.append((18 * math.cos(a), 18 * math.sin(a), 62))
    points.append((2, 1, 92))
    return s3d.hull(name, points)


def nature():
    pitch, label_size = 140, 11
    rows = [(woods(), plank), (barks(), trunk), (stones(), boulder), (crystals(), crystal)]
    frames = iter(s3d.grid(4, 4, pitch, -pitch))
    parts = []
    for looks, shape in rows:
        for k, (name, (kind, extra, tex)) in enumerate(looks.items()):
            frame = next(frames)
            tile = s3d.box("tile", pitch - 8, pitch - 8, 2)
            s3d.material(tile, "plastic", color="#667481")
            piece = shape(name.replace(" ", "_"), k)
            s3d.material(piece, kind, texture=tex, **extra)
            s3d.unwrap(piece)
            label = s3d.extrude("label", s3d.text(name, label_size), 1)
            s3d.material(label, "plastic", color="#ffffff")
            parts.extend([s3d.at(tile, on=frame), s3d.at(piece, on=frame, z=2),
                          s3d.at(label, on=frame, y=-pitch / 2 + 16, z=2)])
    return s3d.assembly("nature", parts)
