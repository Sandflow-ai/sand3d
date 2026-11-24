import sand3d as s3d


def body_from_views(length=120, width=42, height=36):
    plan = [(0, 0), (length / 4, width), (length * .75, width), (length, 0)]
    top = [(0, height / 2), (length / 4, height),
           (length * .75, height), (length, height / 2)]
    bottom = [(0, height / 2), (length / 4, 0),
              (length * .75, 0), (length, height / 2)]
    part = s3d.body("body", plan, top, bottom, n=3)
    return s3d.material(part, "plastic", color="#798fa5")
