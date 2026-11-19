"""Array displacement and construction-path coordinates."""
import os
import subprocess
import sys
import unittest
import numpy as np
import sand3d as s3d
import bmesh
from sand3d.edit import _path_coordinates

def coordinates(ob):
    bm = bmesh.new(); bm.from_mesh(ob.data)
    try:
        return _path_coordinates(bm)
    finally:
        bm.free()

from test_determinism import ROOT


class FunctionDisplace(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()

    def test_direct_values_and_local_frame(self):
        ob = s3d.at(s3d.box("sample", 2, 2, 2), x=100)
        seen = []
        def f(x, y, z):
            seen.append((x.copy(), y.copy(), z.copy()))
            self.assertEqual(x.dtype, np.float64)
            return np.ones_like(x)
        s3d.displace(ob, 3, 10, noise=f, direction="+Z")
        self.assertAlmostEqual(min(v.co.z for v in ob.data.vertices), 3)
        self.assertLessEqual(abs(seen[0][0]).max(), 1)
        self.assertAlmostEqual(ob.location.x, 100)

    def test_curved_wire_coordinates(self):
        ob = s3d.wire("curve", [(0, 0, 0), (0, 0, 10), (10, 0, 10)], 1)
        q = coordinates(ob)
        self.assertAlmostEqual(q[:,0].min(),0)
        self.assertAlmostEqual(q[:,0].max(),20)
        s3d.displace(ob, .1, 2, noise=lambda s,a,r: np.sin(np.radians(a)), coords="path")

    def test_sweep_copy_and_placement(self):
        ob = s3d.sweep("sweep", s3d.circle(2), [(0,0,0), (0,0,8)])
        ob = s3d.at(s3d.copy(ob), ry=60, x=20)
        s3d.displace(ob, .2, 2, noise=lambda s,a,r: s3d.noise(s, a/180, r), coords="path")

    def test_refusals_leave_mesh_untouched(self):
        for f in (lambda x,y,z: 0, lambda x,y,z: x[:,None],
                  lambda x,y,z: x*0+np.nan, lambda x,y,z: x*0+np.inf,
                  lambda x,y,z: x*0+1.1, lambda x,y,z: x.astype(complex)):
            ob = s3d.box("bad", 2, 2, 2)
            before = [tuple(v.co) for v in ob.data.vertices]
            with self.assertRaises(ValueError):
                s3d.displace(ob, 1, 1, noise=f)
            self.assertEqual(before, [tuple(v.co) for v in ob.data.vertices])
        f = lambda x,y,z: x*0
        for kwargs in (dict(coords="path"), dict(coords="bad"), dict(seed=1), dict(octaves=2)):
            with self.assertRaises(ValueError):
                s3d.displace(ob, 1, 2, noise=f, **kwargs)
        wire = s3d.wire("wire", [(0,0,0), (0,0,4)], 2)
        with self.assertRaises(ValueError):
            s3d.displace(wire, 1, 2, coords="path")
        s3d.join(wire, s3d.box("base", 3, 3, 1))
        with self.assertRaisesRegex(ValueError, "coordinates|before join"):
            s3d.displace(wire, 1, 2, noise=f, coords="path")

    def test_fade_and_refinement(self):
        ob = s3d.box("fade", 2, 2, 4)
        s3d.displace(ob, 1, 2, noise=lambda x,y,z: np.ones_like(z),
                     direction="+Z", fade=(0,4))
        self.assertGreater(len(ob.data.vertices), 8)
        self.assertAlmostEqual(min(v.co.z for v in ob.data.vertices), 1)
        self.assertAlmostEqual(max(v.co.z for v in ob.data.vertices), 4)

    def test_path_lengths_use_program_units(self):
        for unit, factor in (("mm", 1), ("m", .001)):
            s3d.empty_scene()
            s3d.units(unit)
            ob = s3d.wire("units", [(0,0,0), (0,0,10*factor)], 2*factor)
            q = coordinates(ob)
            self.assertAlmostEqual(q[:,0].max(),10*factor)
            np.testing.assert_allclose(q[:,2],factor,atol=1e-8)
        s3d.empty_scene()
        s3d.units("mm")

    def test_path_survives_deformation_and_merge(self):
        for edit in (lambda ob: s3d.bend(ob,20,axis='+Z',toward='+X'),
                     lambda ob: s3d.scale(ob,2),
                     lambda ob: s3d.merge(ob,s3d.wire('other',[(0,0,0),(0,0,3)],1))):
            ob = s3d.wire('axis',[(0,0,0),(0,0,10)],2)
            before = coordinates(ob)
            ob = edit(ob)
            after = coordinates(ob)
            np.testing.assert_allclose(before,after[:len(before)])
            s3d.displace(ob,.1,2,noise=lambda s,a,r:s*0,coords='path',step=0)

    def test_two_fresh_processes(self):
        code = """
import sand3d as s3d
import numpy as np
import sys
sys.path.insert(0, "tests")
from harness import digest
ob = s3d.wire("bough", s3d.spline([(0,0,0),(0,0,10),(5,0,20)]), 2)
s3d.displace(ob, .2, 2, noise=lambda s,a,r: s3d.noise(s/4, np.cos(np.radians(a)), r, seed=17), coords="path")
s3d.displace(ob, .1, 2, noise=lambda x,y,z: np.sin(z))
print(digest(None), flush=True)
"""
        results = [subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                   env={**os.environ, "PYTHONPATH": str(ROOT/"src"), "PYTHONHASHSEED": seed},
                   capture_output=True, text=True, timeout=120, check=True).stdout for seed in ("11","37")]
        self.assertEqual(results[0], results[1])
