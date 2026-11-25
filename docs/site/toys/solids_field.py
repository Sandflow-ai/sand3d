import numpy as np
import sand3d as s3d


def sea_sponge(seed=0, d=100, pore=26, cell=2.1):
    def density(x, y, z):
        z, k = z - (d + 4 * cell) / 2, 2 * np.pi / pore
        ball = np.sqrt(x * x + y * y + z * z) - d / 2
        gyroid = np.sin(x * k) * np.cos(y * k) + np.sin(y * k) * np.cos(z * k) + np.sin(z * k) * np.cos(x * k)
        wobble = s3d.noise(x / pore, y / pore, z / pore, seed=seed)
        return np.maximum(ball, np.abs(gyroid + .3 * wobble) - .5)
    sponge = s3d.field("sponge", (d + 4 * cell, d + 4 * cell, d + 4 * cell), density, cell=cell)
    return s3d.assembly("sea_sponge", s3d.material(sponge, "sand", color="#d9a441"))
