"""UV coordinates read off a part's own shape: islands, seams, projections, one atlas.

An island is a piece of surface laid flat. Its outline follows the real edges the verbs
made (a hard edge is always a seam, as a baked normal map needs), and what is inside is
laid by the simplest projection that keeps lengths:

- flat     a plane: as it is
- wall     a cylinder, an extrude's side, any surface ruled along one axis: unrolled
- cone     a cone, a tapered side: unrolled into a fan
- fold     any other surface that unrolls without stretch (two planes and the round between)
- tube     a wire or a sweep that bends: a straight strip along its length
- curved   what no plane can take without stretch (a fillet turning a corner, a dome): laid as
           rigidly as possible; a fillet stays on the wall it rounds

Everything works on millimetres in the world, so a texture has one scale over an assembly.
"""
import heapq
import json
import math

import numpy as np

from . import _core
from ._surface import meshes

#: Face attribute: the island of a face. Object property: what `unwrap` chose for the part.
ISLAND, REPORT = ".s3d_island", "s3d~unwrap"
UV = "UVMap"
#: A sharp edge is a seam past this turn; a smooth one past that (degrees).
HARD, FOLDED = 20.0, 75.0
#: Total angle defect (radians) under which a surface unrolls.
DEFECT = 0.05
#: Stretch a fillet may take, over 95% of its area, to stay on its wall.
BAND_STRETCH = 1.5
#: Mean stretch of a curved island past which it is cut in smaller ones.
CURVED_STRETCH = 1.15
#: A patch narrower than this share of the atlas folds onto its neighbour.
SLIVER = 1 / 512
#: The side of an atlas to pack in, over the root of what goes in it; and the length past
#: which an island in sight is cut to fit (a hidden one, or a ribbon this many times longer
#: than wide, is cut as soon as it does not).
ROOM, LONG, RIBBON = 1.15, 2.0, 100.0
#: Cells of the packing grid along the side of an atlas.
CELLS = 512
#: An island is hidden when less than this share of what it looks at is open space.
OPEN = 0.01

DIRECTIONS = {"+X": (1, 0, 0), "-X": (-1, 0, 0), "+Y": (0, 1, 0), "-Y": (0, -1, 0), "+Z": (0, 0, 1), "-Z": (0, 0, -1)}


def unwrap(ob, seam="+Y", margin=0.004, hidden=1):
    """UVs for every mesh of a part, a group, an assembly or a list: one shared atlas.

    Each surface is laid flat by its shape: planes as they are, walls, cylinders and cones
    unrolled, fillets kept on the wall they round, the rest with the least stretch. Hard edges
    are seams, save round a sliver, which folds onto its neighbour; a closed wall opens on the
    side looking `seam`, the back by default ("+X"… "-Z", in the world); a strip much longer
    than the atlas is cut. Islands keep one scale over the whole atlas and stand upright: V goes up
    the world on walls, along +Y on tops and bottoms. `hidden` is the scale of the islands
    nothing outside sees in the current pose (0.5: half as large; a see-through part hides
    nothing). `margin` is the gap between islands, a share of the atlas. Call it last, once
    everything is placed: a later edit leaves the UVs of what it touches behind."""
    if seam not in DIRECTIONS:
        raise ValueError(f"unwrap: seam={seam!r} is none of {sorted(DIRECTIONS)}")
    for name, value, low, high, what in (("margin", margin, 0, 0.1, "a share of the atlas from 0 to 0.1"),
                                         ("hidden", hidden, 0.05, 1, "a scale from 0.05 to 1")):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
            raise ValueError(f"unwrap: {name}={value!r} is not {what}")
    from .textures import DECAL
    parts = [p for p in meshes(ob) if DECAL not in p]
    if not parts:
        raise TypeError("unwrap: a part, a group, an assembly or a list of them is expected")
    surfaces = [_Surface(part, np.array(DIRECTIONS[seam], float)) for part in parts]
    sliver = SLIVER * math.sqrt(sum(float(s.area.sum()) for s in surfaces))
    for s in surfaces:
        s.join_slivers(sliver)
    islands = [i for s in surfaces for i in s.islands()]
    if hidden < 1:
        _scale_hidden(surfaces, islands, hidden)
    root = math.sqrt(sum(i.size() for i in islands))
    islands = [piece for i in islands for piece in i.cut(ROOM * root, LONG * root)]
    side, places = _pack([i.scale * i.mask_triangles() for i in islands], margin)
    for island, place in zip(islands, places):
        island.place = place
    for s in surfaces:
        s.write(side, [i for i in islands if i.surface is s])
    return ob


class _Island:
    def __init__(self, surface, kind, faces, uv, seams=frozenset()):
        self.surface, self.kind, self.faces, self.seams = surface, kind, faces, seams
        self.uv = uv                                         # {loop: (u, v)} in millimetres
        self.upright()
        self.place, self.scale = (0.0, 0.0), 1.0

    def size(self):
        return float(self.surface.area[self.faces].sum()) * self.scale ** 2

    def cut(self, limit, longest):
        """The island, or where it is longer than `longest`, its pieces along its length, each up to `limit`."""
        corners = np.array(list(self.uv.values())) * self.scale
        spans = np.ptp(corners, axis=0)
        axis = int(np.argmax(spans))
        ribbon = spans[axis] ** 2 > RIBBON * self.size()     # longer than wide, its width read on its area
        if spans[axis] <= (limit if self.scale < 1 or ribbon else longest):
            return [self]
        n = math.ceil(spans[axis] / limit - 1e-6)
        low, bins = float(corners[:, axis].min()), [[] for _ in range(n)]
        for f in self.faces:
            along = [self.uv[l][axis] * self.scale for l in self.surface.faces[f]]
            middle = round(((min(along) + max(along)) / 2 - low) * n / float(spans[axis]), 4)
            bins[min(int(middle), n - 1)].append(f)
        bins = [faces for faces in bins if faces]
        if len(bins) < 2:
            return [self]
        out = []
        for faces in bins:
            for part in self.surface.components(sorted(faces), lambda l: l not in self.seams):
                piece = _Island(self.surface, self.kind, part, {l: self.uv[l] for f in part for l in self.surface.faces[f]},
                                self.seams)
                piece.scale = self.scale
                out.append(piece)
        return out

    def upright(self):
        """Turn the island so that what goes up in the world goes up in it, its corner at 0."""
        s, up = self.surface, np.zeros(2)
        for axis in (np.array((0.0, 0.0, 1.0)), np.array((0.0, 1.0, 0.0)), np.array((1.0, 0.0, 0.0))):
            total = 0.0
            for f in self.faces:
                flat, frame = s.flat(f)
                turn = _turn(flat, [self.uv[l] for l in s.faces[f]])
                d = frame @ axis                             # the axis on the face's own plane
                up += s.area[f] * np.array((turn[0] * d[0] - turn[1] * d[1], turn[1] * d[0] + turn[0] * d[1]))
                total += s.area[f]
            if np.hypot(*up) > 0.2 * total:
                break
            up[:] = 0.0
        size = np.hypot(*up)
        c, n = (up[1] / size, up[0] / size) if size else (1.0, 0.0)
        if self.kind == "tube":                              # a strip stays along an axis of the atlas
            c, n = ((math.copysign(1, c), 0.0) if abs(c) >= abs(n) else (0.0, math.copysign(1, n)))
        turned = {l: (c * u - n * v, n * u + c * v) for l, (u, v) in self.uv.items()}
        low = np.min(np.array(list(turned.values())), axis=0)
        self.uv = {l: (u - low[0], v - low[1]) for l, (u, v) in turned.items()}

    def mask_triangles(self):
        s = self.surface
        return np.array([[self.uv[l] for l in t] for f in self.faces for t in s.triangles[f]]).reshape(-1, 3, 2)

    def stretch(self):
        s = self.surface
        rows = [(s.local(t), [self.uv[l] for l in t]) for f in self.faces for t in s.triangles[f]]
        return _stretch(np.array([r[0] for r in rows]), np.array([r[1] for r in rows]))


class _Surface:
    """One mesh as corners (Blender's loops), placed in the world, in millimetres."""

    def __init__(self, ob, seam):
        self.ob, self.seam = ob, seam
        mesh = self.mesh = _core.own_mesh(ob)
        m = np.array(_core.world(ob), float)
        co = np.empty(3 * len(mesh.vertices))
        mesh.vertices.foreach_get("co", co)
        self.points = (co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]) * _core.in_mm(1.0)
        flip = np.linalg.det(m[:3, :3]) < 0
        self.vert = np.empty(len(mesh.loops), np.int32)
        mesh.loops.foreach_get("vertex_index", self.vert)
        self.faces = [list(p.loop_indices)[::-1] if flip else list(p.loop_indices) for p in mesh.polygons]
        mesh.calc_loop_triangles()
        self.triangles = [[] for _ in self.faces]
        for t in mesh.loop_triangles:
            self.triangles[t.polygon_index].append(tuple(t.loops)[::-1] if flip else tuple(t.loops))
        self.owner = np.empty(len(mesh.loops), np.int32)
        self.next, self.prev = {}, {}
        normals = []
        for f, loops in enumerate(self.faces):
            p = self.points[self.vert[loops]]
            q = np.roll(p, -1, axis=0)
            normals.append(0.5 * np.cross(p - p[0], q - p[0]).sum(axis=0))
            for a, b in zip(loops, loops[1:] + loops[:1]):
                self.next[a], self.prev[b], self.owner[a] = b, a, f
        normals = np.array(normals).reshape(-1, 3)
        self.area = np.linalg.norm(normals, axis=1)
        self.normal = normals / np.maximum(self.area, 1e-12)[:, None]
        self.twin = self._twins()
        self.hard = self._hard()
        self.labels = self._labels()
        self._flat = {}
        self.first = {}                                      # {face: kind of its patch before slivers join it}

    def _twins(self):
        ends, twin = {}, {}
        for loops in self.faces:
            for l in loops:
                a, b = int(self.vert[l]), int(self.vert[self.next[l]])
                ends.setdefault((min(a, b), max(a, b)), []).append(l)
        for pair in ends.values():
            if len(pair) == 2 and self.vert[pair[0]] != self.vert[pair[1]]:
                twin[pair[0]], twin[pair[1]] = pair[1], pair[0]
        return twin

    def _hard(self):
        """Corners whose edge is always a seam."""
        sharp = self.mesh.attributes.get("sharp_edge")
        marked = set()
        if sharp is not None:
            for e, d in zip(self.mesh.edges, sharp.data):
                if d.value:
                    marked.add((min(e.vertices), max(e.vertices)))
        hard = set()
        for l, t in self.twin.items():
            if l > t:
                continue
            f, g = self.owner[l], self.owner[t]
            a, b = int(self.vert[l]), int(self.vert[t])
            angle = math.degrees(math.acos(max(-1.0, min(1.0, float(self.normal[f] @ self.normal[g])))))
            if angle > FOLDED or ((min(a, b), max(a, b)) in marked and angle > HARD):
                hard |= {l, t}
        return hard

    def _labels(self):
        """The plain names of each face: what its maker called it."""
        names = sorted(a.name for a in self.mesh.attributes
                       if a.name.startswith(_core.FACE_TAG) and "." not in a.name[len(_core.FACE_TAG):])
        labels = [set() for _ in self.faces]
        for name in names:
            for f, d in enumerate(self.mesh.attributes[name].data):
                if d.value:
                    labels[f].add(name[len(_core.FACE_TAG):])
        return [frozenset(x) for x in labels]

    # ------------------------------------------------------------ geometry

    def local(self, loops):
        """Corners in the plane of their own face."""
        flat, _ = self.flat(int(self.owner[loops[0]]))
        where = {l: i for i, l in enumerate(self.faces[int(self.owner[loops[0]])])}
        return [flat[where[l]] for l in loops]

    def flat(self, f):
        """A face in its own plane: its corners, and the 2 x 3 frame of that plane."""
        if f not in self._flat:
            p = self.points[self.vert[self.faces[f]]]
            sides = np.roll(p, -1, axis=0) - p
            n = self.normal[f]
            x = sides[int(np.argmax((sides ** 2).sum(axis=1)))]
            x = x - n * (x @ n)
            x = x / max(np.linalg.norm(x), 1e-12)
            frame = np.array((x, np.cross(n, x)))
            self._flat[f] = ((p - p[0]) @ frame.T, frame)
        return self._flat[f]

    def length(self, l):
        return float(np.linalg.norm(self.points[self.vert[l]] - self.points[self.vert[self.next[l]]]))

    def pairs(self, faces, seams=frozenset()):
        """Inner edges of a set of faces, one corner of each."""
        inside = set(faces)
        return [l for f in faces for l in self.faces[f]
                if l in self.twin and l < self.twin[l] and int(self.owner[self.twin[l]]) in inside
                and l not in self.hard and l not in seams]

    def components(self, faces, joined=lambda l: True):
        faces = list(faces)
        left, out = set(faces), []
        for f in faces:
            if f not in left:
                continue
            left.discard(f)
            todo, found = [f], []
            while todo:
                g = todo.pop()
                found.append(g)
                for l in self.faces[g]:
                    t = self.twin.get(l)
                    if t is not None and l not in self.hard and int(self.owner[t]) in left and joined(l):
                        left.discard(int(self.owner[t]))
                        todo.append(int(self.owner[t]))
            out.append(sorted(found))
        return out

    def wedges(self, faces, seams=frozenset()):
        """The points of a cut surface: {corner: id}, and how many."""
        parent = {l: l for f in faces for l in self.faces[f]}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for l in self.pairs(faces, seams):
            t = self.twin[l]
            for a, b in ((l, self.next[t]), (self.next[l], t)):
                a, b = find(a), find(b)
                if a != b:
                    parent[max(a, b)] = min(a, b)
        ids = {}
        return {l: ids.setdefault(find(l), len(ids)) for f in faces for l in self.faces[f]}, len(ids)

    def defect(self, faces):
        """The total angle by which the inner points of a surface miss a full turn."""
        wedge, n = self.wedges(faces)
        inner = [True] * n
        angle = [0.0] * n
        joined = set()
        for l in self.pairs(faces):
            joined |= {l, self.twin[l]}
        for f in faces:
            p = self.flat(f)[0]
            for i, l in enumerate(self.faces[f]):
                a, b = p[i - 1] - p[i], p[(i + 1) % len(p)] - p[i]
                turn = math.atan2(b[0] * a[1] - b[1] * a[0], a @ b) % (2 * math.pi)
                angle[wedge[l]] += turn
                if l not in joined or self.prev[l] not in joined:
                    inner[wedge[l]] = False
        return sum(abs(2 * math.pi - a) for a, i in zip(angle, inner) if i)

    def kind(self, faces):
        n, a = self.normal[faces], self.area[faces]
        mean = (n * a[:, None]).sum(axis=0)
        mean = mean / max(np.linalg.norm(mean), 1e-12)
        if (n @ mean).min() > math.cos(math.radians(1.0)):
            return "flat"
        if self.defect(faces) > DEFECT:
            return "curved"
        for centre, name in ((np.zeros(3), "wall"), ((n * a[:, None]).sum(axis=0) / a.sum(), "cone")):
            d = n - centre
            _, axes = np.linalg.eigh((d * a[:, None]).T @ d)
            if np.abs(d @ axes[:, 0]).max() < 0.02:
                return name
        return "fold"

    # ------------------------------------------------------------ islands

    def join_slivers(self, limit):
        """Open the hard edge between a patch narrower than `limit` and a neighbour it unrolls with."""
        patches = dict(enumerate(self.components(range(len(self.faces)))))
        for faces in patches.values():
            kind = self.kind(faces)
            self.first.update((f, kind) for f in faces)
        owner = {f: k for k, faces in patches.items() for f in faces}

        def width(faces):
            rim = sum(self.length(l) for f in faces for l in self.faces[f] if l in self.hard or l not in self.twin)
            return (2 * float(self.area[faces].sum()) / rim if rim else math.inf), rim
        kept = set()
        while True:
            thin = sorted((round(w, 4), k) for k, w in ((k, width(p)[0]) for k, p in patches.items() if k not in kept)
                          if w < limit)
            if not thin:
                return
            k = thin[0][1]
            rim, common = width(patches[k])[1], {}
            for f in patches[k]:
                for l in self.faces[f]:
                    t = self.twin.get(l)
                    if t is not None and l in self.hard and owner[int(self.owner[t])] != k:
                        common.setdefault(owner[int(self.owner[t])], []).append(l)
            for j in sorted(common, key=lambda j: (-round(sum(map(self.length, common[j])), 3), j)):
                if sum(map(self.length, common[j])) < 0.25 * rim:
                    break
                opened = {x for l in common[j] for x in (l, self.twin[l])}
                self.hard -= opened
                both = sorted(patches[k] + patches[j])
                if self.kind(both) != "curved":
                    uv, _ = self.unrolled(both)
                    if not _overlaps(np.array([[uv[l] for l in t] for f in both for t in self.triangles[f]])):
                        patches[j] = both
                        owner.update((f, j) for f in patches.pop(k))
                        kept.discard(j)
                        break
                self.hard |= opened
            else:
                kept.add(k)
                continue
            if k in patches:
                kept.add(k)

    def islands(self):
        out = []
        for patch in self.components(range(len(self.faces))):
            kind = self.kind(patch)
            if kind != "curved":
                out += self.laid(kind, patch)
                continue
            whole = self.tube(patch) or self.sheet(patch)
            out += [whole] if whole is not None else self.decomposed(patch)
        return out

    def tube(self, faces):
        """A patch that still carries its path: a straight strip, its length by its turn."""
        from ._coordinates import NAMES
        layers = [self.mesh.attributes.get(name) for name in NAMES]
        if None in layers:
            return None
        at = np.array([[d.value for d in layer.data] for layer in layers]).T
        turn, round_ = np.arctan2(at[:, 2], at[:, 1]), np.hypot(at[:, 1], at[:, 2])
        corners = [l for f in faces for l in self.faces[f]]
        used = sorted({int(self.vert[l]) for l in corners})
        total = float(np.max(at[used, 3]))
        if total <= 0 or round_[used].min() < 1e-3 * round_[used].max():
            return None
        reach = float(np.ptp(at[used, 0]))
        ratios = []                                          # of a length to the one the path says, along it
        for l in corners:
            d = abs(float(at[self.vert[l], 0] - at[self.vert[self.next[l]], 0]))
            if 1e-6 * reach < d <= 0.5 * reach:              # not round it, nor where a ring closes
                ratios.append(self.length(l) / d)
        if not ratios:
            return None
        ratios.sort()
        k = ratios[len(ratios) // 2]
        score = {}
        for f in faces:
            for l in self.faces[f]:
                score.setdefault(round(float(turn[self.vert[l]]), 2), []).append(float(self.normal[f] @ self.seam))
        start = max(sorted(score), key=lambda a: round(sum(score[a]) / len(score[a]), 3))
        uv = {}
        for f in faces:
            v = self.vert[self.faces[f]]
            x, y = np.cos(turn[v]).sum(), np.sin(turn[v]).sum()
            mean = math.atan2(y, x)
            mean = (mean - start) % (2 * math.pi)
            along = at[v, 0].copy()
            if np.ptp(along) > 0.5 * total:
                along[along < 0.5 * total] += total
            for l, t, r, a in zip(self.faces[f], turn[v], round_[v], along):
                angle = mean + (t - start - mean + math.pi) % (2 * math.pi) - math.pi
                uv[l] = (k * r * (angle - math.pi), k * a)
        if sum(float(_cross(np.array(uv[t[1]]) - uv[t[0]], np.array(uv[t[2]]) - uv[t[0]]))
               for f in faces for t in self.triangles[f]) < 0:
            uv = {l: (-u, v) for l, (u, v) in uv.items()}
        size = max(k * total, 1e-9)
        seams = {x for l in self.pairs(faces) for x in (l, self.twin[l])
                 if max(math.dist(uv[l], uv[self.next[self.twin[l]]]), math.dist(uv[self.next[l]], uv[self.twin[l]]))
                 > 1e-3 * size + 1e-3}
        island = _Island(self, "tube", faces, self.averaged(faces, uv, seams), frozenset(seams))
        mean, high, _, flipped = island.stretch()
        if flipped or mean > 1.25 or high > 1.8 or _overlaps(island.mask_triangles()):
            return None
        return island

    def sheet(self, faces):
        """A patch that looks one way all over (a wavy sheet), whole, where that hardly stretches it."""
        mean = (self.normal[faces] * self.area[faces][:, None]).sum(axis=0)
        mean = mean / max(np.linalg.norm(mean), 1e-12)
        if (self.normal[faces] @ mean).min() < math.cos(math.radians(FOLDED)):
            return None
        island = self.relaxed(faces)
        return island if island is not None and island.stretch()[0] < 1.05 else None

    def decomposed(self, patch):
        """A smooth surface no plane takes whole: its named pieces, fillets back on their walls."""
        by_name = self.components(patch, lambda l: self.labels[self.owner[l]] == self.labels[self.owner[self.twin[l]]])
        if len(by_name) == 1:
            by_name = self.flats_apart(patch)
        pieces = [(self.kind(p), p) for p in by_name]
        pieces = self.merged(pieces)
        solid = [[k, p, *self.unrolled(p), list(p)] for k, p in pieces if k != "curved"]
        out = []
        for _, band in sorted(((k, p) for k, p in pieces if k == "curved"), key=lambda x: -len(x[1])):
            if self.attached(band, solid):
                continue
            for k, part in self.parted(band, solid):
                if k is None or not self.attached(part, solid, only=k):
                    out += self.laid("curved", part)
        for k, p, uv, seams, faces in solid:
            if len(faces) > len(p):
                out.append(_Island(self, k + "+fillet", faces, uv, seams))
            else:
                out += self.laid(k, p)
        return out

    def flats_apart(self, patch):
        total = self.area[patch].sum()
        close = math.cos(math.radians(0.5))
        regions = self.components(patch, lambda l: self.normal[self.owner[l]] @ self.normal[self.owner[self.twin[l]]] > close)
        flat = [r for r in regions if self.area[r].sum() > 0.1 * total]
        taken = {f for r in flat for f in r}
        rest = [f for f in patch if f not in taken]
        inside = set(rest)
        return flat + self.components(rest, lambda l: int(self.owner[self.twin[l]]) in inside)

    def shared(self, a, b):
        other = set(b)
        return sum(self.length(l) for f in a for l in self.faces[f]
                   if l in self.twin and l not in self.hard and int(self.owner[self.twin[l]]) in other)

    def merged(self, pieces):
        """Neighbours that unroll together become one piece, the longest common edge first."""
        while True:
            best = None
            for i in range(len(pieces)):
                for j in range(i + 1, len(pieces)):
                    if "curved" in (pieces[i][0], pieces[j][0]):
                        continue
                    common = self.shared(pieces[i][1], pieces[j][1])
                    if common > 0 and (best is None or common > best[0] + 1e-6):
                        both = sorted(pieces[i][1] + pieces[j][1])
                        kind = self.kind(both)
                        if kind != "curved":
                            best = (common, i, j, kind, both)
            if best is None:
                return pieces
            _, i, j, kind, both = best
            pieces = [p for k, p in enumerate(pieces) if k not in (i, j)] + [(kind, both)]

    def laid(self, kind, faces):
        if kind != "curved":
            uv, seams = self.unrolled(faces)
            island = _Island(self, kind, faces, uv, seams)
            if not _overlaps(island.mask_triangles()):
                return [island]
            if kind == "flat" or len(faces) == 1:
                return [island]
        else:
            island = self.relaxed(faces)
            if island is not None:
                return [island]
        out = []
        for part in self.clusters(faces):
            island = self.relaxed(part) if len(part) < len(faces) else None
            if island is None and len(part) < len(faces) and len(part) > 1:
                out += self.laid("curved", part)
            elif island is None:
                out += [_Island(self, "flat", [f], dict(zip(self.faces[f], map(tuple, self.flat(f)[0])))) for f in part]
            else:
                out.append(island)
        return out

    def clusters(self, faces):
        """Pieces whose faces look at most 45 degrees away from their own."""
        for limit in (60.0, 45.0, 30.0, 15.0, 5.0):
            close = math.cos(math.radians(limit))
            left, out = set(faces), []
            while left:
                seed = min(left, key=lambda f: (-self.area[f], f))
                mean, found, heap = self.normal[seed] * self.area[seed], [], [(0.0, seed)]
                left.discard(seed)
                while heap:
                    _, f = heapq.heappop(heap)
                    direction = mean / max(np.linalg.norm(mean), 1e-12)
                    if found and self.normal[f] @ direction < close:
                        left.add(f)
                        continue
                    found.append(f)
                    if f != seed:
                        mean = mean + self.normal[f] * self.area[f]
                    for l in self.faces[f]:
                        t = self.twin.get(l)
                        if t is not None and l not in self.hard and int(self.owner[t]) in left:
                            g = int(self.owner[t])
                            left.discard(g)
                            heapq.heappush(heap, (1.0 - float(self.normal[g] @ direction), g))
                out.append(sorted(found))
            if len(out) > 1:
                return [c for part in out for c in self.components(part)]
        return [[f] for f in faces]

    # ------------------------------------------------------------ laying flat

    def tree(self, faces):
        """A tree through the faces that crosses the edges far from the seam side first."""
        across = np.cross(self.seam, (0.0, 0.0, 1.0) if abs(self.seam[2]) < 0.5 else (0.0, 1.0, 0.0))
        spread = self.points[self.vert[[l for f in faces for l in self.faces[f]]]] @ across
        low, reach = spread.min(), max(float(np.ptp(spread)), 1e-9)
        rows = []
        for l in self.pairs(faces):
            t = self.twin[l]
            f, g = int(self.owner[l]), int(self.owner[t])
            middle = 0.5 * (self.points[self.vert[l]] + self.points[self.vert[t]])
            turn = math.acos(max(-1.0, min(1.0, float(self.normal[f] @ self.normal[g]))))
            cost = float((self.normal[f] + self.normal[g]) @ self.seam) / 2 + 0.2 * turn
            cost += 0.01 * (float(middle @ across) - low) / reach    # of two alike, always the same one, past float noise
            rows.append((round(cost, 4), l))
        rows.sort()
        parent = {f: f for f in faces}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        links = {f: [] for f in faces}
        for _, l in rows:
            f, g = int(self.owner[l]), int(self.owner[self.twin[l]])
            a, b = find(f), find(g)
            if a != b:
                parent[max(a, b)] = min(a, b)
                links[f].append((g, l))
                links[g].append((f, self.twin[l]))
        return links

    def beside(self, l, uv):
        """The face across corner `l`'s edge, laid against it: {corner: (u, v)}."""
        t = self.twin[l]
        g = int(self.owner[t])
        flat = {c: np.array(p) for c, p in zip(self.faces[g], self.flat(g)[0])}
        a, b = np.array(uv[l]), np.array(uv[self.next[l]])
        p, q = flat[self.next[t]], flat[t]
        d, e = b - a, q - p
        size = max(np.hypot(*d) * np.hypot(*e), 1e-18)
        c, s = (d @ e) / size, (e[0] * d[1] - e[1] * d[0]) / size
        mid, off = 0.5 * (p + q), 0.5 * (a + b)
        return {k: (off[0] + c * (x[0] - mid[0]) - s * (x[1] - mid[1]),
                    off[1] + s * (x[0] - mid[0]) + c * (x[1] - mid[1])) for k, x in flat.items()}

    def unrolled(self, faces):
        """Faces laid one against the next; where a turn does not close, a seam."""
        links = self.tree(faces)
        root = max(faces, key=lambda f: (self.area[f], -f))
        uv = dict(zip(self.faces[root], map(tuple, self.flat(root)[0])))
        done, todo = {root}, [root]
        while todo:
            f = todo.pop(0)
            for g, l in sorted(links[f], key=lambda x: x[1]):
                if g not in done:
                    done.add(g)
                    uv.update(self.beside(l, uv))
                    todo.append(g)
        size = np.ptp(np.array(list(uv.values())), axis=0).max()
        seams = set()
        for l in self.pairs(faces):
            t = self.twin[l]
            gap = max(math.dist(uv[l], uv[self.next[t]]), math.dist(uv[self.next[l]], uv[t]))
            if gap > 1e-3 * size + 1e-3:
                seams |= {l, t}
        return self.averaged(faces, uv, seams), frozenset(seams)

    def averaged(self, faces, uv, seams):
        wedge, n = self.wedges(faces, seams)
        total, count = np.zeros((n, 2)), np.zeros(n)
        for l, w in wedge.items():
            total[w] += uv[l]
            count[w] += 1
        mean = total / count[:, None]
        return {l: tuple(mean[w]) for l, w in wedge.items()}

    def disk(self, faces):
        """Seams that open a surface into a disk, or None for one with no edge of its own."""
        links = self.tree(faces)
        crossed = {min(l, self.twin[l]) for rows in links.values() for _, l in rows}
        wedge, n = self.wedges(faces)
        joined = set(self.pairs(faces))
        border = [False] * n
        for f in faces:
            for l in self.faces[f]:
                if min(l, self.twin.get(l, l)) not in joined:
                    border[wedge[l]] = border[wedge[self.next[l]]] = True
        if not any(border):
            return None
        cut = {l for l in joined if l not in crossed}
        at = {}
        for l in cut:
            for w in (wedge[l], wedge[self.next[l]]):
                at.setdefault(w, set()).add(l)
        todo = [w for w in sorted(at) if len(at[w]) == 1 and not border[w]]
        while todo:                                          # a cut that ends inside opens nothing
            w = todo.pop()
            if len(at[w]) != 1 or border[w]:
                continue
            l = next(iter(at[w]))
            cut.discard(l)
            for x in (wedge[l], wedge[self.next[l]]):
                at[x].discard(l)
                if len(at[x]) == 1 and not border[x]:
                    todo.append(x)
        return frozenset(x for l in cut for x in (l, self.twin[l]))

    def relaxed(self, faces):
        """A curved surface laid as rigidly as possible, or None where that folds or stretches it."""
        mean = (self.normal[faces] * self.area[faces][:, None]).sum(axis=0)
        mean = mean / max(np.linalg.norm(mean), 1e-12)
        if (self.normal[faces] @ mean).min() < math.cos(math.radians(100)):
            return None                                      # it turns past a half sphere: no flat layout keeps it
        seams = self.disk(faces)
        if seams is None:
            return None
        wedge, n = self.wedges(faces, seams)
        links = self.tree(faces)
        root = max(faces, key=lambda f: (self.area[f], -f))
        uv = dict(zip(self.faces[root], map(tuple, self.flat(root)[0])))
        done, todo = {root}, [root]
        while todo:
            f = todo.pop(0)
            for g, l in sorted(links[f], key=lambda x: x[1]):
                if g not in done:
                    done.add(g)
                    uv.update(self.beside(l, uv))
                    todo.append(g)
        uv = self.rigid(faces, wedge, n, self.averaged(faces, uv, seams), {})
        island = _Island(self, "curved", faces, uv, seams)
        mean, _, _, flipped = island.stretch()
        if flipped or mean > CURVED_STRETCH or _overlaps(island.mask_triangles()):
            return None
        return island

    def rigid(self, faces, wedge, n, uv, pinned, rounds=40):
        """As-rigid-as-possible, from `uv`; the points of `pinned` ({id: (u, v)}) stay."""
        tris = [t for f in faces for t in self.triangles[f]]
        rest = np.array([self.local(t) for t in tris])
        ids = np.array([[wedge[l] for l in t] for t in tris])
        area = np.abs(_cross(rest[:, 1] - rest[:, 0], rest[:, 2] - rest[:, 0]))
        keep = area > 1e-9 * area.max()
        rest, ids, area = rest[keep], ids[keep], area[keep]
        x = np.zeros((n, 2))
        for l, w in wedge.items():
            x[w] = uv[l]
        free = np.ones(n, bool)
        for w, p in pinned.items():
            x[w], free[w] = p, False
        if not pinned:
            free[0] = False
        cot = np.empty((len(ids), 3))                        # of the angle opposite each side (i, i + 1)
        for i in range(3):
            a, b = rest[:, i] - rest[:, (i + 2) % 3], rest[:, (i + 1) % 3] - rest[:, (i + 2) % 3]
            cot[:, i] = (a * b).sum(axis=1) / area
        i, j = ids[:, [0, 1, 2]].ravel(), ids[:, [1, 2, 0]].ravel()
        w = cot.ravel()
        side = (rest[:, [0, 1, 2]] - rest[:, [1, 2, 0]]).reshape(-1, 2)
        diagonal = np.bincount(i, w, n) + np.bincount(j, w, n)
        diagonal = np.where(diagonal > 1e-9, diagonal, 1.0)

        def apply(v):
            d = w * (v[i] - v[j])
            return np.bincount(i, d, n) - np.bincount(j, d, n)
        reach = float(np.ptp(x, axis=0).max())
        for _ in range(rounds):
            before = x.copy()
            e = x[i] - x[j]
            c = (w * (side * e).sum(axis=1)).reshape(-1, 3).sum(axis=1)
            s = (w * (side[:, 0] * e[:, 1] - side[:, 1] * e[:, 0])).reshape(-1, 3).sum(axis=1)
            size = np.maximum(np.hypot(c, s), 1e-12)
            c, s = np.repeat(c / size, 3), np.repeat(s / size, 3)
            turned = np.stack((c * side[:, 0] - s * side[:, 1], s * side[:, 0] + c * side[:, 1]), axis=1)
            for k in range(2):
                b = np.bincount(i, w * turned[:, k], n) - np.bincount(j, w * turned[:, k], n)
                x[:, k] = _solve(apply, b, x[:, k], free, diagonal)
            if np.abs(x - before).max() < 2e-5 * reach:
                break
        return {l: tuple(x[k]) for l, k in wedge.items()}

    def parted(self, band, solid):
        """A network of fillets shared between the surfaces it rounds, each face to the nearest."""
        near = [k for k in range(len(solid)) if self.shared(band, solid[k][4]) > 1e-6]
        if len(near) < 2 or self.area[band].sum() > 2 * sum(self.area[solid[k][1]].sum() for k in near):
            return [(None, band)]
        inside, owner, heap = set(band), {}, []
        middle = {f: self.points[self.vert[self.faces[f]]].mean(axis=0) for f in band}

        def step(l, f, g):
            """From an edge, or from face `f`, to the middle of face `g`."""
            at = middle[f] if f in middle else 0.5 * (self.points[self.vert[l]] + self.points[self.vert[self.next[l]]])
            return round(float(np.linalg.norm(middle[g] - at)), 4)
        for k in near:
            for f in solid[k][4]:
                for l in self.faces[f]:
                    t = self.twin.get(l)
                    if t is not None and l not in self.hard and int(self.owner[t]) in inside:
                        g = int(self.owner[t])
                        heapq.heappush(heap, (step(l, f, g), k, g))
        while heap:
            cost, k, f = heapq.heappop(heap)
            if f in owner:
                continue
            owner[f] = k
            for l in self.faces[f]:
                t = self.twin.get(l)
                if t is not None and l not in self.hard and int(self.owner[t]) in inside:
                    g = int(self.owner[t])
                    if g not in owner:
                        heapq.heappush(heap, (cost + step(l, f, g), k, g))
        parts = self.components(band, lambda l: owner.get(int(self.owner[l])) == owner.get(int(self.owner[self.twin[l]])))
        return [(owner.get(part[0]), part) for part in parts]

    def attached(self, band, solid, only=None):
        """A fillet laid on the wall (or else the plane) it shares most edge with."""
        order = sorted(range(len(solid)), key=lambda k: (solid[k][0] == "flat", -self.shared(band, solid[k][4])))
        for k in order if only is None else [only]:
            kind, base, uv, seams, faces = solid[k]
            if self.shared(band, faces) < 1e-6 or self.area[band].sum() > 2 * self.area[base].sum():
                continue
            extra = self.through(band, faces, seams)
            if extra is None:
                continue
            both, cut = sorted(faces + band), seams | extra
            wedge, n = self.wedges(both, cut)
            pinned = {wedge[l]: uv[l] for f in faces for l in self.faces[f]}
            placed = dict(uv)
            done, todo = set(faces), list(faces)
            inside = set(both)
            while todo:
                f = todo.pop(0)
                for l in self.faces[f]:
                    t = self.twin.get(l)
                    if t is None or l in self.hard or l in cut:
                        continue
                    g = int(self.owner[t])
                    if g in inside and g not in done:
                        done.add(g)
                        placed.update(self.beside(l, placed))
                        todo.append(g)
            if done != inside:
                continue
            laid = self.rigid(both, wedge, n, self.averaged(both, placed, cut), pinned)
            trial = _Island(self, kind, band, {l: laid[l] for f in band for l in self.faces[f]})
            _, high, _, flipped = trial.stretch()
            whole = _Island(self, kind, both, dict(laid), cut)
            if flipped or high > BAND_STRETCH or _overlaps(whole.mask_triangles()):
                continue
            solid[k] = [kind, base, laid, cut, both]
            return True
        return False

    def through(self, band, base, seams):
        """The base's seams carried on across the band, to its far edge."""
        inside, under = set(band), set(base)
        touching, far, steps = set(), set(), {}
        for f in band:
            for l in self.faces[f]:
                t = self.twin.get(l)
                g = int(self.owner[t]) if t is not None and l not in self.hard else None
                a, b = int(self.vert[l]), int(self.vert[self.next[l]])
                if g in under:
                    touching |= {a, b}
                elif g in inside:
                    steps.setdefault(a, []).append((b, l))
                    steps.setdefault(b, []).append((a, l))
                else:
                    far |= {a, b}
        starts = sorted({int(self.vert[x]) for l in seams for x in (l, self.next[l])} & touching)
        extra = set()
        for start in starts:
            best, heap, seen = None, [(0.0, start, ())], set()
            while heap:
                cost, v, path = heapq.heappop(heap)
                if v in seen:
                    continue
                seen.add(v)
                if v in far and v not in touching:
                    best = path
                    break
                for w, l in sorted(steps.get(v, [])):
                    if w not in seen and w not in touching:
                        heapq.heappush(heap, (cost + self.length(l), w, path + (l,)))
            if best is None:
                return None
            extra |= {x for l in best for x in (l, self.twin[l])}
        return frozenset(extra)

    # ------------------------------------------------------------ the mesh

    def label(self, island):
        """An island's kind; with slivers folded on, the kind of its largest patch."""
        if "+" in island.kind or island.kind not in ("wall", "cone", "fold"):
            return island.kind
        area = {}
        for f in island.faces:
            kind = self.first.get(f, island.kind)
            area[kind] = area.get(kind, 0.0) + float(self.area[f])
        kind = max(sorted(area), key=lambda k: area[k])
        return kind if kind != "curved" else island.kind

    def write(self, side, islands):
        mesh = self.mesh
        while mesh.uv_layers:
            mesh.uv_layers.remove(mesh.uv_layers[0])
        layer = mesh.uv_layers.new(name=UV)
        uv = np.zeros(2 * len(mesh.loops))
        which = np.zeros(len(mesh.polygons), np.int32)
        report = []
        for k, island in enumerate(islands):
            for l, p in island.uv.items():
                uv[2 * l: 2 * l + 2] = [(island.scale * p[n] + island.place[n]) / side for n in (0, 1)]
            which[island.faces] = k
            mean, high, most, _ = island.stretch()
            report.append({"kind": self.label(island), "faces": len(island.faces), "stretch": round(mean, 4),
                           "p95": round(high, 4), "max": round(most, 4), "scale": island.scale,
                           "area": round(float(self.area[island.faces].sum()), 3)})
        layer.data.foreach_set("uv", np.round(uv, 7).astype(np.float32))
        old = mesh.attributes.get(ISLAND)
        if old is not None:
            mesh.attributes.remove(old)
        mesh.attributes.new(ISLAND, "INT", "FACE").data.foreach_set("value", which)
        mesh.update()
        self.ob[REPORT] = json.dumps({"side_mm": round(side, 6), "islands": report})


# ---------------------------------------------------------------- plane geometry

def _cross(a, b):
    return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]


def _turn(flat, uv):
    """The turn (cos, sin) that best takes a face's own corners onto its UVs."""
    p = np.array(flat) - np.mean(flat, axis=0)
    q = np.array(uv) - np.mean(uv, axis=0)
    c, s = float((p * q).sum()), float(_cross(p, q).sum())
    size = math.hypot(c, s)
    return (c / size, s / size) if size > 1e-12 else (1.0, 0.0)


def _stretch(rest, uv):
    """Over triangles, (area mean, 95th percentile, greatest) of how far a length is from kept: the
    larger of the greatest stretch and the greatest shrink; and whether any is turned over."""
    a, b = rest[:, 1] - rest[:, 0], rest[:, 2] - rest[:, 0]
    area = _cross(a, b)
    keep = np.abs(area) > 1e-9 * max(np.abs(area).max(), 1e-12)
    a, b, area = a[keep], b[keep], area[keep]
    c, d = uv[keep, 1] - uv[keep, 0], uv[keep, 2] - uv[keep, 0]
    jx = (c * b[:, 1:2] - d * a[:, 1:2]) / area[:, None]
    jy = (d * a[:, 0:1] - c * b[:, 0:1]) / area[:, None]
    e, f, g = (jx * jx).sum(axis=1), (jx * jy).sum(axis=1), (jy * jy).sum(axis=1)
    root = np.sqrt(np.maximum((e - g) ** 2 / 4 + f * f, 0))
    big = np.sqrt((e + g) / 2 + root)
    small = np.sqrt(np.maximum((e + g) / 2 - root, 1e-12))
    worst = np.maximum(big, 1 / small)
    weight = np.abs(area)
    order = np.argsort(worst, kind="stable")
    share = np.cumsum(weight[order]) / weight.sum()
    high = worst[order][min(int(np.searchsorted(share, 0.95)), len(order) - 1)]
    return (float((worst * weight).sum() / weight.sum()), float(high), float(worst.max()),
            bool((_cross(jx, jy) <= 0).any()))


def _solve(apply, b, x, free, diagonal):
    """Conjugate gradients on the free unknowns, from `x`."""
    r = np.where(free, b - apply(x), 0.0)
    z = r / diagonal
    p, rho = z.copy(), float(r @ z)
    limit = 1e-9 * max(float((b * b / diagonal).sum()), 1e-12)
    x = x.copy()
    for _ in range(min(4 * len(x) + 50, 300)):          # ARAP's next round corrects what is left
        if rho <= limit:
            break
        q = np.where(free, apply(p), 0.0)
        step = float(p @ q)
        if step <= 0:
            break
        x += rho / step * p
        r -= rho / step * q
        z = r / diagonal
        rho, old = float(r @ z), rho
        p = z + rho / old * p
    return x


def _raster(triangles, cell, shape, count=False):
    """Cells whose centre a triangle covers (`count`: how many do), and every cell of its corners."""
    grid = np.zeros(shape, np.int32)
    for t in triangles:
        low = np.floor(t.min(axis=0) / cell).astype(int)
        high = np.floor(t.max(axis=0) / cell).astype(int) + 1
        u = (np.arange(low[0], high[0]) + 0.5) * cell
        v = (np.arange(low[1], high[1]) + 0.5) * cell
        u, v = np.meshgrid(u, v)
        area = _cross(t[1] - t[0], t[2] - t[0])
        slack = 0.0 if count else 0.71 * cell
        inside = np.ones(u.shape, bool)
        for i in range(3):
            a, e = t[i], t[(i + 1) % 3] - t[i]
            size = max(math.hypot(*e), 1e-12)
            away = (e[0] * (v - a[1]) - e[1] * (u - a[0])) / size * (1 if area >= 0 else -1)
            inside &= away > -slack if not count else away > 0
        grid[low[1]:high[1], low[0]:high[0]] += inside
    return grid if count else grid > 0


def _overlaps(triangles):
    size = np.ptp(triangles.reshape(-1, 2), axis=0).max()
    if size <= 0:
        return False
    cell = size / 256
    low = triangles.reshape(-1, 2).min(axis=0)
    shape = tuple(np.ceil(np.ptp(triangles.reshape(-1, 2), axis=0) / cell).astype(int)[::-1] + 2)
    grid = _raster(triangles - low, cell, shape, count=True)
    return (grid > 1).sum() > 0.005 * max((grid > 0).sum(), 1) + 2


# ---------------------------------------------------------------- what is seen

def _scale_hidden(surfaces, islands, scale):
    """Scale the islands from which next to no straight line leaves the parts."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    from . import materials

    points, triangles, count = [], [], 0
    for s in surfaces:
        tag = materials._nearest(s.ob)
        look = materials.look(tag) if tag else {}
        if look.get("opacity", 1) < 1 or look.get("transmission", 0) > 0:
            continue
        points += [Vector(p) for p in s.points]
        triangles += [tuple(count + int(s.vert[l]) for l in t) for rows in s.triangles for t in rows]
        count += len(s.points)
    if not triangles:
        return
    tree = BVHTree.FromPolygons(points, triangles, all_triangles=True)
    golden = math.pi * (3 - math.sqrt(5))
    z = 1 - 2 * (np.arange(96) + 0.5) / 96
    around = golden * np.arange(96)
    rays = np.stack((np.sqrt(1 - z * z) * np.cos(around), np.sqrt(1 - z * z) * np.sin(around), z), axis=1)
    for island in islands:
        s = island.surface
        rows = [(f, t) for f in island.faces for t in s.triangles[f]]
        corners = np.array([s.points[s.vert[list(t)]] for _, t in rows])
        area = np.linalg.norm(np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1)
        edge = np.cumsum(area) / max(area.sum(), 1e-12)
        tried = out = 0
        for k in range(32):
            i = min(int(np.searchsorted(edge, (k + 0.5) / 32)), len(rows) - 1)
            u, v = (0.5 + 0.7548776662 * k) % 1, (0.5 + 0.5698402910 * k) % 1
            if u + v > 1:
                u, v = 1 - u, 1 - v
            p, q, r = corners[i]
            n = s.normal[rows[i][0]]
            origin = Vector(p + u * (q - p) + v * (r - p) + 0.05 * n)
            for d in rays[rays @ n > 0.05]:
                tried += 1
                out += tree.ray_cast(origin, Vector(d))[0] is None
            if out > OPEN * 32 * 48:                             # seen, whatever the other points see
                break
        if out <= OPEN * tried:
            island.scale = float(scale)


# ---------------------------------------------------------------- packing

def _pack(shapes, margin):
    """Where each island goes in one square, none turned: (its side in millimetres, corners).

    The longest first, each at the free place nearest the square's corner, on a grid of cells."""
    sizes = [np.ptp(s.reshape(-1, 2), axis=0) for s in shapes]
    total = sum(float(np.abs(_cross(s[:, 1] - s[:, 0], s[:, 2] - s[:, 0])).sum()) / 2 for s in shapes)
    cell = max(ROOM * math.sqrt(total), max(float(s.max()) for s in sizes)) / CELLS
    gap = max(1, round(margin * CELLS))
    taken = np.zeros((2 * CELLS, 2 * CELLS), bool)
    places = [None] * len(shapes)
    order = sorted(range(len(shapes)), key=lambda k: (-round(float(sizes[k].max()), 3), -round(float(sizes[k].prod()), 3), k))
    end = 0
    for k in order:
        w, h = (np.ceil(sizes[k] / cell - 1e-3).astype(int) + 1)
        mask = _raster(shapes[k], cell, (h, w))
        mask = mask[:np.flatnonzero(mask.any(axis=1)).max() + 1, :np.flatnonzero(mask.any(axis=0)).max() + 1]
        h, w = mask.shape
        full = np.zeros((h + gap, w + gap), bool)            # the gap goes on the upper right
        for dy in range(gap + 1):
            for dx in range(gap + 1):
                full[dy:dy + h, dx:dx + w] |= mask
        h, w = full.shape
        n = end + max(h, w)                                  # beside all that is there, there is room
        if n > len(taken):
            taken = np.pad(taken, (0, n))
        free = _free(taken[:n, :n], full)
        reach = np.maximum(np.arange(h, n + 1)[:, None], np.arange(w, n + 1)[None, :]).astype(np.int64)
        cost = np.maximum(reach, end) * (4 * n * n) + reach * (2 * n) + np.arange(n - h + 1)[:, None]
        y, x = np.unravel_index(int(np.argmin(np.where(free, cost, 1 << 60))), cost.shape)
        taken[y:y + h, x:x + w] |= full
        end = max(end, y + h, x + w)
        places[k] = ((x + gap / 2) * cell, (y + gap / 2) * cell)
    return end * cell, places


def _free(taken, full):
    """Where `full` fits: one bool per place of its corner."""
    h, w = full.shape
    n = taken.shape[0]
    if full.mean() > 0.85 or h * w <= 100:
        s = np.zeros((n + 1, n + 1), np.int32)
        s[1:, 1:] = taken.cumsum(axis=0, dtype=np.int32).cumsum(axis=1)
        return (s[h:, w:] - s[:-h, w:] - s[h:, :-w] + s[:-h, :-w]) == 0
    size = 1
    while size < n + max(h, w):
        size *= 2
    shape = (size, size)
    product = np.fft.irfft2(np.fft.rfft2(taken, shape) * np.conj(np.fft.rfft2(full, shape)), shape)
    return product[:n - h + 1, :n - w + 1] < 0.5
