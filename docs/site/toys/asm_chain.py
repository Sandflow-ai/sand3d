import sand3d as s3d


def chain():
    length, width, height = 80, 18, 12
    base = s3d.cylinder("base", 38, height)
    shoulder = s3d.local(base, z=height)
    first = s3d.at(link("first", length, width, height), on=shoulder)
    s3d.joint("shoulder", first, shoulder, axis="+Z", range=(-90, 90))
    elbow = s3d.local(first, x=length, z=height)
    second = s3d.at(link("second", length, width, height), on=elbow)
    s3d.joint("elbow", second, elbow, axis="+Z", range=(-120, 120))
    model = s3d.assembly("arm", base, first, second)
    s3d.material(base, "steel")
    s3d.material(first, "plastic", color="#d78344")
    s3d.material(second, "plastic", color="#438d99")
    s3d.pose(first, 35)
    s3d.pose(second, 65)
    return model


def link(name, length, width, height):
    bar = s3d.at(s3d.box(name, length, width, height), x=length / 2)
    return s3d.group(name + "_pivot", bar)
