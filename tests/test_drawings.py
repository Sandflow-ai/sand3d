"""A drawing lies on a surface: one period as an image, repeated over every face of the part."""
import json
import math
import os
import struct
import tempfile
import unittest
import bpy
import numpy as np
import sand3d as s3d
from sand3d import drawings, materials
from test_determinism import run_cases


def linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def uv_of(ob):
    """{a face's normal: {a corner's place: where it falls in the drawing}}, all rounded."""
    mesh, layer, out = ob.data, ob.data.uv_layers[drawings.LAYER], {}
    for face in mesh.polygons:
        normal = tuple(round(v) for v in face.normal)
        for corner in face.loop_indices:
            place = tuple(round(v) for v in mesh.vertices[mesh.loops[corner].vertex_index].co)
            out.setdefault(normal, {})[place] = tuple(round(v, 4) for v in layer.data[corner].uv)
    return out


class Drawings(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()
        s3d.units('mm')

    def test_tiles_are_rectangles_parted_by_a_joint(self):
        drawn = s3d.tiles(400, 200, joint=8, color="#ffffff", joint_color="#000000")
        self.assertEqual(drawn.period, (408, 208))
        image = drawn.image()
        lines, columns = image.shape[:2]
        self.assertEqual(image.shape[2], 3)
        self.assertTrue(columns >= 102 and lines >= 52)                      # the joint is two dots wide at least
        at = lambda u, v: image[int(v / 208 * lines), int(u / 408 * columns)]
        self.assertTrue(np.allclose(at(4, 100), 0) and np.allclose(at(200, 4), 0))      # in the joints
        self.assertTrue(np.allclose(at(200, 100), 1) and np.allclose(at(400, 200), 1))  # in the tile
        share = 1 - 400 * 200 / (408 * 208)                                  # what the joints take of a period
        self.assertAlmostEqual(linear(int(drawn.color[1:3], 16) / 255), 1 - share, delta=.01)
        self.assertEqual(s3d.tiles(300).period, (302, 302))                  # square, a joint of 2 by default
        plain = s3d.tiles(300, joint=0, color="#336699")
        self.assertEqual(plain.color, "#336699")
        self.assertTrue(np.allclose(plain.image(), plain.image()[0, 0]))

    def test_a_shift_slides_each_row(self):
        boards = s3d.tiles(800, 120, joint=4, color="#ffffff", joint_color="#000000", shift=.5)
        self.assertEqual(boards.period, (804, 248))                          # two rows before it repeats
        image = boards.image()
        lines, columns = image.shape[:2]
        at = lambda u, v: round(float(image[int(v / 248 * lines), int(u / 804 * columns)][0]), 6)
        self.assertEqual((at(2, 60), at(404, 60)), (0, 1))                   # first row: its joint at u = 0
        self.assertEqual((at(2, 184), at(404, 184)), (1, 0))                 # second row: half a board on
        self.assertEqual(s3d.tiles(300, shift=1 / 3).period, (302, 906))     # three rows
        self.assertEqual(s3d.tiles(300, shift=.26).spec["shift"], [1, 4])    # kept to eighths

    def test_stripes_run_one_way_or_the_other(self):
        up = s3d.stripes(300, "#ffffff", "#000000", share=.25)
        self.assertEqual(up.period, (300, 300))
        image = up.image()
        self.assertEqual(image.shape[0], 1)                                  # the same all along v
        columns = image.shape[1]
        self.assertTrue(np.allclose(image[0, int(.1 * columns)], 1) and np.allclose(image[0, int(.6 * columns)], 0))
        level = s3d.stripes(300, "#ffffff", "#000000", share=.25, along="u").image()
        self.assertEqual(level.shape[1], 1)
        self.assertTrue(np.allclose(level[int(.1 * level.shape[0]), 0], 1))
        self.assertAlmostEqual(linear(int(up.color[1:3], 16) / 255), .25, delta=.01)

    def test_a_grain_is_streaks_about_a_colour(self):
        oak = s3d.grain("#a0522d", pitch=12)
        self.assertEqual(oak.period, (768, 192))                             # 64 pitches along u, 16 across
        self.assertEqual(s3d.grain("#a0522d", pitch=12, along="v").period, (192, 768))
        image = oak.image()
        across, along = image[:, 0, 0], image[0, :, 0]
        self.assertGreater(float(across.std()), 4 * float(along.std()))      # it changes across, hardly along
        turns = int((np.diff(np.sign(across - across.mean())) != 0).sum())
        self.assertTrue(16 <= turns <= 96, turns)                            # about a streak a pitch, of sixteen
        self.assertTrue(np.array_equal(image, s3d.grain("#a0522d", pitch=12).image()))   # the same board again
        self.assertFalse(np.array_equal(image, s3d.grain("#a0522d", pitch=12, seed=1).image()))
        base = np.array([0xa0, 0x52, 0x2d]) / 255
        self.assertTrue(np.allclose(s3d.grain("#a0522d", depth=0).image(), base, atol=1e-6))
        self.assertEqual(oak.color, "#a0522d")                               # lighter and darker about it: its mean
        self.assertEqual(s3d.grain("#b3babd", pitch=30, depth=.6, along="v").color, "#b3babd")

    def test_a_part_wears_it_and_each_corner_knows_its_place(self):
        slab = s3d.box("slab", 800, 400, 200)                                # x -400..400, y -200..200, z 0..200
        self.assertIs(s3d.material(slab, "ceramic", color=s3d.tiles(398, 198, joint=2)), slab)
        tag = json.loads(slab[materials.TAG])
        self.assertEqual(tag["drawing"]["draw"], "tiles")
        self.assertEqual(materials.look(slab[materials.TAG])["color"], s3d.tiles(398, 198, joint=2).color)
        mat = slab.data.materials[0]
        self.assertIn("ceramic tiles", mat.name)
        node = mat.node_tree.nodes["Drawing"]
        self.assertEqual((node.extension, tuple(node.image.size) >= (16, 16)), ("REPEAT", True))
        self.assertTrue(node.outputs["Color"].links[0].to_socket.name == "Base Color")
        uv = uv_of(slab)
        self.assertEqual(uv[(0, 0, 1)][(400, 200, 200)], (1, 1))             # the top: u is X, v is Y, in periods
        self.assertEqual(uv[(0, 0, 1)][(-400, -200, 200)], (-1, -1))
        self.assertEqual(uv[(0, -1, 0)][(400, -200, 200)], (1, 1))           # the front: u to the right, v up
        self.assertEqual(uv[(0, 1, 0)][(400, 200, 200)], (-1, 1))            # the back, seen from behind
        self.assertEqual(uv[(1, 0, 0)][(400, 200, 0)], (.5, 0))              # the right side: u is Y
        self.assertEqual(uv[(-1, 0, 0)][(-400, 200, 200)], (-.5, 1))
        self.assertEqual(len(bpy.data.images), 1)
        twin = s3d.material(s3d.box("twin", 100, 100, 100), "ceramic", color=s3d.tiles(398, 198, joint=2))
        self.assertIs(twin.data.materials[0], mat)                           # the same drawing: one material
        self.assertEqual(len(bpy.data.images), 1)

    def test_the_drawing_follows_the_part_through_edits_copies_and_groups(self):
        post = s3d.material(s3d.box("post", 100, 100, 400), "oak", color=s3d.grain(pitch=10, along="v"))
        s3d.fillet(post, 10, "top")
        layer = post.data.uv_layers[drawings.LAYER]
        self.assertEqual(len(layer.data), len(post.data.loops))              # every corner of the new mesh
        s3d.at(post, x=5000)
        self.assertEqual(uv_of(post)[(0, -1, 0)][(50, -50, 0)], (round(50 / 160, 4), 0))   # in its own space
        twin = s3d.copy(post)
        self.assertIn("oak grain", twin.data.materials[0].name)
        legs = s3d.group("legs", s3d.box("a", 50, 50, 700), s3d.at(s3d.box("b", 50, 50, 700), x=600))
        s3d.material(legs, "oak", color=s3d.grain("#7a3b1e", pitch=10, along="v"))
        for leg in legs.children:
            self.assertIn(drawings.LAYER, leg.data.uv_layers)
        plain = s3d.material(s3d.box("plain", 10, 10, 10), "oak")
        self.assertNotIn(drawings.LAYER, plain.data.uv_layers)

    def test_a_picture_shows_it(self):
        floor = s3d.material(s3d.box("floor", 8000, 8000, 20), "plastic", roughness=1,
                             color=s3d.tiles(1000, joint=200, color="#ffffff", joint_color="#000000"))
        room = s3d.assembly("room", floor, s3d.light("sun", "sun", lux=math.pi))
        path = os.path.join(tempfile.mkdtemp(), "floor.png")
        s3d.render(room, path, eye=(0, 0, 6000), size=(96, 64), samples=16, bounces=0)   # 68 mm of floor a pixel
        image = bpy.data.images.load(path)
        at = lambda x, y: linear(image.pixels[4 * (round(32 + y / 68) * 96 + round(48 + x / 68))])
        self.assertLess(at(100, 700), .1)                                    # the joint at u 0..200
        self.assertGreater(at(700, 700), .9)                                 # the tile
        self.assertLess(at(700, 100), .1)                                    # the joint at v 0..200
        self.assertLess(at(100 - 1200, 700), .1)                             # one period on: a joint again
        self.assertGreater(at(700 + 1200, 700 - 1200), .9)

    def test_a_glb_carries_the_drawing_and_the_other_formats_its_mean(self):
        floor = s3d.material(s3d.box("floor", 4000, 4000, 20), "ceramic", color=s3d.tiles(400, joint=8))
        post = s3d.material(s3d.at(s3d.box("post", 100, 100, 900), z=20), "oak")
        room = s3d.assembly("room", floor, post)
        folder = tempfile.mkdtemp()
        s3d.export(room, os.path.join(folder, "room.glb"))
        raw = open(os.path.join(folder, "room.glb"), "rb").read()
        doc = json.loads(raw[20:20 + struct.unpack("<I", raw[12:16])[0]])
        self.assertEqual((len(doc["images"]), len(doc["textures"])), (1, 1))
        drawn = {m["name"]: m["pbrMetallicRoughness"] for m in doc["materials"]}
        tiled = next(v for k, v in drawn.items() if "tiles" in k)
        self.assertIn("baseColorTexture", tiled)
        self.assertNotIn("baseColorTexture", next(v for k, v in drawn.items() if "tiles" not in k))
        wrap = doc["samplers"][doc["textures"][0].get("sampler", 0)]
        self.assertEqual((wrap.get("wrapS", 10497), wrap.get("wrapT", 10497)), (10497, 10497))   # it repeats
        mesh = next(m for m in doc["meshes"] if m["name"] == "floor")
        self.assertIn("TEXCOORD_0", mesh["primitives"][0]["attributes"])
        for suffix in (".obj", ".stl", ".usda", ".urdf", ".ifc"):
            s3d.export(room, os.path.join(folder, "room" + suffix))
            self.assertGreater(os.path.getsize(os.path.join(folder, "room" + suffix)), 0)
        self.assertIn(drawings.LAYER, floor.data.uv_layers)                  # an export leaves the part as it was

    def test_errors(self):
        for wrong in (lambda: s3d.tiles(0), lambda: s3d.tiles(-5), lambda: s3d.tiles("wide"), lambda: s3d.tiles(True),
                      lambda: s3d.tiles(100, 0), lambda: s3d.tiles(100, joint=-1), lambda: s3d.tiles(100, shift=1),
                      lambda: s3d.tiles(100, shift=-.5), lambda: s3d.tiles(100, color="white"),
                      lambda: s3d.tiles(100, joint_color=(2, 0, 0)), lambda: s3d.tiles(math.inf)):
            with self.assertRaisesRegex(ValueError, "tiles:"):
                wrong()
        for wrong in (lambda: s3d.stripes(0), lambda: s3d.stripes(10, share=0), lambda: s3d.stripes(10, share=1),
                      lambda: s3d.stripes(10, along="x"), lambda: s3d.stripes(10, other="blue")):
            with self.assertRaisesRegex(ValueError, "stripes:"):
                wrong()
        for wrong in (lambda: s3d.grain(pitch=0), lambda: s3d.grain(depth=2), lambda: s3d.grain(depth=-.1),
                      lambda: s3d.grain(seed=-1), lambda: s3d.grain(seed=1.5), lambda: s3d.grain(along="z"),
                      lambda: s3d.grain("oak")):
            with self.assertRaisesRegex(ValueError, "grain:"):
                wrong()
        self.assertEqual(len(bpy.data.images), 0)                            # a refused drawing leaves nothing

    def test_fresh_processes(self):
        first = run_cases('drawn_room', seed='11')['digests']['drawn_room']
        second = run_cases('drawn_room', seed='37')['digests']['drawn_room']
        self.assertFalse(first.startswith('error'), first)
        self.assertEqual(first, second)


if __name__ == '__main__':
    unittest.main()
