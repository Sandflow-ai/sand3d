"""OBJ and STL: the meshes under a root, at the current pose, in metres, in one file.

Geometry only — no material, no joint: the GLB and the USDA carry those. The meshes are
Blender's triangles (a reader that fans a concave face itself gets it wrong), each mesh in
the order of the tree, its children by name. OBJ is written Y up (Z of the program
becomes Y, Y becomes −Z), the axes OBJ readers expect and the GLB's; STL keeps Z up, as a
slicer expects.
"""
import os
import json
import struct

from . import _core
from .urdf import _metres, _num


def _meshes(root):
    out = []

    def walk(ob):
        if ob.type == "MESH":
            out.append(ob)
        for child in sorted(ob.children, key=lambda c: c.name):
            walk(child)
    walk(root)
    return out


def _triangles(ob, y_up):
    """`ob`'s vertices in the world at the current pose, in metres, and its triangles."""
    m, unit = _core.world(ob), _metres()
    rows = [[m[r][c] * unit for c in range(4)] for r in range(3)]
    flip = m.to_3x3().determinant() < 0          # a mirror image: its triangles turn the other way
    me = ob.data
    co = [0.0] * (3 * len(me.vertices))
    me.vertices.foreach_get("co", co)
    verts = []
    for i in range(0, len(co), 3):
        x, y, z = (r[0] * co[i] + r[1] * co[i + 1] + r[2] * co[i + 2] + r[3] for r in rows)
        verts.append((x, z, -y) if y_up else (x, y, z))
    me.calc_loop_triangles()
    tris = [tuple(reversed(t.vertices)) if flip else tuple(t.vertices) for t in me.loop_triangles]
    return verts, tris


def write_obj(root, path):
    lines = [f"# {_core.given_name(root)} — written by sand3d, metres, Y up"]
    from . import materials
    means = [(ob, materials.mean_tag(ob)) for ob in _meshes(root)
             if materials._nearest(ob) and materials.FUNCTION in json.loads(materials._nearest(ob))]
    if means:
        lines.append(f"mtllib {os.path.splitext(os.path.basename(os.fspath(path)))[0]}.mtl")
        mtl = []
        for index, (ob, tag) in enumerate(means):
            rgba = materials._linear(materials.look(tag)['color'])
            mtl += [f"newmtl colour{index}", "Kd " + " ".join(_num(c) for c in rgba[:3])]
        with open(os.path.splitext(os.fspath(path))[0]+'.mtl', 'w', newline='\n') as f:
            f.write('\n'.join(mtl)+'\n')
    base = 1
    for ob in _meshes(root):
        verts, tris = _triangles(ob, y_up=True)
        lines.append(f"o {_core.given_name(ob)}")
        for index, (part, tag) in enumerate(means):
            if part == ob:
                lines.append(f"usemtl colour{index}")
        lines += ["v " + " ".join(_num(c) for c in v) for v in verts]
        lines += ["f " + " ".join(str(base + i) for i in t) for t in tris]
        base += len(verts)
    with _core.text_file(path) as f:
        f.write("\n".join(lines) + "\n")


def write_stl(root, path):
    """Binary STL: an 80-byte header, the count, then per triangle its normal and corners."""
    body = []
    for ob in _meshes(root):
        verts, tris = _triangles(ob, y_up=False)
        for t in tris:
            a, b, c = (verts[i] for i in t)
            u = [b[k] - a[k] for k in range(3)]
            v = [c[k] - a[k] for k in range(3)]
            n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
            length = sum(x * x for x in n) ** 0.5 or 1.0
            body.append(struct.pack("<12fH", *(x / length for x in n), *a, *b, *c, 0))
    header = f"{_core.given_name(root)} — written by sand3d, metres, Z up".encode()
    if header[:5].lower() == b"solid":
        header = b"sand3d: " + header
    header = header[:80].ljust(80, b" ")
    with open(os.fspath(path), "wb") as f:
        f.write(header + struct.pack("<I", len(body)) + b"".join(body))
