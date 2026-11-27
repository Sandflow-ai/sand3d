"""Patterns tile and repeat; a texture's maps say what its patterns say; a GLB carries them at scale."""
import json
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np
import sand3d as s3d
from sand3d import _core, textures, uvs


def gltf(root):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "thing.glb"
        s3d.export(root, path)
        raw = path.read_bytes()
    n = struct.unpack("<I", raw[12:16])[0]
    return json.loads(raw[20:20 + n])


ALL = [("perlin", 4), ("ridged", 6), ("turbulence", (5, 2)), ("cells", 5), ("creases", 12), ("strands", (6, 0.5)),
       ("bubbles", 10), ("waves", 7.5), ("plates", (8, 12))]


class Patterns(unittest.TestCase):
    def test_every_pattern_repeats_over_its_tile(self):
        u, v = np.meshgrid(np.linspace(0, 60, 40, endpoint=False), np.linspace(0, 40, 30, endpoint=False))
        for kind, size in ALL:
            spec = s3d.pattern(kind, size, octaves=2, seed=3).spec
            here = textures.evaluate(spec, u, v, [60, 40])
            there = textures.evaluate(spec, u + 60, v - 40, [60, 40])
            self.assertLess(np.abs(here - there).max(), 1e-9, kind)
            self.assertGreater(np.ptp(here), 0.2, kind)
            self.assertLessEqual(np.abs(here).max(), 1 + 1e-9, kind)

    def test_plates_crack_where_cells_meet(self):
        u, v = np.meshgrid(np.linspace(0, 40, 200, endpoint=False), np.linspace(0, 40, 200, endpoint=False))
        values = textures.evaluate(s3d.pattern("plates", 10).spec, u, v, [40, 40])
        self.assertLess(values.min(), 0.01)
        self.assertEqual(values.max(), 1.0)
        cracks = (values < 0.1).mean()
        self.assertTrue(0.03 < cracks < 0.3, cracks)

    def test_the_seed_sets_the_pattern(self):
        u, v = np.meshgrid(np.arange(20.0), np.arange(20.0))
        a, b, c = (s3d.pattern("perlin", 3, seed=s)(u + 0.3, v + 0.3) for s in (1, 1, 2))
        self.assertTrue((a == b).all())
        self.assertGreater(np.abs(a - c).max(), 0.1)

    def test_they_add_up(self):
        p, q = s3d.pattern("perlin", 5), s3d.pattern("cells", 7)
        x, y = np.meshgrid(np.arange(10) + 0.4, np.arange(10) + 0.7)
        a, b = p(x, y), q(x, y)
        for got, want in ((2 * p + q / 4 - 1, 2 * a + b / 4 - 1), (1 - p, 1 - a), (-p, -a), (abs(p), abs(a)),
                          (p.max(q), np.maximum(a, b)), (p.min(0), np.minimum(a, 0)), (p.clip(0, 0.1), np.clip(a, 0, 0.1))):
            self.assertLess(np.abs(got(x, y) - want).max(), 1e-12)
        self.assertEqual(set(np.unique(s3d.pattern("waves", 2).levels(-2, -1.5)(x, y))), {1.0})

    def test_a_pattern_displaces(self):
        s3d.empty_scene()
        ob = s3d.displace(s3d.box("b", 40, 40, 2), 3, 5, noise=s3d.pattern("bubbles", 10), direction="+Z", step=2)
        self.assertGreater(max(v.co.z for v in ob.data.vertices), 4.5)

    def test_arguments(self):
        for bad in (lambda: s3d.pattern("marble", 3), lambda: s3d.pattern("perlin", 0), lambda: s3d.pattern("perlin", 3, octaves=0),
                    lambda: s3d.pattern("perlin", 3, density=2), lambda: s3d.pattern("bubbles", 3, density=2),
                    lambda: s3d.texture(tile=10), lambda: s3d.texture(tile=0, height=s3d.pattern("perlin", 1)),
                    lambda: s3d.pattern("perlin", 1).levels(1, 0)):
            self.assertRaises(ValueError, bad)
        for bad in (lambda: s3d.texture(tile=10, height=1), lambda: s3d.texture(tile=10, color="#ffffff"),
                    lambda: s3d.texture(tile=10, roughness=(s3d.pattern("perlin", 1), 0, 2)),
                    lambda: s3d.material(s3d.box("b", 1, 1, 1), "plastic", texture="wood")):
            self.assertRaises(TypeError, bad)


class Textures(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()

    def test_maps(self):
        waves = s3d.pattern("waves", 10)
        maps = textures.maps(s3d.texture(tile=20, px=64, height=0.5 * waves, color=(0.5 + 0.5 * waves, "#000000", "#ffffff"),
                                         roughness=(0.5 + 0.5 * waves, 0.2, 0.6)).spec)
        self.assertAlmostEqual(maps["color"].max(), 254, delta=2)
        self.assertEqual(maps["roughness"][..., 1].min(), 51)
        n = maps["normal"] / 127.5 - 1
        slope = -n[..., 0] / n[..., 2]
        self.assertAlmostEqual(np.abs(slope).max(), 0.5 * 2 * np.pi / 10, delta=0.02)   # a relief in millimetres
        self.assertLess(np.abs(n[..., 1]).max(), 0.01)

    def test_a_tile_keeps_its_size_on_every_part(self):
        paint = s3d.texture(tile=30, px=32, height=0.1 * s3d.pattern("perlin", 5))
        a, b = s3d.box("a", 50, 50, 50), s3d.at(s3d.box("b", 400, 20, 20), y=200)
        s3d.material([a, b], "plastic", texture=paint)
        for parts in (a, b):
            s3d.unwrap(parts)
            side = json.loads(parts[uvs.REPORT])["side_mm"]
            place = parts.data.materials[0].node_tree.nodes["Tile"]
            self.assertAlmostEqual(place.inputs["Scale"].default_value[0], side / 30, places=4)
        self.assertEqual(len({m.node_tree.nodes["normal"].image.name for p in (a, b) for m in p.data.materials}), 1)

    def test_a_glb_carries_the_maps(self):
        w = s3d.pattern("perlin", 5)
        ob = s3d.material(s3d.box("a", 50, 50, 50), "steel", coat=0.5, texture=s3d.texture(
            tile=25, px=32, height=0.1 * w, color=(w, "#102030", "#405060"), roughness=(w, 0.1, 0.5)))
        j = gltf(s3d.unwrap(ob))
        mat, = j["materials"]
        self.assertIn("normalTexture", mat)
        pbr = mat["pbrMetallicRoughness"]
        self.assertIn("baseColorTexture", pbr)
        self.assertIn("metallicRoughnessTexture", pbr)
        self.assertEqual(pbr.get("metallicFactor", 1), 1)
        self.assertIn("KHR_texture_transform", pbr["baseColorTexture"]["extensions"])
        self.assertNotIn("extras", mat)
        self.assertFalse(any("extras" in x for x in j["images"]))

    def test_without_uvs_the_part_is_plain(self):
        ob = s3d.material(s3d.box("a", 50, 50, 50), "plastic",
                          texture=s3d.texture(tile=25, px=32, color=(s3d.pattern("waves", 5), "#000000", "#ffffff")))
        self.assertNotIn("images", gltf(ob))


def png(path, size=(8, 4), alpha=True):
    """A small PNG, red, half of it see-through."""
    import zlib
    w, h = size
    n = 4 if alpha else 3
    rows = b"".join(b"\0" + bytes(v for x in range(w) for v in (200, 30, 20, 255 if x < w / 2 else 0)[:n]) for _ in range(h))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6 if alpha else 2, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
    return path


class Decals(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = png(Path(self.tmp.name) / "label.png")

    def test_it_keeps_the_proportions_and_lies_on_a_face(self):
        box = s3d.box("box", 60, 40, 20)
        label = s3d.decal("label", self.path, 30)
        self.assertEqual([round(d, 4) for d in label.dimensions], [30, 15, 0])
        s3d.at(label, on=box.face("+X"), z=0.1)
        m = _core.world(label)
        self.assertAlmostEqual(m.translation.x, 30.1, places=4)
        self.assertAlmostEqual((m.to_3x3() @ label.data.polygons[0].normal).x, 1, places=4)

    def test_unwrap_leaves_its_uvs_and_the_glb_carries_it(self):
        box = s3d.material(s3d.box("box", 60, 40, 20), "plastic")
        label = s3d.at(s3d.decal("label", self.path, 30), on=box.face("+Z"), z=0.1)
        root = s3d.unwrap(s3d.assembly("all", box, label))
        uv = np.empty(8, np.float32)
        label.data.uv_layers[0].data.foreach_get("uv", uv)
        self.assertEqual(uv.tolist(), [0, 0, 1, 0, 1, 1, 0, 1])
        j = gltf(root)
        mat = next(m for m in j["materials"] if m["name"].startswith("decal"))
        self.assertIn("baseColorTexture", mat["pbrMetallicRoughness"])
        self.assertEqual(mat["alphaMode"], "BLEND")
        self.assertNotIn(self.tmp.name, json.dumps(j))         # no path of this machine in the file

    def test_an_opaque_image_is_opaque_and_an_assembly_s_material_does_not_hide_it(self):
        label = s3d.decal("label", png(Path(self.tmp.name) / "o.png", alpha=False), 30)
        root = s3d.material(s3d.group("g", s3d.box("box", 9, 9, 9), label), "oak")
        mat = next(m for m in gltf(root)["materials"] if m["name"].startswith("decal"))
        self.assertEqual(mat.get("alphaMode", "OPAQUE"), "OPAQUE")

    def test_arguments(self):
        for bad in (lambda: s3d.decal("x", "nowhere.png", 3), lambda: s3d.decal("x", self.path, 0), lambda: s3d.decal("x", __file__, 3)):
            self.assertRaises(ValueError, bad)


if __name__ == "__main__":
    unittest.main()
