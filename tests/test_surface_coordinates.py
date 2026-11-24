"""Persistent construction labels and seating without a skeleton."""
import unittest
import math
import sys
import warnings
import bpy
import bmesh
from mathutils import Vector
from sand3d import _core
import sand3d as s3d
from sand3d import materials
from sand3d import edit
from sand3d._coordinates import face_u, NAMES
from harness import _object_digest

class Surfaces(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()

    def test_lengthwise_tangent_threshold_is_in_mm(self):
        def label(unit, k):
            s3d.empty_scene()
            s3d.units(unit)
            builder = _core.Builder('rows')
            try:
                centres = [Vector(), Vector((1e-8 * k, 0, 0))]
                rows = [[builder.vert(centre + Vector((0, 0, k)))] for centre in centres]
                builder.lengthwise(rows, [0., 1.], centres=centres)
                y = builder.bm.verts.layers.float['.s3d_y']
                return [row[0][y] / k for row in rows]
            finally:
                builder.bm.free()

        expected = label('mm', 1)
        self.assertEqual(expected, [1., 1.])
        for y in label('m', .001):
            self.assertAlmostEqual(y, expected[0])

    def test_missing_merge_coordinates_are_rejected(self):
        a = s3d.cylinder('a',4,12)
        s3d.material(a,'plastic',color=lambda x,y,z,n,u: (u,0,0))
        s3d.merge(a,s3d.at(s3d.box('b',2,2,2),x=20))
        with self.assertRaisesRegex(ValueError,'no lengthwise u'):
            materials.face_colors(a)

    def test_join_keeps_coordinates_and_first_function(self):
        a = s3d.cylinder('a',4,12)
        s3d.material(a,'plastic',color=lambda x,y,z,n,u: (u,0,0))
        s3d.join(a,s3d.at(s3d.cylinder('b',4,12),x=2))
        self.assertTrue(all(0 <= u <= 1 for u in face_u(a.data)))
        self.assertEqual(len(materials.face_colors(a)),len(a.data.polygons))

    def test_refine_false_keeps_topology_and_labels(self):
        ob = s3d.wire('strand',[(0,0,0),(0,0,10)],(4,2),rings=2)
        before = ([tuple(f.vertices) for f in ob.data.polygons],
                  [[d.value for d in ob.data.attributes[n].data] for n in NAMES])
        s3d.displace(ob,.1,1,step=0)
        self.assertEqual(before,([tuple(f.vertices) for f in ob.data.polygons],
                  [[d.value for d in ob.data.attributes[n].data] for n in NAMES]))

    def test_lay_height_and_reach(self):
        support = s3d.box('support',20,20,5)
        patch = s3d.box('patch',4,4,2)
        with edit.strict():
            with self.assertRaisesRegex(ValueError,'beyond reach'):
                s3d.lay(patch,support,reach=1)
        s3d.lay(patch,support,step=2)
        self.assertAlmostEqual(min(v.co.z for v in patch.data.vertices),5)
        self.assertAlmostEqual(max(v.co.z for v in patch.data.vertices),7,places=5)

    def test_lay_overhang_warns_and_keeps_nearest_point_geometry(self):
        carrier = s3d.box("carrier", 50, 50, 10)
        plate = s3d.at(s3d.box("plate", 100, 20, 2), z=30)
        with edit.strict(False), warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            line = sys._getframe().f_lineno + 1
            s3d.lay(plate, carrier, step=10)
        # Recorded on the original nearest-point fallback, including subdivision.
        self.assertEqual(_object_digest(plate),
                         "8467be86280a04ac8806d566af6af088ffa2d088e2db9c21d8e03659c0339e94")
        self.assertEqual(len(captured), 1)
        self.assertEqual((captured[0].filename, captured[0].lineno), (__file__, line))
        self.assertIs(captured[0].category, edit.LayWarning)
        self.assertRegex(str(captured[0].message), "plate.*miss.*carrier")

    def test_lay_strict_overhang_preserves_mesh(self):
        carrier = s3d.box("carrier", 10, 10, 2)
        patch = s3d.at(s3d.box("patch", 2, 2, 2), x=10)
        with edit.strict(), self.assertRaisesRegex(ValueError, "patch.*miss.*carrier"):
            s3d.lay(patch, carrier, step=1)
        self.assertEqual(len(patch.data.vertices), 8)

    def test_lay_reach_failure_is_atomic_for_nested_lists_and_subdivision(self):
        carrier = s3d.box("carrier", 10, 10, 2)
        a = s3d.box("A", 2, 2, 2)
        b = s3d.at(s3d.box("B", 2, 2, 2), z=40)
        lot = [a, (b,)]
        s3d.material(a, "oak")
        override = bpy.data.materials.new("override")
        a.data.materials.append(override)
        a.data.polygons[0].use_smooth = True
        meshes = a.data, b.data
        snapshot = [tuple(v.co) for part in (a, b) for v in part.data.vertices]
        with edit.strict(), self.assertRaisesRegex(ValueError, "B.*beyond reach"):
            s3d.lay(lot, carrier, reach=3, step=1)
        self.assertEqual(snapshot, [tuple(v.co) for part in (a, b) for v in part.data.vertices])
        with edit.strict(False), s3d.facets(6), self.assertRaisesRegex(ValueError, "B.*beyond reach"):
            s3d.lay(lot, carrier, reach=3, step=1)
        self.assertEqual(snapshot, [tuple(v.co) for part in (a, b) for v in part.data.vertices])
        self.assertEqual(meshes, (a.data, b.data))
        self.assertTrue(a.data.polygons[0].use_smooth)
        self.assertEqual(a.data.materials[1], override)

    def test_lay_empty_carrier_warns_and_leaves_patch_unchanged(self):
        carrier = s3d.tufts("vide", [], 1, 1)
        patch = s3d.box("patch", 2, 2, 2)
        with edit.strict(False), self.assertWarnsRegex(edit.LayWarning, "vide.*no faces"):
            self.assertIs(s3d.lay(patch, carrier, step=1), patch)
        self.assertEqual(len(patch.data.vertices), 8)
        with edit.strict(), self.assertRaisesRegex(ValueError, "vide.*no faces"):
            s3d.lay(patch, carrier, step=1)
        solid = s3d.box("solid", 10, 10, 5)
        s3d.lay(patch, [carrier, solid])
        self.assertAlmostEqual(min(v.co.z for v in patch.data.vertices), 5)

    def test_flat_tip_retains_end_section(self):
        ob = s3d.loft('flat',s3d.station(0,4,2),s3d.station(10,0,0),tip='flat')
        self.assertGreater(sum(f.area for f in ob.data.polygons if f.center.z > 9.99),1)

    def test_bend_and_branches_follow_facets(self):
        s3d.facets(8)
        ob = s3d.bend(s3d.box('bend',2,2,20),90,axis='+Z',toward='+X')
        self.assertLess(len(ob.data.vertices),50)
        axes = s3d.branches(100,2,levels=1,children=1,wander=20,seed=3)
        self.assertLess(len(axes[0].path.points),97)

    def test_refine_seats_the_middle_of_a_long_face(self):
            ball = s3d.at(s3d.sphere('ball', 200), z=-200)
            piece = s3d.extrude('strap', s3d.rect(120, 12), 2)
            coarse = len(piece.data.vertices)
            s3d.lay(piece, ball, step=8, reach=30)
            self.assertGreater(len(piece.data.vertices), coarse)
            from mathutils.bvhtree import BVHTree
            tree = BVHTree.FromPolygons([_core.world(ball) @ v.co for v in ball.data.vertices],
                                       [list(p.vertices) for p in ball.data.polygons])
            for v in piece.data.vertices:
                q, _, _, distance = tree.find_nearest(v.co)
                self.assertLess(distance, 2.01)
            # Refinement preserves the original two planes before seating.
            heights = [round(v.co.z-tree.ray_cast(Vector((v.co.x,v.co.y,100)), (0,0,-1))[0].z, 3)
                       for v in piece.data.vertices]
            self.assertTrue(all(0 <= h <= 2 for h in heights))
            flat = s3d.at(s3d.box('flat', 200, 200, 10), z=-10)
            patch = s3d.extrude('patch', s3d.rect(100, 40), 2)
            s3d.lay(patch, flat, step=8)
            self.assertTrue(all((patch.data.vertices[e.vertices[0]].co-
                                 patch.data.vertices[e.vertices[1]].co).length <= 8.0001 for e in patch.data.edges))

    def test_reach_rejects_a_remote_surface_without_moving_the_piece(self):
            ball = s3d.at(s3d.sphere('ball', 200), z=-200)
            piece = s3d.at(s3d.extrude('patch', s3d.rect(20,20), 2), z=50)
            before = [tuple(v.co) for v in piece.data.vertices]
            with edit.strict(), self.assertRaisesRegex(ValueError, "patch.*distance.*reach"):
                s3d.lay(piece, ball, reach=10)
            self.assertEqual(before, [tuple(v.co) for v in piece.data.vertices])
            for kwargs in ({'reach':-1}, {'refine':-1}, {'reach':math.nan}, {'refine':True}):
                with self.assertRaises((ValueError, TypeError)):
                    s3d.lay(piece, ball, **kwargs)

    def test_common_translation_and_rotation_leave_the_local_result_unchanged(self):
            from mathutils import Matrix, Euler
            def build(move, saddle=False):
                s3d.empty_scene()
                s3d.facets(12)
                if saddle:
                    bm = bmesh.new()
                    outline = [(-100,-100,-30), (60,-100,30), (100,-20,-30),
                               (100,100,30), (-60,100,-30), (-100,20,30)]
                    bm.faces.new([bm.verts.new(p) for p in outline])
                    ball = _core.new_object('saddle', bm)
                else:
                    ball = s3d.at(s3d.sphere('ball', 200), z=-200)
                piece = s3d.extrude('patch', s3d.rect(100,30), 2)
                for ob in (ball, piece):
                    ob.matrix_world = move @ _core.world(ob)
                s3d.lay(piece, ball, step=0 if saddle else 15)
                return [v.co.copy() for v in piece.data.vertices]
            baseline = build(Matrix.Identity(4))
            move = Matrix.Translation((513, -237, 851)) @ Euler((.3, .7, .5)).to_matrix().to_4x4()
            moved = build(move)
            self.assertEqual(len(baseline), len(moved))
            self.assertLess(max((a-b).length for a,b in zip(baseline,moved)), .001)
            import random
            rng = random.Random(16)
            move = Matrix.Translation((513, -237, 851)) @ Euler(tuple(rng.uniform(-3,3) for _ in range(3))).to_matrix().to_4x4()
            baseline, moved = build(Matrix.Identity(4), True), build(move, True)
            self.assertLess(max((a-b).length for a,b in zip(baseline,moved)), .001)

    def test_urdf_uses_the_function_mean(self):
        from sand3d.urdf import _colour
        ob = s3d.box('colour',2,2,2)
        s3d.material(ob,'plastic',color=lambda x,y,z: '#ff0000' if z>1 else '#0000ff')
        expected = materials.look(materials.mean_tag(ob))['color']
        self.assertEqual(tuple(_colour(ob)[1][:3]),tuple(expected))

    def test_boolean_tessellation_has_no_duplicate_triangles(self):
        s3d.facets(10)
        shell = s3d.loft('shell', *[s3d.station(z,w,d,y=y) for z,w,d,y in
                          ((83,14,18,-1),(88,16,21,-1),(95,12,17,1),(100,0,0,4))],
                          tip='sharp',rings=4)
        tool = s3d.loft('tool', *[s3d.station(z,w,30,y=-12) for z,w in
                                ((80,12),(92,12),(96,.01))])
        s3d.cut(shell,tool)
        shell.data.calc_loop_triangles()
        keys = [tuple(sorted(t.vertices)) for t in shell.data.loop_triangles]
        self.assertEqual(len(keys),len(set(keys)))
