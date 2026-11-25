---
title: Edits
order: 4
lead: An edit changes its first argument in place and returns it. Edges and faces are reached by the names their maker gave them. Copy and delete are exceptions; split can return two parts. Keep the returned value of join and merge.
---

## Booleans and copies {#booleans-and-copies}

Lengths below are in program units, millimetres by default. Booleans work on solids, not profiles or groups. Extrude a profile first; pass a group's solid parts individually. To retain a tool that an edit consumes, pass a `copy`.

::: fiche cut join intersect
sig: cut(ob, *tools)
sig: join(ob, *others)
sig: intersect(ob, tool)
what: `cut` subtracts tools, `join` fuses solids, and `intersect` keeps their common volume. The tools or other solids are consumed.
param ob: The solid to change.
param tools, others: Solids or lists of solids; cut and join accept several. To repeat a tool, place copies with `at(tool, on=frames)`.
param tool: One solid for intersect.
toy: edits_booleans | A drilled and notched plate with a joined boss; beside it, the intersection of a cube and a sphere.
limits: A cut that removes nothing raises. Join keeps the first solid's name and material; other materials are lost, with a warning. Use a group for touching parts that must keep separate materials. Use the returned solid.
:::

::: fiche split
sig: split(ob, frame, keep="above")
what: Cut a solid with a frame's plane. Keep one side, or keep both as separate solids.
param ob: The solid to cut.
param frame: Its origin lies on the cutting plane; its normal points above it.
param keep: "above" by default, "below", or "both", which returns (above, below); the second is new.
toy: edits_split | Both halves of a sphere cut by a tilted plane, moved apart.
limits: Above means the frame's normal side, not world +Z. Other keep values raise.
:::

::: fiche copy delete
sig: copy(ob)
sig: delete(ob)
what: Copy makes an independent object and leaves its source untouched. Delete removes an object from the scene and returns no object.
param ob: Copy accepts a solid, group, assembly handle or list; delete also accepts lists of objects.
toy: edits_copies | Two pegs share one mesh after merge. The stretched sphere survives; its temporary copy is deleted.
limits: A copy keeps name, placement, mesh labels and joints. Groups carry their children; handles carry anchors. Copied joints hang on the same parent, or its copy when both are copied. A list returns copies in order and preserves joints between them. Objects consumed by another verb are already gone.
:::

::: fiche merge
sig: merge(*obs)
what: Put several parts into one mesh without a boolean. Touching or overlapping parts remain separate shells; the first mesh's name is kept and the other inputs are consumed.
param obs: One or more parts, lists, groups or assemblies containing meshes.
see: [Example: The two pegs become one mesh without changing their shape.](reference/edits#copy)
limits: Keep the returned mesh. A later boolean fuses its shells first; merge itself does not make a continuous skin. It needs at least one mesh.
:::

::: fiche scale
sig: scale(ob, s)
what: Scale about the object's own origin. A solid changes its mesh; a group or assembly changes all descendant meshes and their positions together, while the root stays in place.
param ob: A solid, group or assembly handle.
param s: A number or (sx, sy, sz) for a solid; one finite positive factor for a group or assembly.
see: [Example: The sphere is stretched 1.6 times along its own X.](reference/edits#copy)
limits: Scaling a solid does not move its children. Group scaling preserves turns, materials, shading and vertex/face counts, and leaves no object scale; a later at keeps each part's scaled place and new lengths remain program units. Frames, Frames lists and anchors already read, including numeric anchors, do not follow: read bbox, faces and local again, or rebuild anchors. Groups with joints inside, attached to them or crossing their boundary are refused: scale before declaring joints or build at size.
:::

For repeated placement, `at(prototype, on=frames, scale=...)` replaces copy, scale, place and delete loops. It scales about the object’s origin before placement and reads the placement anchor after scaling. It consumes the prototype. Give one factor or axis tuple for all copies, or a list with exactly one value per frame. Profiles and paths cannot be scaled this way.

## Machining {#machining}

::: fiche hole pocket
sig: hole(ob, d, on=(0, 0), depth=None, cbore=None, csk=None)
sig: pocket(ob, profile, depth=None, on=None)
what: Hole drills circular openings; pocket cuts a profile inward from a face. Both cut through by default, or stop at the requested depth.
param ob: The solid to machine.
param d: Hole diameter.
param on: Hole accepts a point (x, y), a frame or a list of sites. Points drill down from above. Frames drill against their normal, starting where the axis enters the part. Pocket accepts a frame or frame list; None starts above the part's origin, facing up.
param depth: Inward depth from the entry surface; None cuts through.
param cbore, csk: Counterbore (diameter, depth), or countersink (diameter, included angle in degrees). A numeric csk uses 90 degrees.
param profile: One profile drawn in the pocket frame's plane, translated within that plane only.
toy: edits_machining | Through holes at the corners, a counterbore and countersink, and shallow rectangular and round pockets.
limits: Hole mouths are named hole; pocket floors and walls are pocket.bottom and pocket.side. Repeat a pocket with on=frames, not a list of profiles. A counterbore or countersink no wider than the hole adds no wider opening; a valid counterbore takes precedence when both are given.
:::

::: fiche fillet chamfer soften
sig: fillet(ob, r, edges="all")
sig: chamfer(ob, d, edges="all", d2=None, angle=None)
sig: soften(ob, r, angle=30)
what: Fillet rounds named edges; chamfer cuts flat bevels along them. Soften rounds every edge whose adjoining faces turn by more than its angle threshold.
param ob: The solid to edit.
param r: Rounding radius for fillet and soften.
param edges: A name, space-separated names or a list, such as "top side" or ["hole", "cut"]. "all" means every named edge.
param d, d2: Chamfer distance on both faces, or d on the face the edge is named after and d2 on the other.
param angle: For chamfer, an alternative to d2: d2 = d * tan(angle), with 1 ≤ angle < 90 degrees. For soften, the threshold in degrees, default 30.
toy: edits_edges | Top fillet, unequal top chamfer, and all sharp edges softened.
limits: Rounding clamps where the radius does not fit and raises if it would leave the solid open. Chamfer's angle overrides d2 when both are supplied. Soften changes geometry; smooth changes shading only.
:::

::: fiche shell
sig: shell(ob, t, open=None)
what: Hollow a solid inside its existing surface, leaving walls t thick. Remove selected faces to make an open tray or housing; without open, leave a closed void.
param ob, t: The solid and wall thickness in program units.
param open: Face names, directions, or both: "top", ["top", "start"], "-X +X", or "top -Y".
toy: edits_shell | A rounded tray with its top removed and 1.5 mm walls.
limits: A direction selects the flat face furthest that way, as ob.face does. Facets of a curved side do not count: cut or split it flat first, then open "cut" or the tool's face name. A maker's named curved face can be selected by name.
:::

## Surface relief {#surface-relief}

Choose the structure before adding noise: `blend` fuses masses, `displace` adds relief, and `dent` presses local hollows. `hull` wraps a convex mass and loses concavities. Use relief when it changes the silhouette or surface structure, never only to carry finer colour.

::: fiche displace
sig: displace(ob, amount, size, noise="perlin", octaves=1, seed=0, direction="normal", fade=None, *, faces=None, coords="local", step=None)
what: Move the surface in and out by up to amount, with features about size across. Use a named noise for general grain or a callable for a designed relief.
param ob: The solid to edit.
param amount, size: Displacement amplitude and positive feature size, in program units. With a callable, size controls refinement and the selected-face boundary ramp, not the callable's coordinates.
param noise: "perlin" for soft hills, "cells" for cell bumps and border grooves, "ridged" for sharp crests, "turbulence" for swells and creased hollows; or a function returning values in [-1, 1].
param octaves, seed: A positive integer layer count and an integer seed. Named noise samples local coordinates divided by size; the same seed reproduces the field.
param direction: "normal" follows vertex normals; "radial" points from the local origin (the origin itself stays fixed); an axis such as "+Z" uses that local direction.
param fade: None, or (z0, z1): full strength at z0, zero at z1, linear between, clamped outside. Either height can be higher; they must be finite and different.
param faces: None for the whole surface, a face name, a list of names, or a direction such as "+Z".
param coords: "local" for (x, y, z), or "path" for construction labels (s, angle, r); path requires callable noise.
param step: None for automatic refinement, a positive maximum edge length, or 0 to move existing vertices only.
toy: edits_displace | Perlin, cells, ridged and turbulence on four pebbles, from left to right.
limits: Moved faces may no longer be flat: read needed face frames first. Names survive, but displacement neither preserves thickness nor prevents self-intersection. A small size does not force arbitrarily fine geometry; choose step for the mesh separately.
:::

### Noise and callbacks {#displace-noise}

Named noise layers double frequency and halve weight at each octave, then normalize by the sum of weights. The field is centred by its area- and fade-weighted mean and divided by one plus the absolute mean. This keeps roughly the same volume and bounds movement by amount; amount is an upper bound, not a promised peak height.

A callable receives three float64 arrays in local program units and returns a same-shaped finite real NumPy array in [-1, 1], otherwise the call raises. Its values multiply amount and fade directly, without centring or division of coordinates by size. Keep `octaves=1` and `seed=0`; compose seeded `noise` calls inside the callback for layers and domain warps.

With `coords="path"` on a wire, sweep or loft, the arrays are arc length s in program units, transported angle in degrees in [-180, 180], and construction radius r. The angle is independent of twist and Frenet roll. These are construction labels, not measurements of the edited mesh: they follow copies, joins, merges and deformations without reprojection. Closed paths retain a seam in s. Named noises are refused in this mode.

### Holding a rim {#displace-faces}

A name selects every facet bearing that label, including curved faces. A direction selects the patch that `ob.face` would read before refinement. An unknown name reports available names. Only selected faces are refined and displaced. Shared edges gain collinear vertices to keep the mesh closed; unselected faces are not triangulated.

The selected boundary, including open patch edges, stays fixed. Strength rises with a smoothstep ramp over size, measured by local straight-line distance to that boundary. A selection without a boundary has no ramp. A coarse patch without interior vertices cannot move. This holds a panel rim, a relief frame or a liquid shore.

### Paying for relief {#displace-resolution}

Automatic refinement targets edges of at most max(size / 4, D / 128), with D the largest local box dimension. Fixed `facets(n)` adds the lower bound π D / n; explicit step takes precedence. Existing fine edges are never decimated. Refinement raises if it would exceed 500,000 faces: give a larger step. With step=0, vertex order and attributes remain.

Build the coarse whole first and budget all copies: both copies and instances multiply visible triangles. Increase step to reduce added topology without changing noise feature size. Spend faces on shape visible at the final render size, not on invisible grain.

### Relief in a scene {#displace-scenes}

- An organic blob can start as extruded or lofted superellipse sections. Displace at the outline's scale before adding fine grain.
- Terrain is a supported solid: displace its top along +Z and keep its underside flat. Put broad dunes and small ripples in separate calls. Asymmetric dunes need a callable with a gentle windward slope and steeper slip face; a symmetric sine makes ripples. Ripple relief below about 1/400 of the scene width vanished in the terrain guide's example. Budget sampling across the whole ground.
- Snow drifts can use a 0..1 callable to raise mounds without centring. Named Perlin seldom reaches the requested amount: the terrain guide measured at most 10 mm rise for amount=45 on an 800 mm patch. A dusting is colour alone.
- Moss uses low cushions on the ground itself, a few millimetres high with features about a tenth of the patch. A shared 0..1 mask can drive displacement, colour and pile placement; soil remains between patches.
- Water fills existing banks and a bottom with fill. Displace its "top" only, using waves and direction="+Z", to keep the shore fixed. Waves has no horizontal motion, overturning or breaking; falls need their own solids.

::: fiche dent
sig: dent(ob, points, r, depth, *, coords="local")
what: Press round hollows into a surface at chosen points. Use it for buttoned upholstery, pores or seed seats.
param ob: The mesh to edit.
param points: An iterable of (x, y, z) points or frames, using each frame's origin.
param r, depth: Hollow radius and central depth, both local lengths. Nearby hollows add their pushes.
param coords: "local" reads points in the mesh's own space; "parent" reads the space the part is in.
toy: edits_dent | Nineteen phyllotaxis sites snapped onto a lotus pod, then pressed into its surface.
limits: On a placed part, snap and scatter(part) supply parent-space sites: pass coords="parent". The verb refines around the hollows and pushes vertices inward along their normals; it is not a drilled hole or a thickness constraint. Hollows near a pole can pinch, as at the centre of this toy.
:::

::: fiche blend
sig: blend(ob, *others, r, step=None)
what: Fuse solids and fill concave creases to about radius r. With no others, fill the first solid's own creases; for a branching shape, blend large masses first and smaller details afterwards.
param ob, others: Solids to fuse; others may be lists and are consumed on success. The first solid keeps its name, frame, placement and material; other materials are lost.
param r: Positive closing radius. A ball of this radius rolling outside cannot reach the creases that get filled.
param step: Positive voxel size; None uses r / 5. Zero is refused.
toy: edits_blend | A cactus trunk and two arms become one continuous skin.
limits: This is voxel closing, not an exact fillet: convex shapes stay within about a voxel, and gaps narrower than about 2r close only when resolved. Parts thinner than 2r in their own box are refused. The estimated surface budget is 600,000 faces; increase step or r, or blend smaller groups and join them. A result extending more than 1.5 voxels beyond the input box is refused. No inputs are consumed on failure. All faces become blend and <ob>.blend, with no named edges; construction coordinates are lost. Query the new surface by direction or frame.
:::

With fixed `facets(n)`, blend still performs voxel closing, then targets 4 × area / (√3 L²) triangles, at least four, where L = π D / n. It keeps the original result if collapse breaks manifoldness. Raise n if thin branches or cavities disappear.

::: fiche lay
sig: lay(ob, over, reach=None, *, step=None)
what: Seat a placed piece on a carrier, preserving each point's height above the piece's own Z=0 plane. A flat base follows the carrier; what was below the base stays buried and what was above it stands proud.
param ob: A part, group, assembly or list. A group uses its root frame; a list seats each item independently.
param over: The carrier surface, containing mesh parts.
param reach: Maximum distance from the base plane to the found surface; None is unbounded.
param step: Positive maximum edge length before seating; None or 0 keeps existing vertices.
toy: edits_lay | An elliptical leaf laid over a stone, refined with step=20.
limits: Place first, then lay. Rays follow the piece's own Z; when a ray misses the carrier, the code falls back to its nearest surface point, which can also move sideways. A face stays flat between vertices: refine only when the carrier's curvature needs it. A part cannot be seated on itself. Reach failure leaves positions unchanged for the current part or group, but prior list items can already have moved and positive-step refinement can already have changed topology.
:::

For terrain placement, `lay(at(leaf, on=site), ground)` follows the surface under a sampled site. Common translation and rotation of piece and carrier do not change the result in the piece's frame. Use step=0 unless curvature requires subdivision; step=3, for example, adds sampling at a 3-unit maximum edge length.

::: fiche smooth
sig: smooth(ob, angle=55)
what: Set shading independently of the program's facets setting. Edges where faces turn by more than angle remain sharp; the choice persists through edits, copies and export.
param ob: A part, group, assembly or list; every descendant mesh is shaded.
param angle: Degrees from 0 to 180: 0 shades every face flat; 180 leaves no sharp edge.
toy: edits_smooth | Three twelve-sided logs shaded at 0, 55 and 180 degrees.
limits: Shading changes no geometry: the silhouette stays faceted. Fixed facets normally shades flat unless its smooth setting or this per-part override says otherwise.
:::

## Deformations {#deformations}

::: fiche bend twist taper
sig: bend(ob, angle, axis="+Y", toward="+Z", *, step=None)
sig: twist(ob, angle, axis="+Y", *, step=None)
sig: taper(ob, s, axis="+Y")
what: Bend curls a part, twist rotates its sections, and taper scales them across an axis. A group deforms together in its root frame, using one shared extent.
param ob: The part, group or assembly to deform.
param axis, toward: Directions in the part's own frame, not world directions. Bend requires toward perpendicular to axis.
param angle: Degrees: total curl for bend, right-handed rotation at the far end for twist. Zero leaves the mesh unchanged.
param s: Positive far-end scale for taper; the near end stays at 1. A value of 1 leaves the mesh unchanged. No refinement is needed.
param step: For bend and twist, None gives at least four axial segments and at most 3 degrees per segment in automatic mode; positive sets axial spacing; 0 adds no slices. Fixed facets sets segment count by total angle.
toy: edits_bend | The same blade bent 90 degrees, twisted 180 degrees and tapered to 0.15 of its width.
limits: Bend's neutral axis passes through the origin: signed distance u rotates by angle * u / L, where L is the axial extent. Negative u bends the other way; angles beyond 180 degrees are allowed. Twist fixes the least signed coordinate and rotates the far end. Face names, placement and materials survive; refined faces inherit their parent's names. Read flat face frames before deforming. Taper's s is a ratio, unlike extrude's taper in degrees or superellipse's narrowing fraction.
:::
