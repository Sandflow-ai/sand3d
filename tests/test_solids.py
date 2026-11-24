"""Solids: closed, the right volume, their edges named where the profile turns."""
import math
import unittest

import bpy  # noqa: F401 — before bmesh, which bpy provides
import bmesh

import sand3d as s3d
from sand3d.edit import strict


def closed_volume(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    closed = all(e.is_manifold for e in bm.edges) and all(len(e.link_faces) == 2 for e in bm.edges)
    volume = bm.calc_volume(signed=True)
    bm.free()
    return closed, volume


def edges(ob, tag):
    att = ob.data.attributes.get("s3d_edge:" + tag)
    return 0 if att is None else sum(d.value for d in att.data)


def length(ob, tag):
    att = ob.data.attributes.get("s3d_edge:" + tag)
    if att is None:
        return 0.0
    vs = ob.data.vertices
    return sum((vs[e.vertices[0]].co - vs[e.vertices[1]].co).length
               for e, d in zip(ob.data.edges, att.data) if d.value)


def faces(ob, tag):
    att = ob.data.attributes.get("s3d_face:" + tag)
    return 0 if att is None else sum(d.value for d in att.data)


class Solids(unittest.TestCase):

    def setUp(self):
        s3d.empty_scene()

    def assertSolid(self, ob, volume, rel=0.02):
        closed, v = closed_volume(ob)
        self.assertTrue(closed, f"{ob.name} is not closed")
        self.assertAlmostEqual(v, volume, delta=abs(volume) * rel, msg=ob.name)

    def test_wire_does_not_override_the_callers_path(self):
        points = [(0, 0, 0), (5, 0, 1), (10, 6, 2)]
        path = s3d.spline(points)
        before = [tuple(frame.origin) for frame in s3d.along(path, count=5)]
        s3d.wire('fil', path, (.1, .15), closed=True)
        self.assertFalse(path.closed)
        self.assertEqual([tuple(frame.origin) for frame in s3d.along(path, count=5)], before)

        straight = s3d.spline([(0, 0, 0), (0, 0, 10)])
        s3d.wire('sampled', straight, (.1, .15), rings=[.2, .6])
        self.assertFalse(hasattr(straight, '_at_length'))
        self.assertFalse(hasattr(straight, '_lengths'))

    def test_extrude_names_caps_walls_and_corners(self):
        ob = s3d.extrude("plate", s3d.rect(80, 40), 6)
        self.assertSolid(ob, 80 * 40 * 6, rel=1e-9)
        self.assertEqual((edges(ob, "top"), edges(ob, "bottom"), edges(ob, "side")), (4, 4, 4))
        self.assertEqual((faces(ob, "top"), faces(ob, "plate.top")), (1, 1))
        round_ = s3d.extrude("round", s3d.rect(80, 40, r=4), 6)
        self.assertEqual(edges(round_, "side"), 0, "rounded corners make no side edge")

    def test_extrude_options(self):
        self.assertSolid(s3d.extrude("h", s3d.circle(30) - s3d.circle(10), 5), math.pi * 200 * 5)
        top = (40 - 2 * 20 * math.tan(math.radians(10))) ** 2
        self.assertSolid(s3d.extrude("t", s3d.rect(40, 40), 20, taper=10), 20 / 3 * (1600 + top + 40 * math.sqrt(top)))
        self.assertSolid(s3d.extrude("tw", s3d.rect(40, 20), 50, twist=90), 40 * 20 * 50, rel=0.01)
        both = s3d.extrude("b", s3d.rect(10, 10), 10, both=True)
        self.assertEqual(min(v.co.z for v in both.data.vertices), -5)
        two = s3d.extrude("d", s3d.rect(10, 10), 10, h2=4)
        self.assertSolid(two, 1400, rel=1e-9)

    def test_revolve_rims_and_caps(self):
        cup = s3d.revolve("cup", [(0, 0), (20, 0), (24, 40), (22, 40), (18, 3), (0, 3)])
        self.assertTrue(closed_volume(cup)[0])
        self.assertGreater(edges(cup, "rim"), 0)
        half = s3d.revolve("half", s3d.at(s3d.rect(10, 20), x=10), 180)
        self.assertSolid(half, math.pi * (15 ** 2 - 5 ** 2) * 20 / 2)
        self.assertEqual(faces(half, "start"), 1)
        self.assertRaises(ValueError, s3d.revolve, "bad", s3d.rect(10, 10))

    def test_sweeps(self):
        self.assertSolid(s3d.sweep("bar", s3d.rect(10, 4), [(0, 0, 0), (0, 0, 50), (50, 0, 50)]), 40 * 100, rel=1e-6)
        ring = s3d.sweep("ring", s3d.rect(4, 4), s3d.circle(60))
        self.assertSolid(ring, 16 * math.pi * 60)
        self.assertEqual(faces(ring, "start"), 0, "a closed path has no ends")
        self.assertSolid(s3d.wire("w", [(0, 0, 0), (0, 0, 100)], 10), math.pi * 25 * 100)

    def test_wire_rounds_the_corners_of_a_path_of_points(self):
        """A tube bent to radius r at each corner, as poly's fillet rounds an outline's."""
        from mathutils import Vector
        from sand3d.solids import _filleted
        d, r, up, reach = 33, 60, 650, 250
        leg = [(0, 0, 0), (0, 0, up), (-reach, 0, up)]
        bend = [Vector(q) for q in _filleted(leg, False, r)]
        centre = Vector((-r, 0, up - r))
        arc = [q for q in bend if up - r - 1e-6 <= q.z and q.x >= -r - 1e-6 and q not in (Vector(leg[1]),)]
        self.assertGreater(len(arc), 8)
        for q in arc:
            self.assertAlmostEqual((q - centre).length, r, delta=1e-4)    # a quarter torus round the corner
        def section(d):           # the wire's circle is a polygon: its area, by Pappus along the line
            n = len(s3d.circle(d).loops[0].pts)
            return n / 2 * math.sin(2 * math.pi / n) * d * d / 4
        line = (up - r) + math.pi / 2 * r + (reach - r)
        self.assertSolid(s3d.wire("leg", leg, d, fillet=r), section(d) * line, rel=0.003)
        # one value per point, 0 leaving it, as poly; 0 everywhere is the plain wire, to the bit
        def mesh(ob):
            return [tuple(v.co) for v in ob.data.vertices], [tuple(q.vertices) for q in ob.data.polygons]
        self.assertEqual(mesh(s3d.wire("a", leg, d, fillet=[0, r, 0])), mesh(s3d.wire("b", leg, d, fillet=r)))
        self.assertEqual(mesh(s3d.wire("c", leg, d, fillet=0)), mesh(s3d.wire("e", leg, d)))
        hoop = [(0, 0, 0), (200, 0, 0), (200, 100, 0), (0, 100, 0)]
        self.assertSolid(s3d.wire("hoop", hoop, 10, closed=True, fillet=20),
                         section(10) * (2 * (200 + 100) - 8 * 20 + 2 * math.pi * 20), rel=0.003)
        # too large for a side, in strict mode: said, as poly says it (test_clamped_radius: clamped otherwise)
        with strict(), self.assertRaisesRegex(ValueError, r"wire: fillet too large for the side from "
                                                          r"\(0.0, 0.0, 650.0\) to \(-30.0, 0.0, 650.0\) \(60 > 30\)"):
            s3d.wire("short", [(0, 0, 0), (0, 0, up), (-30, 0, up)], d, fillet=r)
        with self.assertRaisesRegex(ValueError, "wire: fillet rounds the corners of a path given as points"):
            s3d.wire("curve", s3d.spline([(0, 0, 0), (0, 0, 100), (50, 0, 150)]), d, fillet=10)

    def test_wire_fillet_refuses_a_bend_it_cannot_make(self):
        """A path that turns back made a wire 114 km long (float32 put the turn past
        180°, the setback came out negative and passed the size check); a radius under d / 2 built
        a tube folded on itself; a point written twice lost its corner; a list of radii of the
        wrong length was padded with 0."""
        def mesh(ob):
            return [tuple(v.co) for v in ob.data.vertices], [tuple(q.vertices) for q in ob.data.polygons]
        for back in ([(0, 0, 0), (0, 0, 100), (0, 0.001, 0)], [(0, 0, 0), (0, 0, 100), (0, 0, 50)]):
            with self.subTest(back=back):
                with self.assertRaisesRegex(ValueError, r"wire: the path turns back on itself at \(0, 0, 100\)"):
                    s3d.wire("w", back, 10, fillet=5)
        leg = [(0, 0, 0), (0, 0, 100), (100, 0, 100)]
        with self.assertRaisesRegex(ValueError, r"wire: fillet 5 at \(0, 0, 100\) is tighter than the wire's radius "
                                                r"20 \(d / 2\): a tube bent tighter than its radius folds on itself"):
            s3d.wire("w", leg, 40, fillet=5)
        self.assertTrue(closed_volume(s3d.wire("w", leg, 40, fillet=20))[0])         # d / 2 itself bends
        with self.assertRaisesRegex(ValueError, r"wire: fillet gives 2 radii for 4 points — one per point"):
            s3d.wire("w", [(0, 0, 0), (0, 0, 100), (100, 0, 100), (100, 0, 0)], 10, fillet=[0, 20])
        with self.assertRaisesRegex(ValueError, r"wire: fillet gives 4 radii for 3 points"):
            s3d.wire("w", leg, 10, fillet=[0, 20, 0, 0])
        # a point written twice is one point, its corner rounded
        s3d.empty_scene()
        once = mesh(s3d.wire("a", leg, 10, fillet=20))
        s3d.empty_scene()
        self.assertEqual(mesh(s3d.wire("a", [(0, 0, 0), (0, 0, 100), (0, 0, 100), (100, 0, 100)], 10, fillet=20)), once)
        s3d.empty_scene()
        self.assertEqual(mesh(s3d.wire("a", [(0, 0, 0), (0, 0, 100), (0, 0, 100), (100, 0, 100)], 10,
                                       fillet=[0, 20, 0, 0])), once)

    def test_body_is_the_solid_its_views_draw(self):
        """A plan width, a side's top and bottom lines, superellipse sections along Y."""
        def area(ob, tag):
            att = ob.data.attributes.get("s3d_face:" + tag)
            return sum(q.area for q, v in zip(ob.data.polygons, att.data) if v.value) if att else 0
        prism = s3d.body("prism", [(0, 40), (100, 40)], 30, 0, n=4)          # constant views: a prism
        self.assertSolid(prism, s3d.superellipse(40, 30, n=4).area() * 100, rel=1e-6)   # a mesh is single precision
        co = [v.co for v in prism.data.vertices]
        for k, lo, hi in ((0, -20, 20), (1, 0, 100), (2, 0, 30)):
            self.assertAlmostEqual(min(c[k] for c in co), lo, delta=1e-4)
            self.assertAlmostEqual(max(c[k] for c in co), hi, delta=1e-4)
        self.assertEqual({round(c.y, 6) for c in co}, {0.0, 100.0}, "straight views: a section at each point")
        self.assertTrue(closed_volume(s3d.fillet(prism, 3, edges="start"))[0])     # its faces go by name
        self.assertTrue(closed_volume(s3d.shell(s3d.body("cup", [(0, 40), (80, 40)], 30, 0), 2, open="end"))[0])
        # an end where both views close is a point; each point a list gives is a section
        nose = s3d.body("nose", [(0, 0), (37.3, 40), (100, 40)], [(0, 15), (37.3, 30), (100, 30)],
                        [(0, 15), (37.3, 0), (100, 0)])
        self.assertTrue(closed_volume(nose)[0])
        self.assertEqual(sum(1 for c in (v.co for v in nose.data.vertices) if c.y == 0), 1)
        self.assertEqual(area(nose, "start"), 0)
        self.assertEqual({round(v.co.y, 3) for v in nose.data.vertices}, {0.0, 37.3, 100.0})
        # n along the length: round at the start, boxy at the end
        morph = s3d.body("morph", [(0, 40), (100, 40)], 30, 0, n=[(0, 2), (100, 6)])
        self.assertAlmostEqual(area(morph, "start"), s3d.superellipse(40, 30, n=2).area(), delta=1e-3)
        self.assertAlmostEqual(area(morph, "end"), s3d.superellipse(40, 30, n=6).area(), delta=1e-3)
        # a fuselage of three splines
        fuselage = s3d.body("fuselage", s3d.spline([(-3500, 0), (-2500, 1000), (0, 1400), (3000, 900), (4500, 400)]),
                            s3d.spline([(-3500, 900), (-2500, 1400), (0, 1600), (3000, 1300), (4500, 1100)]),
                            s3d.spline([(-3500, 900), (-2500, 500), (0, 300), (3000, 600), (4500, 850)]))
        self.assertTrue(closed_volume(fuselage)[0])
        self.assertEqual(area(fuselage, "start"), 0)
        self.assertGreater(area(fuselage, "end"), 0)
        for bad, said in ((lambda: s3d.body("b", [(0, 10), (100, 10)], 5, 10), "top line .* is under the bottom"),
                          (lambda: s3d.body("b", [(0, 10), (100, 10)], [(0, 20), (50, 20)], 0), "each view covers"),
                          (lambda: s3d.body("b", [(0, 0), (100, 10)], 20, 0), "plan closes but the side view is 20"),
                          (lambda: s3d.body("b", [(0, 10), (50, 10), (40, 10), (100, 10)], 20, 0), "never back"),
                          (lambda: s3d.body("b", 10, 20, 0), "it says where the body starts and ends"),
                          (lambda: s3d.body("b", [(0, 10), (100, 10)], 20, 0, n=0), "n is a squareness")):
            with self.assertRaisesRegex(ValueError, said):
                bad()

    def test_body_builds_a_step_and_reads_a_spline_as_drawn(self):
        """Two points at one y (a windscreen's foot) became a ramp from the point before,
        the shoulder gone; a spline through points that go one way, overshooting back near a round nose,
        raised "never back"."""
        def tops(ob):
            out = {}
            for v in ob.data.vertices:
                y = round(v.co.y, 3)
                out[y] = max(out.get(y, -math.inf), round(v.co.z, 3))
            return out
        cabin = s3d.body("cabin", [(0, 600), (2000, 600)], [(0, 900), (1000, 1000), (1000, 1300), (2000, 1300)], 0, n=3)
        self.assertTrue(closed_volume(cabin)[0])
        got = tops(cabin)
        self.assertEqual(got[1000.0], 1000, "the shoulder's foot, where the line before it ends")
        self.assertEqual(got[1000.05], 1300, "its top, a hair further")
        self.assertEqual(got[0.0], 900)
        self.assertEqual(got[2000.0], 1300)
        # a step at an end is the end's own section: a flat cap, as wide as the body goes on
        def area(ob, tag):
            att = ob.data.attributes.get("s3d_face:" + tag)
            return sum(q.area for q, v in zip(ob.data.polygons, att.data) if v.value) if att else 0
        flat = s3d.body("flat", [(0, 0), (0, 600), (2000, 600), (2000, 0)], 600, 0)
        for cap in ("start", "end"):
            self.assertAlmostEqual(area(flat, cap), s3d.superellipse(600, 600).area(), delta=1)
        # a round nose: a spline of points going one way overshoots back 21 mm before its first point
        nose = s3d.body("nose", s3d.spline([(0, 0), (10, 300), (1000, 400)]), s3d.spline([(0, 200), (10, 350), (1000, 400)]),
                        s3d.spline([(0, 200), (10, 50), (1000, 0)]))
        self.assertTrue(closed_volume(nose)[0])
        self.assertAlmostEqual(min(v.co.y for v in nose.data.vertices), 0, delta=1e-6, msg="it starts where drawn")
        self.assertTrue(closed_volume(s3d.body("blunt", s3d.spline([(0, 40), (5, 400), (400, 500)]), 300, 0))[0])
        with self.assertRaisesRegex(ValueError, r"body: plan's spline turns back along y by 1000"):
            s3d.body("back", s3d.spline([(0, 0), (1000, 100), (0, 200)]), 300, 0)

    def test_lofts(self):
        self.assertSolid(s3d.loft("f", s3d.rect(40, 40), s3d.at(s3d.rect(20, 20), z=30)),
                         30 / 3 * (1600 + 400 + 800), rel=1e-6)
        vase = s3d.loft("v", s3d.circle(40), s3d.at(s3d.circle(60), z=50), s3d.at(s3d.circle(30), z=100))
        self.assertTrue(closed_volume(vase)[0])
        self.assertEqual(edges(vase, "seam"), 0)

    def test_primitives(self):
        self.assertSolid(s3d.box("b", 40, 30, 20), 24000, rel=1e-9)
        self.assertSolid(s3d.cylinder("c", 20, 30), math.pi * 100 * 30)
        self.assertSolid(s3d.tube("t", 30, 20, 10), math.pi * (225 - 100) * 10)
        self.assertSolid(s3d.cone("k", 30, 40), math.pi * 225 * 40 / 3)
        self.assertSolid(s3d.sphere("s", 30), 4 / 3 * math.pi * 15 ** 3)
        self.assertSolid(s3d.wedge("w", 40, 20, 30, 10), 15000, rel=1e-9)
        self.assertSolid(s3d.torus("r", 40, 6), 2 * math.pi ** 2 * 20 * 9, rel=0.03)
        self.assertSolid(s3d.dome("d", 15, 3), math.pi * 3 * (3 * 7.5 ** 2 + 9) / 6, rel=0.05)


if __name__ == "__main__":
    unittest.main()
