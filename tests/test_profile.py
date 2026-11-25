"""Profiles: areas, loops and corners, against what geometry says they must be."""
import math
import unittest

import sand3d as s3d
from mathutils import Vector
from sand3d.edit import strict
from sand3d.profile import _centripetal


def corners(p):
    return sum(p.mesh()[1])


class Profiles(unittest.TestCase):

    def assertArea(self, p, expected, rel=0.01):
        self.assertAlmostEqual(p.area(), expected, delta=abs(expected) * rel)

    def test_rect_and_its_corners(self):
        self.assertArea(s3d.rect(40, 20), 800, rel=1e-12)
        self.assertEqual(corners(s3d.rect(40, 20)), 4)
        self.assertArea(s3d.rect(40, 20, r=4), 800 - (4 - math.pi) * 16)
        self.assertEqual(corners(s3d.rect(40, 20, r=4)), 0)
        self.assertArea(s3d.rect(40, 20, chamfer=3), 800 - 4 * 4.5, rel=1e-12)

    def test_round_shapes(self):
        self.assertArea(s3d.circle(20), math.pi * 100)
        self.assertArea(s3d.ellipse(40, 20), math.pi * 200)
        self.assertArea(s3d.slot(50, 10), 400 + math.pi * 25)
        self.assertArea(s3d.polygon(6, 20), 1.5 * math.sqrt(3) * 100, rel=1e-12)
        self.assertEqual(corners(s3d.circle(20)), 0)

    def test_union_difference_and_holes(self):
        washer = s3d.circle(30) - s3d.circle(10)
        self.assertEqual(len(washer.loops), 2)
        self.assertArea(washer, math.pi * (225 - 25))
        self.assertArea(s3d.rect(40, 10) + s3d.rect(10, 40), 700, rel=1e-12)
        split = s3d.rect(40, 40) - s3d.rect(20, 80)
        self.assertArea(split, 800, rel=1e-12)
        self.assertEqual(len(split.loops), 2, "a strip right across leaves two pieces")

    def test_placed_profiles_combine_in_their_plane(self):
        frame = s3d.rect(70, 70) - s3d.at(s3d.circle(6), x=-30) - s3d.at(s3d.circle(6), x=30)
        self.assertEqual(len(frame.loops), 3)
        self.assertArea(frame, 4900 - 2 * math.pi * 9)
        turned = s3d.rect(10, 10) + s3d.at(s3d.rect(10, 10), rz=45)
        self.assertArea(turned, 200 - 8 * 25 * math.tan(math.pi / 8), rel=1e-9)  # minus the octagon they share
        self.assertRaises(ValueError, lambda: s3d.rect(10, 10) - s3d.at(s3d.circle(4), z=3))

    def test_arcs_inside_poly(self):
        expected = 400 + math.pi * 100 / 2
        for run in (s3d.arc((20, 10), 10, -90, 90), s3d.arc(through=(30, 10), to=(20, 20)),
                    s3d.tangent_arc((20, 20))):
            p = s3d.poly([(0, 0), (20, 0), run, (0, 20)])
            self.assertArea(p, expected)
            self.assertEqual(corners(p), 2, "the arc meets its lines tangent: only (0, 0) and (0, 20) are corners")

    def test_fillet_and_chamfer_corners(self):
        ell = [(0, 0), (30, 0), (30, 10), (10, 10), (10, 30), (0, 30)]
        self.assertEqual(corners(s3d.poly(ell, fillet=2)), 0)
        inner = s3d.poly(ell, fillet=[0, 0, 0, 3, 0, 0])
        self.assertEqual(corners(inner), 5)
        self.assertArea(inner, 500 + (1 - math.pi / 4) * 9)
        with strict():      # too large for a side: an error in strict mode, clamped otherwise (test_clamped_radius)
            self.assertRaises(ValueError, s3d.poly, ell, fillet=12)

    def test_offset(self):
        self.assertArea(s3d.offset(s3d.rect(40, 20), 2), 800 + 2 * 120 + math.pi * 4)
        self.assertArea(s3d.offset(s3d.rect(40, 20), -2), 36 * 16, rel=1e-9)
        grown = s3d.offset(s3d.circle(30) - s3d.circle(10), 2)
        self.assertArea(grown, math.pi * (17 ** 2 - 3 ** 2))

    def test_mirror_completes_a_half(self):
        half = s3d.poly([(0, 0), (20, 0), (20, 5), (5, 20), (0, 20)])
        whole = s3d.mirror(half)
        self.assertArea(whole, 2 * half.area(), rel=1e-9)
        self.assertEqual(corners(whole), 6, "the points on the axis are no corners")

    def test_crossing_outline_is_resolved(self):
        self.assertArea(s3d.poly([(0, 0), (20, 20), (20, 0), (0, 20)]), 200, rel=1e-9)

    def test_spline_leaves_and_reaches_along_its_tangents(self):
        pts = [(0, 0), (20, 10), (40, 0)]
        for t0, t1 in (((1, 0), (1, 0)), ((0, 1), (1, -1)), ((3, 1), (0, -2))):
            # Sampled finely, the first and last pieces are the tangent itself.
            p = _centripetal(pts, False, steps=1000, tangents=(t0, t1))
            for (a, b), t in (((p[0], p[1]), t0), ((p[-2], p[-1]), t1)):
                d = Vector((b[0] - a[0], b[1] - a[1])).normalized()
                self.assertGreater(d.dot(Vector(t).normalized()), 0.9999, (t0, t1))
        # Through the same points whatever the tangents, and the default is untouched.
        self.assertEqual(s3d.spline(pts, tangents=((0, 1), None)).points[12], (20.0, 10.0, 0.0))
        self.assertEqual(s3d.spline(pts).points, s3d.spline(pts, False, (None, None)).points)
        self.assertNotEqual(s3d.spline(pts).points, s3d.spline(pts, tangents=((0, 1), None)).points)
        with self.assertRaises(ValueError):
            s3d.spline(pts, tangents=((-1, 0), None))       # back across the curve
        with self.assertRaises(ValueError):
            s3d.spline(pts + [(0, 0)], closed=True, tangents=(None, (1, 0)))

    def test_spline_loop_is_a_smooth_closed_path(self):
        pts = [(0, 0, 40), (60, 0, 50), (60, 40, 60), (0, 40, 50)]
        rim = s3d.spline(pts, loop=True)
        self.assertTrue(rim.closed)
        for i, p in enumerate(pts):                       # through every point, z kept
            self.assertEqual(rim.points[12 * i], tuple(map(float, p)))
        q = [Vector(p) for p in rim.points]
        turns = [math.degrees((q[i] - q[i - 1]).angle(q[(i + 1) % len(q)] - q[i])) for i in range(len(q))]
        self.assertLess(max(turns), 25, "no kink where the loop closes (an open spline closed by a line: 90°)")
        ring = s3d.wire("rim", rim, d=6)
        names = {a.name for a in ring.data.attributes}
        self.assertNotIn("s3d_face:start", names, "a ring has no ends")
        self.assertEqual(len(s3d.spline([(0, 0), (10, 0), (5, 8)], loop=True).points), 36)
        with self.assertRaises(ValueError):
            s3d.spline(pts, closed=True, loop=True)
        with self.assertRaises(ValueError):
            s3d.spline(pts[:2], loop=True)
        with self.assertRaises(ValueError):
            s3d.spline(pts, loop=True, tangents=((1, 0, 0), None))

    def test_a_point_off_the_plane_is_refused_not_flattened(self):
        """Three programs whose points lost their z without a word."""
        s3d.empty_scene()
        pull = [(-100, -8, 160), (-100, 60, 160), (100, 60, 160), (100, -8, 160)]          # a cabinet's pull
        with self.assertRaisesRegex(ValueError, r"poly: the point \(-100, -8, 160\) is off the plane .*z = 160"
                                                r".*s3d\.wire\(name, points, d\)"):
            s3d.wire("pull", s3d.poly(pull), d=14)
        strut = [(0, -30, 130), (0, 100, 280), (0, 130, 550)]                             # a fighter's tail strut
        with self.assertRaisesRegex(ValueError, "poly: the point"):
            s3d.wire("tail_strut", s3d.poly(strut), d=10)
        rim = [(0, 0, 400), (100, 0, 450), (100, 100, 500), (0, 100, 450)]               # a bathtub's rim
        with self.assertRaisesRegex(ValueError, r"spline: .*z = 400.*s3d\.spline\(points, loop=True\)"):
            s3d.spline(rim, closed=True)
        z = [co.z for co in (v.co for v in s3d.wire("c", s3d.spline(rim), d=14).data.vertices)]
        self.assertAlmostEqual(min(z), 400 - 7, delta=7)           # an open spline was a path in space already
        self.assertGreater(max(z), 500)
        self.assertGreater(min(co.z for co in (v.co for v in s3d.wire("u", pull, d=14).data.vertices)), 150,
                           "the list itself is the path in space the message points to")
        # z = 0 written out is in the plane; runs leaving it are refused like points
        self.assertArea(s3d.poly([(0, 0, 0), (10, 0, 0), (10, 10, 0)]), 50, rel=1e-12)
        self.assertArea(s3d.spline([(0, 0, 0), (20, 0, 0), (10, 15, 0)], closed=True), 200, rel=0.3)
        with self.assertRaisesRegex(ValueError, "poly: the point"):
            s3d.poly([(0, 0), (30, 0), s3d.spline([(30, 0, 0), (35, 10, 4), (30, 20, 0)])])
        with self.assertRaisesRegex(ValueError, "poly: the point"):
            s3d.poly([(0, 0), s3d.arc((20, 0, 5), 10, 180, 0)])
        with self.assertRaisesRegex(ValueError, "poly: the point"):
            s3d.poly([(0, 0), (20, 0), s3d.tangent_arc((20, 20, 3))])

    def test_stroke_thickens_an_open_path(self):
        """A line drawn with a pen t wide, centred on it: square ends, mitred sharp corners."""
        bar = s3d.stroke([(0, 0), (100, 0)], 10)
        self.assertArea(bar, 1000, rel=1e-12)
        self.assertEqual(bar.bounds(), ((0.0, -5.0), (100.0, 5.0)))
        self.assertEqual(corners(bar), 4)
        sector = s3d.stroke(s3d.arc((0, 0), 50, 0, 90), 10)          # an annular sector
        self.assertArea(sector, math.pi / 4 * (55 ** 2 - 45 ** 2), rel=0.002)
        (x0, y0), (x1, y1) = sector.bounds()
        for got, want in ((x0, 0), (y0, 0), (x1, 55), (y1, 55)):
            self.assertAlmostEqual(got, want, delta=1e-9)
        self.assertEqual(corners(sector), 4, "the arc runs smooth between its square ends")
        bracket = s3d.stroke([(0, 0), (50, 0), (50, 50)], 10)       # an L: mitred, its corner sharp both sides
        self.assertArea(bracket, 10 * 100, rel=1e-12)
        self.assertEqual(corners(bracket), 6)
        self.assertEqual(bracket.bounds(), ((0.0, -5.0), (55.0, 50.0)))
        hook = s3d.stroke([(0, 0), (40, 0), s3d.tangent_arc((60, 20)), (60, 60)], 6)     # runs as poly takes them
        self.assertEqual(corners(hook), 4)
        plate = s3d.extrude("fender", s3d.stroke(s3d.arc((0, 0), 480, 180, 40), 18), 300, both=True)
        self.assertIn("s3d_edge:side", plate.data.attributes)
        with self.assertRaisesRegex(ValueError, r"stroke: the band 10 wide crosses itself .*tighter than t / 2 = 5"):
            s3d.stroke(s3d.arc((0, 0), 3, 0, 180), 10)
        with self.assertRaisesRegex(ValueError, "stroke: the band 10 wide crosses itself"):
            s3d.stroke([(0, 0), (100, 0), (50, 50), (50, -50)], 10)
        with self.assertRaisesRegex(ValueError, r"stroke: the path is closed .*s3d\.offset\(p, t\)"):
            s3d.stroke(s3d.circle(20), 2)
        with self.assertRaisesRegex(ValueError, r"stroke: the path ends where it starts"):
            s3d.stroke([(0, 0), (10, 0), (10, 10), (0, 0)], 2)
        with self.assertRaisesRegex(ValueError, "stroke: the point"):
            s3d.stroke([(0, 0, 0), (10, 0, 5)], 2)

    def test_wrap_is_the_convex_outline_round_profiles(self):
        """The outline a belt makes round its wheels."""
        def polygon_area(d):          # a circle is a polygon: what a disc of it covers
            n = len(s3d.circle(d).loops[0].pts)
            return n / 2 * math.sin(2 * math.pi / n) * d * d / 4
        pair = s3d.wrap(s3d.at(s3d.circle(40), x=-50), s3d.at(s3d.circle(40), x=50))      # a stadium
        self.assertArea(pair, 100 * 40 + polygon_area(40), rel=1e-3)
        self.assertEqual(corners(pair), 0)
        self.assertEqual(len(pair.loops), 1)
        (cx0, _), (cx1, _) = s3d.circle(40).bounds()
        (x0, y0), (x1, y1) = pair.bounds()
        self.assertAlmostEqual(x0, cx0 - 50, delta=1e-4)          # the wheels' own extremes
        self.assertAlmostEqual(x1, cx1 + 50, delta=1e-4)
        r, a, b, c = 15, (0, 0), (120, 0), (40, 70)                           # three wheels
        tri = abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) / 2
        perimeter = sum(math.dist(p, q) for p, q in ((a, b), (b, c), (c, a)))
        three = s3d.wrap([s3d.at(s3d.circle(2 * r), x=x, y=y) for x, y in (a, b, c)])     # a list is its elements
        self.assertArea(three, tri + perimeter * r + polygon_area(2 * r), rel=2e-3)
        self.assertEqual(corners(three), 0)
        horn = s3d.wrap(s3d.at(s3d.circle(40), x=-50), s3d.at(s3d.circle(40), x=50), (0, 80))   # a point keeps its corner
        self.assertEqual(corners(horn), 1)
        self.assertIn((0.0, 80.0), horn.loops[0].pts)
        inner = s3d.wrap(s3d.circle(100), s3d.at(s3d.circle(20), x=10))             # inside: it adds nothing
        self.assertEqual(sorted(inner.loops[0].pts), sorted(s3d.circle(100).loops[0].pts))
        belt = s3d.offset(three, 6) - three
        self.assertEqual(len(belt.loops), 2)
        self.assertArea(s3d.wrap(s3d.rect(40, 20), (0, 30)), 800 + 40 * 20 / 2, rel=1e-12)
        with self.assertRaisesRegex(ValueError, "wrap: the profiles and points given lie in a line"):
            s3d.wrap((0, 0), (10, 0), (20, 0))
        with self.assertRaisesRegex(ValueError, "wrap: the point"):
            s3d.wrap(s3d.circle(10), (0, 30, 5))

    def test_spline_and_text(self):
        self.assertEqual(corners(s3d.spline([(0, 0), (20, 5), (30, 20), (10, 30), (-5, 15)], closed=True)), 0)
        path = s3d.spline([(0, 0, 0), (10, 5, 3), (20, 0, 6)])
        self.assertEqual(path.points[0], (0.0, 0.0, 0.0))
        self.assertEqual(path.points[-1], (20.0, 0.0, 6.0))
        letters = s3d.text("A8", 10)
        self.assertEqual(len(letters.loops), 5, "A: outline and counter; 8: outline and two counters")


if __name__ == "__main__":
    unittest.main()
