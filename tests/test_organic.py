"""Organic edits: `blend` fills creases to a radius, `displace` pushes a surface by noise."""
import math
import time
import unittest
from unittest import mock

import bpy  # noqa: F401 — before bmesh, which bpy provides
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

import sand3d as s3d
from test_solids import closed_volume, faces, length


def sharpest_turn(ob):
    """The largest angle, in degrees, between the normals of two faces sharing an edge."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.normal_update()
    turn = max(e.link_faces[0].normal.angle(e.link_faces[1].normal, 0) for e in bm.edges if len(e.link_faces) == 2)
    bm.free()
    return math.degrees(turn)


def box_of(ob):
    co = [v.co for v in ob.data.vertices]
    return [min(c[i] for c in co) for i in range(3)], [max(c[i] for c in co) for i in range(3)]


def inside(ob, point):
    """Whether `point`, in `ob`'s own space, lies inside its closed mesh."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    tree = BVHTree.FromBMesh(bm)
    bm.free()
    co, normal, _, _ = tree.find_nearest(Vector(point))
    return (Vector(point) - co).dot(normal) < 0


class Blend(unittest.TestCase):

    def setUp(self):
        s3d.empty_scene()

    def spheres(self, verb, y=50, **kw):
        a = s3d.at(s3d.sphere("a", 20), y=y)
        b = s3d.at(s3d.sphere("b", 20), x=14, y=y)
        return verb(a, b, **kw)

    def test_two_balls_meet_without_a_crease(self):
        joined = self.spheres(s3d.join, y=0)
        blended = self.spheres(s3d.blend, r=2)
        self.assertGreater(sharpest_turn(joined), 90, "joined, the balls meet at a crease")
        # voxels of r / 5: neighbouring faces turn by about voxel / r, a quad's diagonal a little more
        self.assertLess(sharpest_turn(blended), 25, "blended, the surface nowhere turns sharper than r allows")
        closed, volume = closed_volume(blended)
        self.assertTrue(closed)
        self.assertGreater(volume, closed_volume(joined)[1], "a closing only adds")
        voxel = 2 / 5
        for got, want in zip(box_of(blended), box_of(joined)):
            for g, w in zip(got, want):
                self.assertAlmostEqual(g, w, delta=voxel, msg="the outer silhouette stays within a voxel")

    def test_the_others_are_used_up_and_ob_keeps_its_place(self):
        a = s3d.at(s3d.sphere("a", 20), x=100, rz=30)
        before = a.matrix_basis.copy()
        b = s3d.at(s3d.sphere("b", 20), x=110)
        s3d.blend(a, b, r=2)
        self.assertEqual(a.matrix_basis, before)
        self.assertEqual([o.name for o in bpy.data.objects], ["a"])
        with self.assertRaises(ValueError) as caught:
            s3d.join(a, b)
        self.assertIn("'b' was used up by blend(a, ...)", str(caught.exception))
        lo, hi = box_of(a)
        self.assertAlmostEqual(hi[0] - lo[0], 20 + 10 * math.cos(math.radians(30)), delta=0.4,
                               msg="b read in a's own frame, turned 30°")

    def test_faces_are_named_blend(self):
        a = self.spheres(s3d.blend, r=2)
        self.assertEqual(faces(a, "blend"), len(a.data.polygons))
        self.assertEqual(faces(a, "a.blend"), len(a.data.polygons))
        self.assertEqual(sorted(x.name for x in a.data.attributes if x.name.startswith("s3d_")),
                         ["s3d_face:a.blend", "s3d_face:blend"], "no maker's name, no named edge survives")
        self.assertAlmostEqual(a.face("+Z").origin.z, 20, delta=0.4)

    def test_its_own_creases_fill(self):
        step = s3d.extrude("step", s3d.poly([(0, 0), (20, 0), (20, 8), (8, 8), (8, 20), (0, 20)]), 6)
        corner = (8 + 0.4, 8 + 0.4, 3)          # a hair outside the inner corner
        self.assertFalse(inside(step, corner))
        s3d.blend(step, r=3)
        self.assertTrue(inside(step, corner), "the inner corner is filled to r = 3")
        self.assertFalse(inside(step, (8 + 2, 8 + 2, 3)), "and no further than r")

    def test_a_gap_under_2r_fills(self):
        a = s3d.box("a", 10, 10, 10)
        b = s3d.at(s3d.box("b", 10, 10, 10), x=11)
        s3d.blend(a, b, r=1)
        self.assertTrue(inside(a, (5.5, 0, 5)), "a gap of 1 closes at r = 1")
        c = s3d.at(s3d.box("c", 10, 10, 10), y=40)
        d = s3d.at(s3d.box("d", 10, 10, 10), x=14, y=40)
        s3d.blend(c, d, r=1)
        self.assertFalse(inside(c, (7, 0, 5)), "a gap of 4 stays open at r = 1")

    def test_the_unit_does_not_change_the_shape(self):
        a = self.spheres(s3d.blend, r=2)
        mm = KDTree(len(a.data.vertices))
        for i, v in enumerate(a.data.vertices):
            mm.insert(v.co, i)
        mm.balance()
        count = len(a.data.vertices)
        s3d.empty_scene()
        s3d.units("cm")
        a = s3d.at(s3d.sphere("a", 2), y=5)
        b = s3d.at(s3d.sphere("b", 2), x=1.4, y=5)
        s3d.blend(a, b, r=0.2)
        self.assertEqual(len(a.data.vertices), count)
        self.assertLess(max(mm.find(v.co * 10)[2] for v in a.data.vertices), 1e-3)

    def test_jointed_parts_are_refused(self):
        base = s3d.box("base", 40, 40, 10)
        arm = s3d.at(s3d.box("arm", 10, 10, 30), z=10)
        s3d.joint("hinge", arm, base.face("top"), axis="+X", range=(0, 90))
        with self.assertRaises(ValueError) as caught:
            s3d.blend(base, arm, r=2)
        self.assertIn("blend: 'arm' moves by its joint 'hinge'", str(caught.exception))

    def test_a_blend_past_its_budget_raises_and_uses_nothing_up(self):
        big = s3d.sphere("big", 1000)
        small = s3d.at(s3d.sphere("small", 200), x=500)
        with self.assertRaises(ValueError) as caught:
            s3d.blend(big, small, r=1)
        self.assertRegex(str(caught.exception), r"^blend: r = 1 on 'big' would take about [\d,]+ faces \(voxels of r / 5 "
                                                r"over its surface\), more than 600,000: give a larger r, or blend "
                                                r"smaller groups of parts and join the results$")
        self.assertEqual(sorted(o.name for o in bpy.data.objects), ["big", "small"])
        s3d.join(big, small)

    def assertUntouched(self, names):
        self.assertEqual(sorted(o.name for o in bpy.data.objects), sorted(names), "nothing used up")
        self.assertFalse([m.name for m in bpy.data.meshes if m.name.startswith("_s3d")], "no temporary left")

    def test_a_part_thinner_than_2r_is_refused(self):
        """Under ten voxels across, the voxels swell or shrink a part: a 1 cube at r = 10 came back 123 in volume."""
        a = s3d.box("a", 10, 10, 10)
        chip = s3d.at(s3d.box("chip", 1, 1, 1), x=5.4)
        with self.assertRaises(ValueError) as caught:
            s3d.blend(a, chip, r=10)
        self.assertEqual(str(caught.exception), "blend: 'chip' is 1 thick, under 2 r = 20: the voxels (r / 5) do not "
                                                "hold it — give an r of 0.5 or less, or join it after the blend")
        self.assertUntouched(["a", "chip"])
        self.assertAlmostEqual(closed_volume(chip)[1], 1, places=9)
        s3d.blend(a, chip, r=0.5)
        self.assertAlmostEqual(closed_volume(a)[1], 1000 + 0.9, delta=3, msg="the chip stays a chip")

    def test_a_result_past_its_parts_is_refused(self):
        """Behind the thickness check, the result is held to the parts' box: a closing never grows past it."""
        a = s3d.box("a", 1, 1, 1)
        b = s3d.at(s3d.box("b", 1, 1, 1), x=0.5)
        with mock.patch("sand3d.edit._thinnest", lambda parts, size: None), self.assertRaises(ValueError) as caught:
            s3d.blend(a, b, r=10)
        self.assertRegex(str(caught.exception), r"^blend: the voxels \(r / 5 = 2\) do not resolve 'a': the result would "
                                                r"stand [\d.]+ beyond its parts — give a smaller r$")
        self.assertUntouched(["a", "b"])
        self.assertAlmostEqual(closed_volume(a)[1], 1, places=9)

    def test_an_empty_result_uses_nothing_up(self):
        a = s3d.box("a", 10, 10, 10)
        b = s3d.at(s3d.box("b", 10, 10, 10), x=5)
        a.data.clear_geometry()
        b.data.clear_geometry()
        with self.assertRaises(ValueError) as caught:
            s3d.blend(a, b, r=1)
        self.assertTrue(str(caught.exception).startswith("blend: nothing is left of 'a'"))
        self.assertUntouched(["a", "b"])

    def test_arguments(self):
        a = s3d.sphere("a", 20)
        for r, error in ((0, ValueError), (-1, ValueError), ("2", TypeError)):
            with self.subTest(r=r), self.assertRaises(error):
                s3d.blend(a, r=r)
        with self.assertRaises(TypeError):
            s3d.blend(a, s3d.circle(10), r=1)
        with self.assertRaises(ValueError) as caught:
            s3d.blend(a, a, r=1)
        self.assertIn("is passed 2 times", str(caught.exception))


class Displace(unittest.TestCase):

    def setUp(self):
        s3d.empty_scene()

    def test_a_dense_part_needing_no_cut_is_displaced_whatever_its_faces(self):
        """The budget counts the faces refining adds: a blended part is already dense."""
        ball = s3d.sphere("ball", 100)
        dense = len(ball.data.polygons)
        with mock.patch("sand3d.edit.DISPLACE_FACES", dense // 2):
            s3d.displace(ball, 1, 400)
            with self.assertRaises(ValueError) as caught:
                s3d.displace(ball, 1, 4)
        self.assertIn("would add about", str(caught.exception))

    def test_no_amount_leaves_the_shape(self):
        box = s3d.box("box", 40, 30, 20)
        s3d.displace(box, 0, 8, noise="cells", octaves=3)
        closed, volume = closed_volume(box)
        self.assertTrue(closed)
        self.assertAlmostEqual(volume, 40 * 30 * 20, delta=1e-2)
        for v in box.data.vertices:
            x, y, z = v.co
            self.assertTrue(abs(abs(x) - 20) < 1e-6 or abs(abs(y) - 15) < 1e-6 or min(abs(z), abs(z - 20)) < 1e-6)
        self.assertLessEqual(max((box.data.vertices[e.vertices[0]].co - box.data.vertices[e.vertices[1]].co).length
                                 for e in box.data.edges), 2 * 1.5, "no edge much longer than size / 4")

    def test_a_concave_face_stays_inside_its_outline(self):
        """A U's caps are one concave face each: a fan from their centre would cover the notch."""
        outline = [(0, 0), (10, 0), (10, 10), (8, 10), (8, 2), (2, 2), (2, 10), (0, 10)]
        built = {}
        for unit, k in (("mm", 1), ("m", 0.001)):
            s3d.empty_scene()
            s3d.units(unit)
            u = s3d.extrude("u", s3d.poly([(x * k, y * k) for x, y in outline]), 2 * k)
            s3d.displace(u, 0, 10 * k)
            bm = bmesh.new()
            bm.from_mesh(u.data)
            in_notch = [f for f in bm.faces
                        if 2.01 < f.calc_center_median().x / k < 7.99 and f.calc_center_median().y / k > 2.01]
            in_notch += [v for v in bm.verts if 2.01 < v.co.x / k < 7.99 and v.co.y / k > 2.01]
            area = sum(f.calc_area() for f in bm.faces) / k ** 2
            bm.free()
            with self.subTest(unit=unit):
                self.assertEqual(in_notch, [], "no surface in the notch")
                self.assertAlmostEqual(area, 2 * 52 + 56 * 2, delta=1e-3, msg="two caps of 52, walls 56 round, 2 high")
            built[unit] = sorted(tuple(round(c / k, 3) for c in v.co) for v in u.data.vertices)
        self.assertEqual(built["mm"], built["m"], "the same triangles in any unit")
        s3d.empty_scene()
        s3d.units("mm")

    def test_the_faces_follow_the_area_not_the_cut(self):
        """A loft of two stations is one band of long thin quads; with a third station halfway,
        twice as many. Refined, both should come to about the same count, area / (size / 4)²."""
        counts = []
        for middle in ([], [s3d.station(-175, 440, 260, x=-10, n=2.5)]):
            s3d.empty_scene()
            sections = [s3d.station(0, 480, 340, n=2.5), *middle, s3d.station(-350, 400, 180, x=-20, n=2.5)]
            wall = s3d.shell(s3d.loft("s", *sections), 12, open="start end")
            cells = sum(p.area for p in wall.data.polygons) / (16 / 4) ** 2
            s3d.displace(wall, 4, 16, noise="cells")
            counts.append(len(wall.data.polygons) / cells)
        self.assertLess(max(counts), 5, "a few triangles per cell of size / 4")
        self.assertLess(max(counts) / min(counts), 1.25, "whatever the stations")

    def test_the_refinement_ends_quickly(self):
        """Refinement terminates on a thin bent blade and a zero-area folded wall."""
        outline = [(70 * math.sin(2 * math.pi * i / 32), 550 * (1 - math.cos(2 * math.pi * i / 32))) for i in range(32)]
        blade = s3d.extrude("blade", s3d.poly(outline), 0.8, both=True)
        s3d.bend(blade, -16)
        s3d.twist(blade, 20)
        flat = s3d.at(s3d.box("flat", 1100, 140, 20), y=300)
        s3d.scale(flat, (1, 1, 0))
        start = time.perf_counter()
        s3d.displace(blade, amount=8, size=100, direction="+Z")
        s3d.displace(flat, 8, 100)
        self.assertLess(time.perf_counter() - start, 20, "a few thousand faces: well under a second when idle")
        for ob in (blade, flat):
            with self.subTest(ob=ob.name):
                self.assertTrue(all(math.isfinite(c) for v in ob.data.vertices for c in v.co))
                self.assertLess(len(ob.data.polygons), 20_000)
        self.assertTrue(closed_volume(blade)[0])

    def test_names_are_kept(self):
        box = s3d.box("box", 40, 30, 20)
        s3d.displace(box, 1, 8)
        self.assertGreater(faces(box, "top"), 0)
        self.assertGreater(length(box, "top"), 140, "the top's rim, pushed in and out, is a little longer")
        self.assertLess(length(box, "top"), 170)

    def test_a_fade_leaves_the_faded_end_untouched(self):
        plain = s3d.cylinder("plain", 20, 30)
        s3d.displace(plain, 0, 4, fade=(30, 10))
        rough = s3d.at(s3d.cylinder("rough", 20, 30), x=50)
        s3d.displace(rough, 1.5, 4, octaves=2, fade=(30, 10))
        below = lambda ob: sorted(tuple(round(c, 6) for c in v.co) for v in ob.data.vertices if v.co.z <= 10)
        self.assertEqual(below(plain), below(rough))
        self.assertNotEqual(sorted(tuple(v.co) for v in plain.data.vertices),
                            sorted(tuple(v.co) for v in rough.data.vertices))

    def test_every_noise_stays_within_amount(self):
        for k, kind in enumerate(("perlin", "cells", "ridged", "turbulence")):
            ball = s3d.at(s3d.sphere(kind, 30), x=40 * k)
            s3d.displace(ball, 1, 5, noise=kind, octaves=3, direction="radial")
            radii = [(v.co - Vector((0, 0, 15))).length for v in ball.data.vertices]
            with self.subTest(noise=kind):
                self.assertTrue(closed_volume(ball)[0])
                self.assertLessEqual(max(radii), 15 + 1 + 1e-4)
                self.assertGreaterEqual(min(radii), 15 - 1 - 0.05, "less the facets' sag")
                self.assertGreater(max(radii) - min(radii), 0.5, "and moves it")

    def test_the_noise_is_centred(self):
        """Turbulence and ridged lean to one side; centred, a part keeps about its volume."""
        before = closed_volume(s3d.sphere("ref", 40))[1]
        for k, kind in enumerate(("perlin", "cells", "ridged", "turbulence")):
            ball = s3d.at(s3d.sphere(kind, 40), x=50 * k)
            s3d.displace(ball, 2, 6, noise=kind, octaves=2)
            with self.subTest(noise=kind):
                self.assertAlmostEqual(closed_volume(ball)[1] / before, 1, delta=0.02)

    def test_a_direction_moves_along_it(self):
        plain = s3d.box("plain", 20, 20, 10)
        s3d.displace(plain, 0, 5)
        down = s3d.at(s3d.box("down", 20, 20, 10), x=50)
        s3d.displace(down, 1, 5, direction="-Z")
        across = lambda ob: sorted((round(v.co.x, 6), round(v.co.y, 6)) for v in ob.data.vertices)
        self.assertEqual(across(plain), across(down), "x and y stay where they were")
        self.assertGreater(max(abs(v.co.z - 10) for v in down.data.vertices if v.co.z > 5), 0.3)

    def test_the_seed_picks_the_field(self):
        def build(seed, x):
            ball = s3d.at(s3d.sphere("ball", 20), x=x)
            s3d.displace(ball, 1, 5, seed=seed)
            return sorted(tuple(round(c, 6) for c in v.co) for v in ball.data.vertices)
        self.assertEqual(build(3, 0), build(3, 0))
        self.assertNotEqual(build(3, 0), build(4, 0))

    def test_arguments(self):
        ball = s3d.sphere("ball", 20)
        says = [(ValueError, "displace: noise is 'perlin', 'cells', 'ridged' or 'turbulence', not 'simplex'",
                 dict(noise="simplex")),
                (ValueError, "displace: octaves is a whole number, 1 or more, not 0", dict(octaves=0)),
                (TypeError, "displace: seed is an integer, not 1.5", dict(seed=1.5)),
                (ValueError, "displace: direction is \"normal\", \"radial\" (from the part's origin), a direction "
                             "(\"+Z\", \"-X\"…) or (x, y, z), not 'up'", dict(direction="up")),
                (ValueError, "displace: fade runs between two different heights, not 5 and 5", dict(fade=(5, 5))),
                (TypeError, "displace: fade is (z0, z1), full effect at z0 and none at z1, not 5", dict(fade=5)),
                (ValueError, "displace: fade runs between two finite heights, not 0 and nan", dict(fade=(0, math.nan))),
                (ValueError, "displace: fade runs between two finite heights, not 0 and inf", dict(fade=(0, math.inf))),
                (ValueError, "displace: direction is \"normal\", \"radial\" (from the part's origin), a direction "
                             "(\"+Z\", \"-X\"…) or (x, y, z), not (inf, 0, 0)", dict(direction=(math.inf, 0, 0))),
                (ValueError, "displace: direction is \"normal\", \"radial\" (from the part's origin), a direction "
                             "(\"+Z\", \"-X\"…) or (x, y, z), not (1e+308, 1e+308, 0)",
                 dict(direction=(1e308, 1e308, 0)))]
        before = [tuple(v.co) for v in ball.data.vertices]
        for error, message, kw in says:
            with self.subTest(**kw), self.assertRaises(error) as caught:
                s3d.displace(ball, 1, 5, **kw)
            self.assertEqual(str(caught.exception), message)
        self.assertEqual([tuple(v.co) for v in ball.data.vertices], before, "a refusal leaves the mesh as it was")
        with self.assertRaises(ValueError):
            s3d.displace(ball, 1, 0)
        with self.assertRaises(ValueError) as caught:
            s3d.displace(ball, 1, 0.01, step=.0025)
        self.assertIn("give a larger size", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
