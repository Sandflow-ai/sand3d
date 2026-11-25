import numpy as np
import sand3d as s3d


def litter(seed=0):
    ground = s3d.box("soil", 800, 800, 40)
    s3d.material(ground, "soil", color="#332518")
    sites = s3d.Frames(f for f in s3d.scatter(4096, ground, seed=seed+10) if f.normal.z>.7)
    leaves = s3d.tufts("leaves", sites, height=42, width=24, blades=1, lean=12, direction=flat, seed=seed+20)
    s3d.material(leaves, "leaf", color=lambda x,y,z,n: np.where(
        (s3d.noise(x/23,y/23,0,seed=2)>0)[:,None], [.70,.45,.12], [.42,.20,.06]))
    return s3d.group("leaf_litter", ground, leaves)


def flat(x, y, z, n):
    a = 6*np.pi*(.5+.5*s3d.noise(x/9.7,y/9.7,0,seed=1))
    t = np.stack([np.cos(a), np.sin(a), 0*a], 1)
    n = np.asarray(n).T
    return t - np.sum(t*n,1)[:,None]*n + .12*n
