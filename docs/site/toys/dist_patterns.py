import sand3d as s3d


def patterns(seed=0, gap=150, diameter=100, height=24):
    layouts = [s3d.grid(4, 4, diameter / 3, diameter / 3),
               s3d.ring(16, diameter / 2), s3d.phyllotaxis(45, diameter)]
    groups = []
    for i, sites in enumerate(layouts):
        sites = sites.jitter(rz=12, seed=seed + i)
        peg = s3d.box("peg", 10, 5, height)
        s3d.material(peg, "painted_metal", color="#536f91")
        copies = s3d.at(peg, on=sites, scale=s3d.vary(1, .3, len(sites), seed=seed + 10 + i))
        groups.append(s3d.at(s3d.group("pattern", copies), x=(i - 1) * gap))
    return s3d.group("patterns", groups)
