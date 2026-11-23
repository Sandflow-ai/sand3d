"""Size variation is local geometry, before placement and anchor lookup."""
import unittest
import sand3d as s3d
from sand3d.edit import strict
from sand3d.frames import _bounds

class AtScale(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()

    def test_per_copy_and_common_scale(self):
        for scales, expected in [([1, 2, 3], [2, 4, 6]), (2, [4, 4, 4]), ((1, 2, 3), [2, 2, 2])]:
            s3d.empty_scene()
            out = s3d.at(s3d.box('proto', 2, 4, 6), on=s3d.grid(3, px=20), scale=scales)
            self.assertEqual([round((_bounds(o)[1]-_bounds(o)[0]).x) for o in out], expected)
            self.assertEqual([round(o.matrix_basis.translation.x) for o in out], [-20, 0, 20])

    def test_mismatch_keeps_prototype(self):
        ob = s3d.box('proto', 2, 4, 6)
        with self.assertRaisesRegex(ValueError, 'on has 3 frames but scale has 2 values'):
            s3d.at(ob, on=s3d.grid(3), scale=[1, 2])
        self.assertEqual(len(ob.data.vertices), 8)

    def test_invalid_second_prototype_keeps_the_whole_batch(self):
        import bpy

        part = s3d.box('box', 2, 2, 2)
        profile = s3d.rect(2, 2)
        group = s3d.group('group', s3d.box('child', 2, 2, 2))
        frames = s3d.grid(2, px=10)
        objects = set(bpy.data.objects)
        meshes = set(bpy.data.meshes)
        for invalid, factors, message in [(profile, 2, 'profile is not a solid'),
                                          (group, [2, (1, 2, 3)], 'scales by one factor')]:
            with self.subTest(message=message):
                with strict(True), self.assertRaisesRegex((TypeError, ValueError), message):
                    s3d.at([part, invalid], on=frames, scale=factors)
                self.assertEqual(set(bpy.data.objects), objects)
                self.assertEqual(set(bpy.data.meshes), meshes)
                with strict(False), self.assertWarnsRegex(UserWarning, message):
                    self.assertEqual(s3d.at([part, invalid], on=frames, scale=factors), [])
                self.assertEqual(set(bpy.data.objects), objects)
                self.assertEqual(set(bpy.data.meshes), meshes)

    def test_handle_and_group_rules(self):
        handle = s3d.assembly('plant', s3d.at(s3d.box('leaf', 2, 4, 6), x=5))
        copies = s3d.at(handle, on=s3d.grid(2, px=20), scale=[1, 2])
        self.assertEqual([round(_bounds(h.root)[1].x) for h in copies], [6, 12])
        for factor in [(1, 2, 3), 0, -1]:
            with self.assertRaisesRegex(ValueError, 'scale:'):
                s3d.at(copies[0], scale=factor)

    def test_anchor_after_scale_and_repeated_scale(self):
        ob = s3d.at(s3d.box('solid', 2, 4, 6), z=30, anchor='top', scale=(1, 2, 3))
        self.assertAlmostEqual((ob.matrix_basis @ _bounds(ob)[1]).z, 30)
        s3d.at(ob, scale=2)
        self.assertAlmostEqual((ob.matrix_basis @ _bounds(ob)[1]).z, 30)
        copies = s3d.at(ob, on=s3d.grid(2), scale=[1, 2], anchor='top')
        for copy in copies:
            self.assertAlmostEqual((copy.matrix_basis @ _bounds(copy)[1]).z, 30)

    def test_profiles_and_paths_rejected(self):
        for value in [s3d.rect(2, 4), s3d.arc(r=3)]:
            for on in [None, s3d.grid(2)]:
                with self.assertRaisesRegex(TypeError, 'scale:'):
                    s3d.at(value, on=on, scale=2)

    def test_two_fresh_processes(self):
        import os
        import subprocess
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        code = """
import sand3d as s3d
from sand3d.edit import strict
import sys
sys.path.insert(0, 'tests')
from harness import digest
ob = s3d.assembly('plant', s3d.box('leaf', 2, 4, 6))
s3d.at(ob, on=s3d.ring(5, 20), scale=s3d.vary(1, .2, 5, seed=3), anchor='top')
print(digest(None), flush=True)
import os
os._exit(0)
"""
        rows = [subprocess.run([sys.executable, '-c', code], cwd=root,
                env={**os.environ, 'PYTHONPATH': str(root / 'src'), 'PYTHONHASHSEED': seed},
                capture_output=True, text=True, check=True, timeout=60).stdout for seed in ('1', '7')]
        self.assertEqual(rows[0], rows[1])
