import sand3d as s3d


def open_tray():
    width, depth, height, wall = 40, 30, 20, 1.5
    tray = s3d.box("tray", width, depth, height)
    s3d.fillet(tray, 4, edges="bottom side")
    s3d.shell(tray, wall, open="top")
    return s3d.material(tray, "plastic", color="#71898c")
