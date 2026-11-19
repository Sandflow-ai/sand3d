"""`export` to .obj and .stl: the meshes under the root at the current pose, in metres —
OBJ Y up, STL Z up — each closed mesh still facing out, its mirror image included."""
import struct
import tempfile
import unittest
from pathlib import Path

import sand3d as s3d
from sand3d import _core


def machine():
    s3d.empty_scene()
    cab = s3d.box("cab", 600, 600, 850)
    door = s3d.at(s3d.cylinder("door", 420, 30), on=cab.face("+X").move(z=400))
    s3d.joint("door_hinge", door, s3d.bbox(cab, "+X-Y"), axis="-Z", range=(0, 143))
    twin = s3d.transform(s3d.copy(door), mirror="y")
    return s3d.group("washer", cab, door, twin), cab, door, twin


def read_obj(path):
    """name -> (vertices, triangles), indices local to the object."""
    objects, verts, name, base = {}, [], None, 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("o "):
            name = line[2:] + ("'" if line[2:] in objects else "")
            base = len(verts)
            objects[name] = ([], [])
        elif line.startswith("v "):
            verts.append(tuple(map(float, line.split()[1:])))
            objects[name][0].append(verts[-1])
        elif line.startswith("f "):
            objects[name][1].append(tuple(int(i) - 1 - base for i in line.split()[1:]))
    return objects


def read_stl(path):
    data = Path(path).read_bytes()
    n = struct.unpack("<I", data[80:84])[0]
    return [struct.unpack("<12fH", data[84 + 50 * i:84 + 50 * (i + 1)]) for i in range(n)], len(data)


def volume(tris):
    """Signed volume of closed triangles: positive when they face out."""
    total = 0.0
    for a, b, c in tris:
        total += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
                  + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6
    return total


def triangles(ob):
    ob.data.calc_loop_triangles()
    return len(ob.data.loop_triangles)


class ExportMeshes(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_obj_is_the_meshes_at_the_pose_in_metres_y_up(self):
        root, cab, door, twin = machine()
        s3d.pose(door, 70)
        s3d.export(root, self.tmp / "washer.obj")
        objects = read_obj(self.tmp / "washer.obj")
        self.assertEqual(sorted(objects), ["cab", "door", "door'"])
        cab_v, cab_t = objects["cab"]
        self.assertEqual((len(cab_v), len(cab_t)), (len(cab.data.vertices), triangles(cab)))
        for axis, lo, hi in ((0, -0.3, 0.3), (1, 0.0, 0.85), (2, -0.3, 0.3)):   # Z up becomes Y up
            self.assertAlmostEqual(min(v[axis] for v in cab_v), lo, places=6)
            self.assertAlmostEqual(max(v[axis] for v in cab_v), hi, places=6)
        m = _core.world(door)
        posed = [m @ v.co for v in door.data.vertices]
        got = objects["door"][0]
        self.assertAlmostEqual(max(v[0] for v in got), max(p.x for p in posed) / 1000, places=6)
        self.assertAlmostEqual(min(v[2] for v in got), -max(p.y for p in posed) / 1000, places=6)
        for name, (vs, ts) in objects.items():
            self.assertGreater(volume([[vs[i] for i in t] for t in ts]), 0, f"{name} faces in")

    def test_stl_is_binary_triangles_z_up(self):
        root, cab, door, twin = machine()
        s3d.export(root, self.tmp / "washer.stl")
        rows, size = read_stl(self.tmp / "washer.stl")
        self.assertEqual(len(rows), sum(triangles(ob) for ob in (cab, door, twin)))
        self.assertEqual(size, 84 + 50 * len(rows))
        corners = [r[3 + 3 * k:6 + 3 * k] for r in rows for k in range(3)]
        world = [_core.world(ob) @ v.co for ob in (cab, door, twin) for v in ob.data.vertices]
        for axis in range(3):                                   # Z stays up
            self.assertAlmostEqual(min(c[axis] for c in corners), min(p[axis] for p in world) / 1000, places=6)
            self.assertAlmostEqual(max(c[axis] for c in corners), max(p[axis] for p in world) / 1000, places=6)
        self.assertGreater(volume([(r[3:6], r[6:9], r[9:12]) for r in rows]), 0)

    def test_the_unit_becomes_metres(self):
        s3d.empty_scene()
        s3d.units("cm")
        try:
            root = s3d.group("thing", s3d.box("b", 1, 1, 1))
            s3d.export(root, self.tmp / "thing.obj")
            vs = read_obj(self.tmp / "thing.obj")["b"][0]
            self.assertAlmostEqual(max(v[0] for v in vs) - min(v[0] for v in vs), 0.01, places=9)
        finally:
            s3d.empty_scene()
            s3d.units("mm")


if __name__ == "__main__":
    unittest.main()
