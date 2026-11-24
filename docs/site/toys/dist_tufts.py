import sand3d as s3d


def surface_sites(seed=0, width=240, depth=160, height=20, pitch=18):
    ground = s3d.box("ground", width, depth, height)
    s3d.material(ground, "grass", color="#344d26")
    probes = s3d.grid(12, 8, pitch, pitch).offset(height * 2)
    hits = s3d.snap(ground, probes, direction="-Z")
    grass = s3d.tufts("grass", hits, height=35, width=3, lean=25, seed=seed)
    s3d.material(grass, "grass", color="#63873a")
    sites = s3d.Frames(f for f in s3d.scatter(120, ground, seed=seed + 1) if f.normal.z > .9)[:8]
    if sites:
        stone = s3d.material(s3d.sphere("stone", 14), "rock", color="#868078")
        stones = s3d.at(stone, on=sites.offset(-3))
    else:
        stones = []
    return s3d.group("surface_sites", ground, grass, stones)
