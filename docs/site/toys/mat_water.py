import sand3d as s3d


def p(kind, size, octaves=1, seed=0):
    return s3d.pattern(kind, size, octaves=octaves, seed=seed)


def looks():
    ripples = p("perlin", 14, 3, 1)
    current = p("perlin", (6, 30), 3, 2)
    foam = p("perlin", (14, 20), 3, 3).levels(0.35, 0.7)
    swell = p("waves", 20).warp(p("perlin", (30, 50), 3, 4), 9)
    chop = p("perlin", 8, 3, 5)
    murk = p("perlin", 30, 3, 6)
    algae = p("cells", 10, 2, 7).levels(0.2, 0.7) * p("perlin", 45, 2, 8).levels(0.0, 0.4)
    return {
        "pond": ("water", dict(transmission=0.5), s3d.texture(
            60, height=0.4 * ripples,
            color=(0.5 + 0.5 * ripples, "#1d4f5c", "#3f8a8f", "#8fc9c2"),
            roughness=(ripples.levels(-1, 1), 0.02, 0.1), flow=(2, 4))),
        "river": ("water", dict(transmission=0.4), s3d.texture(
            (40, 120), height=0.4 * current + 0.2 * foam,
            color=(0.35 + 0.25 * current + 0.6 * foam, "#245a63", "#4f9a9a", "#eef6f4"),
            roughness=(foam, 0.04, 0.5), flow=30)),
        "sea": ("water", dict(transmission=0.6), s3d.texture(
            80, height=0.6 * swell + 0.1 * chop,
            color=(0.5 + 0.4 * swell + 0.1 * chop, "#0d3b66", "#1f6f8b", "#7fc8c8"),
            roughness=(chop.levels(-1, 1), 0.03, 0.15), flow=(16, 0))),
        "swamp": ("water", dict(transmission=0.15, roughness=0.3), s3d.texture(
            60, height=0.08 * murk + 0.2 * algae,
            color=(0.3 + 0.2 * murk + 0.6 * algae, "#1f2a14", "#34401f", "#5d7a2a", "#86a63a"),
            roughness=(algae, 0.1, 0.8), flow=(1.5, 1))),
    }


def water():
    pitch, label_size = 150, 12
    parts = []
    for (name, (kind, extra, tex)), frame in zip(looks().items(), s3d.grid(2, 2, pitch, -pitch)):
        basin = s3d.box("basin", pitch - 8, pitch - 8, 6)
        s3d.material(basin, "rock", color="#6f6a60")
        surface = s3d.box(name, pitch - 30, pitch - 44, 2)
        s3d.material(surface, kind, texture=tex, **extra)
        s3d.unwrap(surface)
        label = s3d.extrude("label", s3d.text(name, label_size), 1)
        s3d.material(label, "plastic", color="#ffffff")
        parts.extend([s3d.at(basin, on=frame), s3d.at(surface, on=frame, y=8, z=6),
                      s3d.at(label, on=frame, y=-pitch / 2 + 14, z=6)])
    return s3d.assembly("water", parts)
