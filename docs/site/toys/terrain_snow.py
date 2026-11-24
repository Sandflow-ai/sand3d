import numpy as np
import sand3d as s3d


def snow(seed=0):
    ground = s3d.box("ground", 800, 800, 40)
    drift = lambda x,y,z: (.5+.5*s3d.noise(x/160,y/160,0,seed=seed))**2
    s3d.displace(ground, 110, 160, noise=drift, faces="top", direction="+Z", step=16)
    s3d.material(ground, "snow", color=lambda x,y,z,n: np.where((z<40)[:,None], [.25,.18,.11],
        [.55,.62,.74]+np.clip(n[2],0,1)[:,None]**4*[.35,.30,.21]))
    return ground
