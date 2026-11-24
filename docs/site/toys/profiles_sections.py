import sand3d as s3d


def build(thickness=3, gap=36):
    parts = []
    for i, exponent in enumerate((2, 4)):
        profile = s3d.superellipse(28, 24, n=exponent)
        parts.append(s3d.at(s3d.extrude(f"section{i}", profile, thickness), x=i * gap))
    egg = s3d.superellipse(28, 24, taper=.45)
    parts.append(s3d.at(s3d.extrude("egg", egg, thickness), x=2 * gap))
    shell = s3d.loft("loft", s3d.station(0, 28, 24, n=4),
                     s3d.station(16, 20, 18, x=3), s3d.station(28, 10, 12, x=6))
    parts.append(s3d.at(shell, x=3 * gap))
    result = s3d.group("sections", *parts)
    s3d.material(result, "plastic", color="#729ba0")
    return result
