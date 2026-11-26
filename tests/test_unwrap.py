"""UVs read off the shape: what is found, where it opens, and that lengths are kept."""
import json
import unittest

import numpy as np
import sand3d as s3d
from sand3d import uvs


def islands(ob):
    return json.loads(ob[uvs.REPORT])["islands"]


def kinds(ob):
    return sorted(i["kind"] for i in islands(ob))


def corners(ob):
    uv = np.empty(2 * len(ob.data.loops), np.float32)
    ob.data.uv_layers[0].data.foreach_get("uv", uv)
    return uv.reshape(-1, 2)


def scale(ob):
    """Millimetres per unit of UV, read on every edge of every face."""
    uv, me = corners(ob), ob.data
    out = []
    for p in me.polygons:
        loops = list(p.loop_indices)
        for a, b in zip(loops, loops[1:] + loops[:1]):
            d = (me.vertices[me.loops[a].vertex_index].co - me.vertices[me.loops[b].vertex_index].co).length
            out.append(d / float(np.hypot(*(uv[a] - uv[b]))))
    return np.array(out)


class Unwrap(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()

    def test_a_box_is_six_planes_at_one_scale(self):
        ob = s3d.unwrap(s3d.box("b", 40, 30, 20))
        self.assertEqual(kinds(ob), ["flat"] * 6)
        s = scale(ob)
        self.assertLess(np.ptp(s) / s.mean(), 1e-3)

    def test_a_cylinder_unrolls_into_a_rectangle_open_at_the_back(self):
        ob = s3d.unwrap(s3d.cylinder("c", 40, 30))
        self.assertEqual(kinds(ob), ["flat", "flat", "wall"])
        for seam, axis, sign in (("+Y", 1, 1), ("-X", 0, -1)):
            s3d.unwrap(ob, seam=seam)
            uv, ends = corners(ob), {}
            for p in ob.data.polygons:
                loops = list(p.loop_indices)
                for a, b in zip(loops, loops[1:] + loops[:1]):
                    v, w = ob.data.loops[a].vertex_index, ob.data.loops[b].vertex_index
                    ends.setdefault(frozenset((v, w)), []).append({v: tuple(uv[a]), w: tuple(uv[b])})
            opened = [e for e, (x, y) in ends.items()
                      if any(np.hypot(*np.subtract(x[v], y[v])) > 1e-4 for v in e)
                      and len({round(ob.data.vertices[v].co.z) for v in e}) == 2]
            self.assertEqual(len(opened), 1)
            for v in opened[0]:
                self.assertGreater(sign * ob.data.vertices[v].co[axis], 19)

    def test_a_tapered_side_is_a_cone(self):
        self.assertEqual(kinds(s3d.unwrap(s3d.cone("c", 40, 30, d2=20))), ["cone", "flat", "flat"])

    def test_a_fillet_stays_on_its_wall(self):
        ob = s3d.fillet(s3d.extrude("lid", s3d.rect(60, 50, r=12), 30), 4, edges="top")
        s3d.unwrap(ob)
        self.assertEqual(kinds(ob), ["flat", "flat", "wall+fillet"])
        self.assertLess(max(i["stretch"] for i in islands(ob)), 1.05)

    def test_every_island_keeps_its_orientation_and_no_two_meet(self):
        a = s3d.fillet(s3d.extrude("a", s3d.rect(60, 40, r=8), 20), 3, edges="top")
        b = s3d.at(s3d.sphere("b", 30), x=80)
        c = s3d.transform(s3d.copy(a, "c"), mirror="x")
        root = s3d.group("all", a, b, c)
        s3d.unwrap(root)
        triangles = []
        for ob in (a, b, c):
            uv = corners(ob)
            self.assertGreaterEqual(uv.min(), 0)
            self.assertLessEqual(uv.max(), 1)
            ob.data.calc_loop_triangles()
            triangles += [uv[list(t.loops)] for t in ob.data.loop_triangles]
        self.assertFalse(uvs._overlaps(np.array(triangles)))
        flat = np.array([uvs._cross(t[1] - t[0], t[2] - t[0]) for t in triangles])
        n = len(c.data.loop_triangles)                       # a mirror image: text on it still reads
        self.assertTrue((flat[:-n] > 0).all())
        self.assertTrue((flat[-n:] < 0).all())

    def test_the_program_unit_changes_nothing(self):
        def uv(unit, k):
            s3d.empty_scene()
            s3d.units(unit)
            ob = s3d.unwrap(s3d.extrude("e", s3d.rect(60 * k, 40 * k, r=8 * k), 20 * k))
            at, me = corners(ob), ob.data                    # by place: a face may start at another corner
            return {(p.index, *(round(c / k, 2) for c in me.vertices[me.loops[l].vertex_index].co)): at[l]
                    for p in me.polygons for l in p.loop_indices}
        a, b = uv("mm", 1), uv("m", 0.001)
        self.assertEqual(set(a), set(b))
        self.assertLess(max(np.abs(a[k] - b[k]).max() for k in a), 1e-4)

    def test_a_sliver_folds_onto_its_neighbour(self):
        ob = s3d.unwrap(s3d.box("sheet", 200, 100, 0.2))
        self.assertLess(len(islands(ob)), 6)
        self.assertAlmostEqual(max(i["stretch"] for i in islands(ob)), 1, places=3)

    def test_a_strip_longer_than_the_atlas_is_cut(self):
        ob = s3d.unwrap(s3d.extrude("edge", s3d.rect(400, 300, r=20), 10))
        self.assertGreater(kinds(ob).count("wall"), 1)
        s = scale(ob)
        self.assertLess(np.ptp(s) / s.mean(), 1e-3)

    def test_what_is_hidden_is_scaled_and_what_is_seen_is_not(self):
        outer = s3d.box("outer", 100, 100, 100)
        s3d.shell(outer, 5)
        inner = s3d.at(s3d.box("inner", 40, 40, 40), z=20)
        s3d.unwrap([outer, inner], hidden=0.5)
        self.assertEqual({i["scale"] for i in islands(inner)}, {0.5})
        self.assertEqual(sorted(i["scale"] for i in islands(outer)), [0.5] * 6 + [1] * 6)
        s3d.material(outer, "glass")
        s3d.unwrap([outer, inner], hidden=0.5)
        self.assertEqual({i["scale"] for i in islands(inner)}, {1})

    def test_arguments(self):
        ob = s3d.box("b", 10, 10, 10)
        with self.assertRaisesRegex(ValueError, "seam="):
            s3d.unwrap(ob, seam="back")
        with self.assertRaisesRegex(ValueError, "margin="):
            s3d.unwrap(ob, margin=2)
        with self.assertRaisesRegex(ValueError, "hidden="):
            s3d.unwrap(ob, hidden=0)
        with self.assertRaisesRegex(TypeError, "a part, a group"):
            s3d.unwrap([])


if __name__ == "__main__":
    unittest.main()
