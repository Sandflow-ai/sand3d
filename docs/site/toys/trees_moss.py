import numpy as np
import sand3d as s3d


def moss(seed=0):
    ground = s3d.box("ground", 800, 800, 40)
    patch = lambda x, y: np.clip((s3d.noise(x/160, y/160, 0, seed=seed+5)-.2)*4, 0, 1)
    s3d.displace(ground, 10, 60, faces="top", direction="+Z", step=14,
                 noise=lambda x,y,z: patch(x,y)*(.6+.4*s3d.noise(x/30,y/30,0,seed=seed+6)))
    s3d.material(ground, "soil", color=lambda x,y,z,n: np.where(
        (patch(x,y)>.3)[:,None], [.26,.40,.08], [.22,.16,.10]))
    sites = s3d.Frames(f for f in s3d.scatter(4096, ground, seed=seed+3)
                       if f.normal.z>.85 and patch(f.origin.x,f.origin.y)>.3)
    pile = s3d.tufts("moss", sites, height=7, width=3, blades=3, lean=45, seed=seed+4)
    s3d.material(pile, "moss", color="#5a6e1c")
    return s3d.group("moss_patch", ground, pile)
