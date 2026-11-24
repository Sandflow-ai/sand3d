---
title: Writing an assembly
order: 3
lead: Put the plan first, then the details, then the part builders. Each part has its own dimensions and origin; the head explains how they belong together.
---

## 1. Make the head a table of contents {#head}

The first function is named after the object. It calls part builders, places their results and returns `assembly`; it does not build geometry. Runners call this first function. Keep module-level code to imports and function definitions; a separate runner performs export.

A picnic table's head should read as tabletop, end frame, mirrored frame, benches. A turnstile head should show the frame, rotor and pawl with their pivots beside them. Extrusions buried in the head hide this plan and make parts harder to remove or reuse. Details that remain optional can hang from an assembly with `attach`.

The chair separates a plan, published anchors and removable details. Delete its `add_back` call and the same plan makes a stool.

::: scene start_chair
title: Chair: plan, details, parts
program: docs/examples/chair.py
note: Four legs and a seat establish the plan; the back and rails are attached afterwards. The render adds a fallback material.
:::

## 2. Write one function per distinct part {#parts}

Build each part about its own origin. Parameters express what differs; return one object. Three differently sized levers should call one lever builder. A seesaw's matching crossrails should share one builder, with a mirrored copy for the opposite end, rather than duplicate six lines under two names.

| How the pieces belong together | Use | Result |
|---|---|---|
| Fused permanently | `join` | One solid with the first object's material |
| Separate but moving together | `group` | Each keeps its mesh and material |
| Moving relative to one another | `joint` in the head | Parts connected through parent frames |

`assembly` adds published anchors to a top-level group. A lone solid needs no wrapper group. Return it at its origin: if its builder places it at z = 50, a later `at(..., z=100)` resets it to 100. A child inside a group retains its 50-unit offset when the group goes to 100, reaching 150. Choose this hierarchy deliberately.

The lamp publishes a `head` anchor so its shade can be attached without rebuilding the stand.

::: scene start_lamp
title: Lamp with an attached shade
program: docs/examples/lamp.py
note: The stem stands on the base's top face. The shade attaches at the published head frame. The render adds a fallback material.
:::

## 3. Name each dimension once {#dimensions}

Put main dimensions in keyword arguments, in millimetres unless the program selects another unit. Write a measured value once and derive dependent values as expressions. A freezer's cavity and rim cuts should follow width, depth, height, wall, lip and slot dimensions; unrelated heights and widths break when the cabinet changes size. A collar's taper should have its own dimension, not borrow the base's fillet radius by accident.

Target 15 numeric literals per part, with a ceiling of 40. Count defaults too; exclude 0, 0.5, 1, 2, 45, 90, 180, 270 and 360. Read every argument you declare. Avoid special cases such as `if x == 28` and unexplained fractions that work only for the current measurements. Accept a slightly less exact match if fewer independent numbers make the model coherent. A joint origin copied from a source such as URDF is also a measurement: name it once.

The bracket is a small example: width, depth, thickness, hole diameter and pitch describe its purpose.

::: scene start_bracket
title: A parameterized plate
program: docs/examples/bracket.py
note: The hole pitch is a dimension, not two unrelated hole coordinates. The render adds a fallback material.
:::

## 4. Place each part once in its parent's frame {#placement}

The head places top-level parts with `at`. Part functions place their own children. Derive a placement from a dimension when that is the relationship; use a face, `bbox` or `local` frame when contact or attachment is the relationship.

A lamp stem should stand on its base, rather than use two unrelated measured world heights. A bowl on a stem uses the stem's height. An eyeglass arm should be drawn in its own frame, not as world-coordinate spline points with the head's translation subtracted from every point. See [Frames and placement](reference/frames).

## 5. Repeat with frames and mirror a copy {#repeat}

Use `on=grid(...)`, `ring(...)` or `along(...)` for repeated placements. Use `transform(copy(placed), mirror="x")` for the opposite side of a pair. `at` sets a place; `transform` makes the mirror image. Do not reconstruct rings with sine and cosine in a placement loop.

Three bunk-frame posts at -233, -140 and -47 hide a pitch of 93. Name the pitch and use a three-site grid centred at -140 instead. The rack shows both repetition and mirroring:

::: scene start_rack
title: A rack from one grid and one mirror
program: docs/examples/rack.py
note: The peg prototype is consumed by frame-list placement. The returned list can go directly into join. The render adds a fallback material.
:::

## 6. Use the verb that names the shape {#vocabulary}

Do not replace a named operation with a coordinate table. Assembly programs use neither `bpy` nor `bmesh`. A free form without a matching verb may still need points.

| Shape | Expression |
|---|---|
| Rotational body | `revolve(name, profile)` |
| Hollow open solid | `shell(ob, t=wall, open="top")` |
| Bore or bolt circle | `hole(ob, d=diameter, on=frames)` |
| Bent tube | `wire(name, path, d=diameter, fillet=radius)` |
| Changing cross-section | `loft(name, station(...), ...)` |
| Long body drawn from views | `body(name, plan, top, bottom)` |
| Band following a path | `stroke(path, thickness)` |

A `station` describes height, width, depth, x/y offset and squareness `n`: 2 for an ellipse, 4 for a rounded box. A few stations describe a taper, bulge or drift. A nail shaft can be three named sections; a tray is a box shelled open at the top. For a soup bowl, describe the outer profile and shell the revolved solid, rather than type a second inner curve point by point.

::: scene start_cutlery
title: Spoon and fork
program: programs/cutlery.py
note: Two builders share a lofted handle. The spoon is hollowed; the fork intersects a slotted head with a curved plate. The render wrapper calls both builders, separates them along Y and adds a fallback material.
:::

## 7. Give visible parts materials {#materials}

When appearance matters, assign each part a material and colour once, before repeating it. Shape-only CAD data can omit materials. On a group, `material` reaches descendants without their own material; the nearest material assignment wins.

`join` keeps the first object's material. Join only what should share one colour; use `group` to preserve separate materials. A row of oak planks should receive its material before the grid creates copies. See [Materials and media](reference/materials).

::: scene start_tufted_chair
title: Tufted chair with removable trim
program: programs/tufted_chair.py
note: Lofts describe the seat and back, dents form the tufts, and anchors carry buttons and rows of nails. This repository example is shape-only; the render adds a uniform fallback material, not an upholstery material scheme.
:::

## 8. Reuse one frame per joint {#joints}

Keep the parent frame, placed child and joint together in the head. For a numeric source pivot, read `f = local(parent, x, y, z, rx, ry, rz)` once. Use it in both `at(child, on=f)` and `joint(name, child, f, ...)`. Each moving part can then be removed with its own lines.

`local` works in the parent's own space even deep in a chain. Do not compose source coordinates into world coordinates. A source joint axis must first be turned by its source roll, pitch and yaw; direction-string joint axes use the space the parent lives in. Check the sign with the right-hand rule: a correct pivot with the wrong axis sign can open a door into its cabinet.

Fixed details need no joint. Put them in the moving parent's group before declaring its joint, or they can stay behind. Return mechanisms at rest, every joint at zero, with no `pose` in the builder. Unjointed parts have nothing to pose. The gate example is an explicit demonstration exception: it poses one leaf to show the swing.

A sliding cabinet lid and its hatch illustrate a chain: the two lids use frames on the cabinet and opposite slide axes; the hatch uses a frame read on its moving lid. A rotary spindle must use the same pivot for placement and movement, rather than two nearby frames.

::: scene start_gate
title: Mirrored hinged leaves
program: docs/examples/gate.py
note: The second leaf copies the first leaf's joint, then mirrors the part and pivot. One leaf is posed to 60 degrees for this demonstration. The render adds a fallback material.
:::

See [Articulation and assembly](reference/assembly) for the complete joint API.

## Natural forms {#natural}

### Separate random streams {#seeds}

Use one derived seed per call. Two `vary` calls with the same seed replay the same stream, so the longest leaf also becomes the widest. Use `seed + 1`, `seed + 2`, or `seed * 100 + k` for part k, including calls to `jitter` and `scatter`.

For conditional draws in a loop, such as rejections, choices or colours, create one `random.Random(seed + k)` per part. Keep draw order stable. Use a declared seed parameter or leave it unused; do not hide it with `_ = seed`. A root with `seed=0` defines the reproducible build.

### Shape the outline before the skin {#outline}

Small noise on a symmetric base gives a rough regular shape. First change proportions and silhouette: uneven hull points, varied lengths, a bend, twist or taper, or displacement with features as large as the part. Then add fine grain with a different seed. Inspect the outline before increasing sampling.

### Grow organs from their attachment {#organs}

`along` points frame Z along a curved stem's tangent; cylindrical `phyllotaxis` points it radially outward. Spin around the tangent before leaning away. A subsequent `turn(ry=60)` departs 60 degrees from that tangent.

Build each organ from its base at its origin, along its own +Z. A sweep scale law `[(0, 0), (.35, 1), (1, 0)]` puts its first pole at the attachment. Angular jitter preserves the root; positional jitter detaches it.

::: scene start_curved_stem
title: Leaves on a curved stem
program: docs/examples/curved_stem.py
note: Tangent frames spin before they lean. Angular jitter and independently varied lengths keep each leaf's base on the stem.
:::

### Derive contact from geometry {#contact}

Attach to the actual parent with a face, `snap`, or the final frame of `along(path, count=2)`. Do not measure offsets from a render: attachment must survive changes of seed. Compose frames with `on=`, not translations added across rotated parents. Keep local callback coordinates, sampled sites in the sampled mesh's parent space and world positions distinct.

::: scene start_pond
title: A pond filled against its banks
program: docs/examples/pond.py
note: The lawn is cut first, then filled to a level. The returned water follows the container rather than a separately measured shoreline. The render uses a 25 mm swell and sky lighting so the water surface is visible.
:::

### Select sites once {#sites}

Filter sampled frames with one predicate. Pass every kept site through one placement helper shared by populations such as stones and plants. Use the count that remains, not the requested sample count. For example, a terrain filter can keep frames above a height and outside a circular clearing before enumerating the retained sites and deriving one seed per stone.

### Put repeated stages in a table {#stages}

Leaf tiers, flame layers, smoke columns and layered fungi should use one loop over a parameter table, with a derived seed per item. Store height, scale and rotation together. Refactoring must preserve table order, random draw order and fusion order.

### Dress every component and respect resolution {#natural-materials}

Natural forms require materials. Give flesh, stalk and seeds their own assignments; likewise leaf blades and veins. Use natural presets with explicit colours for the intended mood.

For low-poly work, `facets(n, smooth=False)` reaches field, displace and blend surfaces too; a hull follows its input points. Low-poly is not finer geometry with noise painted on it. Preserve intentional angular silhouettes, raise n if a branch or hole disappears, and use `facets("auto")` to restore adaptive resolution. A face budget is a ceiling, not a target. See [Resolution](guides/resolution).

## A larger plan with optional details {#weight-stack}

::: scene start_weight_stack
title: Weight stack
program: programs/weight_stack.py
note: The plate column publishes anchors for bumpers, guide rods and selector. Each detail can be removed independently. The shape-only source receives a fallback material in the render.
:::
