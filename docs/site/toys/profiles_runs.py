import sand3d as s3d


def build():
    profile = s3d.poly([(-24, -14), (14, -14),
                       s3d.tangent_arc((24, -4)), (24, 6),
                       s3d.arc(through=(16, 16), to=(8, 6)),
                       s3d.spline([(8, 6), (-8, 18), (-24, 6)])])
    result = s3d.extrude("outline", profile, 3)
    s3d.material(result, "plastic", color="#729ba0")
    return result
