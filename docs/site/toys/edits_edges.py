import sand3d as s3d


def edge_finishes():
    width, depth, height, gap = 40, 30, 20, 55
    rounded = s3d.fillet(s3d.box("rounded", width, depth, height), 4, edges="top")
    bevelled = s3d.chamfer(s3d.box("bevelled", width, depth, height), 3, edges="top", d2=6)
    eased = s3d.soften(s3d.box("eased", width, depth, height), 3)
    s3d.at(bevelled, x=gap)
    s3d.at(eased, x=2*gap)
    return s3d.material(s3d.group("finishes", rounded, bevelled, eased), "plastic", color="#71898c")
