"""What every verb shares: making a named object from a bmesh, and reading one back.

Nothing here is public. No function reads `bpy.context.active_object` or the
selection; the scene collection is the only context a verb touches.
"""
import math

import bpy  # before bmesh, which the bpy module only provides once loaded
import bmesh
from mathutils import Matrix, Vector, geometry


#: Custom property holding the name a program gave an object (Blender may suffix ob.name).
NAME = "s3d_name"


# ---------------------------------------------------------------- the program's unit

#: Millimetres in one unit of a program, by the names `units` takes.
UNITS = {"mm": 1.0, "cm": 10.0, "m": 1000.0}
#: The program's unit, and its size in millimetres.
UNIT, MM = "mm", 1.0
#: Whether a verb has measured anything in the unit since the scene was emptied: it is fixed then.
settled = False
#: Whether the program has set a material since the scene was emptied (`materials`).
dressed = False


def mm(x):
    """`x` millimetres in the program's unit: every tolerance is written in millimetres."""
    global settled
    settled = True
    return x / MM


def mm2(x):
    """`x` square millimetres in the program's unit squared."""
    global settled
    settled = True
    return x / (MM * MM)


def in_mm(x):
    """A length of the program in millimetres: where a decision rounds or compares."""
    global settled
    settled = True
    return x * MM


def triangulate(points, edges, output_type, eps):
    """Blender's constrained Delaunay triangulation of 2D `points`, `eps` in millimetres.
    It runs in millimetres: points on one circle (a rounded corner) are told apart by
    float noise, and a program in another unit must meet the same noise. The output
    points come back in the program's unit."""
    size = in_mm(1.0)
    out = geometry.delaunay_2d_cdt([Vector((p[0] * size, p[1] * size)) for p in points], edges, [],
                                   output_type, eps)
    return ([Vector((v.x / size, v.y / size)) for v in out[0]], *out[1:])


def world(ob):
    """`ob`'s placement in the scene, from its own and its parents' placements — no
    depsgraph, so it is current the moment `at` has run.

    Blender keeps a placement as location, Euler angles and scale, in single
    precision: a quarter turn comes back with 7.5e-8 where 0 was meant, and a face
    laid on another drifts off it by microns — enough for an exact boolean to see two
    planes and leave a sliver. Entries within 1e-6 of a whole number are snapped to it —
    a whole millimetre for the translation."""
    m = ob.matrix_parent_inverse @ ob.matrix_basis
    return snapped(world(ob.parent) @ m if ob.parent else Matrix(m))


def snapped(m):
    """`m` with its entries within 1e-6 of a whole number snapped to it — a whole
    millimetre for the translation (`world`)."""
    for row in range(4):
        for col in range(4):
            size = in_mm(1.0) if col == 3 and row < 3 else 1.0
            v = m[row][col] * size
            if abs(v - round(v)) < 1e-6:
                m[row][col] = round(v) / size
    return m


def unknown(owner, kind, missing, known):
    """The message for names `missing` among the `kind` ("edge", "face") names `known` of
    `owner`, with what a program most likely meant."""
    message = f"{owner} has no {kind} named {missing}; its {kind} names: {known}"
    plain = {k for k in known if "." not in k}      # what the edges are, not who made them
    first = missing[0].split(".")[-1]
    if first in ("start", "end") and {"top", "bottom"} <= plain:
        return message + (". extrude names its caps top and bottom; start and end are a sweep's, a loft's or a "
                          "partial revolve's")
    if first in ("top", "bottom") and {"start", "end"} <= plain:
        return message + (". A sweep, a loft or a partial revolve names its caps start and end; top and bottom "
                          "are an extrude's")
    if first == "side" and kind == "edge" and {"top", "bottom"} <= plain and "side" not in plain:
        return message + (". Its outline turns smoothly all round (a rounded rectangle, a circle): no corner "
                          "makes a side edge")
    import difflib
    near = difflib.get_close_matches(missing[0], known, n=1, cutoff=0.6)
    if near:
        return message + f". Did you mean {near[0]!r}?"
    if first in ("vertical", "horizontal", "outer", "inner", "edge", "edges", "corner", "corners", "upper", "lower"):
        return message + (f". {kind.capitalize()}s go by the names their maker gave them, not by direction: "
                          + ("an extrude's walls meet at side" if kind == "edge" else "an extrude's walls are side"))
    return message


def mm_tree(ob, matrix):
    """A BVH of `ob`'s mesh placed by `matrix`, in millimetres: Blender's BVH pads its boxes
    in its own units, which breaks ties — search it with points times `in_mm(1.0)`."""
    from mathutils.bvhtree import BVHTree
    size = in_mm(1.0)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.transform(matrix)
    if size != 1.0:
        bmesh.ops.scale(bm, vec=(size,) * 3, verts=bm.verts)
    tree = BVHTree.FromBMesh(bm)
    bm.free()
    return tree


def given_name(ob):
    return ob.get(NAME, ob.name)


def link(ob):
    """Put `ob` in the scene, where the exporter and the depsgraph see it."""
    bpy.context.scene.collection.objects.link(ob)
    return ob


#: Face tags that name a cap. An edge bounding such a face carries its name;
#: an edge between two other surfaces carries the verb's own kind (`side` for an
#: extrude, `rim` for a revolve, `seam` for a sweep or a loft).
CAPS = ("top", "bottom", "start", "end")
#: Prefixes of the mesh attributes that hold provenance tags: one per domain,
#: because a mesh attribute's name is unique across domains.
FACE_TAG, EDGE_TAG = "s3d_face:", "s3d_edge:"
#: Internal face attribute: which smooth surface a face belongs to.
SURFACE = "s3d~surface"


class Builder:
    """A solid under construction: faces carry a surface id and provenance tags.

    `finish` names the edges. An edge is a real edge when its two faces belong to
    different surfaces; it carries the cap names of the faces it bounds, or the
    verb's `kind` when it runs between two walls. Every tag also exists qualified
    by the object's name (`plate.top`), so a join keeps them apart.

    Adding a bmesh layer invalidates Python references to its elements, so every
    layer is made up front, and `finish` assigns by index once all exist.
    """

    TAGS = ("side",) + CAPS

    def __init__(self, name):
        self.name = name
        self.bm = bmesh.new()
        self.surface = self.bm.faces.layers.int.new(SURFACE)
        self.layers = {t: self.bm.faces.layers.bool.new(FACE_TAG + t) for t in self.TAGS}

    def vert(self, co):
        return self.bm.verts.new(co)

    def face(self, verts, surface, tags):
        """A face through `verts` (outward by the right-hand rule), or None if degenerate."""
        verts = [v for i, v in enumerate(verts) if v is not verts[i - 1]]
        if len(verts) < 3 or len(set(verts)) < len(verts):
            return None
        try:
            f = self.bm.faces.new(verts)
        except ValueError:  # the face exists already
            return None
        f[self.surface] = surface
        for tag in tags:
            f[self.layers[tag]] = True
        f.smooth = True
        return f

    def dissolve(self, faces):
        """Merge each cap's triangles into as few faces as its holes allow."""
        faces = set(f for f in faces if f is not None and f.is_valid)
        inner = [e for e in self.bm.edges if len(e.link_faces) == 2
                 and all(f in faces for f in e.link_faces)
                 and e.link_faces[0][self.surface] == e.link_faces[1][self.surface]]
        if inner:
            bmesh.ops.dissolve_edges(self.bm, edges=inner, use_verts=False, use_face_split=False)

    def finish(self, kind, rim=False):
        """The object. `rim`: every real edge also takes `kind`, save those bounding a
        start or end cap (a revolve's circles are rims whatever faces they bound)."""
        bm, name = self.bm, self.name
        bm.faces.index_update()
        bm.edges.index_update()
        face_tags = [{t for t, lay in self.layers.items() if f[lay]} for f in bm.faces]
        surfaces = [f[self.surface] for f in bm.faces]
        edge_tags = []
        for e in bm.edges:
            fs = [f.index for f in e.link_faces]
            if len(fs) == 2 and surfaces[fs[0]] == surfaces[fs[1]]:
                edge_tags.append(None)
                continue
            tags = {t for i in fs for t in face_tags[i] if t in CAPS}
            if not tags or (rim and not tags & {"start", "end"}):
                tags.add(kind)
            edge_tags.append(tags)
        for t in self.TAGS:  # by name each time: removing a layer invalidates the other handles
            bm.faces.layers.bool.remove(bm.faces.layers.bool[FACE_TAG + t])
        bm.faces.layers.int.remove(bm.faces.layers.int[SURFACE])
        write_tags(bm, name, face_tags, edge_tags)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        mesh = bpy.data.meshes.new(name)
        bm.to_mesh(mesh)
        bm.free()
        ob = link(bpy.data.objects.new(name, mesh))
        ob[NAME] = name
        return ob


def write_tags(bm, name, face_tags, edge_tags):
    """Write provenance onto `bm` by element index: tag sets per face and per edge
    (None for an edge that is no real edge), each tag plain and qualified by `name`.
    Real edges are marked sharp, faces smooth."""
    def qualified(tags):
        return set(tags) | {f"{name}.{t}" for t in tags if "." not in t} if name else set(tags)
    face_tags = [qualified(t) for t in face_tags]
    edge_tags = [None if t is None else qualified(t) for t in edge_tags]
    for t in sorted({t for tags in face_tags for t in tags}):
        if bm.faces.layers.bool.get(FACE_TAG + t) is None:
            bm.faces.layers.bool.new(FACE_TAG + t)
    for t in sorted({t for tags in edge_tags if tags for t in tags}):
        if bm.edges.layers.bool.get(EDGE_TAG + t) is None:
            bm.edges.layers.bool.new(EDGE_TAG + t)
    flayers = {lay.name[len(FACE_TAG):]: lay for lay in bm.faces.layers.bool.values()
               if lay.name.startswith(FACE_TAG)}
    elayers = {lay.name[len(EDGE_TAG):]: lay for lay in bm.edges.layers.bool.values()
               if lay.name.startswith(EDGE_TAG)}
    for f, tags in zip(bm.faces, face_tags):
        for t in tags:
            f[flayers[t]] = True
        f.smooth = True
    for e, tags in zip(bm.edges, edge_tags):
        for t in tags or ():
            e[elayers[t]] = True
        e.smooth = tags is None


def new_object(name, bm):
    """A mesh object named `name` from `bm`, its normals pointing out. Frees `bm`."""
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    return link(bpy.data.objects.new(name, mesh))


def extent(ob, axis):
    """The size of `ob`'s own mesh along an axis (0, 1, 2), before any placement."""
    values = [v.co[axis] for v in ob.data.vertices]
    return max(values) - min(values)


def bridge(bm, a, b):
    """Faces between two rings of vertices; a ring of one vertex is a pole."""
    n = max(len(a), len(b))
    for k in range(n):
        if len(a) == 1:
            bm.faces.new((a[0], b[(k + 1) % n], b[k]))
        elif len(b) == 1:
            bm.faces.new((a[k], a[(k + 1) % n], b[0]))
        else:
            bm.faces.new((a[k], a[(k + 1) % n], b[(k + 1) % n], b[k]))


#: Chord tolerance of every circle and arc, in millimetres, and the bounds on the
#: number of segments a full turn gets: a circle up to 10 mm gets 24, of 30 mm 39,
#: and anything from 84 mm the cap. A function of the radius in millimetres only, so a
#: verb's mesh depends on nothing but its arguments, the unit and the facets.
CHORD = 0.05
TURN_MIN, TURN_MAX = 24, 64
#: Segments of a full turn the program set with `facets`, the same for every radius; None: by
#: the chord tolerance above.
FACETS = None


def segments(r, sweep=360.0):
    """How many straight pieces an arc of radius `r` sweeping `sweep` degrees gets."""
    r = abs(in_mm(r))
    if FACETS is not None:
        per_turn = FACETS
    elif r <= CHORD:
        per_turn = TURN_MIN
    else:
        per_turn = math.ceil(math.pi / math.acos(1 - CHORD / r))
        per_turn = min(max(per_turn, TURN_MIN), TURN_MAX)
    return max(1, math.ceil(per_turn * abs(sweep) / 360.0 - 1e-9))


def add_tags(bm, face_add, edge_add):
    """Add names to elements of `bm` by index: {face index: tags}, {edge index: tags}.
    Edges that gain a name become sharp."""
    for t in sorted({t for tags in face_add.values() for t in tags}):
        if bm.faces.layers.bool.get(FACE_TAG + t) is None:
            bm.faces.layers.bool.new(FACE_TAG + t)
    for t in sorted({t for tags in edge_add.values() for t in tags}):
        if bm.edges.layers.bool.get(EDGE_TAG + t) is None:
            bm.edges.layers.bool.new(EDGE_TAG + t)
    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    for i, tags in face_add.items():
        f = bm.faces[i]
        for t in tags:
            f[bm.faces.layers.bool[FACE_TAG + t]] = True
    for i, tags in edge_add.items():
        e = bm.edges[i]
        for t in tags:
            e[bm.edges.layers.bool[EDGE_TAG + t]] = True
        e.smooth = False
    bm.normal_update()
