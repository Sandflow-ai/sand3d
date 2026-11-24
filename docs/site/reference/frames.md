---
title: Frames and placement
order: 5
lead: Build a part in its own space, then place it on a frame. A frame gives an origin and three axes; placement adds distances and angles along those axes.
---

## Placement is a frame plus values {#placement}

`at` remembers a frame and six values: x, y, z, rx, ry, rz. Values start at zero. Each call sets only the values you give; the others stay. `on=` replaces the frame while keeping those values. Distances run along the frame's axes, and angles are in degrees.

For example, `at(part, x=20, z=10)` followed by `at(part, z=30)` leaves x at 20 and sets z to 30. It does not add 30. A later `at(part, on=face)` keeps x=20 and z=30, now measured in that face's axes. Give zero explicitly when you want to reset a value. Placing on a frame does not itself parent the object; group related parts to move them together. `transform` instead moves the whole placed part as a parent would.

Lengths use the program's unit, millimetres unless `units` was set first. Build ordinary primitives centred in X and Y, with their base at Z=0: `box` is an `extrude` of `rect`. `extrude(..., both=True)` centres the extrusion on its plane. Geometry defined by explicit coordinates, such as `hull` points or a `wire` path, stays where those coordinates put it; it is not recentered.

## Frames and their axes {#frames}

::: fiche Frame Frame.offset Frame.turn Frame.move Frame.point
title: Frame and its operations
sig: Frame(origin=(0, 0, 0), normal=(0, 0, 1), up=None)
sig: Frame.offset(d) -> Frame
sig: Frame.turn(rx=0, ry=0, rz=0) -> Frame
sig: Frame.move(x=0, y=0, z=0) -> Frame
sig: Frame.point(x=0, y=0, z=0) -> Vector
what: A frame is an origin and three axes, exposed as `.origin`, `.x`, `.y`, `.z`; `.normal` is its Z. Move, turn and offset return a new frame, leaving the original unchanged.
param normal: direction of Z; without up, X is parent +Z crossed with normal, or +X when normal is ±Z
param up: direction of Y, projected perpendicular to normal; cannot be parallel to normal
param d: distance along the frame's normal
param rx, ry, rz: turn about own axes, X then Y then Z, in degrees
param x, y, z: move along own axes; point instead returns those coordinates expressed in the parent space
toy: frames_axes | Red is frame X, green is Y, blue is Z. The arrows stand on the block's -Y face, shifted up from its foot.
limits: A Frame is not a point or an iterable of coordinates. Use f.origin or f.point(...). A Vector returned by point has neither .origin nor .turn. Frame operations preserve which part a frame was read on.
see: `ob.face`, `local`, `Frames`
param origin: (x, y, z) in program units, expressed in the space containing the frame.
:::

::: fiche Frames
sig: Frames(frames)
what: A list of frames with `.move`, `.turn` and `.offset` applied to every element in its own axes. Distributors return this type; you can also construct it from an iterable, including filtered sites.
param frames: Frame elements; indexing gives one Frame, slicing gives Frames
toy: dist_patterns | Grid, ring and phyllotaxis all return Frames; a single jitter call perturbs each list.
limits: Concatenation with frames and repetition preserve Frames. There is no collective point method: use each frame's point. On a ring, moving x moves radially because each frame's X points outward.
see: `Frames.jitter`, [Distributions](reference/distributions)
:::

## Read frames and paths from geometry {#geometry}

::: fiche ob.face
sig: ob.face(which) -> Frame
what: Read a named face, such as top, boss.top or cut, or the face furthest in a direction such as +Z. The origin is the parent space's origin projected onto the face plane, not the face's centre.
param which: maker's face name, or a direction in the space containing the part
limits: A named face selects its largest flat group; a curved named surface may refuse. A direction normally needs a face aligned within 1 degree; field surfaces can use their furthest facing facet. A group has no face: use bbox(group, "+Z") or a member's face.
see: [Example: On the -Y wall, frame X points right (+X), Y points up (+Z), and Z points out (-Y). The brass rim comes from the named top edge.](reference/frames#Frame), `bbox`, `ob.edge`
:::

On an unshifted vertical wall the face origin lies at its foot, Z=0. On a translated part it is still the projection of the containing space's origin, so it can lie outside the actual face. Use `bbox` for a side's centre.

A face frame's Z is the outward normal. If that normal is ±Z, its X is parent +X. Otherwise its X is parent +Z crossed with the normal, and Y completes the frame. Thus a face looking +X has frame X along +Y and frame Y upwards. Moving `y=` on a vertical face moves up the wall; moving `z=` moves out from it.

::: fiche ob.edge
sig: ob.edge(which) -> Path
what: Read the longest connected run of edges with a maker's name, already placed in the space containing the part. Feed it to wire for a rim, sweep for a section, or along for repeated parts.
param which: an edge name such as top, cut, a cut tool's name or plate.top; no geometric edge selector
limits: Equal-length runs choose the one reaching furthest -X, then -Y, then -Z. A closing run gives a closed path. Forks raise: name one loop or run. Missing names and paths too short to use also raise.
see: [Example: The brass wire follows block.edge("top"), a closed path around the top.](reference/frames#Frame), `wire`, `sweep`, `along`
:::

::: fiche bbox
sig: bbox(ob, which) -> Frame
what: Read a side centre, edge midpoint or corner of the bounding box of a part, group or assembly, including descendants. The box is aligned to the axes of the space containing the object.
param which: +X for a side, +X-Y for an edge, +X-Y+Z for a corner; each axis at most once, with a sign for each combined direction
toy: frames_placement | The cap's bottom anchor sits on the scaled peg's bounding-box top. The second peg is its mirror image.
limits: Frame orientation follows the first direction named: +X-Y and -Y+X give the same point with different axes. Empty groups have no bounding box. This is a box frame, not necessarily a point on the mesh.
see: `at`, `ob.face`
:::

::: fiche local
sig: local(ob, x=0, y=0, z=0, rx=0, ry=0, rz=0) -> Frame
what: Read a frame at numeric coordinates in a part's own space, rotated in degrees as at rotates. Use it for a pivot specified by xyz and rpy, without composing coordinates through a chain of parents.
param ob: part, group or assembly whose own coordinates define the pivot
limits: The returned frame is expressed in the part's parent space and remembers the part. Use the same frame for at(child, on=f) and joint(name, child, f, ...); joint does not place the child. Reread after scaling.
param x, y, z: Distances along the part's own X, Y and Z axes, in program units.
param rx, ry, rz: Rotations about the part's own X, Y and Z axes, in degrees, using XYZ Euler order.
see: [Example: The red marker is placed on local(base, y=depth/3, z=height), a pivot given by dimensions.](reference/frames#bbox), `joint`, `Frame`
:::

## Place and move {#place-and-move}

::: fiche at
sig: at(ob, x=None, y=None, z=None, rx=None, ry=None, rz=None, on=None, anchor=None, *, scale=None)
what: Set placement values, keeping those omitted, and return the placed result. Works on solids, groups, assembly handles, profiles, paths, and lists of them; always use the returned value.
param on: one frame, or a nonempty list of frames; a list consumes the prototype and returns one copy per frame
param anchor: point of the object's own bounding box to put at the destination; origin by default
param scale: scale about the object's own origin before placement and before reading the anchor; see below
limits: A list of objects cannot share one anchor: place them individually. Profiles and paths do not accept scale. A jointed part refuses placement changes: use transform for the whole mechanism or pose for its joint.
param x, y, z: Distances along the placement frame's X, Y and Z axes, in program units.
param rx, ry, rz: Rotations about the placement frame's X, Y and Z axes, in degrees, using XYZ Euler order.
see: [Example: A peg is scaled before placement; its cap uses a bottom anchor.](reference/frames#bbox), `transform`, `scale`, `grid`, `ring`
:::

An anchor accepts the same directions as `bbox`: `"-Z"`, `"+Y-Z"`, `"+X-Y+Z"`. Words map as follows: top +Z, bottom -Z, left -X, right +X, front -Y, back +Y. Combine them as `"top-front"` or `"bottom-left-back"`; `"center"` selects the box centre, `"origin"` the construction origin. The anchor selects a point, not an orientation. Giving it again rereads the box; omitted, its previously read point stays.

Assembly anchors are attributes, for example `at(flower, on=pot.rim)`. To repeat a part, pass `Frames` to `on=`. `hole` and `pocket` accept them too, applying once per frame.

::: fiche transform
sig: transform(ob, x=0, y=0, z=0, rx=0, ry=0, rz=0, mirror=None)
what: Move the whole placed object as though a parent around it moved. Translation uses the parent's axes; rotation is about the parent's origin, not the object's centre. The placement changes, not the mesh.
param mirror: coordinates whose signs reverse, such as x or yz; x reflects across the parent's x=0 plane
limits: Mirror acts before rotation and translation. Jointed parts move with their pivots, and mirrored motion is mirrored too. A later at(x=...) uses the transformed frame; at(on=...) replaces it. Frames use their own move, turn and offset instead.
param x, y, z: Distances along the parent's X, Y and Z axes, in program units.
param rx, ry, rz: Rotations about the parent's X, Y and Z axes, in degrees, using XYZ Euler order.
see: [Example: transform(copy(peg), mirror="x") preserves the first peg and creates its opposite.](reference/frames#bbox), `copy`, `at`
:::

## Scale before reading attachments {#scale-before-placement}

A solid accepts one scale factor or an `(sx, sy, sz)` tuple. A group or assembly handle accepts one positive factor. With frame-list placement, a number or numeric three-tuple applies to every copy; a **list** supplies exactly one factor or axis tuple per frame. Use a list even for three sites. With one frame or no frame, give one scale value.

`scale(group, s)` scales all descendant meshes and their positions about the group's origin, leaving the group where it stands. Turns, materials, smoothing and vertex and face counts stay; the new size is baked into meshes and child positions, not stored as a new object scale. A later `at` on a member keeps its scaled placement, with newly supplied lengths still in program units. Scaling a solid changes its mesh about its own origin, including per-axis scaling, and does not move its children. Scaling is multiplicative: a second scale factor acts on the already scaled mesh.

Previously read frames, frame lists and assembly anchors do not follow scaling; numeric anchors remain unchanged. Read faces, `bbox` and `local` again afterwards, or rebuild the assembly's anchors. A group cannot be scaled if it contains or is carried by a jointed part, or if an outside joint hangs on or follows it. Scale before declaring joints, or build at size.

For circular paths use `arc(r=r)`. A ring's jittered origins can make an irregular planar `poly`; see [Jitter](reference/distributions#Frames-jitter). For an organic blob, extrude or loft `superellipse` sections, then displace at the outline's scale before adding fine grain.
