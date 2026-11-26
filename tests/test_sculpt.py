"""The sculpting verbs: a solid's surface moved by places on its spine, never by its vertices."""
import unittest

import bpy  # noqa: F401  before bmesh, which only the bpy module provides
import bmesh

import sand3d as s3d


def volume(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    v = bm.calc_volume(signed=True)
    bm.free()
    return v


def extent(ob, axis):
    values = [v.co[axis] for v in ob.data.vertices]
    return max(values) - min(values)


def names(ob):
    return sorted(a.name for a in ob.data.attributes if a.name.startswith(("s3d_face:", "s3d_edge:")))


def egg():
    """A body along Y from -50 to 50, 40 wide, from z = 0 to 30, closed to points at both ends."""
    return s3d.body("egg", plan=s3d.spline([(-50, 0), (-30, 32), (0, 40), (30, 32), (50, 0)]),
                    top=s3d.spline([(-50, 15), (-30, 27), (0, 30), (30, 27), (50, 15)]),
                    bottom=s3d.spline([(-50, 15), (-30, 3), (0, 0), (30, 3), (50, 15)]))


class Spine(unittest.TestCase):

    def setUp(self):
        s3d.empty_scene()

    def test_a_body_runs_along_its_centre_line(self):
        ob = egg()
        start, end, middle = (s3d.spot(ob, u) for u in (0, 1, 0.5))
        self.assertAlmostEqual(start.origin.y, -50, places=4)
        self.assertAlmostEqual(end.origin.y, 50, places=4)
        self.assertAlmostEqual(middle.origin.z, 15, places=3)
        self.assertAlmostEqual(middle.z.y, 1, places=6, msg="on the spine, the frame's Z runs along it")

    def test_a_side_meets_the_surface_square_to_the_spine(self):
        ob = egg()
        belly, back, flank = (s3d.spot(ob, 0.5, side) for side in ("-Z", "+Z", "+X"))
        self.assertAlmostEqual(belly.origin.z, 0, delta=0.2)
        self.assertAlmostEqual(back.origin.z, 30, delta=0.2)
        self.assertAlmostEqual(flank.origin.x, 20, delta=0.2)
        self.assertAlmostEqual(belly.z.z, -1, places=6)
        tip = s3d.spot(ob, 1, "+Y")
        self.assertAlmostEqual(tip.origin.y, 50, delta=0.2)

    def test_a_spot_is_in_the_space_the_solid_is_in(self):
        ob = s3d.at(egg(), x=100, rz=90)
        tip = s3d.spot(ob, 1, "-X")      # the body's +Y end, turned to -X
        self.assertAlmostEqual(tip.origin.x, 50, delta=0.2)
        self.assertAlmostEqual(tip.z.x, -1, places=5)

    def test_any_other_solid_runs_along_the_longest_side_of_its_box(self):
        plank = s3d.box("plank", 20, 200, 10)
        self.assertAlmostEqual(s3d.spot(plank, 0).origin.y, -100, places=5)
        ball = s3d.sphere("ball", 30)
        self.assertAlmostEqual(s3d.spot(ball, 1).origin.z, 30, places=5, msg="a tie goes to Z")

    def test_a_sweep_runs_along_its_path_and_tapers(self):
        horn = s3d.sweep("horn", s3d.circle(20), [(0, 0, 0), (0, 0, 100)], scale=[(0, 1), (0.5, 1.5), (1, 0.2)])
        self.assertAlmostEqual(s3d.spot(horn, 0.5).origin.z, 50, places=4)
        self.assertAlmostEqual(s3d.spot(horn, 0.5, "+X").origin.x, 15, delta=0.1)
        self.assertAlmostEqual(s3d.spot(horn, 1, "+X").origin.x, 2, delta=0.1)
        trunk = s3d.wire("trunk", [(0, 0, 0), (0, 0, 80)], [(0, 30), (1, 10)])
        self.assertAlmostEqual(s3d.spot(trunk, 0, "+X").origin.x, 15, delta=0.1)
        self.assertAlmostEqual(s3d.spot(trunk, 1, "+X").origin.x, 5, delta=0.1)

    def test_scale_scales_the_spine(self):
        ob = egg()
        s3d.scale(ob, 2)
        self.assertAlmostEqual(s3d.spot(ob, 1).origin.y, 100, places=4)

    def test_a_copy_keeps_it(self):
        ob = egg()
        twin = s3d.at(s3d.copy(ob), z=50)
        self.assertAlmostEqual(s3d.spot(twin, 0.5).origin.z, 65, places=3)

    def test_what_it_refuses(self):
        ob = egg()
        with self.assertRaisesRegex(ValueError, "from 0"):
            s3d.spot(ob, 1.5)
        with self.assertRaisesRegex(ValueError, "names no side"):
            s3d.spot(ob, 0.5, "under")
        with self.assertRaisesRegex(ValueError, "on is where"):
            s3d.grab(ob, (0, 0, 5), 10, None)


class Sculpt(unittest.TestCase):

    def setUp(self):
        s3d.empty_scene()

    def test_grab_pulls_the_centre_and_leaves_the_rest(self):
        ob = egg()
        before = names(ob)
        s3d.grab(ob, (0, 20, 0), 15, on=s3d.spot(ob, 1, "+Y"))
        self.assertAlmostEqual(max(v.co.y for v in ob.data.vertices), 70, delta=0.5)
        self.assertAlmostEqual(min(v.co.y for v in ob.data.vertices), -50, places=4)
        self.assertEqual(names(ob), before, "faces and edges keep their names")

    def test_inflate_swells_round_on_or_everywhere(self):
        ob = egg()
        v0 = volume(ob)
        s3d.inflate(ob, 5, r=20, on=s3d.spot(ob, 0.5, "-Z"))
        self.assertAlmostEqual(min(v.co.z for v in ob.data.vertices), -5, delta=0.3)
        self.assertAlmostEqual(max(v.co.z for v in ob.data.vertices), 30, delta=0.01)
        v1 = volume(ob)
        self.assertGreater(v1, v0)
        s3d.inflate(ob, -1)
        self.assertLess(volume(ob), v1)

    def test_pinch_narrows_a_ring_and_never_crosses_the_axis(self):
        ob = egg()
        s3d.pinch(ob, 8, r=15, on=s3d.spot(ob, 0.5))
        waist = [v.co.x for v in ob.data.vertices if abs(v.co.y) < 0.5]
        self.assertAlmostEqual(max(waist), 12, delta=0.5)
        s3d.pinch(ob, 100, r=15, on=s3d.spot(ob, 0.5))
        self.assertGreater(max(v.co.x for v in ob.data.vertices if abs(v.co.y) < 0.5), 0)

    def test_bend_carries_the_spine(self):
        ob = s3d.wire("tail", [(0, 0, 0), (0, 100, 0)], 10)
        s3d.bend(ob, 90, axis="+Y", toward="+Z")
        tip = s3d.spot(ob, 1)
        self.assertGreater(tip.origin.z, 50, "the spine curls with the surface")
        self.assertAlmostEqual(tip.z.z, 1, places=1)

    def test_relax_evens_out_a_spike(self):
        ob = egg()
        s3d.grab(ob, (0, 0, 10), 6, on=s3d.spot(ob, 0.5, "+Z"))
        peak = max(v.co.z for v in ob.data.vertices)
        s3d.relax(ob, r=20, on=s3d.spot(ob, 0.5, "+Z"))
        self.assertLess(max(v.co.z for v in ob.data.vertices), peak - 1.5)

    def test_crease_presses_a_line_in(self):
        ob = egg()
        s3d.crease(ob, [s3d.spot(ob, 0.5, "+Z-X"), s3d.spot(ob, 0.5, "+Z"), s3d.spot(ob, 0.5, "+Z+X")], 3, 5)
        on_line = [v.co.z for v in ob.data.vertices if abs(v.co.y) < 0.3 and abs(v.co.x) < 2]
        self.assertLess(max(on_line), 28)

    def test_stamp_raises_its_profile(self):
        ob = egg()
        top = s3d.spot(ob, 0.5, "+Z")
        s3d.stamp(ob, s3d.circle(10), 2, on=[top, top.move(x=10)])
        self.assertAlmostEqual(max(v.co.z for v in ob.data.vertices), 32, delta=0.3)
        far = [v.co.z for v in ob.data.vertices if abs(v.co.y) > 20 and v.co.z > 25]
        self.assertLess(max(far), 30.01, "nothing moves away from the frames")

    def test_clay_fuses_parts_into_one_even_closed_surface(self):
        torso = egg()
        s3d.material(torso, "plastic", color="#888888")
        arm = s3d.at(s3d.wire("arm", [(0, 0, 0), (60, 0, 0)], 12), x=10, z=15)
        before = s3d.spot(torso, 1).origin
        s3d.clay(torso, arm, detail=2)
        self.assertEqual(sorted(o.name for o in bpy.data.objects), ["egg"], "the arm is used up")
        bm = bmesh.new()
        bm.from_mesh(torso.data)
        lengths = sorted(e.calc_length() for e in bm.edges)
        self.assertTrue(all(len(e.link_faces) == 2 for e in bm.edges), "closed")
        bm.free()
        self.assertLess(lengths[-1], 2 * 2 * 1.5, "no long edge left")
        self.assertAlmostEqual(max(v.co.x for v in torso.data.vertices), 70, delta=2)
        self.assertEqual(names(torso), [], "faces and edges lose their names")
        self.assertEqual([m.name for m in torso.data.materials], ["plastic #888888"])
        self.assertEqual(s3d.spot(torso, 1).origin, before, "the spine stays")
        with self.assertRaisesRegex(ValueError, "detail of"):
            s3d.clay(torso, detail=0.01)

    def test_describe_reads_the_sections_along_the_spine(self):
        card = s3d.describe(egg())
        self.assertIn("spine +Y", card)
        row = next(line for line in card.splitlines() if line.startswith("-z"))
        self.assertEqual(row.split()[6], "15", "at u = 0.5 the belly is 15 below the spine")


class Anatomy(unittest.TestCase):

    def setUp(self):
        s3d.empty_scene()

    def test_a_muscle_runs_between_its_two_joints(self):
        bones = s3d.skeleton(shoulder=(88, 0, 35), elbow=(100, -17, -42))
        m = s3d.muscle("biceps", bones.shoulder, bones.elbow, 40, flat=0.5, side="-Y")
        self.assertLess((s3d.spot(m, 0).origin - bones.shoulder).length, 1e-3)
        self.assertLess((s3d.spot(m, 1).origin - bones.elbow).length, 1e-3)
        across = (s3d.spot(m, 0.5, "+X").origin - s3d.spot(m, 0.5, "-X").origin).length
        through = (s3d.spot(m, 0.5, "-Y").origin - s3d.spot(m, 0.5, "+Y").origin).length
        self.assertAlmostEqual(across, 40, delta=2, msg="belly thick across")
        self.assertAlmostEqual(through, 20, delta=2, msg="flattened toward its side")

    def test_a_skeleton_mirrors_and_names_what_it_lacks(self):
        bones = s3d.skeleton(wrist=(58, -76, -106))
        self.assertEqual(tuple(bones.mirrored("x").wrist), (-58, -76, -106))
        with self.assertRaisesRegex(AttributeError, "no joint 'knee'"):
            bones.knee
        with self.assertRaisesRegex(ValueError, "same place"):
            s3d.muscle("m", bones.wrist, bones.wrist, 10)
        with self.assertRaisesRegex(ValueError, "square to it"):
            s3d.muscle("m", (0, 0, 0), (0, 0, 50), 10, side="+Z")


if __name__ == "__main__":
    unittest.main()
