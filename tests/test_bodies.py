"""Bodies: flesh as the surface of fused pieces, skinned to bones, posed, pressed where parts meet."""
import unittest

import bpy  # noqa: F401  before bmesh, which only the bpy module provides
import bmesh
import numpy as np

import sand3d as s3d
from sand3d import bodies

J = {"hip": (0, 0, 0), "chest": (0, 0, 40), "neck": (0, 0, 70), "top": (0, 0, 100),
     "shoulder": (22, 0, 60), "elbow": (50, 0, 40), "wrist": (72, 0, 14)}
BONES = {"pelvis": ("hip", "chest", None), "chest": ("chest", "neck", "pelvis"), "head": ("neck", "top", "chest"),
         "upperarm": ("shoulder", "elbow", "chest"), "forearm": ("elbow", "wrist", "upperarm")}


def pieces():
    trunk = s3d.stack("trunk", [(0, 40, 30, 0, 2.5, 0), (40, 50, 34, 0, 2.5, 0.1), (70, 30, 26, 0, 2, 0)])
    head = s3d.lobe("head", (0, -2, 88), (13, 15, 17))
    arm = s3d.limb("arm", [J["shoulder"], J["elbow"], J["wrist"]], [(0, 9, 9), (40, 8, 7), (70, 5, 5)])
    arm = s3d.fuse(arm, s3d.lobe("cap", J["shoulder"], 12), r=6)
    return s3d.fuse(s3d.fuse(trunk, head, r=8), arm, r=3, wide=(J["shoulder"], 9, 12, 30))


def body():
    ob = s3d.flesh("body", pieces(), cell=3, soften=3)
    return s3d.rig(ob, J, BONES, s3d.chain("trunk", "pelvis", s3d.band("chest", -8, 8, normal="+Z")),
                   s3d.chain("head", "head"),
                   s3d.chain(["arm", "cap"], "chest", s3d.band("upperarm", -14, -4), s3d.band("forearm", -6, 6),
                             whole={"cap": "upperarm"}),
                   linear=[(("pelvis", "chest"), ("upperarm", "forearm"))], smooth=2, seam=(4, 8))


def coords(ob):
    co = np.empty(3 * len(ob.data.vertices), dtype=np.float32)
    ob.data.vertices.foreach_get("co", co)
    return co.reshape(-1, 3).astype(np.float64)


def closed(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    ok = all(e.is_manifold for e in bm.edges) and bm.calc_volume(signed=True) > 0
    bm.free()
    return ok


class Flesh(unittest.TestCase):

    def setUp(self):
        s3d.empty_scene()

    def test_fused_pieces_make_one_closed_surface_facing_out(self):
        ob = s3d.flesh("body", pieces(), cell=3, soften=3)
        self.assertTrue(closed(ob))
        v = coords(ob)
        self.assertLess(abs(v[:, 2].max() - 105), 3)            # the head's top
        self.assertLess(abs(v[:, 0].max() - 77), 4)             # the wrist's end, rounded
        self.assertEqual(sorted(a.name for a in ob.data.attributes if a.name.startswith("s3d_face:")),
                         ["s3d_face:body.flesh", "s3d_face:flesh"])

    def test_a_ball_is_a_ball(self):
        ob = s3d.flesh("ball", s3d.lobe("ball", (5, 0, 0), 20), cell=2, soften=0)
        r = np.linalg.norm(coords(ob) - [5, 0, 0], axis=1)
        self.assertLess(np.abs(r - 20).max(), 0.05)

    def test_pieces_further_apart_than_r_stay_apart(self):
        a, b = s3d.lobe("a", (0, 0, 0), 10), s3d.lobe("b", (26, 0, 0), 10)
        ob = s3d.flesh("two", s3d.fuse(a, b, r=3), cell=1.5, soften=0, box=((-20, -20, -20), (45, 20, 20)))
        self.assertLess(coords(ob)[:, 0].max(), 12)             # one closed piece is kept: the other is apart

    def test_crisp_keeps_a_gap_the_softening_would_close(self):
        def fingers(**more):
            a = s3d.spindle("a", (-4, 0, 0), (-4, 0, 30), [(0, 2.5, 2.5, 2), (1, 2.5, 2.5, 2)], up="+Y")
            b = s3d.spindle("b", (4, 0, 0), (4, 0, 30), [(0, 2.5, 2.5, 2), (1, 2.5, 2.5, 2)], up="+Y")
            ob = s3d.flesh("two", s3d.fuse(a, b, r=0.5), cell=1, soften=2.5, box=((-14, -10, -10), (14, 10, 40)), **more)
            v = coords(ob)
            return np.abs(v[np.abs(v[:, 2] - 15) < 1, 0]).min()          # how near the middle plane the surface comes
        self.assertLess(fingers(), 0.6)                                  # softened: one mass (the other is dropped,
        self.assertGreater(fingers(crisp=[((0, 0, 15), 20, 30)]), 1.0)   # or they merge); crisp: two, a gap between
        with self.assertRaisesRegex(ValueError, "far is beyond its near"):
            s3d.flesh("x", s3d.lobe("a", (0, 0, 0), 8), crisp=[((0, 0, 0), 5, 5)])

    def test_what_flesh_refuses(self):
        with self.assertRaisesRegex(ValueError, "pieces of flesh"):
            s3d.flesh("x", s3d.sphere("s", 10))
        with self.assertRaisesRegex(ValueError, "two pieces are named"):
            s3d.flesh("x", s3d.lobe("a", (0, 0, 0), 5), s3d.lobe("a", (8, 0, 0), 5))
        with self.assertRaisesRegex(ValueError, "beyond the box"):
            s3d.flesh("x", s3d.lobe("a", (0, 0, 0), 30), box=((-10, -10, -10), (10, 10, 10)))
        with self.assertRaisesRegex(ValueError, "go in order"):
            s3d.stack("t", [(10, 5, 5, 0, 2, 0), (0, 5, 5, 0, 2, 0)])
        with self.assertRaisesRegex(ValueError, "same place"):
            s3d.limb("l", [(0, 0, 0), (0, 0, 0)], [(0, 3, 3), (5, 3, 3)])


class Skin(unittest.TestCase):

    def setUp(self):
        s3d.empty_scene()

    def test_every_vertex_follows_at_most_four_bones_that_share_it_whole(self):
        r = bodies._body(body(), "test").rig
        self.assertEqual(r.order.shape[1], 4)
        self.assertTrue(np.allclose(r.w4.sum(1), 1))
        v = bodies._body(bpy.data.objects["body"], "test").base
        hand = np.linalg.norm(v - J["wrist"], axis=1) < 6
        self.assertTrue(np.all(r.order[hand, 0] == r.index["forearm"]))
        self.assertTrue(np.all(r.w4[hand, 0] > 0.99))

    def test_a_flat_piece_claims_nothing_far_from_it(self):
        # a measured palm (wide, thin, bent) on a long stick down to a ball: far from a limb its field jumps where
        # the nearest point of its curve changes; made a distance by its slope there, it read a few millimetres
        # 200 mm away — a hand's bone then carried a foot's skin
        joints = {"a": (139.31, -12.71, 46.82), "b": (153.16, -21.38, 44.35), "c": (164.47, -25.96, 33.81),
                  "top": (139, -12, 40), "o": (60, 17, -185)}
        rows = [(0, 7.57, 9.43), (8.44, 7.96, 11.18), (16.89, 9.65, 16.0), (25.33, 7.28, 12.36), (33.78, 5.25, 14.76)]
        palm = s3d.limb("palm", [joints["a"], joints["b"], joints["c"]], rows, up=(0.4659, 0.0047, 0.8848))
        stick = s3d.spindle("stick", joints["top"], joints["o"], [(0, 5, 5, 2), (1, 5, 5, 2)], up="+Y")
        ob = s3d.flesh("two", palm, stick, s3d.lobe("ball", joints["o"], 20), cell=1.5, soften=1.5)
        s3d.rig(ob, joints, {"root": ("o", "top", None), "hand": ("a", "c", "root")},
                s3d.chain(["stick", "ball"], "root"), s3d.chain("palm", "hand"))
        b = bodies._body(ob, "test")
        grid = b.pieces["palm"]
        axes = b.axes
        P = np.stack(np.meshgrid(*[a[::3] for a in axes], indexing="ij"), -1).reshape(-1, 3)
        curve = np.array([joints[k] for k in "abc"], float)
        far = np.min(np.linalg.norm(P[:, None] - curve[None], axis=-1), 1) > 80
        self.assertGreater(far.sum(), 1000)
        self.assertGreaterEqual(float(grid(P[far]).min()), 30.0)
        W = np.zeros((len(b.base), 2))
        np.put_along_axis(W, b.rig.order, b.rig.w4, 1)
        ball = np.linalg.norm(b.base - joints["o"], axis=1) < 40
        self.assertEqual(float(W[ball, b.rig.index["hand"]].max()), 0.0)

    def test_the_rest_posture_moves_nothing_and_a_posture_starts_from_rest(self):
        ob = body()
        rest = coords(ob)
        s3d.posture(ob, aim={"upperarm": (1, 0, 0)})
        once = coords(ob)
        s3d.posture(ob, aim={"upperarm": (1, 0, 0)})
        self.assertTrue(np.array_equal(once, coords(ob)))
        s3d.posture(ob)
        self.assertLess(np.abs(coords(ob) - rest).max(), 1e-4)

    def test_an_aimed_bone_points_there_and_carries_its_children(self):
        ob = body()
        rest = coords(ob)
        hand = np.linalg.norm(rest - J["wrist"], axis=1) < 6
        s3d.posture(ob, aim={"upperarm": "+X", "forearm": "+X"}, press=False)
        moved = coords(ob)[hand].mean(0)
        length = np.linalg.norm(np.subtract(J["elbow"], J["shoulder"])) + np.linalg.norm(np.subtract(J["wrist"], J["elbow"]))
        self.assertLess(np.linalg.norm(moved - (np.array(J["shoulder"]) + [length, 0, 0])), 3)
        far = rest[:, 0] < -5                                   # the trunk's other side stays
        self.assertLess(np.abs(coords(ob)[far] - rest[far]).max(), 1e-3)

    def test_a_turn_is_about_the_joint(self):
        ob = body()
        rest = coords(ob)
        s3d.posture(ob, turn={"head": [("z", 90)]}, press=False)
        top = rest[:, 2] > 95
        a, b = rest[top], coords(ob)[top]
        self.assertLess(np.abs(b[:, 0] + a[:, 1]).max(), 0.2)   # (x, y) → (−y, x)
        self.assertLess(np.abs(b[:, 1] - a[:, 0]).max(), 0.2)

    def test_parts_pressed_together_meet_instead_of_crossing(self):
        ob = body()
        b = bodies._body(ob, "test")
        aim = {"upperarm": (-0.35, 0, 1), "forearm": (-0.8, 0, 0.6)}        # the forearm into the head
        s3d.posture(ob, aim=aim, press=False)
        through = coords(ob)
        s3d.posture(ob, aim=aim)
        pressed = coords(ob)
        head = bodies._true(b, "head")
        hand = b.rig.order[:, 0] == b.rig.index["forearm"]
        deep = -head(through[hand]).min()
        self.assertGreater(deep, 4)                             # it did go in
        self.assertLess(-head(pressed[hand]).min(), 0.85 * deep)   # and is pushed back out,
        skull = b.rig.order[:, 0] == b.rig.index["head"]
        self.assertGreater(np.linalg.norm(pressed[skull] - through[skull], axis=1).max(), 1)   # the head giving way too
        self.assertTrue(closed(ob))

    def test_the_floor_is_hard(self):
        ob = body()
        s3d.posture(ob, root=(0, 0, -20), floor=-8)
        self.assertGreater(coords(ob)[:, 2].min(), -8 - 0.05)

    def test_detail_rides_the_bones(self):
        plain = body_posed_plain({"head": [("x", 90)]})
        s3d.empty_scene()
        ob = body()
        n = len(ob.data.vertices)
        rest = coords(ob)
        s3d.detail(ob, np.tile([0.0, 0.0, 1.0], (n, 1)))
        self.assertLess(np.abs(coords(ob) - rest - [0, 0, 1]).max(), 1e-5)
        s3d.posture(ob, turn={"head": [("x", 90)]}, press=False)
        top = rest[:, 2] > 95                                   # the head turned 90° about X: its up is now -Y
        shift = coords(ob)[top] - plain[top]
        self.assertLess(np.abs(shift - [0, -1, 0]).max(), 0.05)
        with self.assertRaisesRegex(ValueError, "one offset"):
            s3d.detail(ob, np.zeros((n - 1, 3)))

    def test_what_rig_and_posture_refuse(self):
        ob = s3d.flesh("body", pieces(), cell=3, soften=3)
        with self.assertRaisesRegex(ValueError, "rig it first"):
            s3d.posture(ob)
        with self.assertRaisesRegex(ValueError, "every piece is in one chain"):
            s3d.rig(ob, J, BONES, s3d.chain("trunk", "pelvis"))
        with self.assertRaisesRegex(ValueError, "listed before it"):
            s3d.rig(ob, J, {"a": ("hip", "chest", "b"), "b": ("chest", "neck", None)}, s3d.chain("trunk", "a"))
        ob = body()
        with self.assertRaisesRegex(ValueError, "not one; bones"):
            s3d.posture(ob, aim={"tail": "+X"})
        with self.assertRaisesRegex(ValueError, "both aimed and turned"):
            s3d.posture(ob, aim={"head": "+X"}, turn={"head": [("z", 5)]})
        with self.assertRaisesRegex(ValueError, "a body made by flesh"):
            s3d.posture(s3d.box("b", 5, 5, 5))


def body_posed_plain(turn):
    """The same body without detail, in a posture: its vertices."""
    s3d.empty_scene()
    ob = body()
    s3d.posture(ob, turn=turn, press=False)
    return coords(ob)


if __name__ == "__main__":
    unittest.main()
