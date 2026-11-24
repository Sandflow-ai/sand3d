import sand3d as s3d


def build(wavelength=16, width=64, thickness=8, amount=3, gap=78):
    fields = [s3d.waves(wavelength, direction="+X", sharpness=.6),
              s3d.waves(wavelength, centers=[(0, 0)], decay=width / 2)]
    parts = []
    for i, height in enumerate(fields):
        plate = s3d.box(f"waves{i}", width, width, thickness)
        s3d.displace(plate, amount, wavelength / 4, noise=height, direction="+Z", faces="top", step=wavelength / 16)
        parts.append(s3d.at(plate, x=i * gap))
    result = s3d.group("heights", *parts)
    s3d.material(result, "plastic", color="#729ba0")
    return result
