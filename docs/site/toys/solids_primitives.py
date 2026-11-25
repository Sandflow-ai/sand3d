import sand3d as s3d


def primitives(size=30, gap=48):
    parts = [s3d.box("box", size, size, size),
             s3d.cylinder("cylinder", size, size),
             s3d.tube("tube", size, size / 2, size),
             s3d.cone("cone", size, size, d2=size / 3)]
    placed = [s3d.at(s3d.material(part, "plastic", color="#798fa5"), on=frame)
              for part, frame in zip(parts, s3d.grid(4, px=gap))]
    return s3d.assembly("primitives", placed)
