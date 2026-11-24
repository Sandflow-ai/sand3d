import sand3d as s3d


def face_axes(width=50, depth=40, height=45, length=32, diameter=2):
    block = s3d.box("block", width, depth, height)
    s3d.material(block, "plastic", color="#c9c5c0")
    face = block.face("+X")
    origin = face.point()
    arrows = []
    for name, end, color in (
        ("face_X", face.point(x=length), "#b84343"),
        ("face_Y", face.point(y=length), "#32824c"),
        ("face_Z", face.point(z=length), "#456aca"),
    ):
        arrow = s3d.wire(name, [origin, end], diameter)
        s3d.material(arrow, "plastic", color=color)
        arrows.append(arrow)
    return s3d.group("face_axes", block, arrows)
