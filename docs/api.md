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

A corner radius too large for its sides (`rect(r=)`, `poly(fillet=)`, `wire(fillet=)`) is
clamped to the largest that fits and warns with `sand3d.edit.ClampedRadius`;
`SAND3D_STRICT=1` or `with sand3d.edit.strict():` raises instead. A wire still raises when
a bend would be tighter than `d / 2`. A loft section whose outline crosses itself says where.

```python
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

## Solids

```python
extrude(name, profile, h=None, taper=0, twist=0, both=False, h2=None, on=None, until=None)  # Prism up Z (taper > 0 narrows it upward), or until a plane or solid; on a face, by on
revolve(name, profile, angle=360)  # X radius, Y height, turned about Z
sweep(name, profile, path, scale=1, twist=0, frenet=False, *, tip="round", rings=0)  # Profile along a path; scale: end ratio or positive (sx, sy), linearly from one; scale and twist also take laws
loft(name, *sections, follow=False, loop=False, tip="round", rings=0)  # Through placed sections, capped; loop: a ring
body(name, plan, top, bottom, n=2)  # Solid along Y from its views, where they draw it: plan (y, width), side top and bottom (y, z) or numbers; superellipse sections
wire(name, path, d, closed=None, fillet=0, *, tip="round", rings=0)  # d also takes a diameter law, zero ends rounded; path: (x, y, z) points, a spline, an arc, a helix; fillet rounds the corners of points, d / 2 at least
hull(name, points)  # Closed convex hull where points are given, no recentering; (x, y, z) or Frame origins; at least 4 distinct non-coplanar points, finite coordinates; unnamed planar faces (read by direction), edges rim
field(name, size, density, *, cell, level=0, min_component_cells=3)  # Closed isosurface: density(x,y,z) < level; size=(w,d,h), local coordinates, centred XY, Z=0..h; faces field
fill(name, container, level, clearance=None)  # Bounded voids below a height or Frame; None: -0.04 mm overlap; 0: exact contact
box(name, w, d, h)  # On Z = 0, centred in X and Y
cylinder(name, d, h)  # Along Z, from Z = 0
tube(name, d, d_in, h)  # Along Z, from Z = 0
cone(name, d, h, d2=0)  # Along Z, from Z = 0
sphere(name, d)  # On Z = 0
wedge(name, w, d, h, top=0)  # Box narrowed on top
torus(name, d, d_wire)  # Ring about Z, on Z = 0
dome(name, d, h)  # Cap on Z = 0
```

## Paths and scalar fields

```python
helix(d, pitch, h, left=False)  # Coil path up Z
spiral(d, d2, turns, h=0, left=False)  # Open path about Z, diameter changes geometrically, height linearly
waves(wavelength, direction=None, centers=None, sharpness=0, spread=0, decay=None, phase=0, seed=0)  # Factory: bounded scalar/array f(x,y,z), local XY; lengths in program units, angles in degrees
noise(x, y, z, seed=0, kind="perlin")  # Dimensionless scalar or broadcast arrays [-1,1]; perlin cells ridged turbulence; independent of displace
```

`poly` and `spline(points, closed=True)` are planar profiles. `wire` takes 3D points or a path:
`spline(points)` (open), `spline(points, loop=True)` (closed); build the spline and the wire inside
the same `facets(...)` context. More `rings` cannot repair a self-crossing: reduce the diameter or
soften the curvature. Sweep and loft caps are `start`/`end`, not `bottom`/`top`.

## Edits

```python
cut(ob, *tools)  # Subtract tools
join(ob, *others)  # Return fused ob, consume others; use the return value. ob's material wins
intersect(ob, tool)  # Keep the common part
split(ob, frame, keep='above')  # By a frame's plane
delete(ob)  # Remove it
copy(ob, name=None)  # Copy with joints. A string names a single object. Lists copy in order and accept only a dict to rename parts and joints
hole(ob, d, on=(0, 0), depth=None, cbore=None, csk=None)  # On frames or points: through, or depth deep
pocket(ob, profile, depth=None, on=None)  # Profile cut in from a face
merge(*obs)  # Return one mesh without boolean, consume other inputs; use the return value
scale(ob, s)  # Solid: s or (sx, sy, sz); group/assembly: one factor s > 0; about its own origin
fillet(ob, r, edges='all')  # Round named edges
chamfer(ob, d, edges='all', d2=None, angle=None)  # Bevel named edges
soften(ob, r, angle=30)  # Round all sharp edges
shell(ob, t, open=None)  # Hollow; open named faces, or the flat faces looking "+Y", "-X +X"
dent(ob, points, r, depth, *, coords="local")  # Press hollows at points in the mesh's local space; parent: the space the part is in
blend(ob, *others, r, step=None)  # Fuse others in, creases filled to about radius r on voxels of r / 5; its faces are all blend
displace(ob, amount, size, noise='perlin', octaves=1, seed=0, direction='normal', fade=None, *, faces=None, coords='local', step=None)  # Push the surface out and in by up to amount, features size across: noise callable or perlin cells ridged turbulence; direction normal, radial or "+Z"…; fade=(z0, z1) along its own Z
bend(ob, angle, axis="+Y", toward="+Z", *, step=None)  # Curl along its own axis toward a perpendicular direction; degrees, groups bend together
twist(ob, angle, axis="+Y", *, step=None)  # Turn sections about its own axis, right handed; near end fixed, far end turned angle degrees
taper(ob, s, axis="+Y")  # Scale across its own axis, from 1 at the near end to ratio s > 0 at the far end
smooth(ob, angle=55)  # Shade each descendant mesh by angle; 0 flat, 180 all smooth
lay(ob, over, reach=None, *, step=None)  # Seat on a surface along own Z, retaining height above own Z=0
```

## Frames, placement and distributions

`Frame.point(x,y,z)` returns a Vector (no `.origin`, no `.turn`); `Frame.move(x,y,z)` returns a Frame.

```python
Frame(origin=(0, 0, 0), normal=(0, 0, 1), up=None)  # A place to build on
.offset(d) .turn(rx=0, ry=0, rz=0) .move(x=0, y=0, z=0) .point(x=0, y=0, z=0)
Frames(frames)  # A list of frames that moves, turns, offsets and jitters as one; what distributors return
ob.face(which)  # Frame of a named face, or furthest along "+Z"
ob.edge(which)  # Path along the edges named which, in the space ob is in: the longest run (as long: the one reaching furthest -X, then -Y, -Z), closed if it closes
bbox(ob, which)  # Frame on its bounding box: a side "+X", an edge "+X-Y", a corner "+X-Y+Z"
local(ob, x=0, y=0, z=0, rx=0, ry=0, rz=0)  # Frame at (x, y, z) of its own space, turned (rx, ry, rz) degrees
at(ob, x=None, y=None, z=None, rx=None, ry=None, rz=None, on=None, anchor=None, *, scale=None)  # Scale about own origin, then place (anchor read after): set what is given, keep the rest; anchor: "-Z", "+Y-Z"…
transform(ob, x=0, y=0, z=0, rx=0, ry=0, rz=0, mirror=None)  # Move it by, as a parent would; its placement, not its mesh
grid(nx, ny=1, px=0, py=0, stagger=False, on=None)  # On a grid
ring(n, r, start=0, angle=360, on=None)  # On a circle
along(path, pitch=None, count=None, spin=0, span=(0, 1))  # Along a path
phyllotaxis(n, d, h=0, angle=137.508, on=None)  # Frames on a disc, or facing out from a cylinder when h > 0
branches(length, d, levels=3, children=3, attach=(0.45, 0.9), angle=45, azimuth=137.508, length_ratio=0.55, diameter_ratio=0.55, tip_ratio=0.15, jitter=0, seed=0, on=None, wander=0, droop=0, *, step=None)  # Depth-first axes and leaf-tip frames, straight or smoothly curved
Frames.jitter(rx=0, ry=0, rz=0, x=0, y=0, z=0, seed=0)  # Random turns and moves along own axes, bounded and bell-shaped
vary(value, spread, n, seed=0)  # Values within spread of value, most near it
scatter(n, size, seed=0, surface=False, on=None)  # size: ellipsoid diameters, or a mesh part / list of mesh parts for its surface
snap(targets, points, direction=None)  # Target first, probe points/frames second; nearest or ray direction "-Z", "+X"… or (x,y,z)
tufts(name, sites, height, width, blades=5, lean=20, direction=None, shape='blade', seed=0)  # One mesh of pointed pieces rooted at Frames in their shared parent space
```

## Parts, materials, articulation, assembly, export

```python
gear(name, teeth, module, width, bore=0, angle=20)  # Involute spur gear
knurl(name, d, h, pitch=None, straight=False)  # Knurled grip; pitch 1 mm by default
thread(name, d, length, pitch, left=False)  # Threaded rod
material(ob, kind, color=None, roughness=None, metallic=None, opacity=None, emission=None, absorb=None, absorb_distance=None, thickness="auto", ior=None, transmission=None, scatter=None, scatter_distance=None, scatter_anisotropy=None)  # Kind: oak walnut pine birch steel brushed_steel chrome aluminium brass copper painted_metal plastic glossy_plastic rubber glass ceramic fabric velvet leather marble concrete bark leaf moss grass rock soil sand water snow foam smoke fog light; color "#rrggbb" or color(x,y,z[,n[,u]])
light(name, kind='point', lm=None, lux=None, color='#ffffff', angle=None, blend=None, shadow=True, size=None)  # Kind: point spot sun ambient; lm lumens (point, spot; 800), lux (sun 100 000, ambient 10 000); spot angle: full opening in degrees, at least 1 and under 180 (default 45); shines along its own -Z
joint(name, child, on, kind='revolute', axis='normal', range=None, follows=None, ratio=1)  # How child moves on the part on was read on: revolute (range in degrees), continuous (no range), prismatic (range in the unit), free (no axis, no range); follows: a child or a joint name, and this joint's value is ratio × its (degrees per unit, or units per degree), no range; returns child
pose(ob, value, joint=None)  # Move the mechanism: that joint to value (degrees or the unit), an error outside its range; what it carries follows; joint= when child has two
seat(host, part)  # Take out of host the volume part fills, as it sits at rest; part untouched
group(name, *children)  # Parent of children
assembly(name, *children, **anchors)  # Parts and anchors
attach(handle, name, *children)  # A detail, under a handle
Handle(root, **anchors)  # Root and anchors
export(root, path, trace=None, *, colors="material")  # root and what hangs on it by its joints, in metres: .glb at the current pose, joints in extras; .urdf a link per moving part, at rest, meshes beside it; .usda the URDF's tree as OpenUSD text, with the materials; .ifc the part tree as IFC4 at the current pose, no joints; GlobalIds can change with geometry or placement and may repeat across models; .obj and .stl its meshes at the current pose; trace=True or SAND3D_TRACE=1 (<stem>.trace.json beside it), or a path: also a JSON of what was built, in the world, nested as the GLB. Export writes meshes and sand3d lights where the format supports them. Curves, text objects and anything else added with raw bpy are left out. Convert them to meshes first, or use Blender's own exporters.
empty_scene()  # Fresh scene
facets(n=None, smooth=...)  # Read count, or set segments per turn (integer >=3 or "auto") at any point; with facets(n): one part, then the previous count
units(name=None)  # Length unit: "mm" (default), "cm", "m"
fingerprint()  # Digest of the source
```

## Worked examples

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
    s3d.pose(leaf, 60)   # shows the swing; a program returns at rest
    return gate
```

## Placement and scale

`at(..., scale=)` scales about the object's own origin, then places it (the anchor is read after). A
solid takes a number or `(sx, sy, sz)`, a group or handle one factor > 0. With a frame list, `at` uses
up the prototype and returns its copies; `scale` is one number or axis tuple for every copy, or a list
of exactly `len(on)` values (a list, even for three sites). With one frame or none, one value.
Profiles and paths take no scale. This replaces copy, scale, place, delete loops; named anchors are
attributes:

```python
sites = s3d.ring(12, 80)
flowers = s3d.at(flower_part(), on=sites, scale=s3d.vary(1.0, .2, len(sites), seed=3))
pot = s3d.assembly("pot", body, handle, rim=body.face("top"))
s3d.at(flower, on=pot.rim)
```

`scale` on a group or handle takes one factor s > 0 and scales everything under it about the group's
own origin: each mesh's coordinates and each part's place in its parent are multiplied by s; the group
stays where it is; turns, materials, `smooth` and vertex and face counts are kept; no object keeps a
scale. A later `at` on a part keeps its scaled place; new lengths given to it are in program units. A
solid keeps its own `scale`, per axis included; its children do not move. **Frames, `Frames` and
anchors read before any scaling do not follow** (number anchors stay as they were): read `bbox`, faces
and `local` again, or rebuild the anchors, after scaling. Refused for now: a group holding a jointed
part, carried by one, or that a joint outside hangs on or follows — scale before declaring joints, or
build at size.

A circle path is `arc(r=r)`. An irregular planar outline:
`poly([tuple(f.origin)[:2] for f in ring(n, r).jitter(x=j, y=j, seed=3)])`. An organic blob: extrude or
loft `superellipse(w, d, n=2)` sections, then `displace` at the outline's scale before fine grain.

## Distributions

`along` covers `span` of the path's arc length; `pitch` starts at the span's start; `count` leaves out
the repeated endpoint only on a full closed span. `spin` adds degrees per frame about the tangent:
nonzero spin parallel-transports X along the path (a closed path may keep a roll jump at its seam);
zero spin keeps X referenced to world Z.

`Frames.jitter` and `vary` draw triangular values in [-a, a], mode 0, from their own seeded generators.
Jitter turns in degrees and moves in program units along each frame's original axes; jittered frames
stay read on their part. `vary` returns floats `value + draw`: its spread is absolute, in the value's
unit (`vary(24, 5, n)` lies in [19, 29]), so a value of zero varies too.

`scatter` gives 0–4096 frames, each the best of 16 Mitchell candidates by spacing. With three ellipsoid
diameters, candidates are uniform in volume (in area with `surface=True`), normals radial, and `on`
sets centre and axes. With a mesh part, a list of parts or a group (all its mesh descendants) instead,
e.g. `scatter(420, fruit, seed=1)`, it samples their closed manifold surface by area, normals facing
out, frames in the parts' shared parent space, as `snap` gives them; `surface` is implicit and `on`
refused. Overlapping parts keep their interior surfaces: `join` first for a union. An empty group
raises. `snap` takes groups and lists the same way and drops ray misses: test `if hits:` before
`hits[0]`. `group.face(...)` raises: use `bbox(group, "+Z")` or a part's `.face(...)`.

`branches` returns its axes depth-first, each with `.path`, `.d` (a diameter law), `.level` (the root
is 0), `.name` and `.parent` (`None` for the root); the list's `.tips` is a `Frames`, one per leaf
axis. Leaf axes: `[a for a in axes if not any(b.parent is a for b in axes)]`. A child's diameter is
relative to its parent's base diameter; azimuth restarts at each parent. Paths and tips are already in
the frame carrying `on`: `wire(axis.name, axis.path, axis.d)`, without applying `on` again. At most
4096 axes and 128 levels. `wander` bounds the random heading turn per segment, in degrees; `droop`
turns toward `on`'s -Z by up to that many degrees over each axis (negative rises). Curved axes are
eight spline-smoothed segments, children attaching by arc length and facing the tangent; with both
zero, axes are exact two-point segments. Curvature radii exceed twice the section radius, so axes
build with `wire` or a matching `sweep` law. `jitter` varies lengths, lean and azimuth steps by up to
its fraction.

`tufts` builds one mesh for all sites, never an object per tuft. Each site (a Frame or `Frames` in one
parent space, kept on the carrier) roots `blades` pieces exactly at its origin, growing along its Z by
default. `height` and `width` (> 0) and `lean` (maximum deviation, degrees in [0, 85]) take a number or
an `(x, y, z, n)` callback per site; `direction` a nonzero vector in the sites' space, or such a
callback (a tangent field combs fur). Vectorized callbacks get x, y, z of shape (N,) and n of shape
(3, N), and return (N,), or (N, 3) for directions. `seed` is an integer ≥ 0. `shape="blade"` is a flat
pointed ribbon, 2 triangles; `"cone"` a triangular double cone, 6; both widest at mid-height, pointed
at tip and root. Triangles = sites × blades × 2 or 6, whatever `facets`. Empty sites give an empty
mesh.

## Laws, poles and tips

Laws are lists of `(u, value)`, u strictly increasing from 0 to 1 by path length, interpolated by
shape-preserving monotone cubics; sweep scale also takes `(sx, sy)` values. A plain `(sx, sy)` end
scale, and numeric scale and twist, run linearly from the start. Laws on closed paths are refused.
Size laws refuse interior zeros, partly zero pairs and all-zero laws. A zero end is a pole (one
outline, no holes), capped by a monotone square-root profile that meets the body tangentially. Section
sizes are never silently reduced: a crossing-ring error gives the path fraction, a section-radius limit
in the program's unit and a uniform size factor to apply to the profile or every diameter.

A zero-size first or last loft section gives only the pole's position (its rotation is ignored); the
neighbouring section, after `follow` turns it, sets the pole's tangent plane, and the cap stays within
the end interval without overshooting the neighbouring sections.

`tip` (loft, wire, sweep) is "round", "sharp" (the end span linear), "flat" (a zero end takes its
neighbour's size, capped in the end plane), or a `(start, end)` pair; nonzero ends are always capped.
`rings` adds that many rings per span. In a numeric sweep, if a span would turn at least 180°
between rings, it keeps chord interpolation and emits `sand3d.solids.UndersampledTwist`
(an error in strict mode). `wire` also takes explicit arc-length fractions strictly inside
(0, 1). `wire(d=(width, thickness))` is a constant elliptical section; laws describe circular
diameters.

## Materials and media

`material` values left `None` inherit the preset; the material's name lists the preset and the
overrides. `color=` changes the surface tint only. `opacity` is alpha; `transmission` (0..1) is the
transmitted fraction, independent of it; `ior` is finite in 1..1000.

`absorb` is the sRGB colour (`#rrggbb` or RGB) white light becomes after `absorb_distance` program
units: transmittance at depth x is `linear(absorb) ** (x / absorb_distance)`. `scatter` is the sRGB
colour the medium sends light back in: channel c scatters `linear(scatter)[c] / scatter_distance` per
unit, so white light travels `scatter_distance` on average before scattering. Distances are finite and
≥ 0; 0 disables the effect. `scatter_anisotropy` in -1..1 (Henyey-Greenstein g): 0 every way alike, > 0
forward (a glow with the light behind), < 0 backward. Absorption and scattering add up.

The medium fills the closed mesh; the surface hides it when opaque. A medium with no visible boundary
needs `transmission=1`, `ior=1`, `roughness=0`, as `smoke` and `fog` set. Its density is the same
everywhere inside: one envelope gives a soft mass, not filaments. Build one closed envelope with one
medium, not stacked alpha shells. A light smoke mostly scatters, a black smoke only absorbs, murky water
is `water` plus `scatter`; fog, mist, steam and cloud are `fog` with a shorter `scatter_distance` where
thicker. How Cycles renders media: guide `fire-smoke`.

| preset | surface colour | roughness | transmission | IOR | absorb at distance | scatter at distance, anisotropy |
|---|---|---|---|---|---|---|
| `water` | `#f4f8f8` | 0.08 | 1 | 1.333 | `#b8e8ed` at 1 m | none |
| `glass` | `#ffffff` | 0 | 1 | 1.5 | none | none |
| `smoke` | `#ffffff` | 0 | 1 | 1 | `#d6d6d6` at 1 m | `#ffffff` at 625 mm, 0.3 |
| `fog` | `#ffffff` | 0 | 1 | 1 | none | `#ffffff` at 10 m, 0.3 |

Natural presets are average untextured colours, nonmetallic, alpha 1: `bark` (outer wood), `leaf`
(waxy foliage, coat 0.12), `moss`, `grass`, `rock`, `soil`, `sand`, `water`, `snow` (coat 0.03), `foam`
(white diffuse sea foam or suds, roughness 0.95, no transmission). There is no `wood` or `coral`.

Water is a volume bounded by a **closed mesh**: model its bottom and sides as well as its top, with
outward normals. Cycles absorbs along the actual ray length. `thickness` is the constant depth glTF
raster viewers assume instead: `"auto"` estimates it at export as 2 × volume / area of the meshes that
wear the material (D/3 for a sphere), one value per material; a length sets it; 0 disables absorption
in those viewers and omits the glTF volume extension. It creates no geometry.

Export: GLB carries `KHR_materials_volume`, `KHR_materials_ior` and transmission (distances in world
metres, thickness in mesh units). **glTF has no ratified scattering**: a scattering medium exports its
total extinction as volume attenuation, so a GLB viewer, and Blender after reimport, show smoke or fog
as a dark medium. USD Preview Surface carries IOR and coat, transmission as `opacity * (1 -
transmission)`, no volume or sheen: fully transmitting water, glass, smoke or fog can be invisible.
IFC carries surface colour, transparency `max(1-opacity, .85*transmission)` and GLASS reflectance. OBJ
carries vertex colour, URDF colour and opacity, STL nothing.

## Colour functions

`color` may be a function `color(x, y, z[, n[, u]])`: exactly 3, 4 or 5 positional parameters, no
variadics or keyword-only ones. It reads face centres in the mesh's local frame, before placement, in
program units, with outward unit normals, and returns sRGB: `"#rrggbb"` or an RGB triple in [0, 1], no
alpha. `u` is the face mean of the vertices' construction progression: along a loft's sections, along a
wire's or sweep's arc length, bottom to top for revolve, dome, sphere, cone and cylinder; caps take
their end value. A five-parameter function refuses a part without it.

Write it vectorized: x, y, z and u are float64 arrays of shape (k,), n has shape (3, k) (`n[2]`, not
`n[:, 2]`); return a numeric array of shape (k, 3), finite, in [0, 1], else it raises — rows are
faces, even when k = 3; no hex arrays, no (3, k). A probe on up to 8 faces selects this path, then one call covers every
face; if the probe raises or returns another shape, the function is called once per face with scalars
and a normal tuple. One vectorized path is enough: no isinstance branch. The probe is an extra call and
every export evaluates anew: functions must be pure. Example:
`lambda x,y,z: np.stack((x*0+.2, y*0+.4, z*0+.6), axis=-1)`.

The colour is reflectance: do not bake a light direction, highlight or shadow into it through normals;
use normals for an authored surface property (dust on upward faces). The review renderer lights with
fixed lights, and emission adds colour without lighting neighbours; Cycles uses real lights and can
look different. One RGB per face, no UVs or textures: fine colour needs fine faces; prefer colour to
sub-millimetre displaced veins or grain. `copy` keeps the function, `join` and `merge` the first
object's; functions are session-local, not saved in Blender files.

GLB always exports callable colours on face corners (COLOR_0); `colors="vertex"`, GLB only, also puts
plain colours on corners and shares white materials, an emissive material keeping its colour (the
area-weighted mean for a function). OBJ, URDF and USD use the area-weighted linear mean.

Placement, copy, merge, displace, bend, twist, taper, scale, lay and interpolating mesh edits keep the
construction labels behind `u` and `coords="path"`; a join between parameterized parts transfers them
(the first operand's at shared intersections). Booleans with an unparameterized operand, blend, field
and new topology drop them; merge fills missing labels with NaN.

## Implicit fields

`field` keeps density < level. Coordinates, `size` and `cell` are in program units; density and level
share one arbitrary scalar unit. Each axis is sampled evenly at spacing ≤ cell, with at least two
intervals. Boundary samples are forced outside: leave a margin of one cell, or the surface closes within
the outermost cell. The density must be pure and deterministic, with finite values. Fast path: it gets
three same-shaped float64 arrays and returns an ndarray of that shape — use `np.sqrt`, `np.sin`,
`np.minimum`, `np.maximum`, not `math` or `min`/`max`; a trial call raising TypeError or ValueError, or
returning a non-array, falls back to scalar calls. Programs may import numpy.

Choose `cell` from the smallest feature the asset must keep, not its overall size: about half the
thinnest wall (a leaf, a frond, a shell), two thirds of the smallest relief that must read. Triangles
and time grow as surface area / cell²: halving cell quadruples both; a closed surface 1.5 m across at a
7 mm cell holds about two million triangles. Features below cell can vanish. Past one million lattice
points, sampling probes four-cell blocks first: a whole component hidden between probes can be missed,
so resolve the coarse scale (four cells) too.

Budget: 1 M coarse probes, 8 M fine samples, 4 M triangles; increase cell to reduce cost. Non-finite
samples, empty or singular surfaces and a cell below mesh coordinate precision are refused.
Disconnected closed shells are allowed; `min_component_cells` (default 3) drops components whose
longest extent is under that many cells, always keeping the largest; 0 keeps all. A direction face on a
field (`ob.face("+Z")`) falls back to its furthest outward-facing triangle when no facet is parallel.

`noise` returns a float for scalars, else a float64 array of the broadcast shape, in [-1, 1]: seeded
gradient (perlin; ridged and turbulence transform it) or nearest-cell noise, the same across runs and
platforms, not the realization `displace` uses. Coordinates are dimensionless, finite, magnitude
≤ 2**50.

`waves` returns a pure `f(x, y, z)` in [-1, 1], float or float64 array, independent of z; it makes no
mesh. `direction` (default "+X"; degrees anticlockwise from +X toward +Y, or a signed XY axis) is the
phase gradient: crests run across it. `wavelength` > 0 is measured along it. `phase` is in degrees, 0 a
crest at the origin. `sharpness` in [0, 1] turns cos(t) into cos(t + sharpness·sin(t)): narrower crests,
broader flatter troughs, same period and bounds; the mean can be negative. A height profile, not a
fluid: no horizontal motion, overturning or breaking. `spread` in [0, 90] is the half-angle of four
seeded satellite waves around the primary (zero: one exact cosine); `seed` acts on spread only.
`centers=[(x, y), …]` gives circular waves sharing wavelength, sharpness and phase, excluding direction and spread; `decay` > 0 (centers only) is an e-folding length
per source, the sum divided by the summed envelopes where they exceed 1, so a lone ring keeps its full
height; without decay the sources are averaged. Inputs finite, |distance / wavelength| ≤ 2**50.

Use it as a height: `f = waves(3000, direction=25, sharpness=.8, spread=15, seed=7)`, then
`displace(ob, 200, 500, noise=f, direction="+Z")`. `size` sets refinement, not wavelength: give the
shortest component at least 16 samples per period (more for sharp crests), or set `step`. Push along a
fixed direction for a height surface; normal displacement on a curved mesh can cross itself. Compose
bounded: a shore is a mask (`f(x,y,z) * np.clip((x-shore)/width, 0, 1)`), not `decay`; modulate with
`(.7 + .3*s3d.noise(x/500,y/500,z/500))`; sum with `np.clip(f(x,y,z)+.2*g(x,y,z), -1, 1)`. The same
field gives sand ripples (`waves(80, direction=20, sharpness=.7)`), dunes (`waves(8000, direction=15,
spread=20, sharpness=.6, seed=3)`) and corrugated sheet (`waves(75, direction="+X")`), as heights, not
thickness-preserving bends. To colour crests (this does not model foam):
`material(ob, "plastic", color=lambda x,y,z: np.where((f(x,y,z) > .7)[:, None], np.array([1.,1.,1.]), np.array([.02,.15,.2])))`.

## Displacement, denting, laying

With a callable `noise=f`, `displace` calls f with three float64 arrays in the part's frame and program
units (`coords="local"`); f returns a same-shaped finite array in [-1, 1], else it raises. Values
multiply `amount` and the fade directly, without the named noises' centring; coordinates are not
divided by `size`. Keep `octaves=1` and `seed=0`; compose seeded `s3d.noise` calls inside f for layers
and domain warps.

`faces` restricts displacement and refinement to a face name, a list of names (every facet with that
label, curved ones included) or a direction (`"+Z"`: the patch `ob.face("+Z")` reads, before
refinement); an unknown name lists the available ones. The selection's boundary, open patch edges
included, stays fixed, with a smoothstep ramp to full strength over `size`, in local straight-line
distance; a selection with no boundary has no ramp. Shared edges gain collinear vertices so the mesh
stays closed; unselected faces are not triangulated. A coarse patch with no interior vertex cannot
move. This holds a panel's rim, a relief's frame, a liquid's shore; it neither keeps thickness nor
prevents self-crossing at large amplitude.

With `coords="path"` (a wire, sweep or loft), f gets construction coordinates (s, angle, r): arc length
in program units, the transported angle in degrees in [-180, 180] (independent of twist and Frenet
roll), and the construction radius. They are labels, not measurements of the edited mesh: they follow
copies, joins, merges and deformations without reprojection; a closed path keeps a seam in s. Named
noise is refused with path coordinates.

`dent` reads points and Frame origins in the mesh's local space; `coords="parent"` reads them in the
space the part is in, as `snap` and `scatter(part)` give them. `r` and `depth` stay local lengths.

`lay` moves every point of a placed piece along its own Z onto `over`, keeping its height above the
piece's Z = 0; a group uses its root frame, a list seats each item. `reach` bounds the travel (None:
unbounded); on a reach failure nothing moves. Seating a piece on itself is refused.

## Filling a container

`fill("soil", pot, 80)` makes a new solid in the voids retained below height 80 in the container's own
frame (a part, group or assembly); the container is kept. A list of parts needs a `Frame`, e.g.
`fill("river", channel, local(channel, z=12, ry=3))`; an unbound Frame is in world space; its normal
points out of the fill. The result takes the plane's axes and stands on its own Z = 0, its origin under
the level's origin at the deepest point: local Z runs up to the free surface, its face `top` (also its
boundary edges), the other faces `side`. On a tilted level local X and Y lie in the surface, so `waves`
and `displace(direction="+Z")` follow it. All pockets are one object; closed cavities count, even with
no free surface. Containers must be closed manifold solids: an open cup is an opening between solid
walls, not missing faces. Waves on the surface alone, shore fixed:
`displace(water, 2, 20, noise=waves(100), direction="+Z", faces="top")`.

`clearance=None` overlaps the walls by about 0.04 mm (no coincident transmissive surfaces); an explicit
clearance is in program units: > 0 a gap, < 0 an overlap, 0 exact contact. It offsets the walls, not
the level, and is a small allowance: large values self-intersect or collapse thin features. A level
below the floor, above an open rim or reaching a leak retains nothing and raises `ValueError`; leaking
pockets are dropped when others retain material. Static geometry: no flow, meniscus, trapped air or
spill search; a tilted channel needs closed ends below its plane.

## Resolution

| verb | `step=None` | `step` > 0 | `step=0` |
|---|---|---|---|
| `displace` | edges ≤ max(size/4, D/128) | maximum edge length | moves existing vertices only |
| `bend`, `twist` | ≥ 4 axial segments, ≤ 3° each | axial spacing | no slices |
| `lay` | existing vertices | maximum edge before seating | existing vertices |
| `blend` | voxels of r/5 | voxel size | — |
| `branches` | 3° of accumulated turn | arc-length spacing | — |

D is the part's largest local box dimension. Automatic `displace` refinement raises past 500 000 faces:
give a larger step. Existing fine edges are never decimated. `field(cell=…)` is a length; `facets(n)` and
`rings=n` are counts.

A fixed `facets(n)` sets turns per revolution across and along sweep, loft, wire, body and spline paths
(a straight span keeps only its stations); bend and twist cut sections by total angle. On axisless
surfaces it means a target edge `L = π D / n`, invariant under placement: `field` uses `max(cell, L)`
(D the requested box); `displace` refines toward `max(size/4, D/128, L)` unless `step` is given;
`blend` keeps its voxel closing, then collapses toward `4 area / (√3 L²)` triangles (at least four,
the original kept if collapse breaks manifoldness); `hull` keeps its points. Use a larger n when thin
branches or cavities vanish. Fixed counts shade flat unless `smooth=True` (chosen at the first `facets`
call). `"auto"`, the default, is a 0.05 mm chord tolerance with usual shading.
`with facets(n):` restores the previous count, even on error. A part keeps its construction
shading through placement, grouping, material changes, copies and mesh edits.
`smooth(ob, angle)` overrides that choice and persists through edits and copies. Triangle budgets: guide `resolution`.
