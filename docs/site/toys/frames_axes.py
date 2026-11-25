import sand3d as s3d


def face_axes(width=80, depth=40, height=65, length=45, thickness=3):
    block = s3d.material(s3d.box("block", width, depth, height), "plastic", color="#ccc8bd")
    face = block.face("-Y")
    origin = face.move(y=height / 3).offset(thickness)
    axes = []
    for name, normal, color in (("X", origin.x, "#b83732"), ("Y", origin.y, "#358345"), ("Z", origin.z, "#365cbd")):
        shaft = s3d.cylinder(name, thickness, length)
        tip = s3d.at(s3d.cone(name + "_tip", thickness * 3, thickness * 4), z=length)
        arrow = s3d.material(s3d.group(name + "_axis", shaft, tip), "plastic", color=color)
        axes.append(s3d.at(arrow, on=s3d.Frame(origin.origin, normal)))
    rim = s3d.material(s3d.wire("rim", block.edge("top"), thickness), "brass")
    return s3d.group("face_axes", block, rim, axes)
