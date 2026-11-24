import sand3d as s3d


def build():
    profiles = [s3d.rect(24, 18, r=3), s3d.circle(20), s3d.ellipse(24, 16),
                s3d.slot(26, 12), s3d.polygon(6, 22)]
    parts = []
    for i, profile in enumerate(profiles):
        part = s3d.extrude(f"shape{i}", profile, 3)
        parts.append(s3d.at(part, x=(i % 3) * 32, y=(i // 3) * 30))
    result = s3d.group("profiles", *parts)
    s3d.material(result, "plastic", color="#729ba0")
    return result
