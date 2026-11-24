import sand3d as s3d


def fire(seed=0):
    base = s3d.box("hearth", 220, 180, 12)
    s3d.material(base, "rock", color="#413b37")
    logs = [s3d.wire("char", [(-75, y, 25), (75, -y, 25)], d=24) for y in (-35, 35)]
    s3d.material(logs, "bark", color="#211913")
    flames = []
    layers = [(-42, 85), (0, 130), (40, 100)]
    attachment_z = 30
    for x, height in layers:
        frame = s3d.local(base, x=x, z=attachment_z)
        flames.append(s3d.at(tongue(height), on=frame))
    return s3d.group("fire", base, *logs, *flames)


def tongue(height, width=34, drift=12, tip_x=10, core_d=16, core_depth=12, core_ratio=.45):
    flame = s3d.wire("tongue", [(0, 0, 0), (-drift, 3, height / 2), (tip_x, 0, height)],
                     d=[(0, width), (1, 0)], tip="sharp")
    s3d.material(flame, "light", color="#ff7b20", emission=3)
    core = s3d.at(s3d.cone("core", core_d, height * core_ratio), y=-core_depth)
    s3d.material(core, "light", color="#ffe5a0", emission=9)
    return s3d.group("flame", flame, core)
