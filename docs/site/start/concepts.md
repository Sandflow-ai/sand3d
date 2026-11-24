---
title: Concepts
order: 2
lead: A program creates named parts in their own frames, edits them, then places them in an assembly. These rules explain how the pieces fit together.
---

## Names, units and repeatability {#basics}

Use `import sand3d as s3d`. Makers take a name and return a solid; edits return the edited object. Keep the returned value, especially when an operation replaces or consumes its inputs. Profiles and paths describe geometry for makers; they are not scene solids.

Lengths are millimetres by default. Call `s3d.units("cm")` or `s3d.units("m")` before the first modelling verb to use another unit. Export converts lengths to metres. Library absolute tolerances are defined in millimetres and converted into the program's unit.

Every public verb is deterministic: two fresh processes with the same inputs produce the same mesh. Keep seeds explicit and draw order stable. This is a reproducibility contract within the same environment, not a promise of identical digests across Blender versions or platforms. Programs may use NumPy, but do not depend on Blender's active object or selection.

## Faces and edges have names {#names}

Use the names the maker gave them: `top`, `bottom`, `side`, `rim`, `seam`, `start`, `end`, `cut`, tool names or qualified names such as `plate.top`. Names depend on the maker: sweep and loft caps are `start` and `end`. A planar face can also be read by direction, for example `part.face("+X")`. Edges have no geometric selectors: use their names.

`part.face(...)` returns a frame; `part.edge(...)` returns a path. See [Frames and placement](reference/frames) and the creating verb in [Solids](reference/solids) for details.

## Placement sets values {#placement}

A placement combines a frame and values along its axes. `at` sets only the values you supply, keeping the others. Calling `at(part, z=50)` and then `at(part, z=100)` puts it at 100, not 150. Supplying `on=` changes the frame; x, y and z then follow that frame's axes. Always use what `at` returns.

`transform` moves the whole object as a parent would, including a mirror image. For a symmetric pair, place one part and use `s3d.transform(s3d.copy(part), mirror="x")` for its partner. See [Frames and placement](reference/frames).

## Repeat with frames, pass lists of parts {#lists}

A list of frames passed to `on=` repeats an operation once per frame. `at` consumes the prototype and returns a list of copies; `hole` and `pocket` repeat their cuts. Distributors such as `grid`, `ring` and `along` construct those frames.

A list of objects stands for its elements wherever a verb accepts objects. The rack scene uses `join(base, pegs, hook, image)`: `pegs` is the list returned by `at`, without a separate join loop.

::: scene start_rack
title: Repeated pegs and a mirrored hook
program: docs/examples/rack.py
note: One grid places the pegs; a copy mirrored across X supplies the second hook. A second grid locates the mounting holes. The render adds a fallback material.
:::

See [Distributions](reference/distributions) and [Edits](reference/edits).

## Consumed inputs are gone {#consumption}

A boolean tool is used up by the operation. `join` fuses the other parts into its first part; those other objects no longer exist. Frame-list placement also uses up its prototype. Use `copy` before the operation if the original must survive. Do not keep editing a reference to a consumed object.

## Origins and face axes {#origins}

Primitive solids such as `box`, `cylinder` and `sphere` stand on z = 0, centred in x and y. `box` is the extrusion of its rectangle; `extrude(..., both=True)` instead centres the thickness on the profile plane. Geometry supplied as coordinates retains those coordinates: a hull, wire, loft or revolved profile need not start at z = 0.

A face frame starts at the projection of the **parent-space origin** onto the face plane, not the face's centre. For a vertical face this is at z = 0 in that space, even if the part was raised. Its Z axis is the outward face normal. On a ±Z face its X axis is +X. Otherwise X is the cross product of parent-space +Z with the normal. Y completes the frame.

Thus a face looking +X has local X along parent +Y, local Y up, and local Z along parent +X.

::: example start_face_axes
note: The +X face's frame starts at its foot. Red is frame X (parent +Y), green is frame Y (up), blue is frame Z (out of the face). The lines show positive directions from their shared origin.
:::

`bbox` locates bounding-box points on parts or groups: `"+X"` is a side centre, `"+X-Y"` an edge midpoint and `"+X-Y+Z"` a corner. Its axes face the first direction named. Unlike a face frame, the side centre is halfway up the box.

`at` accepts the same direction strings as its `anchor`: that point of the object's box lands at the placement. Word aliases are top = +Z, bottom = -Z, left = -X, right = +X, front = -Y, back = +Y. See [Frames and placement](reference/frames).

## Joints describe movement {#joints}

Place the child first. `joint` does not place it; it records how it moves on the part from which `on` was read. Read that frame using a parent's face, `bbox`, `local` or an assembly anchor. It retains its parent through `.move`, `.turn` and `.offset`. Never read it on the child itself.

For a numeric pivot, `local(parent, x, y, z, rx, ry, rz)` expresses position and rotation in the parent's own space. Reuse that frame for placement and the joint. An axis string such as `"+Z"` is in the space the parent lives in; `"normal"` uses the pivot frame's Z axis.

Positive values slide along the axis or rotate by the right-hand rule. Around +Z, +X turns toward +Y. A door hinged on the -Y edge of a +X face opens outward around -Z. The range must contain zero; a follower derives its range from the joint it follows.

Build at rest, with every joint at zero. `pose(child, value)` then moves the mechanism. An unjointed part follows its group; a jointed part follows its joint regardless of its group. Joints may be declared before or after `group` or `assembly`.

`copy` copies a part's joints, attached to the same parent. `transform` moves the part and its pivot together; a mirrored part has the mirrored motion. `at` refuses a jointed part. Two joints on one child compose in declaration order: a screw can combine a turn and a following slide with `ratio=pitch / 360`.

See [Articulation and assembly](reference/assembly) for joint kinds, followers and posing.
