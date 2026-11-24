import sand3d as s3d


def placement(width=90, depth=55, height=12, peg_d=14, peg_h=45):
    base = s3d.material(s3d.box("base", width, depth, height), "oak")
    peg = s3d.material(s3d.cylinder("peg", peg_d, peg_h), "painted_metal", color="#3f6e98")
    peg = s3d.at(peg, on=base.face("top"), x=-width / 3, scale=.75)
    twin = s3d.transform(s3d.copy(peg), mirror="x")
    cap = s3d.material(s3d.box("cap", width / 2, depth / 3, height), "brass")
    cap = s3d.at(cap, on=s3d.bbox(peg, "+Z"), anchor="-Z")
    pivot = s3d.local(base, y=depth / 3, z=height)
    marker = s3d.at(s3d.sphere("pivot", peg_d / 2), on=pivot)
    s3d.material(marker, "plastic", color="#a84336")
    return s3d.group("placement", base, peg, twin, cap, marker)
