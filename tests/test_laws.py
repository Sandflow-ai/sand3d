"""Length laws, rounded poles and the frames of growing structures."""
import math
import unittest

import bpy
import bmesh
import sand3d as s3d
from sand3d import _core


class Laws(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()
        s3d.units("mm")

    def test_interpolation_is_monotone_and_hits_knots(self):
        rows = [(0, 2), (0.1, 3), (0.7, 3), (1, -1)]
        law = _core.Law(rows)
        for u, v in rows:
            self.assertAlmostEqual(law(u), v)
        for (a, x), (b, y) in zip(rows, rows[1:]):
            vals = [law(a + (b-a)*i/100) for i in range(101)]
            self.assertTrue(all(min(x,y)-1e-12 <= v <= max(x,y)+1e-12 for v in vals))
        pair = _core.Law([(0, (1, 2)), (1, (3, 4))])
        self.assertEqual(pair(0.5), (2, 3))

    def test_malformed_laws(self):
        for rows in ([], [(0, 2)], [(0.1, 2), (1, 3)], [(0, 2), (0.9, 3)],
                     [(0, 2), (0.7, 3), (0.5, 4), (1, 2)], [(0, 2), (1, (2, 3))],
                     [(0, 2), (1, float("nan"))], [(0, 2), (2, 3), (1, 4)]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                _core.Law(rows)

    def assert_solid(self, ob):
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        self.assertTrue(all(e.is_manifold for e in bm.edges))
        self.assertTrue(all(v.is_manifold for v in bm.verts))
        self.assertTrue(all(f.calc_area() > 0 for f in bm.faces))
        self.assertGreater(bm.calc_volume(), 0)
        bm.free()

    def test_wire_round_pole(self):
        ob = s3d.wire("tip", [(0, 0, 0), (0, 0, 10)], [(0, 2), (1, 0)])
        self.assert_solid(ob)
        # The tip is rounder than a conical linear taper.
        ring = [v.co for v in ob.data.vertices if abs(v.co.z - 5) < 1e-6]
        self.assertGreater(max(v.xy.length for v in ring), 0.55)
        self.assertEqual(sum(v.co.z == 10 for v in ob.data.vertices), 1)

    def test_wire_law_uses_length_and_closes_both_ends(self):
        ob = s3d.wire("bud", [(0, 0, 0), (0, 0, 2), (0, 0, 20)],
                      [(0, 0), (0.5, 6), (1, 0)])
        self.assert_solid(ob)
        ring = [v.co for v in ob.data.vertices if abs(v.co.z - 10) < 1e-6]
        self.assertAlmostEqual(max(v.xy.length for v in ring), 3, places=5)
        for z in (0, 20):
            self.assertEqual(sum(v.co.z == z for v in ob.data.vertices), 1)

    def test_a_short_end_interval_still_gets_a_dome(self):
        ob = s3d.wire("short", [(0, 0, 0), (0, 0, 100)], [(0, 0), (0.00001, 2), (1, 2)])
        self.assert_solid(ob)
        self.assertGreater(len({v.co.z for v in ob.data.vertices if v.co.z < 0.001}), 8)

    def test_sweep_pair_and_twist_laws(self):
        ob = s3d.sweep("blade", s3d.rect(4, 2), [(0, 0, 0), (0, 0, 20)],
                        scale=[(0, (1, 1)), (0.5, (2, 3)), (1, (0, 0))],
                        twist=[(0, 0), (0.5, 90), (1, 120)])
        self.assert_solid(ob)
        ring = [v.co for v in ob.data.vertices if abs(v.co.z - 10) < 1e-6]
        self.assertAlmostEqual(max(v.x for v in ring), 3, places=5)
        self.assertAlmostEqual(max(v.y for v in ring), 4, places=5)

    def test_soft_loft_ends(self):
        for follow in (False, True):
            ob = s3d.loft("bud", s3d.station(0, 0, 0), s3d.station(10, 12, 8),
                          s3d.station(25, 0, 0), follow=follow)
            self.assert_solid(ob)
            self.assertEqual(sum(v.co.z == 0 for v in ob.data.vertices), 1)
            self.assertEqual(sum(v.co.z == 25 for v in ob.data.vertices), 1)
        self.assert_solid(s3d.loft("cap", s3d.at(s3d.circle(0), z=0), s3d.station(10, 12, 8)))

    def test_phyllotaxis(self):
        frames = s3d.phyllotaxis(20, 40)
        self.assertEqual(len(frames), 20)
        for k, f in enumerate(frames):
            self.assertAlmostEqual(f.origin.xy.length, 20 * math.sqrt((k+0.5)/20), places=5)
            self.assertEqual(tuple(f.z), (0, 0, 1))
        for k, f in enumerate(s3d.phyllotaxis(20, 40, h=60, on=s3d.Frame((0, 0, 5)))):
            self.assertAlmostEqual(f.origin.z, 5+60*(k+0.5)/20, places=5)
            self.assertAlmostEqual(f.origin.xy.length, 20, places=5)
            self.assertAlmostEqual(f.z.z, 0)
        self.assertEqual(len(s3d.phyllotaxis(0, 20)), 0)

    def test_branches(self):
        axes = s3d.branches(100, 10, levels=2, children=2, jitter=0.2, seed=13)
        again = s3d.branches(100, 10, levels=2, children=2, jitter=0.2, seed=13)
        self.assertEqual(len(axes), 7)
        self.assertEqual(len(axes.tips), 4)
        self.assertEqual([a.name for a in axes], ["root", "root/0", "root/0/0", "root/0/1", "root/1", "root/1/0", "root/1/1"])
        self.assertIs(axes[2].parent, axes[1])
        self.assertEqual([a.path.points for a in axes], [a.path.points for a in again])
        with self.assertRaisesRegex(ValueError, "4096"):
            s3d.branches(10, 1, levels=10, children=3)
        for kw in ({"jitter": 2}, {"attach": (0.9, 0.1)}, {"children": -1}):
            with self.assertRaises(ValueError):
                s3d.branches(10, 1, **kw)

    def test_size_law_rejects_nonmanifold_poles(self):
        path = [(0, 0, 0), (0, 0, 10)]
        for law, message in (([(0, 2), (0.5, 0), (1, 2)], "interior zeros"),
                             ([(0, 0), (1, 0)], "all-zero")):
            with self.subTest(law=law), self.assertRaisesRegex(ValueError, message):
                s3d.wire("bad", path, law)
            with self.assertRaisesRegex(ValueError, message):
                s3d.sweep("bad", s3d.circle(4), path, scale=law)
        for law in ([(0, (1, 0)), (1, (1, 1))], [(0, (1, 1)), (1, (0, 1))],
                    [(0, (1, 1)), (0.5, (0, 0)), (1, (1, 1))],
                    [(0, (0, 0)), (1, (0, 0))]):
            with self.subTest(law=law), self.assertRaisesRegex(ValueError, "zero"):
                s3d.sweep("bad", s3d.circle(4), path, scale=law)
        for scale in ([(0, 0), (1, 1)], [(0, 1), (1, 0)]):
            with self.assertRaisesRegex(ValueError, "without holes"):
                s3d.sweep("bad", s3d.circle(4) - s3d.circle(2), path, scale=scale)
        self.assert_solid(s3d.sweep("tube", s3d.circle(4) - s3d.circle(2), path,
                                   scale=[(0, 1), (1, 2)]))

    def test_closed_paths_refuse_laws(self):
        for law in ([(0, 1), (1, 2)], [(0, 1), (1, 1)], [(0, 0), (1, 1)]):
            with self.assertRaisesRegex(ValueError, "closed paths"):
                s3d.wire("bad", s3d.circle(40), law)
        for kw in ({"scale": [(0, 1), (1, 1)]}, {"twist": [(0, 0), (1, 360)]}):
            with self.assertRaisesRegex(ValueError, "closed paths"):
                s3d.sweep("bad", s3d.circle(4), s3d.circle(40), **kw)
        # Numeric calls keep their existing meaning.
        self.assert_solid(s3d.sweep("ring", s3d.circle(4), s3d.circle(40)))

    def test_rounded_laws_match_the_pchip_tangent(self):
        from sand3d.solids import _soft_scale
        for rows in ([(0, 0), (0.3, 2), (1, 4)], [(0, 0), (0.3, 1), (1, 20)],
                     [(0, 4), (0.7, 2), (1, 0)],
                     [(0, (0, 0)), (0.3, (2, 1)), (1, (4, 3))]):
            law = _core.Law(rows)
            end = 0 if all(v == 0 for v in law.values[0]) else -1
            knot = 1 if end == 0 else -2
            u = law.u[knot]
            epsilon = (law.u[knot] - law.u[end]) * 1e-5
            cap = _soft_scale(law, u - epsilon)
            raw = law(u)
            cap, raw = (cap, raw) if law.pair else ((cap,), (raw,))
            for k, (a, b) in enumerate(zip(cap, raw)):
                self.assertAlmostEqual((b - a) / epsilon, law.slopes[k][knot], delta=0.002)
            # A rounded pole has size proportional to sqrt(distance), even
            # when PCHIP's own endpoint derivative vanishes.
            a = _soft_scale(law, law.u[end] + epsilon)
            b = _soft_scale(law, law.u[end] + 4 * epsilon)
            a, b = (a, b) if law.pair else ((a,), (b,))
            for x, y in zip(a, b):
                self.assertAlmostEqual(y / x, 2, delta=0.002)
        ob = s3d.sweep("leaf", s3d.at(s3d.ellipse(4, 2), x=0.3, y=0.15),
                        [(0, 0, 0), (0, 0, 20)],
                        scale=[(0, (0, 0)), (0.3, (1, 1)), (1, (2, 1.4))],
                        twist=[(0, 10), (0.3, 20), (1, 35)])
        self.assert_solid(ob)

    def test_loft_domes_join_nonconstant_offset_sections_smoothly(self):
        from mathutils import Vector
        for follow, reverse in ((False, False), (False, True), (True, False), (True, True)):
            sections = [s3d.station(0, 0, 0), s3d.station(10, 8, 6, x=1),
                        s3d.station(25, 18, 10, x=2.5), s3d.station(40, 12, 8, x=4)]
            ob = s3d.loft("bud", *(sections[::-1] if reverse else sections), follow=follow)
            self.assert_solid(ob)
            bm = bmesh.new()
            bm.from_mesh(ob.data)
            bm.normal_update()
            centre = Vector((1, 0, 10))
            normal = Vector((0.1, 0, 1) if follow else (0, 0, 1)).normalized()
            joins = [e for e in bm.edges if all(abs((v.co - centre).dot(normal)) < 1e-4 for v in e.verts)]
            self.assertGreater(len(joins), 20)
            # Adjacent faces on opposite sides of the first full section have
            # matching limiting normals, despite changing size and centre.
            self.assertLess(max(e.link_faces[0].normal.angle(e.link_faces[1].normal) for e in joins), 0.025)
            bm.free()

    def test_loft_zero_section_contributes_position_not_orientation(self):
        from harness import digest
        from mathutils import Vector
        for follow, reverse in ((False, False), (False, True), (True, False), (True, True)):
            records = []
            for turn in (0, 70):
                s3d.empty_scene()
                sections = [s3d.at(s3d.circle(0), ry=turn, rz=turn),
                            s3d.at(s3d.ellipse(8, 6), x=1, z=10, ry=20),
                            s3d.at(s3d.ellipse(12, 8), x=2.5, z=25, ry=15)]
                ob = s3d.loft("bud", *(sections[::-1] if reverse else sections), follow=follow)
                self.assert_solid(ob)
                records.append(digest(ob))
                bm = bmesh.new()
                bm.from_mesh(ob.data)
                bm.normal_update()
                pole = min(bm.verts, key=lambda v: v.co.length)
                normal = Vector((0.1, 0, 1)) if follow else Vector((math.sin(math.radians(20)), 0, math.cos(math.radians(20))))
                normal.normalize()
                self.assertTrue(all(abs(f.normal.dot(normal)) > 0.96 for f in pole.link_faces))
                bm.free()
            self.assertEqual(records[0], records[1])

    def test_branches_on_is_applied_once_and_each_parent_restarts_azimuth(self):
        from mathutils import Vector
        base = s3d.Frame((12, -8, 5)).turn(rx=25, ry=-40, rz=15)
        local = s3d.branches(40, 8, levels=2, children=2, diameter_ratio=0.5, tip_ratio=0.1)
        placed = s3d.branches(40, 8, levels=2, children=2, diameter_ratio=0.5, tip_ratio=0.1, on=base)
        for a, b in zip(local, placed):
            for p, q in zip(a.path.points, b.path.points):
                self.assertLess((base.matrix @ Vector(p) - Vector(q)).length, 1e-5)
            self.assertEqual(a.d, b.d)
            if b.parent:
                self.assertEqual(b.d[0][1], b.parent.d[0][1] * 0.5)
        for a, b in zip(local.tips, placed.tips):
            self.assertLess((base.matrix @ a.origin - b.origin).length, 1e-5)
            self.assertLess((base.matrix.to_3x3() @ a.z - b.z).length, 1e-6)
        self.assertEqual(len(placed.tips), 4)
        # First child at each generation is in its parent's local XZ plane.
        regular = s3d.branches(40, 8, levels=2, children=2, azimuth=90)
        for name in ("root/0", "root/0/0"):
            a = next(a for a in regular if a.name == name)
            self.assertAlmostEqual(a.path.points[0][1], 0, places=6)
            self.assertAlmostEqual(a.path.points[1][1], 0, places=6)
        first = s3d.wire("stem", placed[0].path, placed[0].d)
        self.assert_solid(first)
        distances = [(v.co - base.origin).dot(base.z) for v in first.data.vertices]
        self.assertAlmostEqual(min(distances), 0, delta=1e-5)
        self.assertAlmostEqual(max(distances), 40, delta=1e-5)
        parent = s3d.Frame().turn(rz=90).turn(ry=45)
        child = next(a for a in regular if a.name == "root/1/0")
        direction = (Vector(child.path.points[1]) - Vector(child.path.points[0])).normalized()
        expected = (parent.x + parent.z).normalized()
        self.assertLess((direction - expected).length, 1e-6)

    def test_loft_pole_keeps_section_indices_on_uneven_samples(self):
        from mathutils import Vector
        for follow in (False, True):
            for reverse in (False, True):
                sections = [s3d.station(0, 150, 80), s3d.station(85, 150, 80, x=15),
                            s3d.station(170, 0, 0, x=30)]
                ob = s3d.loft("tip", *(sections[::-1] if reverse else sections), follow=follow)
                self.assert_solid(ob)
                pole = Vector((30, 0, 170))
                self.assertEqual(sum((v.co - pole).length < 1e-4 for v in ob.data.vertices), 1)

    def test_fast_diameter_law_keeps_rings_in_path_order(self):
        from mathutils import Vector
        path = s3d.spline([(34, 0, 0), (0, 0, 562), (0, 0, 1124)])
        ob = s3d.wire("probe", path,
                      [(0, 0), (0.0227, 154), (0.2227, 516), (0.6317, 860), (0.925, 553), (1, 0)])
        self.assert_solid(ob)
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        start = Vector(path.points[0])
        ring = {min(bm.verts, key=lambda v: (v.co - start).length)}
        seen, count = set(ring), 1
        # Breadth-first edge layers recover the rings independently of mesh
        # vertex numbering. No longitudinal edge may run behind its old ring.
        while ring:
            next_ring = {e.other_vert(v) for v in ring for e in v.link_edges} - seen
            if not next_ring:
                break
            before = sum((v.co for v in ring), Vector()) / len(ring)
            after = sum((v.co for v in next_ring), Vector()) / len(next_ring)
            self.assertGreaterEqual(after.z, before.z - 1e-4)
            self.assertGreater((after - before).length, 1e-6)
            forward = (after - before).normalized()
            advances = [(e.other_vert(v).co - v.co).dot(forward) for v in ring
                        for e in v.link_edges if e.other_vert(v) in next_ring]
            self.assertTrue(advances)
            self.assertGreaterEqual(min(advances), -1e-4)
            seen.update(next_ring)
            ring, count = next_ring, count + 1
        self.assertEqual(len(seen), len(bm.verts))
        self.assertGreater(count, len(path.points))
        bm.free()

    def test_curved_branch_law_coincident_stations(self):
        # Rotated and translated to expose float32 position cancellation at
        # near-coincident uniform samples, original stations and law knots.
        frame = s3d.Frame((66.73914337158203, -18.237369537353516, 881.7660522460938),
                          normal=(-.0601862370967865, .7573658227920532, .6502113342285156),
                          up=(-.9864587187767029, -.14469122886657715, .07722558081150055))
        axis = s3d.branches(450.2895219616927, 91.2, levels=1, children=5,
                            attach=(.38, .88), angle=55, length_ratio=.5, diameter_ratio=.48,
                            wander=10, droop=-8, jitter=.45, seed=11, on=frame)[5]
        ob = s3d.sweep("branch", s3d.polygon(10, axis.d[0][1]), axis.path,
                       scale=[(0, 1), (.9, .65), (1, .12)])
        self.assert_solid(ob)
        from mathutils.bvhtree import BVHTree
        ob.data.calc_loop_triangles()
        triangles = [tuple(t.vertices) for t in ob.data.loop_triangles]
        tree = BVHTree.FromPolygons([v.co for v in ob.data.vertices], triangles,
                                   all_triangles=True)
        collisions = [(a, b) for a, b in tree.overlap(tree)
                      if a < b and not set(triangles[a]).intersection(triangles[b])]
        self.assertEqual(collisions, [], "nonadjacent surface triangles intersect")
        self.assert_solid(s3d.wire("round_branch", axis.path,
                                   [(0, axis.d[0][1]), (.9, axis.d[0][1] * .65),
                                    (1, axis.d[0][1] * .12)]))

    def test_law_rings_refuse_a_path_too_tight_for_the_size(self):
        with self.assertRaisesRegex(ValueError, "rings cross"):
            s3d.wire("fold", s3d.arc(r=1, start=0, end=90), [(0, 10), (1, 10)])

    def test_short_pole_interval_cannot_expand_the_body(self):
        for follow in (False, True):
            for reverse in (False, True):
                for pole in (-20, -60, -120, -190, -320):
                    with self.subTest(follow=follow, reverse=reverse, pole=pole):
                        sections = [s3d.station(pole, 0, 0), s3d.station(0, 640, 380),
                                    s3d.station(165, 620, 430), s3d.station(400, 500, 390)]
                        ob = s3d.loft("bounded", *(sections[::-1] if reverse else sections), follow=follow)
                        self.assert_solid(ob)
                        points = [v.co for v in ob.data.vertices]
                        self.assertLessEqual(max(p.x for p in points) - min(p.x for p in points), 640.05)
                        self.assertLessEqual(max(p.y for p in points) - min(p.y for p in points), 430.05)
                        self.assertGreaterEqual(min(p.z for p in points), pole - 0.05)
                        self.assertLessEqual(max(p.z for p in points), 400.05)
                        for a, b, width in ((pole, 0, 640), (0, 165, 640), (165, 400, 620)):
                            span = [p.x for p in points if a - 1e-4 <= p.z <= b + 1e-4]
                            self.assertLessEqual(max(span) - min(span), width + 0.05)

    def test_plain_pair_is_a_linear_anisotropic_end_scale(self):
        for scale in ((0.9, 0.8), [0.9, 0.8]):
            ob = s3d.sweep("pair", s3d.rect(10, 6), [(0, 0, 0), (0, 0, 5), (0, 0, 10)], scale=scale)
            self.assert_solid(ob)
            for z, width, depth in ((0, 10, 6), (5, 9.5, 5.4), (10, 9, 4.8)):
                ring = [v.co for v in ob.data.vertices if abs(v.co.z - z) < 1e-6]
                self.assertAlmostEqual(max(p.x for p in ring) - min(p.x for p in ring), width, places=5)
                self.assertAlmostEqual(max(p.y for p in ring) - min(p.y for p in ring), depth, places=5)
        ob = s3d.sweep("twisted_pair", s3d.rect(10, 6), [(0, 0, 0), (0, 0, 10)],
                        scale=(0.9, 0.8), twist=[(0, 0), (1, 90)])
        self.assert_solid(ob)
        end = [v.co for v in ob.data.vertices if abs(v.co.z - 10) < 1e-6]
        self.assertAlmostEqual(max(p.x for p in end) - min(p.x for p in end), 4.8, places=5)
        self.assertAlmostEqual(max(p.y for p in end) - min(p.y for p in end), 9, places=5)
        for scale in ((0, 1), (float("nan"), 1), (-1, 1)):
            with self.assertRaisesRegex(ValueError, "positive finite ratios"):
                s3d.sweep("bad_pair", s3d.rect(10, 6), [(0, 0, 0), (0, 0, 10)], scale=scale)

    def test_crossing_diagnostic_locates_and_sizes_the_correction(self):
        import re
        with self.assertRaises(ValueError) as caught:
            s3d.wire("wide", s3d.arc(r=1, start=0, end=90), [(0, 10), (1, 10)])
        message = str(caught.exception)
        u = float(re.search(r"u=([0-9.eE+-]+)", message)[1])
        radius = float(re.search(r"section radius <= ([0-9.eE+-]+) mm", message)[1])
        factor = float(re.search(r"uniform size factor <= ([0-9.eE+-]+)", message)[1])
        self.assertTrue(0 <= u <= 1)
        self.assertTrue(0 < radius < 5)
        self.assertTrue(0 < factor < 1)
        # The suggested single correction must make the complete path valid.
        self.assert_solid(s3d.wire("corrected", s3d.arc(r=1, start=0, end=90),
                                   [(0, 10 * factor), (1, 10 * factor)]))

    def wire_rings(self, ob):
        """Recover cross-sections from the start cap, without vertex-number assumptions."""
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        layer = bm.faces.layers.bool.get(_core.FACE_TAG + "start")
        self.assertIsNotNone(layer)
        ring = {v for f in bm.faces if f[layer] for v in f.verts}
        seen, rings = set(ring), []
        while ring:
            rings.append([v.co.copy() for v in ring])
            ring = {e.other_vert(v) for v in ring for e in v.link_edges} - seen
            seen.update(ring)
        self.assertEqual(len(seen), len(bm.verts))
        bm.free()
        return rings

    def ring_centre(self, ring):
        from mathutils import Vector
        return Vector(tuple(math.fsum(p[k] for p in ring) / len(ring) for k in range(3)))

    def test_shrinking_law_fits_the_same_fillet_as_a_plain_wire(self):
        path = [(31, -54, 5), (44.5, -76, 27), (46.2, -97, 30.8), (47, -123, 29)]
        plain = s3d.wire("plain", path, 24, fillet=14.4)
        self.assert_solid(plain)
        for law in ([(0, 24), (0.4, 21), (0.7, 19.4), (1, 0)], [(0, 24), (1, 24)]):
            ob = s3d.wire("law", path, law, fillet=14.4)
            self.assert_solid(ob)
            previous = 12.0
            for ring in self.wire_rings(ob):
                centre = self.ring_centre(ring)
                radii = [(p - centre).length for p in ring]
                radius = math.fsum(radii) / len(radii)
                self.assertLessEqual(max(radii) - min(radii), 1e-4)
                self.assertLessEqual(radius, previous + 1e-4)
                previous = radius
            self.assertAlmostEqual(previous, law[-1][1] / 2, delta=1e-4)

    def test_fillet_radius_follows_the_law_in_true_arc_length(self):
        from mathutils import Vector
        bend = 14.4
        straight = 40 - bend
        arc_end = straight + bend * math.pi / 2
        total = 2 * straight + bend * math.pi / 2
        law = [(0, 12), (0.4, 10.5), (0.7, 9.7), (1, 9)]
        expected = _core.Law(law)
        ob = s3d.wire("bend", [(0, 0, 0), (0, 0, 40), (40, 0, 40)], law, fillet=bend)
        self.assert_solid(ob)
        records = []
        for ring in self.wire_rings(ob):
            centre = self.ring_centre(ring)
            if abs(centre.x) < 1e-4 and centre.z <= straight + 1e-4:
                distance = centre.z
                point, tangent = Vector((0, 0, distance)), Vector((0, 0, 1))
            elif abs(centre.z - 40) < 1e-4 and centre.x >= bend - 1e-4:
                distance = arc_end + centre.x - bend
                point, tangent = Vector((centre.x, 0, 40)), Vector((1, 0, 0))
            else:
                angle = math.atan2(centre.z - straight, bend - centre.x)
                distance = straight + bend * angle
                point = Vector((bend * (1 - math.cos(angle)), 0, straight + bend * math.sin(angle)))
                tangent = Vector((math.sin(angle), 0, math.cos(angle)))
            self.assertLess((centre - point).length, 4e-5)
            radius = expected(distance / total) / 2
            for p in ring:
                self.assertAlmostEqual((p - point).length, radius, delta=4e-5)
                self.assertAlmostEqual((p - point).dot(tangent), 0, delta=4e-5)
            measured = math.fsum((p - point).length for p in ring) / len(ring)
            records.append((distance, measured))
        # The scalar radius and its derivative agree across both law knots
        # and line/circle joints, not just at the ends of the path.
        for knot in (straight, arc_end, total * 0.4, total * 0.7):
            i = min(range(len(records)), key=lambda j: abs(records[j][0] - knot))
            x0, y0 = records[i]
            self.assertAlmostEqual(x0, knot, delta=4e-5)
            slopes = []
            for a, b in ((i - 1, i - 2), (i + 1, i + 2)):
                x1, y1 = records[a][0] - x0, records[a][1] - y0
                x2, y2 = records[b][0] - x0, records[b][1] - y0
                slopes.append((y1*x2*x2 - y2*x1*x1) / (x1*x2*(x2-x1)))
            self.assertAlmostEqual(slopes[0], slopes[1], delta=0.002)
