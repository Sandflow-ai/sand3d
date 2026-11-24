import sand3d as s3d


def round_forms(size=30, gap=48):
    parts = [s3d.sphere("sphere", size),
             s3d.wedge("wedge", size, size, size),
             s3d.torus("torus", size, size / 4),
             s3d.dome("dome", size, size / 3)]
    placed = [s3d.at(s3d.material(part, "plastic", color="#b68d69"), on=frame)
              for part, frame in zip(parts, s3d.grid(4, px=gap))]
    return s3d.assembly("round_forms", placed)
