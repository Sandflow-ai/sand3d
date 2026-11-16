"""Directional and radial height fields, scalar colours and array displacement."""
import math
import unittest
import bpy
import numpy as np
import sand3d as s3d
from test_determinism import run_cases


class Waves(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()
        s3d.units('mm')

    def test_arrays_bounds_and_scalars(self):
        x = np.linspace(-90, 90, 113)[:, None]
        y = np.linspace(-70, 70, 91)[None, :]
        for kw in ({}, dict(direction=31, spread=25, seed=-19, sharpness=1),
                   dict(centers=[(0, 0), (7, -2), (-9, 3)], decay=12, sharpness=.8)):
            f = s3d.waves(7, **kw)
            values = f(x, y, 0)
            self.assertEqual(values.shape, (113, 91))
            self.assertEqual(values.dtype, np.float64)
            self.assertTrue(np.all(np.abs(values) <= 1))
            for i, j in ((0, 0), (19, 30), (112, 90)):
                self.assertAlmostEqual(values[i, j], f(float(x[i, 0]), float(y[0, j]), 0))
            self.assertIsInstance(f(1, 2, 3), float)

    def test_wavelength_on_displaced_plane(self):
        # A real planar mesh; one row yields a direct FFT of displaced heights.
        n, step, wavelength = 1024, .0625, 4
        mesh = bpy.data.meshes.new('plane')
        verts = [(i*step, y, 0) for y in (0, 1) for i in range(n)]
        mesh.from_pydata(verts, [], [(i, i+1, n+i+1, n+i) for i in range(n-1)])
        ob = bpy.data.objects.new('plane', mesh)
        bpy.context.scene.collection.objects.link(ob)
        s3d.displace(ob, .2, .5, noise=s3d.waves(wavelength), direction='+Z', step=0)
        mesh = ob.data
        h = np.array([v.co.z for v in mesh.vertices[:n]])
        frequency = np.fft.rfftfreq(n, step)[np.argmax(abs(np.fft.rfft(h))[1:])+1]
        self.assertAlmostEqual(1/frequency, wavelength)
        np.testing.assert_allclose([v.co.x for v in mesh.vertices[:n]], np.arange(n)*step)

    def test_direction_phase_and_sharpness(self):
        x = np.linspace(-10, 10, 200)
        for direction, a in (('+X', 0), ('+Y', 90), ('-X', 180), ('-Y', 270), (35, 35)):
            f = s3d.waves(4, direction=direction, phase=30)
            a = math.radians(a)
            np.testing.assert_allclose(f(x*math.cos(a), x*math.sin(a), 0),
                                       np.cos(2*np.pi*x/4+np.pi/6), atol=1e-14)
            np.testing.assert_allclose(f(-x*math.sin(a), x*math.cos(a), 0), math.cos(math.pi/6), atol=1e-14)
        smooth, sharp = s3d.waves(4), s3d.waves(4, sharpness=1)
        self.assertLess(sharp(.2, 0, 0), smooth(.2, 0, 0))
        self.assertLess(sharp(1.8, 0, 0), smooth(1.8, 0, 0))

    def test_radial_decay_and_envelopes(self):
        f = s3d.waves(2, centers=[(1, -1)], decay=5)
        r = np.arange(6)*2
        np.testing.assert_allclose(f(1+r, -1, 0), np.exp(-r/5))
        np.testing.assert_allclose(f(1, -1+r, 88), f(1+r, -1, 0))
        x = np.linspace(-10, 10, 100)
        a = s3d.waves(2, centers=[(0, 0)])
        b = s3d.waves(2, centers=[(3, 1)])
        both = s3d.waves(2, centers=[(0, 0), (3, 1)])
        np.testing.assert_allclose(both(x, 0, 0), (a(x, 0, 0)+b(x, 0, 0))/2)
        # With decay, a ring far from the others keeps its own height; overlaps stay bounded.
        lone = s3d.waves(2, centers=[(0, 0)], decay=3)
        three = s3d.waves(2, centers=[(0, 0), (200, 0), (0, 200)], decay=3)
        np.testing.assert_allclose(three(x, 0, 0), lone(x, 0, 0), atol=1e-12)
        g = np.linspace(-5, 5, 201)
        X, Y = np.meshgrid(g, g)
        crowd = s3d.waves(1.3, centers=[(0, 0), (.4, .1), (-.3, .5)], decay=4, sharpness=.6)
        self.assertLessEqual(np.abs(crowd(X, Y, 0)).max(), 1.0)

    def test_units_and_composition(self):
        x = np.linspace(-10, 10, 100)
        for k in (1, .01, .001):
            np.testing.assert_allclose(s3d.waves(4*k, centers=[(k, 0)], decay=5*k)(x*k, 0, 0),
                                       s3d.waves(4, centers=[(1, 0)], decay=5)(x, 0, 0), atol=1e-14)
        f = s3d.waves(4)
        ob = s3d.box('sample', 4, 4, 1)
        s3d.material(ob, 'plastic', color=lambda x,y,z: (max(0, f(x,y,z)), .2, .3))
        from sand3d.materials import face_colors
        self.assertEqual(len(face_colors(ob)), len(ob.data.polygons))
        s3d.displace(ob, .1, 1, direction='+Z', noise=lambda x,y,z: f(x,y,z)*np.clip(x/2, 0, 1))

    def test_errors(self):
        for kw in (dict(wavelength=0), dict(wavelength=math.inf), dict(wavelength=True),
                   dict(direction='+Z'), dict(direction=[]), dict(spread=-1), dict(spread=91),
                   dict(sharpness=1.1), dict(sharpness=math.nan), dict(phase='bad'),
                   dict(seed=True), dict(seed=1.2), dict(decay=3), dict(centers=[]),
                   dict(centers=[(1,2,3)]), dict(centers=1), dict(centers=[(0,math.nan)]),
                   dict(centers=[(0,0)], direction=0), dict(centers=[(0,0)], spread=1),
                   dict(centers=[(0,0)], decay=0)):
            args = dict(wavelength=4); args.update(kw)
            with self.subTest(kw=kw), self.assertRaisesRegex(ValueError, 'waves:'):
                s3d.waves(**args)
        for xyz in ((math.nan, 0, 0), (0, 0, math.inf), (1e300, 0, 0)):
            with self.assertRaisesRegex(ValueError, 'waves:'):
                s3d.waves(1)(*xyz)

    def test_seed_and_fresh_processes(self):
        x = np.linspace(-10, 10, 100)
        self.assertFalse(np.array_equal(s3d.waves(3, spread=20, seed=1)(x,0,0),
                                        s3d.waves(3, spread=20, seed=2)(x,0,0)))
        first = run_cases('wave_surfaces', seed='11')['digests']['wave_surfaces']
        second = run_cases('wave_surfaces', seed='37')['digests']['wave_surfaces']
        self.assertFalse(first.startswith('error'), first)
        self.assertEqual(first, second)
