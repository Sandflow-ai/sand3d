import sand3d as s3d


def lamp():
    height = 100
    base = s3d.cylinder("base", 65, 10)
    stem = s3d.at(s3d.cylinder("stem", 8, height), on=base.face("top"))
    root = s3d.group("lamp", base, stem)
    lamp = s3d.Handle(root, head=s3d.Frame((0, 0, height + 10)))
    s3d.material(lamp, "brass")
    shade = s3d.shell(s3d.cone("shade", 70, 50, d2=25), 2, open="top bottom")
    s3d.material(shade, "painted_metal", color="#438d99")
    s3d.attach(lamp, "shade", s3d.at(shade, on=lamp.head))
    return lamp
