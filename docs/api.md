# sand3d

`import sand3d as s3d`; mm, or `units("m")` first. Makers take a name, return the solid; edits return
it. Edges and faces go by their maker's names (top bottom side rim seam start end cut, tool names,
plate.top).

1. A placement is a frame plus values. `at` sets the values it is given and keeps the others; `on=`
   changes the frame, and x, y, z then run along its axes; `transform` moves the whole thing, as a parent
   would, mirror included.
2. To repeat, pass a list of frames to `on=`: once per frame, in `at`, `hole` and `pocket`.
3. A list of objects is worth its elements, wherever a verb takes objects.
4. What a verb uses up no longer exists. `copy` keeps it; always use what `at` returns.
5. Every solid starts at z = 0, centred in x and y: `box` is the `extrude` of its `rect`; `extrude(both=True)`
   centres one on its plane. A face's frame starts where the origin projects onto it: a vertical face's, at
   its foot. A frame's Z is the face's normal; on a face whose normal is ±Z its X is +X, on any other
   X is Z × normal: on a face looking +X, X is +Y and Y is up. A side, an edge or a corner of a box is
   named by directions: `bbox(ob, "+X")` is the centre of that side of its bounding box, `"+X-Y"` the
   middle of an edge, `"+X-Y+Z"` a corner, with the axes of a face looking the first way named, on a part
   or a group; `at`'s `anchor` takes the same ("-Z", "+Y-Z"; its words top bottom left right front back
   are +Z -Z -X +X -Y +Y).
6. A joint lets a part move on another. Place the part first: `joint` does not move it, it says how it
   moves — on the part its frame `on` was read on (`ob.face`, `bbox`, `local`, an assembly's anchor; it
   stays read on it through `.move`, `.turn`, `.offset`), about or along `axis`: a direction ("+Z", "-X"…)
   in the space the parent lives in, as in `face`, or "normal", `on`'s Z. A pivot given as numbers — a
   source's joint origin, xyz and rpy — is `local(parent, x, y, z, rx, ry, rz)`, in the parent's own space:
   `at(child, on=…)` places the child there, `joint` hangs it there. Positive values slide along the axis,
   or turn by the right hand about it: about +Z, +X turns toward +Y — a door hinged on the -Y edge of a +X
   face opens outward about "-Z". The range contains 0; a joint that follows another takes its range from
   it. Everything is built at rest, every joint at 0; `pose(child, value)` moves the mechanism. A part with
   no joint moves with its group; a jointed part moves by its joint, whatever group it is in; `on` is never
   read on the child itself. Joints may come before or after `group`/`assembly`. `copy` copies a jointed
   part's joints (it hangs on the same parent); `transform` moves the part with its pivot (a mirror image
   moves as the image of the motion); `at` refuses it. Two joints on one child compose in order (a screw: a
   turn, and a slide that follows it with `ratio=pitch / 360`).

## Profiles and outlines

```python
# profiles
rect(w, d, r=0, chamfer=0)  # Centred; corners rounded or cut
circle(d)  # Centred
ellipse(w, d)  # Centred
slot(l, d)  # Round-ended slot along X
polygon(n, d)  # Regular polygon, corner on +X
poly(pts, fillet=0, chamfer=0)  # Outline through points, arcs, splines
arc(center=(0, 0), r=1, start=0, end=360, *, through=None, to=None)  # Arc from start to end, anticlockwise if end > start: a path, or a poly run
tangent_arc(to)  # Poly run: arc leaving tangent
spline(pts, closed=False, tangents=None, loop=False)  # Smooth curve; closed: a profile; loop: a ring path
superellipse(w, d, n=2, taper=0)  # Ellipse (n=2) to box (n=4); taper narrows its +Y side, an egg
station(z, w, d, x=0, y=0, n=2, taper=0)  # Loft section at height z; n and taper as superellipse
text(s, size, font=None)  # Centred outline
offset(p, t)  # Grown by t
stroke(path, t)  # A band t wide along an open path, centred on it: a closed outline
wrap(*profiles)  # Convex outline round profiles
mirror(p, flip='x')  # Plus its image, flip negated
```

## Solids and paths

```python
# solids, paths
fill(name, container, level, clearance=None)  # Bounded voids below a height or Frame; None: -0.04 mm overlap; 0: exact contact
```

## Implicit surfaces

```python
field(name, size, density, *, cell, level=0, min_component_cells=3)  # Closed isosurface: density(x,y,z) < level; size=(w,d,h), local coordinates, centred XY, Z=0..h; faces field
```

## Scalar fields

```python
waves(wavelength, direction=None, centers=None, sharpness=0, spread=0, decay=None, phase=0, seed=0)  # Factory: bounded scalar/array f(x,y,z), local XY; lengths in program units, angles in degrees
noise(x, y, z, seed=0, kind="perlin")  # Dimensionless scalar or broadcast arrays [-1,1]; perlin cells ridged turbulence; independent of displace
```

## Constructed solids

```python
hull(name, points)  # Closed convex hull where points are given, no recentering; (x, y, z) or Frame origins; at least 4 distinct non-coplanar points, finite coordinates; unnamed planar faces (read by direction), edges rim
extrude(name, profile, h=None, taper=0, twist=0, both=False, h2=None, on=None, until=None)  # Prism up Z (taper > 0 narrows it upward), or until a plane or solid; on a face, by on
revolve(name, profile, angle=360)  # X radius, Y height, turned about Z
sweep(name, profile, path, scale=1, twist=0, frenet=False, *, tip="round", rings=0)  # Profile along a path; scale: end ratio or positive (sx, sy), linearly from one; scale and twist also take laws
loft(name, *sections, follow=False, loop=False, tip="round", rings=0)  # Through placed sections, capped; loop: a ring
body(name, plan, top, bottom, n=2)  # Solid along Y from its views, where they draw it: plan (y, width), side top and bottom (y, z) or numbers; superellipse sections
wire(name, path, d, closed=None, fillet=0, *, tip="round", rings=0)  # d also takes a diameter law, zero ends rounded; path: (x, y, z) points, a spline, an arc, a helix; fillet rounds the corners of points, d / 2 at least
```

## Analytic paths

```python
helix(d, pitch, h, left=False)  # Coil path up Z
spiral(d, d2, turns, h=0, left=False)  # Open path about Z, diameter changes geometrically, height linearly
```

## Solid primitives

```python
box(name, w, d, h)  # On Z = 0, centred in X and Y
cylinder(name, d, h)  # Along Z, from Z = 0
tube(name, d, d_in, h)  # Along Z, from Z = 0
cone(name, d, h, d2=0)  # Along Z, from Z = 0
sphere(name, d)  # On Z = 0
wedge(name, w, d, h, top=0)  # Box narrowed on top
torus(name, d, d_wire)  # Ring about Z, on Z = 0
dome(name, d, h)  # Cap on Z = 0
```

## Boolean and mesh edits

```python
# edits
cut(ob, *tools)  # Subtract tools
join(ob, *others)  # Fuse others in; ob's material wins: group keeps each its own
intersect(ob, tool)  # Keep the common part
split(ob, frame, keep='above')  # By a frame's plane
delete(ob)  # Remove it
copy(ob)  # An independent copy, its joints with it; a list, the list of copies
hole(ob, d, on=(0, 0), depth=None, cbore=None, csk=None)  # On frames or points: through, or depth deep
pocket(ob, profile, depth=None, on=None)  # Profile cut in from a face
merge(*obs)  # No boolean
scale(ob, s)  # About its origin; a group or an assembly whole, by one factor s > 0 — frames and anchors read before stay where they were
fillet(ob, r, edges='all')  # Round named edges
chamfer(ob, d, edges='all', d2=None, angle=None)  # Bevel named edges
soften(ob, r, angle=30)  # Round all sharp edges
shell(ob, t, open=None)  # Hollow; open named faces, or the flat faces looking "+Y", "-X +X"
```

## Surface and form deformation

```python
dent(ob, points, r, depth, *, coords="local")  # Press hollows at points in the mesh's local space; parent: the space the part is in
blend(ob, *others, r)  # Fuse others in, creases filled to about radius r on voxels of r / 5; its faces are all blend
displace(ob, amount, size, noise='perlin', octaves=1, seed=0, direction='normal', fade=None, *, faces=None, coords='local', refine=True)  # Push the surface out and in by up to amount, features size across: noise callable or perlin cells ridged turbulence; direction normal, radial or "+Z"…; fade=(z0, z1) along its own Z
bend(ob, angle, axis="+Y", toward="+Z")  # Curl along its own axis toward a perpendicular direction; degrees, groups bend together
twist(ob, angle, axis="+Y")  # Turn sections about its own axis, right handed; near end fixed, far end turned angle degrees
taper(ob, s, axis="+Y")  # Scale across its own axis, from 1 at the near end to ratio s > 0 at the far end
smooth(ob, angle=55)  # Shade each descendant mesh by angle; 0 flat, 180 all smooth
lay(ob, over, refine=0, reach=None)  # Seat on a surface along own Z, retaining height above own Z=0
```

## Frames and placement

```python
# frames, placement
Frame(origin=(0, 0, 0), normal=(0, 0, 1), up=None)  # A place to build on
.offset(d) .turn(rx=0, ry=0, rz=0) .move(x=0, y=0, z=0) .point(x=0, y=0, z=0)
Frames(frames)  # A list of frames that moves, turns, offsets and jitters as one; what distributors return
ob.face(which)  # Frame of a named face, or furthest along "+Z"
ob.edge(which)  # Path along the edges named which, in the space ob is in: the longest run (as long: the one reaching furthest -X, then -Y, -Z), closed if it closes
bbox(ob, which)  # Frame on its bounding box: a side "+X", an edge "+X-Y", a corner "+X-Y+Z"
local(ob, x=0, y=0, z=0, rx=0, ry=0, rz=0)  # Frame at (x, y, z) of its own space, turned (rx, ry, rz) degrees
at(ob, x=None, y=None, z=None, rx=None, ry=None, rz=None, on=None, anchor=None)  # Place it: set what is given, keep the rest; anchor: "-Z", "+Y-Z"…
transform(ob, x=0, y=0, z=0, rx=0, ry=0, rz=0, mirror=None)  # Move it by, as a parent would; its placement, not its mesh
```

## Distributions

```python
grid(nx, ny=1, px=0, py=0, stagger=False, on=None)  # On a grid
ring(n, r, start=0, angle=360, on=None)  # On a circle
along(path, pitch=None, count=None, spin=0, span=(0, 1))  # Along a path
phyllotaxis(n, d, h=0, angle=137.508, on=None)  # Frames on a disc, or facing out from a cylinder when h > 0
branches(length, d, levels=3, children=3, attach=(0.45, 0.9), angle=45, azimuth=137.508, length_ratio=0.55, diameter_ratio=0.55, tip_ratio=0.15, jitter=0, seed=0, on=None, wander=0, droop=0)  # Depth-first axes and leaf-tip frames, straight or smoothly curved
Frames.jitter(rx=0, ry=0, rz=0, x=0, y=0, z=0, seed=0)  # Random turns and moves along own axes, bounded and bell-shaped
vary(value, spread, n, seed=0)  # Values within spread of value, most near it
scatter(n, size, seed=0, surface=False, on=None)  # size: ellipsoid diameters, or a mesh part / list of mesh parts for its surface
snap(targets, points, direction=None)  # On a surface: nearest, or along direction "-Z", "+X"… or (x, y, z)
```

## Mechanical parts

```python
# parts
gear(name, teeth, module, width, bore=0, angle=20)  # Involute spur gear
knurl(name, d, h, pitch=None, straight=False)  # Knurled grip; pitch 1 mm by default
thread(name, d, length, pitch, left=False)  # Threaded rod
```

## Materials

```python
# materials
material(ob, kind, color=None, roughness=None, metallic=None, opacity=None, emission=None, absorb=None, absorb_distance=None, thickness="auto", ior=None, transmission=None, scatter=None, scatter_distance=None, scatter_anisotropy=None)  # Kind: oak walnut pine birch steel brushed_steel chrome aluminium brass copper painted_metal plastic glossy_plastic rubber glass ceramic fabric velvet leather marble concrete bark leaf moss grass rock soil sand water snow foam smoke fog light; color "#rrggbb" or color(x,y,z[,n[,u]])
```

## Articulation

```python
# articulation
joint(name, child, on, kind='revolute', axis='normal', range=None, follows=None, ratio=1)  # How child moves on the part on was read on: revolute (range in degrees), continuous (no range), prismatic (range in the unit), free (no axis, no range); follows: a child or a joint name, and this joint's value is ratio × its (degrees per unit, or units per degree), no range; returns child
pose(ob, value, joint=None)  # Move the mechanism: that joint to value (degrees or the unit), an error outside its range; what it carries follows; joint= when child has two
seat(host, part)  # Take out of host the volume part fills, as it sits at rest; part untouched
```

## Assembly

```python
# assembly
group(name, *children)  # Parent of children
assembly(name, *children, **anchors)  # Parts and anchors
attach(handle, name, *children)  # A detail, under a handle
Handle(root, **anchors)  # Root and anchors
```

## Export and scene settings

```python
export(root, path, colors="material")  # root and what hangs on it by its joints, in metres: .glb at the current pose, joints in extras; .urdf a link per moving part, at rest, meshes beside it; .usda the URDF's tree as OpenUSD text, with the materials; .ifc the part tree as IFC4 at the current pose, no joints; GlobalIds can change with geometry or placement and may repeat across models; .obj and .stl its meshes at the current pose
empty_scene()  # Fresh scene
facets(n=None, smooth=...)  # Read count, or set segments per turn (integer >=3 or "auto") at any point; with facets(n): one part, then the previous count
units(name=None)  # Length unit: "mm" (default), "cm", "m"
fingerprint()  # Digest of the source
```


## Materials and media

`material` overrides inherit their preset when None. `absorb` is an sRGB colour
(`#rrggbb` or RGB tuple), independent of the surface `color`: white light becomes
its linear RGB value after travelling `absorb_distance` in program units.
Transmittance at distance x is `linear(absorb) ** (x / absorb_distance)`.
Distance 0 disables absorption. `ior` is finite in 1..1000; `transmission` in 0..1
controls the transmitted fraction, independently of alpha (`opacity`).
`absorb_distance` must be finite and nonnegative; `thickness` is "auto" or such a length.

`scatter` is the sRGB colour a medium sends light back in, `scatter_distance` (program
units, finite, 0 or more) how far white light travels on average before it scatters:
channel c scatters `linear(scatter)[c] / scatter_distance` per unit. Distance 0 disables
scattering. `scatter_anisotropy` in -1..1 is the Henyey-Greenstein g: 0 scatters every
way alike, > 0 forwards (a bright glow with the light behind), < 0 backwards. Absorption
and scattering add up: extinction is their sum. A light smoke mostly scatters, a black
smoke only absorbs (`absorb`), murky water is `water` with `scatter` added.

The medium fills the closed mesh; the surface stays what its own values say and hides
the medium when opaque. A medium with no visible boundary needs `transmission=1`,
`ior=1`, `roughness=0`, as `smoke` and `fog` set. Cycles stops shadow rays at any
refracting surface, IOR 1 included, so such a clear boundary around a medium (no
metallic, coat, sheen or emission either) reaches Cycles as a transparent surface tinted
by `color`: the medium gets direct light and casts its own shadow. GLB and EEVEE keep
the Principled BSDF. Each crossing of that boundary is one of Cycles' transparent
bounces (`scene.cycles.transparent_max_bounces`, 8 by default): a folded envelope, a
noisy `field`, can take a grazing ray past them and show black cracks along its outline;
raise the limit. One closed envelope with a constant medium gives a soft mass, not
filaments: the density is the same everywhere inside. Cycles renders single scattering
unless the scene allows volume bounces (`scene.cycles.volume_bounces`, 0 by default);
sand3d leaves render settings alone.

| preset | surface colour | roughness | transmission | IOR | absorb at distance | scatter at distance, anisotropy |
|---|---|---|---|---|---|---|
| `water` | `#f4f8f8` | 0.08 | 1 | 1.333 | `#b8e8ed` at 1 m | none |
| `glass` | `#ffffff` | 0 | 1 | 1.5 | none | none |
| `smoke` | `#ffffff` | 0 | 1 | 1 | `#d6d6d6` at 1 m | `#ffffff` at 625 mm, 0.3 |
| `fog` | `#ffffff` | 0 | 1 | 1 | none | `#ffffff` at 10 m, 0.3 |

Fog, mist, steam and cloud are `fog` with a shorter `scatter_distance` where the medium
is thicker.

Water is a volume bounded by a **closed mesh**, not a single surface: model its
bottom and sides as well as its top, with outward normals. Cycles uses actual ray
length for absorption. `thickness` is the constant depth glTF raster viewers
assume, since they cannot follow rays through the mesh. `"auto"`, the default,
estimates it at export from the meshes that wear the material: 2 × volume / area,
the thickness of a slab (D/3 for a sphere of diameter D), one value per material;
a length sets it. It creates no geometry, and a varying-depth pool still shows one
depth in those viewers (no thickness map is generated). Zero thickness disables
absorption and omits the glTF volume extension; Cycles surface refraction still follows the mesh.
A black absorb channel is approximated as 1e-6 in Cycles to keep density finite.

GLB carries `KHR_materials_volume`, `KHR_materials_ior` and transmission; absorption
requires a viewer supporting these extensions. Export converts distance to world
metres and leaves thickness in mesh units, scaled by the exported node. **glTF has no
ratified scattering** (`KHR_materials_volume_scatter` is a draft): a scattering medium
exports its total extinction, absorption plus scattering, as `KHR_materials_volume`
attenuation over the distance that dims its densest channel to 1/e. It keeps its place
and its transmission, but the light it would scatter is lost: a GLB viewer, and Blender after
reimport, show smoke or fog as a dark medium. No other extension is written. Cycles
and glTF use different absorption socket conventions; export temporarily converts
them and restores the Cycles material. USD Preview Surface carries IOR and coat,
approximates transmission by `opacity * (1 - transmission)` and carries no volume
absorption, scattering, thickness or sheen. Fully transmitting water, glass, smoke
or fog can thus be invisible in USD. IFC carries surface colour and transparency `max(1-opacity, .85*transmission)`
with GLASS reflectance; no IOR, volume absorption or scattering. OBJ carries vertex colour; URDF carries surface colour
and opacity only; STL has no materials.

Natural presets have average untextured colours: `bark` (outer wood), `leaf`
(waxy foliage), `moss`, `grass`, `rock`, `soil`, `sand`, `water`, `snow`, `foam` (white diffuse sea foam or suds, roughness 0.95,
no transmission or volume absorption).
All are nonmetallic with alpha 1; leaf has coat 0.12 and snow 0.03.
`color=` changes the surface tint without changing absorption or other properties.
Material names contain the preset and explicit overrides, not its default values.

## Scale and local frames

`scale` on a group or an assembly (its handle) takes one factor s > 0 — no (sx, sy, sz), no 0, no
negative — and scales everything under it in place about the group's own origin: each mesh's
coordinates and each part's place in its parent are multiplied by s; the group stays where it is in its
parent, turns, materials, `smooth`, vertex and face counts are kept, and no scale is left on any object.
A later `at` on a part keeps its scaled place; new lengths given to it are in program units. **Frames,
`Frames` and a handle's anchors read before the call do not follow**, and number anchors stay as they
were: read `bbox`, faces and `local` again, or rebuild the anchors from scaled parameters, after scaling.
Refused for now: a group holding a jointed part, carried by one, or that a joint outside hangs on or
follows — scale before declaring joints, or build at size. A solid keeps its own `scale`, per axis
included; its children do not move.

Laws are lists of `(u, value)` pairs, strictly increasing from 0 to 1, measured by path
length. Values interpolate with shape-preserving monotone cubics; sweep scale also accepts
`(sx, sy)` values. A plain positive `(sx, sy)` end scale interpolates linearly from `(1, 1)`.
Numeric sweep scale and twist retain their linear start-to-end meaning.
Laws on closed paths are refused. Size laws refuse interior zeros, partially zero pairs and
all-zero laws; a pole requires one outline without holes. On a zero-ended interval, a monotone
square-root cap replaces PCHIP, matching its value and slope at the neighbouring knot.
An offset profile's centre follows the unrounded scale while its outline rounds.
Law sampling merges stations closer than max(0.0001 mm, path length × 1e-7,
coordinate magnitude × 2⁻²⁰) before building rings, avoiding spurious reversals
from float32 roundoff. Section sizes are
never silently reduced. A crossing-ring error gives the path fraction, a section-radius limit
in the program's unit, and a uniform size factor that can be applied to the profile or every diameter.

A zero-size first or last loft section supplies only the pole's position; its rotation is
ignored. The neighbouring full section sets the pole's tangent plane, after `follow` turns it.
The cap joins the continuing body with a matching tangent. With poles, centres and transported
section offsets use shape-preserving cubics between the original stations. The rounded cap is
confined to the end interval; its slope does not make the body overshoot neighbouring sections.

Branch levels count generations after the root (level 0); `.parent` is the parent axis, or
`None` for the root. `.tips` holds leaf axes only. A child's diameter is relative to its parent's
base diameter, not the diameter at attachment; azimuth restarts at each parent. `.path` and
`.tips` are already in the frame carrying `on`: build `wire(axis.name, axis.path, axis.d)` without
applying `on` again. At most 4096 axes and 128 generations are allowed.
`wander` bounds random heading turns per segment in degrees; `droop` turns toward `on`'s
-Z by up to that many degrees over each axis (negative rises). Eight segments are spline-smoothed
into a `Path`; children attach by its arc length, facing its tangent. With both zero, paths
remain exact straight two-point segments. Curvature radii exceed twice the local section
radius, so axes build with `wire` or a matching `sweep` scale law. `jitter` also perturbs
child azimuth by up to its fraction of `azimuth`, as well as lean and length.

## Along and surface distributions

`along` covers `span` of the path's arc length. `spin` adds degrees per frame about its tangent.
Nonzero spin uses rotation-minimizing parallel transport through every path segment, starting
with the usual frame X. Zero spin keeps the historical world-Z reference; transport around
a closed curve may leave a roll difference at the seam. Count excludes the repeated endpoint
only for a full closed span; pitch starts at the span's start.

`Frames.jitter` uses independent triangular draws on [-amplitude, amplitude], mode zero;
turns are in degrees and moves in program units along the original axes. It preserves part
memory. `vary` returns floats `value + draw`, with triangular draws in [-spread, spread]:
spread is in the value's own unit, like jitter's amplitudes, so a value of zero varies too. All use local seeded generators.
`scatter` accepts 0–4096 frames and three positive ellipsoid diameters. Best-of-16 Mitchell
sampling favours physical separation; candidates are uniform in volume or surface area.
Normals point radially outward (not the ellipsoid's differential surface normal). `on` sets
centre and axes. Give a mesh part instead of diameters, e.g. `scatter(420, fruit, seed=1)`, to sample
its surface directly: triangle candidates are weighted by placed area, normals face out,
and the same best-of-16 choice measures spacing in 3D. A list of mesh parts samples their
combined area. Parts must be closed manifold meshes in the same parent space; frames are
in that space, like `snap`. `surface` is implicit and `on` is refused. Overlapping parts
retain their interior surfaces: `join` first for a union. Groups are not mesh parts.

```python
def bracket(w=80, d=40, t=6, hole_d=6.6, pitch=50):
    plate = s3d.extrude("plate", s3d.rect(w, d, r=4), t)
    s3d.hole(plate, hole_d, on=s3d.grid(2, 1, pitch, 0))
    s3d.fillet(plate, 1, edges="top")
    return plate

def lamp(stem_h=300):
    base = s3d.revolve("base", [(0, 0), (70, 0), (60, 20), (0, 20)])
    stem = s3d.at(s3d.cylinder("stem", 12, stem_h), on=base.face("top"))
    lamp = s3d.assembly("lamp", base, stem, head=s3d.Frame((0, 0, 20 + stem_h)))
    add_shade(lamp)
    return lamp

def add_shade(lamp, d=180):
    shade = s3d.shell(s3d.cone("shade", d, 120, d2=d / 2), 1.5, open="top bottom")
    s3d.attach(lamp, "shade", s3d.at(shade, on=lamp.head))

def rack(n=4, pitch=30, depth=40, t=5):
    base = s3d.extrude("base", s3d.rect(n * pitch, depth, r=3), t)
    pegs = s3d.at(s3d.cylinder("peg", 6, 20), on=s3d.grid(n, 1, pitch), z=t)         # a copy per frame
    hook = s3d.at(s3d.extrude("hook", s3d.rect(4, 12), 12), x=n * pitch / 2 - 4, z=t)
    image = s3d.transform(s3d.copy(hook), mirror="x")                                # its image across x = 0
    s3d.join(base, pegs, hook, image)                                                # a list is its elements
    s3d.hole(base, 4, on=s3d.grid(2, 1, (n - 1) * pitch).move(y=depth / 2 - 6))
    s3d.chamfer(base, 0.6, edges="peg")
    return base

def gate(w=750, h=1200, post=100):
    l_post = s3d.at(s3d.box("post", post, post, h + 300), x=-w - post / 2)
    r_post = s3d.transform(s3d.copy(l_post), mirror="x")
    board = s3d.at(s3d.box("board", w, 40, h), x=-w / 2, z=150)                    # from the post to x = 0
    handle = s3d.at(s3d.cylinder("handle", 20, 60), on=s3d.bbox(board, "+Y").move(x=60 - w / 2))  # near x = 0
    leaf = s3d.group("leaf", board, handle)                                        # the handle moves with it
    s3d.joint("hinge", leaf, s3d.bbox(l_post, "+X+Y"), axis="+Z", range=(0, 90))   # the post's edge it opens toward: +X turns toward +Y
    twin = s3d.transform(s3d.copy(leaf), mirror="x")                               # its image, hinged at x = +w: opens toward +Y too
    gate = s3d.assembly("gate", l_post, r_post, leaf, twin)
    s3d.pose(leaf, 60)
    return gate
```

## Implicit fields

`field` samples each axis at evenly spaced intervals no larger than `cell` (at least two).
Boundary samples are forced outside: leave a margin of `cell` to preserve the surface;
otherwise it closes within the outermost cell. The density must be a deterministic callable
returning finite values; coordinates, size and cell use the program unit, density and level
use the same arbitrary scalar unit. Features below cell can disappear. Marching tetrahedra
shares vertices and preserves cavity orientation. Disconnected closed shells are allowed.
Up to one million lattice points, all cells are sampled. Larger grids probe corners and
centres of four-cell blocks, retaining blocks that straddle the level or whose distance
in density is within twice the local variation. The band then follows every mixed-sign
fine block face into its neighbour until its boundary has uniform-sign faces.
Extraction uses the same fine lattice
throughout: no coarse/fine seams. This is a heuristic, not a bound for arbitrary callbacks;
a whole component hidden between all initial probes may be missed. Choose cell
small enough to resolve the features, including at the coarse scale (four cells),
and no smaller: about half the thinnest wall, two thirds of the smallest relief.
Triangles and time grow as surface area / cell².
Crossings are refined by up to twelve bracketed zero-finding steps on shared edges,
reducing interpolation ripples for non-distance densities; clipped boundary edges keep
linear interpolation. Refinement preserves connectivity, but cannot recover missing sheets.
Budget: 1,000,000 coarse lattice probes, 8,000,000 fine-band samples and 4,000,000
output triangles. Fine samples are cached by slab; discovery evaluates block faces in
bounded batches. Triangle connectivity and unique edges use memory proportional to output. Coarse probes,
face completion and edge refinement add density calls beyond the fine-band budget. Non-finite samples,
empty and singular surfaces are refused. Increase cell to reduce cost.
Nonzero edge crossings stay at least 1e-5 of their edge from its endpoints,
increased where necessary to four float32 coordinate rounding units on each varying
axis, to avoid collapse far from the origin; exact-level vertices are welded.
A cell below mesh coordinate precision is refused. Directional face frames on a field
fall back to its furthest outward-facing triangle when no facet is parallel to the direction.

`field` density fast path: three same-shaped float64 numpy arrays in local program
units; return an ndarray of the same shape. A small trial failing with TypeError
or ValueError, or returning a non-array, selects scalar fallback. Deterministic,
pure callbacks only. Blocks, fine-face band completion, tetrahedra and shared-edge
root refinement use numpy. At most 1 M coarse probes, 8 M fine samples and 4 M
triangles; root evaluations and completion probes are additional. Coarse probes
can miss wholly hidden sub-cell features. Boundary samples are forced outside;
leave one cell of margin. Non-finite, empty and singular surfaces are refused.
`min_component_cells` drops closed components shorter than that many cells on
every axis; always keeps the largest. Set 0 to keep all components.

## Noise and waves

`noise` returns a float for scalar input, otherwise a float64 broadcast-shaped
array, in [-1,1]. Seeded gradient/nearest-cell noise is deterministic
across runs and platforms; independent of `displace`'s existing realization.
Coordinates must be finite with magnitude <= 2**50. Programs may import numpy.


`waves` returns a deterministic `f(x,y,z)` in [-1,1]: float for scalars,
float64 ndarray for broadcast arrays, independent of Z. Default direction is
"+X"; degrees turn counterclockwise from +X toward +Y. Signed XY axes are also
accepted. Direction is the phase-gradient direction; crests run perpendicular.
`wavelength` is positive, measured along that direction, in program units.
`phase` is in degrees (0 gives a crest at the origin); changing it shifts the
pattern. `sharpness` in [0,1] changes cos(t) to cos(t + sharpness*sin(t)):
narrower crests, broader flatter troughs, with unchanged period and bounds.
This is a height profile inspired by trochoids, not a fluid simulation; it can
have a negative mean. No horizontal motion, overturning or breaking waves.

`spread` in [0,90] degrees is the half-angle of four seeded components around
the primary direction, with wavelengths 0.85..1.15 times the requested length
and random phases. The primary carries half the weight, each satellite 1/8;
zero spread is one exact cosine and ignores seed. `centers=[(x,y), ...]` selects
circular waves instead, excluding direction and nonzero spread. Sources share
wavelength, sharpness and phase. Optional positive `decay` is an e-folding
length: each source is multiplied by its envelope exp(-distance/decay), and the
sum is divided by the summed envelopes where they exceed 1, so a ring far from
the others keeps its full height and overlaps stay in [-1,1]. Without decay the
sources are averaged. It requires centers.
Seed affects spread only. Inputs must be finite; distance / wavelength must
have magnitude <= 2**50. `waves` creates no mesh and stores no animation state.

Use `f = waves(3000, direction=25, sharpness=.8, spread=15, seed=7)` then
`displace(ob, 200, 500, noise=f, direction="+Z")`. Size controls refinement,
not wavelength: resolve the shortest component with at least 16 samples per
period, more for sharp crests. Use a fixed push direction for a height surface;
normal displacement on an already curved mesh does not guarantee no crossings.
For foam colouring, wrap the scalar field in an RGB colour function:
`material(ob, "plastic", color=lambda x,y,z: (1,1,1) if f(x,y,z) > .7 else (.02,.15,.2))`.
This colours crests; it does not model foam. Colour callbacks still run per face.

A shore belongs to composition, not radial decay: multiply `f(x,y,z)` by a
bounded mask such as `np.clip((x-shore)/width, 0, 1)` (positive width).
Multiply by `(.7 + .3*s3d.noise(x/500,y/500,z/500))` for bounded modulation;
use `np.clip(f(x,y,z)+.2*g(x,y,z), -1, 1)` for a bounded sum.
The same field describes sand ripples (`waves(80, direction=20, sharpness=.7)`),
dunes (`waves(8000, direction=15, spread=20, sharpness=.6, seed=3)`) and
corrugated sheet (`waves(75, direction="+X")`), each displaced along "+Z" with
an appropriate amplitude. These are surface heights, not thickness-preserving bends.


Callable displacement: `displace(ob, amount, size, noise=f, coords="local")`
calls a pure deterministic `f(x, y, z)` with three float64 numpy arrays in the
part's frame and program units. Return an ndarray of the same shape, finite
real values in [-1, 1]; invalid results raise. Values multiply amount and fade
directly, without the named noises' area centring. Size still controls surface
refinement (about size / 4); coordinates are not divided by size. Keep octaves=1
and seed=0; compose seeded `s3d.noise` calls inside f for layers and domain warps.

## Displacement

`faces=None` preserves whole-surface displacement. Use `faces="top"` or a list
of construction face names to displace only their vertices; names select all
facets carrying that label, including curved surfaces. A direction such as
`faces="+Z"` selects exactly the patch that `face(ob, "+Z")` reads (in the
parent's space, before refinement). Unknown names list the available labels.
Vertices shared with unselected faces stay fixed. Displacement multiplies fade
by a cubic smoothstep of distance to the selection boundary, reaching full
strength at distance `size`, with zero slope at either end. Distance is local
Euclidean distance to boundary segments, not distance along a folded surface.
Open patch edges are held too; a selection without a boundary has no attenuation.
Only selected faces are refined. Shared edges gain collinear vertices to keep
the mesh closed, but unselected faces are not triangulated. `refine=False`
keeps existing topology. A coarse patch with no interior vertices cannot move.
This holds a panel's rim, a relief's frame or a liquid's shore; it does not
preserve thickness or prevent intersections at large amplitudes.

With `coords="path"`, f receives construction (s, a, r): arc length in program
units, transported angle in degrees [-180,180], and construction radius. Constructors
write one POINT source: `.s3d_s`, `.s3d_x`, `.s3d_y`, `.s3d_extent`.
The angle uses the usual Frame X and rotation-minimising transport, independent of
section twist and Frenet roll; transverse x/y encode angle via atan2 and radius
via hypot, interpolating across the seam and across cap interiors. A deformed
part no longer has a unique recoverable axis, so these offsets are retained. These
are construction labels, not measurements of the edited mesh. No path projection.
Closed paths retain a seam in s. Named noise with path coordinates is refused.

Colour functions declare exactly 3, 4 or 5 positional parameters, no variadics or
keyword-only arguments: `color(x,y,z[,n[,u]])`, returning sRGB `"#rrggbb"` or an RGB
triple in [0,1]. They read local face centres in program units and outward unit
normal tuples, once per face in index order after the array probe below. Identical
instances can share these colours during one export. `u` is the face mean of vertex
s / extent: section progression for loft, arc-length progression for wire/sweep,
height from bottom to top for revolve/dome/sphere/cone/cylinder; caps take their
end value. Loft's normalization extent varies with section progression so s stays
an arc length even between uneven stations. Functions are pure, session-local,
not serialized in Blender files; copy keeps the function, join/merge the first one's.
A five-argument colour refuses missing or undefined coordinates.

Array colour functions receive float64 `x`, `y`, `z`, and `u` arrays of shape `(k,)`
for all faces of a part, and `n` of shape `(3, k)` (`n[2]` is always the z normal).
Return a numeric NumPy sRGB array of shape `(k, 3)`, finite and in [0,1]. Only this
orientation is accepted: rows are faces, even when k=3. Hex string arrays and
channel-first `(3, k)` arrays are not accepted; convert hex to RGB in the function.
For example, `lambda x,y,z: np.stack((x*0+.2, y*0+.4, z*0+.6), axis=-1)`.
A probe with up to eight faces selects array evaluation. If it raises or returns
the wrong shape, evaluation falls back to scalar calls; otherwise the function
is called once with all faces. Invalid array values raise an error. The probe is
one extra call on every evaluation, including scalar fallback: functions must
have no side effects or random state. A function supporting both forms must give
the same colours in both, using float64 arithmetic. Each export evaluates anew;
its face corners and area mean reuse those colours.

Placement, copy, merge, displace, bend, twist, taper, scale, lay and interpolating
mesh edits retain construction labels; refinement interpolates them. Join between
parameterized parts transfers labels on the operand surfaces, first operand at shared
intersections. Booleans with any unparameterized operand discard labels conservatively.
Merge fills missing labels with NaN instead of inventing u. Blend/voxel remeshing
and field reconstruction discard them. New topology with no source has no u.
Repeated path displacement reads the same construction labels. `refine=False`
changes existing vertices only, keeping vertex order, faces and attributes.

GLB always exports callable colours on face corners (COLOR_0). `colors="vertex"`
also puts plain colours on corners and shares white materials by surface look;
an emissive material retains its own colour (area-weighted mean for a function).
OBJ, URDF and USD use the area-weighted linear mean, STL has no colour.
`colors="vertex"` is accepted only for GLB. Export restores meshes and materials.

A fixed `facets(n, smooth=False)` controls turns across and along sweep, loft,
wire, body and spline paths; bend/twist cut sections by their total angle.
Straight spans keep only their stations. "auto" is
the default chord tolerance and usual shading. `smooth=True` retains smooth shading;
choose this flag at the first facets call. Fixed counts can change between makers.
`with facets(n):` restores the previous count even on error. `smooth(ob, angle=55)`
overrides shading for one mesh or its descendants and persists through edits/copies.

`tip` is "round", "sharp", "flat" or a (start,end) pair on loft/wire/sweep.
Round rounds zero ends; sharp interpolates the end span linearly; flat replaces a
zero end size by its neighbouring section size and caps it in the end plane.
Nonzero ends stay capped. `rings` adds that many rings per span; wire also accepts
explicit arc-length fractions strictly inside (0,1). `wire(d=(width,thickness))`
has a constant elliptical section; laws still describe circular diameters.

## Denting and laying

`dent` reads points and Frame origins in the mesh's local space by default, preserving
that convention after placement. With `coords="parent"`, it reads them in the space
the part is in, matching `snap` and `scatter(part)` frames. Radius and depth retain
their local program-unit meaning.

`lay` moves a placed piece along its own Z onto `over`, preserving every point's
height above its Z=0 plane. A group uses its root frame; a list seats each item.
`refine` splits edges to at most that length before seating (0 leaves topology);
`reach` bounds base-plane travel (None unbounded). Carrier tessellation uses local
frames. It refuses self-seating and leaves vertex positions intact on reach failure.


For axisless surfaces, fixed `facets(n)` means target edge length `L = π D / n`,
where D is the largest local bounding-box dimension (the requested box for field).
This is invariant under placement and scales with the part, like segments per turn.
`field` uses `max(cell, L)` for its cell limit, with at least two intervals per
axis; actual equally spaced intervals can be shorter after rounding. Boundary
closure and shared crossings are unchanged. Thin branches or cavities below this
resolution can disappear: use a larger n to retain them. `displace` refines toward
`max(size/4, L)`; it retains existing edges even when shorter. `hull` connects
explicit points without subdivision or simplification, so point count still controls
its complexity. `blend` retains its fine voxel closing and guards, then collapses
toward `4 area / (√3 L²)` triangles (at least four), retaining the original mesh if
collapse breaks manifoldness. This is an area resolution, not a strict edge bound.
All fixed-count results shade flat unless `smooth=True` or a part has an explicit
`smooth` override. `branches` and `along` create paths/frames, not surfaces;
wire/sweep consume those paths with the existing angular rule. Bend and twist
already refine by total angle. Auto sampling, refinement and shading are unchanged.

### Filling a container

`fill("soil", pot, 80)` makes a new solid in the voids retained below local
height 80, preserving the container. A part, group or assembly supplies its own
height frame; a list of parts requires a `Frame`, for example
`fill("river", channel, local(channel, z=12, ry=3))`. The frame's normal points
out of the fill; an unbound Frame is in world space. The result takes that
plane's axes and, like every solid, stands on its own Z=0: its origin is under
the level's origin at the depth of the deepest point, so its local Z runs from
the bottom up to the free surface. That surface is the face `top` (also its
boundary edges): `face(water, "top")` reads it, `at(water, ..., anchor="+Z")`
places by it; other faces are `side`. On a tilted level, local X and Y lie in
the surface, so a `waves` field or `displace(direction="+Z")` follows it. Multiple pockets share one object.
For waves on the surface alone, use
`displace(water, 2, 20, noise=waves(100), direction="+Z", faces="top")`:
the shore and submerged faces stay fixed.
Closed cavities are included, even without a free surface. Container parts must
be closed manifold solids; an open cup means an opening between solid walls,
not a mesh with missing faces.

[examples/pond.py](examples/pond.py) digs a basin, fills it and dresses the water:
`pond()` is still water, `pond(swell=15, wavelength=400)` a breeze on the surface
alone (`displace(..., faces="top")` keeps the shoreline on the banks).

`clearance=None` overlaps the walls by approximately 0.04 mm, converted to the
program's unit, to avoid coincident transmissive surfaces. Explicit clearance
is in program units: positive leaves a gap, negative overlaps, zero gives
exact boolean contact. Clearance offsets the retained boundary after finding
pockets and leaves the level plane fixed; it is a small rendering allowance,
not a robust large geometric offset. Large values can self-intersect or collapse
thin features. A level below the cavity floor, above an open rim or connected
to a leak retains nothing and raises `ValueError`; leaking pockets are discarded
if other pockets retain material. This is static geometry, without fluid flow,
meniscus, trapped-air modelling or automatic spill-level search. A tilted
channel needs closed ends below its chosen plane.
