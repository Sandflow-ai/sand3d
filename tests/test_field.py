"""Implicit solids: closure, cavity orientation, units and bounded extraction."""
import math
import unittest
import bpy
from mathutils import Vector
import sand3d as s3d
from test_solids import closed_volume


class Field(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()
        s3d.units('mm')

    def test_sphere_and_exact_zero_samples(self):
        ob = s3d.field('ball', (24, 24, 24), lambda x,y,z: x*x+y*y+(z-12)**2-100, cell=1)
        closed, volume = closed_volume(ob)
        self.assertTrue(closed)
        self.assertAlmostEqual(volume, 4*math.pi*1000/3, delta=45)
        self.assertGreater(ob.face('+Z').origin.z, 21)
        self.assertIn('s3d_face:field', ob.data.attributes)
        s3d.at(ob, x=40)
        s3d.displace(ob, amount=.01, size=3)
        self.assertTrue(closed_volume(ob)[0])

    def test_cavity_winding(self):
        ob = s3d.field('shell', (24,24,24), lambda x,y,z: abs(math.sqrt(x*x+y*y+(z-12)**2)-8)-2, cell=1.1)
        ob.data.calc_loop_triangles()
        volume = sum(ob.data.vertices[t.vertices[0]].co.dot(
            ob.data.vertices[t.vertices[1]].co.cross(ob.data.vertices[t.vertices[2]].co))/6
                     for t in ob.data.loop_triangles)
        self.assertAlmostEqual(volume, 4*math.pi*(1000-216)/3, delta=70)
        self.assertTrue(closed_volume(ob)[0])

    def test_boundary_and_units(self):
        try:
            for unit, k in [('mm',1), ('cm',.1), ('m',.001)]:
                s3d.empty_scene(); s3d.units(unit)
                ob = s3d.field('clip', (10*k,)*3, lambda x,y,z: -1, cell=k)
                self.assertTrue(closed_volume(ob)[0])
                self.assertGreater(closed_volume(ob)[1]/k**3, 700)
                self.assertTrue(all(-5*k <= v.co.x <= 5*k for v in ob.data.vertices))
        finally:
            s3d.empty_scene(); s3d.units('mm')

    def test_errors_leave_scene_empty(self):
        for kw in [dict(cell=0), dict(cell=1e-12), dict(size=(1,2)), dict(level=math.inf),
                   dict(density=lambda *p: math.nan), dict(density=lambda *p: math.inf),
                   dict(density=lambda *p: 1), dict(density=None)]:
            args = dict(size=(10,10,10), density=lambda *p:-1, cell=1)
            args.update(kw)
            with self.subTest(kw=kw), self.assertRaises((ValueError, TypeError)):
                s3d.field('bad', **args)
        self.assertEqual(len(bpy.data.objects), 0)

    def test_noise(self):
        import numpy as np
        from sand3d.edit import NOISES

        for kind in NOISES:
            q = np.linspace(-3, 3, 19)
            values = s3d.noise(q, q * 0.7, 1.2, seed=4, kind=kind)
            self.assertEqual(values.shape, q.shape)
            np.testing.assert_array_equal(
                values, [s3d.noise(x, x * 0.7, 1.2, seed=4, kind=kind) for x in q]
            )
            self.assertTrue(np.all(np.abs(values) <= 1))
        for kwargs in [dict(kind="bad"), dict(seed=1.5), dict(x=math.nan)]:
            args = dict(x=0, y=0, z=0)
            args.update(kwargs)
            with self.assertRaises(ValueError):
                s3d.noise(**args)

    def test_triangle_budget(self):
        from unittest.mock import patch
        with patch('sand3d.implicit.MAX_TRIANGLES', 10):
            with self.assertRaisesRegex(ValueError, 'triangles'):
                s3d.field('bad', (10,10,10), lambda *p: -1, cell=1)
        self.assertEqual(len(bpy.data.objects), 0)

    def test_level_and_density_scale(self):
        a = s3d.field('a', (12, 14, 16), lambda x,y,z: x*x+y*y+(z-8)**2, cell=1.3, level=16)
        b = s3d.field('b', (12, 14, 16), lambda x,y,z: (x*x+y*y+(z-8)**2-16)*1e200, cell=1.3)
        self.assertEqual([tuple(f.vertices) for f in a.data.polygons], [tuple(f.vertices) for f in b.data.polygons])
        for x, y in zip(a.data.vertices, b.data.vertices):
            self.assertLess((x.co-y.co).length, 1e-5)

    def test_tunnel(self):
        ob = s3d.field('ring', (24,24,12), lambda x,y,z: (math.hypot(x,y)-7)**2+(z-6)**2-4, cell=.8)
        self.assertTrue(closed_volume(ob)[0])
        self.assertEqual(len(ob.data.vertices)-len(ob.data.edges)+len(ob.data.polygons), 0)

    def test_near_level_crossings_survive_mesh_precision(self):
        ob = s3d.field('sliver', (20,20,20), lambda x,y,z: x+y+z-10+1e-7, cell=1)
        self.assertTrue(closed_volume(ob)[0])
        self.assertTrue(all(p.area > 0 for p in ob.data.polygons))

    def test_lattice_ties_far_from_origin(self):
        import numpy as np

        # At z=1024, 1e-5 of a unit edge is below one float32 ULP.
        # Exact ties weld; either sign of a near-tie used to collapse distinct
        # edge crossings after root refinement and float32 conversion.
        for offset in (0, 1e-12, -1e-12, 1e-7):
            with self.subTest(offset=offset):
                s3d.empty_scene()
                def density(x, y, z):
                    return x*x + y*y + (z-1024)**2 - 4 + offset
                ob = s3d.field('ties', (8, 8, 1030), density, cell=1)
                closed, volume = closed_volume(ob)
                self.assertTrue(closed)
                self.assertGreater(volume, 0)
                self.assertTrue(all(p.area > 0 for p in ob.data.polygons))
                co = np.array([tuple(v.co) for v in ob.data.vertices])
                self.assertLess(np.max(np.abs(density(*co.T))), .005)
                self.assertTrue(all(v.normal.dot(v.co-Vector((0,0,1024))) > 0
                                    for v in ob.data.vertices))

    def test_precision_guard_in_two_fresh_processes(self):
        import os
        from pathlib import Path
        import subprocess
        import sys

        here = Path(__file__).resolve().parent
        code = """
import sand3d as s3d
from harness import digest
s3d.field('ties', (8,8,1030),
          lambda x,y,z: x*x+y*y+(z-1024)**2-4+1e-12, cell=1)
print(digest(None), flush=True)
"""
        results = [subprocess.check_output(
            [sys.executable, '-c', code], text=True, timeout=60,
            env={**os.environ, 'PYTHONHASHSEED': seed,
                 'PYTHONPATH': os.pathsep.join((str(here), str(here.parent/'src')))})
                   for seed in ('11', '37')]
        self.assertEqual(results[0], results[1])

    def test_noisy_density_seed_and_cell_fuzz(self):
        import numpy as np

        for seed in range(24):
            for cell in (.7, 1, 1.3, 1.9):
                with self.subTest(seed=seed, cell=cell):
                    s3d.empty_scene()
                    def density(x, y, z):
                        return (np.sqrt(x*x+y*y+(z-8)**2)-5
                                + 1.2*s3d.noise(x*.6,y*.6,z*.6,seed=seed))
                    ob = s3d.field('noisy', (16,)*3, density, cell=cell,
                                   min_component_cells=0)
                    closed, volume = closed_volume(ob)
                    self.assertTrue(closed)
                    self.assertGreater(volume, 0)
                    self.assertTrue(all(p.area > 0 for p in ob.data.polygons))

    def test_warped_sheet_residual_and_normals(self):
        def mid(x,y):
            return 6 + .7*s3d.noise(x*.2,y*.2,0,seed=7)
        def density(x,y,z):
            return abs(z-mid(x,y))-.7
        ob = s3d.field('sheet', (12,12,12), density, cell=.65)
        self.assertTrue(closed_volume(ob)[0])
        dots = []
        for v in ob.data.vertices:
            x,y,z = v.co
            if abs(x)>4 or abs(y)>4:
                continue
            self.assertLess(abs(density(x,y,z)), .0001)
            h=.01
            normal = Vector((
                -(mid(x+h,y)-mid(x-h,y))/(2*h),
                -(mid(x,y+h)-mid(x,y-h))/(2*h), 1)).normalized()
            dots.append(abs(v.normal.dot(normal)))
        self.assertGreater(len(dots), 100)
        self.assertGreater(sum(dots)/len(dots), .9999)
        self.assertGreater(min(dots), .999)

    def test_sparse_band_matches_dense_surface(self):
        from unittest.mock import patch
        def density(x,y,z):
            return (x*x+y*y+(z-10)**2)/49-1
        a = s3d.field('dense', (20,20,20), density, cell=.55)
        with patch('sand3d.implicit.DENSE_SAMPLES', 0):
            b = s3d.field('sparse', (20,20,20), density, cell=.55)
        self.assertTrue(closed_volume(b)[0])
        self.assertEqual([tuple(v.co) for v in a.data.vertices],
                         [tuple(v.co) for v in b.data.vertices])
        self.assertEqual([tuple(f.vertices) for f in a.data.polygons],
                         [tuple(f.vertices) for f in b.data.polygons])

    def test_sample_budget(self):
        from unittest.mock import patch
        with patch('sand3d.implicit.MAX_SAMPLES', 500):
            with self.assertRaisesRegex(ValueError, 'samples'):
                s3d.field('bad', (10,10,10), lambda *p: -1, cell=1)
        self.assertEqual(len(bpy.data.objects), 0)

    def test_sparse_band_in_two_fresh_processes(self):
        import os
        from pathlib import Path
        import subprocess
        import sys
        here = Path(__file__).resolve().parent
        code = ('import sand3d.implicit as implicit; implicit.DENSE_SAMPLES = 0; '
                'import cases; from harness import digest; '
                'print(digest(cases.implicit_solid()), flush=True)')
        digests = []
        for seed in ('11', '37'):
            env = {**os.environ, 'PYTHONHASHSEED': seed,
                   'PYTHONPATH': os.pathsep.join((str(here), str(here.parent/'src')))}
            digests.append(subprocess.check_output([sys.executable, '-c', code],
                                                   env=env, text=True, timeout=60).strip())
        self.assertEqual(digests[0], digests[1])

    def test_band_follows_crossings_missed_by_coarse_face_probes(self):
        from unittest.mock import patch
        # The negative centre seeds one block. On its neighbour all coarse
        # corners AND the centre lie on a constant positive plateau, although
        # their common fine face cuts the sphere. A variation margin cannot
        # select that neighbour; fine-face completion must follow the crossing.
        def density(x,y,z):
            return min(.2, math.sqrt((x-.15)**2+(y-.1)**2+(z-2.1)**2))-.19
        a = s3d.field('dense', (4,4,4), density, cell=.1)
        with patch('sand3d.implicit.DENSE_SAMPLES', 0):
            b = s3d.field('band', (4,4,4), density, cell=.1)
        self.assertTrue(closed_volume(b)[0])
        self.assertEqual([tuple(v.co) for v in a.data.vertices],
                         [tuple(v.co) for v in b.data.vertices])
        self.assertEqual([tuple(f.vertices) for f in a.data.polygons],
                         [tuple(f.vertices) for f in b.data.polygons])

    def test_array_density_and_scalar_fallback(self):
        import numpy as np

        arrays = []

        def density(x, y, z):
            arrays.append((x.dtype, x.shape, y.shape, z.shape))
            return np.sqrt(x * x + y * y + (z - 6) ** 2) - 4

        a = s3d.field("array", (12,) * 3, density, cell=0.8)
        b = s3d.field(
            "scalar",
            (12,) * 3,
            lambda x, y, z: math.sqrt(x * x + y * y + (z - 6) ** 2) - 4,
            cell=0.8,
        )
        self.assertTrue(all(t == np.float64 and x == y == z for t, x, y, z in arrays))
        self.assertEqual(
            [tuple(v.co) for v in a.data.vertices],
            [tuple(v.co) for v in b.data.vertices],
        )
        self.assertEqual(
            [tuple(f.vertices) for f in a.data.polygons],
            [tuple(f.vertices) for f in b.data.polygons],
        )

    def test_fragment_filter(self):
        import numpy as np

        def density(x, y, z):
            return np.minimum(
                np.sqrt((x + 4) ** 2 + y * y + (z - 8) ** 2) - 3,
                np.sqrt((x - 4) ** 2 + y * y + (z - 8) ** 2) - 0.7,
            )

        a = s3d.field("filtered", (20, 20, 16), density, cell=0.7)
        b = s3d.field("all", (20, 20, 16), density, cell=0.7, min_component_cells=0)
        self.assertTrue(closed_volume(a)[0])
        self.assertTrue(closed_volume(b)[0])
        self.assertLess(max(v.co.x for v in a.data.vertices), 0)
        self.assertGreater(max(v.co.x for v in b.data.vertices), 4)
