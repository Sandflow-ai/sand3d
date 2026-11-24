import sand3d as s3d


def coupled():
    length, gap = 45, 75
    base = s3d.box("base", 180, 60, 8)
    left_frame = s3d.local(base, x=-gap / 2, z=8)
    right_frame = s3d.local(base, x=gap / 2, z=8)
    left = s3d.at(lever("leader", length), on=left_frame)
    right = s3d.at(lever("follower", length), on=right_frame)
    s3d.joint("input", left, left_frame, range=(-90, 90))
    s3d.joint("output", right, right_frame, follows=left, ratio=-2)
    s3d.material(base, "steel")
    s3d.material(left, "plastic", color="#d78344")
    s3d.material(right, "plastic", color="#438d99")
    s3d.pose(left, 30)
    return s3d.assembly("coupled", base, left, right)


def lever(name, length, width=12, height=10):
    bar = s3d.at(s3d.box(name, length, width, height), x=length / 2)
    return s3d.group(name + "_pivot", bar)
