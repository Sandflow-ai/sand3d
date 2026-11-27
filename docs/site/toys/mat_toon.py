import math

import sand3d as s3d


def p(kind, size, octaves=1, seed=0, **extra):
    return s3d.pattern(kind, size, octaves=octaves, seed=seed, **extra)


def step(pattern, at):
    """A hard edge where the pattern crosses `at`: 0 below, 1 above."""
    return pattern.levels(at - 0.02, at + 0.02)


def flat(tile, pattern, *tones, flow=None):
    """A toon texture: no relief, flat tones picked by a stepped pattern (0, 0.5, 1 ...)."""
    return s3d.texture(tile, color=(pattern, *tones), px=256, flow=flow)


def woods():
    def grain(seed, wobble):
        streaks = p("perlin", (8, 70), 2, seed).warp(p("perlin", (40, 120), 1, seed + 1), wobble)
        knots = step(p("cells", 80, seed=seed + 2), 0.8)
        return 0.5 * step(streaks, -0.15) + 0.5 * step(streaks, 0.25) - knots
    return {
        "oak": flat((60, 140), grain(1, 8), "#6b4426", "#8f5e33", "#b07a45"),
        "pine": flat((60, 140), grain(5, 5), "#b07a45", "#c99257", "#e0b072"),
        "walnut": flat((60, 140), grain(9, 12), "#3f2618", "#57351f", "#6e4630"),
        "birch": flat((60, 140), grain(13, 3), "#c4a776", "#d8c08f", "#ecd9b0"),
    }


def barks():
    furrows = p("ridged", (12, 80), 2, 20).warp(p("perlin", (30, 90), 1, 21), 6)
    plates = p("plates", (14, 30), 1, 30).warp(p("perlin", 14, 2, 31), 1.5)
    dashes = p("strands", (20, 2.5), seed=40, density=2, spread=6)
    patches = p("perlin", 35, 2, 50)
    rings = p("perlin", (300, 7), 1, 51).warp(p("perlin", 40, 1, 52), 2)
    scales = p("plates", (16, 10), 1, 53)
    return {
        "oak bark": flat((60, 120), 1 - 0.5 * step(furrows, 0.55) - 0.5 * step(furrows, 0.8),
                         "#433428", "#584638", "#6e5a4a"),
        "pine bark": flat((60, 120), 0.5 * step(plates, 0.12) + 0.5 * step(plates, 0.55),
                          "#6e3420", "#b05a30", "#c9703f"),
        "birch bark": flat((60, 120), 1 - step(dashes, 0.15) - 0.5 * step(patches, 0.55),
                           "#3b3835", "#c8c4ba", "#f2efe6"),
        "beech bark": flat((60, 120), step(patches, 0.15), "#858c86", "#9aa19b"),
        "palm bark": flat((60, 120), 0.5 * step(rings, 0.0) + 0.5 * step(scales, 0.25),
                          "#5e4430", "#7a5a3e", "#957452"),
    }


def grounds():
    """Ground and desert: grass, sand, cactus skin and the layered rock of cliffs."""
    tufts = p("perlin", 60, 2, 90)
    blades = p("cells", 6, seed=91)
    ripples = p("waves", 10).warp(p("perlin", 40, 2, 92), 6)
    dunes = p("perlin", 70, 1, 93)
    ribs = p("perlin", (5, 300), 1, 94).warp(p("perlin", 60, 1, 95), 1)
    spines = p("cells", 6, seed=96)
    strata = p("perlin", (400, 10), 2, 97).warp(p("perlin", 80, 1, 98), 6)
    drifts = p("perlin", 60, 2, 99)
    sparkles = p("cells", 4, seed=100)
    cracks = p("plates", 22, 1, 101).warp(p("perlin", 30, 1, 102), 2)
    stains = p("perlin", 50, 1, 103)
    return {
        "grass": flat(80, 0.5 * step(tufts, 0.05) + 0.5 * step(blades, 0.75),
                      "#3f7a2c", "#4f8f35", "#6aaa45"),
        "sand": flat(80, 0.5 * step(dunes, 0.0) + 0.5 * step(ripples, 0.7),
                     "#d9b27a", "#e6c48e", "#f2d9a8"),
        "cactus": flat((60, 120), 0.5 * step(ribs, 0.0) + 0.5 * step(spines, 0.8),
                       "#3f7a3a", "#4f9446", "#a8d08a"),
        "strata": flat(80, 0.5 * step(strata, -0.2) + 0.5 * step(strata, 0.25),
                       "#5c4a6e", "#76628a", "#9282a6"),
        "snow": flat(80, 0.5 * step(drifts, -0.1) + 0.5 * step(sparkles, 0.85),
                     "#b9c8e6", "#dfe8f6", "#ffffff"),
        "canyon floor": flat(80, 0.5 * step(cracks, 0.08) + 0.5 * step(stains, 0.2),
                             "#4a3b5a", "#76628a", "#8f7ea3"),
    }


def foliage():
    """Leaves after Eyvind Earle (Sleeping Beauty): a dark crown, large lighter spots on it, and
    small points lighter still inside the spots, shaped by the tree: round spots for an oak,
    tall ones with strokes for a pine, tiers for a fir, long ones lined for a palm's fronds,
    flat ones in layers for an acacia, small sparse ones for a shrub."""
    def spotted(spot, points, seed):
        dome = p("bubbles", spot, density=0.9).warp(p("perlin", 10, 1, seed), 1.6)
        spots = step(dome, 0.45)
        return 0.5 * spots + 0.5 * spots * points

    oak = spotted(15, step(p("cells", 2, seed=11) + 0.25 * p("perlin", 8, 1, 12), 0.5), 13)
    pine = spotted((11, 26), step(p("perlin", (1.2, 9), 1, 21), 0.35), 23)
    acacia = spotted((26, 10), step(p("cells", 2.6, seed=31), 0.5), 33)
    tier = step(p("perlin", (300, 9), 1, 41).warp(p("perlin", 30, 1, 42), 2), 0.0)
    fir = 0.5 * tier + 0.5 * tier * step(p("perlin", (1.2, 6), 1, 43), 0.4)
    palm = spotted((9, 30), step(p("perlin", (0.8, 40), 1, 51), 0.3), 53)
    shrub = spotted(8, step(p("cells", 1.6, seed=61), 0.45), 63)
    return {
        "leaves": flat(60, oak, "#1e3a34", "#3f7a55", "#a8d08a"),
        "needles": flat(60, pine, "#122e28", "#2c5a44", "#8fb886"),
        "acacia leaves": flat(60, acacia, "#2a3418", "#6f7f34", "#d8d27a"),
        "fir needles": flat(60, fir, "#10302a", "#25553f", "#7fae7e"),
        "palm fronds": flat(60, palm, "#26401f", "#4f7a34", "#b8d07a"),
        "shrub leaves": flat(60, shrub, "#3a3a22", "#6f7040", "#c2bc80"),
    }


def ruins():
    """Masonry for columns and walls: cut blocks with their joints; on the shafts, moss
    running down from the joints."""
    blocks = p("plates", (30, 12), 1, 130)
    wear = p("perlin", 40, 1, 131)
    moss = p("perlin", (12, 60), 2, 132).warp(p("perlin", 30, 1, 133), 3)
    masonry = 0.5 * step(blocks, 0.1) + 0.25 * step(wear, 0.3)
    return {
        "column stone": flat(80, masonry, "#6f6a60", "#a39d90", "#c9c3b4"),
        "mossy column": flat(80, masonry * (1 - step(moss, 0.35)) + 0.25 * step(moss, 0.35),
                             "#4f5a3a", "#8f9a78", "#b9b8a2"),
    }


def stones():
    blotch = p("perlin", 30, 2, 60)
    dots = p("cells", 7, seed=61)
    layers = p("perlin", (300, 12), 1, 62).warp(p("perlin", 70, 1, 63), 5)
    moss = p("perlin", 40, 2, 64)
    return {
        "rock": flat(80, 0.5 * step(blotch, -0.2) + 0.5 * step(blotch, 0.3),
                     "#67645f", "#77746f", "#8d8a86"),
        "granite": flat(40, 1 - step(dots, 0.55) * 0.5 - 0.5 * step(p("cells", 11, seed=65), 0.7),
                        "#9a7a72", "#c49c93", "#d9b3a8"),
        "sandstone": flat(80, 0.5 * step(layers, -0.2) + 0.5 * step(layers, 0.25),
                          "#b0723f", "#c98b55", "#e0a96e"),
        "mossy rock": flat(80, 0.5 * step(blotch, 0.0) + 0.5 * step(moss, 0.2),
                           "#77746f", "#8a8a82", "#6f9a3a"),
    }


def crystals():
    facets = p("creases", 22, 1, 70)

    def gem(*tones):
        return flat(40, 0.5 * step(facets, -0.3) + 0.5 * step(facets, 0.45), *tones)
    return {
        "amethyst": gem("#9259d1", "#b27ee8", "#d9b8ff"),
        "quartz": gem("#cfe6f0", "#e8f4fa", "#ffffff"),
        "emerald": gem("#22a866", "#3ccf86", "#8af0b8"),
        "citrine": gem("#f29424", "#ffb347", "#ffd98a"),
    }


def waters():
    ripples = p("perlin", 25, 2, 80)
    current = p("perlin", (10, 40), 2, 81)
    crests = p("waves", 24).warp(p("perlin", (30, 60), 2, 82), 8)
    algae = p("perlin", 30, 2, 83)
    return {
        "pond": flat(60, 0.5 * step(ripples, 0.1) + 0.5 * step(ripples, 0.5),
                     "#3f9fb5", "#4fb3c8", "#8fdbe6", flow=(2, 4)),
        "river": flat((40, 120), 0.5 * step(current, -0.1) + 0.5 * step(current, 0.45),
                      "#3c95c2", "#56addb", "#eef8fb", flow=30),
        "sea": flat(80, 0.5 * step(crests, 0.1) + 0.5 * step(crests, 0.9),
                    "#236fb0", "#2b7fc4", "#e8f6ff", flow=(16, 0)),
        "swamp": flat(60, 0.5 * step(algae, 0.0) + 0.5 * step(algae, 0.45),
                      "#4a6122", "#5d7a2a", "#86a63a", flow=(1.5, 1)),
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
        flat_r = math.sqrt(1 - z * z)
        points.append((r * flat_r * math.cos(turn), r * flat_r * math.sin(turn) * 0.85, 20 * (1 + z)))
    return s3d.hull(name, points)


def crystal(name, k):
    points = []
    for i in range(6):
        a = math.pi / 3 * i
        points.append((16 * math.cos(a), 16 * math.sin(a), 0))
        points.append((18 * math.cos(a), 18 * math.sin(a), 62))
    points.append((2, 1, 92))
    return s3d.hull(name, points)


def pool(name, k):
    return s3d.box(name, 110, 100, 4)


def cliff(name, k):
    return s3d.box(name, 70, 50, 80)


#: The pieces that wear a look other than their row's shape.
SHAPES = {"cactus": trunk, "strata": cliff, "column stone": trunk, "mossy column": trunk}


def toon():
    pitch, label_size = 140, 11
    rows = [(woods(), plank), (barks(), trunk), (stones(), boulder), (crystals(), crystal),
            (waters(), pool), (grounds(), pool), (foliage(), boulder), (ruins(), trunk)]
    columns = max(len(looks) for looks, _ in rows)
    frames = s3d.grid(columns, len(rows), pitch, -pitch)
    parts = []
    for row, (looks, shape) in enumerate(rows):
        for k, (name, tex) in enumerate(looks.items()):
            frame = frames[row * columns + k]
            tile = s3d.box("tile", pitch - 8, pitch - 8, 2)
            s3d.material(tile, "plastic", color="#667481")
            piece = SHAPES.get(name, shape)(name.replace(" ", "_"), k)
            s3d.material(piece, "plastic", roughness=0.9, texture=tex)
            s3d.unwrap(piece)
            label = s3d.extrude("label", s3d.text(name, label_size), 1)
            s3d.material(label, "plastic", color="#ffffff")
            parts.extend([s3d.at(tile, on=frame), s3d.at(piece, on=frame, z=2),
                          s3d.at(label, on=frame, y=-pitch / 2 + 14, z=2)])
    return s3d.assembly("toon", parts)
