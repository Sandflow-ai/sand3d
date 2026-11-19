"""Fixed-count organic surfaces: bounded refinement, closed topology and stable output."""
import math
import os
import subprocess
import sys
import unittest

import bpy
import bmesh
import sand3d as s3d
from sand3d import _core


def triangles(ob):
    return sum(len(p.vertices)-2 for p in ob.data.polygons)


def specimens(n, smooth=False):
    s3d.empty_scene()
    if n != 'auto':
        s3d.facets(n, smooth=smooth)
    cylinder = s3d.cylinder('cylinder', 20, 20)
    # Twelve explicit points, without relying on the global circle sampler.
    points = [(10*math.cos(i*math.pi/3), 9*math.sin(i*math.pi/3), z)
              for z in (0, 18) for i in range(6)]
    rock = s3d.displace(s3d.hull('rock', points), 1.5, 8, seed=7)
    coral = s3d.field('coral', (32, 32, 32),
                     lambda x,y,z: min((x+4)**2+y*y+(z-12)**2-81,
                                       (x-4)**2+y*y+(z-20)**2-81),
                     cell=2, min_component_cells=0)
    return cylinder, rock, coral


class NatureFacets(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()

    def tearDown(self):
        s3d.empty_scene()

    def assertClosed(self, ob):
        bm = bmesh.new()
        try:
            bm.from_mesh(ob.data)
            self.assertTrue(all(e.is_manifold for e in bm.edges))
            self.assertTrue(all(f.calc_area() > 0 for f in bm.faces))
        finally:
            bm.free()

    def test_triangle_budget_and_flat_shading(self):
        previous = None
        for n in (6, 12, 24, 'auto'):
            parts = specimens(n)
            counts = [triangles(ob) for ob in parts]
            for ob in parts:
                self.assertClosed(ob)
                if n != 'auto':
                    self.assertFalse(any(p.use_smooth for p in ob.data.polygons))
            if n == 6:
                # Tetrahedral extraction has several triangles per grid cell;
                # four times a six-sided cylinder allows this overhead, not thousands.
                self.assertTrue(all(0 < c <= 4*counts[0] for c in counts[1:]), counts)
            if previous:
                self.assertTrue(all(a <= b for a,b in zip(previous, counts)), (previous, counts))
            previous = counts

    def test_smooth_opt_in(self):
        for ob in specimens(6, smooth=True)[1:]:
            self.assertTrue(any(p.use_smooth for p in ob.data.polygons))

    def test_target_is_local_scale_covariant(self):
        s3d.facets(12)
        self.assertAlmostEqual(_core.surface_edge((10,20,30)), math.pi*30/12)
        self.assertAlmostEqual(_core.surface_edge((1,2,3))*10, _core.surface_edge((10,20,30)))
        ob = specimens(6)[1]
        twin = s3d.copy(ob)
        s3d.displace(twin, 0, 8)
        before = triangles(twin)
        s3d.at(ob, x=1000, ry=40)
        s3d.displace(ob, 0, 8)
        self.assertEqual(triangles(ob), before)

    def test_field_explicit_cell_stays_a_floor(self):
        def build(n):
            s3d.empty_scene()
            s3d.facets(n)
            return s3d.field('sphere', (32,32,32), lambda x,y,z:x*x+y*y+(z-16)**2-100, cell=20)
        self.assertEqual(triangles(build(6)), triangles(build(24)))

    def test_blend_simplifies_and_preserves_closure(self):
        counts = []
        for n in (6, 12, 'auto'):
            s3d.empty_scene()
            s3d.facets(n)
            ob = s3d.blend(s3d.box('base',20,20,20), r=3)
            self.assertClosed(ob)
            if n != 'auto':
                self.assertFalse(any(p.use_smooth for p in ob.data.polygons))
            counts.append(triangles(ob))
        self.assertLess(counts[0], counts[1])
        self.assertLess(counts[1], counts[2])

    def test_two_fresh_processes(self):
        code = '''import sys, os
sys.path.insert(0, 'tests')
from test_nature_facets import specimens
from harness import digest
import sand3d as s
for n in (6,12,24):
 specimens(n)
 s.blend(s.box('blend',20,20,20),r=3)
 print('@@nature', n, digest(None), flush=True)
os._exit(0)
'''
        outputs = []
        for seed in ('11', '37'):
            result = subprocess.run([sys.executable, '-c', code], capture_output=True, check=True,
                                    env={**os.environ, 'PYTHONHASHSEED':seed}, timeout=180)
            outputs.append([l for l in result.stdout.splitlines() if l.startswith(b'@@nature')])
        self.assertEqual(len(outputs[0]), 3)
        self.assertEqual(*outputs)
