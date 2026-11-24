import sand3d as s3d


def ground_stones(seed=0):
    ground = s3d.box("ground", 800, 800, 80)
    s3d.displace(ground, 85, 240, faces="top", direction="+Z", step=30, seed=seed+1)
    s3d.material(ground, "soil", color="#66513b")
    sites = s3d.Frames(f for f in s3d.scatter(240, ground, seed=seed+4) if f.normal.z>.85)[:24]
    stones = []
    for i, (site, size) in enumerate(zip(sites, s3d.vary(65, 20, len(sites), seed=seed+5))):
        points = s3d.scatter(8, (size, size, size*.7), surface=True, seed=seed+100+i)
        stone = s3d.hull("stone", [tuple(f.origin) for f in points])
        stones.append(s3d.at(stone, on=site.offset(-size*.15)))
    rocks = s3d.group("rocks", *stones)
    s3d.material(rocks, "rock", color="#8c8376")
    return s3d.group("strewn_ground", ground, rocks)
