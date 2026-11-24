import sand3d as s3d


def copies():
    diameter, height, gap = 16, 30, 30
    peg = s3d.cylinder("peg", diameter, height)
    twin = s3d.at(s3d.copy(peg), x=gap)
    egg = s3d.at(s3d.scale(s3d.sphere("egg", height), (1.6, 1, 1)), x=3*gap)
    pair = s3d.merge(peg, twin)
    discarded = s3d.copy(egg)
    s3d.delete(discarded)
    return s3d.material(s3d.group("copies", pair, egg), "plastic", color="#71898c")
