"""Convex solids and grain that keeps their planar envelope."""
import itertools
import math
import random
import unittest

from mathutils import Matrix, Vector
import sand3d as s3d
from test_solids import closed_volume


class Hull(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()

    def test_cube_with_duplicate_and_interior_points(self):
        corners = list(itertools.product((-10, 10), (-15, 15), (5, 25)))
        ob = s3d.hull("stone", (s3d.Frame(p) for p in corners + [(0, 0, 10), corners[0]]))
        self.assertEqual(len(ob.data.vertices), 8)
        closed, volume = closed_volume(ob)
        self.assertTrue(closed)
        self.assertAlmostEqual(volume, 12000)
        self.assertEqual(ob.matrix_basis, Matrix.Identity(4))
        self.assertAlmostEqual(ob.face("+Z").origin.z, 25)
        self.assertFalse(any(a.name.startswith("s3d_face:") for a in ob.data.attributes))
        self.assertTrue(all(e.use_edge_sharp for e in ob.data.edges))

    def test_contains_every_point(self):
        rng = random.Random(19)
        points = [tuple(rng.uniform(-20, 20) for _ in range(3)) for _ in range(40)]
        ob = s3d.hull("stone", points)
        self.assertTrue(closed_volume(ob)[0])
        self.assertGreater(closed_volume(ob)[1], 0)
        for face in ob.data.polygons:
            for point in points:
                self.assertLessEqual((Vector(point) - face.center).dot(face.normal), 1e-5)

    def test_input_order_does_not_change_mesh(self):
        points = list(itertools.product((-10, 10), repeat=3))
        a = s3d.hull("a", points)
        b = s3d.hull("b", reversed(points))
        self.assertEqual([tuple(v.co) for v in a.data.vertices], [tuple(v.co) for v in b.data.vertices])
        self.assertEqual([tuple(f.vertices) for f in a.data.polygons], [tuple(f.vertices) for f in b.data.polygons])

    def test_coordinates_follow_the_program_unit(self):
        points = [(0, 0, 0), (20, 0, 0), (0, 30, 0), (0, 0, 40)]
        try:
            for unit, scale in (("mm", 1), ("m", 0.001)):
                s3d.empty_scene()
                s3d.units(unit)
                ob = s3d.hull("tetrahedron", [tuple(c * scale for c in p) for p in points])
                self.assertTrue(closed_volume(ob)[0])
                self.assertAlmostEqual(closed_volume(ob)[1] / scale ** 3, 4000, delta=0.001)
        finally:
            s3d.empty_scene()
            s3d.units("mm")

    def test_degenerate_and_invalid_points(self):
        for points in ([], [(0, 0, 0)] * 4, [(0, 0, 0), (1, 0, 0), (0, 1, 0)],
                       [(i, 0, 0) for i in range(4)], list(itertools.product((0, 1), (0, 1), (0,)))):
            with self.subTest(points=points), self.assertRaisesRegex(ValueError, "hull:.*(4|coplanar|degenerate)"):
                s3d.hull("bad", points)
        for point in ((math.nan, 0, 0), (math.inf, 0, 0), (1, 2), ("x", 0, 0)):
            with self.subTest(point=point), self.assertRaisesRegex(ValueError, "finite"):
                s3d.hull("bad", [(0, 0, 0), point])
        # An error creates no scene object.
        import bpy
        self.assertEqual(len(bpy.data.objects), 0)

    def test_grain_preserves_planes_and_ridges(self):
        corners = list(itertools.product((-10, 10), repeat=3))
        rock = s3d.hull("stone", corners)
        amount = 0.02
        s3d.displace(rock, amount=amount, size=4, seed=3)
        self.assertTrue(closed_volume(rock)[0])
        # Every refined vertex remains within amount of an original face plane.
        # A smoothing subdivision would pull corners far inside this envelope.
        for v in rock.data.vertices:
            self.assertLessEqual(min(abs(abs(c) - 10) for c in v.co), amount + 1e-5)
        for point in corners:
            self.assertLessEqual(min((v.co - Vector(point)).length for v in rock.data.vertices), amount + 1e-5)
