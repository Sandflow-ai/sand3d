import sand3d as s3d


def rock(seed=0):
    width, depth, height = 90, 70, 60
    points = s3d.scatter(28, (width, depth, height), surface=True, seed=seed + 1)
    points = points.jitter(x=8, y=8, z=8, seed=seed + 2)
    stone = s3d.hull("stone", points)
    s3d.displace(stone, amount=7, size=40, step=12, seed=seed + 3)
    s3d.displace(stone, amount=.5, size=6, step=6, seed=seed + 4)
    return s3d.material(stone, "rock", color="#807569")
