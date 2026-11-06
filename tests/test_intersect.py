"""An intersection must have geometry; a miss leaves the target intact."""
import unittest

import bpy

import sand3d as s3d
from test_solids import closed_volume


class Intersect(unittest.TestCase):

    def setUp(self):
        s3d.empty_scene()

    def test_a_miss_raises_and_leaves_the_part(self):
        a = s3d.at(s3d.box("a", 10, 10, 10), x=20)
        b = s3d.at(s3d.box("b", 10, 10, 10), x=100)
        mesh = a.data
        with self.assertRaises(ValueError) as caught:
            s3d.intersect(a, b)
        self.assertEqual(str(caught.exception),
                         "intersect: 'a' and 'b' share nothing — they miss each other, or only touch "
                         "(their boxes (15, -5, 0) .. (25, 5, 10); (95, -5, 0) .. (105, 5, 10))")
        self.assertEqual(a.data, mesh)
        self.assertAlmostEqual(closed_volume(a)[1], 1000)
        self.assertEqual([o.get("s3d_name") for o in bpy.data.objects], ["a"], "the tool is used up")

    def test_touching_at_a_face_edge_or_point_raises(self):
        for x, y, z in [(10, 0, 0), (10, 10, 0), (10, 10, 10)]:
            with self.subTest(placement=(x, y, z)):
                s3d.empty_scene()
                a = s3d.box("a", 10, 10, 10)
                b = s3d.at(s3d.box("b", 10, 10, 10), x=x, y=y, z=z)
                with self.assertRaisesRegex(ValueError, "^intersect: 'a' and 'b' share nothing"):
                    s3d.intersect(a, b)
                self.assertAlmostEqual(closed_volume(a)[1], 1000)

    def test_overlapping_boxes_do_not_imply_shared_volume(self):
        ring = s3d.tube("ring", 30, 20, 10)
        core = s3d.cylinder("core", 10, 10)
        with self.assertRaisesRegex(ValueError, "^intersect: 'ring' and 'core' share nothing"):
            s3d.intersect(ring, core)

    def test_overlap_containment_and_coincidence_still_work(self):
        for width, x, volume in [(10, 5, 500), (4, 0, 160), (10, 0, 1000)]:
            with self.subTest(width=width, x=x):
                s3d.empty_scene()
                a = s3d.box("a", 10, 10, 10)
                b = s3d.at(s3d.box("b", width, width, 10), x=x)
                self.assertIs(s3d.intersect(a, b), a)
                closed, actual = closed_volume(a)
                self.assertTrue(closed)
                self.assertAlmostEqual(actual, volume)


if __name__ == "__main__":
    unittest.main()
