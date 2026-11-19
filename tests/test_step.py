"""Feature dimensions and explicit mesh sampling are independent."""
import unittest
import sand3d as s3d


def triangles(ob):
    ob.data.calc_loop_triangles()
    return len(ob.data.loop_triangles)


class Step(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()

    def test_explicit_displace_step_decouples_noise_size(self):
        counts = []
        for size in (1, 8):
            ob = s3d.box('patch', 20, 20, 2)
            s3d.displace(ob, .1, size, step=4)
            counts.append(triangles(ob))
        self.assertEqual(*counts)
        ob = s3d.box('unrefined', 20, 20, 2)
        s3d.displace(ob, .1, 1, step=0)
        self.assertEqual(triangles(ob), 12)

    def test_tiny_noise_does_not_explode_topology(self):
        counts = []
        for size in (.01, .1):
            ob = s3d.box('leaf', 94, 40, 1)
            s3d.displace(ob, .001, size)
            counts.append(triangles(ob))
        self.assertEqual(*counts)
        self.assertLess(counts[0], 150000)

    def test_resolved_features_keep_their_sampling(self):
        a = s3d.box('auto', 20, 20, 2)
        b = s3d.box('explicit', 20, 20, 2)
        s3d.displace(a, .1, 8)
        s3d.displace(b, .1, 8, step=2)
        self.assertEqual(triangles(a), triangles(b))

    def test_explicit_step_wins_over_facets(self):
        with s3d.facets(8):
            a = s3d.box('a', 20, 20, 2)
            s3d.displace(a, .1, 8, step=2)
        b = s3d.box('b', 20, 20, 2)
        s3d.displace(b, .1, 8, step=2)
        self.assertEqual(triangles(a), triangles(b))
