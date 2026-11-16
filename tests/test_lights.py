"""A light is a named object that is not a solid: placed, grouped, copied and exported like one."""
import json
import math
import os
import struct
import tempfile
import unittest
import bpy
from mathutils import Matrix, Quaternion, Vector
import sand3d as s3d
from sand3d import _core
from test_determinism import run_cases


def glb_json(root):
    path = os.path.join(tempfile.mkdtemp(), "scene.glb")
    s3d.export(root, path)
    raw = open(path, "rb").read()
    return json.loads(raw[20:20 + struct.unpack("<I", raw[12:16])[0]])


def node_world(doc, index):
    """A node's matrix in the GLB's own space, through its parents."""
    parent = {c: i for i, n in enumerate(doc["nodes"]) for c in n.get("children", [])}
    world = Matrix.Identity(4)
    while index is not None:
        n = doc["nodes"][index]
        x, y, z, w = n.get("rotation", [0, 0, 0, 1])
        own = Matrix.LocRotScale(Vector(n.get("translation", [0, 0, 0])), Quaternion((w, x, y, z)),
                                 Vector(n.get("scale", [1, 1, 1])))
        world = own @ world
        index = parent.get(index)
    return world


class Lights(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()
        s3d.units('mm')

    def test_three_kinds_with_their_units(self):
        bulb = s3d.light("bulb")
        spot = s3d.light("spot", "spot", lm=1200, angle=60, blend=.3, color="#ffb76c")
        sun = s3d.light("key", "sun", lux=3.25, color=(1, .5, 0))
        self.assertEqual([o.type for o in (bulb, spot, sun)], ["LIGHT"] * 3)
        self.assertEqual([o.data.type for o in (bulb, spot, sun)], ["POINT", "SPOT", "SUN"])
        self.assertEqual([_core.given_name(o) for o in (bulb, spot, sun)], ["bulb", "spot", "key"])
        self.assertAlmostEqual(bulb.data.energy, 800 / 683, places=5)        # a household bulb, by default
        self.assertAlmostEqual(spot.data.energy, 1200 / 683, places=5)
        self.assertAlmostEqual(sun.data.energy, 3.25 / 683, places=7)
        self.assertAlmostEqual(s3d.light("noon", "sun").data.energy, 3 / 683, places=7)
        self.assertAlmostEqual(math.degrees(spot.data.spot_size), 60, places=4)
        self.assertAlmostEqual(spot.data.spot_blend, .3)
        self.assertEqual([round(c, 4) for c in bulb.data.color], [1, 1, 1])
        half = ((0x80 / 255 + .055) / 1.055) ** 2.4                          # a colour is one of 256 per channel
        self.assertEqual([round(c, 4) for c in sun.data.color], [1, round(half, 4), 0])
        self.assertEqual(len(bpy.data.meshes), 0)                            # a light has no faces

    def test_it_is_placed_like_a_part_and_shines_along_its_own_minus_z(self):
        down = Vector((0, 0, -1))
        shines = lambda ob: tuple(round(v, 6) for v in _core.world(ob).to_3x3() @ down)
        spot = s3d.light("spot", "spot")
        self.assertEqual(shines(spot), (0, 0, -1))                           # down, as built
        self.assertEqual(shines(s3d.at(spot, x=500, z=2000, rx=90)), (0, 1, 0))
        self.assertEqual(tuple(round(v) for v in _core.world(spot).translation), (500, 0, 2000))
        self.assertEqual(shines(s3d.at(spot, rx=0, ry=90)), (-1, 0, 0))
        wall = s3d.box("wall", 400, 20, 300)
        on_wall = s3d.at(s3d.light("washer", "spot"), on=wall.face("-Y"), rx=180)
        self.assertEqual(shines(on_wall), (0, -1, 0))                        # out of the face it is put on
        self.assertEqual(shines(s3d.transform(s3d.light("sun", "sun"), rx=180)), (0, 0, 1))

    def test_a_lamp_holds_its_light(self):
        shade = s3d.at(s3d.tube("shade", 120, 110, 160), z=1400)
        bulb = s3d.at(s3d.light("bulb", lm=250), z=1480)
        lamp = s3d.group("lamp", shade, bulb)
        s3d.at(lamp, x=700)
        self.assertEqual(tuple(round(v) for v in _core.world(bulb).translation), (700, 0, 1480))
        twin = s3d.copy(lamp)
        lights = [o for o in twin.children_recursive if o.type == "LIGHT"]
        self.assertEqual(len(lights), 1)
        self.assertIsNot(lights[0].data, bulb.data)                          # a light of its own
        self.assertAlmostEqual(lights[0].data.energy, 250 / 683, places=5)
        row = s3d.at(twin, on=s3d.grid(3, 1, px=400))
        self.assertEqual(sum(o.type == "LIGHT" for r in row for o in r.children_recursive), 3)
        s3d.scale(lamp, 2)                                                   # it moves with its group
        self.assertEqual(tuple(round(v) for v in _core.world(bulb).translation), (700, 0, 2960))
        self.assertAlmostEqual(bulb.data.energy, 250 / 683, places=5)        # and gives what it gave
        s3d.delete(bulb)
        self.assertNotIn("bulb", bpy.data.lights)

    def test_it_is_not_a_solid(self):
        bulb = s3d.light("bulb")
        box = s3d.box("box", 10, 10, 10)
        for edit in (lambda: s3d.fillet(bulb, 1), lambda: s3d.cut(bulb, box), lambda: s3d.cut(box, bulb),
                     lambda: s3d.shell(bulb, 1), lambda: s3d.displace(bulb, 1, 2)):
            with self.assertRaisesRegex(TypeError, "is a light object, not a solid"):
                edit()

    def test_a_glb_carries_the_lights(self):
        bulb = s3d.at(s3d.light("bulb", lm=800, color="#ffb76c"), x=1000, y=2000, z=1500)
        spot = s3d.at(s3d.light("spot", "spot", lm=1200, angle=60, blend=.3), z=2000, ry=90)
        sun = s3d.at(s3d.light("key", "sun", lux=3.25), rx=40)
        doc = glb_json(s3d.assembly("room", s3d.box("floor", 4000, 4000, 10), bulb, spot, sun))
        self.assertIn("KHR_lights_punctual", doc["extensionsUsed"])
        lights = {l["name"]: l for l in doc["extensions"]["KHR_lights_punctual"]["lights"]}
        self.assertEqual({k: l["type"] for k, l in lights.items()},
                         {"bulb": "point", "spot": "spot", "key": "directional"})
        self.assertAlmostEqual(lights["bulb"]["intensity"], 800 / (4 * math.pi), places=3)     # candela
        self.assertAlmostEqual(lights["spot"]["intensity"], 1200 / (4 * math.pi), places=3)
        self.assertAlmostEqual(lights["key"]["intensity"], 3.25, places=5)                      # lux
        self.assertAlmostEqual(lights["spot"]["spot"]["outerConeAngle"], math.radians(30), places=5)
        self.assertAlmostEqual(lights["spot"]["spot"]["innerConeAngle"], math.radians(30) * .7, places=5)
        for got, want in zip(lights["bulb"]["color"], (1, ((0xb7 / 255 + .055) / 1.055) ** 2.4,
                                                        ((0x6c / 255 + .055) / 1.055) ** 2.4)):
            self.assertAlmostEqual(got, want, places=4)                                         # linear
        of = {doc["extensions"]["KHR_lights_punctual"]["lights"][n["extensions"]["KHR_lights_punctual"]["light"]]
              ["name"]: i for i, n in enumerate(doc["nodes"]) if "KHR_lights_punctual" in n.get("extensions", {})}
        self.assertEqual(sorted(of), ["bulb", "key", "spot"])
        place = node_world(doc, of["bulb"]).translation          # metres, Y up: (x, z, -y)
        for got, want in zip(place, (1, 1.5, -2)):
            self.assertAlmostEqual(got, want, places=5)
        shines = (node_world(doc, of["spot"]).to_3x3() @ Vector((0, 0, -1))).normalized()
        for got, want in zip(shines, (-1, 0, 0)):                # ry=90 shines along -X, here as there
            self.assertAlmostEqual(got, want, places=5)
        shines = (node_world(doc, of["key"]).to_3x3() @ Vector((0, 0, -1))).normalized()
        for got, want in zip(shines, (0, -math.cos(math.radians(40)), -math.sin(math.radians(40)))):
            self.assertAlmostEqual(got, want, places=5)          # rx=40: down and along +Y there, -Z here

    def test_a_tree_with_no_light_exports_as_before_and_other_formats_carry_none(self):
        self.assertNotIn("extensions", glb_json(s3d.assembly("plain", s3d.box("box", 10, 10, 10))))
        room = s3d.assembly("room", s3d.box("floor", 400, 400, 10), s3d.at(s3d.light("bulb"), z=200))
        folder = tempfile.mkdtemp()
        for suffix in (".obj", ".stl", ".usda", ".urdf", ".ifc"):
            s3d.export(room, os.path.join(folder, "room" + suffix))
            self.assertGreater(os.path.getsize(os.path.join(folder, "room" + suffix)), 0)

    def test_a_shadow_is_sharp_soft_or_none(self):
        self.assertEqual(s3d.light("hard").data.shadow_soft_size, 0)            # a sharp edge by default
        self.assertTrue(s3d.light("casts").data.use_shadow)
        bulb = s3d.light("bulb", size=60)
        self.assertEqual(bulb.data.shadow_soft_size, 30)                        # the bulb's radius, in the unit
        self.assertEqual(s3d.light("cone", "spot", size=20).data.shadow_soft_size, 10)
        fill = s3d.light("fill", "sun", lux=.5, shadow=False)
        self.assertFalse(fill.data.use_shadow)
        self.assertEqual(fill.data.angle, 0)
        self.assertAlmostEqual(math.degrees(s3d.light("real", "sun", angle=.53).data.angle), .53, places=5)
        self.assertAlmostEqual(math.degrees(s3d.light("spot", "spot").data.spot_size), 45, places=4)

    def test_an_ambient_light_says_the_sky_and_gives_nothing_as_a_lamp(self):
        from sand3d.lights import ambient
        sky = s3d.light("sky", "ambient", lux=1.35, color="#ffffff", ground="#000000")
        self.assertEqual((sky.type, sky.data.type, sky.data.energy), ("LIGHT", "SUN", 0))
        self.assertEqual(ambient(sky), (1.35, (1, 1, 1), (0, 0, 0)))
        lux, above, below = ambient(s3d.light("even", "ambient", color="#ff8000"))
        self.assertEqual(lux, 1)                                                # 1 lux, the same from below
        for one, other in zip(above, below):
            self.assertAlmostEqual(one, other, places=6)
        self.assertIsNone(ambient(s3d.light("bulb")))
        self.assertIsNone(ambient(s3d.box("box", 10, 10, 10)))
        self.assertEqual(ambient(s3d.copy(sky)), ambient(sky))                  # a copy says the same
        with self.assertRaisesRegex(TypeError, "is a light object, not a solid"):
            s3d.fillet(sky, 1)
        doc = glb_json(s3d.assembly("room", s3d.box("floor", 400, 400, 10), sky))
        said = {l["name"]: l for l in doc["extensions"]["KHR_lights_punctual"]["lights"]}["sky"]
        self.assertEqual((said["type"], said["intensity"]), ("directional", 0))  # glTF has no ambient light:
        self.assertEqual(said["extras"]["s3d_ambient"], [1.35, 0, 0, 0])         # what it says rides along

    def test_errors(self):
        for kw in (dict(kind="sun", size=10), dict(kind="sun", angle=180), dict(kind="sun", angle=-1),
                   dict(shadow=1), dict(shadow="no"), dict(size=-1), dict(size="wide"), dict(ground="#ffffff"),
                   dict(kind="spot", ground="#ffffff"), dict(kind="ambient", lm=5), dict(kind="ambient", size=3),
                   dict(kind="ambient", shadow=False), dict(kind="ambient", angle=3),
                   dict(kind="ambient", ground="soil"), dict(kind="ambient", lux=-1)):
            with self.subTest(kw=kw), self.assertRaisesRegex(ValueError, "light:"):
                s3d.light("l", **kw)
        for kw in (dict(kind="area"), dict(kind="sun", lm=800), dict(kind="point", lux=3), dict(kind="spot", lux=3),
                   dict(lm=-1), dict(lm="800"), dict(lm=True), dict(lm=math.inf), dict(kind="sun", lux=math.nan),
                   dict(color="warm"), dict(color="#fff"), dict(color=(2, 0, 0)),
                   dict(kind="spot", angle=0), dict(kind="spot", angle=180), dict(kind="spot", angle="wide"),
                   dict(kind="spot", blend=1.5), dict(kind="spot", blend=-.1)):
            with self.subTest(kw=kw), self.assertRaisesRegex(ValueError, "light:"):
                s3d.light("l", **kw)
        with self.assertRaisesRegex(TypeError, "light:"):
            s3d.light(3)
        self.assertEqual(len(bpy.data.lights), 0)                # a refused light leaves nothing behind

    def test_fresh_processes(self):
        first = run_cases('lit_room', seed='11')['digests']['lit_room']
        second = run_cases('lit_room', seed='37')['digests']['lit_room']
        self.assertFalse(first.startswith('error'), first)
        self.assertEqual(first, second)


if __name__ == '__main__':
    unittest.main()
