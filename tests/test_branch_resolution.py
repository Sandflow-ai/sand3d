"""Curved-axis sampling is angular by default, with an explicit spacing."""
import unittest
import sand3d as s3d
from sand3d.frames import _path_measure


class BranchResolution(unittest.TestCase):
    def test_default_and_spacing(self):
        default = s3d.branches(1000, 10, levels=0, wander=20, seed=1)[0].path
        fine = s3d.branches(1000, 10, levels=0, wander=20, seed=1, step=5)[0].path
        coarse = s3d.branches(1000, 10, levels=0, wander=20, seed=1, step=100)[0].path
        pts, _ = _path_measure(fine._mesh_path)
        self.assertTrue(all((b-a).length <= 5.01 for a,b in zip(pts,pts[1:])))
        self.assertLess(len(_path_measure(default._mesh_path)[0]), 97)
        self.assertLess(len(_path_measure(coarse._mesh_path)[0]), len(pts))
        with self.assertRaises(ValueError):
            s3d.branches(1000, 10, step=0)
