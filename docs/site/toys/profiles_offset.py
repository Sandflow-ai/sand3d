import sand3d as s3d


def build(width=28, depth=20, offset=3, thickness=3, gap=42):
    profile = s3d.rect(width, depth)
    parts = []
    for i, amount in enumerate((-offset, 0, offset)):
        grown = s3d.offset(profile, amount)
        parts.append(s3d.at(s3d.extrude(f"offset{i}", grown, thickness), x=i * gap))
    result = s3d.group("offsets", *parts)
    s3d.material(result, "plastic", color="#729ba0")
    return result
