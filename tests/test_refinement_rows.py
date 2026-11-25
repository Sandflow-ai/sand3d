"""Interior refinement points agree with the original scalar construction."""
import math
import random
import unittest
from types import SimpleNamespace
from mathutils import Vector
from sand3d.edit import _rows


def reference_rows(corners, sides, longest):
    """The rows of points to add inside a triangle whose sides will be cut in `sides`
    pieces, as (start, stop, pieces): rows parallel to its most cut side (the first of
    them), as many as its height over that side asks, each cut as its own length asks —
    about one point per longest² of area, however long and thin the triangle. The points
    are the row's inner cuts. In double precision."""
    k = max(range(3), key=lambda i: (sides[i], -i))
    a, b, c = (tuple(corners[(k + i) % 3].co) for i in range(3))
    ab = [q - p for p, q in zip(a, b)]
    ac = [q - p for p, q in zip(a, c)]
    base = math.sqrt(sum(x * x for x in ab))
    cross = (ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0])
    if not base or not all(math.isfinite(x) for x in cross):
        return []
    height = math.sqrt(sum(x * x for x in cross)) / base
    count = max(1, math.ceil(height / longest))
    rows = []
    for r in range(1, count):
        t = r / count
        rows.append(([p + (q - p) * t for p, q in zip(a, c)], [p + (q - p) * t for p, q in zip(b, c)],
                     max(1, math.ceil(base * (1 - t) / longest))))
    return rows


class RefinementRows(unittest.TestCase):
    def test_interior_points_and_order(self):
        rng = random.Random(73)
        triangles = [((0, 0, 0), (1, 0, 0), (0, h, 0))
                     for h in (0, 1e-8, 1, 2, 100)]
        triangles += [tuple(tuple(rng.uniform(-3, 3) for _ in range(3))
                            for _ in range(3)) for _ in range(100)]
        def points(rows):
            return [tuple(p + (q - p) * j / n for p, q in zip(start, stop))
                    for start, stop, n in rows for j in range(1, n)]
        for triangle in triangles:
            corners = [SimpleNamespace(co=Vector(p)) for p in triangle]
            for longest in (0.5, math.nextafter(1.0, 0), 1.0,
                            math.nextafter(1.0, 2), 2.0, 10.0):
                sides = [max(1, math.ceil((corners[i].co - corners[(i+1)%3].co).length / longest))
                         for i in range(3)]
                self.assertEqual(points(_rows(corners, sides, longest)),
                                 points(reference_rows(corners, sides, longest)))

    def test_fine_triangle_keeps_elements_and_labels(self):
        import bmesh
        from unittest.mock import patch
        from sand3d.edit import _refine
        for scale in (1e-12, 1.0, 1e12):
            bm = bmesh.new()
            try:
                verts = [bm.verts.new(Vector(p) * scale)
                         for p in ((0, 0, 0), (1, 0, 0), (0, 1, 0))]
                layer = bm.faces.layers.int.new('label')
                face = bm.faces.new(verts)
                face[layer] = 17
                before = [tuple(v.co) for v in bm.verts]
                with patch('sand3d.edit._rows', side_effect=AssertionError('unneeded rows')):
                    _refine(bm, 16 * scale, 'triangle')
                self.assertEqual([tuple(v.co) for v in bm.verts], before)
                self.assertEqual(list(bm.faces), [face])
                self.assertEqual(face[layer], 17)
                self.assertEqual(len(bm.edges), 3)
            finally:
                bm.free()
