import sand3d as s3d


def lawn(seed=0):
    ground = s3d.box("ground", 1000, 1000, 50)
    s3d.material(ground, "grass", color="#1f3d0a")
    sites = s3d.Frames(f for f in s3d.scatter(3500, ground, seed=seed+7) if f.normal.z > .9)[:1000]
    grass = s3d.tufts("grass", sites, height=45, width=3, blades=5, lean=25, seed=seed+8)
    s3d.material(grass, "grass", color="#2e590d")
    return s3d.group("lawn", ground, grass)
