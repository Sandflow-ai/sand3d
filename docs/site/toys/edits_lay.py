import sand3d as s3d


def leaf_on_stone(d=140, leaf=95, width=50):
    stone = s3d.material(s3d.sphere("stone", d), "rock", color="#77736b")
    fallen = s3d.at(flat_leaf(leaf, width), z=d + 10, rz=30)
    s3d.lay(fallen, stone, step=20)
    return s3d.assembly("leaf_on_stone", stone, fallen)


def flat_leaf(length, width, t=1.5):
    leaf = s3d.extrude("leaf", s3d.ellipse(length, width), t)
    return s3d.material(leaf, "leaf", color="#b5651d")
