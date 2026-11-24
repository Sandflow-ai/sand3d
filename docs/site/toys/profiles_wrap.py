import sand3d as s3d


def build(gap=48, belt_width=3, thickness=4):
    wheels = [s3d.at(s3d.circle(24), x=-gap / 2), s3d.at(s3d.circle(16), x=gap / 2)]
    outline = s3d.wrap(*wheels)
    belt = s3d.extrude("belt", s3d.offset(outline, belt_width) - outline, thickness)
    hubs = [s3d.extrude(f"wheel{i}", p, thickness * 1.5) for i, p in enumerate(wheels)]
    result = s3d.group("belt_and_wheels", belt, *hubs)
    s3d.material(result, "plastic", color="#729ba0")
    return result
