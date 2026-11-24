import sand3d as s3d


def gate():
    width, height, post = 80, 100, 15
    left = s3d.at(s3d.box("post", post, post, height + 20), x=-width - post / 2)
    s3d.material(left, "steel")
    right = s3d.transform(s3d.copy(left), mirror="x")
    panel = s3d.at(s3d.box("panel", width, 8, height), x=-width / 2, z=10)
    knob = s3d.at(s3d.sphere("knob", 10), x=-10, y=8, z=height / 2)
    leaf = s3d.group("leaf", panel, knob)
    s3d.joint("hinge", leaf, s3d.bbox(left, "+X+Y"), axis="+Z", range=(0, 90))
    s3d.material(leaf, "oak")
    twin = s3d.transform(s3d.copy(leaf), mirror="x")
    s3d.pose(leaf, 25)
    s3d.pose(twin, 25)
    return s3d.assembly("gate", left, right, leaf, twin)
