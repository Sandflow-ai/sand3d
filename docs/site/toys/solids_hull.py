import sand3d as s3d


def quartz_cluster(seed=0, h=90):
    tall = quartz(h=h)
    left = s3d.at(quartz(h=h * .7), x=-15, ry=-25)
    right = s3d.at(quartz(h=h * .55), x=15, rx=20, ry=30)
    return s3d.assembly("quartz_cluster", tall, left, right)


def quartz(d=26, h=90, point=18):
    base, shoulder = s3d.ring(6, d / 2), s3d.ring(6, d / 2, on=s3d.Frame((0, 0, h)))
    crystal = s3d.hull("quartz", list(base) + list(shoulder) + [(0, 0, h + point)])
    return s3d.material(crystal, "glass", color="#e9e4f0")
