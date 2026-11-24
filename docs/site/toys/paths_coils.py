import sand3d as s3d


def build(wire_d=2, gap=52):
    coil = s3d.helix(26, 10, 32)
    a = s3d.wire("helix", coil, wire_d)
    growing = s3d.spiral(10, 40, 2, h=16)
    b = s3d.at(s3d.wire("spiral", growing, wire_d), x=gap)
    result = s3d.group("paths", a, b)
    s3d.material(result, "plastic", color="#729ba0")
    return result
