import sand3d as s3d


def rain_basin(seed=0, d=320, h=140, bowl=260):
    stone = s3d.material(s3d.cylinder("basin", d, h), "rock", color="#6f6a62")
    s3d.cut(stone, s3d.at(s3d.sphere("bowl", bowl), z=h - bowl / 3))
    s3d.displace(stone, 4, 30, seed=seed)
    water = s3d.fill("water", stone, h - 15)
    drops = s3d.waves(18, centers=[(-30, 20), (40, -25), (10, 50)], decay=40, sharpness=.4)
    s3d.displace(water, 1.5, 4.5, noise=drops, direction="+Z", faces="top")
    s3d.material(water, "water", absorb="#3f7f86", absorb_distance=150)
    return s3d.assembly("rain_basin", stone, water)
