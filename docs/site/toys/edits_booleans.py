import sand3d as s3d


def booleans():
    width, depth, height = 60, 40, 8
    plate = s3d.box("plate", width, depth, height)
    s3d.cut(plate, s3d.at(s3d.cylinder("pin", 10, 20), x=10, z=-6),
            s3d.at(s3d.box("notch", 10, 50, 20), x=-30, z=-2))
    plate = s3d.join(plate, s3d.at(s3d.cylinder("boss", 16, 10), x=-10, z=7))
    common = s3d.intersect(s3d.box("cube", 30, 30, 30),
                           s3d.at(s3d.sphere("ball", 40), z=-5))
    s3d.at(common, x=65)
    return s3d.material(s3d.group("booleans", plate, common), "plastic", color="#71898c")
