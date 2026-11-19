"""Bitwise regression against the original float64 noise arithmetic."""
import itertools
import math
import unittest
import numpy as np
from sand3d.implicit import noise
from sand3d.edit import NOISES


def _hash(x, y, z, seed):
    # Integer mixer using explicitly wrapping 32-bit arithmetic.
    with np.errstate(over="ignore"):
        h = (
            x.astype(np.uint32) * np.uint32(1597334677)
            ^ y.astype(np.uint32) * np.uint32(3812015801)
            ^ z.astype(np.uint32) * np.uint32(2798796415)
            ^ np.uint32(seed & 0xFFFFFFFF)
        )
        h = np.asarray(h, dtype=np.uint32)
        h ^= h >> np.uint32(16)
        h *= np.uint32(2246822519)
        h ^= h >> np.uint32(13)
        h *= np.uint32(3266489917)
        return h ^ (h >> np.uint32(16))


def original_noise(x, y, z, seed=0, kind="perlin"):
    """Float64 noise in [-1, 1]; scalars or broadcastable arrays.

    Seeded gradient / nearest-cell noise, stable across runs and bpy versions.
    Coordinates are dimensionless. This is independent of displace's noise.
    """
    if kind not in NOISES:
        raise ValueError(f"noise: kind must be one of {NOISES}")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("noise: seed must be an integer")
    q = np.broadcast_arrays(*[np.asarray(a, dtype=np.float64) for a in (x, y, z)])
    if any(not np.all(np.isfinite(a)) or np.any(np.abs(a) > 2**50) for a in q):
        raise ValueError("noise: coordinates must be finite and within 2**50")
    base = [np.floor(a).astype(np.int64) for a in q]
    frac = [a - b for a, b in zip(q, base)]
    if kind == "cells":
        distance = np.full(q[0].shape, np.inf)
        for delta in itertools.product((-1, 0, 1), repeat=3):
            b = [a + d for a, d in zip(base, delta)]
            dist = np.zeros(q[0].shape)
            for c in range(3):
                offset = (
                    _hash(*b, seed + 1013 * (c + 1)).astype(np.float64) / 4294967296
                )
                dist += (delta[c] + offset - frac[c]) ** 2
            distance = np.minimum(distance, dist)
        result = 1 - 2 * np.minimum(1, np.sqrt(distance) / math.sqrt(3))
    else:
        fade = [f * f * f * (f * (f * 6 - 15) + 10) for f in frac]
        result = np.zeros(q[0].shape)
        for corner in itertools.product((0, 1), repeat=3):
            h = _hash(*[b + d for b, d in zip(base, corner)], seed)
            # Twelve edge directions of the cube, constructed without a table.
            axis = h % 3
            dot = np.zeros(q[0].shape)
            for c in range(3):
                sign = np.where((h >> (c + 3)) & 1, 1.0, -1.0)
                dot += np.where(axis == c, 0.0, sign * (frac[c] - corner[c]))
            weight = np.ones(q[0].shape)
            for c in range(3):
                weight *= fade[c] if corner[c] else 1 - fade[c]
            result += weight * dot
        result = np.clip(result, -1, 1)
        if kind == "ridged":
            result = 1 - 2 * np.abs(result)
        if kind == "turbulence":
            result = 2 * np.abs(result) - 1
    return float(result) if result.ndim == 0 else result


class NoiseIdentity(unittest.TestCase):
    def test_original_bits(self):
        rng = np.random.default_rng(1729)
        coordinates = np.concatenate((
            rng.uniform(-100, 100, (3, 1200)),
            rng.uniform(-2**50, 2**50, (3, 300)),
            rng.integers(-10000, 10000, (3, 200)).astype(float),
            np.array([[0., -0., 2**50, -2**50]] * 3),
        ), axis=1)
        for kind in NOISES:
            for seed in (0, -7, 2**65 + 11):
                with self.subTest(kind=kind, seed=seed):
                    def compare(x, y, z):
                        a = np.asarray(original_noise(x, y, z, seed=seed, kind=kind))
                        b = np.asarray(noise(x, y, z, seed=seed, kind=kind))
                        self.assertEqual(a.dtype, b.dtype)
                        self.assertEqual(a.shape, b.shape)
                        self.assertEqual(a.tobytes(), b.tobytes())
                    compare(*coordinates)
                    compare(*coordinates[:, :31])
                    compare(coordinates[0, :5, None], coordinates[1, None, :7], -3.)
                    compare(coordinates[0, :17, None], coordinates[1, None, :13], -3.)
                    compare(*coordinates[:, :0])
                    for xyz in coordinates[:, ::43].T:
                        compare(*xyz)
