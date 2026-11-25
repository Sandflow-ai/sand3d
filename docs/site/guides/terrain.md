---
title: Terrain and ground
order: 4
lead: Start with a solid support, shape its top, then sample that surface to place its cover. Stones, leaves, snow and dunes should belong to the ground beneath them.
hero: terrain_dunes
---

## A first patch of ground {#ground}

::: example terrain_stones
note: A supported solid with displaced top faces. Stones sit on samples of the resulting mesh, including its slopes.
:::

Make the terrain wide enough to carry its subject. Displace its top faces and keep the underside flat; avoid hidden floating islands beneath props. [displace](reference/edits#displace) explains the sampling step and face restriction.

## Seat objects on the actual surface {#contact}

Never calculate a stone's landing height from the noise formula that shaped the terrain. Refinement, smoothing and earlier edits can change the surface. Sample the mesh itself instead.

1. Ask [scatter](reference/distributions#scatter) for about ten times the number of sites you want, within its 4096-per-call limit. It samples the whole closed surface, including the sides and underside.
2. Filter by `f.normal` for slope and `f.origin` for position. For a maximum slope angle, require `f.normal.z > math.cos(math.radians(steepest))`; a test such as `abs(f.origin.y) > channel` keeps a channel clear.
3. Count the survivors, then take the number you need. Vary sizes with a separate seed.
4. Place each object with `at(ob, on=site)`. It stands along the site's local normal. `site.offset(-d / 4)` sinks it a quarter of its size into the ground.

A flat piece needs surface contact across its width: use `lay(at(leaf, on=site), ground)`. To place something at a chosen horizontal position, `snap(ground, [(x, y, above)], direction="-Z")` finds the surface below it. Construct `Frame(hit.origin)` from the hit if a post must remain upright instead of following the slope. See [lay](reference/edits#lay), [snap](reference/distributions#snap) and [Frame](reference/frames#Frame).

## Leaf litter {#litter}

Covers belong to the ground. A dark carrier visible in the gaps reads as depth, so fill the view, not every gap.

Use one-blade [tufts](reference/distributions#tufts) for leaves: two triangles per leaf, width about half the length. A tangent direction field with a random azimuth and slight normal lift lays their long axes nearly along the ground. Subtract the normal component from a horizontal direction, then add a small amount of the normal back. Blade widths still rotate around those axes, so some leaves tilt: this makes loose litter, not flat sheets conforming to the ground. Use separate leaf geometry with [lay](reference/edits#lay) when full surface contact matters.

::: example terrain_litter
note: One mesh of short leaves, with two autumn tones selected by noise. The dark soil stays visible between them.
:::

For dense litter, combine a few surface samples of 4096 sites with different seeds. The source guide reports roughly 5,500 accepted leaves on 0.64 m² from three calls, about 14k triangles including its support and details. These are scene measurements, not a guaranteed acceptance rate. A sparse patch needs only a few dozen leaves. Use two or three autumn tones by noise and add a few twigs at their sampled site's height, for example cylinders turned with `ry=90`.

## Gravel {#gravel}

The bed does much of the work. Give the ground fine relief with features about three grains wide and a dark per-face speckle. Add pebbles made with [hull](reference/solids#hull) from eight surface points, about 12 triangles each when all points remain hull vertices. Sink them with `at(p, on=site.offset(-d * .15))`, then put one material on their group.

Pebbles smaller than roughly 1/25 of the patch width can disappear at render size. The source guide's 800 mm patch used 450 pebbles of 30–60 mm and cost about 25k triangles with the bed. For sparse gravel, try 20–30 larger pebbles on soil. The first example uses that smaller arrangement; its final count depends on the accepted sites.

## Snow {#snow}

A blanket is the ground mesh with the `snow` preset, not a second layer floating above it. Shape drifts with a callable returning 0..1. Named Perlin noise seldom reaches the requested displacement amount: in the source guide's 800 mm example with two broad features, an amount of 45 mm produced at most about 10 mm of rise.

::: example terrain_snow
note: Positive noise makes mounds. Low side faces retain soil colour, while surface normals tint the snow from blue-grey on slopes to pale on top.
:::

Flat white hides relief. Tint slopes blue-grey using the normal and keep the soil colour on sides below the snow line. Snow on objects can be colour selected by `n[2]`, the upward normal component. A dusting needs colour only: mix soil toward white using noise multiplied by `n[2] ** 4` on upward-facing surfaces. Face size sets the grain of this per-face colour.

## Sand, dunes and wind ripples {#dunes}

Separate three scales of relief: low-frequency noise for the broad ground, an asymmetric dune profile, then smaller wind ripples. Apply all three to the top of a supported solid. Keep the underside flat.

Windward slopes are long and gentle; a dune's slip face is short, near 32 degrees, or a rise/run of about .625. A symmetric sine makes ripples, not that dune profile. Bend the crest sideways so it reads as a dune rather than a straight ramp.

::: scene terrain_dunes
title: Sinuous dunes
program: docs/site/toys/terrain_dunes.py
note: A slow rise over four fifths of each period, a short slip face, then a separate wave field for surface ripples.
:::

The example's 200 mm height over a 320 mm slip-face run gives about 32 degrees before other relief and the boundary fade. Its sine bends the crest across the patch. Colour uses both height and normal to highlight high crests, rather than every upward-facing face.

The source recipe budgets about 35k triangles. Ripple relief below roughly 1/400 of the scene width can vanish at render size: 3 mm on a 3 m patch did in the source trial. This example uses 8 mm ripples. Budget ripple sampling across the whole ground. The `sand` material gives the rough response; do not model individual grains. See [waves](reference/paths#waves) for the wave field and [displace](reference/edits#displace) for refinement controls.

## Scenes to adapt {#scenes}

::: scene terrain_stones
title: Stones on uneven soil
program: docs/site/toys/terrain_stones.py
note: Change the ground shape without rewriting the placement formula: sites come from its mesh.
:::

::: scene terrain_snow
title: A snow blanket
program: docs/site/toys/terrain_snow.py
note: The same supported-solid method, with positive drift displacement and normal-based colour.
:::

## Verbs used {#verbs}

::: chips box displace scatter vary at lay snap Frame hull tufts noise waves material
:::

Next: [Water](guides/water) to dig basins and fill them against this ground.
