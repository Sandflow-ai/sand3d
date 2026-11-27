import sand3d as s3d


def gourd():
    body = s3d.wire("gourd", [(0, 0, 0), (0, 0, 160)],
                    d=[(0, 0), (0.08, 60), (0.35, 110), (0.6, 70), (0.85, 85), (1, 0)])
    s3d.displace(body, 3, 12, seed=2)
    dots = s3d.pattern("bubbles", 8, density=0.7)
    s3d.material(body, "plastic", roughness=0.45,
                 texture=s3d.texture(32, color=(dots.levels(0.2, 0.4), "#e9e2d0", "#c0392b"), height=0.4 * dots))
    return s3d.unwrap(body, by="build")
