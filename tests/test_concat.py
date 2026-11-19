"""Raw mesh parity for concatenation, including bmesh's edge creation order."""
import unittest

import bpy
import bmesh
import numpy as np
from mathutils import Matrix

from sand3d import edit


class Concat(unittest.TestCase):
    def test_arrays_and_layer_order(self):
        inputs = []
        expected = bmesh.new()
        weight = expected.verts.layers.float.new('weight')
        ft = expected.faces.layers.bool.new('s3d_face:rim')
        et = expected.edges.layers.bool.new('s3d_edge:rim')
        scalar = expected.faces.layers.float.new('scalar')
        integer = expected.faces.layers.int.new('integer')
        vector = expected.faces.layers.float_vector.new('vector')
        selected = expected.faces.layers.bool.new('.select_poly')
        sharp = expected.faces.layers.bool.new('sharp_face')
        flag = expected.faces.layers.bool.new('flag')
        for reflected in (False, True):
            mesh = bpy.data.meshes.new('source')
            mesh.from_pydata([(0, 0, 0), (1.125, 0, 0), (1, 2, 0), (0, 1, 0)], [], [(0, 1, 2), (0, 2, 3)])
            matrix = Matrix.Translation((.123, .456, .789)) @ Matrix.Diagonal((-1 if reflected else 1, 2, 3, 1))
            attributes = [('weight', 'FLOAT', 'POINT', [-0., 1e-20, 1e20, -1.25]),
                          ('scalar', 'FLOAT', 'FACE', [-0., 1e-20]),
                          ('integer', 'INT', 'FACE', [-123, 345]),
                          ('vector', 'FLOAT_VECTOR', 'FACE', [(1, -0., .125), (3, 4, 5)]),
                          ('flag', 'BOOLEAN', 'FACE', [True, False]),
                          ('s3d_face:rim', 'BOOLEAN', 'FACE', [True, False]),
                          ('s3d_edge:rim', 'BOOLEAN', 'EDGE', [True] * len(mesh.edges))]
            for name, kind, domain, values in attributes:
                attr = mesh.attributes.new(name, kind, domain)
                attr.data.foreach_set('vector' if kind == 'FLOAT_VECTOR' else 'value', np.asarray(values).ravel())
            mesh.polygons[0].use_smooth = True
            inputs.append((mesh, matrix))
            vertices = [expected.verts.new(matrix @ v.co) for v in mesh.vertices]
            for v, value in zip(vertices, attributes[0][3]):
                v[weight] = value
            for i, indices in enumerate(((0, 1, 2), (0, 2, 3))):
                face = expected.faces.new([vertices[j] for j in (indices[::-1] if reflected else indices)])
                face[ft] = i == 0
                face[scalar] = attributes[1][3][i]
                face[integer] = attributes[2][3][i]
                face[vector] = attributes[3][3][i]
                face[selected] = True
                face[sharp] = i != 0
                face[flag] = i == 0
                face.smooth = i == 0
        for edge in expected.edges:
            edge[et] = True
            edge.smooth = False
        result = edit._concat(inputs)
        meshes = [bpy.data.meshes.new('expected'), bpy.data.meshes.new('result')]
        try:
            expected.to_mesh(meshes[0])
            result.to_mesh(meshes[1])
            self.assertEqual(self.snapshot(meshes[0]), self.snapshot(meshes[1]))
        finally:
            expected.free()
            result.free()
            for mesh in [*meshes, *(me for me, _ in inputs)]:
                bpy.data.meshes.remove(mesh)

    @staticmethod
    def snapshot(mesh):
        result = []
        types = {'FLOAT': ('value', 1, np.float32), 'INT': ('value', 1, np.int32),
                 'BOOLEAN': ('value', 1, np.bool_), 'FLOAT_VECTOR': ('vector', 3, np.float32),
                 'INT32_2D': ('value', 2, np.int32)}
        for attr in mesh.attributes:
            prop, width, dtype = types[attr.data_type]
            values = np.empty(len(attr.data) * width, dtype=dtype)
            attr.data.foreach_get(prop, values)
            result.append((attr.name, attr.domain, attr.data_type, values.tobytes()))
        for prop in ('loop_start', 'loop_total'):
            result.append(edit._mesh_array(mesh.polygons, prop).tobytes())
        return result

    def test_add_tags_keeps_existing_layers_and_marks_empty_edges(self):
        from sand3d import _core
        bm = bmesh.new()
        try:
            vertices = [bm.verts.new(co) for co in ((0, 0, 0), (1, 0, 0), (0, 1, 0))]
            bm.faces.new(vertices)
            original = bm.faces.layers.bool.new('s3d_face:z')
            _core.add_tags(bm, {0: {'z', 'a'}}, {0: set(), 1: {'rim'}})
            self.assertEqual([l.name for l in bm.faces.layers.bool.values()], ['s3d_face:z', 's3d_face:a'])
            self.assertTrue(bm.faces[0][original])
            self.assertTrue(bm.faces[0][bm.faces.layers.bool['s3d_face:a']])
            self.assertFalse(bm.edges[0].smooth)
            self.assertFalse(bm.edges[1].smooth)
            self.assertTrue(bm.edges[2].smooth)
            self.assertTrue(bm.edges[1][bm.edges.layers.bool['s3d_edge:rim']])
        finally:
            bm.free()

    def test_bounds_keep_double_subtraction_and_first_signed_zero(self):
        from sand3d import _core
        mesh = bpy.data.meshes.new('bounds')
        ob = bpy.data.objects.new('bounds', mesh)
        try:
            mesh.from_pydata([(-1e20, -0., 3), (1e-20, 0., 1), (1.25, 0., 2)], [], [])
            for axis in range(3):
                values = [v.co[axis] for v in mesh.vertices]
                self.assertEqual(_core.extent(ob, axis), max(values) - min(values))
            coordinates = [c for v in mesh.vertices for c in v.co]
            lo, hi = edit._span(coordinates)
            self.assertEqual(lo, [min(coordinates[a::3]) for a in range(3)])
            self.assertEqual(hi, [max(coordinates[a::3]) for a in range(3)])
            self.assertTrue(np.signbit(lo[1]))
            self.assertTrue(np.signbit(hi[1]))
            self.assertIsNone(edit._span([]))
        finally:
            bpy.data.objects.remove(ob)
            bpy.data.meshes.remove(mesh)

    def test_soup_matches_inferred_edges(self):
        inputs = []
        coordinates, faces = [], []
        for reflected in (False, True):
            me = bpy.data.meshes.new('source')
            me.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1, 2), (0, 2, 3)])
            matrix = Matrix.Diagonal((-1 if reflected else 1, 1, 1, 1))
            inputs.append((me, matrix))
            base = len(coordinates)
            coordinates.extend(matrix @ v.co for v in me.vertices)
            for polygon in me.polygons:
                ring = [base + i for i in polygon.vertices]
                faces.append(ring[::-1] if reflected else ring)
        expected = bpy.data.meshes.new('expected')
        expected.from_pydata(coordinates, [], faces)
        result = edit._soup(inputs)
        try:
            self.assertEqual(self.snapshot(expected), self.snapshot(result))
        finally:
            for mesh in [expected, result, *(me for me, _ in inputs)]:
                bpy.data.meshes.remove(mesh)

    def test_signaling_nan_attributes_follow_scalar_conversion(self):
        me = bpy.data.meshes.new('source')
        me.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
        inputs = np.array([0x7f801234, 0xff805678, 0x80000000], dtype=np.uint32).view(np.float32)
        for name, kind, domain in [('point', 'FLOAT', 'POINT'), ('face', 'FLOAT', 'FACE'), ('vector', 'FLOAT_VECTOR', 'FACE')]:
            a = me.attributes.new(name, kind, domain)
            a.data.foreach_set('vector' if kind == 'FLOAT_VECTOR' else 'value', inputs[:1] if name == 'face' else inputs)
        bm = edit._concat([(me, Matrix.Identity(4))])
        result = bpy.data.meshes.new('result')
        try:
            bm.to_mesh(result)
            for name, prop, width in [('point', 'value', 1), ('face', 'value', 1), ('vector', 'vector', 3)]:
                source = me.attributes[name]
                reference = np.array([c for d in source.data for c in d.vector] if width == 3 else [d.value for d in source.data], dtype=np.float32)
                actual = np.empty(len(source.data) * width, dtype=np.float32)
                result.attributes[name].data.foreach_get(prop, actual)
                self.assertEqual(actual.tobytes(), reference.tobytes())
        finally:
            bm.free()
            bpy.data.meshes.remove(result)
            bpy.data.meshes.remove(me)
