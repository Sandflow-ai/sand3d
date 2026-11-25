import sand3d as s3d


def pond(size=3000, depth=500, basin=(1600, 1000), dig=400, margin=60, swell=0, wavelength=700):
    """A garden pond: still water, or a wind-blown swell `swell` high."""
    lawn = s3d.material(s3d.box("lawn", size, size, depth), "grass")
    hollow = s3d.extrude("hollow", s3d.ellipse(*basin), dig + margin, taper=-30)
    s3d.cut(lawn, s3d.at(hollow, z=depth - dig))
    water = s3d.fill("water", lawn, depth - margin)
    s3d.material(water, "water", absorb="#5f9c8a", absorb_distance=800)
    if swell:
        waves = s3d.waves(wavelength, direction=30, sharpness=0.5, spread=15)
        s3d.displace(water, swell, wavelength / 8, noise=waves, direction="+Z", faces="top")
    return s3d.group("pond", lawn, water)
