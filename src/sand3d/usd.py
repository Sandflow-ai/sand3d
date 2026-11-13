"""An articulated object written out as OpenUSD text: `export(root, "x.usda")`.

The URDF's tree (`urdf.Mechanism`), at rest, in UsdGeom and UsdPhysics, one flat layer
in SimReady's conventions: Z up, metres (`metersPerUnit = 1`), the default prim the
root — an `Xform` carrying `PhysicsArticulationRootAPI` once anything is jointed — and
under it three scopes:

- `Geometry`: an `Xform` per link, the URDF's, at its frame (`PhysicsRigidBodyAPI`); in
  it a `Mesh` per part, in that frame, triangulated as the URDF's OBJs are, with
  Blender's normals per corner. A mirror image is baked into its points, as in the OBJ.
- `Joints`: `PhysicsRevoluteJoint` (revolute, continuous) or `PhysicsPrismaticJoint`,
  `physics:body0` the parent link, `body1` the child. UsdPhysics names the axis by a
  token, so the joint frame is the child link's, turned to put the token's axis on the
  joint's: its own axis if it is +X, +Y or +Z, else X; `localPos0/1` and `localRot0/1`
  give it in each link. Limits in degrees for a turn, metres for a slide; a continuous
  joint's are ±inf. A joint that follows another carries `NewtonMimicAPI` — read by
  Newton, PhysX and MuJoCo — the joint it follows and the ratio in USD's units, follower
  = ratio × leader; a follower of a follower, the head of the chain and the product of
  the ratios. PhysX takes no revolute without finite limits there, Newton no pair
  of a turn and a slide: they ignore the coupling, not the joint. A `free` joint has no
  UsdPhysics equivalent: its child is a rigid body of its own, with no joint. What has
  no joint welds into its body, as in the URDF: no `PhysicsFixedJoint`.
- `Looks`: a `UsdPreviewSurface` per look `material` set, bound to its meshes. It has no
  transmission: a transmissive look is written in its opacity, as Blender writes it.

Names are the URDF's, made USD identifiers (any other character becomes `_`, a leading
digit takes one before it) and unique by a suffix, in a fixed order. Text only: `.usdc`,
the binary, needs USD's own library, which sand3d does not take. Dynamics are out, as in
the URDF: no mass, no drive, no collider.
"""
import math
import os
import re

from . import _core, materials
from .urdf import Mechanism, _clean, _d, _det3, _inv, _metres, _mul, _num

_I3 = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def _identifier(name):
    """`name` as a USD identifier: letters, digits and `_`, not starting with a digit."""
    out = re.sub(r"[^A-Za-z0-9_]", "_", name)
    return out if out and not out[0].isdigit() else "_" + out


def _tuple(vs):
    return "(" + ", ".join(_num(v) for v in vs) + ")"


def _array(rows):
    return "[" + ", ".join(_tuple(r) for r in rows) + "]"


def _quat(m):
    """The unit quaternion (w, x, y, z) of the rotation in `m` (rows), w ≥ 0 — or, at a
    half turn, its first non-zero part positive: one spelling per rotation."""
    t = m[0][0] + m[1][1] + m[2][2]
    if t > 0:
        s = 2 * math.sqrt(t + 1)
        q = [s / 4, (m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s]
    elif m[0][0] >= m[1][1] and m[0][0] >= m[2][2]:
        s = 2 * math.sqrt(1 + m[0][0] - m[1][1] - m[2][2])
        q = [(m[2][1] - m[1][2]) / s, s / 4, (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s]
    elif m[1][1] >= m[2][2]:
        s = 2 * math.sqrt(1 + m[1][1] - m[0][0] - m[2][2])
        q = [(m[0][2] - m[2][0]) / s, (m[0][1] + m[1][0]) / s, s / 4, (m[1][2] + m[2][1]) / s]
    else:
        s = 2 * math.sqrt(1 + m[2][2] - m[0][0] - m[1][1])
        q = [(m[1][0] - m[0][1]) / s, (m[0][2] + m[2][0]) / s, (m[1][2] + m[2][1]) / s, s / 4]
    q = [_clean(v) for v in q]
    if next(v for v in q if v != 0) < 0:
        q = [-v for v in q]
    return q


def _onto(a):
    """The token for a joint's axis `a` (unit, in its child link's frame) and the turn of
    that frame (rows) that brings the token's axis onto `a`: `a`'s own axis if it is +X,
    +Y or +Z; else X, by the shortest turn."""
    for i, token in enumerate("XYZ"):
        if abs(a[i] - 1) < 1e-9:
            return token, _I3
    x, y, z = a
    if x < -1 + 1e-9:                                     # -X: a half turn about Z
        return "X", [[-1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, 1.0]]
    k = 1 / (1 + x)                                       # Rodrigues, about X × a
    return "X", [[x, -y, -z], [y, 1 - y * y * k, -y * z * k], [z, -y * z * k, 1 - z * z * k]]


def _turned(m, r):
    """`m` (4×4 rows) turned by `r` (3×3 rows) about its own origin."""
    return [[sum(m[i][k] * r[k][j] for k in range(3)) for j in range(3)] + [m[i][3]] for i in range(3)] + [m[3]]


def _unit(kind):
    """A joint's unit in USD's, per unit of the program: metres, or degrees."""
    return _metres() if kind == "prismatic" else 1.0


class _Text:
    """usda, four spaces a level."""

    def __init__(self):
        self.lines, self.depth = [], 0

    def __call__(self, line):
        self.lines.append("    " * self.depth + line)

    def open(self, head, schemas=()):
        if self.lines and not self.lines[-1].endswith("{"):
            self.lines.append("")
        if schemas:
            self(head + " (")
            self("    prepend apiSchemas = [" + ", ".join(f'"{s}"' for s in schemas) + "]")
            self(")")
        else:
            self(head)
        self("{")
        self.depth += 1

    def close(self):
        self.depth -= 1
        self("}")


def _mesh(out, name, ob, m, unit, look):
    """`ob`'s mesh placed by `m` (rows: its link's frame from its own), × `unit`, as a Mesh
    prim — the OBJ's points and triangles, and the corners' normals."""
    me = ob.data
    det = _det3(m)
    rows = [[m[r][c] * unit for c in range(4)] for r in range(3)]
    co = [0.0] * (3 * len(me.vertices))
    me.vertices.foreach_get("co", co)
    points = [[r[0] * co[i] + r[1] * co[i + 1] + r[2] * co[i + 2] + r[3] for r in rows] for i in range(0, len(co), 3)]
    a = [row[:3] for row in m[:3]]
    carry = [[(a[(r + 1) % 3][(c + 1) % 3] * a[(r + 2) % 3][(c + 2) % 3]
               - a[(r + 1) % 3][(c + 2) % 3] * a[(r + 2) % 3][(c + 1) % 3]) / det for c in range(3)]
             for r in range(3)]                           # (M⁻¹)ᵀ: what carries a normal
    corner = [0.0] * (3 * len(me.loops))
    me.corner_normals.foreach_get("vector", corner)
    me.calc_loop_triangles()                  # Blender's triangles: a concave face fanned by a reader is wrong
    indices, normals = [], []
    for t in me.loop_triangles:
        vs, ls = list(t.vertices), list(t.loops)
        if det < 0:                                       # a mirror image: the winding turns over
            vs.reverse()
            ls.reverse()
        indices += vs
        for l in ls:
            n = [sum(carry[r][c] * corner[3 * l + c] for c in range(3)) for r in range(3)]
            size = math.sqrt(sum(v * v for v in n)) or 1.0
            normals.append([v / size for v in n])
    out.open(f'def Mesh "{name}"', ["MaterialBindingAPI"] if look else ())
    out("uniform bool doubleSided = 1")
    if points:
        low, high = ([f(p[i] for p in points) for i in range(3)] for f in (min, max))
        out(f"float3[] extent = {_array([low, high])}")
    out(f"int[] faceVertexCounts = [{', '.join(['3'] * len(me.loop_triangles))}]")
    out(f"int[] faceVertexIndices = [{', '.join(map(str, indices))}]")
    if look:
        out(f"rel material:binding = <{look}>")
    out(f"normal3f[] normals = {_array(normals)} (")
    out('    interpolation = "faceVarying"')
    out(")")
    out(f"point3f[] points = {_array(points)}")
    out('uniform token subdivisionScheme = "none"')
    out.close()


def _look(out, path, tag):
    """The Material of a tag, at `path`: a UsdPreviewSurface of its values."""
    v = materials.look(tag)
    rgb = materials._linear(v["color"])[:3]
    out.open(f'def Material "{path.rsplit("/", 1)[1]}"')
    out(f"token outputs:surface.connect = <{path}/PreviewSurface.outputs:surface>")
    out.open('def Shader "PreviewSurface"')
    out('uniform token info:id = "UsdPreviewSurface"')
    out(f"color3f inputs:diffuseColor = {_tuple(rgb)}")
    out(f"float inputs:roughness = {_num(v['roughness'])}")
    out(f"float inputs:metallic = {_num(v['metallic'])}")
    out(f"float inputs:opacity = {_num(v['opacity'] * (1 - v['transmission']))}")
    if v["coat"]:
        out(f"float inputs:clearcoat = {_num(v['coat'])}")
        out("float inputs:clearcoatRoughness = 0.05")
    if v["emission"]:
        out(f"color3f inputs:emissiveColor = {_tuple(c * v['emission'] for c in rgb)}")
    out("token outputs:surface")
    out.close()
    out.close()


def write_usda(root, path):
    mech = Mechanism(root, clean=_identifier)
    mech.check()
    k = mech.k
    unit = _metres()
    links, joints = mech.rest()
    joints = [j for j in joints if j["type"] != "floating"]
    by_name = {j["name"]: j for j in joints}
    frame = {key: F for key, _, F in links}
    top = mech.link[None]
    looks = {}                                            # tag -> the Material's path, in the order met

    def body_path(key):
        return f"/{top}/Geometry/{mech.link[key]}"

    out = _Text()
    out.open(f'def Xform "{top}"', ["PhysicsArticulationRootAPI"] if joints else ())
    out.open('def Scope "Geometry"')
    base = _inv(frame[None])
    for key, body, F in links:
        out.open(f'def Xform "{mech.link[key]}"', ["PhysicsRigidBodyAPI"])
        place = _mul(base, F)
        out(f"double3 xformOp:translate = {_tuple(place[r][3] * unit for r in range(3))}")
        out(f"quatd xformOp:orient = {_tuple(_quat(place))}")
        out('uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:orient"]')
        if key is None or body is not None:              # between two joints of one child: no geometry
            for ob in mech.meshes(body):
                name = mech.names.visual(_core.given_name(ob))
                tag = materials._nearest(ob)
                if tag is not None and tag not in looks:
                    looks[tag] = f"/{top}/Looks/{mech.names.unique('look', materials._name(tag))}"
                _mesh(out, name, ob, _mul(_inv(F), _d(k.rest_world(ob))), unit, looks.get(tag))
        out.close()
    out.close()

    if joints:
        out.open('def Scope "Joints"')
        for j in joints:
            kind = "Prismatic" if j["type"] == "prismatic" else "Revolute"
            follows = j["follows"]
            out.open(f'def Physics{kind}Joint "{j["name"]}"', ["NewtonMimicAPI"] if follows else ())
            token, turn = _onto(j["axis"])
            here = _turned(_mul(_inv(frame[j["parent"]]), frame[j["child"]]), turn)
            out(f'uniform token physics:axis = "{token}"')
            out(f"rel physics:body0 = <{body_path(j['parent'])}>")
            out(f"rel physics:body1 = <{body_path(j['child'])}>")
            out(f"point3f physics:localPos0 = {_tuple(here[r][3] * unit for r in range(3))}")
            out(f"quatf physics:localRot0 = {_tuple(_quat(here))}")
            out("point3f physics:localPos1 = (0, 0, 0)")
            out(f"quatf physics:localRot1 = {_tuple(_quat(turn))}")
            if j["type"] == "continuous":
                lo, hi = -math.inf, math.inf
            else:
                lo, hi = (v * _unit(j["kind"]) for v in j["span"])
            out(f"float physics:lowerLimit = {_num(lo)}")
            out(f"float physics:upperLimit = {_num(hi)}")
            if follows:
                leader, ratio, lead_kind = follows
                while by_name[leader]["follows"]:                # a chain, to its head: no reader takes one
                    leader, more, lead_kind = by_name[leader]["follows"]
                    ratio *= more
                out(f"rel newton:mimicJoint = </{top}/Joints/{leader}>")
                out("float newton:mimicCoef0 = 0")
                out(f"float newton:mimicCoef1 = {_num(ratio * _unit(j['kind']) / _unit(lead_kind))}")
            out.close()
        out.close()

    if looks:
        out.open('def Scope "Looks"')
        for tag, at in looks.items():
            _look(out, at, tag)
        out.close()
    out.close()

    path = os.fspath(path)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("#usda 1.0\n(\n")
        f.write(f'    defaultPrim = "{top}"\n')
        f.write(f'    doc = "written by sand3d: {top} at rest, metres and degrees"\n')
        f.write('    metersPerUnit = 1\n    upAxis = "Z"\n)\n\n')
        f.write("\n".join(out.lines) + "\n")
    return path
