"""Retained voids, placement, contact and dense boolean operands."""

import unittest
import bpy
import bmesh
import numpy as np
import sand3d as s3d
from mathutils import Matrix
from sand3d import _core


def vessel(name="vessel"):
    return s3d.revolve(name, s3d.poly([(0, 0), (12, 0), (16, 30), (14, 30), (10, 3), (0, 3)]))


def terrain(two=False, size=5, step=None):
    ground = s3d.box("terrain", 100, 80, 20)

    def height(x, y, z):
        dip = np.exp(-((x - 22 if two else x) ** 2 + y * y) / 180)
        if two:
            dip += np.exp(-((x + 22) ** 2 + y * y) / 180)
        return -dip * np.clip(z / 20, 0, 1)

    return s3d.displace(ground, 12, size, noise=height, direction="+Z", step=step)


def volume(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    result = bm.calc_volume(signed=True)
    bm.free()
    return result


class Fill(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()
        s3d.units("mm")
        s3d.facets(64)

    def closed(self, ob):
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        self.assertTrue(all(e.is_manifold for e in bm.edges))
        self.assertGreater(bm.calc_volume(signed=True), 0)
        bm.free()

    def test_glass_contact(self):
        glass = vessel()
        exact = s3d.fill("contact", glass, 22, clearance=0)
        overlap = s3d.fill("overlap", glass, 22)
        self.closed(exact)
        self.closed(overlap)
        self.assertGreater(volume(overlap), volume(exact))
        self.assertAlmostEqual(overlap.face("top").origin.z, 22, places=4)
        self.assertEqual(len(glass.data.vertices), len(vessel("other").data.vertices))
        gap = s3d.fill("gap", glass, 22, clearance=0.1)
        self.assertLess(volume(gap), volume(exact))

    def test_mug_handle(self):
        mug = vessel()
        expected = volume(s3d.fill("reference", mug, 22, 0))
        handle = s3d.at(s3d.torus("handle", 18, 4), x=24, z=14, rx=90)
        mug = s3d.group("mug", mug, handle)
        water = s3d.fill("drink", mug, 22, 0)
        self.closed(water)
        self.assertAlmostEqual(volume(water), expected, delta=0.01)

    def test_bottle(self):
        bottle = s3d.revolve(
            "bottle",
            s3d.poly(
                [(0, 0), (14, 0), (14, 30), (2, 40), (2, 45), (1, 45), (1, 40), (12, 29), (12, 2), (0, 2)]
            ),
        )
        self.closed(s3d.fill("contents", bottle, 43))

    def test_dense_terrain(self):
        s3d.facets("auto")
        ground = terrain(size=4, step=1)
        ground.data.calc_loop_triangles()
        self.assertGreater(len(ground.data.loop_triangles), 40000)
        self.closed(s3d.fill("pond", ground, 16))

    def test_two_depressions(self):
        water = s3d.fill("ponds", terrain(True), 16, 0)
        self.closed(water)
        bm = bmesh.new()
        bm.from_mesh(water.data)
        pending = set(bm.verts)
        count = 0
        while pending:
            stack = [pending.pop()]
            count += 1
            while stack:
                v = stack.pop()
                for e in v.link_edges:
                    w = e.other_vert(v)
                    if w in pending:
                        pending.remove(w)
                        stack.append(w)
        bm.free()
        self.assertEqual(count, 2)

    def test_pavers_and_bed(self):
        bed = s3d.shell(s3d.box("bed", 100, 80, 12), 2, open="top")
        stones = s3d.at(s3d.box("paver", 16, 15, 12), on=s3d.grid(5, 4, 18, 18), z=2)
        paved = s3d.group("paved", bed, stones)
        self.closed(s3d.fill("puddle", paved, 6))

    def test_inclined_and_parented(self):
        channel = s3d.shell(s3d.box("channel", 100, 20, 20), 2, open="top")
        parent = s3d.at(s3d.group("parent", channel), x=100, ry=12)
        f = s3d.local(channel, z=10, ry=4)
        water = s3d.fill("river", channel, f, 0)
        self.closed(water)
        expected = _core.world(channel) @ f._in_part()
        heights = [v.co.z for v in water.data.vertices]
        self.assertAlmostEqual(min(heights), 0, places=4)  # it stands on its own Z = 0
        surface = _core.world(water) @ Matrix.Translation((0, 0, max(heights)))
        self.assertLess((surface.translation - expected.translation).length, 1e-4)
        for got, want in zip(surface.to_3x3(), expected.to_3x3()):
            self.assertLess((got - want).length, 1e-6)
        top = water.face("top")
        self.assertLess((top.matrix.col[2].xyz - expected.col[2].xyz).length, 1e-6)

    def test_other_materials(self):
        for name, kind in (("pot", "soil"), ("tray", "sand"), ("form", "concrete")):
            container = s3d.shell(s3d.box(name, 30, 20, 25), 2, open="top")
            contents = s3d.fill(kind, container, 18)
            s3d.material(contents, kind)
            self.closed(contents)

    def test_errors_and_no_leaked_objects(self):

        glass = vessel()
        for level in (-1, 1, 35):
            before = set(bpy.data.objects)
            with self.assertRaisesRegex(ValueError, "fill:"):
                s3d.fill("empty", glass, level)
            self.assertEqual(before, set(bpy.data.objects))
        with self.assertRaisesRegex(TypeError, "Frame"):
            s3d.fill("ambiguous", [glass], 20)
        s3d.hole(glass, 2, on=s3d.local(glass), depth=5)
        with self.assertRaisesRegex(ValueError, "leak|retained"):
            s3d.fill("leaking", glass, 20)

    def test_open_part_is_named_and_located(self):
        tray = s3d.shell(s3d.box("tray", 40, 30, 20), 2, open="top")
        bm = bmesh.new()
        bm.from_mesh(tray.data)
        bm.faces.ensure_lookup_table()
        lowest = min(bm.faces, key=lambda f: f.calc_center_median().z)
        bmesh.ops.delete(bm, geom=[lowest], context="FACES_ONLY")
        bm.to_mesh(tray.data)
        bm.free()
        with self.assertRaisesRegex(ValueError, r"'tray' is not a closed solid: \d+ open edges?, in its own frame at x "):
            s3d.fill("water", tray, 12)

    def test_submerged_obstacles(self):
        cup = s3d.shell(s3d.box("cup", 30, 30, 30), 2, open="top")
        stone = s3d.at(s3d.box("stone", 4, 4, 4), z=5)
        outside = s3d.at(s3d.box("outside", 4, 4, 4), x=50, z=5)
        exact = s3d.fill("plain", cup, 20, 0)
        water = s3d.fill("with_stone", [cup, stone, outside], s3d.Frame((0, 0, 20)), 0)
        self.assertAlmostEqual(volume(exact) - volume(water), 64, places=3)

    def test_units(self):
        s3d.empty_scene()
        s3d.units("m")
        cup = s3d.shell(s3d.box("cup", 0.03, 0.03, 0.03), 0.002, open="top")
        water = s3d.fill("water", cup, 0.02)
        self.assertAlmostEqual(max(v.co.x for v in water.data.vertices), 0.01304, places=6)

    def test_sealed_cavity(self):
        sealed = s3d.shell(s3d.box("sealed", 20, 20, 20), 2)
        contents = s3d.fill("inside", sealed, 30, 0)
        self.closed(contents)
        self.assertAlmostEqual(volume(contents), 16**3, places=3)

    def test_partial_leak_and_assembly(self):
        good = s3d.shell(s3d.box("good", 20, 20, 20), 2, open="top")
        bad = s3d.at(s3d.tube("leaking", 20, 16, 20), x=40)
        assembly = s3d.assembly("pair", good, bad)
        contents = s3d.fill("retained", assembly, 15, 0)
        self.assertAlmostEqual(volume(contents), 16 * 16 * 13, places=3)

    def test_hollow_submerged_obstacle(self):
        cup = s3d.shell(s3d.box("cup", 30, 30, 30), 2, open="top")
        obstacle = s3d.at(s3d.shell(s3d.box("hollow", 4, 4, 4), 0.5), z=5)
        plain = s3d.fill("plain", cup, 20, 0)
        filled = s3d.fill("filled", [cup, obstacle], s3d.Frame((0, 0, 20)), 0)
        self.assertAlmostEqual(volume(plain) - volume(filled), 64 - 27, places=3)
