"""Explicit poles and longitudinal colour bands."""
import unittest
import bmesh
import sand3d as s3d


def valid(test, ob):
    bm = bmesh.new(); bm.from_mesh(ob.data)
    test.assertTrue(all(e.is_manifold and e.is_contiguous for e in bm.edges))
    test.assertTrue(all(f.calc_area() > 1e-8 for f in bm.faces))
    test.assertGreater(bm.calc_volume(signed=True), 0)
    bm.free()


class Tips(unittest.TestCase):
    def setUp(self):
        s3d.empty_scene()

    def tearDown(self):
        s3d.empty_scene()

    def test_sharp_loft(self):
        for count in (10, 'auto'):
            s3d.facets(count)
            ob = s3d.loft('horn', s3d.station(0, 40, 40), s3d.station(100, 0, 0), tip='sharp')
            valid(self, ob)
            self.assertEqual({v.co.z for v in ob.data.vertices}, {0, 100})
            if count == 10:
                ob.data.calc_loop_triangles()
                self.assertEqual(len(ob.data.loop_triangles), 18)
            s3d.empty_scene()

    def test_strand(self):
        s3d.facets(10)
        ob = s3d.sweep('strand', s3d.ellipse(74, 35),
                       s3d.spline([(0,0,1482),(0,58.5,1277),(0,0,897)]),
                       scale=[(0,1),(.5,1),(1,0)], tip='sharp')
        valid(self, ob)
        ob.data.calc_loop_triangles()
        self.assertLess(len(ob.data.loop_triangles), 80)

    def test_rings_on_surface(self):
        s3d.facets(8)
        for make in (lambda: s3d.loft('bands', s3d.station(0,20,20), s3d.station(100,20,20), rings=3),
                     lambda: s3d.wire('bands', [(0,0,0),(0,0,100)], 20, rings=3),
                     lambda: s3d.sweep('bands', s3d.circle(20), [(0,0,0),(0,0,100)], rings=3)):
            ob = make()
            self.assertEqual({v.co.z for v in ob.data.vertices}, {0,25,50,75,100})
            self.assertTrue(all(abs(v.co.xy.length-10)<1e-5 for v in ob.data.vertices))
            valid(self, ob)

    def test_options_and_both_ends(self):
        s3d.facets(8)
        for tip in ('sharp', 'flat', ('sharp','round'), ('round','sharp')):
            ob = s3d.wire('tips', [(0,0,0),(0,0,100)], [(0,0),(.5,20),(1,0)], tip=tip)
            valid(self, ob)
        for option in (-1, 1.5, True):
            with self.assertRaisesRegex(ValueError, 'rings'):
                s3d.wire('bad', [(0,0,0),(0,0,100)], 10, rings=option)
        for option in ('bad', (), ('sharp','bad')):
            with self.assertRaisesRegex(ValueError, 'tip:'):
                s3d.loft('bad', s3d.station(0,10,10), s3d.station(20,0,0), tip=option)



    def test_thick_bends(self):
        for n in (8,10):
            s3d.facets(n)
            for ob in (s3d.wire('corner', [(200,-740,1670),(400,-740,1220),(720,-1310,2420)],
                               [(0,233),(.08,244),(.18,261),(.35,283),(.65,326),(.7,333),(1,216)]),
                       s3d.wire('claw', s3d.spline([(0,-45.56,0),(107.25,-70.2,0),(214.5,-70.2,-48.75),(234,-70.2,-156)]),
                               [(0,54.6),(.5,37.05),(1,0)])):
                valid(self, ob)
            s3d.empty_scene()


    def test_closed_path_extra_rings(self):
        s3d.facets(8)
        ob = s3d.wire('loop', [(0,0,0),(100,0,0),(100,100,0),(0,100,0)], 10, closed=True, rings=2)
        self.assertEqual(len(ob.data.vertices), 8*4*3)
        valid(self,ob)

    def test_sweep_twist_law_sampling(self):
        s3d.facets(10)
        ob = s3d.sweep('turn',s3d.ellipse(20,10),[(0,0,0),(0,0,200)],twist=[(0,0),(1,360)])
        self.assertGreaterEqual(len(ob.data.vertices),110)
        valid(self,ob)

    def test_auto_sharp_sweep_has_no_cap_rings(self):
        ob=s3d.sweep('cone',s3d.circle(20),[(0,0,0),(0,0,100)],scale=[(0,1),(1,0)],tip='sharp')
        self.assertEqual({v.co.z for v in ob.data.vertices},{0,100})
        valid(self,ob)

    def test_extra_ring_count_when_samples_coincide(self):
        for mode in ('auto',10):
            s3d.facets(mode)
            for follow in (False,True):
                def make(extra):
                    return s3d.loft('bands',s3d.station(0,20,20),s3d.station(100,30,30),
                                    s3d.station(200,20,20),follow=follow,rings=extra)
                base=make(0); refined=make(3)
                n=sum(abs(v.co.z)<1e-5 for v in base.data.vertices)
                self.assertEqual(len(refined.data.vertices)-len(base.data.vertices),6*n)
                valid(self,refined)
            s3d.empty_scene()

    def test_offset_sharp_sweep_rings_stay_on_cone(self):
        s3d.facets(8)
        profile=s3d.at(s3d.circle(20),x=20)
        ob=s3d.sweep('cone',profile,[(0,0,0),(0,0,100)],scale=[(0,1),(1,0)],tip='sharp',rings=3)
        for v in ob.data.vertices:
            t=1-v.co.z/100
            self.assertAlmostEqual(((v.co.x-20*t)**2+v.co.y**2)**.5,10*t,places=4)
        valid(self,ob)


    def test_folded_centre_line_is_still_refused(self):
        s3d.facets(8)
        with self.assertRaisesRegex(ValueError, 'consecutive diameter rings cross'):
            s3d.wire('fold',[(0,0,0),(0,0,20),(0,0,0)],[(0,50),(1,50)],rings=1)
        path = s3d.spline([(0,-798*1.3,1197),(0,-1302*1.3,1386),
                           (0,-1218*1.3,1722),(0,-1092*1.3,2016)])
        with self.assertRaisesRegex(ValueError, 'consecutive diameter rings cross'):
            s3d.wire('fold',path,[(0,504),(.5,273),(1,336)],rings=1)

    def test_uneven_tilted_limb_is_bounded(self):
        from mathutils import Vector
        from sand3d.solids import _through, _loft_through
        s3d.facets(8)
        stations = [s3d.station(0,100,100),s3d.station(400,100,100,x=160),
                    s3d.at(s3d.station(430,100,100,x=160),rx=40),s3d.station(900,80,80)]
        origins = [r.matrix.translation for r in stations]
        params = [0.]
        for a,b in zip(origins,origins[1:]):
            params.append(params[-1]+(b-a).length)
        values = [r.matrix@Vector((0,50,0)) for r in stations]
        ts = [params[-1]*i/1000 for i in range(1001)]
        self.assertGreater(max(p.y for p in _through(values,params,ts)),80)
        self.assertLessEqual(max(p.y for p in _loft_through(values,params,ts)),50.0001)
        ob=s3d.loft('limb',*stations)
        self.assertLessEqual(max(v.co.y for v in ob.data.vertices),50.001)


    def test_spline_inserted_ring_centres_follow_cubic(self):
        from mathutils import Vector
        s3d.facets(8)
        for sweep in (False,True):
            path=s3d.spline([(0,0,0),(100,0,100),(-30,0,200),(0,0,300)])
            ob=(s3d.sweep('curve',s3d.circle(2),path,rings=2) if sweep else
                s3d.wire('curve',path,[(0,2),(1,2)],rings=2))
            coords=[v.co for v in ob.data.vertices]
            curve=[path._curve_at_length(path._curve_lengths[-1]*i/4000)[0] for i in range(4001)]
            # Each group of eight vertices is a construction ring.
            for i in range(0,len(coords),8):
                centre=sum(coords[i:i+8],Vector())/8
                self.assertLess(min((q-centre).length for q in curve),.15)
