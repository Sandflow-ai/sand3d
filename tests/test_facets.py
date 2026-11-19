"""`facets` sets the segments of a full circle for the whole program, as `units` sets its unit."""
import unittest

from mathutils import Vector

import sand3d as s3d


def sides(ob):
    """Faces of a prism standing on Z = 0 that are neither its top nor its bottom."""
    return sum(1 for f in ob.data.polygons if abs(f.normal.z) < 1e-6)


class Facets(unittest.TestCase):

    def setUp(self):
        s3d.empty_scene()

    def tearDown(self):
        s3d.empty_scene()

    def test_scopes_restore_nested_counts_and_exceptions(self):
        s3d.facets(12)
        with s3d.facets(4) as count:
            self.assertEqual(count, 4)
            self.assertEqual(sides(s3d.cylinder('four', 20, 10)), 4)
            with s3d.facets(8):
                self.assertEqual(sides(s3d.cylinder('eight', 20, 10)), 8)
            self.assertEqual(s3d.facets(), 4)
            with self.assertRaisesRegex(RuntimeError, 'stop'):
                with s3d.facets(6):
                    raise RuntimeError('stop')
            self.assertEqual(s3d.facets(), 4)
        self.assertEqual(sides(s3d.cylinder('twelve', 20, 10)), 12)
        s3d.facets(6)
        self.assertEqual(s3d.facets(), 6)

    def test_scope_restores_auto_and_shading(self):
        from sand3d import _core
        # A first scoped setting must not constrain the following bare call.
        with s3d.facets(4, smooth=True):
            self.assertTrue(_core.FACET_SMOOTH)
        self.assertEqual(s3d.facets(), 'auto')
        s3d.facets(8, smooth=False)
        self.assertFalse(_core.FACET_SMOOTH)

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
        auto = s3d.cylinder("auto", 20, 10)
        with s3d.facets(8):
            low = s3d.cylinder("low", 20, 10)
        self.assertEqual(s3d.facets(), "auto")
        after = s3d.cylinder("after", 20, 10)
        self.assertEqual(sides(low), 8)
        self.assertEqual(len(after.data.polygons), len(auto.data.polygons))
        s3d.facets(6)
        self.assertEqual(sides(s3d.cylinder("six", 20, 10)), 6)
        with s3d.facets("auto"):
            again = s3d.cylinder("again", 20, 10)
        self.assertEqual(len(again.data.polygons), len(auto.data.polygons))
        self.assertEqual(s3d.facets(), 6)

    def test_a_facets_block_flattens_only_what_it_builds(self):
        before = s3d.cylinder("before", 20, 10)
        with s3d.facets(8):
            low = s3d.cylinder("low", 20, 10)
        after = s3d.cylinder("after", 20, 10)
        self.assertTrue(all(p.use_smooth for p in before.data.polygons))
        self.assertFalse(any(p.use_smooth for p in low.data.polygons))
        self.assertTrue(all(p.use_smooth for p in after.data.polygons))

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


    def test_straight_meridians_need_only_stations(self):
        s3d.facets(10)
        ob = s3d.loft("form", s3d.station(0, 100, 100), s3d.station(100, 100, 100),
                      s3d.station(200, 100, 100))
        self.assertEqual(len(ob.data.vertices), 30)
        self.assertEqual({v.co.z for v in ob.data.vertices}, {0, 100, 200})

    def test_curved_meridians_and_sections(self):
        counts = []
        for n in (6, 10, 20):
            s3d.empty_scene()
            s3d.facets(n)
            sections = [s3d.station(z, w, d) for z, w, d in ((0, 300, 200), (300, 360, 220), (600, 120, 110))]
            expected = [tuple(q) for section in sections for q in
                        (section.matrix @ Vector((x, y, 0))
                         for x, y in section.profile.loops[0].pts)]
            ob = s3d.loft("form", *sections)
            coords = [tuple(v.co) for v in ob.data.vertices]
            for q in expected:
                self.assertTrue(any(sum((a-b)**2 for a,b in zip(q,v)) < 1e-7 for v in coords))
            counts.append(len(coords) / n)
            self.assert_valid(ob)
        self.assertEqual(counts, sorted(counts))
        self.assertGreater(counts[-1], counts[0])

    def assert_valid(self, ob):
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        self.assertTrue(all(e.is_manifold and e.is_contiguous for e in bm.edges))
        self.assertTrue(all(f.calc_area() > 1e-8 for f in bm.faces))
        bm.free()

    def test_quarter_turn_pole_cap(self):
        import math
        for n in (6, 10, 20):
            s3d.empty_scene()
            s3d.facets(n)
            ob = s3d.loft("cap", s3d.station(0, 0, 0), s3d.station(100, 100, 100))
            self.assertEqual(len(ob.data.vertices), 1 + n * math.ceil(n / 4))
            self.assertIn((0, 0, 0), [tuple(v.co) for v in ob.data.vertices])
            self.assert_valid(ob)

    def test_shading_survives_edits(self):
        for smooth in (False, True):
            s3d.empty_scene()
            s3d.facets(10, smooth=smooth)
            ob = s3d.box("block", 80, 60, 40)
            s3d.fillet(ob, 4, edges="top")
            s3d.cut(ob, s3d.cylinder("tool", 12, 50))
            ob = s3d.copy(ob)
            s3d.transform(ob, mirror="x")
            self.assertEqual({p.use_smooth for p in ob.data.polygons}, {smooth})

    def test_smoothing_errors(self):
        with self.assertRaisesRegex(ValueError, "fixed count"):
            s3d.facets("auto", smooth=True)
        with self.assertRaisesRegex(ValueError, "fixed count"):
            s3d.facets(smooth=True)
        self.assertEqual(s3d.facets("auto", smooth=False), "auto")
        for option in (None, 1, "flat"):
            with self.assertRaises(ValueError):
                s3d.facets(10, smooth=option)
        s3d.facets(10)
        s3d.box("block", 10, 10, 10)
        with self.assertRaisesRegex(ValueError, "s3d.smooth"):
            s3d.facets(10, smooth=True)

    def test_auto_unchanged(self):
        ob = s3d.loft("form", s3d.station(0,300,200), s3d.station(300,360,220), s3d.station(600,120,110))
        ob.data.calc_loop_triangles()
        self.assertEqual(len(ob.data.loop_triangles), 2492)
        self.assertTrue(all(p.use_smooth for p in ob.data.polygons))

    def test_loop_and_follow(self):
        for n in (6, 20):
            for follow, loop in ((True, False), (False, True), (True, True)):
                s3d.empty_scene()
                s3d.facets(n)
                sections = [s3d.station(z, 20, 20, x=x) for x, z in
                            ((0, 0), (100, 100), (200, 0), (100, -100))]
                ob = s3d.loft("loop", *sections, follow=follow, loop=loop)
                self.assert_valid(ob)

    def test_wire_law_and_body(self):
        for n in (6, 10, 20):
            s3d.empty_scene()
            s3d.facets(n)
            ob = s3d.wire("stem", [(0, 0, 0), (0, 0, 300)], [(0, 0), (.5, 80), (1, 20)])
            self.assert_valid(ob)
            self.assertIn((0, 0, 0), [tuple(v.co) for v in ob.data.vertices])
            body = s3d.body("body", s3d.spline([(0, 10), (100, 80), (300, 20)]), 50, -50)
            self.assert_valid(body)

    def test_glb_flat_normals(self):
        import json
        import struct
        import tempfile
        from pathlib import Path
        s3d.facets(6)
        ob = s3d.cylinder("post", 20, 40)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "post.glb"
            s3d.export(ob, path)
            raw = path.read_bytes()
        size, kind = struct.unpack_from("<II", raw, 12)
        gltf = json.loads(raw[20:20+size])
        binary = raw[28+size:]

        def values(index):
            accessor = gltf["accessors"][index]
            view = gltf["bufferViews"][accessor["bufferView"]]
            start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
            dim = {"SCALAR": 1, "VEC3": 3}[accessor["type"]]
            fmt = {5121: "B", 5123: "H", 5125: "I", 5126: "f"}[accessor["componentType"]]
            step = view.get("byteStride", struct.calcsize("<" + fmt * dim))
            return [struct.unpack_from("<" + fmt * dim, binary, start + i * step)
                    for i in range(accessor["count"])]

        for mesh in gltf["meshes"]:
            for primitive in mesh["primitives"]:
                normals = values(primitive["attributes"]["NORMAL"])
                indices = [v[0] for v in values(primitive["indices"])]
                for i in range(0, len(indices), 3):
                    a, b, c = (normals[j] for j in indices[i:i+3])
                    self.assertEqual(a, b)
                    self.assertEqual(b, c)


    def test_counts_can_change_between_parts(self):
        s3d.facets(16, smooth=True)
        hat = s3d.dome('hat', 100, 40)
        before = [tuple(v.co) for v in hat.data.vertices]
        s3d.facets(8)
        limb = s3d.cylinder('limb', 20, 100)
        self.assertEqual(sides(limb), 8)
        self.assertEqual(s3d.facets(), 8)
        self.assertEqual(before, [tuple(v.co) for v in hat.data.vertices])
        self.assertTrue(all(p.use_smooth for p in limb.data.polygons))
        with self.assertRaisesRegex(ValueError, 's3d.smooth'):
            s3d.facets(12, smooth=False)
        self.assertEqual(s3d.facets('auto'), 'auto')

    def test_first_shading_choice_is_kept_before_geometry(self):
        s3d.facets(16, smooth=True)
        s3d.facets(8)
        with self.assertRaisesRegex(ValueError, 's3d.smooth'):
            s3d.facets(12, smooth=False)
        s3d.box('built',1,1,1)

    def test_changing_counts_is_deterministic(self):
        import subprocess
        import sys
        code = """import sand3d as s
s.facets(16); a=s.dome('hat',100,40)
with s.facets(4): c=s.cylinder('scope',20,100)
s.facets(8); b=s.cylinder('limb',20,100)
print([(tuple(v.co),) for p in (a,b,c) for v in p.data.vertices])
"""
        results=[subprocess.run([sys.executable,'-c',code],capture_output=True,check=True).stdout.splitlines() for _ in range(2)]
        self.assertEqual(*[[line for line in output if line.startswith(b'[(')] for output in results])


if __name__ == "__main__":
    unittest.main()
