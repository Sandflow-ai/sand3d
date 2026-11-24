import sand3d as s3d


def three_blades(length=200, gap=50):
    bent = s3d.bend(blade("bent", length), 90)
    twisted = s3d.twist(blade("twisted", length), 180)
    tapered = s3d.taper(blade("tapered", length), .15)
    rows = [s3d.at(b, x=(k - 1) * gap, rx=90) for k, b in enumerate((bent, twisted, tapered))]
    return s3d.assembly("three_blades", rows)


def blade(name, length, width=24, t=2):
    return s3d.material(s3d.box(name, width, length, t), "grass")
