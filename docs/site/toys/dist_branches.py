import sand3d as s3d


def three_saplings(seed=0, gap=650):
    stiff = sapling(seed, wander=0, droop=0)
    rising = sapling(seed, wander=15, droop=-25)
    weeping = sapling(seed, wander=15, droop=40)
    return s3d.assembly("three_saplings", s3d.at(stiff, x=-gap), rising, s3d.at(weeping, x=gap))


def sapling(seed, wander, droop, length=700, d=40):
    axes = s3d.branches(length, d, levels=2, wander=wander, droop=droop, seed=seed)
    wood = s3d.merge([s3d.wire(a.name, a.path, a.d) for a in axes])
    return s3d.material(wood, "bark")
