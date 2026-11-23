"""A list of frames moves, turns and offsets like one frame."""
import unittest

import sand3d as s3d
from sand3d.edit import strict


def same(a, b):
    return [tuple(map(tuple, f.matrix)) for f in a] == [tuple(map(tuple, f.matrix)) for f in b]


class FrameLists(unittest.TestCase):

    def setUp(self):
        s3d.empty_scene()

    def distributions(self):
        body = s3d.box("body", 100, 50, 50)
        return {"grid": lambda: s3d.grid(2, 3, 50, 12, on=s3d.Frame((0, 0, 5))),
                "ring": lambda: s3d.ring(5, 20, start=15),
                "along": lambda: s3d.along(s3d.arc((0, 0, 0), 30, 0, 180), count=4),
                "snap": lambda: s3d.snap(body, [(x, -60, 10) for x in (-20, 0, 20)], direction=(0, 1, 0))}

    def test_every_distributor_moves_turns_and_offsets_like_one_frame(self):
        for name, make in self.distributions().items():
            with self.subTest(name):
                self.assertTrue(same(make().move(y=12), [f.move(y=12) for f in make()]))
                self.assertTrue(same(make().move(3, -2, 1), [f.move(3, -2, 1) for f in make()]))
                self.assertTrue(same(make().turn(rx=20, rz=45), [f.turn(rx=20, rz=45) for f in make()]))
                self.assertTrue(same(make().offset(4), [f.offset(4) for f in make()]))
                self.assertTrue(same(make().move(y=1).turn(rz=90).offset(2),
                                     [f.move(y=1).turn(rz=90).offset(2) for f in make()]))

    def test_at_list_reuses_names_in_prototype_order(self):
        a = s3d.box("same.001", 2, 2, 2)
        b = s3d.box("same", 3, 3, 3)
        frames = s3d.grid(2, px=10)
        with strict(False), self.assertWarnsRegex(UserWarning, "no copies placed"):
            self.assertEqual(s3d.at([a, s3d.rect(2, 2)], on=frames, scale=2), [])
        self.assertEqual((a.name, b.name), ("same.001", "same"))
        placed = s3d.at([a, b], on=frames)
        self.assertEqual([part.name for part in placed],
                         ["same.002", "same.003", "same.001", "same.004"])

    def test_it_stays_a_list_of_frames(self):
        frames = s3d.grid(4, 1, 20)
        self.assertIsInstance(frames, list)
        self.assertTrue(same(frames[1:].move(y=5), [f.move(y=5) for f in frames[1:]]))
        self.assertEqual(len((s3d.grid(2, 1, 50) + s3d.ring(3, 10)).move(z=1)), 5)
        self.assertEqual(len(([s3d.Frame()] + frames).move(z=1)), 5)
        self.assertEqual(len((frames * 2).move(z=1)), 8)
        self.assertNotIsInstance(frames + [(0, 0, 0)], type(frames), "points added: a plain list, as before")

    def test_grid_and_ring_are_laid_on_one_frame(self):
        with self.assertRaisesRegex(TypeError, r"^grid: on is one frame, not Frames: a grid or a ring is laid on one "
                                               r"plane$"):
            s3d.grid(2, on=s3d.grid(2, 1, 10))
        with self.assertRaisesRegex(TypeError, r"^ring: on is one frame, not list"):
            s3d.ring(3, 10, on=[])

    def test_a_hole_pattern_moved(self):
        """`hole(base, 4, on=s3d.grid(2, 1, 50, 0).move(y=12))`."""
        meshes = []
        for moved in (lambda g: g.move(y=12), lambda g: [f.move(y=12) for f in g]):
            s3d.empty_scene()
            a = s3d.box("a", 80, 40, 6)
            s3d.hole(a, 4, on=moved(s3d.grid(2, 1, 50, 0)))
            meshes.append(sorted(tuple(v.co) for v in a.data.vertices))
        self.assertEqual(meshes[0], meshes[1])
        self.assertTrue(any(abs(v[1] - 14) < 1e-4 for v in meshes[0]), "the holes are at y = 12")


if __name__ == "__main__":
    unittest.main()
