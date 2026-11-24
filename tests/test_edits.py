"""Edits: booleans stay closed and right in volume; what they create is named."""
import math
import unittest

import bpy

import sand3d as s3d
from test_solids import closed_volume, edges, faces, length


class Edits(unittest.TestCase):

    def setUp(self):
        s3d.empty_scene()

    def assertSolid(self, ob, volume, rel=0.02):
        closed, v = closed_volume(ob)
        self.assertTrue(closed, f"{ob.name} is not closed")
        self.assertAlmostEqual(v, volume, delta=abs(volume) * rel, msg=ob.name)

    def test_cut_join_intersect(self):
        plate = s3d.box("plate", 60, 40, 8)
        s3d.cut(plate, s3d.at(s3d.cylinder("pin", 10, 20), x=10, z=-6))
        self.assertSolid(plate, 60 * 40 * 8 - math.pi * 25 * 8)
        self.assertEqual(edges(plate, "pin"), edges(plate, "cut"), "the mouth edges carry the tool's name")
        self.assertGreater(faces(plate, "cut"), 0)
        self.assertGreaterEqual(faces(plate, "plate.top"), 1, "a face with a hole is cut in pieces")
        self.assertNotIn("pin", [o.name for o in bpy.data.objects], "tools are used up")
        s3d.join(plate, s3d.at(s3d.box("boss", 10, 10, 10), x=-10, z=7))
        self.assertSolid(plate, 60 * 40 * 8 - math.pi * 25 * 8 + 900, rel=0.005)
        self.assertAlmostEqual(length(plate, "boss"), 40, places=4, msg="the boss meets the top in a 10 mm square")
        self.assertSolid(s3d.intersect(s3d.box("c", 30, 30, 30), s3d.at(s3d.box("d", 30, 30, 30), x=15)), 13500, 1e-9)

    def test_a_cut_with_many_tools_is_one_boolean(self):
        plate = s3d.box("p", 100, 20, 5)
        s3d.cut(plate, *[s3d.at(s3d.box("slot", 4, 30, 10), x=x) for x in range(-40, 41, 10)])
        self.assertSolid(plate, 100 * 20 * 5 - 9 * 4 * 20 * 5, rel=1e-9)

    def test_a_pattern_is_the_tool_once_per_frame(self):
        """`at(tool, on=[frames])` builds what a comprehension over frames
        builds: the tool placed on each frame, its own placement kept relative to it, in
        one boolean."""
        a = s3d.cylinder("a", 80, 6)
        s3d.cut(a, s3d.at(s3d.at(s3d.box("slot", 12, 3, 10), x=25, z=-2), on=s3d.ring(12, 0)))
        b = s3d.at(s3d.cylinder("b", 80, 6), x=200)
        s3d.cut(b, *[s3d.at(s3d.box("slot", 12, 3, 10), x=25, z=-2, on=f)
                     for f in s3d.ring(12, 0, on=s3d.Frame((200, 0, 0)))])
        self.assertSolid(a, math.pi * 40 ** 2 * 6 - 12 * 12 * 3 * 6, rel=0.01)   # a tessellated disc
        self.assertAlmostEqual(closed_volume(a)[1], closed_volume(b)[1], places=6)
        self.assertEqual(edges(a, "slot"), edges(b, "slot"))
        self.assertNotIn("slot", [o.name for o in bpy.data.objects], "tool and copies are used up")
        plate = s3d.box("plate", 60, 40, 4)
        s3d.join(plate, s3d.at(s3d.at(s3d.box("rib", 2, 30, 6), z=4), on=s3d.grid(4, 1, 12, 0)))
        self.assertSolid(plate, 60 * 40 * 4 + 4 * 2 * 30 * 6, rel=1e-6)
        one = s3d.box("one", 20, 20, 4)
        s3d.cut(one, s3d.at(s3d.cylinder("pin", 4, 10), on=s3d.Frame((5, 0, -3))))   # a single frame
        self.assertSolid(one, 20 * 20 * 4 - math.pi * 4 * 4, rel=0.02)

    def test_flat_names_are_dropped(self):
        a = s3d.box("a", 10, 10, 10)
        s3d.join(a, s3d.at(s3d.box("b", 10, 10, 10), x=10))
        self.assertSolid(a, 2000, rel=1e-9)
        self.assertAlmostEqual(length(a, "top"), 60, places=4, msg="the seam across the joined tops is no edge")

    def test_split(self):
        above, below = s3d.split(s3d.box("b", 20, 20, 20), s3d.Frame((0, 0, 14)), keep="both")
        self.assertSolid(above, 20 * 20 * 6, rel=1e-9)
        self.assertSolid(below, 20 * 20 * 14, rel=1e-9)
        self.assertEqual(faces(above, "cut"), 1)

    def test_holes(self):
        plate = s3d.box("plate", 80, 50, 10)
        s3d.hole(plate, 6, on=[(-30, -15), (30, 15)])
        self.assertSolid(plate, 40000 - 2 * math.pi * 9 * 10)
        self.assertEqual(edges(plate, "hole") % 2, 0)
        blind = s3d.box("blind", 40, 40, 20)
        s3d.hole(blind, 10, on=(0, 0), depth=8)
        self.assertSolid(blind, 32000 - math.pi * 25 * 8)
        bored = s3d.box("bored", 40, 40, 20)
        s3d.hole(bored, 6, on=(0, 0), cbore=(12, 5))
        self.assertSolid(bored, 32000 - math.pi * (36 * 5 + 9 * 15))
        sunk = s3d.box("sunk", 40, 40, 20)
        s3d.hole(sunk, 6, on=(0, 0), csk=(12, 90))
        cone = math.pi * 3 / 3 * (36 + 9 + 18)
        self.assertSolid(sunk, 32000 - cone - math.pi * 9 * 17)

    def test_pocket(self):
        plate = s3d.box("plate", 80, 50, 10)
        s3d.pocket(plate, s3d.rect(20, 10), depth=3)
        self.assertSolid(plate, 40000 - 600, rel=1e-9)
        self.assertEqual(faces(plate, "pocket.bottom"), 1)
        self.assertEqual(edges(plate, "pocket.side"), 4)
        s3d.pocket(plate, s3d.circle(8))
        self.assertSolid(plate, 40000 - 600 - math.pi * 16 * 7)

    def test_merge_and_scale(self):
        m = s3d.merge(s3d.box("m", 10, 10, 10), s3d.at(s3d.box("n", 10, 10, 10), x=20, rz=45))
        self.assertSolid(m, 2000, rel=1e-6)
        self.assertEqual(edges(m, "n.top"), 4)
        self.assertSolid(s3d.scale(s3d.box("s", 10, 10, 10), (2, 1, -1)), 2000, rel=1e-9)

    def test_a_dent_lands_where_snap_found_the_surface(self):
        for x, rz in ((0, 0), (1000, 30)):
            ball = s3d.at(s3d.sphere(f"ball{x}", 20), x=x, rz=rz)
            top = s3d.snap(ball, [(x, 0, 30)], direction=(0, 0, -1))[0]
            s3d.dent(ball, [top], r=4, depth=2, coords="parent")
            after = s3d.snap(ball, [(x, 0, 30)], direction=(0, 0, -1))[0]
            self.assertAlmostEqual(after.origin.z, top.origin.z - 2, delta=.05,
                                   msg=f"placed at x={x}, the hollow is where the frame was")

    def test_dent_defaults_to_mesh_local_after_placement(self):
        for placement in ({}, dict(x=100), dict(x=100, y=30, rx=20, ry=40, rz=30)):
            for coords in ({}, dict(coords="local")):
                pad = s3d.at(s3d.box("pad", 20, 20, 10), **placement)
                s3d.dent(pad, [(0, 0, 10)], r=5, depth=1, **coords)
                self.assertEqual(len(pad.data.vertices), 81)
                self.assertAlmostEqual(min(v.co.z for v in pad.data.vertices if abs(v.co.x) < .01
                                           and abs(v.co.y) < .01), 9)
                if not placement and not coords:
                    reference = [tuple(v.co) for v in pad.data.vertices]
                self.assertEqual([tuple(v.co) for v in pad.data.vertices], reference)

    def test_dent_parent_matches_local_on_rotated_part(self):
        from mathutils import Vector
        local = s3d.box("local", 20, 20, 10)
        placed = s3d.at(s3d.box("placed", 20, 20, 10), x=100, y=30, rx=20, ry=40, rz=30)
        s3d.dent(local, [(0, 0, 10)], r=5, depth=1)
        point = placed.matrix_basis @ Vector((0, 0, 10))
        s3d.dent(placed, [point], r=5, depth=1, coords="parent")
        self.assertEqual(len(placed.data.vertices), len(local.data.vertices))
        for a, b in zip(local.data.vertices, placed.data.vertices):
            self.assertLess((a.co - b.co).length, 1e-4)
        with self.assertRaisesRegex(ValueError, 'coords'):
            s3d.dent(placed, [], r=5, depth=1, coords="world")

    def test_delete(self):
        s3d.delete(s3d.box("gone", 5, 5, 5))
        self.assertNotIn("gone", bpy.data.objects)


if __name__ == "__main__":
    unittest.main()
