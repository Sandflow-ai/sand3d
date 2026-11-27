import sand3d as s3d


def looks():
    grain = s3d.pattern("perlin", 0.6, octaves=2)
    pebble = s3d.pattern("cells", 1.6, octaves=2).warp(s3d.pattern("perlin", 3), 0.5)
    domes = s3d.pattern("bubbles", 6, density=0.86)
    streaks = s3d.pattern("perlin", (40, 0.25), octaves=2)
    veins = s3d.pattern("ridged", 30, octaves=3).warp(s3d.pattern("perlin", 20, octaves=2), 1.2)
    pulp = s3d.pattern("perlin", 20, octaves=4, seed=1)
    fibres = s3d.pattern("strands", (3, 0.15), density=3, seed=3)
    return {
        "grain": ("plastic", dict(color="#3f6f9e", roughness=0.5),
                  s3d.texture(16, height=0.012 * grain)),
        "pebble": ("leather", {},
                   s3d.texture(24, height=0.09 * pebble, roughness=(0.5 + 0.5 * pebble, 0.35, 0.6))),
        "bubbles": ("glossy_plastic", dict(color="#e6eef3", roughness=0.15),
                    s3d.texture((36, 41.57), height=1.4 * domes)),
        "brushed": ("aluminium", {},
                    s3d.texture(40, height=0.004 * streaks, roughness=(0.5 + 0.5 * streaks, 0.25, 0.45))),
        "marble": ("marble", {},
                   s3d.texture(48, color=(veins.levels(0.55, 0.95), "#f2efe9", "#b9b3aa", "#55504b"))),
        "kraft": ("plastic", dict(roughness=0.9),
                  s3d.texture(32, height=0.02 * fibres + 0.01 * pulp,
                              color=(0.5 + 0.25 * pulp - 0.3 * fibres, "#6b4626", "#a87a4b", "#c49a68"))),
    }


def textures():
    diameter, pitch_x, pitch_y, label_size, label_gap = 60, 150, 130, 12, 22
    parts = []
    for (name, (kind, extra, tex)), frame in zip(looks().items(), s3d.grid(2, 3, pitch_x, -pitch_y)):
        tile = s3d.box("tile", pitch_x - 8, pitch_y - 8, 2)
        s3d.material(tile, "plastic", color="#667481")
        ball = s3d.sphere(name, diameter)
        s3d.material(ball, kind, texture=tex, **extra)
        s3d.unwrap(ball)
        label = s3d.extrude("label", s3d.text(name, label_size), 1)
        s3d.material(label, "plastic", color="#ffffff")
        parts.extend([s3d.at(tile, on=frame), s3d.at(ball, on=frame, z=2),
                      s3d.at(label, on=frame, y=-diameter / 2 - label_gap, z=2)])
    return s3d.assembly("textures", parts)
