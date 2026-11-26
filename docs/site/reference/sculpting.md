---
title: Sculpting and bodies
order: 10
lead: An organic shape is worked like clay. Build its masses first, then work them by places along a solid's spine, never by points. A body is flesh made of fused pieces, skinned to bones and posed.
---

## Places on a spine {#places}

Every solid has a spine, its own axis. A `body` runs from -Y to +Y, `sweep` and `wire` follow their path, and `loft` passes through the centres of its sections. Any other solid uses the longest side of its own box. `scale`, `bend`, `twist` and `taper` move the spine with the surface.

::: fiche spot
sig: spot(ob, u, side=None)
what: A frame on the spine at `u`, measured by length from 0 at its start to 1 at its end. Without a side, the frame lies on the spine with its Z along it. With a side, it lies where the surface is met going that way from the spine, its Z pointing that way: the belly, the back, a flank.
param ob: The solid to read.
param u: A number from 0 to 1 along the spine.
param side: A direction in the space `ob` is in, named as `bbox` names them ("-Z", "+X+Z"), or (x, y, z). A side along the spine ("+Y" on a body at u = 1) meets the tip.
limits: Read it again after an edit that moves the surface; a frame already read does not follow.
:::

::: fiche describe
sig: describe(ob)
what: A text card of the solid in millimetres: its own box, where its spine runs, and at u = 0, 0.1 … 1 how far the surface is from the spine across it. Read it against a target's measures to see where a `grab`, an `inflate` or a `pinch` is due, and at which u.
param ob: The solid to describe.
:::

## Sculpting {#sculpting}

The sculpting verbs change a solid in place and return it. `on` is a frame from `spot`, a point, or a list of them, in the space `ob` is in. Their effect is full at the centre and fades to nothing at `r`. On a spot on the spine, they work the whole ring there, `r` along the spine each way.

::: fiche grab inflate pinch relax
sig: grab(ob, move, r, on)
sig: inflate(ob, by, r=None, on=None)
sig: pinch(ob, by, r, on)
sig: relax(ob, r=None, on=None, passes=3)
what: `grab` moves the surface by `move`, an (x, y, z): a snout drawn out, a back arched. `inflate` moves it along its normals by `by`, out or, below 0, in: a belly, cheeks. `pinch` draws it toward the spine by `by`, never past it: a waist, a neck, a wrist. `relax` evens out bumps and seams, `passes` times; the seam a `join` leaves becomes a fillet.
param ob: The solid to change.
param move: An (x, y, z) in the space `ob` is in.
param by: A length; below 0, `inflate` hollows and `pinch` swells.
param r: The distance at which the change fades to nothing. Without `on`, `inflate` and `relax` work the whole surface; `relax` then uses a tenth of the solid's size unless `r` is given.
param on: Where to work; see above.
limits: They move existing vertices: a solid with few sections has little surface to move between them. Remake it with `clay` first.
:::

::: fiche crease stamp
sig: crease(ob, path, depth, r)
sig: stamp(ob, profile, depth, on, soft=None)
what: `crease` presses a fold along a path over the surface, `depth` deep on the line and nothing at `r` from it: a wrinkle, the line between two muscles, a lip. Below 0 it raises a ridge. `stamp` lays a profile on each frame of `on` and raises the surface under it `depth` along its normals: scales, warts, nostrils, the pads of a paw. Below 0 it sinks it.
param path: Frames or points joined by a smooth curve, or a path such as a `spline`; each point is taken to the nearest surface.
param profile: A closed profile: `circle`, `rect`, `poly`…, laid square to each frame's Z.
param soft: How far the edge of a stamp is softened; a quarter of the profile's size by default.
limits: A stamp only reaches the surface facing its frame's way.
:::

::: fiche clay
sig: clay(ob, *others, detail=None)
what: Remake `ob`, and others fused into it, as one closed surface of even faces about `detail` across, as a sculptor's remesh does. Overlapping parts become one mass with no seam inside, and the sculpting verbs find surface to move everywhere.
param ob: The solid to remake; it keeps its name, placement, material and spine.
param others: Solids or lists of solids to fuse in; they are used up.
param detail: The edge length; by default the diagonal of their box divided by 150.
limits: Faces and edges lose their names.
:::

## Anatomy {#anatomy}

::: fiche skeleton muscle
sig: skeleton(**joints)
sig: muscle(name, a, b, belly, flat=1.0, side=None, peak=0.5, bow=0.0)
what: `skeleton` names joints, read back as `bones.elbow`; `bones.mirrored("x")` gives the other side's. A `muscle` is a spindle between the two places it attaches, thick `belly` at its widest, `peak` of the way along, rounded to nothing at both ends. Its spine runs from `a` to `b`.
param joints: Points or frames by name.
param a, b: Points, joints or frames.
param flat: Below 1, flattens the section toward `side`: a pectoral lies flat on the chest with `flat=0.4, side="-Y"`.
param side: A direction square to the muscle: "+Y", "-X+Z" or (x, y, z).
param bow: Pushes the belly that far toward `side`, off the line between its ends.
limits: A muscle is placed by its two ends, never by a rotation.
:::

## Flesh {#flesh}

A body's flesh is the surface of fused pieces. The pieces are fields, not meshes: `fuse` joins them and `flesh` makes their surface.

::: fiche stack limb lobe spindle
sig: stack(name, stations, cap=None)
sig: limb(name, joints, sections, up="+Y")
sig: lobe(name, centre, radii)
sig: spindle(name, a, b, sections, up="+Z")
what: `stack` is a trunk read at a few heights. `limb` is one piece along a smooth curve through its joints, with no ring at a joint. `lobe` is an ellipsoid: a skull, a muzzle, a shoulder's cap. `spindle` is a straight tapered piece: a foot, a hand.
param stations: Rows (z, width, depth, y, n, taper): at each z its width along X and depth along Y, centred at y, a superellipse of exponent n, taper narrowing its +Y side. Every number follows a smooth curve between rows.
param cap: How far the two ends of a stack are rounded; 14 mm by default.
param joints: Points, joints or frames the limb passes through.
param sections: For a limb, rows (distance along it, half-width, half-depth). For a spindle, rows (share of the way from a to b, half-width, half-depth, n).
param up: The direction of the half-depth, carried along without twisting.
param centre, radii: A lobe's centre, and its radii along X, Y and Z, or one number for a ball.
:::

::: fiche fuse flesh
sig: fuse(*pieces, r, wide=None)
sig: flesh(name, *pieces, cell=None, soften=None, box=None, crisp=None)
what: `fuse` joins pieces with a smooth union: a crease `r` across is rounded over, and pieces further apart than `r` stay apart. `flesh` makes one closed smooth mesh where the pieces' field crosses zero, its faces named `flesh`.
param r: The radius of the union.
param wide: (point, r2, near, far): a radius `r2` within `near` of a joint, falling back to `r` at `far`.
param cell: The grid's step; 1.5 mm by default. Detail under two or three cells is lost.
param soften: How far the field is blurred before the surface is taken; 2 mm by default.
param box: ((x0, y0, z0), (x1, y1, z1)), the grid's extent; the pieces' own with a margin by default.
param crisp: [(point, near, far), ...]: the field is left sharp within `near` of a point, so that fingers a few cells apart stay apart.
limits: Several pieces given to `flesh` are fused with r = 3 mm; `fuse` them first to choose.
:::

## Bones and postures {#bones}

::: fiche band chain rig
sig: band(bone, lo, hi, normal=None, carry=(0, 1), twist=None)
sig: chain(pieces, first, *bands, whole=None, share=None)
sig: rig(ob, joints, bones, *chains, linear=None, smooth=None, seam=None)
what: `rig` binds a body made by `flesh` to bones. Each group of pieces follows a `chain`: its first bone, then a `band` for each next one, where the skin passes from the bone before to `bone` between `lo` and `hi` of its joint. Nothing moves until `posture`.
param bones: {name: (joint, joint, parent)}; the root's parent is None, parents come before their children.
param lo, hi: Distances from the bone's head joint, along `normal`. For a trunk give `normal="+Z"`: the bands are heights.
param carry: The stretch of the chain's first piece the bone holds when a posture presses parts together, in shares of its length.
param twist: (bone2, a, b): `bone2` follows this bone without its twist, the skin passing from one to the other between shares a and b.
param whole: {piece: bone}: a piece held entire by one bone.
param share: [(bone, of, joint, amount, near, far)]: `bone` takes `amount` of `of`'s skin round a joint.
param linear: [(bones, bones)]: where the skin is shared between the two sets, as at an armpit, it is blended linearly instead of with dual quaternions.
param smooth, seam: How far the weights are smoothed; 3.5 mm, and (22, 36.5) mm at a linear seam, by default.
:::

::: fiche posture detail
sig: posture(ob, aim=None, turn=None, root=(0, 0, 0), press=True, floor=None)
sig: detail(ob, offsets)
what: `posture` poses a rigged body from its rest pose, never from the last posture; children follow their parents. `detail` adds what flesh cannot say, fitted from a scan or a sculpture: one offset per vertex of the mesh `flesh` made. The bones carry it.
param aim: {bone: direction}: a bone pointed along a direction of the world, swung the shortest way.
param turn: {bone: [(axis, degrees), ...]}: turns on its joint in its parent's rest frame, the first applied last. A knee is `[("x", 80)]`.
param root: Moves the whole body, to sit it down.
param press: Where a posture pushes one part into another, both skins are pressed back to meet half-way. False leaves them through one another.
param floor: A hard floor at that height.
param offsets: (x, y, z) per vertex, or a .npy file of them. Calling it again replaces the layer.
limits: The same program makes the same flesh vertex for vertex, so a layer stays valid while the pieces, cell and box do not change.
:::
