"""Read-only group queries respect nested placements and reject ambiguous faces."""
import unittest
import sand3d as s3d


class GroupSurface(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()
        s3d.units('mm')

    def nested(self):
        part = s3d.box('part', 10, 10, 10)
        inner = s3d.at(s3d.group('inner', part), x=20)
        root = s3d.at(s3d.group('root', inner), x=30, rz=90)
        return root, part

    def test_face_names_alternative(self):
        root, _ = self.nested()
        with self.assertRaisesRegex(ValueError, 'face:.*root.*bbox.*part'):
            root.face('top')

    def test_snap_nested_group(self):
        root, part = self.nested()
        hits = s3d.snap(root, [(30,20,30)], direction='-Z')
        self.assertEqual(len(hits), 1)
        self.assertAlmostEqual(hits[0].origin.x, 30, places=4)
        self.assertAlmostEqual(hits[0].origin.y, 20, places=4)
        self.assertAlmostEqual(hits[0].origin.z, 10, places=4)
        self.assertEqual(s3d.snap(root, [(100,100,30)], direction='-Z'), [])
        self.assertIsNotNone(part.data)

    def test_scatter_nested_group(self):
        root, _ = self.nested()
        sites = s3d.scatter(20, root, seed=5)
        again = s3d.scatter(20, [root], seed=5)
        self.assertEqual([tuple(f.origin) for f in sites], [tuple(f.origin) for f in again])
        for f in sites:
            self.assertTrue(25-1e-4 <= f.origin.x <= 35+1e-4)
            self.assertTrue(15-1e-4 <= f.origin.y <= 25+1e-4)
            self.assertTrue(-1e-4 <= f.origin.z <= 10+1e-4)

    def test_empty_group(self):
        root = s3d.group('empty')
        for fn in [lambda: s3d.snap(root, [(0,0,0)]), lambda: s3d.scatter(4, root)]:
            with self.assertRaisesRegex(ValueError, '(snap|scatter):.*no mesh'):
                fn()
