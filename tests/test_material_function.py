"""Local rest-space face colour functions."""
import unittest
import numpy as np
import sand3d as s3d
from sand3d import materials


class MaterialFunction(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()
        s3d.facets(8)

    def test_lazy_inheritance_copy_and_edits(self):
        calls = []
        def color(x, y, z, n):
            calls.append((x, y, z, n))
            return '#ffffff' if z > 10 else '#000000'
        a = s3d.box('a', 20, 20, 20)
        b = s3d.box('b', 10, 10, 10)
        s3d.material(s3d.group('g', a, b), 'plastic', color=color)
        s3d.material(b, 'brass')
        self.assertEqual(calls, [])
        self.assertIsNone(materials.face_colors(b))
        c = s3d.copy(a)
        self.assertEqual(materials.face_colors(a), materials.face_colors(c))
        calls.clear()
        s3d.hole(a, 4)
        s3d.twist(a, 30, axis='+Z')
        self.assertEqual(calls, [])
        colors = materials.face_colors(a)
        self.assertEqual(len(calls), len(a.data.polygons) + 1)
        self.assertEqual(len(colors), len(calls) - 1)

    def test_export_evaluates_once(self):
        from unittest.mock import patch
        a = s3d.box('a', 20, 20, 20)
        s3d.material(a, 'plastic', color=lambda x,y,z: '#336699')
        with patch.object(materials, 'face_colors', wraps=materials.face_colors) as evaluate:
            with materials.exporting(a):
                self.assertEqual(evaluate.call_count, 1)

    def test_corner_colours(self):
        a = s3d.cone('mixed', 20, 50)
        colors = [materials._linear('#336699' if i % 2 else '#ff0000')
                  for i in range(len(a.data.polygons))]
        materials.put_colors(a.data, colors)
        for face, color in zip(a.data.polygons, colors):
            for i in face.loop_indices:
                for actual, expected in zip(a.data.color_attributes['Colour'].data[i].color, color):
                    self.assertAlmostEqual(actual, expected, places=7)

    def test_face_u_matches_scalar_sum(self):
        from sand3d._coordinates import face_u, NAMES
        a = s3d.cone('a', 20, 50)
        mesh = a.data
        s, e = (mesh.attributes[n] for n in (NAMES[0], NAMES[-1]))
        def reference():
            return [sum(s.data[i].value/e.data[i].value if e.data[i].value else float('nan')
                        for i in f.vertices)/len(f.vertices) for f in mesh.polygons]
        self.assertEqual(face_u(mesh), reference())
        rng = np.random.default_rng(0)
        s.data.foreach_set('value', rng.uniform(-100, 100, len(s.data)))
        e.data.foreach_set('value', rng.uniform(.1, 100, len(e.data)))
        self.assertEqual(face_u(mesh), reference())
        e.data[0].value = 0
        import math
        for actual, expected in zip(face_u(mesh), reference()):
            self.assertTrue(math.isnan(actual) if math.isnan(expected) else actual == expected)

    def test_array_colours_equal_scalar(self):
        a = s3d.cone('a', 20, 50)
        calls = []
        def color(x,y,z,n,u):
            calls.append((np.shape(x), np.shape(n), np.shape(u)))
            return np.stack((x*0+.2, n[2]*.1+.5, u*.3), axis=-1)
        s3d.material(a, 'plastic', color=color)
        vector = materials.face_colors(a)
        self.assertEqual(calls, [((8,), (3,8), (8,)),
                                 ((len(vector),), (3,len(vector)), (len(vector),))])
        def scalar(x,y,z,n,u):
            if not np.isscalar(x):
                raise TypeError('scalar only')
            return color(x,y,z,n,u).tolist()
        s3d.material(a, 'plastic', color=scalar)
        self.assertEqual(vector, materials.face_colors(a))

    def test_scalar_rgb_tuple_on_three_faces(self):
        import bpy
        mesh = bpy.data.meshes.new('three faces')
        mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0),(0,0,1)], [],
                         [(0,1,2),(0,2,3),(0,3,1)])
        a = bpy.data.objects.new('three faces', mesh)
        bpy.context.collection.objects.link(a)
        s3d.material(a, 'plastic', color=lambda x,y,z: (x*.2, y*.3, z*.4))
        expected = [materials._linear((f.center.x*.2, f.center.y*.3, f.center.z*.4))
                    for f in mesh.polygons]
        self.assertEqual(materials.face_colors(a), expected)

    def test_array_errors_and_scalar_fallback(self):
        a = s3d.box('a', 10, 10, 10)
        def fallback(x,y,z):
            if not np.isscalar(x):
                return np.zeros((len(x), 4))
            return (.2,.4,.6)
        s3d.material(a, 'plastic', color=fallback)
        self.assertEqual(materials.face_colors(a)[0], materials._linear((.2,.4,.6)))
        for fn, message in [
                (lambda x,y,z: np.zeros((3,len(np.atleast_1d(x)))), 'shape'),
                (lambda x,y,z: np.full((len(x),3), 1.1), r'finite.*\[0, 1\]'),
                (lambda x,y,z: np.full((len(x),3), np.nan), 'finite'),
                (lambda x,y,z: np.full((len(x),3), True), 'numeric')]:
            s3d.material(a, 'plastic', color=fn)
            with self.assertRaisesRegex(ValueError, message):
                materials.face_colors(a)
        def changed(x,y,z):
            return np.zeros((len(x), 3 if len(x) == 8 else 4))
        # Six box faces would make the probe and full call the same size.
        b = s3d.cone('b', 20, 50)
        s3d.material(b, 'plastic', color=changed)
        with self.assertRaisesRegex(ValueError, 'expected RGB array shape'):
            materials.face_colors(b)

    def test_examples(self):
        a = s3d.loft('limb', *(s3d.station(z, 20, 20) for z in (0, 80, 160, 240)))
        s3d.material(a, 'plastic', color=lambda x,y,z: '#c9a137' if int(z//80)%2 else '#2c2d33')
        self.assertEqual(len(set(materials.face_colors(a))), 2)
        b = s3d.hull('stone', [(-80,-80,0), (80,-80,0), (0,80,0), (0,0,100)])
        s3d.material(b, 'concrete', color=lambda x,y,z,n: '#6f8a4c' if n[2]>.5 and s3d.noise(x/60,y/60,z/60,seed=3)>0 else '#9a9893')
        self.assertEqual(len(materials.face_colors(b)), len(b.data.polygons))

    def test_errors(self):
        a = s3d.box('a', 10, 10, 10)
        for fn in (lambda x: x, lambda *args: '#ffffff', lambda x,y,z,*,n: n):
            with self.assertRaisesRegex(ValueError, 'three or four'):
                s3d.material(a, 'plastic', color=fn)
        s3d.material(a, 'plastic', color=lambda x,y,z: 'bad')
        with self.assertRaisesRegex(ValueError, 'face centre'):
            materials.face_colors(a)

    def test_glb_and_mean_formats(self):
        import tempfile
        from pathlib import Path
        from glb import Glb
        a = s3d.box('a', 20, 20, 20)
        s3d.material(a, 'plastic', color=lambda x,y,z: '#ff0000' if z > 10 else '#0000ff')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'a.glb'
            s3d.export(a, path)
            g = Glb(path)
            p = g.doc['meshes'][0]['primitives'][0]
            rows = g.rows(p['attributes']['COLOR_0'])
            self.assertEqual({r[:3] for r in rows}, {(1., 0., 0.), (0., 0., 1.)})
            ids = [r[0] for r in g.rows(p['indices'])]
            for i in range(0, len(ids), 3):
                self.assertEqual(rows[ids[i]], rows[ids[i+1]])
                self.assertEqual(rows[ids[i]], rows[ids[i+2]])
            self.assertNotIn('baseColorFactor', g.doc['materials'][0]['pbrMetallicRoughness'])
            for ext in ('.ifc', '.urdf', '.usda', '.obj', '.stl'):
                s3d.export(a, path.with_suffix(ext))
            self.assertIn('IFCCOLOURRGB', path.with_suffix('.ifc').read_text())
            s3d.export(a, path, colors='vertex')
            again = Glb(path)
            primitive = again.doc['meshes'][0]['primitives'][0]
            self.assertEqual({r[:3] for r in again.rows(primitive['attributes']['COLOR_0'])},
                             {(1., 0., 0.), (0., 0., 1.)})
            self.assertIn('Kd ', path.with_suffix('.mtl').read_text())
            self.assertIn('diffuseColor', path.with_suffix('.usda').read_text())


    def test_fresh_process_determinism(self):
        import subprocess
        import sys
        code = """import sand3d as s
from sand3d import materials
import numpy as np
s.empty_scene(); s.facets(6)
a=s.wire('a',s.spline([(0,-798,1197),(0,-1302,1386),(0,-1218,1722),(0,-1092,2016)]),[(0,504),(.5,273),(1,336)],rings=1)
s.material(a,'plastic',color=lambda x,y,z,n,u: '#ff0000' if int(u*6)%2 else '#0000ff')
b=s.dome('cap',1200,450); s.displace(b,40,300,seed=3,step=0)
s.material(b,'plastic',color=lambda x,y,z,n,u: np.stack((x*0+.2,n[2]*.1+.5,u*.3),axis=-1))
print(([tuple(v.co) for v in a.data.vertices], [tuple(f.vertices) for f in a.data.polygons], __import__('sand3d._coordinates',fromlist=['face_u']).face_u(a.data), materials.face_colors(a), materials.face_colors(b), [tuple(v.co) for v in b.data.vertices]))
"""
        a = subprocess.run([sys.executable, '-c', code], check=True, capture_output=True).stdout
        b = subprocess.run([sys.executable, '-c', code], check=True, capture_output=True).stdout
        self.assertEqual(a.splitlines()[-1], b.splitlines()[-1])

    def test_mean_and_first_material(self):
        import json
        import warnings
        a = s3d.box('a', 10, 10, 10)
        fn = lambda x,y,z: '#ffffff' if z > 5 else '#000000'
        s3d.material(a, 'plastic', color=fn)
        mean = materials._linear(materials.look(materials.mean_tag(a))['color'])
        self.assertAlmostEqual(mean[0], 1/6, places=6)
        b = s3d.at(s3d.box('b', 10, 10, 10), x=30)
        s3d.material(b, 'brass')
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            s3d.merge(a, b)
        key = json.loads(materials._nearest(a))[materials.FUNCTION]
        self.assertIs(materials.FUNCTIONS[key], fn)
        c = s3d.at(s3d.box('c', 5, 5, 5), z=10)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            s3d.join(a, c)
        self.assertIs(materials.FUNCTIONS[key], fn)

    def test_coordinates_use_program_units(self):
        s3d.empty_scene()
        s3d.units('m')
        a = s3d.box('a', .02, .02, .16)
        seen = []
        def color(x,y,z):
            seen.append(z)
            return '#336699'
        s3d.material(a, 'plastic', color=color)
        colors = materials.face_colors(a)
        self.assertAlmostEqual(max(z for z in seen if np.isscalar(z)), .16)
        self.assertEqual(colors[0], materials._linear('#336699'))


    def test_vertex_without_material(self):
        import tempfile
        from pathlib import Path
        from glb import Glb
        a = s3d.box('plain', 10, 10, 10)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'plain.glb'
            s3d.export(a, path, colors='vertex')
            g = Glb(path)
            self.assertEqual(len(g.doc['materials']), 1)
            self.assertIn('COLOR_0', g.doc['meshes'][0]['primitives'][0]['attributes'])

    def test_lengthwise_color_after_displace_refinement(self):
        import tempfile
        from pathlib import Path

        ob = s3d.wire('wire', [(0, 0, 0), (0, 0, 30)], 4)
        s3d.displace(ob, .1, 2, direction='+X', step=.5)
        mesh = ob.data
        np.testing.assert_allclose([v.value for v in mesh.attributes['.s3d_extent'].data], 30, rtol=1e-6)
        np.testing.assert_allclose([v.value for v in mesh.attributes['.s3d_s'].data],
                                   [v.co.z for v in mesh.vertices], atol=1e-5)
        s3d.material(ob, 'plastic', color=lambda x, y, z, n, u: (u, 0, 1-u))
        with tempfile.TemporaryDirectory() as tmp:
            s3d.export(ob, Path(tmp) / 'wire.glb')

    def test_lengthwise_makers_and_edits(self):
        makers = [lambda: s3d.loft('loft', s3d.station(0,20,20), s3d.station(100,30,30), rings=5),
                  lambda: s3d.wire('wire', s3d.spline([(0,0,0),(20,0,100),(0,0,200)]),
                                   [(0,20),(1,30)], rings=5),
                  lambda: s3d.sweep('sweep', s3d.ellipse(20,10), [(0,0,0),(0,0,100)], rings=5),
                  lambda: s3d.cylinder('cylinder',20,100), lambda: s3d.cone('cone',20,100),
                  lambda: s3d.sphere('sphere',20), lambda: s3d.dome('dome',20,10)]
        for make in makers:
            ob = make()
            values = __import__('sand3d._coordinates',fromlist=['face_u']).face_u(ob.data)
            self.assertTrue(all(0 <= u <= 1 for u in values))
            s3d.material(ob, 'plastic', color=lambda x,y,z,n,u: '#ff0000' if u > .1 else '#0000ff')
            self.assertEqual(len(set(materials.face_colors(ob))), 2)
            clone = s3d.copy(ob)
            s3d.at(clone, x=500); s3d.transform(clone, rz=20); s3d.scale(clone, 2)
            self.assertEqual(values, __import__('sand3d._coordinates',fromlist=['face_u']).face_u(clone.data))
        box = s3d.box('unparameterised',10,10,10)
        s3d.material(box,'plastic',color=lambda x,y,z,n,u: '#ffffff')
        with self.assertRaisesRegex(ValueError, "'unparameterised'.*loft, wire, sweep"):
            materials.face_colors(box)
