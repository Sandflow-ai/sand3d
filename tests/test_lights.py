"""A light is a named object that is not a solid: placed, grouped and copied like a part, in
lumens or lux, and written by each export in the words its format has for it — the GLB read
back as JSON, the USDA by USD's own library, the IFC by IfcOpenShell."""
import json
import math
import os
import struct
import tempfile
import unittest
import warnings

import bpy
from mathutils import Matrix, Quaternion, Vector

import sand3d as s3d
from sand3d import _core
from test_determinism import run_cases
from test_export_ifc import read_back as ifc_read_back
from test_export_usd import read_back as usd_read_back


def linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def glb_json(root):
    path = os.path.join(tempfile.mkdtemp(), "scene.glb")
    s3d.export(root, path)
    with open(path, "rb") as f:
        raw = f.read()
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


def shines(ob):
    return tuple(round(v, 6) for v in _core.world(ob).to_3x3() @ Vector((0, 0, -1)))


def room():
    """A floor, a bulb hung in a lamp, a spot turned toward -X, a sun and the sky."""
    floor = s3d.box("floor", 4000, 4000, 10)
    bulb = s3d.at(s3d.light("bulb", lm=800, color="#ffb76c", size=60), x=1000, y=2000, z=1500)
    lamp = s3d.group("lamp", s3d.at(s3d.box("shade", 200, 200, 100), x=1000, y=2000, z=1550), bulb)
    spot = s3d.at(s3d.light("spot", "spot", lm=1200, angle=60, blend=.3, shadow=False), z=2000, ry=90)
    sun = s3d.at(s3d.light("key", "sun", lux=80_000, angle=0), rx=40)
    sky = s3d.light("sky", "ambient", lux=12_000, color="#cfe0ff")
    return s3d.assembly("room", floor, lamp, spot, sun, sky)


class Lights(unittest.TestCase):

    def setUp(self):
        s3d.empty_scene()
        s3d.units("mm")

    def test_four_kinds_in_lumens_and_lux(self):
        bulb, spot = s3d.light("bulb"), s3d.light("spot", "spot", lm=1200, angle=60, blend=.3, color="#ffb76c")
        sun, sky = s3d.light("key", "sun", lux=80_000, color=(1, .5, 0)), s3d.light("sky", "ambient")
        made = (bulb, spot, sun, sky)
        self.assertEqual([o.type for o in made], ["LIGHT"] * 4)
        self.assertEqual([o.data.type for o in made], ["POINT", "SPOT", "SUN", "SUN"])
        self.assertEqual([_core.given_name(o) for o in made], ["bulb", "spot", "key", "sky"])
        self.assertEqual([o.data["s3d_light"]["kind"] for o in made], ["point", "spot", "sun", "ambient"])
        self.assertEqual([o.data["s3d_light"]["power"] for o in made], [800, 1200, 80_000, 10_000])
        self.assertEqual(s3d.light("noon", "sun").data["s3d_light"]["power"], 100_000)     # the midday sun
        self.assertAlmostEqual(bulb.data.energy, 800 / 683, places=5)        # Blender's watts, at 683 lm a watt
        self.assertAlmostEqual(sun.data.energy, 80_000 / 683, places=3)       # watts per square metre
        self.assertEqual(sky.data.energy, 0)                                 # Blender has no sky
        self.assertAlmostEqual(math.degrees(spot.data.spot_size), 60, places=4)
        self.assertAlmostEqual(spot.data.spot_blend, .3)
        self.assertAlmostEqual(math.degrees(s3d.light("cone", "spot").data.spot_size), 45, places=4)
        self.assertAlmostEqual(s3d.light("cone", "spot").data.spot_blend, .15)
        self.assertAlmostEqual(math.degrees(s3d.light("noon", "sun").data.angle), .53, places=5)   # the real sun
        self.assertEqual(spot.data["s3d_light"]["color"], "#ffb76c")
        self.assertEqual(sun.data["s3d_light"]["color"], "#ff8000")
        for got, want in zip(spot.data.color, (1, linear(0xb7 / 255), linear(0x6c / 255))):
            self.assertAlmostEqual(got, want, places=5)                      # Blender's colours are linear
        self.assertEqual(len(bpy.data.meshes), 0)                            # a light has no faces

    def test_a_shadow_is_soft_sharp_or_none(self):
        self.assertEqual(s3d.light("bulb").data.shadow_soft_size, 30)       # a household bulb's 60 mm, by default
        self.assertEqual(s3d.light("cone", "spot").data.shadow_soft_size, 15)
        self.assertEqual(s3d.light("hard", size=0).data.shadow_soft_size, 0)
        self.assertTrue(s3d.light("casts").data.use_shadow)
        self.assertEqual(s3d.light("bulb", size=60).data.shadow_soft_size, 30)     # the radius, in the unit
        self.assertEqual(s3d.light("cone", "spot", size=20).data.shadow_soft_size, 10)
        self.assertFalse(s3d.light("fill", "sun", shadow=False).data.use_shadow)
        self.assertEqual(s3d.light("sharp", "sun", angle=0).data.angle, 0)
        self.assertAlmostEqual(s3d.light("still", "sun", size=0).data.angle, math.radians(.53))   # no size

    def test_a_bulb_is_as_wide_whatever_the_unit(self):
        s3d.empty_scene()
        s3d.units("m")
        bulb = s3d.light("bulb")
        self.assertAlmostEqual(bulb.data.shadow_soft_size, .03)              # 60 mm, in metres
        self.assertAlmostEqual(bulb.data["s3d_light"]["size"], .06)

    def test_it_keeps_what_the_program_said_in_units_no_reader_converts(self):
        said = lambda ob: dict(ob.data["s3d_light"])
        self.assertEqual(said(s3d.light("bulb", size=40, color="#ffcf8a")),
                         {"kind": "point", "power": 800, "color": "#ffcf8a", "shadow": True, "size": .04})
        self.assertEqual(said(s3d.light("spot", "spot", lm=600, shadow=False)),
                         {"kind": "spot", "power": 600, "color": "#ffffff", "shadow": False, "size": .03})
        self.assertEqual(said(s3d.light("sun", "sun", angle=1)),
                         {"kind": "sun", "power": 100_000, "color": "#ffffff", "shadow": True, "angle": 1})
        self.assertEqual(said(s3d.light("sky", "ambient")),
                         {"kind": "ambient", "power": 10_000, "color": "#ffffff", "shadow": True})

    def test_it_is_placed_like_a_part_and_shines_along_its_own_minus_z(self):
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
        lo, hi = s3d.bbox(lamp, "-X-Y-Z").origin, s3d.bbox(lamp, "+X+Y+Z").origin
        self.assertEqual(round(hi.z - lo.z), 160)                            # a light has no extent
        twin = s3d.copy(lamp)
        lights = [o for o in twin.children_recursive if o.type == "LIGHT"]
        self.assertEqual(len(lights), 1)
        self.assertIsNot(lights[0].data, bulb.data)                          # a light of its own
        self.assertEqual(lights[0].data["s3d_light"]["power"], 250)
        row = s3d.at(twin, on=s3d.grid(3, 1, px=400))
        self.assertEqual(sum(o.type == "LIGHT" for r in row for o in r.children_recursive), 3)
        s3d.delete(bulb)
        self.assertEqual(sorted(l.name for l in bpy.data.lights).count("bulb"), 0)   # its data goes with it

    def test_it_is_not_a_solid(self):
        bulb = s3d.light("bulb")
        box = s3d.box("box", 10, 10, 10)
        for edit in (lambda: s3d.fillet(bulb, 1), lambda: s3d.cut(bulb, box), lambda: s3d.cut(box, bulb),
                     lambda: s3d.shell(bulb, 1), lambda: s3d.scale(bulb, 2), lambda: s3d.material(bulb, "oak")):
            with self.subTest(edit=edit), self.assertRaisesRegex(TypeError, "is a light object, not a solid"):
                edit()

    def test_errors(self):
        for kw in (dict(kind="area"), dict(kind="sun", lm=800), dict(kind="point", lux=3), dict(kind="spot", lux=3),
                   dict(kind="ambient", lm=5), dict(lm=-1), dict(lm="800"), dict(lm=True), dict(lm=math.inf),
                   dict(kind="sun", lux=math.nan), dict(kind="ambient", lux=-1),
                   dict(color="warm"), dict(color="#fff"), dict(color=(2, 0, 0)),
                   dict(angle=30), dict(blend=.2), dict(kind="sun", blend=.2), dict(kind="ambient", angle=3),
                   dict(kind="spot", angle=0), dict(kind="spot", angle=180), dict(kind="spot", angle="wide"),
                   dict(kind="spot", blend=1.5), dict(kind="spot", blend=-.1),
                   dict(kind="sun", size=10), dict(kind="sun", angle=180), dict(kind="sun", angle=-1),
                   dict(kind="ambient", size=3), dict(kind="ambient", shadow=False),
                   dict(shadow=1), dict(shadow="no"), dict(size=-1), dict(size="wide")):
            with self.subTest(kw=kw), self.assertRaisesRegex(ValueError, "light:"):
                s3d.light("l", **kw)
        with self.assertRaisesRegex(TypeError, "light:"):
            s3d.light(3)
        self.assertEqual(len(bpy.data.lights), 0)                            # a refused light leaves nothing

    def test_fresh_processes(self):
        first = run_cases("lit_room", seed="11")["digests"]["lit_room"]
        second = run_cases("lit_room", seed="37")["digests"]["lit_room"]
        self.assertFalse(first.startswith("error"), first)
        self.assertEqual(first, second)

    def test_a_spot_rejects_an_angle_below_one_degree(self):
        with self.assertRaisesRegex(ValueError, "at least 1 and under 180 degrees"):
            s3d.light("tiny", "spot", angle=0.1)


class Export(unittest.TestCase):

    def setUp(self):
        s3d.empty_scene()
        s3d.units("mm")
        self.folder = tempfile.mkdtemp()

    def export(self, root, name):
        """Export, and the warnings it gave, each said at this file's line."""
        path = os.path.join(self.folder, name)
        with warnings.catch_warnings(record=True) as said:
            warnings.simplefilter("always")
            s3d.export(root, path)
        for w in said:
            self.assertEqual(w.filename, __file__)                           # the program's line, not sand3d's
        return path, [str(w.message) for w in said]

    def test_a_glb_carries_points_spots_and_suns_in_candela_and_lux(self):
        root = room()
        path, said = self.export(root, "room.glb")
        self.assertEqual(said, ["export: room.glb leaves out 'sky': glTF has no ambient light"])
        with open(path, "rb") as f:
            raw = f.read()
        doc = json.loads(raw[20:20 + struct.unpack("<I", raw[12:16])[0]])
        self.assertIn("KHR_lights_punctual", doc["extensionsUsed"])
        lights = {l["name"]: l for l in doc["extensions"]["KHR_lights_punctual"]["lights"]}
        self.assertEqual({k: l["type"] for k, l in lights.items()},
                         {"bulb": "point", "spot": "spot", "key": "directional"})
        self.assertAlmostEqual(lights["bulb"]["intensity"], 800 / (4 * math.pi), places=3)     # candela
        self.assertAlmostEqual(lights["spot"]["intensity"], 1200 / (4 * math.pi), places=3)
        self.assertAlmostEqual(lights["key"]["intensity"] / 80_000, 1, places=6)               # lux
        self.assertAlmostEqual(lights["spot"]["spot"]["outerConeAngle"], math.radians(30), places=5)
        self.assertAlmostEqual(lights["spot"]["spot"]["innerConeAngle"], math.radians(30) * .7, places=5)
        for got, want in zip(lights["bulb"]["color"], (1, linear(0xb7 / 255), linear(0x6c / 255))):
            self.assertAlmostEqual(got, want, places=4)
        self.assertEqual(lights["bulb"]["extras"]["s3d_light"],                 # what glTF has no word for
                         {"kind": "point", "power": 800, "color": "#ffb76c", "shadow": True, "size": .06})
        self.assertEqual(lights["spot"]["extras"]["s3d_light"]["shadow"], False)
        self.assertEqual(lights["key"]["extras"]["s3d_light"]["angle"], 0)
        of = {doc["extensions"]["KHR_lights_punctual"]["lights"][n["extensions"]["KHR_lights_punctual"]["light"]]
              ["name"]: i for i, n in enumerate(doc["nodes"]) if "KHR_lights_punctual" in n.get("extensions", {})}
        self.assertEqual(sorted(of), ["bulb", "key", "spot"])
        self.assertNotIn("sky", [n.get("name") for n in doc["nodes"]])
        for got, want in zip(node_world(doc, of["bulb"]).translation, (1, 1.5, -2)):   # metres, Y up: (x, z, -y)
            self.assertAlmostEqual(got, want, places=5)
        down = Vector((0, 0, -1))
        for got, want in zip((node_world(doc, of["spot"]).to_3x3() @ down).normalized(), (-1, 0, 0)):
            self.assertAlmostEqual(got, want, places=5)                      # ry=90 shines along -X there too
        key = (node_world(doc, of["key"]).to_3x3() @ down).normalized()
        for got, want in zip(key, (0, -math.cos(math.radians(40)), -math.sin(math.radians(40)))):
            self.assertAlmostEqual(got, want, places=5)                      # rx=40: down and along +Y, -Z there

    def test_a_glb_leaves_the_scene_as_it_was(self):
        lamps = s3d.at(s3d.light("bulb"), on=s3d.grid(3, 1, px=100))
        before = sorted((o.name, o.data.name) for o in lamps)
        self.export(s3d.group("row", lamps), "row.glb")
        self.assertEqual(sorted((o.name, o.data.name) for o in lamps), before)
        self.assertEqual(len(bpy.data.objects), 4)

    def test_a_glb_spot_cone_stays_within_limits(self):
        hard = s3d.light("hard", "spot", angle=45, blend=0)
        wide = s3d.light("wide", "spot", angle=179.999999)
        narrow = s3d.light("narrow", "spot", angle=1, blend=1e-12)
        spots = (hard, wide, narrow)
        before = [(ob.data.spot_size, ob.data.spot_blend) for ob in spots]
        doc = glb_json(s3d.group("cones", *spots))
        exported = doc["extensions"]["KHR_lights_punctual"]["lights"]
        self.assertEqual({light["name"] for light in exported}, {"hard", "wide", "narrow"})
        for light in exported:
            with self.subTest(light=light["name"]):
                spot = light["spot"]
                inner, outer = struct.unpack("<ff", struct.pack("<ff", spot["innerConeAngle"], spot["outerConeAngle"]))
                self.assertGreaterEqual(inner, 0)
                self.assertLess(inner, outer)
                self.assertLessEqual(outer, math.pi / 2)
        self.assertEqual([(ob.data.spot_size, ob.data.spot_blend) for ob in spots], before)

    def test_a_glb_with_no_light_is_written_as_before(self):
        path, said = self.export(s3d.assembly("plain", s3d.box("box", 10, 10, 10)), "plain.glb")
        self.assertEqual(said, [])
        with open(path, "rb") as f:
            raw = f.read()
        self.assertNotIn(b"KHR_lights_punctual", raw)

    def test_a_raw_bpy_light_is_left_out_in_every_format(self):
        light = bpy.data.objects.new("raw", bpy.data.lights.new("raw", "AREA"))
        bpy.context.scene.collection.objects.link(light)
        root = s3d.group("fixture", s3d.box("base", 40, 40, 10), light)
        markers = {"glb": b"KHR_lights_punctual", "ifc": b"IFCLIGHTFIXTURE", "usda": b'Light "'}
        for suffix in ("glb", "ifc", "obj", "stl", "urdf", "usda"):
            with self.subTest(suffix=suffix):
                path, said = self.export(root, f"fixture.{suffix}")
                self.assertEqual(said, [])
                with open(path, "rb") as f:
                    data = f.read()
                self.assertTrue(data)
                if suffix in markers:
                    self.assertNotIn(markers[suffix], data)

    def test_a_usda_carries_every_light_in_usdlux_units(self):
        path, said = self.export(room(), "room.usda")
        self.assertEqual(said, [])
        stage = usd_read_back(path)
        self.assertEqual(stage["errors"], [])
        lights = {p.rsplit("/", 1)[1]: v for p, v in stage["lights"].items()}
        self.assertEqual({k: v["type"] for k, v in lights.items()},
                         {"bulb": "SphereLight", "spot": "SphereLight", "key": "DistantLight", "sky": "DomeLight"})
        bulb, spot, key, sky = (lights[k] for k in ("bulb", "spot", "key", "sky"))
        self.assertAlmostEqual(bulb["inputs:intensity"] * math.pi / 800, 1, places=6)   # normalized: lm / π
        self.assertTrue(bulb["inputs:normalize"])
        self.assertAlmostEqual(bulb["inputs:radius"], .03, places=6)                     # metres
        self.assertNotIn("treatAsPoint", bulb)
        self.assertEqual(bulb["schemas"], ["CollectionAPI:lightLink", "CollectionAPI:shadowLink"])
        self.assertAlmostEqual(spot["inputs:intensity"] * math.pi / 1200, 1, places=6)
        self.assertAlmostEqual(spot["inputs:radius"], .015, places=6)                    # 30 mm by default
        self.assertNotIn("treatAsPoint", spot)
        self.assertAlmostEqual(spot["inputs:shaping:cone:angle"], 30, places=4)          # off the axis
        self.assertAlmostEqual(spot["inputs:shaping:cone:softness"], .3, places=6)
        self.assertIn("ShapingAPI", spot["schemas"])
        self.assertIn("ShadowAPI", spot["schemas"])
        self.assertFalse(spot["inputs:shadow:enable"])
        self.assertAlmostEqual(key["inputs:intensity"] / 80_000, 1, places=6)            # normalized: lux
        self.assertTrue(key["inputs:normalize"])
        self.assertEqual(key["inputs:angle"], 0)
        self.assertAlmostEqual(sky["inputs:intensity"] * math.pi / 12_000, 1, places=6)  # luminance: lux / π
        for got, want in zip(sky["inputs:color"], (linear(0xcf / 255), linear(0xe0 / 255), 1)):
            self.assertAlmostEqual(got, want, places=6)
        world = lambda m: Matrix(m)
        for got, want in zip(world(bulb["world"]).translation, (1, 2, 1.5)):             # metres, Z up
            self.assertAlmostEqual(got, want, places=6)
        for got, want in zip(world(spot["world"]).to_3x3() @ Vector((0, 0, -1)), (-1, 0, 0)):
            self.assertAlmostEqual(got, want, places=6)                                 # UsdLux shines along -Z
        for got, want in zip(world(key["world"]).to_3x3() @ Vector((0, 0, -1)),
                             (0, math.sin(math.radians(40)), -math.cos(math.radians(40)))):
            self.assertAlmostEqual(got, want, places=6)

    def test_a_mirrored_point_light_still_shines_its_way_in_a_usda(self):
        spot = s3d.transform(s3d.at(s3d.light("spot", "spot", size=0), x=100, ry=30), mirror="x")
        down = tuple(_core.world(spot).to_3x3() @ Vector((0, 0, -1)))
        path, _ = self.export(s3d.group("pair", s3d.box("box", 10, 10, 10), spot), "pair.usda")
        stage = usd_read_back(path)
        self.assertEqual(stage["errors"], [])
        (lamp,) = stage["lights"].values()
        self.assertEqual((lamp["inputs:radius"], lamp["treatAsPoint"]), (0, True))       # size 0: a point
        for got, want in zip(Matrix(lamp["world"]).to_3x3() @ Vector((0, 0, -1)), down):
            self.assertAlmostEqual(got, want, places=6)

    def test_an_ifc_carries_points_and_spots_as_light_fixtures_in_lumens(self):
        path, said = self.export(room(), "room.ifc")
        self.assertEqual(said, ["export: room.ifc leaves out 'key', 'sky': IFC gives a sun or the sky only a "
                                "share of 0..1, not lux"])
        model = ifc_read_back(path)
        self.assertEqual(model["errors"], [])
        self.assertIn("LUMINOUSFLUXUNIT", model["units"])
        self.assertIn("LUMINOUSINTENSITYDISTRIBUTIONUNIT", model["units"])
        self.assertEqual(sorted(model["lights"]), ["bulb", "spot"])
        bulb, spot = model["lights"]["bulb"], model["lights"]["spot"]
        self.assertEqual((bulb["product"], bulb["type"], bulb["source"]),
                         ("IfcLightFixture", "POINTSOURCE", "IfcLightSourceGoniometric"))
        self.assertEqual(spot["type"], "DIRECTIONSOURCE")
        self.assertEqual((bulb["lm"], spot["lm"]), (800, 1200))
        self.assertEqual(bulb["colour"], [1, round(0xb7 / 255, 9), round(0x6c / 255, 9)])     # sRGB, as given
        self.assertTrue(2500 < bulb["kelvin"] < 3500)                        # a warm white
        self.assertEqual(model["lights"]["spot"]["kelvin"], 6504)            # white: D65
        self.assertEqual(bulb["curve"], "TYPE_C")
        for got, want in zip(bulb["at"], (1, 2, 1.5)):
            self.assertAlmostEqual(got, want, places=6)
        (plane,) = bulb["planes"]
        self.assertEqual(plane[1], [0, round(math.pi, 8)])
        for candela in plane[2]:
            self.assertAlmostEqual(candela, 1 / (4 * math.pi), places=8)     # per lumen, every way
        (plane,) = spot["planes"]                                            # nadir on the way it shines
        for got, want in zip(spot["z"], (1, 0, 0)):
            self.assertAlmostEqual(got, want, places=6)
        for got, want in zip(plane[1], (0, math.radians(30) * .7, math.radians(30), math.pi)):
            self.assertAlmostEqual(got, want, places=6)
        for got, want in zip(plane[2], (1 / (4 * math.pi), 1 / (4 * math.pi), 0, 0)):
            self.assertAlmostEqual(got, want, places=8)

    def test_an_ifc_with_no_point_or_spot_has_no_photometric_unit(self):
        path, said = self.export(s3d.assembly("plain", s3d.box("box", 10, 10, 10)), "plain.ifc")
        self.assertEqual(said, [])
        with open(path) as f:
            text = f.read()
        self.assertNotIn("LUMEN", text)
        self.assertNotIn("LIGHT", text)

    def test_formats_with_no_light_leave_them_out_and_say_so(self):
        root = room()
        for name, why in (("room.urdf", "a URDF has no light"), ("room.obj", "an OBJ or an STL holds meshes only"),
                          ("room.stl", "an OBJ or an STL holds meshes only")):
            path, said = self.export(root, name)
            self.assertEqual(said, [f"export: {name} leaves out 'bulb', 'key', 'sky', 'spot': {why}"])
            self.assertGreater(os.path.getsize(path), 0)


if __name__ == "__main__":
    unittest.main()
