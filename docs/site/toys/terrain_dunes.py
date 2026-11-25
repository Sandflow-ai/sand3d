import numpy as np
import sand3d as s3d


def dunes(seed=0):
    sand = s3d.box("sand", 3000, 2000, 100)
    s3d.displace(sand, 15, 500, seed=seed+4, faces="top", direction="+Z", step=80)
    s3d.displace(sand, 200, 80, noise=dune, faces="top", direction="+Z", step=60)
    s3d.displace(sand, 8, 120, noise=s3d.waves(110, direction=10),
                 faces="top", direction="+Z", step=30)
    s3d.material(sand, "sand", color=lambda x,y,z,n: np.where(
        ((n[2]>.95)&(z>220))[:,None], [.82,.68,.43], [.64,.49,.28]))
    return sand


def dune(x, y, z):
    q = ((x + 180*np.sin(y/420) + 800) % 1600)/1600
    return np.where(q<.8, q/.8, (1-q)/.2)
