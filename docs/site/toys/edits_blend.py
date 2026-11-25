import sand3d as s3d


def cactus(h=300, d=70, r=14):
    trunk = s3d.wire("trunk", [(0, 0, 0), (0, 0, h)], d=d)
    right = s3d.at(arm(d), z=h * .35)
    left = s3d.at(s3d.transform(arm(d), mirror="x"), z=h * .5)
    plant = s3d.blend(trunk, right, left, r=r)
    return s3d.assembly("cactus", s3d.material(plant, "leaf", color="#4f7a3a"))


def arm(d, reach=1.4, rise=.9):
    path = s3d.spline([(0, 0, 0), (d * reach, 0, d * .2), (d * reach, 0, d * (1 + rise))])
    return s3d.wire("arm", path, d=d * .6)
