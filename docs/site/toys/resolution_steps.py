import sand3d as s3d


def same_relief(seed=0):
    diameter, gap = 60, 80
    stones = []
    for index, step in enumerate((14, 7, 3.5)):
        with s3d.facets(12):
            stone = s3d.sphere("stone", diameter)
        s3d.displace(stone, amount=5, size=20, step=step, seed=seed)
        s3d.material(stone, "rock", color="#847d6d")
        stones.append(s3d.at(stone, x=(index - 1) * gap))
    return s3d.assembly("same_relief", stones)
