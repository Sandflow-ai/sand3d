import sand3d as s3d


def four_noises(seed=0, d=60, gap=80):
    kinds = ["perlin", "cells", "ridged", "turbulence"]
    pebbles = [s3d.at(pebble(kind, d, seed), x=(k - 1.5) * gap) for k, kind in enumerate(kinds)]
    return s3d.assembly("four_noises", pebbles)


def pebble(kind, d, seed, amount=8, size=16):
    stone = s3d.displace(s3d.sphere("pebble", d), amount, size, noise=kind, seed=seed)
    return s3d.material(stone, "rock", color="#5a554d")
