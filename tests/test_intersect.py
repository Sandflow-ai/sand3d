"""Empty intersections warn and return empty meshes so existing programs continue."""
import unittest
import warnings

import bpy

import sand3d as s3d
from test_solids import closed_volume


class Intersect(unittest.TestCase):

    def setUp(self):
        s3d.empty_scene()

    def assertEmpty(self, ob):
        self.assertEqual(len(ob.data.vertices), 0)
        self.assertEqual(len(ob.data.edges), 0)
        self.assertEqual(len(ob.data.polygons), 0)

    def test_a_miss_warns_and_returns_an_empty_mesh(self):
        a = s3d.at(s3d.box("a", 10, 10, 10), x=20)
        b = s3d.at(s3d.box("b", 10, 10, 10), x=100)
        placement = a.matrix_basis.copy()
        with self.assertWarns(UserWarning) as caught:
            self.assertIs(s3d.intersect(a, b), a)
        self.assertEqual(str(caught.warning),
                         "intersect: 'a' and 'b' share nothing — they miss each other, or only touch "
                         "(their boxes (15, -5, 0) .. (25, 5, 10); (95, -5, 0) .. (105, 5, 10)); "
                         "returning an empty mesh")
        self.assertEqual(caught.filename, __file__)
        self.assertEmpty(a)
        self.assertEqual(a.matrix_basis, placement)
        self.assertEqual([o.get("s3d_name") for o in bpy.data.objects], ["a"], "the tool is used up")

    def test_touching_at_a_face_edge_or_point_warns(self):
        for x, y, z in [(10, 0, 0), (10, 10, 0), (10, 10, 10)]:
            with self.subTest(placement=(x, y, z)):
                s3d.empty_scene()
                a = s3d.box("a", 10, 10, 10)
                b = s3d.at(s3d.box("b", 10, 10, 10), x=x, y=y, z=z)
                with self.assertWarnsRegex(UserWarning, "^intersect: 'a' and 'b' share nothing"):
                    self.assertIs(s3d.intersect(a, b), a)
                self.assertEmpty(a)
                self.assertEqual([o.get("s3d_name") for o in bpy.data.objects], ["a"])

    def test_overlapping_boxes_do_not_imply_shared_volume(self):
        ring = s3d.tube("ring", 30, 20, 10)
        core = s3d.cylinder("core", 10, 10)
        with self.assertWarnsRegex(UserWarning, "^intersect: 'ring' and 'core' share nothing"):
            self.assertIs(s3d.intersect(ring, core), ring)
        self.assertEmpty(ring)
        self.assertEqual([o.get("s3d_name") for o in bpy.data.objects], ["ring"])

    def test_repeated_parts_beyond_a_boundary_do_not_stop_the_program(self):
        boundary = s3d.box("boundary", 16, 16, 10)
        parts = []
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            for i, x in enumerate((0, 10, 20)):
                part = s3d.at(s3d.box(f"part_{i}", 4, 4, 4), x=x)
                parts.append(s3d.intersect(part, s3d.copy(boundary)))
        self.assertEqual(len(parts), 3)
        self.assertAlmostEqual(closed_volume(parts[0])[1], 64)
        for part in parts[1:]:
            self.assertEmpty(part)
        self.assertEqual(len(caught), 2)
        for i, warning in enumerate(caught, 1):
            self.assertIn(f"'part_{i}'", str(warning.message))
            self.assertIn("'boundary'", str(warning.message))
        self.assertEqual(len(bpy.data.objects), 4, "every boundary copy is used up")

    def test_overlap_containment_and_coincidence_still_work(self):
        for width, x, volume in [(10, 5, 500), (4, 0, 160), (10, 0, 1000)]:
            with self.subTest(width=width, x=x):
                s3d.empty_scene()
                a = s3d.box("a", 10, 10, 10)
                b = s3d.at(s3d.box("b", width, width, 10), x=x)
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    self.assertIs(s3d.intersect(a, b), a)
                self.assertEqual(caught, [])
                closed, actual = closed_volume(a)
                self.assertTrue(closed)
                self.assertAlmostEqual(actual, volume)


if __name__ == "__main__":
    unittest.main()
