"""The determinism harness, bpy side: build cases, hash what they built.

A case is a function that builds something in an empty scene, registered with
the public verbs it exercises. `digest()` hashes every object the scene holds —
world placement, vertices, faces, edges and every named attribute, exactly (no
rounding) — plus whatever non-geometric value the case returns, so a verb that
returns points or frames is held to the same standard as one that returns a mesh.
Names are left out: Blender suffixes them (`plate.001`) and a mesh does not
depend on them.
"""
import hashlib
import struct

import bpy
from mathutils import Matrix

CASES = {}


def case(*verbs):
    """Register a case under its function name, exercising `verbs`."""
    def register(fn):
        CASES[fn.__name__] = (fn, tuple(verbs))
        return fn
    return register


def world(ob):
    """`ob`'s placement in the scene, computed from its parents — no depsgraph."""
    m = ob.matrix_parent_inverse @ ob.matrix_basis
    return world(ob.parent) @ m if ob.parent else Matrix(m)


def _object_digest(ob):
    h = hashlib.sha256()
    h.update(ob.type.encode())
    for row in world(ob):
        h.update(struct.pack("<4d", *row))
    if ob.type == "MESH":
        me = ob.data
        co = [0.0] * (3 * len(me.vertices))
        me.vertices.foreach_get("co", co)
        h.update(struct.pack(f"<{len(co)}f", *co))
        ev = [0] * (2 * len(me.edges))
        me.edges.foreach_get("vertices", ev)
        h.update(struct.pack(f"<{len(ev)}i", *ev))
        for p in me.polygons:
            h.update(struct.pack(f"<{len(p.vertices) + 1}i", len(p.vertices), *p.vertices))
        for att in sorted(me.attributes, key=lambda a: a.name):
            if att.name.startswith(".") or att.name == "position":
                continue
            h.update(f"{att.name}:{att.domain}:{att.data_type}".encode())
            if att.data_type in ("BOOLEAN", "INT", "FLOAT"):
                values = [d.value for d in att.data]
                h.update(repr([float(v).hex() for v in values]).encode())
        for mat in me.materials:   # only once a program sets a material: no other digest moves
            h.update(f"material:{mat.get('s3d_material') if mat else None}".encode())
    if ob.type == "LIGHT" and "s3d_light" in ob.data:            # only once a program makes a light: no other digest moves
        lamp = ob.data
        said = lamp["s3d_light"]
        values = [said["kind"], said["power"], said["color"], lamp.use_shadow, lamp.shadow_soft_size]
        values += [lamp.angle] if lamp.type == "SUN" else []
        values += [lamp.spot_size, lamp.spot_blend] if lamp.type == "SPOT" else []
        h.update(("light:" + ",".join(v if isinstance(v, str) else float(v).hex() for v in values)).encode())
    if "s3d_material" in ob:
        h.update(f"tag:{ob['s3d_material']}".encode())
    if "s3d~joints" in ob:            # only once a program declares a joint: no other digest moves
        from sand3d.joints import digest_text
        h.update(f"joints:{digest_text(ob)}".encode())
    return h.hexdigest()


def exact(value):
    """A value as text, floats in hex: two equal texts mean two equal values."""
    if isinstance(value, float):
        return value.hex()
    if value is None or isinstance(value, (str, int, bool)):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "(" + ",".join(exact(v) for v in value) + ")"
    if isinstance(value, dict):
        return "{" + ",".join(f"{k}:{exact(v)}" for k, v in sorted(value.items())) + "}"
    if isinstance(value, bpy.types.ID):
        return f"<{type(value).__name__}>"
    if hasattr(value, "__dict__") and not isinstance(value, type):
        fields = vars(value)
        if type(value).__name__ == "Frame":     # the part a frame was read on is no value of it
            fields = {k: v for k, v in fields.items() if k not in ("part", "_basis", "_seen")}
        return type(value).__name__ + exact(fields)
    try:
        return exact(tuple(value))  # mathutils vectors and matrices
    except TypeError:
        return repr(value)


def digest(returned=None):
    """The scene's objects, order-free, and the case's returned value."""
    objects = sorted(_object_digest(ob) for ob in bpy.data.objects)
    h = hashlib.sha256("\n".join(objects).encode())
    h.update(exact(returned).encode())
    return h.hexdigest()[:16]
