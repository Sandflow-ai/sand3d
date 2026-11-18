"""A program builds the same piece in every unit, to scale.

`run_units.py` builds the golden corpus in three fresh processes: as written, in
millimetres; then through `unitshim`, every length the program passes divided by the
unit's size, under the matching `s3d.units`, in two units:

- `p2`, 1 024 mm: a power of two, so scaling is exact in floating point. Each piece
  must come out the same to the last bit once converted back to millimetres: the same
  objects and placements, the same vertices, edges and faces, the same names on them,
  the same returned values. Any tolerance left in millimetres, or any Blender
  operation whose own tolerances are absolute run outside millimetres, shows here.
- `m`, metres: what a program in metres really gets. Its lengths are not exact in
  single precision where round millimetres were, so where two surfaces meet almost
  exactly a boolean or a bevel may settle otherwise and facet a spot differently. Each
  piece must still be the same piece: the same objects, placements, names and bounding
  box, and as many open edges. `METRE_EXCEPTIONS` lists the ones that are not, and why.

Vertices are matched by position, not index: their order follows their coordinates.

    python tests/test_units.py MM.json OTHER.json [--loose]   # the report, without the test
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MARK = "@@sand3d-units "
#: Millimetres: how far a metre piece's placement and bounding box may be from the millimetre one's.
TOL = 1e-2
#: Pieces a metre program does not build as the same piece, each with the reason.
METRE_EXCEPTIONS = {}


def build(units, tmp):
    """unit -> its corpus dump, the builds run side by side."""
    env = {**os.environ, "PYTHONPATH": f"{ROOT / 'src'}"}
    runs = {u: subprocess.Popen([sys.executable, str(HERE / "run_units.py"), str(Path(tmp) / f"{u}.json"),
                                 "--unit", u], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for u in units}
    out = {}
    for unit, run in runs.items():
        stdout, stderr = run.communicate(timeout=1800)
        if not any(line.startswith(MARK) for line in stdout.splitlines()):
            raise AssertionError(f"run_units.py --unit {unit} wrote nothing:\n{stderr[-3000:]}")
        out[unit] = json.loads((Path(tmp) / f"{unit}.json").read_text(encoding="utf-8"))["pieces"]
    return out


def _same_values(a, b, path="returned"):
    """None, or where two returned values first differ."""
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return f"{path}: {len(a)} items vs {len(b)}"
        return next((d for d in (_same_values(x, y, f"{path}[{i}]") for i, (x, y) in enumerate(zip(a, b))) if d),
                    None)
    if isinstance(a, dict) and isinstance(b, dict):
        if sorted(a) != sorted(b):
            return f"{path}: keys {sorted(a)} vs {sorted(b)}"
        return next((d for d in (_same_values(a[k], b[k], f"{path}.{k}") for k in a) if d), None)
    return None if a == b else f"{path}: {a!r} vs {b!r}"


def _key(ob):
    vs = ob.get("verts") or [[0, 0, 0]]
    centre = [round(sum(v[i] for v in vs) / len(vs), 1) for i in range(3)]
    return ob["name"], ob["type"], len(vs), centre


def _same_object(a, b):
    """None, or how two dumped objects differ, to the last bit."""
    import bpy  # noqa: F401 — mathutils comes with it
    from mathutils import Vector
    from mathutils.kdtree import KDTree
    if a["world"] != b["world"]:
        return f"{a['name']}: placed otherwise"
    if a.get("joints") != b.get("joints"):
        return f"{a['name']}: jointed otherwise"
    if a["type"] != "MESH":
        return None
    counts = [(len(a[k]), len(b[k])) for k in ("verts", "edges", "faces")]
    if any(x != y for x, y in counts):
        return f"{a['name']}: verts/edges/faces {[c[0] for c in counts]} vs {[c[1] for c in counts]}"
    # Vertices at one spot (shells that touch after a merge) are one place: compare places.
    first = {}
    place = [first.setdefault(tuple(v), i) for i, v in enumerate(a["verts"])]
    tree = KDTree(len(first))
    for v, i in first.items():
        tree.insert(v, i)
    tree.balance()
    twin = []
    for v in b["verts"]:
        _, i, dist = tree.find(Vector(v))
        if dist > 0:
            return f"{a['name']}: a vertex lands {dist:.3g} mm from its twin"
        twin.append(i)
    if Counter(twin) != Counter(place):
        return f"{a['name']}: vertices land on other places"

    def face(vs):
        k = vs.index(min(vs))
        return tuple(vs[k:] + vs[:k])
    edges_a = [frozenset(place[i] for i in e) for e in a["edges"]]
    edges_b = [frozenset(twin[i] for i in e) for e in b["edges"]]
    faces_a = [face([place[i] for i in f]) for f in a["faces"]]
    faces_b = [face([twin[i] for i in f]) for f in b["faces"]]
    if Counter(edges_a) != Counter(edges_b):
        return f"{a['name']}: {len(set(edges_a) ^ set(edges_b))} edges differ"
    if Counter(faces_a) != Counter(faces_b):
        return f"{a['name']}: {len(set(faces_a) ^ set(faces_b))} faces differ"
    if sorted(a["tags"]) != sorted(b["tags"]):
        return f"{a['name']}: names {sorted(set(a['tags']) ^ set(b['tags']))} on one side only"
    for tag in a["tags"]:
        elems_a, elems_b = (edges_a, edges_b) if tag.startswith("s3d_edge:") else (faces_a, faces_b)
        if Counter(elems_a[i] for i in a["tags"][tag]) != Counter(elems_b[i] for i in b["tags"][tag]):
            return f"{a['name']}: {tag} on other elements"
    return None


def _open_edges(ob):
    sides = Counter(frozenset((f[i - 1], f[i])) for f in ob["faces"] for i in range(len(f)))
    return sum(1 for n in sides.values() if n != 2)


def _like_object(a, b):
    """None, or how two dumped objects are not the same piece: placement, names, extent, open edges."""
    drift = max(abs(x - y) for ra, rb in zip(a["world"], b["world"]) for x, y in zip(ra, rb))
    if drift > TOL:
        return f"{a['name']}: placement off by {drift:.3g}"
    if a["type"] != "MESH":
        return None
    if sorted(a["tags"]) != sorted(b["tags"]):
        return f"{a['name']}: names {sorted(set(a['tags']) ^ set(b['tags']))} on one side only"
    for axis in range(3):
        for pick in (min, max):
            x, y = pick(v[axis] for v in a["verts"]), pick(v[axis] for v in b["verts"])
            if abs(x - y) > TOL:
                return f"{a['name']}: extent along {'xyz'[axis]} off by {abs(x - y):.3g}"
    if _open_edges(a) != _open_edges(b):
        return f"{a['name']}: {_open_edges(a)} open edges vs {_open_edges(b)}"
    return None


def compare(mm, other, exact=True):
    """piece -> None, or how it differs: to the last bit (`exact`) or as a piece."""
    out = {}
    for name in sorted(set(mm) | set(other)):
        a, b = mm.get(name), other.get(name)
        if a is None or b is None:
            out[name] = "built in one unit only"
        elif "error" in a or "error" in b:
            out[name] = f"raised: {a.get('error') or b.get('error')}"
        elif len(a["objects"]) != len(b["objects"]):
            out[name] = f"{len(a['objects'])} objects vs {len(b['objects'])}"
        else:
            same = _same_object if exact else _like_object
            pairs = zip(sorted(a["objects"], key=_key), sorted(b["objects"], key=_key))
            out[name] = next((d for d in (same(x, y) for x, y in pairs) if d), None)
            if exact and out[name] is None:
                out[name] = _same_values(a["returned"], b["returned"])
    return out


class Units(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as tmp:
            cls.built = build(("mm", "p2", "m"), tmp)

    def test_every_parameter_is_classified(self):
        from surface import surface
        from unitshim import LENGTHS
        published = {name: [p[0] for p in entry["params"]] for name, entry in surface(ROOT / "src/sand3d").items()
                     if entry["kind"] != "value"}
        unclassified = sorted(f"{n}({p})" for n, ps in published.items() for p in ps if p not in LENGTHS.get(n, {}))
        unclassified += sorted(n for n in published if n not in LENGTHS)
        self.assertEqual(unclassified, [], "parameters unitshim.LENGTHS does not classify")
        stale = sorted(n for n in LENGTHS if n not in published)
        self.assertEqual(stale, [], "unitshim.LENGTHS entries the surface no longer has")

    def test_an_exact_unit_builds_every_piece_to_the_bit(self):
        differ = {k: v for k, v in compare(self.built["mm"], self.built["p2"]).items() if v}
        self.assertEqual(differ, {}, "pieces a program in 1 024 mm does not build to scale")

    def test_a_metre_program_builds_the_same_pieces(self):
        differ = {k: v for k, v in compare(self.built["mm"], self.built["m"], exact=False).items() if v}
        self.assertEqual(sorted(differ), sorted(METRE_EXCEPTIONS),
                         "\n".join(f"{k}: {v}" for k, v in differ.items()))


class UnitSetting(unittest.TestCase):

    def setUp(self):
        import sand3d as s3d
        self.s3d = s3d
        s3d.empty_scene()
        s3d.units("mm")

    tearDown = setUp

    def test_millimetres_by_default(self):
        self.assertEqual(self.s3d.units(), "mm")

    def test_an_unknown_unit_raises(self):
        with self.assertRaisesRegex(ValueError, "none of"):
            self.s3d.units("in")

    def test_the_unit_is_fixed_once_a_verb_has_measured_in_it(self):
        s3d = self.s3d
        s3d.rect(10, 10)
        with self.assertRaisesRegex(ValueError, "before the first verb"):
            s3d.units("m")
        self.assertEqual(s3d.units("mm"), "mm")   # the same unit again is no change
        s3d.empty_scene()
        self.assertEqual(s3d.units("m"), "m")
        self.assertEqual(s3d.units(), "m")

    def test_export_scales_the_unit_to_metres(self):
        s3d = self.s3d
        for unit, scale in (("mm", 0.001), ("cm", 0.01), ("m", 1.0)):
            s3d.empty_scene()
            s3d.units(unit)
            root = s3d.group("thing", s3d.box("b", 1, 1, 1))
            with tempfile.TemporaryDirectory() as tmp:
                s3d.export(root, Path(tmp) / "thing.glb")
                glb = (Path(tmp) / "thing.glb").read_bytes()
            size = int.from_bytes(glb[12:16], "little")          # the JSON chunk follows the 12-byte header
            nodes = json.loads(glb[20:20 + size])["nodes"]
            thing = next(n for n in nodes if n.get("name") == "thing")
            for c in thing.get("scale", [1.0] * 3):   # single precision
                self.assertAlmostEqual(c, scale, places=9)
            self.assertEqual(tuple(root.scale), (1.0, 1.0, 1.0), "the model stays in its unit")

    def test_a_knurl_pitch_left_out_is_a_millimetre(self):
        """The default pitch was one unit of the program — a metre, in metres."""
        s3d = self.s3d
        in_mm = s3d.knurl("grip", 20, 30)
        mm_points = [tuple(v.co) for v in in_mm.data.vertices]
        s3d.empty_scene()
        s3d.units("m")
        in_m = s3d.knurl("grip", 0.02, 0.03)
        m_points = [tuple(c * 1000 for c in v.co) for v in in_m.data.vertices]
        self.assertEqual(len(m_points), len(mm_points), "the same teeth")
        self.assertLess(max(abs(a - b) for p, q in zip(m_points, mm_points) for a, b in zip(p, q)), 1e-3)
        with self.assertRaisesRegex(ValueError, "pitch"):
            s3d.knurl("grip", 0.02, 0.03, pitch=1)       # a metre, given: the guard stays
        with self.assertRaises(ValueError) as caught:
            s3d.knurl("pin", 0.0008, 0.005)
        self.assertEqual(str(caught.exception), "knurl: the diameter 0.0008 is not above the default pitch of 1 mm: "
                                                "give a smaller pitch")

    def test_a_knurl_counts_its_teeth_in_millimetres(self):
        """1.5 mm long in cm is 0.15 / 0.1 = 1.4999999999999998 pitches: it rounded to 1 ring
        where millimetres give 2."""
        s3d = self.s3d
        counts = []
        for unit, scale in (("mm", 1.0), ("cm", 0.1)):
            s3d.empty_scene()
            s3d.units(unit)
            counts.append(len(s3d.knurl("g", 20 * scale, 1.5 * scale, straight=True).data.vertices))
        self.assertEqual(counts[0], counts[1])

    # One process, several programs: a harness runs them back to back. A program that
    # sets no unit must build in millimetres whatever ran before it.

    def test_the_next_program_starts_in_millimetres(self):
        s3d = self.s3d
        s3d.units("m")
        s3d.box("b", 1, 1, 1)
        s3d.empty_scene()
        self.assertEqual(s3d.units(), "mm")

    def test_a_verb_that_raises_still_fixes_the_unit(self):
        s3d = self.s3d
        s3d.units("m")
        with self.assertRaises(ValueError):
            s3d.knurl("grip", 0.02, 0.03, pitch=1)   # raises before measuring anything
        with self.assertRaisesRegex(ValueError, "before the first verb"):
            s3d.units("cm")
        s3d.empty_scene()
        self.assertEqual(s3d.units(), "mm")

    def test_objects_built_without_a_verb_count(self):
        import bpy
        s3d = self.s3d
        s3d.units("m")
        bpy.context.scene.collection.objects.link(bpy.data.objects.new("raw", None))   # a `# raw` block
        s3d.empty_scene()
        self.assertEqual(s3d.units(), "mm")

    def test_a_unit_set_before_the_empty_scene_holds(self):
        s3d = self.s3d
        s3d.units("m")
        s3d.empty_scene()   # a program that opens on it, the unit set by its harness or its first line
        self.assertEqual(s3d.units(), "m")
        root = s3d.group("thing", s3d.box("b", 1, 1, 1))
        with tempfile.TemporaryDirectory() as tmp:
            s3d.export(root, Path(tmp) / "thing.glb")
        self.assertAlmostEqual(root.scale[0], 1.0, places=9)

    def test_a_millimetre_program_builds_the_same_after_a_metre_one(self):
        import cases  # noqa: F401  (registers the cases)
        import harness
        s3d = self.s3d
        names = ("edge_treatments", "holes_and_pockets", "metre_bracket", "sweeps")

        def build(name):
            s3d.empty_scene()
            fn = harness.CASES[name][0]
            return harness.digest(fn())

        fresh = {name: build(name) for name in names}
        for before in names:
            for name in names:
                build(before)
                self.assertEqual(build(name), fresh[name], f"{name} after {before}")


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        report = compare(*(json.loads(Path(p).read_text(encoding="utf-8"))["pieces"] for p in sys.argv[1:3]),
                         exact="--loose" not in sys.argv)
        for name, found in report.items():
            print(f"{'DIFF' if found else 'ok  '} {name:45} {found or ''}")
        print(f"{sum(1 for f in report.values() if f)} of {len(report)} pieces differ")
    else:
        unittest.main()
