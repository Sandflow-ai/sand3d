import sand3d as s3d


def profile_solids(width=40, height=60, gap=70):
    prism = s3d.extrude("twisted", s3d.rect(width, width / 2), height, twist=60)
    outline = s3d.poly([(0, 0), (width / 2, 0), (width / 3, height / 2),
                        (width / 2, height), (0, height)])
    turned = s3d.revolve("turned", outline, angle=270)
    s3d.material(prism, "plastic", color="#798fa5")
    s3d.material(turned, "plastic", color="#b68d69")
    return s3d.assembly("profile_solids", s3d.at(prism, x=-gap / 2),
                        s3d.at(turned, x=gap / 2))
