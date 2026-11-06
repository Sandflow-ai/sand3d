"""`facets` sets the segments of a full circle for the whole program, as `units` sets its unit."""
import unittest

import sand3d as s3d


def sides(ob):
    """Faces of a prism standing on Z = 0 that are neither its top nor its bottom."""
    return sum(1 for f in ob.data.polygons if abs(f.normal.z) < 1e-6)


class Facets(unittest.TestCase):

    def setUp(self):
        s3d.empty_scene()

    def tearDown(self):
        s3d.empty_scene()

    def test_auto_by_default(self):
        self.assertEqual(s3d.facets(), "auto")
        self.assertEqual(sides(s3d.cylinder("c", 20, 10)), 32)     # 10 mm radius at the 0.05 mm chord

    def test_a_count_is_the_same_for_every_radius(self):
        s3d.facets(8)
        for d in (2, 20, 2000):
            self.assertEqual(sides(s3d.cylinder(f"c{d}", d, 10)), 8)
        self.assertEqual(s3d.facets(), 8)

    def test_an_arc_takes_its_share(self):
        s3d.facets(12)
        half = s3d.extrude("half", s3d.poly([(0, 0), s3d.arc((0, 0), 10, 0, 180)]), 5)
        self.assertEqual(sides(half), 6 + 2)                        # six pieces of arc, and a radius to each end

    def test_a_fillet_takes_its_quarter(self):
        s3d.facets(8)
        plate = s3d.box("plate", 40, 40, 10)
        before = len(plate.data.polygons)
        s3d.fillet(plate, 2, edges="top")
        self.assertGreater(len(plate.data.polygons), before)
        auto = len(plate.data.polygons)
        s3d.empty_scene()
        plate = s3d.box("plate", 40, 40, 10)
        s3d.fillet(plate, 2, edges="top")
        self.assertGreater(len(plate.data.polygons), auto)

    def test_set_after_the_first_verb(self):
        s3d.box("b", 10, 10, 10)
        with self.assertRaises(ValueError) as caught:
            s3d.facets(8)
        self.assertEqual(str(caught.exception), "facets: set 8 before the first verb — this scene is already "
                                                "built with 'auto' (s3d.empty_scene() starts over)")

    def test_the_same_value_again_is_no_change(self):
        s3d.facets(8)
        s3d.box("b", 10, 10, 10)
        self.assertEqual(s3d.facets(8), 8)

    def test_not_a_count(self):
        for bad in (2, 0, -8, 8.0, True, "low", [8]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                s3d.facets(bad)

    def test_empty_scene_goes_back_to_auto_once_built(self):
        s3d.facets(8)
        s3d.empty_scene()
        self.assertEqual(s3d.facets(), 8)                           # nothing built: what was set holds
        s3d.cylinder("c", 20, 10)
        s3d.empty_scene()
        self.assertEqual(s3d.facets(), "auto")

    def test_auto_resets(self):
        s3d.facets(8)
        self.assertEqual(s3d.facets("auto"), "auto")
        self.assertEqual(sides(s3d.cylinder("c", 20, 10)), 32)


if __name__ == "__main__":
    unittest.main()
