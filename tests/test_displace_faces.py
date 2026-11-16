"""Bounded, construction-named displacement patches."""
import subprocess
import sys
import unittest

import bpy  # noqa: F401 — provides bmesh
import bmesh
import numpy as np
import sand3d as s3d


def mesh(ob):
    return ([tuple(v.co) for v in ob.data.vertices],
            [tuple(p.vertices) for p in ob.data.polygons],
            [(a.name, [d.value for d in a.data]) for a in ob.data.attributes
             if a.name.startswith('s3d_')])


def tagged(ob, name):
    return [p for p, d in zip(ob.data.polygons, ob.data.attributes['s3d_face:' + name].data) if d.value]


class DisplaceFaces(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()

    def test_none_is_bitwise_legacy(self):
        ob = s3d.box('sample', 12, 10, 3)
        s3d.displace(ob, .5, 5)
        expected = mesh(ob)
        s3d.empty_scene()
        ob = s3d.box('sample', 12, 10, 3)
        s3d.displace(ob, .5, 5, faces=None)
        self.assertEqual(mesh(ob), expected)

    def test_only_selected_faces_refine_and_boundary_is_fixed(self):
        ob = s3d.box('sample', 20, 16, 4)
        original = {tuple(v.co) for v in ob.data.vertices}
        s3d.displace(ob, 2, 4, faces='top', noise=lambda x,y,z: np.ones_like(x), direction='+Z')
        self.assertGreater(max(v.co.z for v in ob.data.vertices), 5.9)
        self.assertEqual(len(ob.data.polygons) - len(tagged(ob, 'top')), 5)
        for p in ob.data.polygons:
            if p not in tagged(ob, 'top'):
                for i in p.vertices:
                    v = ob.data.vertices[i].co
                    self.assertTrue(v.z in (0, 4))
        self.assertTrue(original <= {tuple(v.co) for v in ob.data.vertices})
        bm = bmesh.new(); bm.from_mesh(ob.data)
        self.assertTrue(all(e.is_manifold for e in bm.edges))
        bm.free()
        self.assertFalse(any(a.name.startswith('.displace') for a in ob.data.attributes))

    def test_existing_vertices_only_and_fade(self):
        ob = s3d.box('sample', 20, 20, 4)
        s3d.displace(ob, 0, 4, faces='top')
        before = [tuple(v.co) for v in ob.data.vertices]
        polygons = [tuple(p.vertices) for p in ob.data.polygons]
        s3d.displace(ob, 2, 4, faces=['top'], step=0,
                     noise=lambda x,y,z: np.ones_like(x), direction='+Z', fade=(0, 8))
        self.assertEqual(polygons, [tuple(p.vertices) for p in ob.data.polygons])
        for a, v in zip(before, ob.data.vertices):
            x,y,z = a
            t = min((10-max(abs(x),abs(y)))/4, 1)
            expected = t*t*(3-2*t) if z == 4 else 0
            self.assertAlmostEqual(v.co.z-z, expected, places=5)
            self.assertEqual(tuple(v.co)[:2], a[:2])

    def test_direction_matches_face_and_names_union(self):
        for faces in ('top', '+Z', ['top', 'sample.top']):
            s3d.empty_scene()
            ob = s3d.box('sample', 10, 10, 3)
            s3d.displace(ob, 1, 3, faces=faces, noise=s3d.waves(5), direction='+Z')
            if faces == 'top':
                expected = mesh(ob)
            else:
                self.assertEqual(mesh(ob), expected)

    def test_empty_selection_and_errors_do_not_change_mesh(self):
        ob = s3d.box('sample', 10, 10, 3)
        before = mesh(ob)
        s3d.displace(ob, 1, 2, faces=[])
        self.assertEqual(mesh(ob), before)
        for invalid in ('missing', ['top', 'missing']):
            with self.assertRaisesRegex(ValueError, 'top') as caught:
                s3d.displace(ob, 1, 2, faces=invalid)
            self.assertIn('missing', str(caught.exception))
            self.assertIn('bottom', str(caught.exception))
            self.assertEqual(mesh(ob), before)
        for invalid in (42, [None], {'top'}):
            with self.assertRaises(TypeError):
                s3d.displace(ob, 1, 2, faces=invalid)

    def test_fill_waves_keep_all_submerged_vertices(self):
        ground = s3d.box('terrain', 40, 30, 12)
        s3d.cut(ground, s3d.at(s3d.cylinder('pocket', 24, 15), z=2))
        ob = s3d.fill('water', ground, 10)
        original = {tuple(v.co) for v in ob.data.vertices}
        side_count = len(tagged(ob, 'side'))
        level = max(v.co.z for v in ob.data.vertices)
        s3d.displace(ob, .7, 4, faces='top', noise=s3d.waves(8), direction='+Z')
        self.assertTrue(original <= {tuple(v.co) for v in ob.data.vertices})
        self.assertEqual(len(tagged(ob, 'side')), side_count)
        self.assertGreater(max(v.co.z for v in ob.data.vertices), level + .1)
        for p in tagged(ob, 'side'):
            self.assertLessEqual(max(ob.data.vertices[i].co.z for i in p.vertices), level)

    def test_path_and_callable_colours_survive(self):
        from sand3d import materials
        from sand3d.edit import _path_coordinates
        ob = s3d.cylinder('sample', 20, 6)
        s3d.material(ob, 'plastic', color=lambda x,y,z,n,u: (u, .2, .3))
        tags = {a.name for a in ob.data.attributes if a.name.startswith('s3d_')}
        s3d.displace(ob, .3, 4, faces='top', coords='path',
                     noise=lambda s,a,r: np.cos(np.radians(a)), direction='+Z')
        self.assertTrue(tags <= {a.name for a in ob.data.attributes})
        bm = bmesh.new(); bm.from_mesh(ob.data)
        self.assertTrue(np.all(np.isfinite(_path_coordinates(bm))))
        bm.free()
        self.assertEqual(len(materials.face_colors(ob)), len(ob.data.polygons))

    def test_units_and_normal_radial_directions(self):
        def build(unit, factor, direction):
            s3d.empty_scene(); s3d.units(unit)
            ob = s3d.box('sample', 20/factor, 16/factor, 4/factor)
            s3d.displace(ob, .5/factor, 4/factor, faces='top', direction=direction)
            return np.array([tuple(v.co) for v in ob.data.vertices])*factor
        for direction in ('normal', 'radial'):
            np.testing.assert_allclose(build('mm', 1, direction), build('cm', 10, direction), atol=2e-5)

    def test_two_fresh_processes(self):
        code = '''import hashlib, os
import sand3d as s3d
ob = s3d.box('sample', 20, 16, 4)
s3d.displace(ob, .8, 4, faces='top', noise=s3d.waves(6), direction='+Z')
print(hashlib.sha256(repr(([tuple(v.co) for v in ob.data.vertices], [tuple(p.vertices) for p in ob.data.polygons], [(a.name, [d.value for d in a.data]) for a in ob.data.attributes if a.name.startswith('s3d_')])).encode()).hexdigest(), flush=True)
os._exit(0)
'''
        a, b = [subprocess.check_output([sys.executable, '-c', code]) for _ in range(2)]
        self.assertEqual(a.splitlines()[-1], b.splitlines()[-1])
