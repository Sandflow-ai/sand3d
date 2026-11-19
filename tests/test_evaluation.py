"""Private modifier graphs contain only their operands and leave no scene data."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import bpy
import sand3d as s3d
from sand3d import _core


class Evaluation(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()

    def test_boolean_graph_is_private_and_temporary(self):
        for i in range(40):
            s3d.box(f"other{i}", 1, 1, 1)
        base = s3d.at(s3d.box("base", 10, 10, 10), x=30, y=20)
        tool = s3d.at(s3d.box("tool", 4, 4, 20), x=30, y=20, z=-5)
        scene = bpy.context.scene
        counts = [len(bpy.data.scenes), len(bpy.data.collections)]
        observed = []

        convert = bpy.data.meshes.new_from_object

        def record(ob, **kwargs):
            observed.append(sorted(o.original.name for o in kwargs["depsgraph"].objects))
            return convert(ob, **kwargs)

        evaluate = _core.evaluated_mesh

        def inspect(*args, **kwargs):
            with patch.object(_core, "bpy", self.proxy(record)):
                return evaluate(*args, **kwargs)

        with patch.object(_core, "evaluated_mesh", inspect):
            s3d.cut(base, tool)
        self.assertTrue(observed)
        self.assertTrue(all(names == ["_s3d_base", "_s3d_tool"] for names in observed))
        self.assertIs(bpy.context.scene, scene)
        self.assertEqual(counts, [len(bpy.data.scenes), len(bpy.data.collections)])
        self.assertEqual(len(bpy.data.objects), 41)
        self.assertEqual(len(bpy.data.meshes), 41)
        self.assertEqual(base.name, "base")
        self.assertEqual(s3d.box("tool", 1, 1, 1).name, "tool")

    def test_failed_conversion_removes_private_objects(self):
        mesh = bpy.data.meshes.new("input")
        ob = bpy.data.objects.new("private", mesh)
        before = len(bpy.data.scenes)
        def fail(*args, **kwargs):
            raise RuntimeError("conversion")

        with patch.object(_core, "bpy", self.proxy(fail)):
            with self.assertRaisesRegex(RuntimeError, "conversion"):
                _core.evaluated_mesh(ob)
        self.assertEqual(len(bpy.data.scenes), before)
        self.assertNotIn("private", bpy.data.objects)
        self.assertEqual(mesh.users, 0)
        bpy.data.meshes.remove(mesh)

    @staticmethod
    def proxy(convert):
        return SimpleNamespace(
            context=bpy.context,
            data=SimpleNamespace(scenes=bpy.data.scenes, batch_remove=bpy.data.batch_remove,
                                 meshes=SimpleNamespace(new_from_object=convert)))
