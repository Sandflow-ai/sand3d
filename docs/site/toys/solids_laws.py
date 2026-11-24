import sand3d as s3d


def radish(h=110, d=44):
    root = s3d.wire("root", [(0, 0, 0), (0, 0, -h)], d=[(0, d * .4), (.2, d), (.5, d * .5), (1, 0)])
    leaves = s3d.at(leaf(), on=s3d.ring(3, 4).turn(ry=25))
    return s3d.assembly("radish", s3d.material(root, "soil", color="#c2364a"), leaves)


def leaf(length=140, width=40, t=2, roll=120):
    rib = s3d.spline([(0, 0, 0), (length * .2, 0, length * .6), (length * .5, 0, length)])
    blade = s3d.sweep("leaf", s3d.rect(width, t), rib, scale=[(0, .1), (.5, 1), (1, .2)],
                      twist=[(0, 0), (.6, roll / 3), (1, roll)])
    return s3d.material(blade, "leaf")
