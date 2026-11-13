"""cut, hole and pocket: when no tool cuts into the part, they raise in strict mode
(SAND3D_STRICT=1, or `with strict()`), and otherwise warn and leave the part as it was."""
import os
import unittest
import warnings

import bpy

import sand3d as s3d
from sand3d.edit import MissedCut, NothingCut as NothingCutError, strict
from test_solids import closed_volume


class NothingCut(unittest.TestCase):
    """Strict mode: the behaviour of every release up to 1.6.3."""

    def setUp(self):
        s3d.empty_scene()
        self._strict = strict()
        self._strict.__enter__()

    def tearDown(self):
        self._strict.__exit__(None, None, None)

    def test_a_cut_that_misses_raises_and_leaves_the_part(self):
        plate = s3d.box("plate", 60, 40, 8)
        before = len(plate.data.vertices)
        with self.assertRaises(ValueError) as caught:
            s3d.cut(plate, s3d.at(s3d.cylinder("pin", 10, 20), x=80))
        self.assertEqual(str(caught.exception),
                         "cut: no tool cuts into 'plate' — they miss it, or only touch it (its box (-30, -20, 0) .. "
                         "(30, 20, 8); the tools' (75, -5, 0) .. (85, 5, 20))")
        self.assertEqual(len(plate.data.vertices), before)
        self.assertEqual([o.get("s3d_name") for o in bpy.data.objects], ["plate"], "the tool is used up")

    def test_hole_and_pocket_too(self):
        plate = s3d.box("plate", 60, 40, 8)
        with self.assertRaisesRegex(ValueError, r"^hole: no tool cuts into 'plate' — they miss it, or only touch it "):
            s3d.hole(plate, 5, on=s3d.Frame((100, 0, 0)))
        with self.assertRaisesRegex(ValueError, r"^pocket: no tool cuts into 'plate' — they miss it, or only touch it "):
            s3d.pocket(plate, s3d.circle(8), depth=2, on=s3d.Frame((100, 0, 8)))

    def test_one_tool_among_several_that_misses_is_dropped(self):
        """As in a pattern over an irregular part: the tools that cut stay, the others go."""
        plate = s3d.box("plate", 60, 40, 8)
        s3d.hole(plate, 5, on=[(0, 0), (100, 0)])
        self.assertTrue(closed_volume(plate)[0])
        self.assertLess(closed_volume(plate)[1], 60 * 40 * 8)

    def test_split_keeps_its_silence(self):
        b = s3d.box("b", 20, 20, 20)
        s3d.split(b, s3d.Frame((0, 0, 50)), keep="below")       # the plane misses: nothing to take away
        self.assertAlmostEqual(closed_volume(b)[1], 8000, places=3)

    def test_a_pocket_pattern_drops_a_frame_off_the_part(self):
        plate = s3d.box("plate", 60, 40, 8)
        s3d.pocket(plate, s3d.circle(8), depth=2, on=[s3d.Frame((0, 0, 8)), s3d.Frame((100, 0, 8))])
        self.assertLess(closed_volume(plate)[1], 60 * 40 * 8)
        with self.assertRaisesRegex(ValueError, r"^pocket: no tool cuts into 'plate'"):
            s3d.pocket(plate, s3d.circle(8), depth=2, on=[s3d.Frame((100, 0, 8)), s3d.Frame((-100, 0, 8))])

    def test_a_tool_that_takes_everything_says_so(self):
        """Not "they miss it": nothing would be left."""
        plate = s3d.box("plate", 20, 20, 4)
        with self.assertRaises(ValueError) as caught:
            s3d.cut(plate, s3d.at(s3d.box("big", 200, 200, 200), z=-100))
        self.assertEqual(str(caught.exception), "cut: the tools take all of 'plate' away — nothing would be left")

    def test_the_boxes_are_where_the_program_placed_them(self):
        plate = s3d.at(s3d.box("plate", 60, 40, 8), x=100)
        with self.assertRaises(ValueError) as caught:
            s3d.cut(plate, s3d.at(s3d.cylinder("pin", 10, 20), x=180))
        self.assertIn("(its box (70, -20, 0) .. (130, 20, 8); the tools' (175, -5, 0) .. (185, 5, 20))",
                      str(caught.exception))


class MissedCutWarns(unittest.TestCase):
    """By default a missed cut warns, as a boolean that misses does in Blender or in a CAD kernel."""

    def setUp(self):
        s3d.empty_scene()
        os.environ.pop("SAND3D_STRICT", None)

    def test_a_cut_that_misses_warns_and_leaves_the_part(self):
        plate = s3d.box("plate", 60, 40, 8)
        before = len(plate.data.vertices)
        with self.assertWarns(MissedCut) as caught:
            out = s3d.cut(plate, s3d.at(s3d.cylinder("pin", 10, 20), x=80))
        self.assertIs(out, plate)
        self.assertEqual(str(caught.warning),
                         "cut: no tool cuts into 'plate' — they miss it, or only touch it (its box (-30, -20, 0) .. "
                         "(30, 20, 8); the tools' (75, -5, 0) .. (85, 5, 20))")
        self.assertEqual(len(plate.data.vertices), before)
        self.assertEqual([o.get("s3d_name") for o in bpy.data.objects], ["plate"], "the tool is used up")

    def test_the_program_goes_on(self):
        plate = s3d.box("plate", 60, 40, 8)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", MissedCut)
            s3d.hole(plate, 5, on=s3d.Frame((100, 0, 0)))
        s3d.hole(plate, 5)
        self.assertTrue(closed_volume(plate)[0])
        self.assertLess(closed_volume(plate)[1], 60 * 40 * 8)

    def test_hole_and_pocket_warn_too(self):
        plate = s3d.box("plate", 60, 40, 8)
        with self.assertWarnsRegex(MissedCut, r"^hole: no tool cuts into 'plate'"):
            s3d.hole(plate, 5, on=s3d.Frame((100, 0, 0)))
        with self.assertWarnsRegex(MissedCut, r"^pocket: no tool cuts into 'plate'"):
            s3d.pocket(plate, s3d.circle(8), depth=2, on=s3d.Frame((100, 0, 8)))
        self.assertAlmostEqual(closed_volume(plate)[1], 60 * 40 * 8, places=3)

    def test_a_pocket_pattern_all_off_the_part_warns_once(self):
        plate = s3d.box("plate", 60, 40, 8)
        with warnings.catch_warnings(record=True) as seen:
            warnings.simplefilter("always")
            s3d.pocket(plate, s3d.circle(8), depth=2, on=[s3d.Frame((100, 0, 8)), s3d.Frame((-100, 0, 8))])
        self.assertEqual([type(w.message) for w in seen if issubclass(w.category, MissedCut)], [MissedCut])

    def test_the_environment_makes_it_strict(self):
        plate = s3d.box("plate", 60, 40, 8)
        os.environ["SAND3D_STRICT"] = "1"
        try:
            with self.assertRaises(NothingCutError):
                s3d.cut(plate, s3d.at(s3d.cylinder("pin", 10, 20), x=80))
        finally:
            del os.environ["SAND3D_STRICT"]

    def test_strict_off_overrides_the_environment(self):
        plate = s3d.box("plate", 60, 40, 8)
        os.environ["SAND3D_STRICT"] = "1"
        try:
            with strict(False), self.assertWarns(MissedCut):
                s3d.cut(plate, s3d.at(s3d.cylinder("pin", 10, 20), x=80))
        finally:
            del os.environ["SAND3D_STRICT"]


if __name__ == "__main__":
    unittest.main()
