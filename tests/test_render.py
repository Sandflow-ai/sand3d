"""A picture shows what the lights light: brightness follows the lux a face receives, whatever the unit."""
import math
import os
import tempfile
import unittest
import bpy
import sand3d as s3d
from test_determinism import run_cases


def linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def seen(root, box=(.4, .4, .6, .6), **kw):
    """The mean brightness (linear, 1: white) of a part of the picture: (left, bottom, right, top), as shares."""
    path = os.path.join(tempfile.mkdtemp(), "picture.png")
    s3d.render(root, path, **{"eye": (0, 0, 6000), "fov": 40, "size": (96, 64), "samples": 16, **kw})
    image = bpy.data.images.load(path)
    w, h = image.size
    px = list(image.pixels)
    bpy.data.images.remove(image)
    spots = [(x, y) for y in range(int(box[1] * h), int(box[3] * h)) for x in range(int(box[0] * w), int(box[2] * w))]
    return [sum(linear(px[4 * (y * w + x) + c]) for x, y in spots) / len(spots) for c in range(3)]


def floor(k=1.0):
    return s3d.material(s3d.box("floor", 8000 * k, 8000 * k, 20 * k), "plastic", color="#ffffff", roughness=1)


class Render(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()
        s3d.units('mm')

    def grey(self, got, want, places=.03):
        for channel in got:
            self.assertAlmostEqual(channel, want, delta=places)

    def test_a_white_face_under_pi_lux_is_white(self):
        self.grey(seen(s3d.assembly("a", floor(), s3d.light("sun", "sun", lux=math.pi))), 1)
        s3d.empty_scene()
        self.grey(seen(s3d.assembly("a", floor(), s3d.light("sun", "sun", lux=math.pi / 2))), .5)
        s3d.empty_scene()                                # a sun 60 degrees off the face's normal gives half
        self.grey(seen(s3d.assembly("a", floor(), s3d.at(s3d.light("sun", "sun", lux=math.pi), rx=60))), .5)
        s3d.empty_scene()
        self.grey(seen(s3d.assembly("a", floor(), s3d.light("sun", "sun", lux=math.pi)), exposure=.25), .25)

    def test_a_bulb_lights_by_its_distance_in_metres_whatever_the_unit(self):
        candela = math.pi * 2 ** 2                       # π lux at 2 m, straight under it
        under = (.47, .45, .53, .55)
        bulb = s3d.at(s3d.light("bulb", lm=4 * math.pi * candela), z=2020)
        self.grey(seen(s3d.assembly("a", floor(), bulb), under), 1)
        s3d.empty_scene()                                # twice as far: a quarter
        bulb = s3d.at(s3d.light("bulb", lm=4 * math.pi * candela), z=4020)
        self.grey(seen(s3d.assembly("a", floor(), bulb), under, eye=(0, 0, 12000)), .25)
        s3d.empty_scene()
        s3d.units('m')
        bulb = s3d.at(s3d.light("bulb", lm=4 * math.pi * candela), z=2.02)
        self.grey(seen(s3d.assembly("a", floor(.001), bulb), under, eye=(0, 0, 6)), 1)

    def test_what_stands_in_the_way_casts_a_shadow_unless_the_light_is_told_not_to(self):
        shade = (.45, .68, .55, .78)                     # the floor at y = 1000, where the lid's shadow falls
        for shadow, want in ((True, 0), (False, math.cos(math.radians(45)))):
            s3d.empty_scene()                            # a black lid: it sends no light back down
            lid = s3d.material(s3d.at(s3d.box("lid", 1000, 1000, 20), z=1000), "plastic", color="#000000")
            sun = s3d.at(s3d.light("sun", "sun", lux=math.pi, shadow=shadow), rx=45)
            self.grey(seen(s3d.assembly("a", floor(), lid, sun), shade), want)
        s3d.empty_scene()                                # an ambient light keeps the shadow from being black
        lid = s3d.material(s3d.at(s3d.box("lid", 1000, 1000, 20), z=1000), "plastic", color="#000000")
        sun = s3d.at(s3d.light("sun", "sun", lux=math.pi), rx=45)
        sky = s3d.light("sky", "ambient", lux=math.pi / 4)
        got = seen(s3d.assembly("a", floor(), lid, sun, sky), shade)
        self.assertTrue(all(.15 < channel < .26 for channel in got), got)   # a quarter, less what the lid hides

    def test_a_part_told_so_casts_no_shadow_and_is_still_seen_and_lit(self):
        shade = (.45, .68, .55, .78)                     # the floor at y = 1000, where the lid's shadow would fall
        lid = s3d.material(s3d.at(s3d.box("lid", 1000, 1000, 20), z=1000), "plastic", color="#ffffff", roughness=1)
        self.assertIs(s3d.shadow(lid, False), lid)
        sun = s3d.at(s3d.light("sun", "sun", lux=math.pi), rx=45)
        room = s3d.assembly("a", floor(), lid, sun)
        self.grey(seen(room, shade, bounces=0), math.cos(math.radians(45)))       # the sun goes through the lid
        self.grey(seen(room, (.45, .45, .55, .55), bounces=0), math.cos(math.radians(45)))   # which is lit and seen
        self.assertTrue(lid.visible_shadow)                                       # Blender's own flag is left alone
        twin = s3d.copy(lid)
        self.assertFalse(twin["s3d_shadow"])                                      # a copy casts none either
        s3d.shadow(room, True)                                                    # a tree tells each of its solids
        self.assertNotIn("s3d_shadow", lid)
        self.grey(seen(room, shade, bounces=0), 0)
        for wrong in (lambda: s3d.shadow(lid, 0), lambda: s3d.shadow(lid, "no")):
            with self.assertRaisesRegex(ValueError, "shadow:"):
                wrong()
        with self.assertRaisesRegex(TypeError, "shadow:"):
            s3d.shadow(sun, False)

    def test_light_sent_on_from_face_to_face_can_be_left_out(self):
        def by_the_wall(bounces):                        # a sun level with the floor lights only the wall
            s3d.empty_scene()
            wall = s3d.material(s3d.at(s3d.box("wall", 8000, 20, 4000), y=1500), "plastic", color="#ffffff",
                                roughness=1)
            sun = s3d.at(s3d.light("sun", "sun", lux=math.pi), rx=90)
            return seen(s3d.assembly("a", floor(), wall, sun), (.4, .74, .6, .80), bounces=bounces)[0]
        self.assertLess(by_the_wall(0), .01)             # straight light only: the floor gets none
        self.assertGreater(by_the_wall(4), .2)           # the white wall sends nearly half of its own down

    def test_film_bends_the_bright_end_and_keeps_the_backdrop(self):
        root = s3d.assembly("a", floor(), s3d.light("sun", "sun", lux=4 * math.pi))
        self.grey(seen(root), 1)                         # plain: four times white is white
        film = seen(root, tone="film")
        self.assertTrue(all(.5 < channel < .99 for channel in film), film)
        dim = seen(root, tone="film", exposure=1 / 16)
        self.assertTrue(all(channel < film[0] - .2 for channel in dim), dim)
        s3d.empty_scene()
        root = s3d.assembly("b", s3d.box("b", 10, 10, 10), s3d.light("sun", "sun"))
        for channel, want in zip(seen(root, (0, 0, .2, .2), background="#26211d", tone="film"), (0x26, 0x21, 0x1d)):
            self.assertAlmostEqual(channel, linear(want / 255), delta=.002)

    def test_a_wide_light_makes_a_soft_edge(self):
        def blurred(size):
            """Pixels of the row across the shadow's edge that are neither in the shadow nor in full light."""
            s3d.empty_scene()                            # the lid's shadow ends on the floor at x = 750
            lid = s3d.material(s3d.at(s3d.box("lid", 2000, 8000, 20), x=-1000, z=1000), "plastic", color="#000000")
            bulb = s3d.at(s3d.light("bulb", lm=280, size=size), x=-1500, z=3000)
            path = os.path.join(tempfile.mkdtemp(), "edge.png")
            s3d.render(s3d.assembly("a", floor(), lid, bulb), path, eye=(0, 0, 6000), size=(96, 64), samples=64)
            image = bpy.data.images.load(path)
            row = [linear(image.pixels[4 * (32 * 96 + x)]) for x in range(49, 70)]   # 68 mm of floor a pixel
            bpy.data.images.remove(image)
            return sum(.15 * row[-1] < v < .85 * row[-1] for v in row)
        self.assertLessEqual(blurred(0), 2)              # a sharp edge
        self.assertGreaterEqual(blurred(1600), 5)        # a bulb 1600 wide: an edge of 800, twelve pixels

    def test_an_ambient_light_comes_from_above_and_from_below(self):
        self.grey(seen(s3d.assembly("a", floor(), s3d.light("sky", "ambient", lux=math.pi))), 1)
        s3d.empty_scene()                                # a wall gets half of the sky and half of the ground
        wall = s3d.material(s3d.box("wall", 4000, 20, 4000), "plastic", color="#ffffff", roughness=1)
        sky = s3d.light("sky", "ambient", lux=math.pi, color="#ffffff", ground="#000000")
        self.grey(seen(s3d.assembly("a", wall, sky), eye=(0, -6000, 2000), target=(0, 0, 2000)), .5)
        s3d.empty_scene()                                # two of them add up; the sky shows behind the scene
        both = s3d.assembly("a", s3d.box("b", 10, 10, 10), s3d.light("one", "ambient", lux=1, color="#ff0000"),
                            s3d.light("two", "ambient", lux=1, color="#0000ff"))
        red, green, blue = seen(both, (0, 0, .2, .2))
        self.assertAlmostEqual(red, 1 / math.pi, delta=.02)
        self.assertAlmostEqual(blue, 1 / math.pi, delta=.02)
        self.assertAlmostEqual(green, 0, delta=.01)

    def test_the_background_is_shown_as_given(self):
        root = s3d.assembly("a", s3d.box("b", 10, 10, 10), s3d.light("sun", "sun"), s3d.light("sky", "ambient"))
        for exposure in (1, 5):
            got = seen(root, (0, 0, .2, .2), background="#26211d", exposure=exposure)
            for channel, want in zip(got, (0x26, 0x21, 0x1d)):
                self.assertAlmostEqual(channel, linear(want / 255), delta=.002)
        self.grey(seen(s3d.assembly("dark", s3d.box("c", 10, 10, 10)), (0, 0, 1, 1)), 0, .001)   # no light: black

    def test_only_the_tree_is_seen_and_only_its_lights_shine(self):
        room = s3d.assembly("room", floor(), s3d.light("sun", "sun", lux=math.pi / 2))
        s3d.at(s3d.light("other", "sun", lux=math.pi), ry=10)                  # not of the room
        s3d.at(s3d.box("roof", 9000, 9000, 20), z=3000)                        # nor is this, over the floor
        self.grey(seen(room), .5)

    def test_nothing_of_the_scene_is_changed(self):
        bulb = s3d.at(s3d.light("bulb", lm=800), z=2000)
        room = s3d.assembly("room", floor(), bulb, s3d.light("sky", "ambient"))
        scene = bpy.context.scene
        before = (sorted(o.name for o in bpy.data.objects), len(bpy.data.worlds), len(bpy.data.cameras),
                  scene.render.engine, scene.render.resolution_x, scene.view_settings.exposure, scene.camera,
                  scene.world, bulb.data.energy, [o.hide_render for o in bpy.data.objects])
        path = os.path.join(tempfile.mkdtemp(), "room.jpg")
        self.assertEqual(s3d.render(room, path, eye=(3000, -5000, 3000), size=(48, 32), samples=4), path)
        self.assertGreater(os.path.getsize(path), 0)
        after = (sorted(o.name for o in bpy.data.objects), len(bpy.data.worlds), len(bpy.data.cameras),
                 scene.render.engine, scene.render.resolution_x, scene.view_settings.exposure, scene.camera,
                 scene.world, bulb.data.energy, [o.hide_render for o in bpy.data.objects])
        self.assertEqual(before, after)

    def test_errors(self):
        room = s3d.assembly("room", floor(), s3d.light("sun", "sun"))
        folder = tempfile.mkdtemp()
        good = dict(path=os.path.join(folder, "p.png"), eye=(0, 0, 6000))
        for kw in (dict(path=os.path.join(folder, "p.gif")), dict(path=os.path.join(folder, "p")),
                   dict(eye=(0, 0)), dict(eye="above"), dict(eye=(0, 0, 0)), dict(target=(0, 0, math.nan)),
                   dict(fov=0), dict(fov=180), dict(fov="wide"), dict(size=(0, 64)), dict(size=(96, 64.5)),
                   dict(size=96), dict(exposure=0), dict(exposure="bright"), dict(samples=0), dict(samples=1.5),
                   dict(bounces=-1), dict(bounces=1.5), dict(bounces=True), dict(tone="aces"), dict(tone=None),
                   dict(background="dark"), dict(background=(2, 0, 0))):
            with self.subTest(kw=kw), self.assertRaisesRegex(ValueError, "render:"):
                s3d.render(room, **{**good, **kw})
        with self.assertRaisesRegex(TypeError, "render:"):
            s3d.render("room", **good)
        self.assertEqual(os.listdir(folder), [])                               # a refused picture writes nothing
        self.assertEqual((len(bpy.data.cameras), len(bpy.data.worlds)), (0, 0))

    def test_fresh_processes(self):
        first = run_cases('lit_picture', seed='11')['digests']['lit_picture']
        second = run_cases('lit_picture', seed='37')['digests']['lit_picture']
        self.assertFalse(first.startswith('error'), first)
        self.assertEqual(first, second)


if __name__ == '__main__':
    unittest.main()
