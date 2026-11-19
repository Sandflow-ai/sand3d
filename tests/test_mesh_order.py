"""Canonical ordering retains Python's stable, lexicographic ordering."""
import unittest
import bpy
import bmesh
from sand3d.edit import _sort_mesh


class MeshOrder(unittest.TestCase):
    def test_ties_and_mixed_polygon_sizes(self):
        bm = bmesh.new()
        try:
            verts = [bm.verts.new(p) for p in (
                (2, 0, 0), (0, 0, 0), (0, 1, 0), (1, 1, 0),
                (0, 0, 0), (0, 0, 1), (0, -1, 0))]
            for indices in ((0, 1, 2), (0, 1, 2, 3), (4, 5, 6)):
                bm.faces.new([verts[i] for i in indices])
            vl = bm.verts.layers.int.new("identity")
            el = bm.edges.layers.int.new("identity")
            fl = bm.faces.layers.int.new("identity")
            for seq, layer in ((bm.verts, vl), (bm.edges, el), (bm.faces, fl)):
                for i, item in enumerate(seq):
                    item[layer] = i
            expected_vertices = sorted(bm.verts, key=lambda v: tuple(v.co))
            indices = {v: i for i, v in enumerate(expected_vertices)}
            expected_edges = sorted(bm.edges, key=lambda e: sorted(indices[v] for v in e.verts))
            expected_faces = sorted(bm.faces, key=lambda f: [indices[v] for v in f.verts])
            expected = [[item[layer] for item in seq] for seq, layer in (
                (expected_vertices, vl), (expected_edges, el), (expected_faces, fl))]
            for _ in range(2):
                _sort_mesh(bm)
                actual = [[item[layer] for item in seq] for seq, layer in (
                    (bm.verts, vl), (bm.edges, el), (bm.faces, fl))]
                self.assertEqual(actual, expected)
        finally:
            bm.free()

    def test_empty(self):
        bm = bmesh.new()
        try:
            _sort_mesh(bm)
        finally:
            bm.free()
