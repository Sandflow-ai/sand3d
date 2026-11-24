import numpy as np
import sand3d as s3d


def weathered_stone(seed=0):
    stone = s3d.sphere("stone", 100)
    s3d.displace(stone, amount=6, size=35, step=8, seed=seed)
    return s3d.material(stone, "rock", color=weathered)


def weathered(x, y, z):
    t = np.clip(z / 100, 0, 1)
    low = np.array([.12, .08, .04])
    high = np.array([.48, .38, .22])
    blend = np.interp(t, [0, .4, 1], [0, .2, 1])
    rgb = low + blend[:, None] * (high - low)
    return np.where((z < 30)[:, None], low, rgb)
