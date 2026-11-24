import sand3d as s3d


def crystals(seed=0):
    height, gap = 65, 65
    crystals = []
    for index, diameter in enumerate((20, 40)):
        base = s3d.ring(6, diameter / 2)
        shoulder = s3d.ring(6, diameter / 2, on=s3d.Frame((0, 0, height)))
        points = list(base) + list(shoulder) + [(0, 0, height + 15)]
        crystal = s3d.hull("crystal", points)
        s3d.material(crystal, "glass", absorb="#70b7c5", absorb_distance=35)
        crystals.append(s3d.at(crystal, x=(index - .5) * gap, z=5))
    ground = s3d.box("ground", 145, 80, 5)
    s3d.material(ground, "ceramic", color="#d9ceb8")
    return s3d.assembly("crystals", ground, crystals)
