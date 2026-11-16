"""Own-frame deformation and geometric spiral paths."""
import math
import unittest

import bpy
from mathutils import Vector

import sand3d as s3d
from test_solids import closed_volume, faces


class Deformers(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()

    def test_bend_centred_negative_axis_and_large_curl(self):
        for axis, sign in (("+Y", 1), ("-Y", -1)):
            ob = s3d.extrude("strip", s3d.rect(4, 60), 0.5, both=True)
            old = [v.co.copy() for v in ob.data.vertices]
            s3d.bend(ob, 220, axis=axis)
            self.assertTrue(closed_volume(ob)[0])
            k = math.radians(220) / 60
            for p in old:
                u, z = sign * p.y, p.z
                want = Vector((p.x, sign * (1/k-z) * math.sin(k*u),
                               (1-math.cos(k*u))/k + z*math.cos(k*u)))
                self.assertLess(min((v.co-want).length for v in ob.data.vertices), 1e-4)
            self.assertGreater(faces(ob, "top"), 48, "caps have interior refinement")
            self.assertTrue(all(any(ob.data.attributes['s3d_face:'+tag].data[f.index].value
                                     for tag in ('top', 'bottom', 'side')) for f in ob.data.polygons))

    def test_twist_and_taper_end_sections(self):
        for axis, end in (("+Y", 20), ("-Y", -20)):
            ob = s3d.box("bar", 8, 40, 2)
            s3d.twist(ob, 90, axis)
            self.assertLessEqual(max(abs(ob.data.vertices[e.vertices[0]].co.y -
                                         ob.data.vertices[e.vertices[1]].co.y) for e in ob.data.edges),
                                 40/max(4, math.ceil(90/3)) + 1e-5)
            near = [v.co for v in ob.data.vertices if abs(v.co.y+end) < 1e-5]
            self.assertAlmostEqual(max(abs(p.x) for p in near), 4, places=5)
            self.assertAlmostEqual(max(p.z for p in near), 2, places=5)
            endpts = [v.co for v in ob.data.vertices if abs(v.co.y-end) < 1e-5]
            self.assertAlmostEqual(max(abs(p.z) for p in endpts), 4, places=5)
            self.assertAlmostEqual(max(abs(p.x) for p in endpts), 2, places=5)
            ob = s3d.box("bar", 8, 40, 2)
            s3d.taper(ob, 0.5, axis)
            self.assertAlmostEqual(max(abs(v.co.x) for v in ob.data.vertices if v.co.y == end), 2)
            self.assertAlmostEqual(max(v.co.z for v in ob.data.vertices if v.co.y == end), 1)
            self.assertEqual(len(ob.data.vertices), 8)

    def test_placement_name_material_and_frame_are_kept(self):
        for verb, value in ((s3d.bend, 130), (s3d.twist, 90), (s3d.taper, 0.5)):
            a = s3d.box("plain", 4, 40, 2)
            b = s3d.at(s3d.box("placed", 4, 40, 2), x=123, ry=30, rz=40)
            material = bpy.data.materials.new("finish")
            b.data.materials.append(material)
            name = b.name
            frame = b.matrix_basis.copy()
            self.assertIs(verb(b, value), b)
            verb(a, value)
            self.assertEqual([tuple(v.co) for v in a.data.vertices], [tuple(v.co) for v in b.data.vertices])
            self.assertEqual(b.matrix_basis, frame)
            self.assertEqual(b.name, name)
            self.assertEqual(b.data.materials[0], material)

    def test_group_uses_shared_extent_in_its_frame(self):
        for verb, value in ((s3d.bend, 120), (s3d.twist, 90), (s3d.taper, 0.5)):
            blade = s3d.box("blade", 4, 60, 1)
            vein = s3d.at(s3d.box("vein", 1, 30, 1), y=15, z=1, rz=180)
            vein_frame = vein.matrix_basis.copy()
            group = s3d.at(s3d.group("leaf", blade, s3d.group("detail", vein)), x=50, rx=30)
            # The matching vertex at y=30 on both parts must use the group's L=60.
            before = vein_frame @ vein.data.vertices[0].co
            a = Vector((0, 1, 0))
            u, t = before.y, (before.y + 30) / 60
            if verb == s3d.bend:
                k = math.radians(value)/60
                want = Vector((before.x, (1/k-before.z)*math.sin(k*u),
                               (1-math.cos(k*u))/k + before.z*math.cos(k*u)))
            elif verb == s3d.twist:
                p = before-a*u
                want = a*u+p*math.cos(math.radians(value)*t)+a.cross(p)*math.sin(math.radians(value)*t)
            else:
                want = a*u+(before-a*u)*(1+(value-1)*t)
            self.assertIs(verb(group, value), group)
            self.assertLess(min((vein_frame @ v.co-want).length for v in vein.data.vertices), 1e-4)
            self.assertEqual(vein.matrix_basis, vein_frame)

    def test_millimetres_and_metres_agree(self):
        for verb, value in ((s3d.bend, 220), (s3d.twist, 90), (s3d.taper, 0.5)):
            results = []
            for unit, factor in (("mm", 1), ("m", 0.001)):
                s3d.empty_scene()
                s3d.units(unit)
                ob = s3d.extrude("strip", s3d.rect(4*factor, 60*factor), factor, both=True)
                verb(ob, value)
                results.append(sorted(tuple(c/factor for c in v.co) for v in ob.data.vertices))
            self.assertEqual(len(results[0]), len(results[1]))
            for left in results[0]:
                self.assertLess(min((Vector(left)-Vector(right)).length for right in results[1]), 1e-3)

    def test_arguments_and_neutral_values(self):
        ob = s3d.box("bar", 4, 40, 2)
        original = [tuple(v.co) for v in ob.data.vertices]
        for verb, value in ((s3d.bend, 0), (s3d.twist, 0), (s3d.taper, 1)):
            verb(ob, value)
            self.assertEqual(original, [tuple(v.co) for v in ob.data.vertices])
            for axis in ("Y", "up", (0, 1, 0), None):
                with self.assertRaises(ValueError):
                    verb(ob, value, axis=axis)
            for bad in (True, "90", math.inf, math.nan):
                with self.assertRaises(TypeError):
                    verb(ob, bad)
            flat = bpy.data.objects.new("flat", bpy.data.meshes.new("flat"))
            flat.data.from_pydata([(0, 0, 0), (1, 0, 0), (0, 0, 1)], [], [(0, 1, 2)])
            with self.assertRaisesRegex(ValueError, "axis '\\+Y'"):
                verb(flat, value)
        for ratio in (0, -1):
            with self.assertRaises(ValueError):
                s3d.taper(ob, ratio)
        with self.assertRaises(ValueError):
            s3d.bend(ob, 10, toward="-Y")
        for verb in (s3d.bend, s3d.twist, s3d.taper):
            with self.assertRaises(TypeError):
                verb(s3d.circle(2), 1)


class Spiral(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()

    def test_endpoints_mean_radius_and_handedness(self):
        for left in (False, True):
            p = s3d.spiral(20, 80, 1.25, h=-12, left=left)
            self.assertFalse(p.closed)
            self.assertLess((Vector(p.points[0])-Vector((10, 0, 0))).length, 1e-5)
            self.assertLess((Vector(p.points[-1])-Vector((0, -40 if left else 40, -12))).length, 1e-4)
            middle = Vector(p.points[len(p.points)//2])
            self.assertAlmostEqual(math.hypot(middle.x, middle.y), 20, places=5)
            self.assertAlmostEqual(middle.z, -6)
        p = s3d.spiral(20, 20, 1)
        self.assertFalse(p.closed)
        for q in p.points:
            self.assertAlmostEqual(math.hypot(q[0], q[1]), 10, places=5)

    def test_sweep_with_law_and_wire_are_closed(self):
        path = s3d.spiral(20, 80, 2)
        ob = s3d.sweep("coil", s3d.circle(2), path, scale=[(0, 1), (0.5, 1.5), (1, 0.5)])
        self.assertTrue(closed_volume(ob)[0])
        self.assertTrue(closed_volume(s3d.wire("wire", path, 1))[0])

    def test_arguments(self):
        for name in ("d", "d2", "turns", "h"):
            for bad in (True, math.inf, math.nan, "2"):
                kw = dict(d=20, d2=40, turns=2, h=0)
                kw[name] = bad
                with self.assertRaises(TypeError):
                    s3d.spiral(**kw)
            if name != "h":
                for bad in (0, -1):
                    kw = dict(d=20, d2=40, turns=2)
                    kw[name] = bad
                    with self.assertRaises(ValueError):
                        s3d.spiral(**kw)
