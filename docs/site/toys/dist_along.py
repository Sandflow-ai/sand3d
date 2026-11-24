import sand3d as s3d


def leafy_stem(height=400, d=8, leaves=14):
    path = s3d.spline([(0, 0, 0), (20, 0, height / 2), (0, 30, height)])
    stem = s3d.wire("stem", path, d=[(0, d), (1, d / 3)])
    nodes = s3d.along(path, count=leaves, spin=137.508, span=(.3, .95)).turn(ry=55)
    blades = s3d.at(s3d.material(leaf(), "leaf"), on=nodes)
    return s3d.assembly("leafy_stem", s3d.material(stem, "leaf"), blades)


def leaf(length=90, width=34, t=2):
    rib = [(0, 0, 0), (0, 0, length)]
    return s3d.sweep("leaf", s3d.rect(width, t), rib, scale=[(0, .1), (.4, 1), (1, 0)])
