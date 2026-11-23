"""The trace `export` writes beside its file: what the program built, for a model to read."""
import json

import bpy
import bmesh

from . import _core, joints, materials, meshfile, urdf
from .edit import _open_edges


def write(root, path):
    """`root` and what hangs on it, nested as the GLB nests them, into a JSON file at `path`:
    in the world at the current pose, in metres."""
    mech = urdf.Mechanism(root)
    kids = {}
    for o in mech.members[1:]:
        p = joints.parent_of(o) if joints.jointed(o) else None
        up = p if p is not None and p.as_pointer() in mech.ids else o.parent
        kids.setdefault(up.as_pointer(), []).append(o)
    out = _trace(root, kids, mech.k, urdf._metres())
    out["joints"] = []        # the root's own joints are not in the export
    with _core.text_file(path) as f:
        json.dump(out, f)


def _r(v, n=9):
    """A length to the nanometre: float noise off."""
    return round(v, n) + 0.0


def _g(v):
    """An area or a volume to 9 significant digits."""
    return float(f"{v:.9g}")


def _trace(ob, kids, kin, unit):
    parts = [_trace(c, kids, kin, unit) for c in sorted(kids.get(ob.as_pointer(), []), key=_core.given_name)]
    boxes = [p["bbox"] for p in parts if p["bbox"]]
    open_edges = volume = None
    faces, edges = {}, []
    if ob.type == "MESH" and ob.data.vertices:
        pts = meshfile._triangles(ob, False)[0]
        boxes.append([[f(p[k] for p in pts) for k in range(3)] for f in (min, max)])
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        open_edges = _open_edges(bm)
        volume = None if open_edges else _g(bm.calc_volume() * unit ** 3)
        bm.free()
        areas = [p.area for p in ob.data.polygons]
        held = {(a.domain, a.name.split(":", 1)[1]): [v.value for v in a.data] for a in ob.data.attributes
                if a.name.startswith((_core.FACE_TAG, _core.EDGE_TAG))}
        for (domain, name), h in sorted(held.items()):
            plain = held.get((domain, name.rpartition(".")[2]))
            if not any(h) or ("." in name and h == plain):      # box.top where it is top: once
                continue
            if domain == "FACE":
                faces[name] = _g(sum(x for x, v in zip(areas, h) if v) * unit ** 2)
            else:
                edges.append(name)
    bbox = [[_r(f(b[i][k] for b in boxes)) for k in range(3)] for i, f in ((0, min), (1, max))] if boxes else None
    js = joints.joints_of(ob)
    frames = kin.frames(ob) if js else []
    tag = materials._nearest(ob)
    return {"name": _core.given_name(ob), "bbox": bbox, "open_edges": open_edges, "volume": volume,
            "faces": faces, "edges": edges, "joints": [_joint(ob, k, j, frames[k], unit) for k, j in enumerate(js)],
            "material": materials._name(tag) if tag else None, "parts": parts}


def _joint(ob, k, j, frame, unit):
    """The k-th joint of `ob`, `frame` its world frame after its own motion."""
    axis = joints.axis_in_world(ob, k, frame @ joints._matrix(j["pivot"]).inverted())[1]   # placed at that frame
    length = unit if j["kind"] == "prismatic" else 1.0
    span = urdf._span(ob, k, j)
    parent = joints.parent_of(ob)
    return {"name": j["name"], "kind": j["kind"], "on": _core.given_name(parent) if parent else None,
            "axis": None if axis is None else [_r(c, 6) for c in axis],
            "range": None if span is None else [_r(v * length) for v in span], "value": _r(j["value"] * length)}
