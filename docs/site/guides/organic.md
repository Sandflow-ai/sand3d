---
title: Organic forms
order: 5
lead: Build the structure before adding surface noise. A rock needs a silhouette, a coral needs connected branches or ridges, and a fungus needs lobes that meet its stem.
---

## A first rock {#rock}

::: example organic_rock
note: A hull of 28 seeded points, with broad relief and a second, smaller grain. The point count sets the large facets before displacement adds detail.
:::

Start with points scattered over an ellipsoid's surface. Jitter them to break regular spacing, then wrap them with [hull](reference/solids#hull). This gives a convex mass: any inward pockets between the points are lost. Broad [displacement](reference/edits#displace) can break that convexity; a second pass adds grain. Keep both seeds explicit so the same program makes the same rock.

## Choose the structure {#structure}

Choose a verb for the shape you need before choosing a noise pattern.

| Need | Method |
|---|---|
| A convex, faceted mass | [hull](reference/solids#hull) wraps points |
| Several masses flowing into one another | [blend](reference/edits#blend) fuses them and fills the meeting creases |
| Relief on a surface that already exists | [displace](reference/edits#displace) moves its vertices |
| A local hollow | [dent](reference/edits#dent) pushes in a patch |
| Cavities, tunnels or folded sheets | [field](reference/solids#field) builds the boundary of a density function |

Noise cannot rescue a missing structural feature. Keep coral branches attached, fungal lobes connected to stems, and the rock's important outline visible.

## Holes, folds and lobes {#fields}

A field describes inside and outside throughout a box. Its boundary becomes the surface, so it can form tunnels and cavities as well as outer relief. Combine a broad envelope with seeded [noise](reference/paths#noise) or [waves](reference/paths#waves) to shape folded sheets, brain-coral ridges, fungal lobes or rock masses. The [field reference](reference/solids#field) explains the density convention, bounds and sampling parameters.

::: example solids_field
note: A spherical envelope clips a periodic density to form an open lattice.
:::

Start with coarse cells to find the overall shape within the build budget. Then check that holes stay open and narrow connections survive. Refine only where the visible geometry needs it; never refine a field solely to carry finer colour. For relief on an otherwise adequate surface, use displacement instead of rebuilding the whole volume.


## Verbs used {#verbs}

::: chips hull scatter Frames.jitter field noise waves blend displace dent material
:::

Next: [Colour and weathering](guides/colour) for surface variation that does not add geometry.
