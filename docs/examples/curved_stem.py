"""Lateral leaves attached by their bases to a curved stem."""
import sand3d as s3d


def curved_stem():
    path = stem_axis()
    stem = stem_part(path)
    frames = s3d.along(path, count=13, spin=137.508, span=(.12, .92))
    frames = frames.turn(ry=60).jitter(rx=5, ry=8, rz=12, seed=2)
    lengths = s3d.vary(24, 5, len(frames), seed=3)
    leaves = [s3d.at(leaf_part(f"leaf{k}", length), on=frame)
              for k, (frame, length) in enumerate(zip(frames, lengths))]
    return s3d.assembly("curved_stem", stem, leaves)


def stem_axis():
    return s3d.spline([(0, 0, 0), (8, 0, 35), (-5, 4, 75), (12, 0, 110)])


def stem_part(path):
    stem = s3d.wire("stem", path, [(0, 2.4), (1, .8)])
    s3d.material(stem, "rubber", color="#48643e")
    return stem


def leaf_part(name, length=24, width=9, thickness=.8):
    leaf = s3d.sweep(name, s3d.ellipse(width, thickness),
                     [(0, 0, 0), (0, 0, length)],
                     scale=[(0, 0), (.35, 1), (1, 0)])
    s3d.material(leaf, "rubber", color="#749950")
    return leaf
