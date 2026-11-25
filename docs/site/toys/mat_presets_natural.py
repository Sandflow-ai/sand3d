import sand3d as s3d


def presets():
    kinds = ['leather', 'marble', 'concrete', 'bark', 'leaf', 'moss']
    diameter, pitch_x, pitch_y, label_size, label_gap = 40, 145, 120, 12, 22
    parts = []
    for kind, frame in zip(kinds, s3d.grid(2, 3, pitch_x, -pitch_y)):
        tile = s3d.box("tile", pitch_x - 8, pitch_y - 8, 2)
        s3d.material(tile, "plastic", color="#667481")
        ball = s3d.sphere(kind, diameter)
        s3d.material(ball, kind)
        label = s3d.extrude("label", s3d.text(kind, label_size), 1)
        s3d.material(label, "plastic", color="#ffffff")
        parts.extend([s3d.at(tile, on=frame), s3d.at(ball, on=frame, z=2),
                      s3d.at(label, on=frame, y=-diameter / 2 - label_gap, z=2)])
    return s3d.assembly("presets", parts)
