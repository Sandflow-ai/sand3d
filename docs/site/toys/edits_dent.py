import sand3d as s3d


def lotus_pod(d=80, h=50, holes=19, r=5, depth=5):
    pod = s3d.wire("pod", [(0, 0, 0), (0, 0, h)], d=[(0, d * .4), (.8, d), (1, 0)])
    probes = s3d.phyllotaxis(holes, d * .6, on=s3d.Frame((0, 0, h * 2)))
    sites = s3d.snap(pod, probes, direction=(0, 0, -1))
    s3d.dent(pod, sites, r=r, depth=depth)
    return s3d.assembly("lotus_pod", s3d.material(pod, "soil", color="#a89a5c"))
