"""Frames: faces give the planes CAD sketches on; `at` and the distributors put things there."""
import math
import unittest

import sand3d as s3d
from test_solids import closed_volume


def close(a, b, tol=1e-5):
    return all(abs(x - y) < tol for x, y in zip(a, b))


class Frames(unittest.TestCase):

    def setUp(self):
        s3d.empty_scene()

    def test_edge_is_a_named_edge_as_a_path(self):
        """Ob.edge, as ob.face — a named edge's geometry, for wire, sweep and along."""
        import bmesh
        box = s3d.box("box", 40, 20, 10)
        top = box.edge("top")
        self.assertTrue(top.closed)
        self.assertEqual(top.points, [(20.0, 10.0, 10.0), (-20.0, 10.0, 10.0), (-20.0, -10.0, 10.0), (20.0, -10.0, 10.0)],
                         "a closed run anticlockwise seen from +Z, from where it crosses its +X")
        side = box.edge("side")                                  # four runs as long: one answer, open, toward +Z
        self.assertFalse(side.closed)
        self.assertEqual(side.points, [(-20.0, -10.0, 0.0), (-20.0, -10.0, 10.0)])
        placed = s3d.at(s3d.box("placed", 40, 20, 10), x=100, rx=90)    # in the space the box is in, as face
        self.assertTrue(all(abs(p[1] + 10) < 1e-5 and 79.99 < p[0] < 120.01 for p in placed.edge("top").points))   # rx=90: +Z to -Y
        # a cylinder cut by a box: the loop the cut left, in 3D, on the cylinder's wall
        cyl = s3d.cylinder("cyl", 40, 60)
        s3d.cut(cyl, s3d.at(s3d.box("notch", 20, 20, 20), x=20, z=20))
        notch = cyl.edge("notch")
        self.assertTrue(notch.closed)
        self.assertGreater(len(notch.points), 8)
        for x, y, z in notch.points:
            self.assertLess(abs(math.hypot(x, y) - 20), 0.05)
            self.assertTrue(20 - 1e-4 <= z <= 40 + 1e-4)
        self.assertTrue(closed_volume(s3d.wire("bead", notch, 2))[0])
        self.assertTrue(closed_volume(s3d.sweep("trim", s3d.rect(2, 3), box.edge("top")))[0])
        self.assertEqual(len(s3d.along(top, count=12)), 12)
        # a name that forks is refused: a path follows a line
        fork = s3d.box("fork", 40, 20, 10)
        bm = bmesh.new()
        bm.from_mesh(fork.data)
        layer = bm.edges.layers.bool["s3d_edge:top"]
        next(e for e in bm.edges if {round(v.co.z, 3) for v in e.verts} == {0.0, 10.0})[layer] = True
        bm.to_mesh(fork.data)
        bm.free()
        with self.assertRaisesRegex(ValueError, r"fork: the edges named 'top' fork at 1 point\(s\)"):
            fork.edge("top")
        with self.assertRaisesRegex(ValueError, r"box has no edge named \['rim'\]"):
            box.edge("rim")

    def test_face_by_name_and_direction(self):
        plate = s3d.extrude("plate", s3d.rect(60, 40), 8)
        top = plate.face("top")
        self.assertTrue(close(top.origin, (0, 0, 8)) and close(top.normal, (0, 0, 1)))
        self.assertTrue(close(top.x, (1, 0, 0)))
        front = plate.face("-Y")
        self.assertTrue(close(front.origin, (0, -20, 0)) and close(front.x, (1, 0, 0)) and close(front.y, (0, 0, 1)))
        self.assertTrue(close(plate.face("+X").x, (0, 1, 0)), "CadQuery's rule: X is Z × normal")
        self.assertRaises(ValueError, plate.face, "rim")

    def test_sketch_on_a_face(self):
        plate = s3d.extrude("plate", s3d.rect(60, 40), 8)
        boss = s3d.extrude("boss", s3d.circle(20), 10, on=plate.face("top").move(10, 5))
        s3d.join(plate, boss)
        self.assertAlmostEqual(closed_volume(plate)[1], 60 * 40 * 8 + math.pi * 100 * 10, delta=40)
        self.assertTrue(close(plate.face("top").origin, (0, 0, 8)), "the plate's top is still the largest")
        self.assertTrue(close(plate.face("boss.top").origin, (0, 0, 18)))
        self.assertTrue(close(plate.face("+Z").origin, (0, 0, 18)), "furthest along +Z: the boss")

    def test_face_of_a_placed_part(self):
        bar = s3d.at(s3d.box("bar", 10, 10, 40), x=100, rx=90)
        end = bar.face("top")
        self.assertTrue(close(end.normal, (0, -1, 0)), "the box's top looks along -Y once turned")
        self.assertTrue(close(end.origin, (0, -40, 0)), "40 up from its base, at the origin")

    def test_at_anchor_and_mirror(self):
        b = s3d.at(s3d.box("b", 10, 20, 30), z=5, anchor="bottom-left-front")
        self.assertTrue(close(b.matrix_basis.to_translation(), (5, 10, 5)))
        m = s3d.transform(s3d.extrude("w", s3d.poly([(0, 0), (10, 0), (0, 5)]), 1), mirror="x")
        xs = [(m.matrix_basis @ v.co).x for v in m.data.vertices]
        self.assertAlmostEqual(min(xs), -10)
        plate = s3d.box("plate", 60, 40, 8)
        peg = s3d.at(s3d.cylinder("peg", 4, 10), on=plate.face("top"), anchor="bottom", x=5)
        self.assertTrue(close(peg.matrix_basis @ s3d.Frame().origin, (5, 0, 8)))

    def test_grid_and_ring(self):
        g = s3d.grid(3, 2, 10, 20)
        self.assertEqual(len(g), 6)
        self.assertTrue(close(g[0].origin, (-10, -10, 0)) and close(g[-1].origin, (10, 10, 0)))
        r = s3d.ring(4, 10, start=45)
        self.assertTrue(close(r[0].origin, (10 / math.sqrt(2), 10 / math.sqrt(2), 0)))
        self.assertTrue(close(r[1].x, (-1 / math.sqrt(2), 1 / math.sqrt(2), 0)), "X points outward")
        arc = s3d.ring(3, 10, angle=90)
        self.assertTrue(close(arc[-1].origin, (0, 10, 0)))
        plate = s3d.box("plate", 100, 60, 10)
        s3d.hole(plate, 5, on=s3d.grid(3, 2, 30, 30, on=plate.face("top")))
        self.assertAlmostEqual(closed_volume(plate)[1], 60000 - 6 * math.pi * 6.25 * 10, delta=60)

    def test_along_and_snap(self):
        f = s3d.along([(0, 0, 0), (100, 0, 0)], pitch=25)
        self.assertEqual(len(f), 5)
        self.assertTrue(close(f[2].origin, (50, 0, 0)) and close(f[2].normal, (1, 0, 0)))
        self.assertEqual(len(s3d.along(s3d.circle(40), count=8)), 8)
        body = s3d.at(s3d.box("body", 100, 50, 50), z=75)
        hits = s3d.snap(body, [(0, -100, 100), (0, 0, 300)], direction=(0, 1, 0))
        self.assertEqual(len(hits), 1, "a line that misses is dropped")
        self.assertTrue(close(hits[0].origin, (0, -25, 100)) and close(hits[0].normal, (0, -1, 0)))
        near = s3d.snap(body, [(0, 0, 200)])
        self.assertTrue(close(near[0].origin, (0, 0, 125)) and close(near[0].normal, (0, 0, 1)))
        inside = s3d.snap(body, [(0, 0, 110)])
        self.assertTrue(close(inside[0].origin, (0, 0, 125)) and close(inside[0].normal, (0, 0, 1)),
                        "from inside, the normal still points out of the solid")
        through = s3d.snap(body, [(0, 0, 75)], direction=(0, 1, 0))
        self.assertTrue(close(through[0].origin, (0, 25, 75)) and close(through[0].normal, (0, 1, 0)),
                        "a line from inside meets the far wall, its normal out of the solid")

    def test_snap_takes_named_axes(self):
        body = s3d.at(s3d.box("body", 100, 50, 50), z=75)
        down = s3d.snap(body, [(0, 0, 300)], direction="-Z")
        self.assertTrue(close(down[0].origin, (0, 0, 125)) and close(down[0].normal, (0, 0, 1)))
        for name, vector in (("+Y", (0, 1, 0)), ("Y", (0, 1, 0)), ("-x", (-1, 0, 0))):
            with self.subTest(name=name):
                start = [(0, -100, 100)] if "Y" in name else [(200, 0, 75)]
                self.assertEqual([tuple(f.origin) for f in s3d.snap(body, start, direction=name)],
                                 [tuple(f.origin) for f in s3d.snap(body, start, direction=vector)])
        for bad in ("down", "-W", (0, 0, 0), (0, "a", 1), 3):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "snap: direction is"):
                s3d.snap(body, [(0, 0, 300)], direction=bad)


if __name__ == "__main__":
    unittest.main()
