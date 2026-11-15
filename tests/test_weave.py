"""A basket weave as a height field: strands over and under stakes, row after row."""
import math
import unittest
import bpy
import numpy as np
import sand3d as s3d
from test_determinism import run_cases


class Weave(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()
        s3d.units('mm')

    def test_arrays_bounds_and_scalars(self):
        x = np.linspace(-90, 90, 113)[:, None]
        z = np.linspace(-70, 70, 91)[None, :]
        for kw in ({}, dict(row=9, stake=1), dict(across=30, stake=.1), dict(across='-Y', up='+X')):
            f = s3d.weave(7, **kw)
            values = f(x, 3, z)
            self.assertEqual(values.shape, (113, 91))
            self.assertEqual(values.dtype, np.float64)
            self.assertTrue(np.all(np.abs(values) <= 1))
            for i, j in ((0, 0), (19, 30), (112, 90)):
                self.assertAlmostEqual(values[i, j], f(float(x[i, 0]), 3, float(z[0, j])))
            self.assertIsInstance(f(1, 2, 3), float)

    def test_over_one_stake_under_the_next(self):
        f = s3d.weave(30)                       # stakes every 30 along X, rows 15 high along Z
        mid = 7.5                               # the middle of the first row
        self.assertAlmostEqual(f(0, 0, mid), 1)                 # over the stake at x = 0: proud
        self.assertAlmostEqual(f(30, 0, mid), 2 * .8 - 1)       # under the next: the stake shows, lower
        self.assertAlmostEqual(f(15, 0, mid), 0)                # between the two: half way down
        self.assertAlmostEqual(f(30, 0, mid + 15), 1)           # the row above is shifted by one stake
        self.assertAlmostEqual(f(0, 0, mid + 15), 2 * .8 - 1)
        for x in (0, 11, 30):                                   # a groove between two rows
            self.assertAlmostEqual(f(x, 0, 0), -1)
            self.assertAlmostEqual(f(x, 0, 15), -1)
        self.assertLess(f(30 + .3 * 15 + 1, 0, mid), f(30, 0, mid))    # beside the stake's ridge: lower

    def test_periods_and_the_other_axis(self):
        x = np.linspace(-100, 100, 401)
        z = np.linspace(-40, 40, 161)[:, None]
        f = s3d.weave(12, row=5)
        np.testing.assert_allclose(f(x + 24, 0, z), f(x, 0, z), atol=1e-9)        # two stakes on: the same
        np.testing.assert_allclose(f(x + 12, 0, z + 5), f(x, 0, z), atol=1e-9)    # one stake on, one row up
        np.testing.assert_allclose(f(x, 17, z), f(x, -3, z))                      # the third axis does not count
        self.assertFalse(np.allclose(f(x + 12, 0, z), f(x, 0, z)))

    def test_across_and_up(self):
        p = np.linspace(-50, 50, 211)
        q = np.linspace(-20, 20, 83)[:, None]
        base = s3d.weave(9)(p, 0, q)
        np.testing.assert_allclose(s3d.weave(9, across='+Y')(0, p, q), base)
        np.testing.assert_allclose(s3d.weave(9, across='+X', up='+Y')(p, q, 0), base)
        np.testing.assert_allclose(s3d.weave(9, across=90)(4, p, q), base, atol=1e-9)
        # at 45 degrees in XY, a wall along X and a wall along Y see the same weave, sqrt(2) wider
        r = math.sqrt(2)
        np.testing.assert_allclose(s3d.weave(9, across=45)(p * r, 0, q), base, atol=1e-9)
        np.testing.assert_allclose(s3d.weave(9, across=45)(0, p * r, q), base, atol=1e-9)
        # the same weave at another scale
        np.testing.assert_allclose(s3d.weave(90, row=45)(p * 10, 0, q * 10), base, atol=1e-9)

    def test_on_a_displaced_wall(self):
        # A real planar mesh in XZ pushed along -Y: its depths are the field's.
        n, rows, step = 200, 60, .5
        mesh = bpy.data.meshes.new('wall')
        verts = [(i * step, 0, j * step) for j in range(rows) for i in range(n)]
        faces = [(j * n + i, j * n + i + 1, (j + 1) * n + i + 1, (j + 1) * n + i)
                 for j in range(rows - 1) for i in range(n - 1)]
        mesh.from_pydata(verts, [], faces)
        ob = bpy.data.objects.new('wall', mesh)
        bpy.context.scene.collection.objects.link(ob)
        f = s3d.weave(10)
        s3d.displace(ob, .4, 2, noise=f, direction='-Y', refine=False)
        co = np.array([v.co for v in ob.data.vertices])
        np.testing.assert_allclose(co[:, 1], -.4 * f(co[:, 0], 0, co[:, 2]), atol=1e-6)
        np.testing.assert_allclose(co[:, 0], np.tile(np.arange(n) * step, rows), atol=1e-6)

    def test_errors(self):
        for kw in (dict(pitch=0), dict(pitch=-3), dict(pitch=math.inf), dict(pitch=True), dict(pitch='3'),
                   dict(row=0), dict(row=math.nan), dict(stake=0), dict(stake=1.1), dict(stake='wide'),
                   dict(across='+W'), dict(across=[]), dict(across=math.inf), dict(up=45), dict(up='up'),
                   dict(across='+Z'), dict(across='+X', up='-X'), dict(across=30, up='+Y')):
            args = dict(pitch=4); args.update(kw)
            with self.subTest(kw=kw), self.assertRaisesRegex(ValueError, 'weave:'):
                s3d.weave(**args)
        for xyz in ((math.nan, 0, 0), (0, 0, math.inf), (1e300, 0, 0)):
            with self.assertRaisesRegex(ValueError, 'weave:'):
                s3d.weave(1)(*xyz)

    def test_fresh_processes(self):
        first = run_cases('woven_walls', seed='11')['digests']['woven_walls']
        second = run_cases('woven_walls', seed='37')['digests']['woven_walls']
        self.assertFalse(first.startswith('error'), first)
        self.assertEqual(first, second)


if __name__ == '__main__':
    unittest.main()
