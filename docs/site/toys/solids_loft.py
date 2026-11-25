import sand3d as s3d


def drifting_loft(height=100, width=36, drift=22):
    part = s3d.loft("drift", s3d.station(0, width, width),
                    s3d.station(height / 2, width, width / 2, x=drift),
                    s3d.station(height, 0, 0, x=drift), follow=True)
    return s3d.material(part, "plastic", color="#798fa5")
