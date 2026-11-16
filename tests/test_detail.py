"""Resolution density is independent of feature dimensions and external policy wins."""
import os
import unittest
from unittest.mock import patch
import sand3d as s3d
from sand3d import _core


def triangles(ob):
    ob.data.calc_loop_triangles()
    return len(ob.data.loop_triangles)


class Detail(unittest.TestCase):
    def tearDown(self):
        s3d.empty_scene()
        _core.DETAIL = 1

    def test_external_override_wins_and_scales_explicit(self):
        with patch.dict(os.environ, {'SAND3D_DETAIL': '.5'}):
            self.assertEqual(s3d.detail(2), .5)
            self.assertEqual(_core.resolution_step(2, explicit=True), 4)
            with s3d.facets(32):
                self.assertEqual(_core.FACETS, 16)
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_core.resolution_step(2, explicit=True), 2)

    def test_bend_cost_drops(self):
        s3d.detail(1)
        a=s3d.box('a',10,100,1)
        s3d.bend(a,30)
        before=triangles(a)
        s3d.detail(.5)
        b=s3d.box('b',10,100,1)
        s3d.bend(b,30)
        self.assertLess(triangles(b),before*.65)

    def test_displace_step_decouples_noise_size(self):
        a=s3d.box('a',20,20,2)
        s3d.displace(a,0.1,1,step=4)
        b=s3d.box('b',20,20,2)
        s3d.displace(b,0.1,8,step=4)
        self.assertEqual(triangles(a),triangles(b))
        c=s3d.box('c',20,20,2)
        s3d.displace(c,.1,1,step=0)
        self.assertEqual(triangles(c),12)

    def test_invalid_density(self):
        for value in (0,-1,float('nan'),float('inf'),True):
            with self.assertRaises(ValueError):s3d.detail(value)
        with patch.dict(os.environ, {'SAND3D_DETAIL':'0'}):
            with self.assertRaises(ValueError):s3d.detail()
