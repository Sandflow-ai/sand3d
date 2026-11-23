"""export's trace: what a program built, beside the file."""
import json
import os
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

import bpy
import bmesh

import sand3d as s3d


def traced(root, suffix=".glb"):
    with tempfile.TemporaryDirectory() as tmp:
        s3d.export(root, Path(tmp) / ("x" + suffix), trace=Path(tmp) / "x.json")
        return json.loads((Path(tmp) / "x.json").read_text(encoding="utf-8"))


def chest():
    """A box and a lid hinged on its +X face."""
    box = s3d.box("box", 100, 60, 10)
    lid = s3d.at(s3d.box("lid", 100, 60, 4), z=10)
    s3d.joint("hinge", lid, box.face("+X"), range=(0, 90))
    return box, lid


def close(test, got, want):
    for g, w in zip(got, want):
        test.assertAlmostEqual(g, w, places=6)


class Trace(unittest.TestCase):

    def setUp(self):
        s3d.empty_scene()

    def test_where_it_goes(self):
        """None by default; True, 1 or SAND3D_TRACE=1 beside the file; a path wins; False none;
        a failed export none, and no stale one left."""
        box, lid = chest()
        lone = s3d.group("lone", lid)
        with tempfile.TemporaryDirectory() as tmp:
            s3d.export(box, Path(tmp) / "a.glb")
            with mock.patch.dict(os.environ, SAND3D_TRACE="1"):
                s3d.export(box, Path(tmp) / "b.glb")
                s3d.export(box, str(Path(tmp) / "c.glb"), trace=str(Path(tmp) / "mine.json"))
                s3d.export(box, Path(tmp) / "d.glb", trace=False)
                s3d.export(box, Path(tmp) / "lone.glb")
                self.assertRaises(ValueError, s3d.export, lone, Path(tmp) / "lone.glb")
            s3d.export(s3d.assembly("kit", box), Path(tmp) / "e.stl", trace=True)
            s3d.export(box, Path(tmp) / "f.stl", trace=1)
            self.assertEqual(sorted(p.name for p in Path(tmp).glob("*.json")),
                             ["b.trace.json", "e.trace.json", "f.trace.json", "mine.json"])

    def test_a_box_in_metres(self):
        t = traced(s3d.box("box", 100, 60, 10))
        self.assertEqual((t["name"], t["bbox"], t["open_edges"], t["volume"], t["parts"]),
                         ("box", [[-0.05, -0.03, 0], [0.05, 0.03, 0.01]], 0, 6e-5, []))
        self.assertEqual(t["faces"], {"bottom": 0.006, "side": 0.0032, "top": 0.006}, "box.top is top: once")
        self.assertEqual(t["edges"], ["bottom", "side", "top"])
        self.assertAlmostEqual(traced(s3d.cylinder("pin", 3, 10))["volume"], 6.988e-8, delta=1e-10)

    def test_a_lamp_in_every_format(self):
        lamp = s3d.group("lamp", s3d.box("base", 40, 40, 10), s3d.light("bulb"), s3d.light("spot", "spot"))
        with tempfile.TemporaryDirectory() as tmp:
            for suffix in ("glb", "ifc", "obj", "stl", "urdf", "usda"):
                with self.subTest(suffix=suffix), warnings.catch_warnings():
                    warnings.filterwarnings("ignore", message="export: .* leaves out .*", category=UserWarning)
                    path = Path(tmp) / f"lamp.{suffix}"
                    s3d.export(lamp, path, trace=True)
                    self.assertGreater(path.stat().st_size, 0)
                    trace = json.loads(path.with_suffix(".trace.json").read_text(encoding="utf-8"))
                    self.assertEqual([p["name"] for p in trace["parts"]], ["base", "bulb", "spot"])
                    self.assertIsNotNone(trace["bbox"])
                    for light in trace["parts"][1:]:
                        self.assertIsNone(light["bbox"])
                        self.assertIsNone(light["volume"])

    def test_in_metres_whatever_the_unit(self):
        s3d.units("cm")
        t = traced(s3d.box("box", 10, 6, 1))
        self.assertEqual((t["bbox"][1][0], t["volume"]), (0.05, 6e-5))

    def test_names_after_a_hole_and_a_join(self):
        part = s3d.box("a_very_long_part_name_that_goes_past_what_blender_keeps", 40, 20, 10)
        s3d.hole(part, 6, on=part.face("top"))
        s3d.join(part, s3d.at(s3d.box("b", 10, 10, 10), z=10))
        t = traced(part)
        self.assertIn("hole.side", t["faces"])
        self.assertIn("b.top", t["faces"], "after a join, top is two parts' tops")
        for name in t["edges"]:
            part.edge(name)

    def test_volume_only_when_closed(self):
        cube = s3d.box("cube", 10, 10, 10)
        bm = bmesh.new()
        bm.from_mesh(cube.data)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.normal.z > 0.5], context="FACES_ONLY")
        bm.to_mesh(cube.data)
        bm.free()
        t = traced(cube)
        self.assertEqual((t["open_edges"], t["volume"]), (4, None))

    def test_parts_joints_and_pose(self):
        """The lid under its hinge, as the GLB nests it; a hinge on a +X face turns about X."""
        box, lid = chest()
        s3d.material(lid, "oak")
        s3d.pose(lid, 90)
        t = traced(s3d.at(s3d.group("chest", box, lid), x=100))
        self.assertEqual([[p["name"], [q["name"] for q in p["parts"]]] for p in t["parts"]], [["box", ["lid"]]])
        self.assertEqual(t["parts"][0]["bbox"][0][0], 0.05)
        lid = t["parts"][0]["parts"][0]
        j = lid["joints"][0]
        self.assertEqual((lid["material"], j["name"], j["kind"], j["on"], j["range"], j["value"]),
                         ("oak", "hinge", "revolute", "box", [0, 90], 90))
        close(self, j["axis"], (1, 0, 0))

    def test_a_part_once(self):
        """Under a hung part but jointed on the root: once, nested by its joint as the GLB nests it."""
        box, lid = chest()
        knob = s3d.at(s3d.box("knob", 5, 5, 5), z=14)
        knob.parent = lid
        s3d.joint("turn", knob, box.face("top"), range=(0, 90))
        t = traced(box)
        self.assertEqual([[p["name"], [q["name"] for q in p["parts"]]] for p in t["parts"]], [["knob", []], ["lid", []]])

    def test_two_joints_on_one_child(self):
        """Each axis after the motions before it: tilting does not move the pan axis."""
        base = s3d.box("base", 40, 40, 10)
        head = s3d.at(s3d.box("head", 20, 20, 20), z=10)
        s3d.joint("pan", head, base.face("top"), range=(-90, 90))
        s3d.joint("tilt", head, base.face("top"), axis="+X", range=(0, 90))
        s3d.pose(head, 90, joint="tilt")
        pan, tilt = traced(base)["parts"][0]["joints"]
        close(self, pan["axis"], (0, 0, 1))
        close(self, tilt["axis"], (1, 0, 0))

    def test_slides_in_metres_and_followers(self):
        """A prismatic joint's range and value in metres; a follower's range from what it follows."""
        base = s3d.box("base", 40, 40, 10)
        cap = s3d.at(s3d.cylinder("cap", 20, 10), z=10)
        s3d.joint("turn", cap, base.face("top"), range=(0, 720))
        s3d.joint("lift", cap, base.face("top"), kind="prismatic", follows="turn", ratio=3 / 360)
        slide = s3d.at(s3d.box("slide", 10, 10, 10), x=30)
        s3d.joint("rail", slide, base.face("+X"), kind="prismatic", range=(0, 50))
        s3d.pose(slide, 20)
        cap, slide = traced(base)["parts"]
        self.assertEqual(cap["joints"][1]["range"], [0, 0.006])
        self.assertEqual((slide["joints"][0]["range"], slide["joints"][0]["value"]), ([0, 0.05], 0.02))

    def test_in_the_world(self):
        """Under a moved, turned parent, boxes and axes are where the exported files put them."""
        box, lid = chest()
        whole = s3d.group("chest", box, lid)
        s3d.at(s3d.group("outer", whole), x=500, rz=90)
        t = traced(whole)
        close(self, (t["bbox"][0][0], t["bbox"][1][0], *t["parts"][0]["parts"][0]["joints"][0]["axis"]),
              (0.47, 0.53, 0, 1, 0))

    def test_kinds(self):
        """Continuous: no range; free: no axis; the root's own joint, not in the export: none."""
        box = s3d.box("box", 40, 40, 10)
        wheel = s3d.at(s3d.cylinder("wheel", 10, 5), z=10)
        s3d.joint("spin", wheel, box.face("top"), kind="continuous")
        ball = s3d.at(s3d.sphere("ball", 10), x=40)
        s3d.joint("float", ball, box.face("+X"), kind="free")
        t = traced(box)
        self.assertEqual([(p["joints"][0]["kind"], p["joints"][0]["range"] is None, p["joints"][0]["axis"] is None)
                          for p in t["parts"]], [("free", True, True), ("continuous", True, False)])
        self.assertEqual(traced(wheel)["joints"], [])

    def test_what_hangs_outside_the_export(self):
        """A group holding a lid hinged on a box outside it: the STL writes the lid, so does the trace."""
        box, lid = chest()
        t = traced(s3d.group("lone", lid), ".stl")
        self.assertEqual(([p["name"] for p in t["parts"]], t["parts"][0]["joints"][0]["on"]), (["lid"], "box"))


if __name__ == "__main__":
    unittest.main()
