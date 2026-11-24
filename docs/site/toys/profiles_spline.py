import sand3d as s3d


def build():
    points = [(-18, 0), (-12, 16), (12, 16), (18, 0), (0, -12)]
    with s3d.facets(64):
        plate = s3d.extrude("profile", s3d.spline(points, closed=True), 3)
        path = s3d.spline(points, loop=True)
        rim = s3d.at(s3d.wire("loop", path, 2), x=48)
        open_path = s3d.spline(points)
        line = s3d.at(s3d.wire("open", open_path, 2), x=96)
    result = s3d.group("curves", plate, rim, line)
    s3d.material(result, "plastic", color="#729ba0")
    return result
