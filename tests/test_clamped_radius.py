"""A corner radius too large for its side — rect(r=), poly(fillet=), wire(fillet=) — is
clamped to the largest that fits, with a ClampedRadius warning; strict mode (SAND3D_STRICT=1,
or `with strict()`) raises, as every release up to 1.6.3. And a loft section whose outline
crosses itself says so."""
import math
import os
import sys
import unittest
import warnings
from unittest import mock

import sand3d as s3d
from sand3d.edit import ClampedRadius, strict
from test_solids import closed_volume

LEG = [(0, 0, 0), (0, 0, 650), (-30, 0, 650)]


def mesh(ob):
    return [tuple(v.co) for v in ob.data.vertices], [tuple(q.vertices) for q in ob.data.polygons]


def outline(profile):
    return [loop.pts for loop in profile.loops]


class Clamped(unittest.TestCase):
    """By default the radius is clamped, and the program goes on."""

    def setUp(self):
        s3d.empty_scene()
        environ = mock.patch.dict(os.environ)     # put back as it was, SAND3D_STRICT included
        environ.start()
        self.addCleanup(environ.stop)
        os.environ.pop("SAND3D_STRICT", None)

    def test_rect(self):
        with self.assertWarns(ClampedRadius) as caught:
            p = s3d.rect(70, 600, r=50)
        self.assertEqual(str(caught.warning), "rect: r=50 too large for the side of 70; clamped to 35")
        self.assertEqual(outline(p), outline(s3d.rect(70, 600, r=35)), "the short sides become half-circles")
        self.assertTrue(closed_volume(s3d.extrude("panel", p, 20))[0])

    def test_poly(self):
        with self.assertWarns(ClampedRadius) as caught:
            p = s3d.poly([(0, 0), (70, 0), (70, 600), (0, 600)], fillet=50)
        self.assertEqual(str(caught.warning),
                         "poly: fillet=50 too large for the side of 70 from (0, 0) to (70, 0); clamped to 35")
        self.assertEqual(outline(p), outline(s3d.poly([(0, 0), (70, 0), (70, 600), (0, 600)], fillet=35)))

    def test_poly_clamps_only_the_corners_of_the_short_sides(self):
        """A trapezoid's two corners on its short side are clamped; the others keep their radius."""
        pts = [(-100, 0), (100, 0), (20, 80), (-20, 80)]
        with self.assertWarns(ClampedRadius):
            p = s3d.poly(pts, fillet=[5, 5, 60, 60])
        q = s3d.poly(pts, fillet=[5, 5, 0, 0])
        self.assertEqual(len(p.loops), 1)
        bottom = sorted(pt for pt in p.loops[0].pts if pt[1] < 1)
        kept = sorted(pt for pt in q.loops[0].pts if pt[1] < 1)
        self.assertEqual(len(bottom), len(kept), "the bottom corners keep 5")
        for a, b in zip(bottom, kept):
            self.assertAlmostEqual(a[0], b[0], places=4)
            self.assertAlmostEqual(a[1], b[1], places=4)
        self.assertLess(min(math.dist(pt, (0, 80)) for pt in p.loops[0].pts), 1e-3, "the two arcs meet mid-side")

    def test_wire(self):
        with self.assertWarns(ClampedRadius) as caught:
            ob = s3d.wire("short", LEG, 33, fillet=60)
        self.assertEqual(str(caught.warning),
                         "wire: fillet=60 too large for the side of 30 from (0, 0, 650) to (-30, 0, 650); "
                         "clamped to 30")
        self.assertEqual(mesh(ob), mesh(s3d.wire("fits", LEG, 33, fillet=30)))

    def test_wire_preserves_the_minimum_bend_radius(self):
        pts = [(0, 0), (0, 100), (10, 100), (10, 200)]
        with self.assertWarns(ClampedRadius) as caught:
            ob = s3d.wire("minimum", pts, 4, fillet=[0, 100, 2, 0])
        self.assertIn("clamped to 8", str(caught.warning))
        self.assertEqual(mesh(ob), mesh(s3d.wire("fits", pts, 4, fillet=[0, 8, 2, 0])))
        self.assertTrue(closed_volume(ob)[0])

    def test_a_wire_clamped_tighter_than_its_radius_raises(self):
        with self.assertRaisesRegex(ValueError, r"^wire: fillet too large for the side from \(0.0, 0.0, 650.0\) to "
                                                r"\(-30.0, 0.0, 650.0\) \(60 > 30\): the largest fillet that fits at "
                                                r"\(0, 0, 650\), 30, is tighter than the wire's radius 40 \(d / 2\)"):
            s3d.wire("thick", LEG, 80, fillet=60)

    def test_the_warning_points_at_the_program_line(self):
        """At the line of the program that calls the verb, however deep in the library it was found."""
        lines = []

        def build():
            lines.append(sys._getframe().f_lineno + 1)
            s3d.extrude("panel", s3d.rect(70, 600, r=50), 20)
        with warnings.catch_warnings(record=True) as seen:
            warnings.simplefilter("always")
            build()
            lines.append(sys._getframe().f_lineno + 1)
            s3d.wire("short", LEG, 33, fillet=60)
        self.assertEqual([(w.category, w.filename, w.lineno) for w in seen],
                         [(ClampedRadius, __file__, n) for n in lines])

    def test_a_chamfer_too_large_still_raises(self):
        with self.assertRaisesRegex(ValueError, r"^chamfer too large for the side"):
            s3d.rect(70, 600, chamfer=50)


class Strict(unittest.TestCase):
    """Strict mode: the error of every release up to 1.6.3, unchanged."""

    def setUp(self):
        s3d.empty_scene()

    def test_strict_raises(self):
        with strict():
            with self.assertRaisesRegex(ValueError, r"^fillet too large for the side from \(-35.0, -300.0\) to "
                                                    r"\(35.0, -300.0\) \(100 > 70\)$"):
                s3d.rect(70, 600, r=50)
            with self.assertRaisesRegex(ValueError, r"^fillet too large for the side from \(0.0, 0.0\) to "
                                                    r"\(70.0, 0.0\) \(100 > 70\)$"):
                s3d.poly([(0, 0), (70, 0), (70, 600), (0, 600)], fillet=50)
            with self.assertRaisesRegex(ValueError, r"^wire: fillet too large for the side from \(0.0, 0.0, 650.0\) "
                                                    r"to \(-30.0, 0.0, 650.0\) \(60 > 30\)$"):
                s3d.wire("short", LEG, 33, fillet=60)

    def test_the_environment_makes_it_strict(self):
        with mock.patch.dict(os.environ, {"SAND3D_STRICT": "1"}):
            with self.assertRaisesRegex(ValueError, r"^fillet too large"):
                s3d.rect(70, 600, r=50)
            with strict(False), self.assertWarns(ClampedRadius):
                s3d.rect(70, 600, r=50)


class LoftSection(unittest.TestCase):
    """A section poly split because its outline crosses itself is not a section with holes."""

    def setUp(self):
        s3d.empty_scene()

    def test_a_section_that_crosses_itself_says_where(self):
        # the shoulders (z = 490) dip below the base (z = 500): the outline crosses itself
        sec = s3d.poly([(-500, 500), (500, 500), (380, 490), (120, 700), (-120, 700), (-380, 490)])
        ok = s3d.poly([(-500, 500), (500, 500), (380, 900), (120, 1000), (-120, 1000), (-380, 900)])
        with self.assertRaises(ValueError) as caught:
            s3d.loft("shell", s3d.at(ok, y=0, rx=90), s3d.at(sec, y=1000, rx=90))
        self.assertEqual(str(caught.exception),
                         "loft: section 2 crosses itself near (367.619, 500) — poly split its outline into 3 pieces, "
                         "and a section is one outline: move its points so that its sides do not cross")

    def test_a_section_with_a_hole_says_so_as_before(self):
        with self.assertRaises(ValueError) as caught:
            s3d.loft("h", s3d.at(s3d.rect(100, 100) - s3d.circle(20)), s3d.at(s3d.rect(100, 100), z=50))
        self.assertEqual(str(caught.exception), "loft: each section must be one outline, without holes")


if __name__ == "__main__":
    unittest.main()
