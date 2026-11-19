"""copy: an independent copy, deep, with the same mesh, names and placement."""
import unittest

import bpy

import sand3d as s3d
from harness import world
from sand3d.joints import joints_of
from test_solids import closed_volume, edges


def mesh_of(ob):
    me = ob.data
    names = sorted((a.name, tuple(d.value for d in a.data)) for a in me.attributes if a.name.startswith("s3d_"))
    return [tuple(v.co) for v in me.vertices], [tuple(p.vertices) for p in me.polygons], names


class Copy(unittest.TestCase):

    def setUp(self):
        s3d.empty_scene()

    def test_shared_mesh_detaches_on_edits(self):
        operations = [lambda o: s3d.scale(o, 2),
                      lambda o: s3d.dent(o, [(0, 0, 10)], 4, 1),
                      lambda o: s3d.bend(o, 15),
                      lambda o: s3d.twist(o, 15),
                      lambda o: s3d.taper(o, .7),
                      lambda o: s3d.displace(o, .2, 5),
                      lambda o: s3d.smooth(o, 30)]
        for operation in operations:
            with self.subTest(operation=operation):
                s3d.empty_scene()
                original = s3d.box("part", 10, 10, 10)
                twin = s3d.copy(original)
                before = mesh_of(original)
                operation(twin)
                self.assertEqual(mesh_of(original), before)
                self.assertIsNot(original.data, twin.data)

    def test_inherited_materials_detach(self):
        original = s3d.box("part", 10, 10, 10)
        twin = s3d.copy(original)
        a = s3d.group("a", original)
        b = s3d.group("b", twin)
        s3d.material(a, "oak")
        s3d.material(b, "steel")
        self.assertIsNot(original.data, twin.data)
        self.assertNotEqual(original.data.materials[0], twin.data.materials[0])

    def test_shared_colour_export_restores_data(self):
        from sand3d import materials
        original = s3d.box("part", 10, 10, 10)
        s3d.material(original, "plastic", color=lambda x, y, z: (abs(x)/10, .2, .3))
        twin = s3d.copy(original)
        root = s3d.group("pair", original, twin)
        mesh = original.data
        count = len(bpy.data.meshes)
        with self.assertRaisesRegex(RuntimeError, "test"):
            with materials.exporting(root):
                self.assertIs(original.data, twin.data)
                self.assertIsNot(original.data, mesh)
                raise RuntimeError("test")
        self.assertIs(original.data, mesh)
        self.assertIs(twin.data, mesh)
        self.assertEqual(len(bpy.data.meshes), count)

    def test_common_parent_material_keeps_sharing(self):
        original = s3d.box("part", 10, 10, 10)
        twin = s3d.copy(original)
        root = s3d.group("pair", original, twin)
        s3d.material(root, "oak")
        self.assertIs(original.data, twin.data)
        s3d.material(root, "steel")
        self.assertIs(original.data, twin.data)

    def test_glb_instances_and_repeated_export(self):
        import json
        import struct
        import tempfile
        from pathlib import Path
        for mode in ("material", "vertex"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                s3d.empty_scene()
                original = s3d.box("part", 10, 10, 10)
                s3d.material(original, "plastic", color=lambda x, y, z: (.2, .4, abs(z)/10))
                twin = s3d.at(s3d.copy(original), x=20, rz=30)
                root = s3d.group("pair", original, twin)
                mesh = original.data
                count = len(bpy.data.meshes)
                path = Path(directory) / "part.glb"
                s3d.export(root, path, colors=mode)
                first = path.read_bytes()
                size = struct.unpack_from("<I", first, 12)[0]
                doc = json.loads(first[20:20+size])
                self.assertEqual(len(doc["meshes"]), 1)
                self.assertEqual(sum("mesh" in n for n in doc["nodes"]), 2)
                s3d.export(root, path, colors=mode)
                self.assertEqual(path.read_bytes(), first)
                self.assertIs(original.data, mesh)
                self.assertIs(twin.data, mesh)
                self.assertEqual(len(bpy.data.meshes), count)

    def test_lay_detaches_before_refinement_and_placement(self):
        for refine in (0, 8):
            with self.subTest(step=refine):
                s3d.empty_scene()
                original = s3d.box("part", 10, 10, 2)
                twin = s3d.copy(original)
                before = mesh_of(original)
                carrier = s3d.box("carrier", 40, 40, 5)
                s3d.lay(twin, carrier, step=refine)
                self.assertEqual(mesh_of(original), before)
                self.assertIsNot(original.data, twin.data)

    def test_a_list_is_copied_element_by_element(self):
        """A list is worth its elements: `copy([a, b])` raised AttributeError on the list."""
        base = s3d.box("base", 40, 40, 10)
        arm = s3d.at(s3d.box("arm", 10, 10, 30), z=10)
        s3d.joint("hinge", arm, base.face("top"), axis="+X", range=(0, 90))
        copies = s3d.copy([base, [arm]])
        self.assertEqual([c["s3d_name"] for c in copies], ["base", "arm"])
        self.assertTrue(all(c is not o for c, o in zip(copies, (base, arm))))
        self.assertEqual([mesh_of(c) for c in copies], [mesh_of(base), mesh_of(arm)])
        from sand3d.joints import parent_of
        self.assertIs(parent_of(copies[1]), copies[0], "the arm's copy hangs on the base's copy")
        self.assertIs(parent_of(arm), base, "the originals are untouched")
        self.assertEqual(s3d.copy([]), [])

    def test_list_name_dict_spans_roots_and_joints(self):
        from sand3d.joints import parent_of
        base = s3d.box("base", 20, 20, 5)
        arm = s3d.box("arm", 5, 5, 20)
        s3d.joint("hinge", arm, base.face("top"), axis="+X", range=(0, 90))
        old_mesh_name = base.data.name
        twin, lever = s3d.copy([base, arm], name={"base": "foot", "arm": "lever", "hinge": "pivot"})
        self.assertEqual([twin.name, lever.name], ["foot", "lever"])
        self.assertIs(parent_of(lever), twin)
        self.assertEqual([j["name"] for j in joints_of(lever)], ["pivot"])
        self.assertEqual(base.data.name, old_mesh_name)
        count = len(bpy.data.objects)
        with self.assertRaisesRegex(TypeError, "dict"):
            s3d.copy([base], name="foot")
        with self.assertRaisesRegex(ValueError, "holds no part"):
            s3d.copy([base, arm], name={"base": "foot", "absent": "new"})
        self.assertEqual(len(bpy.data.objects), count)

    def test_same_mesh_names_and_placement(self):
        plate = s3d.at(s3d.extrude("plate", s3d.rect(40, 20, r=3), 5), x=10, z=4, rz=30)
        s3d.hole(plate, 4, on=(5, 0))
        twin = s3d.copy(plate)
        self.assertIsNot(twin, plate)
        self.assertEqual(mesh_of(twin), mesh_of(plate))
        self.assertEqual(twin["s3d_name"], "plate")
        self.assertEqual(world(twin), world(plate))
        self.assertIs(twin.data, plate.data)

    def test_the_original_is_untouched_and_independent(self):
        lid = s3d.extrude("lid", s3d.rect(40, 30, r=4), 3)
        before = mesh_of(lid)
        twin = s3d.copy(lid)
        s3d.hole(twin, 5, on=(0, 0))
        s3d.at(twin, z=16)
        self.assertEqual(mesh_of(lid), before)
        self.assertEqual(tuple(lid.matrix_basis.translation), (0.0, 0.0, 0.0))

    def test_a_tool_kept_with_copy(self):
        """The report's lid: a copy cuts the seat, the lid itself stays — the same meshes as
        building the lid twice."""
        def build(with_copy):
            s3d.empty_scene()
            box = s3d.box("box", 50, 40, 20)
            if with_copy:
                lid = s3d.extrude("lid", s3d.rect(40, 30, r=4), 3)
                s3d.cut(box, s3d.at(s3d.copy(lid), z=18.5))
                s3d.at(lid, z=26)
            else:
                s3d.cut(box, s3d.at(s3d.extrude("lid", s3d.rect(40, 30, r=4), 3), z=18.5))
                lid = s3d.at(s3d.extrude("lid", s3d.rect(40, 30, r=4), 3), z=26)
            return mesh_of(box), mesh_of(lid), world(lid)
        self.assertEqual(build(True), build(False))

    def test_copies_keep_the_name_edges_answer_to(self):
        """Same sand3d name: after a join, `fillet(edges="leg")` reaches every copy."""
        top = s3d.box("top", 60, 30, 4)
        leg = s3d.at(s3d.cylinder("leg", 6, 40), x=-20, z=-40)
        s3d.join(top, leg, s3d.at(s3d.copy(leg), x=20, z=-40))
        self.assertEqual(edges(top, "leg"), 2 * edges(s3d.cylinder("probe", 6, 40), "bottom"))

    def test_a_group_is_copied_with_its_children(self):
        a = s3d.at(s3d.box("a", 10, 10, 10), x=-10)
        b = s3d.at(s3d.sphere("b", 8), x=10, z=5)
        g = s3d.at(s3d.group("pair", a, b), y=30, rz=45)
        twin = s3d.copy(g)
        self.assertEqual(twin.type, "EMPTY")
        self.assertEqual(twin["s3d_name"], "pair")
        self.assertEqual(world(twin), world(g))
        self.assertEqual(len(twin.children), 2)
        self.assertEqual(len(g.children), 2, "the original keeps its children")
        pairs = sorted(((c["s3d_name"], tuple(map(tuple, world(c)))) for c in twin.children))
        originals = sorted(((c["s3d_name"], tuple(map(tuple, world(c)))) for c in g.children))
        self.assertEqual(pairs, originals)
        self.assertEqual({c.data for c in twin.children}, {c.data for c in g.children})
        s3d.at(twin, x=100)
        moved = sorted(((c["s3d_name"], tuple(map(tuple, world(c)))) for c in g.children))
        self.assertEqual(moved, originals, "moving the copy leaves the original where it was")

    def test_a_handle_is_copied_with_its_anchors(self):
        table = s3d.assembly("table", s3d.at(s3d.box("top", 100, 60, 4), z=68),
                             s3d.cylinder("leg", 5, 68), top=72, seat=s3d.Frame((0, 0, 72)))
        s3d.attach(table, "lamp", s3d.at(s3d.dome("shade", 20, 10), z=table.top))
        twin = s3d.copy(table)
        self.assertIsInstance(twin, s3d.Handle)
        self.assertIsNot(twin.root, table.root)
        self.assertEqual(twin.top, 72)
        self.assertEqual(tuple(twin.seat.origin), (0.0, 0.0, 72.0))
        self.assertIsNot(twin.seat, table.seat)
        self.assertEqual(len(twin.root.children), 3)   # top, leg and the attached lamp
        self.assertEqual(len([o for o in bpy.data.objects if o.get("s3d_name") == "shade"]), 2)

    def test_anchors_are_copied_exactly_and_objects_map_to_their_twins(self):
        """A frame anchor is the same frame to the bit; an anchor that is a part of the
        assembly is that part's copy; namedtuples and dicts are copied too."""
        from collections import namedtuple
        Corner = namedtuple("Corner", "x y")
        lid = s3d.at(s3d.box("lid", 20, 20, 2), z=28)
        seat = s3d.Frame((1, 2, 3)).turn(rx=17.3, ry=-41.9, rz=73.1)
        h = s3d.assembly("crate", s3d.box("body", 20, 20, 28), lid, seat=seat, lid=lid, corner=Corner(1, 2),
                         holes={"a": s3d.Frame((0, 0, 5))}, sizes=[1, 2.5])
        twin = s3d.copy(h)
        self.assertEqual(tuple(map(tuple, twin.seat.matrix)), tuple(map(tuple, seat.matrix)))
        self.assertIsNot(twin.seat.origin, seat.origin)
        self.assertIsNot(twin.lid, lid)
        self.assertIs(twin.lid.parent, twin.root)
        self.assertEqual((twin.corner, type(twin.corner)), (Corner(1, 2), Corner))
        self.assertIsNot(twin.holes["a"], h.holes["a"])
        self.assertEqual(twin.sizes, [1, 2.5])

    def test_a_handle_subclass_stays_one(self):
        class Crate(s3d.Handle):
            def volume(self):
                return 42
        h = Crate(s3d.group("c", s3d.box("b", 1, 1, 1)), top=1)
        self.assertEqual(s3d.copy(h).volume(), 42)

    def test_a_copy_of_a_merged_part_is_merged(self):
        """The copy is the same object: what `merge` marked stays marked."""
        m = s3d.merge(s3d.box("m", 10, 10, 10), s3d.at(s3d.box("n", 10, 10, 10), x=5))
        twin = s3d.copy(m)
        self.assertTrue(twin.get("s3d~merged"))
        s3d.hole(twin, 3, on=(0, 0))
        self.assertTrue(closed_volume(twin)[0])
        self.assertAlmostEqual(closed_volume(twin)[1], 15 * 10 * 10 - 3.14 * 1.5 ** 2 * 10, delta=2)

    def test_a_copy_named(self):
        plate = s3d.extrude("plate", s3d.rect(40, 20), 5)
        twin = s3d.copy(plate, name="plate_2")
        self.assertEqual((twin["s3d_name"], twin.name, twin.data.name), ("plate_2", "plate_2", "plate_2"))
        self.assertEqual((plate["s3d_name"], plate.name), ("plate", "plate"), "the original keeps its name")
        self.assertEqual(mesh_of(twin), mesh_of(plate))
        handle = s3d.copy(s3d.assembly("pair", plate, twin), name="pairs")
        self.assertEqual(handle.root["s3d_name"], "pairs")

    def test_a_copy_names_what_it_holds_and_its_joints_export_under_those_names(self):
        """A door on its hinge, its mirror image the other door: the group, its panel and
        its joint named through the copy, the URDF exports two links, two joints and two
        visuals under those names — an unnamed copy exports `right_door_2`, `right_hinge_2`."""
        import tempfile
        import xml.etree.ElementTree as ET
        from pathlib import Path
        cab = s3d.box("cab", 600, 600, 850)
        panel = s3d.transform(s3d.box("panel", 30, 290, 800), x=15, y=-145)
        door = s3d.at(s3d.group("right_door", panel), on=s3d.local(cab, 300, 300, 25))
        s3d.joint("right_hinge", door, s3d.local(cab, 300, 300, 25), axis="+Z", range=(0, 90))
        left = s3d.transform(s3d.copy(door, name={"right_door": "left_door", "panel": "left_panel",
                                                  "right_hinge": "left_hinge"}), mirror="y")
        self.assertEqual((left["s3d_name"], left.name), ("left_door", "left_door"))
        self.assertEqual([(c["s3d_name"], c.data.name) for c in left.children], [("left_panel", "left_panel")])
        self.assertEqual([j["name"] for j in joints_of(left)], ["left_hinge"])
        self.assertEqual([j["name"] for j in joints_of(door)], ["right_hinge"], "the original's joint keeps its name")
        root = s3d.group("cabinet", cab, door, left)
        with tempfile.TemporaryDirectory() as tmp:
            s3d.export(root, Path(tmp) / "cabinet.urdf")
            robot = ET.parse(Path(tmp) / "cabinet.urdf").getroot()
        self.assertEqual({link.get("name") for link in robot.findall("link")}, {"cabinet", "right_door", "left_door"})
        self.assertEqual({j.get("name") for j in robot.findall("joint")}, {"right_hinge", "left_hinge"})
        visuals = {v.get("name") for link in robot.findall("link") for v in link.findall("visual")}
        self.assertTrue({"panel", "left_panel"} <= visuals, visuals)

    def test_a_name_the_copy_holds_nothing_of_is_refused(self):
        box = s3d.box("box", 10, 10, 10)
        with self.assertRaisesRegex(ValueError, "holds no part, group or joint"):
            s3d.copy(box, name={"box": "crate", "lid": "cover"})
        with self.assertRaisesRegex(TypeError, "a string, or"):
            s3d.copy(box, name=3)
        with self.assertRaisesRegex(TypeError, "a name is a string"):
            s3d.copy(box, name={"box": None})
        self.assertEqual(len(bpy.data.objects), 1, "a refused name makes no copy")


if __name__ == "__main__":
    unittest.main()
