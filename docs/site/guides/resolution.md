---
title: Resolution and cost
order: 8
lead: Build the whole object coarsely before detailing one part. Count visible triangles across every copy, then spend geometry where it changes the silhouette at the final image size.
hero: resolution_steps
---

## One relief, three mesh spacings {#steps}

::: example resolution_steps
note: From left to right, displacement uses step 14, 7 and 3.5 mm. Amount, noise size and seed stay the same. The smaller spacing gives the relief more vertices to move: 384, 1,224 and 3,000 triangles respectively, measured with seed 0.
:::

For displacement, a larger `step` reduces added topology without changing the noise's feature size. It does not decimate fine edges already present in the input mesh. Start with a coarse prototype, then compare the silhouette at the size the final image will actually use.

## Budget the whole scene {#budget}

Copies and instances both multiply visible triangles. Before refining a leaf or stone, multiply its triangle count by the number you plan to show. Build the coarse whole with explicit `step` and [facets](reference/export#facets), then spend the remaining budget on visible shape.

These are indicative budgets at 1024 px, measured in triangles, not quality scores or library limits.

| Subject | Triangle budget |
|---|---:|
| Single piece | About 50,000 |
| Plant, bouquet or small group | About 150,000 |
| Full tree | About 200,000 |
| Scene with ground, water, fire or smoke | About 300,000 |

Per-face colour needs a mesh coarse enough to stay affordable while retaining the visible pattern. If a fine pattern disappears, broaden the colour rather than refining solely for colour.

## Choose the spacing control {#spacing}

Use the table to decide which operation spends the triangles. Each linked reference gives that verb's full parameters. Lengths use the program's unit; `field(cell=...)` is a length, while `facets(n)` and `rings=n` are counts.

| Operation | Automatic spacing, step omitted | Positive step | Zero step |
|---|---|---|---|
| [displace](reference/edits#displace) | Target maximum edge max(size / 4, D / 128) | Maximum edge length | Move existing vertices only |
| [bend](reference/edits#bend), [twist](reference/edits#twist) | At least four axial segments, at most 3 degrees each | Axial spacing | No added slices |
| [lay](reference/edits#lay) | Existing vertices | Maximum edge length before seating | Existing vertices |
| [blend](reference/edits#blend) | Voxel size r / 5 | Voxel size | Not accepted |
| [branches](reference/distributions#branches) | Sample accumulated turn at 3 degrees | Maximum arc-length spacing | Not accepted |

Here D is the largest dimension of the part's local bounding box. The automatic angular and displacement rules above apply without a fixed facet count; the next section explains that override. Straight branch axes keep their two endpoints.

Automatic displacement refinement raises an error if it would exceed 500,000 faces. Give a larger step. Existing fine edges are never decimated by displacement. Use `lay(..., step=0)` unless the carrier's curvature needs extra vertices in the part being seated.

For example, a leaf can use `displace(leaf, amount=0.2, size=1.0, step=2.0)`: the mesh spacing is independent of the feature size. A stem can use `bend(stem, 35, step=4.0)`, a patch `lay(patch, terrain, step=3.0)`, and a rock group `blend(rocks, r=4.0, step=1.0)`. These are call patterns for existing parts, with lengths in the program's unit.

## What a fixed facet count controls {#facets}

A fixed `facets(n)` sets segments per revolution both across sections and along turns in sweeps, lofts, wires, bodies and spline paths. A straight span retains its stations. Bend and twist choose their sections from the total angle when no explicit step is given.

Create a path inside its intended facets context. Setting facets only around the later sweep cannot remove stations already stored in the path. [Along](reference/distributions#along) chooses placements with `count`; it does not choose mesh rings. A six-sided sweep costs about 12 triangles per path interval, plus its caps. More section facets, more path rings and smaller editing steps all spend triangles.

For surfaces without an axis, a fixed count defines a target edge length **L = π D / n**, independent of placement.

| Operation | Effect of a fixed facet count |
|---|---|
| [field](reference/solids#field) | Uses max(cell, L), with D from the requested box |
| [displace](reference/edits#displace) | Refines toward max(size / 4, D / 128, L), unless an explicit step overrides it |
| [blend](reference/edits#blend) | Keeps voxel closing, then collapses toward 4 × area / (√3 × L²) triangles, with a minimum of four; keeps the original if collapse breaks manifoldness |
| [hull](reference/solids#hull) | Keeps the supplied points |

If thin branches or cavities vanish, increase n. Keep inspecting the shape rather than assuming a lower count is harmless.

## Shading is a separate choice {#shading}

Fixed counts shade flat unless `smooth=True` was chosen at the program's first facets call, or the part has a [smooth](reference/edits#smooth) override. `smooth(ob, angle)` persists through edits and copies. Smooth shading does not add geometry to a silhouette.

The default `"auto"` uses a 0.05 mm chord tolerance with the usual shading. `with s3d.facets(n):` restores the previous count on exit, even if the block raises an error. See [facets](reference/export#facets) for count and shading settings.

## A scene to budget {#scenes}

::: scene organic_rock
title: A rock to repeat
program: docs/site/toys/organic_rock.py
note: Judge the displaced hull by its silhouette before copying this rock across a landscape. The visible triangle total grows with every copy, even when the copies share one mesh.
:::

## Verbs used {#verbs}

::: chips facets displace lay bend twist blend branches field smooth along
:::

Next: [Organic forms](guides/organic) to choose the structure before spending the detail budget.
