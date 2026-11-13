"""Criterion 5: a spoon and a fork from generic verbs, closed, in one piece."""
import importlib.util
import unittest
from pathlib import Path

import bpy  # noqa: F401 — before bmesh, which bpy provides
import bmesh

import sand3d as s3d

PROGRAM = Path(__file__).resolve().parents[1] / "programs/cutlery.py"


def load():
    spec = importlib.util.spec_from_file_location("cutlery", PROGRAM)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Cutlery(unittest.TestCase):

    def test_closed_and_in_one_piece(self):
        cutlery = load()
        for name in ("spoon", "fork"):
            s3d.empty_scene()
            ob = getattr(cutlery, name)()
            bm = bmesh.new()
            bm.from_mesh(ob.data)
            self.assertTrue(all(len(e.link_faces) == 2 for e in bm.edges), f"{name} is not closed")
            bm.verts.ensure_lookup_table()
            bm.verts.index_update()
            seen, todo = set(), [bm.verts[0]]
            while todo:
                v = todo.pop()
                if v.index in seen:
                    continue
                seen.add(v.index)
                todo += [e.other_vert(v) for e in v.link_edges]
            self.assertEqual(len(seen), len(bm.verts), f"{name} is in more than one piece")
            self.assertGreater(bm.calc_volume(), 0)
            bm.free()

    def test_no_category_verb_and_no_escape(self):
        source = PROGRAM.read_text(encoding="utf-8")
        self.assertNotIn("s3d.spoon", source)
        self.assertNotIn("s3d.fork", source)
        self.assertNotIn("import bpy", source)
        self.assertNotIn("bmesh", source)


if __name__ == "__main__":
    unittest.main()
