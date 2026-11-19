"""Bounded organic variation, transported frames and curved branch attachment."""
import math
import random
import unittest

import sand3d as s3d
from sand3d.frames import Frames
from mathutils import Vector


class Variation(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()

    def assertVector(self, a, b, tolerance=1e-4):
        self.assertLess((Vector(a) - Vector(b)).length, tolerance)

    def test_jitter_local_axes_bounds_and_part_memory(self):
        part = s3d.box("base", 20, 20, 20)
        base = part.face("top").turn(ry=70)
        frames = Frames([base] * 500)
        state = random.getstate()
        varied = frames.jitter(rx=8, ry=12, rz=20, x=3, y=4, z=5, seed=9)
        self.assertEqual(state, random.getstate())
        self.assertIsInstance(varied, Frames)
        self.assertEqual([repr(f) for f in varied], [repr(f) for f in frames.jitter(rx=8, ry=12, rz=20, x=3, y=4, z=5, seed=9)])
        self.assertGreater(len({repr(f) for f in varied}), 490)
        for f in varied:
            self.assertIs(f.part, part)
            self.assertEqual(f._basis, base._basis)
            delta = f.origin - base.origin
            for axis, bound in zip((base.x, base.y, base.z), (3, 4, 5)):
                self.assertLessEqual(abs(delta.dot(axis)), bound)
        self.assertVector(frames.jitter()[0].x, base.x)
        rng = random.Random(9)
        a, b, c, dx, dy, dz = [rng.triangular(-v, v, 0) for v in (8, 12, 20, 3, 4, 5)]
        expected = base.move(dx, dy, dz).turn(a, b, c)
        self.assertVector(varied[0].x, expected.x)
        self.assertVector(varied[0].origin, expected.origin)

    def test_vary_triangular_distribution(self):
        state = random.getstate()
        values = s3d.vary(10, 2, 10000, seed=1)
        self.assertEqual(state, random.getstate())
        self.assertEqual(values, s3d.vary(10, 2, 10000, seed=1))
        self.assertTrue(all(8 <= v <= 12 for v in values))
        self.assertAlmostEqual(sum(values) / len(values), 10, delta=.04)
        variance = sum((v - 10) ** 2 for v in values) / len(values)
        self.assertAlmostEqual(variance, 4 / 6, delta=.04)
        self.assertEqual(s3d.vary(-5, 0, 3), [-5.] * 3)
        zero = s3d.vary(0, 2, 1000, seed=3)
        self.assertTrue(all(-2 <= v <= 2 for v in zero) and min(zero) < -1 and max(zero) > 1,
                        "round zero, values fall either side")

    def test_along_span_spin_and_vertical_continuity(self):
        path = [(0, 0, 0), (0, 0, 100)]
        frames = s3d.along(path, count=5, span=(.1, .9), spin=90)
        self.assertEqual([round(f.origin.z) for f in frames], [10, 30, 50, 70, 90])
        self.assertVector(frames[1].x, (0, 1, 0))
        self.assertEqual([round(f.origin.z) for f in s3d.along(path, pitch=30, span=(.1, .9))], [10, 40, 70])
        curve = [(0, 0, 0), (0, 0, 10), (.01, 0, 20), (-.01, 0, 30), (0, 0, 40)]
        frames = s3d.along(curve, count=20, spin=.001)
        self.assertTrue(all(a.x.dot(b.x) > .999 for a, b in zip(frames, frames[1:])))
        # Transport is independent of sampling density, including skipped corners.
        sparse = s3d.along(curve, count=2, spin=13)
        dense = s3d.along(curve, count=5, spin=13 / 4)
        self.assertVector(sparse[-1].x, dense[-1].x)
        self.assertEqual(len(s3d.along(s3d.circle(20), count=8)), 8)
        self.assertEqual(len(s3d.along(path, count=0)), 0)

    def test_scatter_bounds_radial_orientation_and_placement(self):
        base = s3d.Frame((10, 20, 30)).turn(ry=45, rz=20)
        state = random.getstate()
        for surface in (False, True):
            frames = s3d.scatter(100, (40, 60, 80), seed=3, surface=surface, on=base)
            self.assertEqual([repr(f) for f in frames], [repr(f) for f in s3d.scatter(100, (40, 60, 80), seed=3, surface=surface, on=base)])
            for f in frames:
                delta = f.origin - base.origin
                norm = sum((delta.dot(a) / r) ** 2 for a, r in zip((base.x, base.y, base.z), (20, 30, 40)))
                self.assertLessEqual(norm, 1.00001)
                if surface:
                    self.assertAlmostEqual(norm, 1, places=5)
                self.assertVector(f.z, delta.normalized())
        self.assertEqual(state, random.getstate())
        self.assertEqual(s3d.scatter(0, (1, 1, 1)), [])

    def test_scatter_spacing_and_snap(self):
        frames = s3d.scatter(100, (100, 100, 100), surface=True, seed=5)
        nearest = min((a.origin - b.origin).length for i, a in enumerate(frames) for b in frames[i+1:])
        self.assertGreater(nearest, 5)
        ball = s3d.at(s3d.sphere("ball", 80), z=-40)
        snapped = s3d.snap(ball, frames)
        self.assertEqual(len(snapped), 100)
        self.assertTrue(all(39 < f.origin.length < 40.01 for f in snapped))

    def test_curved_children_attach_by_arc_length_and_tips_follow_tangent(self):
        axes = s3d.branches(100, 2, levels=1, children=1, angle=0, attach=(.63, .63), wander=8, droop=35, seed=4)
        root, child = axes
        self.assertGreater(len(root.path), 9)
        expected = s3d.along(root.path, count=1, span=(.63, .63))[0]
        self.assertVector(child.path[0], expected.origin)
        tip = axes.tips[0]
        self.assertVector(tip.origin, child.path[-1])
        self.assertVector(tip.z, (Vector(child.path[-1]) - Vector(child.path[-2])).normalized())
        s3d.wire(root.name, root.path, root.d)
        s3d.wire(child.name, child.path, child.d)
        straight = s3d.branches(100, 2, levels=1, children=1, jitter=0)
        self.assertEqual(straight[0].path.points, [(0., 0., 0.), (0., 0., 100.)])
        base = s3d.Frame().turn(ry=90)
        falling = s3d.branches(100, 2, levels=0, on=base, droop=45)
        rising = s3d.branches(100, 2, levels=0, on=base, droop=-45)
        self.assertAlmostEqual(falling.tips[0].z.dot(base.z), math.cos(math.radians(45)), delta=.005)
        self.assertVector(rising.tips[0].z, base.z)
        rising_child = s3d.branches(100, 2, levels=1, children=1, angle=65, droop=-35)
        self.assertAlmostEqual(rising_child.tips[0].z.z, math.cos(math.radians(30)), delta=.005)

    def test_curved_axes_build_for_large_turns_and_thick_sections(self):
        for params in (
                dict(length=200, d=41, wander=80, droop=90, tip_ratio=.15),
                dict(length=60, d=120, wander=160, droop=-120, tip_ratio=1),
                dict(length=100, d=65, wander=120, droop=180, tip_ratio=0)):
            for seed in range(100):
                with self.subTest(params=params, seed=seed):
                    s3d.empty_scene()
                    axes = s3d.branches(**params, levels=1, children=2, jitter=.8,
                                        length_ratio=.35, diameter_ratio=.8, seed=seed,
                                        on=s3d.Frame((1000, -2000, 3000)).turn(ry=65))
                    for axis in axes:
                        s3d.wire(axis.name, axis.path, axis.d)
                        d0, d1 = axis.d[0][1], axis.d[-1][1]
                        s3d.sweep(axis.name, s3d.polygon(8, d0), axis.path,
                                  scale=[(0, 1), (1, d1 / d0)])

    def test_thin_curved_axes_build_far_from_origin(self):
        for seed in range(10):
            s3d.empty_scene()
            axes = s3d.branches(500, 16, levels=2, children=2, tip_ratio=0,
                                wander=25, droop=-25, jitter=.6, seed=seed,
                                on=s3d.Frame((0, -2000, 2000), normal=(.2, -.4, .9)))
            for axis in axes:
                with self.subTest(seed=seed, axis=axis.name):
                    s3d.wire(axis.name, axis.path, axis.d)
                    s3d.sweep(axis.name, s3d.polygon(8, axis.d[0][1]), axis.path,
                              scale=[(0, 1), (1, 0)])

    def test_curvature_limit_preserves_units_and_thin_wander(self):
        paths = []
        for unit, factor in (("mm", 1), ("m", .001)):
            s3d.empty_scene()
            s3d.units(unit)
            axis = s3d.branches(200 * factor, 41 * factor, levels=0,
                                wander=80, droop=90, seed=3)[0]
            paths.append([Vector(p) / factor for p in axis.path])
            s3d.wire(axis.name, axis.path, axis.d)
        self.assertEqual(len(paths[0]), len(paths[1]))
        for a, b in zip(*paths):
            self.assertVector(a, b, .002)
        s3d.empty_scene()
        s3d.units("mm")
        thin = s3d.branches(200, 1, levels=0, wander=40, seed=2)[0]
        thick = s3d.branches(200, 100, levels=0, wander=40, seed=2)[0]

        def turns(axis):
            segments = [(Vector(b) - Vector(a)).normalized()
                        for a, b in zip(axis.path, axis.path[1:])]
            return sum(a.angle(b) for a, b in zip(segments, segments[1:]))

        self.assertGreater(turns(thin), 1)
        self.assertGreater(turns(thin), 2 * turns(thick))

    def test_scatter_mesh_surface_normals_placement_and_spacing(self):
        ball = s3d.at(s3d.sphere("ball", 80), x=25, y=-10, z=-40, ry=25)
        state = random.getstate()
        frames = s3d.scatter(180, ball, seed=5)
        self.assertEqual(state, random.getstate())
        self.assertEqual([repr(f) for f in frames],
                         [repr(f) for f in s3d.scatter(180, ball, seed=5)])
        projected = s3d.snap(ball, frames)
        for f, g in zip(frames, projected):
            self.assertVector(f.origin, g.origin, 2e-4)
            self.assertGreater(f.z.dot(g.z), .9)  # snap may use a nonplanar quad normal
        nearest = min((a.origin - b.origin).length for i, a in enumerate(frames) for b in frames[i+1:])
        self.assertGreater(nearest, 3)
        self.assertEqual(s3d.scatter(0, ball), [])
        with self.assertRaisesRegex(ValueError, "on"):
            s3d.scatter(1, ball, on=s3d.Frame())
        with self.assertRaisesRegex(ValueError, "area"):
            s3d.scatter(1, [])

    def test_scatter_reflected_scaled_part_normals(self):
        part = s3d.transform(s3d.box("part", 10, 20, 30), mirror="x")
        part.scale = (-2, 1, .5)
        for f in s3d.scatter(100, part, seed=4):
            centre = part.matrix_basis @ Vector((0, 0, 15))
            self.assertGreater((f.origin - centre).dot(f.z), 0)
            delta = part.matrix_basis.inverted() @ f.origin - Vector((0, 0, 15))
            self.assertAlmostEqual(max(abs(delta.x) / 5, abs(delta.y) / 10,
                                       abs(delta.z) / 15), 1, delta=1e-5)

    def test_scatter_mesh_area_weights_and_parent_space(self):
        # Two translated cubes, area ratio 1:4. A single candidate selection has
        # no spacing bias, so independent seeds test the area distribution.
        a = s3d.at(s3d.box("small", 10, 10, 10), x=-100)
        b = s3d.at(s3d.box("large", 20, 20, 20), x=100)
        group = s3d.at(s3d.group("parent", a, b), x=500)
        count = sum(s3d.scatter(1, [a, b], seed=k)[0].origin.x > 0 for k in range(500))
        self.assertTrue(365 < count < 435, count)
        for f in s3d.scatter(100, [a, b], seed=8):
            centre = Vector((-100, 0, 5) if f.origin.x < 0 else (100, 0, 10))
            half = 5 if f.origin.x < 0 else 10
            self.assertAlmostEqual(max(abs(c) for c in f.origin - centre), half, delta=1e-4)
            self.assertGreater((f.origin - centre).dot(f.z), 0)
        self.assertEqual(group.location.x, 500)

    def test_scatter_mesh_sampling_keeps_placements_across_units(self):
        samples = []
        for unit, k in (("mm", 1), ("m", .001)):
            s3d.empty_scene()
            s3d.units(unit)
            fruit = s3d.at(s3d.sphere("fruit", 40 * k), x=10 * k, ry=30)
            stone = s3d.at(s3d.box("stone", 10 * k, 15 * k, 20 * k), x=60 * k)
            samples.append([(f.origin / k, f.z) for f in s3d.scatter(120, [fruit, stone], seed=3)])
        for (p, n), (q, m) in zip(*samples):
            self.assertVector(p, q, .001)
            self.assertVector(n, m, .001)
        s3d.empty_scene()
        s3d.units("mm")

    def test_validation(self):
        calls = [lambda: Frames().jitter(x=-1), lambda: Frames().jitter(seed="x"),
                 lambda: s3d.vary(2, -.1, 3), lambda: s3d.vary(math.nan, .1, 3),
                 lambda: s3d.vary(2, .1, 2.5), lambda: s3d.vary(2, .1, 2, seed=None),
                 lambda: s3d.scatter(4097, (1, 1, 1)), lambda: s3d.scatter(2, (1, 0, 1)),
                 lambda: s3d.scatter(2, (1, 1)), lambda: s3d.branches(10, 1, wander=-1),
                 lambda: s3d.branches(10, 1, droop=math.inf)]
        for kw in ({"span": (-.1, 1)}, {"spin": math.nan}, {"pitch": -1}, {"count": -2}):
            calls.append(lambda kw=kw: s3d.along([(0, 0, 0), (0, 0, 1)], **kw))
        for call in calls:
            with self.assertRaises(ValueError):
                call()
