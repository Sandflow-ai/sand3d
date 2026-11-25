"""scale on a group or an assembly: the whole thing, by one factor, about its own origin."""
import os
import subprocess
import sys
import unittest
from pathlib import Path

import bpy
from mathutils import Vector

import sand3d as s3d
from harness import world

ROOT = Path(__file__).resolve().parent.parent


def under(root):
    """Every mesh point under `root`, in `root`'s own space, by object name."""
    inv = world(root).inverted()
    out = {}
    for o in [root, *root.children_recursive]:
        if o.type == "MESH":
            m = inv @ world(o)
            out[o.name] = [m @ v.co for v in o.data.vertices]
    return out


def topology(ob):
    me = ob.data
    return len(me.vertices), len(me.edges), [tuple(p.vertices) for p in me.polygons]


def close(case, a, b, places=4):
    case.assertEqual(len(a), len(b))
    for p, q in zip(a, b):
        case.assertLess((Vector(p) - Vector(q)).length, 10 ** -places, f"{tuple(p)} != {tuple(q)}")


def plant():
    """Nested, turned groups under an assembly that is itself placed and turned."""
    leaf = s3d.at(s3d.box("leaf", 10, 2, 4), x=20, rz=30)
    stalk = s3d.at(s3d.cylinder("stalk", 3, 25), x=-4, ry=15)
    bough = s3d.at(s3d.group("bough", leaf, stalk), x=5, y=3, z=2, rz=45)
    ball = s3d.at(s3d.sphere("ball", 6), z=10, anchor="bottom")
    crown = s3d.at(s3d.group("crown", bough, ball), x=40, rx=20, rz=10)
    pot = s3d.cylinder("pot", 30, 20)
    h = s3d.assembly("plant", pot, s3d.at(crown, z=20), top=s3d.bbox(pot, "+Z"), height=20)
    s3d.at(h, x=100, y=-50, rz=25)
    plant.ball, plant.pot = ball, pot
    return h, leaf, bough, crown


class ScaleGroup(unittest.TestCase):

    def setUp(self):
        s3d.empty_scene()

    def test_every_point_goes_from_p_to_sp_and_the_root_stays(self):
        h, leaf, bough, crown = plant()
        before, placed = under(h.root), world(h.root).copy()
        self.assertIs(s3d.scale(h, 1.5), h)
        after = under(h.root)
        self.assertEqual(sorted(before), sorted(after))
        for name in before:
            close(self, after[name], [1.5 * p for p in before[name]], places=3)
        self.assertEqual(world(h.root), placed)
        for o in [h.root, *h.root.children_recursive]:  # no scale left anywhere: baked
            self.assertEqual(tuple(round(c, 6) for c in o.scale), (1.0, 1.0, 1.0))

    def test_a_group_scales_as_a_handle_does(self):
        h, leaf, bough, crown = plant()
        before = under(crown)
        rot = [o.rotation_euler.copy() for o in [crown, *crown.children_recursive]]
        self.assertIs(s3d.scale(crown, 0.5), crown)
        after = under(crown)
        for name in before:
            close(self, after[name], [0.5 * p for p in before[name]], places=3)
        self.assertEqual([o.rotation_euler.copy() for o in [crown, *crown.children_recursive]], rot)

    def test_copies_scale_apart(self):
        """The bough case: copy a group, scale each copy by its own factor."""
        h, leaf, bough, crown = plant()
        ref = under(bough)
        copies = [s3d.copy(bough), s3d.copy(bough)]
        for c, f in zip(copies, (0.8, 1.2)):
            s3d.scale(c, f)
        close(self, sum(under(bough).values(), []), sum(ref.values(), []), places=5)   # the original is untouched
        for c, f in zip(copies, (0.8, 1.2)):
            close(self, sum(under(c).values(), []), [f * p for p in sum(ref.values(), [])], places=3)

    def test_a_shared_mesh_is_not_scaled_twice_nor_outside(self):
        a = s3d.box("a", 10, 10, 10)
        b = s3d.at(s3d.box("b", 10, 10, 10), x=20)
        outside = s3d.at(s3d.box("c", 10, 10, 10), y=40)
        b.data = outside.data = a.data
        g = s3d.group("g", a, b)
        s3d.scale(g, 2)
        self.assertAlmostEqual(max(v.co.x for v in a.data.vertices), 10)
        self.assertAlmostEqual(max(v.co.x for v in outside.data.vertices), 5)
        self.assertAlmostEqual(b.location.x, 40)

    def test_a_later_at_keeps_the_scaled_place(self):
        h, leaf, bough, crown = plant()
        s3d.scale(h, 2)
        here = world(leaf).translation.copy()
        s3d.at(leaf, rz=30)                              # the same turn: nothing moves
        close(self, [world(leaf).translation], [here])
        s3d.at(leaf, rz=90)                              # a new turn about the same, scaled, place
        close(self, [world(leaf).translation], [here])
        self.assertAlmostEqual(leaf["s3d~place"]["x"], 40)
        s3d.at(leaf, y=1)                                # new lengths are in program units
        self.assertAlmostEqual(leaf.matrix_basis.translation.y, 1)
        top = world(plant.ball).translation.copy()
        s3d.at(plant.ball, x=0)                          # an anchored part keeps its scaled anchor point
        close(self, [world(plant.ball).translation], [top])

    def test_frames_and_anchors_stay_snapshots(self):
        h, leaf, bough, crown = plant()
        f, top, side = h.top, h.height, s3d.bbox(h, "+X")
        origin, side_origin = f.origin.copy(), side.origin.copy()
        s3d.scale(h, 2)
        self.assertEqual(h.top.origin, origin)           # the handle's frame is a snapshot
        self.assertEqual(h.height, top)                  # numbers are numbers
        self.assertEqual(side.origin, side_origin)
        now = s3d.bbox(h, "+X")                          # read again: the scaled box
        self.assertNotEqual(tuple(round(c, 3) for c in now.origin), tuple(round(c, 3) for c in side_origin))

    def test_materials_shading_and_topology_are_kept(self):
        h, leaf, bough, crown = plant()
        s3d.material(h, "oak")
        s3d.material(leaf, "plastic", color="#2e8b57")
        s3d.smooth(plant.ball, 30)
        meshes = [o for o in [h.root, *h.root.children_recursive] if o.type == "MESH"]
        before = {o.name: (topology(o), [m.name for m in o.data.materials], o.get("s3d~smooth"),
                           [p.use_smooth for p in o.data.polygons]) for o in meshes}
        parents = {o.name: o.parent.name for o in h.root.children_recursive}
        s3d.scale(h, 3)
        after = {o.name: (topology(o), [m.name for m in o.data.materials], o.get("s3d~smooth"),
                          [p.use_smooth for p in o.data.polygons]) for o in meshes}
        self.assertEqual(after, before)
        self.assertEqual({o.name: o.parent.name for o in h.root.children_recursive}, parents)
        self.assertEqual(s3d.copy(leaf).data.materials[0].name, leaf.data.materials[0].name)

    def test_a_group_is_scaled_by_one_positive_number(self):
        h, leaf, bough, crown = plant()
        before = under(h.root)
        cases = [((1, 2, 1), ValueError, r"one factor, not \(1, 2, 1\) .* shear .* s3d\.scale\(part, \(sx, sy, sz\)\)"),
                 ([2, 2, 2], ValueError, r"one factor"),
                 (0, ValueError, r"would shrink to a point: give a factor s > 0"),
                 (-2, ValueError, r"mirror=\"xyz\"\) then s3d\.scale\(plant, 2\)"),
                 (True, TypeError, r"one number s > 0, not True"),
                 (float("inf"), ValueError, r"a finite number"),
                 ("2", TypeError, r"one number s > 0")]
        for s, error, message in cases:
            with self.subTest(s=s), self.assertRaisesRegex(error, message):
                s3d.scale(h, s)
            with self.subTest(s=s, group=True), self.assertRaises(error):
                s3d.scale(crown, s)
        self.assertEqual(under(h.root), before)

    def test_joints_inside_are_refused_before_anything_moves(self):
        h, leaf, bough, crown = plant()
        s3d.joint("sway", bough, plant.pot.face("top"), axis="+X", range=(-10, 10))
        before = under(h.root)
        with self.assertRaisesRegex(ValueError, r"^scale: 'bough' moves by its joint 'sway': scaling 'plant' would "
                                                r"move its pivot .* scale 'plant' before declaring its joints"):
            s3d.scale(h, 2)
        self.assertEqual(under(h.root), before)

    def test_a_joint_across_the_boundary_is_refused(self):
        h, leaf, bough, crown = plant()
        lid = s3d.at(s3d.box("lid", 30, 30, 2), z=60)      # outside the plant, hangs on its pot
        s3d.joint("flap", lid, plant.pot.face("top"), axis="+X", range=(0, 90))
        before = under(h.root)
        with self.assertRaisesRegex(ValueError, r"^scale: 'lid' hangs on 'pot', inside 'plant', by its joint 'flap'"):
            s3d.scale(h, 2)
        self.assertEqual(under(h.root), before)
        s3d.scale(crown, 2)                                # the pot is not in the crown

    def test_a_group_carried_by_a_jointed_part_is_refused(self):
        base = s3d.box("base", 40, 40, 10)
        arm = s3d.at(s3d.group("arm", s3d.box("bar", 5, 5, 30), s3d.at(s3d.group("head", s3d.sphere("bulb", 8)),
                                                                          z=30)), z=10)
        s3d.joint("shoulder", arm, base.face("top"), axis="+X", range=(0, 90))
        head = arm.children[1] if arm.children[1].type == "EMPTY" else arm.children[0]
        with self.assertRaisesRegex(ValueError, r"^scale: 'head' is carried by 'arm', which moves by its joint "
                                                r"'shoulder': scale 'head' before it goes into the mechanism"):
            s3d.scale(head, 2)

    def test_a_follower_is_refused(self):
        h, leaf, bough, crown = plant()
        base = s3d.box("base", 40, 40, 10)
        cap = s3d.at(s3d.cylinder("cap", 10, 5), z=10)
        s3d.joint("turn", cap, base.face("top"), kind="revolute", range=(0, 720))
        nut = s3d.at(s3d.cylinder("nut", 6, 3), z=15)
        s3d.joint("lift", nut, base.face("top"), kind="prismatic", follows="turn", ratio=3 / 360)
        g = s3d.group("screw", cap)                        # the leader inside, its follower outside
        with self.assertRaisesRegex(ValueError, r"^scale: 'cap' moves by its joint 'turn'"):
            s3d.scale(g, 2)

    def test_solids_scale_as_before(self):
        b = s3d.box("b", 10, 10, 10)
        child = s3d.at(s3d.box("c", 2, 2, 2), x=20)
        child.parent = b
        self.assertIs(s3d.scale(b, (2, 1, -1)), b)
        self.assertAlmostEqual(max(v.co.x for v in b.data.vertices), 10)
        self.assertAlmostEqual(min(v.co.z for v in b.data.vertices), -10)
        self.assertAlmostEqual(child.location.x, 20)       # a solid's children are not a group's
        self.assertAlmostEqual(max(v.co.x for v in child.data.vertices), 1)
        with self.assertRaisesRegex(TypeError, r"a profile is not a solid"):
            s3d.scale(s3d.rect(10, 10), 2)

    def test_in_two_fresh_processes(self):
        code = """
import sys
sys.path.insert(0, 'tests')
import sand3d as s3d
from harness import digest
from test_scale_group import plant
h, leaf, bough, crown = plant()
twins = [s3d.copy(bough) for _ in range(3)]
for t, f in zip(twins, s3d.vary(1, 0.2, 3, seed=4)):
    s3d.scale(t, f)
s3d.scale(h, 1.7)
s3d.at(leaf, rz=80)
print(digest(None), flush=True)
"""
        runs = [subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                               env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONHASHSEED": seed},
                               capture_output=True, text=True, check=True, timeout=120).stdout for seed in ("11", "37")]
        self.assertTrue(runs[0].strip())
        self.assertEqual(runs[0], runs[1])


if __name__ == "__main__":
    unittest.main()
