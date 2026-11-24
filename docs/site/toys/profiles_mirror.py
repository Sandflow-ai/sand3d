import sand3d as s3d


def build(thickness=3, gap=66):
    half = s3d.poly([(0, -18), (16, -12), (24, 8), (0, 18)])
    single = s3d.extrude("half", half, thickness)
    whole = s3d.at(s3d.extrude("whole", s3d.mirror(half), thickness), x=gap)
    result = s3d.group("symmetry", single, whole)
    s3d.material(result, "plastic", color="#729ba0")
    return result
