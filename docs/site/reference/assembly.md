---
title: Articulation and assembly
order: 8
lead: Build parts at rest, place them, then declare their motion. Groups organise parts; joints describe which part carries which.
---

## Place first, declare motion second {#motion}

A joint does not align or move its child. Use `at` to put the child where it rests, then declare the joint. Every joint starts at zero. Build and declare the whole mechanism at rest before posing it.

The frame `on` identifies both the pivot and the parent. Read it from that parent with `ob.face`, `bbox`, `local` or an assembly anchor. Its parent identity survives `.move`, `.turn` and `.offset`. Never read it on the moving child or one of that child's descendants. A bare `Frame` has no parent; publish it as an assembly anchor first.

For a pivot supplied as xyz and roll, pitch, yaw, use `local(parent, x, y, z, rx, ry, rz)`. These coordinates are in the parent's own frame. `at(child, on=pivot)` places there; `joint(..., on=pivot)` declares motion there.

::: fiche joint
sig: joint(name, child, on, kind="revolute", axis="normal", range=None, follows=None, ratio=1)
what: Declare how a solid, group or assembly moves on another part. Returns the child without moving it.
param name: Nonempty joint name; use distinct names when posing through an assembly.
param child: The moving part, group or Handle.
param on: Frame read on the parent, with its origin at the pivot.
param kind: revolute, continuous, prismatic or free; see the table below.
param axis: normal means the frame's Z; a signed axis is in the space the parent lives in.
param range: Ordered (low, high) containing zero, degrees for a revolute joint, program units for a slide.
param follows: A child with one joint, or a joint name; this joint follows that value.
param ratio: Nonzero multiplier of the leader's value, default 1.
toy: asm_chain | Two links: the second joint is read on the first link, so the elbow travels with the shoulder.
limits: Cyclic mechanisms are refused. Multiple joints on one child must share a parent. Declare joints at rest.
see: `pose`, `local`, `seat`
:::

### Axes and signs {#axes}

`axis="normal"` follows the pivot frame's Z, including its turns. `axis="+Z"` means Z of the space containing the parent, not necessarily Z of the parent's own mesh. A positive slide travels along the axis. A positive turn obeys the right hand: about +Z, +X turns toward +Y.

On a face looking +X, frame X points +Y and frame Y points up. A door hinged at that face's -Y edge opens outward about **-Z**.

### Four kinds {#kinds}

| Kind | Motion | Range | Pose value |
|---|---|---|---|
| revolute | Rotation about the pivot | Required, contains 0 | Degrees |
| continuous | Unlimited rotation | Forbidden | Degrees |
| prismatic | Translation along the axis | Required, contains 0 | Program units |
| free | Unconstrained connection | Forbidden; omit axis too | No scalar pose |

A follower takes its limits from its leader and ratio, so it takes no explicit range. Free joints cannot follow. A slide cannot follow an endless turn: use a bounded revolute leader.

::: example asm_kinds
note: Left to right: bounded turn, endless turn, lifted slide, free connection at rest. The last connection is export metadata, not a scalar animation.
:::

::: fiche pose
sig: pose(ob, value, joint=None)
what: Set a mechanism's state and move everything it carries. Returns ob; zero restores rest, and setting a value is absolute, not an increment.
param ob: Jointed child, or a group or assembly containing the named joint.
param value: Finite number, in degrees for turns or program units for slides.
param joint: Required when the child has several joints or the joint is under a group or assembly.
limits: Values outside the range raise. Pose the leader, not its follower; a free joint has no scalar value. Copied joint names can be ambiguous under an assembly: pose the copied part itself.
see: `joint`, [Posed two-link example](reference/assembly#joint)
:::

The examples below show chosen poses. To inspect another state, change the pose value in Python and rebuild; the embedded model viewer rotates the view, not the joints.

## Chains, groups and copied motion {#chains}

In the arm toy, posing the shoulder carries the elbow and second link; posing the elbow changes only the second link relative to the first. A part without a joint moves with its group. A jointed part follows its joint regardless of its organisational group. Joints may be declared before or after `group` or `assembly`.

`copy` keeps the joints and their original parent. `transform` moves a jointed part together with its pivot. A mirrored part moves as the mirror image of the original motion, including the rotation sign. `at` refuses a jointed part; finish placement first or use `transform`. Scale groups before declaring joints: scaling groups involved in a mechanism is refused.

::: example asm_mirror
note: The copied gate leaf keeps its hinge parent. Mirroring moves the copy and pivot together; both leaves open toward the same side at positive 25 degrees.
:::

## Coupled motion and a screw {#coupling}

`follows` links values, not positions: follower value = leader value × ratio. A negative ratio reverses motion; magnitude 2 doubles it. Between kinds, ratio has units: degrees per program unit, or program units per degree. A follower may name a leader child with one joint or name a specific joint.

::: example asm_follow
note: The orange leader turns 30 degrees; the blue follower turns -60 degrees through ratio=-2. Only the leader is posed.
:::

Two joints on the same child compose in declaration order. A screw uses a bounded turn, then a slide following that turn with `ratio=pitch / 360`. One full turn advances one pitch. Name the turn in `pose`, since the child has two joints.

::: example asm_screw
note: A 20 mm pitch gives 15 mm travel at 270 degrees. The transverse bar makes rotation visible; the gap above the base shows travel.
:::

::: fiche seat
sig: seat(host, part)
what: Remove from host the volume occupied by part at rest, leaving part untouched. Returns the modified host even when the mechanism is currently posed.
param host: Solid to cut.
param part: Solid, group or assembly whose rest volume cuts the host.
toy: asm_seat | The brass insert is raised before seat is called. The socket is still cut where the insert rests.
limits: No shared volume at rest raises. The host cannot be the part or lie inside it. This cuts a seat, not the swept clearance through the entire motion.
see: `cut`, `pose`
:::

## Build an assembly that publishes anchors {#architecture}

Write the plan first, then optional details, then the part functions. The plan publishes dimensions and frames once. A detail reads those anchors and attaches its children; removing that detail's call should remove only the detail. Parts build at their origin; their caller places them.

::: fiche group
sig: group(name, *children)
what: Create a parent object for children, keeping their placements in its frame. The children stay separate meshes; this is not a boolean union.
param children: Parts or lists, flattened to their elements.
limits: A group has no mesh faces: group.face raises. Read bbox(group, "+Z") or a child part's face instead.
see: `assembly`, `join`, [Lamp group example](reference/assembly#Handle)
:::

::: fiche assembly
sig: assembly(name, *children, **anchors)
what: Group the main parts and return a Handle publishing named anchors. Use attributes such as machine.front or lamp.head to place details.
param anchors: Dimensions, points, frames or lists of frames needed by details.
limits: Frames captured before scaling do not follow scaling; reread faces, bbox and local, or rebuild anchors afterwards. Numeric anchors are not rescaled.
see: `Handle`, `attach`, [Gate example](reference/assembly#gate)
:::

::: fiche Handle
sig: Handle(root, **anchors)
what: Wrap an existing root and publish anchors as attributes. assembly constructs the group and this wrapper together; Handle lets you wrap a root already built.
param root: Root object, available as handle.root.
param anchors: Named values; a hand-built frame, or list of such frames, becomes read on this root, allowing joints to hang on it.
toy: asm_details | A lamp publishes head once. Its shade attaches there, inherits the assembly structure, and overrides the brass material.
see: `assembly`, `local`
limits: Anchors are captured values. They do not update after scaling; reread frames or rebuild the anchors.
:::

::: fiche attach
sig: attach(handle, name, *children)
what: Group a detail's children under handle.root and return the detail group. Children are already placed in the handle's frame: attach does not place them on an anchor.
param handle: Handle receiving the detail.
param name: Name of its new group.
param children: Placed parts or lists of parts.
see: `at`, `Handle`, [Attached shade example](reference/assembly#Handle)
limits: Children must already be placed in the handle’s frame; attaching does not align them to an anchor.
:::

## Worked example: a gate {#gate}

::: scene start_gate
title: A mirrored gate
program: docs/examples/gate.py
note: The hinge frame is read on the post. Mirroring the leaf preserves the joint on the opposite side.
:::
