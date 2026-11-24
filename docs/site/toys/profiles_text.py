import sand3d as s3d


def build(size=28, thickness=4):
    letters = s3d.text("S3D", size)
    result = s3d.extrude("letters", letters, thickness)
    s3d.material(result, "plastic", color="#729ba0")
    return result
