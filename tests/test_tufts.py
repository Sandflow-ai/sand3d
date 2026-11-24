"""Root contact, fixed cost, fields and one-mesh throughput."""
import time
import unittest
import bpy
import numpy as np
import sand3d as s3d
from sand3d import _core, materials
from test_determinism import run_cases


class Tufts(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()
        s3d.units('mm')

    def test_triangle_cost_and_contact(self):
        ground = s3d.box('ground', 100, 100, 10)
        sites = s3d.scatter(40, ground, seed=8)
        for shape, cost, stride in [('blade', 2, 4), ('cone', 6, 5)]:
            grass = s3d.tufts(shape, sites, 8, 1, blades=7, shape=shape, seed=8)
            self.assertEqual(len(grass.data.polygons), 40 * 7 * cost)
            tree = _core.mm_tree(ground, ground.matrix_basis)
            for i, site in enumerate(sites):
                for j in range(7):
                    root = grass.data.vertices[(i*7+j)*stride].co
                    self.assertLess((root-site.origin).length, 1e-5)
                    self.assertLess(tree.find_nearest(root)[3], 1e-3)

    def test_scalar_and_vector_fields_agree(self):
        sites = s3d.grid(4, 2, 3, 3)
        a = s3d.tufts('a', sites, lambda x,y,z,n: 5+x, lambda x,y,z,n: 1.,
                      lean=lambda x,y,z,n: 0., direction=lambda x,y,z,n: (1,0,0))
        b = s3d.tufts('b', sites, lambda x,y,z,n: 5+x,
                      lambda x,y,z,n: np.ones_like(x), lean=0,
                      direction=lambda x,y,z,n: np.column_stack((np.ones_like(x), x*0, x*0)))
        self.assertEqual([tuple(v.co) for v in a.data.vertices], [tuple(v.co) for v in b.data.vertices])
        self.assertAlmostEqual(a.data.vertices[3].co.x-sites[0].origin.x, 5+sites[0].origin.x)

    def test_material_colour(self):
        grass = s3d.tufts('grass', s3d.grid(2,2,5,5), 5, 1)
        s3d.material(grass, 'grass', color=lambda x,y,z,n: (.1,.5,.1))
        self.assertEqual(len(materials.face_colors(grass)), len(grass.data.polygons))

    def test_30000_blades(self):
        sites = s3d.grid(100, 60, 2, 2)
        start = time.perf_counter()
        grass = s3d.tufts('lawn', sites, 4, .3, blades=5)
        seconds = time.perf_counter()-start
        print(f'\nTUFTS 30000 blades: {seconds:.3f}s', flush=True)
        self.assertEqual(len(grass.data.polygons), 60000)
        self.assertEqual(len([o for o in bpy.data.objects if o.type == 'MESH']), 1)
        self.assertLess(seconds, 10)

    def test_fresh_processes(self):
        a = run_cases('rooted_tufts', seed='11')['digests']['rooted_tufts']
        b = run_cases('rooted_tufts', seed='37')['digests']['rooted_tufts']
        self.assertFalse(a.startswith('error'), a)
        self.assertEqual(a, b)

    def test_invalid_fields(self):
        sites = s3d.Frames([s3d.Frame()])
        for kw in [dict(height=0), dict(width=-1), dict(lean=90), dict(direction=(0,0,0)), dict(blades=0), dict(shape='bad'), dict(height=lambda x,y,z,n: float('nan'))]:
            args = dict(height=5, width=1, **{})
            args.update(kw)
            with self.assertRaises(ValueError):
                s3d.tufts('bad', sites, **args)
