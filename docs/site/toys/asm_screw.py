import sand3d as s3d


def screw():
    pitch, length = 20, 70
    base = s3d.box("base", 65, 65, 12)
    pivot = s3d.local(base, z=12)
    moving = s3d.at(screw_part(pitch, length), on=pivot)
    s3d.joint("turn", moving, pivot, range=(0, 720))
    s3d.joint("advance", moving, pivot, kind="prismatic", follows="turn", ratio=pitch / 360)
    s3d.material(base, "painted_metal", color="#438d99")
    s3d.material(moving, "brass")
    s3d.pose(moving, 270, joint="turn")
    return s3d.assembly("screw_motion", base, moving)


def screw_part(pitch, length, rod_d=22, bar_length=65, bar_width=12, bar_height=10):
    rod = s3d.thread("rod", rod_d, length, pitch)
    bar = s3d.at(s3d.box("bar", bar_length, bar_width, bar_height), z=length)
    return s3d.group("screw", rod, bar)
