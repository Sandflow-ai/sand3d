import sand3d as s3d


def split_ball():
    diameter, gap = 40, 55
    ball = s3d.sphere("ball", diameter)
    plane = s3d.Frame((0, 0, 25), (0, 1, 1))
    above, below = s3d.split(ball, plane, keep="both")
    s3d.at(above, x=gap)
    return s3d.material(s3d.group("halves", below, above), "plastic", color="#71898c")
