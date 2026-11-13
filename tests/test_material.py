"""material: a named preset, its values changed where given, inherited down a group."""
import json
import struct
import tempfile
import unittest
from pathlib import Path

import bpy

import sand3d as s3d
from sand3d import materials


def worn(ob):
    """The names of the materials `ob`'s mesh wears."""
    return [m.name for m in ob.data.materials]


def bsdf(ob):
    return ob.data.materials[0].node_tree.nodes["Principled BSDF"].inputs


def gltf(path):
    """The JSON chunk of a GLB."""
    raw = Path(path).read_bytes()
    n = struct.unpack("<I", raw[12:16])[0]
    return json.loads(raw[20:20 + n])


def export(root):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "thing.glb"
        s3d.export(root, path)
        return gltf(path), path.stat().st_size


class Presets(unittest.TestCase):

    def setUp(self):
        s3d.empty_scene()

    def test_a_part_wears_its_preset(self):
        plate = s3d.box("plate", 40, 20, 4)
        self.assertIs(s3d.material(plate, "brass"), plate)
        self.assertEqual(worn(plate), ["brass"])
        inputs = bsdf(plate)
        self.assertAlmostEqual(inputs["Metallic"].default_value, 1.0)
        self.assertAlmostEqual(inputs["Roughness"].default_value, 0.25)
        # '#c9a24a' in sRGB, written linear
        self.assertAlmostEqual(inputs["Base Color"].default_value[0], 0.584078, places=5)

    def test_values_changed_where_given(self):
        a, b, c = (s3d.at(s3d.box(n, 10, 10, 10), x=20 * i) for i, n in enumerate("abc"))
        s3d.material(a, "plastic", color="#C0392B")
        s3d.material(b, "plastic", color=(192 / 255, 57 / 255, 43 / 255))
        s3d.material(c, "plastic", color="#c0392b", roughness=0.2, opacity=0.5, emission=3)
        self.assertEqual(worn(a), ["plastic #c0392b"])
        self.assertIs(a.data.materials[0], b.data.materials[0])      # one colour, one spelling, one material
        self.assertEqual(worn(c), ["plastic #c0392b emission=3 opacity=0.5 roughness=0.2"])
        inputs = bsdf(c)
        self.assertAlmostEqual(inputs["Alpha"].default_value, 0.5)
        self.assertAlmostEqual(inputs["Emission Strength"].default_value, 3.0)
        self.assertEqual(c.data.materials[0].surface_render_method, "BLENDED")

    def test_the_reference_lists_every_preset(self):
        """docs/api.md shows a docstring's first paragraph: the one place a model learns the names."""
        first = s3d.material.__doc__.split("\n\n")[0]
        listed = first.split(":", 1)[1].split(";")[0].split()
        self.assertEqual(listed, list(materials.PRESETS))

    def test_every_preset_builds(self):
        for i, kind in enumerate(materials.PRESETS):
            s3d.material(s3d.at(s3d.box(kind, 5, 5, 5), x=10 * i), kind)
        self.assertEqual(len(bpy.data.materials), len(materials.PRESETS))


class Inheritance(unittest.TestCase):

    def setUp(self):
        s3d.empty_scene()

    def table(self, order):
        s3d.empty_scene()
        top = s3d.box("top", 100, 60, 4)
        legs = s3d.at(s3d.cylinder("leg", 5, 68), on=s3d.grid(2, 2, 90, 50))
        table = s3d.assembly("table", s3d.at(top, z=68), legs)
        calls = [lambda: s3d.material(table, "oak"), lambda: s3d.material(legs, "steel")]
        for i in order:
            calls[i]()
        return top, legs, table

    def test_the_nearest_call_wins_in_any_order(self):
        for order in ((0, 1), (1, 0)):
            top, legs, _ = self.table(order)
            self.assertEqual(worn(top), ["oak"])
            self.assertEqual([worn(leg) for leg in legs], [["steel"]] * 4)

    def test_a_detail_attached_later_inherits(self):
        top, legs, table = self.table((0,))
        lamp = s3d.attach(table, "lamp", s3d.at(s3d.dome("shade", 20, 10), z=72))
        self.assertEqual(worn(lamp.children[0]), ["oak"])

    def test_a_list_and_a_group(self):
        a, b = s3d.box("a", 5, 5, 5), s3d.at(s3d.box("b", 5, 5, 5), x=10)
        s3d.material([a, s3d.group("g", b)], "rubber")
        self.assertEqual((worn(a), worn(b)), (["rubber"], ["rubber"]))


class ThroughEdits(unittest.TestCase):

    def setUp(self):
        s3d.empty_scene()

    def test_edits_that_rebuild_the_mesh_keep_it(self):
        plate = s3d.material(s3d.box("plate", 40, 20, 4), "oak")
        s3d.hole(plate, 4, on=(5, 0))
        s3d.cut(plate, s3d.material(s3d.at(s3d.box("notch", 6, 30, 2), x=-15, z=3), "steel"))
        s3d.fillet(plate, 0.5, edges="top")
        s3d.shell(plate, 1, open="top")
        self.assertEqual(worn(plate), ["oak"])
        self.assertEqual({p.material_index for p in plate.data.polygons}, {0})
        self.assertNotIn("steel", [m.name for m in bpy.data.materials if m.users])

    def test_join_keeps_the_first_objects(self):
        plate = s3d.material(s3d.box("plate", 40, 20, 4), "pine")
        s3d.join(plate, s3d.material(s3d.at(s3d.cylinder("peg", 6, 10), z=4), "brass"))
        self.assertEqual(worn(plate), ["pine"])

    def test_join_says_which_materials_it_loses(self):
        """The review's red and blue boxes; nothing said for one colour, or for none."""
        import warnings
        red = s3d.material(s3d.box("red", 100, 100, 100), "plastic", color="#ff0000")
        blue = s3d.material(s3d.at(s3d.box("blue", 50, 50, 50), z=100), "plastic", color="#0000ff")
        with self.assertWarnsRegex(UserWarning, r"join \(line \d+\): 'red' keeps its 'plastic #ff0000', and the "
                                                r"parts joined into it lose theirs: 'plastic #0000ff' on 'blue' — .*"
                                                r"s3d\.group"):
            s3d.join(red, blue)
        self.assertEqual(worn(red), ["plastic #ff0000"])
        plain = s3d.box("plain", 10, 10, 10)
        with self.assertWarnsRegex(UserWarning, r"'plain' wears no material, and the parts joined into it lose "
                                                r"theirs: 'brass' on 'peg' —"):
            s3d.join(plain, s3d.material(s3d.at(s3d.cylinder("peg", 6, 10), z=10), "brass"))
        pegs = [s3d.material(s3d.at(s3d.cylinder("peg", 6, 10), x=x, z=10), "brass") for x in (-2, 2)]
        with self.assertWarnsRegex(UserWarning, r"'brass' on 'peg' — "):     # a name said once
            s3d.join(s3d.box("rail", 10, 10, 10), pegs)
        with warnings.catch_warnings(record=True) as said:
            warnings.simplefilter("always")
            same = s3d.material(s3d.box("a", 10, 10, 10), "plastic", color="#ff0000")
            s3d.join(same, s3d.material(s3d.at(s3d.box("b", 10, 10, 10), z=10), "plastic", color="#FF0000"))
            s3d.join(s3d.box("c", 10, 10, 10), s3d.at(s3d.box("d", 10, 10, 10), z=10))
            painted = s3d.material(s3d.box("e", 10, 10, 10), "oak")
            s3d.join(painted, s3d.at(s3d.box("f", 10, 10, 10), z=10))     # it had none: it takes the oak
            kit = s3d.group("kit", s3d.box("g", 10, 10, 10), s3d.at(s3d.box("h", 10, 10, 10), z=10))
            s3d.material(kit, "steel")
            s3d.join(*kit.children)                                       # both wear the group's steel
        self.assertEqual([str(w.message) for w in said if str(w.message).startswith("join")], [])

    def test_copies_keep_it(self):
        peg = s3d.material(s3d.cylinder("peg", 6, 10), "brass")
        pegs = s3d.at(s3d.copy(peg), on=s3d.grid(3, 1, 10))
        self.assertEqual([worn(p) for p in pegs], [["brass"]] * 3)


class Export(unittest.TestCase):

    def setUp(self):
        s3d.empty_scene()

    def test_without_material_no_material_is_written(self):
        doc, _ = export(s3d.group("thing", s3d.box("b", 10, 10, 10)))
        self.assertNotIn("materials", doc)

    def test_flat_values_reach_the_glb(self):
        parts = [s3d.material(s3d.box("wood", 10, 10, 10), "walnut"),
                 s3d.material(s3d.at(s3d.box("see", 10, 10, 10), x=20), "plastic", opacity=0.4),
                 s3d.material(s3d.at(s3d.box("pane", 10, 10, 10), x=40), "glass"),
                 s3d.material(s3d.at(s3d.box("bulb", 10, 10, 10), x=60), "light")]
        doc, _ = export(s3d.group("thing", *parts))
        got = {m["name"]: m for m in doc["materials"]}
        self.assertEqual(set(got), {"walnut", "plastic opacity=0.4", "glass", "light"})
        self.assertAlmostEqual(got["walnut"]["pbrMetallicRoughness"]["roughnessFactor"], 0.45, places=5)
        self.assertEqual(got["plastic opacity=0.4"]["alphaMode"], "BLEND")
        self.assertAlmostEqual(got["plastic opacity=0.4"]["pbrMetallicRoughness"]["baseColorFactor"][3], 0.4, places=5)
        self.assertEqual(got["glass"]["extensions"]["KHR_materials_transmission"]["transmissionFactor"], 1)
        self.assertEqual(got["light"]["extensions"]["KHR_materials_emissive_strength"]["emissiveStrength"], 12)


class Mistakes(unittest.TestCase):

    def setUp(self):
        s3d.empty_scene()
        self.box = s3d.box("box", 10, 10, 10)

    def message(self, *args, **kwargs):
        with self.assertRaises((ValueError, TypeError)) as caught:
            s3d.material(*args, **kwargs)
        return str(caught.exception)

    def test_an_unknown_preset_says_the_nearest(self):
        self.assertTrue(self.message(self.box, "oaak").startswith(
            "material: no preset named 'oaak' — did you mean 'oak'?; the presets: oak, walnut"))

    def test_values_out_of_range(self):
        self.assertEqual(self.message(self.box, "plastic", opacity=1.5),
                         "material: opacity=1.5 is not a number between 0 and 1 — 1 is opaque, 0 invisible")
        self.assertEqual(self.message(self.box, "plastic", emission=-1),
                         "material: emission=-1 is not a number of 0 or more")
        self.assertEqual(self.message(self.box, "plastic", color="red"),
                         "material: color='red' is not a colour — write '#rrggbb' or (r, g, b) in 0..1")
        self.assertEqual(self.message(self.box, "plastic", color=(200, 0, 0)),
                         "material: color=(200, 0, 0) is not a colour — write '#rrggbb' or (r, g, b) in 0..1")

    def test_a_profile_is_not_a_part(self):
        self.assertIn("is not a part, a group or an assembly", self.message(s3d.rect(10, 10), "oak"))

    def test_nothing_is_tagged_when_the_call_fails(self):
        self.message(self.box, "plastic", opacity=2)
        self.assertNotIn(materials.TAG, self.box)

class Nature(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()

    kinds = ('bark', 'leaf', 'moss', 'grass', 'rock', 'soil', 'sand', 'water', 'snow', 'foam')

    def test_nature_exports_and_tints(self):
        for kind in self.kinds:
            for color in (None, '#778899'):
                with self.subTest(kind=kind, color=color):
                    s3d.empty_scene()
                    ob = s3d.material(s3d.box('sample', 10, 10, 10), kind, color=color)
                    v = materials.look(ob[materials.TAG])
                    name = kind + (' #778899' if color else '')
                    self.assertEqual(worn(ob), [name])
                    self.assertEqual(v['color'], color or materials.PRESETS[kind]['color'])
                    doc, _ = export(ob)
                    mat = doc['materials'][0]
                    self.assertEqual(mat['name'], name)
                    pbr = mat['pbrMetallicRoughness']
                    self.assertAlmostEqual(pbr.get('roughnessFactor', 1), v['roughness'])
                    self.assertEqual(pbr.get('metallicFactor', 1), 0)
                    for i, c in enumerate(materials._linear(v['color'])[:3]):
                        self.assertAlmostEqual(pbr['baseColorFactor'][i], c, places=6)
                    for key, ext, factor in [('transmission', 'transmission', 'transmissionFactor'),
                                             ('coat', 'clearcoat', 'clearcoatFactor')]:
                        if v[key]:
                            self.assertAlmostEqual(mat['extensions']['KHR_materials_'+ext][factor], v[key])
                    if v['sheen']:
                        self.assertIn('KHR_materials_sheen', mat['extensions'])
                    with tempfile.TemporaryDirectory() as tmp:
                        path = Path(tmp) / 'sample.usda'
                        s3d.export(ob, path)
                        text = path.read_text()
                        self.assertIn('float inputs:roughness = '+str(v['roughness']).rstrip('0').rstrip('.'), text)
                        self.assertIn('float inputs:opacity = '+str(1-v['transmission']).rstrip('0').rstrip('.'), text)
                        self.assertNotIn('inputs:sheen', text)
                        if v['coat']:
                            self.assertIn('float inputs:clearcoat = '+str(v['coat']), text)

    def test_foam_is_white_diffuse_and_rough(self):
        ob = s3d.material(s3d.box("suds", 10, 10, 10), "foam")
        inputs = bsdf(ob)
        self.assertAlmostEqual(inputs["Roughness"].default_value, .95)
        self.assertEqual(inputs["Transmission Weight"].default_value, 0)
        self.assertEqual(inputs["Metallic"].default_value, 0)
        self.assertEqual(inputs["Alpha"].default_value, 1)
        self.assertGreater(min(inputs["Base Color"].default_value[:3]), .88)
        self.assertNotIn("Absorption", ob.data.materials[0].node_tree.nodes)

    def test_nature_suggestions(self):
        for typo, kind in [('barrk', 'bark'), ('watr', 'water'), ('snoow', 'snow')]:
            with self.assertRaisesRegex(ValueError, "did you mean.*'"+kind+"'"):
                s3d.material(s3d.box('sample', 1, 1, 1), typo)

    def test_nature_in_fresh_processes(self):
        import subprocess
        import sys
        code = '''import sand3d as s
from sand3d import materials as m
for kind in ('bark','leaf','moss','grass','rock','soil','sand','water','snow','foam'):
 ob=s.material(s.box(kind,1,1,1),kind,color='#778899')
 print('@@nature', kind, m.look(ob[m.TAG]), ob.data.materials[0].name, flush=True)
import os; os._exit(0)
'''
        outputs = [subprocess.run([sys.executable, '-c', code], check=True, capture_output=True).stdout for _ in range(2)]
        self.assertEqual(*[[line for line in output.splitlines() if line.startswith(b'@@nature')] for output in outputs])


class Absorption(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()

    def test_beer_lambert_and_glb_units(self):
        import math
        for unit, metre in (("mm", 1000), ("cm", 100), ("m", 1)):
            for mode in ("material", "vertex"):
                s3d.empty_scene()
                s3d.units(unit)
                ob = s3d.material(s3d.box("pool", metre, metre, metre), "water")
                mat = ob.data.materials[0]
                node = mat.node_tree.nodes["Absorption"]
                rgba = tuple(node.inputs["Color"].default_value)
                density = node.inputs["Density"].default_value
                tint = materials._linear("#b8e8ed")[:3]
                for i, c in enumerate(tint):
                    self.assertAlmostEqual(math.exp(-(1-rgba[i])*density*metre), c, places=6)
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "pool.glb"
                    s3d.export(ob, path, colors=mode)
                    doc = gltf(path)
                ext = doc["materials"][0]["extensions"]
                volume = ext["KHR_materials_volume"]
                self.assertAlmostEqual(volume["attenuationDistance"], 1)
                # Mesh coordinates remain in program units; the root scales to SI.
                # "auto": 2 x volume / area of the cube, a third of its side.
                self.assertAlmostEqual(volume["thicknessFactor"], metre / 3, places=4)
                for a, b in zip(volume["attenuationColor"], tint):
                    self.assertAlmostEqual(a, b)
                self.assertAlmostEqual(ext["KHR_materials_ior"]["ior"], 1.333, places=5)
                self.assertEqual(tuple(node.inputs["Color"].default_value), rgba)
                self.assertEqual(node.inputs["Density"].default_value, density)

    def test_auto_thickness_follows_the_meshes(self):
        slab = s3d.material(s3d.box("puddle", 3000, 3000, 300), "water")
        doc, _ = export(slab)
        self.assertAlmostEqual(doc["materials"][0]["extensions"]["KHR_materials_volume"]["thicknessFactor"],
                               250, places=3)
        # One value per material: the meshes wearing it are pooled.
        s3d.empty_scene()
        a = s3d.material(s3d.box("shallow", 1000, 1000, 20), "water")
        b = s3d.at(s3d.material(s3d.box("deep", 1000, 1000, 1000), "water"), x=3000)
        doc, _ = export(s3d.group("ponds", a, b))
        va, aa = 1000 * 1000 * 20, 2 * 1000 * 1000 + 4 * 1000 * 20
        vb, ab = 1000 ** 3, 6 * 1000 ** 2
        self.assertEqual(len(doc["materials"]), 1)
        self.assertAlmostEqual(doc["materials"][0]["extensions"]["KHR_materials_volume"]["thicknessFactor"],
                               2 * (va + vb) / (aa + ab), places=3)
        with self.assertRaises(ValueError):
            s3d.material(a, "water", thickness="deep")

    def test_overrides_disable_and_invalid_values(self):
        ob = s3d.box("pane", 10, 10, 10)
        s3d.material(ob, "glass", absorb="#aabbcc", absorb_distance=20, thickness=4,
                     ior=1.4, transmission=.7)
        doc, _ = export(ob)
        ext = doc["materials"][0]["extensions"]
        self.assertAlmostEqual(ext["KHR_materials_volume"]["attenuationDistance"], .02)
        self.assertEqual(ext["KHR_materials_volume"]["thicknessFactor"], 4)
        self.assertAlmostEqual(ext["KHR_materials_transmission"]["transmissionFactor"], .7)
        for kw in ({"absorb_distance": 0}, {"thickness": 0}):
            s3d.material(ob, "water", **kw)
            self.assertNotIn("Absorption", ob.data.materials[0].node_tree.nodes)
            doc, _ = export(ob)
            self.assertNotIn("KHR_materials_volume", doc["materials"][0]["extensions"])
        for key in ("absorb_distance", "thickness", "ior", "transmission"):
            for value in (-1, True, float("nan"), float("inf"), "1"):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    s3d.material(ob, "water", **{key: value})
        for kw in ({"ior": .9}, {"ior": 1001}, {"transmission": 1.1}, {"absorb": "blue"}):
            with self.assertRaises(ValueError):
                s3d.material(ob, "water", **kw)

    def test_failed_export_restores_cycles(self):
        ob = s3d.material(s3d.box("pool", 10, 10, 10), "water")
        node = ob.data.materials[0].node_tree.nodes["Absorption"]
        color = tuple(node.inputs["Color"].default_value)
        density = node.inputs["Density"].default_value
        with self.assertRaises(RuntimeError):
            with materials.volume_export():
                raise RuntimeError("failed")
        self.assertEqual(tuple(node.inputs["Color"].default_value), color)
        self.assertEqual(node.inputs["Density"].default_value, density)


    def test_volume_in_fresh_processes(self):
        import subprocess
        import sys
        code = """import sand3d as s3d
from sand3d import materials
import json, tempfile, struct, pathlib, os
s3d.empty_scene()
ob=s3d.material(s3d.box('pane',10,10,10),'glass',absorb='#aabbcc',
                absorb_distance=250,thickness=10,ior=1.4,transmission=.8)
with tempfile.TemporaryDirectory() as tmp:
 path=pathlib.Path(tmp)/'pane.glb'
 s3d.export(ob,path)
 raw=path.read_bytes(); n=struct.unpack('<I',raw[12:16])[0]
 doc=json.loads(raw[20:20+n]); doc.pop('asset',None)
 print('@@volume',json.dumps(doc,sort_keys=True),flush=True)
os._exit(0)
"""
        outputs = [subprocess.run([sys.executable, '-c', code], check=True,
                                 capture_output=True).stdout for _ in range(2)]
        self.assertEqual(*[[line for line in output.splitlines() if line.startswith(b'@@volume')]
                           for output in outputs])

    def test_surface_only_formats(self):
        ob = s3d.material(s3d.box("pool", 10, 10, 10), "water")
        with tempfile.TemporaryDirectory() as tmp:
            usd = Path(tmp) / "pool.usda"
            ifc = Path(tmp) / "pool.ifc"
            s3d.export(ob, usd)
            s3d.export(ob, ifc)
            self.assertIn("float inputs:ior = 1.333", usd.read_text())
            self.assertIn("float inputs:opacity = 0", usd.read_text())
            self.assertNotIn("absorption", usd.read_text().lower())
            self.assertIn(".GLASS.", ifc.read_text())
            self.assertNotIn("absorption", ifc.read_text().lower())


class Scattering(unittest.TestCase):
    """A medium that scatters: Volume Scatter beside Absorption in Cycles, extinction in glTF."""

    def setUp(self):
        s3d.empty_scene()

    def extinction(self, volume):
        """Per metre, per channel, from a glTF KHR_materials_volume."""
        import math
        return [-math.log(c) / volume["attenuationDistance"] for c in volume["attenuationColor"]]

    def test_scattering_and_absorption_add_up(self):
        import math
        for unit, metre in (("mm", 1000), ("cm", 100), ("m", 1)):
            for mode in ("material", "vertex"):
                s3d.empty_scene()
                s3d.units(unit)
                ob = s3d.material(s3d.box("plume", metre, metre, metre), "smoke")
                nodes = ob.data.materials[0].node_tree.nodes
                scatter, absorption = nodes["Scatter"], nodes["Absorption"]
                medium = nodes["Material Output"].inputs["Volume"].links[0].from_node
                self.assertEqual(medium.name, "Medium")
                self.assertEqual({link.from_node.name for socket in medium.inputs for link in socket.links},
                                 {"Scatter", "Absorption"})
                self.assertAlmostEqual(scatter.inputs["Anisotropy"].default_value, .3, places=6)
                # Cycles: sigma_s = colour x density; white light scatters every 625 mm.
                for c in scatter.inputs["Color"].default_value[:3]:
                    self.assertAlmostEqual(c * scatter.inputs["Density"].default_value * metre, 1 / .625, places=4)
                sigma_a = -math.log(materials._linear("#d6d6d6")[0])
                rgba = tuple(absorption.inputs["Color"].default_value)
                density = absorption.inputs["Density"].default_value
                self.assertAlmostEqual((1 - rgba[0]) * density * metre, sigma_a, places=4)
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "plume.glb"
                    s3d.export(ob, path, colors=mode)
                    ext = gltf(path)["materials"][0]["extensions"]
                for sigma in self.extinction(ext["KHR_materials_volume"]):
                    self.assertAlmostEqual(sigma, sigma_a + 1 / .625, places=4)
                self.assertAlmostEqual(ext["KHR_materials_volume"]["thicknessFactor"], metre / 3, places=4)
                self.assertAlmostEqual(ext["KHR_materials_ior"]["ior"], 1)
                self.assertEqual(ext["KHR_materials_transmission"]["transmissionFactor"], 1)
                self.assertEqual(tuple(absorption.inputs["Color"].default_value), rgba)
                self.assertEqual(absorption.inputs["Density"].default_value, density)

    def test_a_tinted_medium_attenuates_by_channel(self):
        # Water made murky: its absorption and a yellow-green scattering, per channel.
        import math
        ob = s3d.material(s3d.box("pond", 1000, 1000, 1000), "water", scatter="#c0d080", scatter_distance=2000)
        ext = export(ob)[0]["materials"][0]["extensions"]
        for sigma, a, sc in zip(self.extinction(ext["KHR_materials_volume"]),
                                materials._linear("#b8e8ed"), materials._linear("#c0d080")):
            self.assertAlmostEqual(sigma, -math.log(a) + sc / 2, places=5)
        # Fog scattering no blue: blue passes unattenuated.
        s3d.material(ob, "fog", scatter="#ff8000")
        self.assertNotIn("Absorption", [l.from_node.name for l in
                                        ob.data.materials[0].node_tree.nodes["Material Output"].inputs["Volume"].links])
        volume = export(ob)[0]["materials"][0]["extensions"]["KHR_materials_volume"]
        self.assertAlmostEqual(volume["attenuationColor"][2], 1)
        self.assertAlmostEqual(self.extinction(volume)[0], 1 / 10, places=5)

    def test_absorption_alone_is_unchanged(self):
        ob = s3d.material(s3d.box("pool", 10, 10, 10), "water")
        nodes = ob.data.materials[0].node_tree.nodes
        self.assertNotIn("Scatter", nodes)
        self.assertEqual(nodes["Material Output"].inputs["Volume"].links[0].from_node.name, "Absorption")

    def test_disable_bounds_and_errors(self):
        ob = s3d.box("cloud", 10, 10, 10)
        for kind, kw in (("fog", {"scatter_distance": 0}), ("smoke", {"thickness": 0})):
            s3d.material(ob, kind, **kw)
            nodes = ob.data.materials[0].node_tree.nodes
            self.assertNotIn("Scatter", nodes)
            self.assertFalse(nodes["Material Output"].inputs["Volume"].is_linked)
            self.assertNotIn("KHR_materials_volume", export(ob)[0]["materials"][0]["extensions"])
        for g in (-1, 1, 0):
            s3d.material(ob, "fog", scatter_anisotropy=g)
            self.assertEqual(ob.data.materials[0].node_tree.nodes["Scatter"].inputs["Anisotropy"].default_value, g)
        for key, values in (("scatter_distance", (-1, True, float("nan"), float("inf"), "1")),
                            ("scatter_anisotropy", (-1.01, 1.01, True, float("nan"), "0"))):
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, key):
                    s3d.material(ob, "smoke", **{key: value})
        with self.assertRaisesRegex(ValueError, "scatter='grey'"):
            s3d.material(ob, "smoke", scatter="grey")

    def test_surface_formats_ignore_scattering(self):
        """USD and IFC write the surface: adding a medium changes nothing they carry."""
        def inputs(**kw):
            s3d.empty_scene()
            ob = s3d.material(s3d.box("pond", 10, 10, 10), "water", **kw)
            with tempfile.TemporaryDirectory() as tmp:
                usd, ifc = Path(tmp) / "pond.usda", Path(tmp) / "pond.ifc"
                s3d.export(ob, usd)
                s3d.export(ob, ifc)
                return ([line.strip() for line in usd.read_text().splitlines() if "inputs:" in line],
                        [line for line in ifc.read_text().splitlines() if "IFCSURFACESTYLERENDERING" in line])
        self.assertEqual(inputs(), inputs(scatter="#c0d080", scatter_distance=2000, scatter_anisotropy=.5))

    def test_medium_in_fresh_processes(self):
        import subprocess
        import sys
        code = """import sand3d as s3d
import json, tempfile, struct, pathlib, os
s3d.empty_scene()
ob=s3d.material(s3d.box('plume',300,300,900),'smoke',scatter='#d0d8e0',scatter_anisotropy=.6)
with tempfile.TemporaryDirectory() as tmp:
 path=pathlib.Path(tmp)/'plume.glb'
 s3d.export(ob,path)
 raw=path.read_bytes(); n=struct.unpack('<I',raw[12:16])[0]
 doc=json.loads(raw[20:20+n]); doc.pop('asset',None)
 print('@@medium',json.dumps(doc,sort_keys=True),flush=True)
os._exit(0)
"""
        outputs = [subprocess.run([sys.executable, '-c', code], check=True,
                                 capture_output=True).stdout for _ in range(2)]
        lines = [[line for line in output.splitlines() if line.startswith(b'@@medium')] for output in outputs]
        self.assertTrue(lines[0])
        self.assertEqual(*lines)


if __name__ == "__main__":
    unittest.main()
