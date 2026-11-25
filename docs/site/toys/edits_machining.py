import sand3d as s3d


def machined_plate():
    width, depth, height = 80, 50, 10
    plate = s3d.box("plate", width, depth, height)
    s3d.hole(plate, 6.6, on=[(-30, -15), (30, -15), (-30, 15), (30, 15)])
    s3d.hole(plate, 5, on=(0, 12), cbore=(10, 4))
    s3d.hole(plate, 5, on=(0, -12), csk=(11, 90))
    s3d.pocket(plate, s3d.rect(14, 8, r=2), depth=4, on=plate.face("top").move(-20, 0))
    s3d.pocket(plate, s3d.circle(8), depth=3,
               on=s3d.grid(1, 2, 0, 16, on=plate.face("top").move(20, 0)))
    return s3d.material(plate, "plastic", color="#71898c")
