"""unwrap(by="build"): UVs read off the way a part was built.

A wire, sweep, loft, revolve or cylinder records on every vertex where it was made: `s` along its path or
axis, and `x`, `y` in its section (`_coordinates.NAMES`). Displace, bend, twist and the other edits move the
vertex and keep the record. So a part keeps the order of its rings and of its meridians however bumpy it has
become, and lays out as one strip around and along it, cut once, its two ends as flat caps. Faces without the
record (a merged part, a flat end closing a solid) and parts without it go through the shape path of `uvs`.
"""
import json
import math

import bmesh
import bpy
import numpy as np

from . import _core
from ._coordinates import NAMES

#: A ring is a pole cap where its section is under this share of the widest; the strip's scale stays under 1 / POLE.
POLE = 0.3
#: The grid the strip is measured on: rings along the path, meridians around it.
BINS, SECTORS = 96, 72


def _labels(mesh):
    out = {}
    for name in NAMES:
        layer = mesh.attributes.get(name)
        if layer is None:
            return None
        values = np.empty(len(mesh.vertices))
        layer.data.foreach_get("value", values)
        out[name] = values
    return out


def _corners(mesh):
    vert = np.empty(len(mesh.loops), np.int32)
    mesh.loops.foreach_get("vertex_index", vert)
    start = np.empty(len(mesh.polygons), np.int32)
    mesh.polygons.foreach_get("loop_start", start)
    total = np.empty(len(mesh.polygons), np.int32)
    mesh.polygons.foreach_get("loop_total", total)
    return vert, start, total


def _world_mm(ob):
    mesh = ob.data
    m = np.array(_core.world(ob), float)
    co = np.empty(3 * len(mesh.vertices))
    mesh.vertices.foreach_get("co", co)
    return (co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]) * _core.in_mm(1.0)


def _split(mesh, lab):
    """The faces the record covers, and the others: no record, or a flat end (all its corners on one ring)."""
    vert, start, total = _corners(mesh)
    s = lab[NAMES[0]]
    finite = lab[NAMES[-1]][np.isfinite(lab[NAMES[-1]])]
    extent = float(finite.max()) if finite.size else 1.0
    good, bad = [], []
    for f in range(len(mesh.polygons)):
        vv = vert[start[f]:start[f] + total[f]]
        if np.isnan(s[vv]).any() or np.ptp(s[vv]) < 1e-4 * extent:
            bad.append(f)
        else:
            good.append(f)
    return good, bad


def _subset(ob, faces):
    """A temporary part holding only `faces` of ob, each knowing the face it came from."""
    tmp = ob.copy()
    tmp.data = ob.data.copy()
    tmp.name = ob.name + "~build"
    for key in [k for k in tmp.keys() if k.startswith("s3d~unwrap")]:
        del tmp[key]
    bpy.context.scene.collection.objects.link(tmp)
    tmp.matrix_world = ob.matrix_world.copy()
    tmp.data.attributes.new(".s3d_from_face", "INT", "FACE").data.foreach_set(
        "value", np.arange(len(ob.data.polygons), dtype=np.int32))
    keep = set(faces)
    bm = bmesh.new()
    bm.from_mesh(tmp.data)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.faces[f] for f in range(len(bm.faces)) if f not in keep], context="FACES")
    bm.to_mesh(tmp.data)
    bm.free()
    return tmp


def _strips(ob, faces, lab, seam):
    """The recorded faces of a part as islands [(kind, {loop: (u, v)} in mm)]: a strip, and up to two caps.

    The strip keeps angles: U is the share of the ring from the cut times the widest ring, so every meridian is a
    vertical line; V is the mean meridian length, scaled at each ring as U is there, smoothed from ring to ring.
    Lengths are measured on the surface as it is now, on a grid of BINS rings by SECTORS meridians, each node the
    mean position of its vertices."""
    mesh = ob.data
    vert, start, total = _corners(mesh)
    s, x, y, e = (lab[n] for n in NAMES)
    points = _world_mm(ob)
    theta = np.arctan2(y, x)
    ext = float(np.nanmax(e[np.isfinite(e)])) if np.isfinite(e).any() else 1.0
    ds, dt = ext / BINS, 2 * math.pi / SECTORS
    # the cut: the meridian whose faces look most toward `seam`
    corners = [vert[start[f]:start[f] + total[f]] for f in faces]
    normals = []
    for vv in corners:
        p = points[vv]
        q = np.roll(p, -1, axis=0)
        n = 0.5 * np.cross(p - p[0], q - p[0]).sum(axis=0)
        normals.append(n / max(float(np.linalg.norm(n)), 1e-12))
    normals = np.array(normals).reshape(-1, 3)
    if np.linalg.det(np.array(_core.world(ob), float)[:3, :3]) < 0:
        normals = -normals
    sector = np.clip(((np.array([theta[vv].mean() for vv in corners]) + math.pi) / dt).astype(int), 0, SECTORS - 1)
    looks = np.bincount(sector, normals @ seam, SECTORS) / np.maximum(np.bincount(sector, None, SECTORS), 1)
    cut = -math.pi + (int(np.argmax(looks)) + 0.5) * dt
    rel = (theta - cut) % (2 * math.pi)
    # the grid of mean positions
    used = np.unique(np.concatenate(corners))
    b = np.clip((s[used] / ds).astype(int), 0, BINS - 1)
    k = np.clip((rel[used] / dt).astype(int), 0, SECTORS - 1)
    acc = np.zeros((BINS, SECTORS, 3))
    count = np.zeros((BINS, SECTORS))
    reach = np.zeros((BINS, SECTORS))
    angle = np.zeros((BINS, SECTORS))
    np.add.at(angle, (b, k), rel[used])
    np.add.at(acc, (b, k), points[used])
    np.add.at(count, (b, k), 1)
    np.add.at(reach, (b, k), np.hypot(x[used], y[used]))
    known = count > 0
    grid = np.where(known[..., None], acc / np.maximum(count, 1)[..., None], np.nan)
    radius = np.where(known, reach / np.maximum(count, 1), np.nan)
    ring = np.arange(SECTORS)
    for i in range(BINS):                                    # a ring's empty meridians, from its others
        ok = known[i]
        if 2 <= ok.sum() < SECTORS:
            for c in range(3):
                grid[i, :, c] = np.interp(ring, ring[ok], grid[i, ok, c], period=SECTORS)
            radius[i] = np.interp(ring, ring[ok], radius[i, ok], period=SECTORS)
    full = ~np.isnan(grid).any(axis=(1, 2))
    if not full.any():
        return []
    for kk in range(SECTORS):                                # empty rings, from their neighbours
        for c in range(3):
            grid[:, kk, c] = np.interp(np.arange(BINS), np.flatnonzero(full), grid[full, kk, c])
        radius[:, kk] = np.interp(np.arange(BINS), np.flatnonzero(full), radius[full, kk])
    around = np.linalg.norm(np.diff(np.concatenate([grid, grid[:, :1]], axis=1), axis=1), axis=2)
    perimeter = np.maximum(around.sum(axis=1), 1e-9)
    mean_r = radius.mean(axis=1)
    widest = float(mean_r.max())
    strip_rows = mean_r >= POLE * widest
    pref = float(perimeter[strip_rows].max()) if strip_rows.any() else float(perimeter.max())
    share = np.concatenate([np.zeros((BINS, 1)), np.cumsum(around, axis=1)], axis=1) / perimeter[:, None]
    share = share[strip_rows].mean(axis=0) if strip_rows.any() else share.mean(axis=0)
    # where each meridian of the grid sits around the ring: the mean angle of its vertices, not its sector's centre
    seen = known.sum(axis=0)
    node = np.where(seen > 0, angle.sum(axis=0) / np.maximum(count.sum(axis=0), 1), (ring + 0.5) * dt)
    node = np.r_[node, node[0] + 2 * math.pi]
    along = np.linalg.norm(np.diff(grid, axis=0), axis=2).mean(axis=1) * pref / (0.5 * (perimeter[:-1] + perimeter[1:]))
    kernel = np.array([1, 2, 3, 4, 3, 2, 1], float) / 16
    smooth = np.convolve(np.pad(along, 3, mode="edge"), kernel, mode="valid")
    height = np.r_[0.0, np.cumsum(smooth * along.sum() / max(float(smooth.sum()), 1e-12))]
    centres = (np.arange(BINS) + 0.5) * ds
    strip, caps = {}, ({}, {})
    for f, vv in zip(faces, corners):
        loops = range(start[f], start[f] + total[f])
        sf = float(s[vv].mean())
        if float(np.interp(sf, centres, mean_r)) < POLE * widest:
            cap = caps[0 if sf < ext / 2 else 1]
            for l, v in zip(loops, vv):
                cap[l] = v                                   # a vertex, laid flat below
            continue
        t = rel[vv].copy()
        if t.max() - t.min() > math.pi:                     # the face straddles the cut: kept whole, past the end
            t = np.where(t < math.pi, t + 2 * math.pi, t)
        turns = np.floor((t - node[0]) / (2 * math.pi))
        u = (np.interp(t - turns * 2 * math.pi, node, share) + turns) * pref
        v = np.interp(s[vv] / ds - 0.5, np.arange(BINS), height)   # height is read at the rings' centres
        for l, uu, w in zip(loops, u, v):
            strip[l] = (float(uu), float(w))
    out = [("strip", strip)] if strip else []
    for cap in caps:
        if not cap:
            continue
        ids = np.array(sorted(set(cap.values())))
        p = points[ids]
        centre = p.mean(axis=0)
        _, _, axes = np.linalg.svd(p - centre, full_matrices=False)
        flat = {int(i): ((points[i] - centre) @ axes[0], (points[i] - centre) @ axes[1]) for i in ids}
        out.append(("cap", {l: (float(flat[v][0]), float(flat[v][1])) for l, v in cap.items()}))
    return out


def _rest(points, triangles):
    """Each triangle in its own plane, in mm: (n, 3, 2)."""
    p = points[triangles]
    a, b = p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]
    e1 = a / np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-12)
    n = np.cross(a, b)
    e2 = np.cross(n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12), e1)
    out = np.zeros((len(p), 3, 2))
    out[:, 1, 0] = (a * e1).sum(1)
    out[:, 2, 0], out[:, 2, 1] = (b * e1).sum(1), (b * e2).sum(1)
    return out


def unwrap_built(parts, seam, margin, hidden):
    from . import uvs
    plans, shaped, temps = [], [], {}
    for part in parts:
        _core.own_mesh(part)
        lab = _labels(part.data)
        if lab is None:
            shaped.append(part)
            continue
        good, bad = _split(part.data, lab)
        if not good:
            shaped.append(part)
            continue
        plans.append((part, good, lab))
        if bad:
            tmp = _subset(part, bad)
            temps[tmp.name] = (tmp, part)
            shaped.append(tmp)
    records = []                                             # (part, kind, {loop of the part: (u, v) mm})
    try:
        if shaped:
            _, islands = uvs._shape_islands(shaped, seam, hidden)
            for island in islands:
                ob = island.surface.ob
                if ob.name in temps:
                    tmp, part = temps[ob.name]
                    origin = np.empty(len(tmp.data.polygons), np.int32)
                    tmp.data.attributes[".s3d_from_face"].data.foreach_get("value", origin)
                    first = {f: int(tmp.data.polygons[f].loop_start) for f in island.faces}
                    target = {}
                    for f in island.faces:
                        base = int(part.data.polygons[int(origin[f])].loop_start)
                        for c in range(tmp.data.polygons[f].loop_total):
                            target[first[f] + c] = base + c
                    uv = {target[l]: (p[0] * island.scale, p[1] * island.scale) for l, p in island.uv.items()}
                else:
                    part = ob
                    uv = {l: (p[0] * island.scale, p[1] * island.scale) for l, p in island.uv.items()}
                records.append((part, island.surface.label(island), uv))
        for part, good, lab in plans:
            for kind, uv in _strips(part, good, lab, seam):
                records.append((part, kind, uv))
    finally:
        for tmp, _ in temps.values():
            mesh = tmp.data
            bpy.data.objects.remove(tmp, do_unlink=True)
            bpy.data.meshes.remove(mesh)
    # one atlas: each island at its corner, then packed
    triangles = {}
    for part in {id(p): p for p, _, _ in records}.values():
        part.data.calc_loop_triangles()
        triangles[part.name] = [tuple(t.loops) for t in part.data.loop_triangles]
    shapes = []
    for part, kind, uv in records:
        low = np.array(list(uv.values())).min(axis=0)
        for l in uv:
            uv[l] = (uv[l][0] - low[0], uv[l][1] - low[1])
        shapes.append(np.array([[uv[l] for l in t] for t in triangles[part.name] if t[0] in uv]).reshape(-1, 3, 2))
    side, places = uvs._pack(shapes, margin)
    by_part = {}
    for (part, kind, uv), place, shape in zip(records, places, shapes):
        by_part.setdefault(part.name, (part, []))[1].append((kind, uv, place))
    for part, items in by_part.values():
        _write(part, side, items, triangles[part.name])


def _write(part, side, items, triangles):
    from . import uvs
    mesh = part.data
    points = _world_mm(part)
    vert, start, total = _corners(mesh)
    face_of = np.repeat(np.arange(len(mesh.polygons)), total)
    uv = np.zeros(2 * len(mesh.loops))
    which = np.zeros(len(mesh.polygons), np.int32)
    report = []
    for k, (kind, isl, place) in enumerate(items):
        for l, (u, v) in isl.items():
            uv[2 * l], uv[2 * l + 1] = (u + place[0]) / side, (v + place[1]) / side
            which[face_of[l]] = k
        tris = np.array([t for t in triangles if t[0] in isl])
        faces = np.unique(face_of[tris[:, 0]]) if len(tris) else np.zeros(0, int)
        if len(tris):
            mean, high, most, _ = uvs._stretch(_rest(points, vert[tris]), np.array([[isl[l] for l in t] for t in tris]))
            area = float(np.linalg.norm(np.cross(*(points[vert[tris[:, i]]] - points[vert[tris[:, 0]]] for i in (1, 2))), axis=1).sum() / 2)
        else:
            mean = high = most = area = 0.0
        report.append({"kind": kind, "faces": int(len(faces)), "stretch": round(mean, 4), "p95": round(high, 4),
                       "max": round(most, 4), "scale": 1.0, "area": round(area, 3)})
    while mesh.uv_layers:
        mesh.uv_layers.remove(mesh.uv_layers[0])
    mesh.uv_layers.new(name="UVMap").data.foreach_set("uv", np.round(uv, 7).astype(np.float32))
    old = mesh.attributes.get(".s3d_island")
    if old is not None:
        mesh.attributes.remove(old)
    mesh.attributes.new(".s3d_island", "INT", "FACE").data.foreach_set("value", which)
    mesh.update()
    part["s3d~unwrap"] = json.dumps({"side_mm": round(side, 6), "islands": report})
