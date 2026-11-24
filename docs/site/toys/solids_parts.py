import sand3d as s3d


def ready_parts(diameter=30, height=24, gap=50, pitch=3):
    gear = s3d.gear("gear", teeth=16, module=2, width=height / 3, bore=8)
    grip = s3d.knurl("grip", diameter, height, pitch=pitch)
    rod = s3d.thread("rod", diameter / 2, height, pitch=pitch)
    placed = [s3d.at(s3d.material(part, "brass"), on=frame)
              for part, frame in zip((gear, grip, rod), s3d.grid(3, px=gap))]
    return s3d.assembly("ready_parts", placed)
