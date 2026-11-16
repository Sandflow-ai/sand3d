"""What every verb shares: making a named object from a bmesh, and reading one back.

Nothing here is public. No function reads `bpy.context.active_object` or the
selection; the scene collection is the only context a verb touches.
"""
from functools import lru_cache
import hashlib
import math

import bpy  # before bmesh, which the bpy module only provides once loaded
import bmesh
import numpy as np
from mathutils import Matrix, Vector, geometry


#: Custom property holding the name a program gave an object (Blender may suffix ob.name).
NAME = "s3d_name"


def evaluated_mesh(ob, *, collection=None, preserve_all_data_layers=False):
    """Evaluate private, unlinked objects without updating the program's scene.

    Consume the temporary object and optional operand collection, even on failure.
    Their input data stays owned by the caller; the returned mesh is independent.
    """
    scene = bpy.data.scenes.new("_s3d_evaluation")
    objects = [ob] if collection is None else [ob, *collection.objects]
    try:
        scene.collection.objects.link(ob)
        if collection is not None:
            scene.collection.children.link(collection)
        with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
            graph = bpy.context.evaluated_depsgraph_get()
            return bpy.data.meshes.new_from_object(
                ob.evaluated_get(graph), depsgraph=graph,
                preserve_all_data_layers=preserve_all_data_layers)
    finally:
        bpy.data.batch_remove([*objects, scene, *([collection] if collection is not None else [])])


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


# Objects touched during the current public call. References live only until its hooks
# finish: removed IDs are filtered there, so a reused address cannot hit old state.
hook_objects = []
hook_all = False


def touch(value):
    """Conservatively include object arguments and results, including nested calls."""
    global hook_all
    from .assembly import Handle
    if isinstance(value, Handle):
        value = value.root
    if isinstance(value, bpy.types.Object):
        try:
            if value.type == "EMPTY":
                hook_all = True          # descendants may inherit or have been rebuilt
            hook_objects.append(value)
        except ReferenceError:
            pass
    elif isinstance(value, (list, tuple)):
        for item in value:
            touch(item)
    elif isinstance(value, dict):
        for item in value.values():
            touch(item)


def touched():
    """Live candidates; None requests the conservative whole-scene path."""
    if hook_all:
        return None
    live = {}
    for ob in hook_objects:
        try:
            if ob.as_pointer():
                live[ob.as_pointer()] = ob
        except ReferenceError:
            pass
    return list(live.values())


def link(ob):
    """Put `ob` in the scene, where the exporter and the depsgraph see it."""
    bpy.context.scene.collection.objects.link(ob)
    hook_objects.append(ob)
    return ob


#: Face tags that name a cap. An edge bounding such a face carries its name;
#: an edge between two other surfaces carries the verb's own kind (`side` for an
#: extrude, `rim` for a revolve, `seam` for a sweep or a loft).
CAPS = ("top", "bottom", "start", "end")
#: Prefixes of the mesh attributes that hold provenance tags: one per domain,
#: because a mesh attribute's name is unique across domains.
FACE_TAG, EDGE_TAG = "s3d_face:", "s3d_edge:"
#: The longest attribute name, in UTF-8 bytes, Blender keeps whole (4.5 and 5.2): it cuts a longer one.
NAME_MAX = 67


@lru_cache(maxsize=8192)
def _size(s):
    return len(s.encode())


def _fit(s, n):
    """`s`, or its first characters and a digest of it, in `n` bytes."""
    b = s.encode()
    return s if len(b) <= n else b[:max(n - 9, 0)].decode(errors="ignore") + "~" + hashlib.sha1(b).hexdigest()[:8]


@lru_cache(maxsize=8192)
def tag_key(prefix, tag):
    """The attribute name that holds `tag`: `prefix + tag`, or, past NAME_MAX bytes, the
    part before the last dot shortened with a digest, so long names stay apart and the
    cap after the dot (`plate.top`) still reads."""
    if _size(prefix + tag) <= NAME_MAX:
        return prefix + tag
    name, dot, cap = tag.rpartition(".")
    cap = _fit(cap, 20)
    return prefix + _fit(name, NAME_MAX - _size(prefix + dot + cap)) + dot + cap


@lru_cache(maxsize=8192)
def stored(prefix, tag):
    """`tag` as the attribute holding it spells it, without the prefix."""
    return tag_key(prefix, tag)[len(prefix):]


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
        self.parameters = {}
        self.bm = bmesh.new()
        from ._coordinates import NAMES
        for name in NAMES:
            self.bm.verts.layers.float.new(name)
        self.surface = self.bm.faces.layers.int.new(SURFACE)
        self.layers = {t: self.bm.faces.layers.bool.new(tag_key(FACE_TAG, t)) for t in self.TAGS}

    def lengthwise(self, rings, parameters, centres=None, lengths=None):
        """Construction coordinates on vertices; parameters select colour progression.

        Transported transverse offsets encode angle and radius without an angular seam.
        Edits move the geometry, not its construction coordinates.
        """
        from .frames import Frame, _transport
        centres = centres or [sum((v.co for v in dict.fromkeys(ring)), Vector()) / len(set(ring)) for ring in rings]
        if lengths is None:
            lengths = [0.]
            for a, b in zip(centres, centres[1:]):
                lengths.append(lengths[-1] + (b-a).length)
        frame = None
        layers = {name: self.bm.verts.layers.float.get(name) or self.bm.verts.layers.float.new(name)
                  for name in ('.s3d_s', '.s3d_x', '.s3d_y', '.s3d_extent')}
        self.bm.verts.index_update()
        self.parameters = {v.index: u for ring, u in zip(rings, parameters) for v in ring}
        for i, (ring, u, centre, distance) in enumerate(zip(rings, parameters, centres, lengths)):
            tangent = centres[min(i+1,len(centres)-1)] - centres[max(0,i-1)]
            if tangent.length < 1e-10:
                tangent = Vector((0,0,1))
            tangent.normalize()
            frame = Frame(centre, tangent) if frame is None else _transport(frame, centre, tangent)
            for v in dict.fromkeys(ring):
                offset = v.co-centre
                x,y = offset.dot(frame.x),offset.dot(frame.y)
                values = (distance, x, y,
                          distance/u if u else (lengths[-1] or 1.))
                for name,value in zip(layers,values):
                    v[layers[name]] = value

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
        if not self.parameters:
            from ._coordinates import NAMES
            for label in NAMES:
                bm.verts.layers.float.remove(bm.verts.layers.float[label])
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
            bm.faces.layers.bool.remove(bm.faces.layers.bool[tag_key(FACE_TAG, t)])
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
    def names(groups):
        tags = {tag for group in groups if group for tag in group}
        return {tag: {tag, f"{name}.{tag}"} if name and "." not in tag else {tag}
                for tag in tags}
    fnames, enames = names(face_tags), names(edge_tags)
    for domain, prefix, mapping in ((bm.faces, FACE_TAG, fnames), (bm.edges, EDGE_TAG, enames)):
        for tag in sorted({t for qualified in mapping.values() for t in qualified}):
            key = tag_key(prefix, tag)
            if domain.layers.bool.get(key) is None:
                domain.layers.bool.new(key)
    # Resolve handles only once every layer exists: adding one invalidates handles.
    flayers = {tag: tuple(bm.faces.layers.bool[tag_key(FACE_TAG, t)] for t in qualified)
               for tag, qualified in fnames.items()}
    elayers = {tag: tuple(bm.edges.layers.bool[tag_key(EDGE_TAG, t)] for t in qualified)
               for tag, qualified in enames.items()}
    for face, tags in zip(bm.faces, face_tags):
        for tag in tags:
            for layer in flayers[tag]:
                face[layer] = True
        face.smooth = True
    for edge, tags in zip(bm.edges, edge_tags):
        for tag in tags or ():
            for layer in elayers[tag]:
                edge[layer] = True
        edge.smooth = tags is None


def new_object(name, bm):
    """A mesh object named `name` from `bm`, its normals pointing out. Frees `bm`."""
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    return link(bpy.data.objects.new(name, mesh))


def extent(ob, axis):
    """The size of `ob`'s own mesh along an axis (0, 1, 2), before any placement."""
    co = np.empty(len(ob.data.vertices) * 3, dtype=np.float32)
    ob.data.vertices.foreach_get("co", co)
    values = co.reshape(-1, 3)[:, axis]
    if not len(values) or np.isnan(values).any():
        values = values.tolist()
        return max(values) - min(values)
    return float(values[values.argmax()]) - float(values[values.argmin()])


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
FACET_SMOOTH = False
FACET_CONFIGURED = False


def surface_edge(size):
    """Fixed-count target for an axisless surface; size is its local box extent."""
    return math.pi * max(size) / FACETS if FACETS is not None else 0.0


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
    layers = []
    for domain, prefix, additions in ((bm.faces, FACE_TAG, face_add), (bm.edges, EDGE_TAG, edge_add)):
        resolved = {}
        for tag in sorted({t for tags in additions.values() for t in tags}):
            key = tag_key(prefix, tag)
            layer = domain.layers.bool.get(key)
            resolved[tag] = layer if layer is not None else domain.layers.bool.new(key)
        layers.append(resolved)
    face_layers, edge_layers = layers
    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    for i, tags in face_add.items():
        f = bm.faces[i]
        for t in tags:
            f[face_layers[t]] = True
    for i, tags in edge_add.items():
        e = bm.edges[i]
        for t in tags:
            e[edge_layers[t]] = True
        e.smooth = False
    bm.normal_update()


class Law:
    """A checked, shape-preserving cubic law on [0, 1], scalar or two-dimensional."""

    def __init__(self, points, name="law", pairs=True):
        import bisect
        self._bisect = bisect.bisect_right
        message = f"{name}: a law is (u, value) pairs, strictly increasing from 0 to 1, with finite numbers"
        try:
            rows = list(points)
            self.u = [float(u) for u, v in rows]
            self.pair = isinstance(rows[0][1], (list, tuple))
            if self.pair and not pairs:
                raise ValueError(message)
            values = []
            for u, v in rows:
                if isinstance(v, (list, tuple)) != self.pair or (self.pair and len(v) != 2):
                    raise ValueError(message + "; do not mix scalars and pairs")
                values.append(tuple(float(x) for x in v) if self.pair else (float(v),))
            if (len(rows) < 2 or self.u[0] != 0 or self.u[-1] != 1
                    or any(a >= b for a, b in zip(self.u, self.u[1:]))
                    or not all(math.isfinite(x) for x in self.u + [x for v in values for x in v])):
                raise ValueError(message)
        except (TypeError, ValueError, IndexError) as e:
            raise ValueError(message) from e
        self.values = values
        h = [b - a for a, b in zip(self.u, self.u[1:])]
        self.slopes = []
        for k in range(len(values[0])):
            delta = [(b[k] - a[k]) / step for a, b, step in zip(values, values[1:], h)]
            if len(delta) == 1:
                slopes = delta * 2
            else:
                def end(h0, h1, d0, d1):
                    m = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
                    return 0.0 if m * d0 <= 0 else math.copysign(min(abs(m), 3 * abs(d0)), d0)
                slopes = [end(h[0], h[1], delta[0], delta[1])]
                for i in range(1, len(delta)):
                    a, b = delta[i - 1:i + 1]
                    w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
                    slopes.append((w1 + w2) / (w1 / a + w2 / b) if a * b > 0 else 0.0)
                slopes.append(end(h[-1], h[-2], delta[-1], delta[-2]))
            self.slopes.append(slopes)

    def __call__(self, u):
        i = min(max(self._bisect(self.u, u) - 1, 0), len(self.u) - 2)
        h = self.u[i + 1] - self.u[i]
        t = min(1.0, max(0.0, (u - self.u[i]) / h))
        out = tuple((2*t**3 - 3*t*t + 1)*self.values[i][k]
                    + (t**3 - 2*t*t + t)*h*m[i]
                    + (-2*t**3 + 3*t*t)*self.values[i + 1][k]
                    + (t**3 - t*t)*h*m[i + 1] for k, m in enumerate(self.slopes))
        return out if self.pair else out[0]


#: Object property: the angle in degrees past which a part's edges stay sharp (`smooth`).
SHADE = "s3d~smooth"
#: Edge attribute: edges their maker keeps sharp on a part shaded smooth, whatever the angle.
CREASE = "s3d~crease"


def shade_meshes(objects=None):
    """Enforce program shading after a verb, including rebuilt meshes: flat under a fixed
    facet count, and by its own angle for a part `smooth` shaded."""
    all_meshes = objects is None
    objects = list(bpy.data.objects if all_meshes else objects)
    own = {ob.data.as_pointer(): ob[SHADE] for ob in objects if ob.type == "MESH" and SHADE in ob}
    flat = FACETS is not None and not FACET_SMOOTH
    if not own and not flat:
        return
    kept = {ob.data.as_pointer() for ob in objects if ob.type == "MESH" and ob.get("s3d~merged.shading")}
    meshes = bpy.data.meshes if all_meshes else dict.fromkeys(ob.data for ob in objects if ob.type == "MESH")
    for mesh in meshes:
        if mesh.as_pointer() in kept:
            continue
        angle = own.get(mesh.as_pointer())
        if angle is not None:
            mesh.polygons.foreach_set("use_smooth", [angle > 0] * len(mesh.polygons))
            mesh.set_sharp_from_angle(angle=math.radians(angle))
            crease = mesh.attributes.get(CREASE)
            if crease is not None and angle > 0 and len(crease.data) == len(mesh.edges):
                forced = [False] * len(mesh.edges)
                crease.data.foreach_get("value", forced)
                sharp = mesh.attributes.get("sharp_edge") or mesh.attributes.new("sharp_edge", "BOOLEAN", "EDGE")
                now = [False] * len(mesh.edges)
                sharp.data.foreach_get("value", now)
                sharp.data.foreach_set("value", [a or b for a, b in zip(now, forced)])
        elif flat:
            mesh.polygons.foreach_set("use_smooth", [False] * len(mesh.polygons))


def turn_steps(paths):
    """Pieces for the greatest accumulated meridian turn in dense probe paths.

    The probes estimate curvature only; the caller evaluates the original curve
    again at the chosen parameters, retaining its interpolation stations.
    """
    turn = 0.0
    for path in paths:
        chords = [b - a for a, b in zip(path, path[1:])]
        directions = [v.normalized() for v in chords if v.length > 1e-10]
        angle = sum(math.atan2(a.cross(b).length, a.dot(b))
                    for a, b in zip(directions, directions[1:]))
        turn = max(turn, angle)
    return max(1, math.ceil(FACETS * turn / (2 * math.pi) - 1e-4))


def own_mesh(ob):
    """Detach shared data before a verb writes to this part alone; the call's hooks then
    revisit the part, even when the verb was handed only its parent."""
    hook_objects.append(ob)
    if ob.data.users > 1:
        ob.data = ob.data.copy()
    return ob.data
