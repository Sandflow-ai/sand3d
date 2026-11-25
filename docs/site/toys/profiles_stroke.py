import sand3d as s3d


def build(radius=24, width=5, thickness=3, gap=62):
    path = s3d.arc(r=radius, start=20, end=160)
    band = s3d.stroke(path, width)
    curved = s3d.extrude("curved", band, thickness)
    bent = s3d.stroke([(-20, -10), (12, -10), (12, 16)], width)
    corner = s3d.at(s3d.extrude("corner", bent, thickness), x=gap)
    result = s3d.group("bands", curved, corner)
    s3d.material(result, "plastic", color="#729ba0")
    return result
