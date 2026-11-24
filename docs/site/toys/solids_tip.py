import sand3d as s3d


def three_tips(length=120, d=24, gap=50):
    tips = ["round", "sharp", "flat"]
    thorns = [s3d.at(thorn(kind, length, d), x=(k - 1) * gap) for k, kind in enumerate(tips)]
    return s3d.assembly("three_tips", thorns)


def thorn(kind, length, d):
    spike = s3d.wire("thorn", [(0, 0, 0), (0, 0, length)], d=[(0, d), (.6, d * .7), (1, 0)], tip=kind)
    return s3d.material(spike, "bark")
