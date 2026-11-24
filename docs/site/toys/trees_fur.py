import numpy as np
import sand3d as s3d


def fur(seed=0):
    body = s3d.scale(s3d.sphere("carrier", 240), (1.6, 1, .7))
    s3d.material(body, "plastic", color="#4b2d19", roughness=.85)
    sites = s3d.Frames(f for f in s3d.scatter(4096, body, seed=seed+2) if f.normal.z>-.5)
    pile = s3d.tufts("fur", sites, height=34, width=6, blades=7, lean=14, direction=comb, seed=seed+6)
    s3d.material(pile, "plastic", color="#6b4423", roughness=.85)
    return s3d.group("combed_fur", body, pile)


def comb(x, y, z, n):
    n = np.asarray(n).T
    t = np.array([-1.0, 0, -.25])
    return t - (n @ t)[:, None] * n + .3 * n
