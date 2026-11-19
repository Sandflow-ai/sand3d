"""Bounded voids below a plane, without changing their container."""

import math

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from . import _core
from .edit import _flat, _deform_parts, _tool_mesh, _solve, _offset, box_tool
from .frames import Frame, local


def fill(name, container, level, clearance=None):
    """Make the bounded voids below level; negative clearance overlaps the walls.

    A numeric level is local to a single container root. A Frame is a plane,
    with its normal pointing out of the fill. The result takes the plane's axes
    and stands on its own Z = 0; its face "top" is the level. Containers are preserved.
    None means -0.04 mm; explicit clearance is in the program's unit.
    """
    if clearance is None:
        clearance = -_core.mm(0.04)
    if isinstance(clearance, bool) or not isinstance(clearance, (int, float)) or not math.isfinite(clearance):
        raise ValueError("fill: clearance must be a finite length")
    roots = _flat([container])
    if not roots:
        raise ValueError("fill: container has no solids")
    if not isinstance(level, Frame):
        if isinstance(container, (list, tuple)):
            raise TypeError("fill: a list of containers needs a Frame level; group them for a local height")
        if isinstance(level, bool) or not isinstance(level, (int, float)) or not math.isfinite(level):
            raise ValueError("fill: level must be a finite height or a Frame")
        level = local(roots[0], z=level)
    matrix = _core.world(level.part) @ level._in_part() if level.part is not None else level.matrix
    if not all(math.isfinite(x) for row in matrix for x in row):
        raise ValueError("fill: level frame must be finite")
    inverse = matrix.inverted()
    meshes = []
    bm = None
    try:
        seen = set()
        for root in roots:
            for part, relative in _deform_parts(root, "fill"):
                if part in seen:
                    continue
                seen.add(part)
                mesh = _tool_mesh(part, inverse @ _core.world(root) @ relative, False)
                meshes.append(mesh)
                check = bmesh.new()
                check.from_mesh(mesh)
                valid = bool(check.faces) and all(e.is_manifold for e in check.edges)
                check.free()
                if not valid:
                    raise ValueError(_not_closed(part))
        coords = [v.co for mesh in meshes for v in mesh.vertices]
        if not coords:
            raise ValueError("fill: container has no solids")
        reach = max(v.length for v in coords) * 2 + _core.mm(1)
        if min(v.z for v in coords) >= 0:
            raise ValueError("fill: level is below the container bottom")
        box = box_tool(reach, True)
        base = box.data
        bpy.data.objects.remove(box, do_unlink=True)
        bm = _solve(base, meshes, "DIFFERENCE", False)
        meshes = []  # _solve consumes the operand meshes
        bm.normal_update()
        bm.verts.index_update()
        bm.faces.index_update()
        # Connected boundary shells: the artificial sides and bottom mark exterior.
        pending = set(bm.verts)
        shells = []
        while pending:
            start = min(pending, key=lambda v: v.index)
            pending.remove(start)
            stack, vertices = [start], [start]
            while stack:
                v = stack.pop()
                for edge in v.link_edges:
                    other = edge.other_vert(v)
                    if other in pending:
                        pending.remove(other)
                        vertices.append(other)
                        stack.append(other)
            exterior = any(
                abs(v.co.x) > reach * 0.99 or abs(v.co.y) > reach * 0.99 or v.co.z < -reach * 0.99
                for v in vertices
            )
            if not exterior:
                faces = set(f for v in vertices for f in v.link_faces)
                volume = (
                    sum(
                        f.verts[0].co.dot(f.verts[i].co.cross(f.verts[i + 1].co))
                        for f in sorted(faces, key=lambda f: f.index)
                        for i in range(1, len(f.verts) - 1)
                    )
                    / 6
                )
                shells.append((vertices, faces, volume))
        if not shells:
            raise ValueError(
                "fill: nothing retained at this level (below the cavity bottom, open rim or leak)"
            )
        positive = [(vs, fs) for vs, fs, volume in shells if volume > 0]
        if not positive:
            raise ValueError("fill: nothing retained at this level (open rim or leak)")
        kept = {v for vs, fs in positive for v in vs}
        trees = []
        for vs, fs in positive:
            vertices = sorted(vs, key=lambda v: v.index)
            indices = {v: i for i, v in enumerate(vertices)}
            faces = sorted(fs, key=lambda f: f.index)
            trees.append(
                BVHTree.FromPolygons([v.co for v in vertices], [[indices[v] for v in f.verts] for f in faces])
            )
        for vs, fs, volume in shells:
            if volume < 0:
                # Test each enclosing shell: a hollow submerged obstacle may also
                # contain a smaller positive cavity closer than the surrounding fill.
                for tree in trees:
                    point, normal, _, _ = tree.find_nearest(vs[0].co)
                    if point is not None and (vs[0].co - point).dot(normal) < 0:
                        kept.update(vs)
                        break
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v not in kept], context="VERTS")
        if not bm.faces or any(not e.is_manifold for e in bm.edges):
            raise ValueError("fill: boolean did not produce closed pockets; check container intersections")
        bm.normal_update()
        tolerance = max(_core.mm(1e-5), reach * 1e-7)
        top = {f for f in bm.faces if all(abs(v.co.z) <= tolerance for v in f.verts) and f.normal.z > 0.9}
        if clearance:
            moves = []
            for v in bm.verts:
                walls = [f for f in v.link_faces if f not in top]
                if any(f in top for f in v.link_faces):
                    # Solve in the level plane: the free surface stays exactly at level.
                    planes = []
                    for f in walls:
                        n = Vector((f.normal.x, f.normal.y, 0))
                        if n.length > 1e-6:
                            planes.append((n, -1))
                    if planes:
                        a = np.array([[n.x, n.y] for n, _ in planes])
                        xy = np.linalg.lstsq(a, np.full(len(a), -clearance), rcond=0.03)[0]
                        move = Vector((float(xy[0]), float(xy[1]), 0))
                    else:
                        move = Vector()
                    move.z = 0
                else:
                    move = _offset([(f.normal, -1) for f in walls], clearance)
                moves.append((v, move))
            for v, move in moves:
                v.co += move
        bm.faces.index_update()
        bm.edges.index_update()
        face_tags = [{"top"} if f in top else {"side"} for f in bm.faces]
        edge_tags = [{"top"} if any(f in top for f in e.link_faces) else {"rim"} for e in bm.edges]
        # Discard operand provenance: these are the fill's surfaces, not its walls'.
        for domain, prefix in ((bm.faces, _core.FACE_TAG), (bm.edges, _core.EDGE_TAG)):
            for label in list(domain.layers.bool.keys()):
                if label.startswith(prefix):
                    domain.layers.bool.remove(domain.layers.bool[label])
        _core.write_tags(bm, name, face_tags, edge_tags)
        # Like every solid, it stands on its own Z = 0: the origin is the deepest
        # point's depth under the level's origin, the free surface its top.
        depth = -min(v.co.z for v in bm.verts)
        for v in bm.verts:
            v.co.z += depth
        mesh = bpy.data.meshes.new(name)
        bm.to_mesh(mesh)
        ob = _core.link(bpy.data.objects.new(name, mesh))
        ob[_core.NAME] = name
        ob.matrix_basis = matrix @ Matrix.Translation((0, 0, -depth))
        return ob
    finally:
        if bm is not None:
            bm.free()
        for mesh in meshes:
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)


def _not_closed(part):
    """Which part is not a closed solid, and where: its open and over-shared edges, in its own frame."""
    name = _core.given_name(part)
    check = bmesh.new()
    check.from_mesh(part.data)
    try:
        if not check.faces:
            return f"fill: container part {name!r} has no faces — every part must be a closed solid"
        open_edges = [e for e in check.edges if len(e.link_faces) < 2]
        shared = [e for e in check.edges if len(e.link_faces) > 2]
        bad = open_edges + shared
        points = [v.co for e in bad for v in e.verts]
        lo = [min(p[i] for p in points) for i in range(3)]
        hi = [max(p[i] for p in points) for i in range(3)]
        where = ", ".join(f"{axis} {lo[i]:.4g}..{hi[i]:.4g}" for i, axis in enumerate("xyz"))
        counts = []
        if open_edges:
            counts.append(f"{len(open_edges)} open edge{'s' * (len(open_edges) > 1)}")
        if shared:
            counts.append(f"{len(shared)} edge{'s' * (len(shared) > 1)} shared by more than two faces")
        return (f"fill: container part {name!r} is not a closed solid: {' and '.join(counts)}, "
                f"in its own frame at {where}. Every part must be closed, even when its hollow is open "
                f"at the top; the usual causes are a profile that does not close, or a join or merge "
                f"that left a seam or two surfaces touching along an edge")
    finally:
        check.free()

