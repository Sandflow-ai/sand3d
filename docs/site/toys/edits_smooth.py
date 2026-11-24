import sand3d as s3d


def three_shadings(d=60, h=70, gap=90):
    s3d.facets(12)
    logs = [s3d.cylinder("log", d, h) for _ in range(3)]
    for log, angle, k in zip(logs, (0, 55, 180), (-1, 0, 1)):
        s3d.at(s3d.smooth(log, angle), x=k * gap)
    return s3d.assembly("three_shadings", s3d.material(logs, "bark"))
