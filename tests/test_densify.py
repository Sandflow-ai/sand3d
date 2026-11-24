"""Spatial candidate searches retain the strict vertex-distance predicate."""
import unittest
from unittest.mock import patch

import bpy
import bmesh
from mathutils import Vector
from sand3d import edit


class Densify(unittest.TestCase):
    def test_strict_radius_boundary(self):
        for x, skip in ((0.249999, True), (0.25, False), (0.250001, False)):
            with self.subTest(x=x):
                bm = bmesh.new()
                bm.verts.new((x, 0, 0))
                with patch.object(edit, 'BVHTree') as surface:
                    surface.FromBMesh.return_value.find_nearest_range.return_value = []
                    edit._densify(bm, Vector((0, 0, 0)), 1)
                    self.assertEqual(surface.FromBMesh.called, not skip)
                bm.free()

    def test_spatial_candidates_match_linear_predicate(self):
        bm = bmesh.new()
        for i in range(100):
            bm.verts.new((i / 10, (i % 7) / 10, 0))
        tree = edit._vertex_tree(bm)
        for i in range(200):
            c = Vector((i / 20, 0.15, 0))
            expected = any((v.co - c).length < 0.25 for v in bm.verts)
            with patch.object(edit, 'BVHTree') as surface:
                surface.FromBMesh.return_value.find_nearest_range.return_value = []
                edit._densify(bm, c, 1, vertices=tree)
                self.assertEqual(surface.FromBMesh.called, not expected)
        bm.free()
