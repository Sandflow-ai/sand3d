import sand3d as s3d


def build(width=48, thickness=8, scale=12, amount=5, gap=60):
    parts = []
    for i, kind in enumerate(("perlin", "cells", "ridged", "turbulence")):
        height = lambda x, y, z: s3d.noise(x / scale, y / scale, z / scale, seed=5, kind=kind)
        plate = s3d.box(kind, width, width, thickness)
        s3d.displace(plate, amount, scale / 3, noise=height, direction="+Z", faces="top", step=1)
        parts.append(s3d.at(plate, x=(i % 2) * gap, y=(i // 2) * gap))
    result = s3d.group("noises", *parts)
    s3d.material(result, "plastic", color="#729ba0")
    return result
