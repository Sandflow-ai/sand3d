---
title: Distributions
order: 6
lead: Generate sites first, then put geometry on them. Grids, rings, path samples and surface samples return Frames; the geometry remains a separate choice.
---

## Repeat on frames {#repeat}

Pass a distributor's `Frames` to `at(..., on=sites)` to consume one prototype and return one copy per site. `hole` and `pocket` use the same `on=` list to cut once at each site. Always use what `at` returns. If filtering or ray casting can leave no sites, test `if sites:` before placement; empty frame lists are refused.

`Frames` behaves as a list and supports `.move`, `.turn`, `.offset` and `.jitter`. Each operation uses each frame's own axes. Distances use program units, millimetres by default; angles use degrees. The exceptions to the return type are `vary`, which gives numbers, `branches`, which gives axes with `.tips` frames, and `tufts`, which makes a mesh.

To vary size, use `at(prototype, on=sites, scale=vary(1, .2, len(sites), seed=3))`. A number or numeric axis tuple scales all copies alike; a list gives exactly one scale per site, even for three sites. Use the number of accepted sites after filtering. See [Placement and scale](reference/frames#scale-before-placement).

## Regular and spiral layouts {#layouts}

::: fiche grid
sig: grid(nx, ny=1, px=0, py=0, stagger=False, on=None) -> Frames
what: Make nx by ny frames centred on one base frame, the origin by default. All frames keep its axes, so the parts have parallel orientations.
param px, py: spacing along base X and Y; zero places those sites together
param stagger: shift alternate rows by half px, with the overall layout centred
param on: one frame, not a list
toy: dist_patterns | Left: a 4 by 4 grid. Small seeded changes in size and rotation leave the grid visible.
see: `ring`, `Frames.jitter`
limits: on accepts one frame, not a frame list. Zero pitch puts sites on top of each other along that axis.
:::

::: fiche ring
sig: ring(n, r, start=0, angle=360, on=None) -> Frames
what: Make frames on a circle of radius r around the base frame's Z. Each frame's X points outward; Z stays the base normal, so an asymmetric part turns with the ring.
param start: start angle in degrees, zero along base X
param angle: span in degrees; 360 spaces n sites without duplicating the start, other spans include both ends when n > 1
param on: one frame, the origin by default
see: [Example: Middle: radial pegs around a ring; frame X faces away from the centre.](reference/distributions#grid), `arc`, `phyllotaxis`
limits: on accepts one frame, not a frame list. On a partial arc, both endpoints are included; a full 360-degree ring does not repeat its first site.
:::

::: fiche phyllotaxis
sig: phyllotaxis(n, d, h=0, angle=137.508, on=None) -> Frames
what: Place n sites on a disc of diameter d, or on a cylinder when h is positive. Each site advances by angle degrees; disc radii distribute equal areas and cylinder heights are evenly spaced.
param h: zero for a disc with Z along the base normal; positive for a cylinder with Z pointing radially outwards and Y along the cylinder axis
param on: one base frame, the origin by default
limits: n is a nonnegative integer; d and h must be finite and nonnegative, and angle finite. Cylindrical sites lie between the ends, not on the end planes. This distributor creates no mesh.
see: [Example: Right: a disc layout. Radii grow with the square root of the site index.](reference/distributions#grid), `along`, `at`
:::

## Follow paths and branches {#paths}

::: fiche along
sig: along(path, pitch=None, count=None, spin=0, span=(0, 1)) -> Frames
what: Sample a path by arc length, with frame Z along its tangent. Use pitch for a fixed spacing or count for an evenly spaced number of sites.
param span: two ordered arc-length fractions in [0, 1]
param pitch: positive spacing starting at span's start, stopping at or before its end
param count: nonnegative integer; includes both span endpoints, except on the full span of a closed path, where the repeated endpoint is omitted; one site is at the start
param spin: additional degrees about the tangent per successive frame
toy: dist_along | Leaves turn around a curved stem, then lean away from its tangent.
limits: Give pitch or count; count takes precedence if both are supplied. Zero spin references X to parent/world Z. Nonzero spin parallel-transports X along the path; a closed path can still have a roll jump at the seam.
see: `ob.edge`, `phyllotaxis`, `Frames.jitter`
:::

For lateral leaves, spin around the tangent first, then lean with `.turn(ry=60)`. Build the leaf from its root at the origin along its own +Z. Angular jitter keeps that root attached; position jitter detaches it. Cylindrical `phyllotaxis` already points outward, while `along` points along the stem. `along(path, count=2)[-1]` gives an open path's end frame.

::: fiche branches
sig: branches(length, d, levels=3, children=3, attach=(0.45, 0.9), angle=45, azimuth=137.508, length_ratio=0.55, diameter_ratio=0.55, tip_ratio=0.15, jitter=0, seed=0, on=None, wander=0, droop=0, *, step=None)
what: Generate a root axis along base +Z and generations of child axes, in depth-first order. Build wood with wire or sweep and put buds or foliage on the returned list's `.tips`, a Frames containing one frame per leaf axis.
param length, d: root length and base diameter, both positive
param levels, children: nonnegative generation count and children per axis
param attach: ordered fractions in [0, 1]; children attach evenly over this interval, a lone child at its midpoint
param angle, azimuth: lean from the parent tangent and angular step around it, in degrees; azimuth restarts at each parent
param length_ratio, diameter_ratio: positive child-to-parent ratios; diameter uses the parent's base, not the diameter at the attachment
param tip_ratio: end-to-base diameter ratio in [0, 1]
param jitter: fraction in [0, 1] varying lengths, lean and azimuth steps
param wander: nonnegative maximum random heading turn per segment, in degrees
param droop: up to this many degrees towards base -Z over each axis; negative rises
param step: optional positive maximum arc-length sampling spacing; automatic angular sampling uses 3 degrees of accumulated turn, overridden by facets
toy: dist_branches | The same seed with straight axes, rising curved axes, and drooping curved axes.
limits: At most 4096 axes and 128 levels. Paths and tips already include on: do not place them on it again. With wander and droop both zero, paths are exact two-point segments; otherwise eight spline-smoothed segments, with children attached by arc length and facing transported tangents. Curvature radii exceed twice the section radius for wire or a matching sweep diameter law.
see: `wire`, `sweep`, `at`
param seed: Integer seed for the local random generator; the same inputs reproduce the axes.
param on: One base Frame, not a frame list; None uses the origin and default axes. Paths and tips already include this frame.
:::

Each axis exposes `.path`, `.d` (a diameter law), `.level` (root 0), `.name`, and `.parent` (root None). Build it as `wire(axis.name, axis.path, axis.d)`. Leaf axes are those for which no other axis has `.parent is axis`. Keep the branching visible; foliage cost is leaf count times faces per leaf, plus twigs.

## Controlled variation {#variation}

Seeded calls replay their results for the same inputs. They use their own random generators rather than changing global randomness. Derive a different seed for each job, such as `seed + 1` for sites and `seed + 2` for sizes. Reusing the same seed for two `vary` calls correlates their draws: the longest leaf can also always be the widest. Keep draw order stable.

::: fiche vary
sig: vary(value, spread, n, seed=0) -> list
what: Return n floats near value. Each is value plus a triangular draw between -spread and +spread, with its mode at zero, so most stay near the requested value.
param spread: absolute nonnegative variation in the value's own unit, not a fraction
param n: nonnegative integer count
param seed: integer seed
limits: value and spread must be finite. vary(24, 5, n) lies in [19, 29]; a value of zero varies too. Choose a range that stays positive when passing values to a positive dimension or scale.
see: [Example: A scale of 1 with spread .3 changes each peg's proportions uniformly between .7 and 1.3.](reference/distributions#grid), `at`, `Frames.jitter`
:::

::: fiche Frames.jitter
sig: Frames.jitter(rx=0, ry=0, rz=0, x=0, y=0, z=0, seed=0) -> Frames
what: Return perturbed frames, turning and moving each independently. Each amplitude bounds a triangular draw centred at zero; small changes are more likely than extreme ones.
param rx, ry, rz: finite nonnegative angle amplitudes, degrees
param x, y, z: finite nonnegative distance amplitudes, program units; moves use each original frame's axes, before the random turn
param seed: integer seed; frames preserve which part they were read on
limits: Jitter is not a collision solver. For attached organs, use angular jitter to keep their bases on the carrier.
see: [Example: Each site's Z rotation varies by at most 12 degrees.](reference/distributions#grid), `Frames`, `vary`
:::

An irregular planar outline can be built from `poly([tuple(f.origin)[:2] for f in ring(n, r).jitter(x=j, y=j, seed=3)])`. A faceted rock can use `hull` over `scatter(..., surface=True).jitter(...)` sites. Point count changes the hull silhouette; fine surface noise alone does not break a regular outline.

## Sample and project onto surfaces {#surfaces}

::: fiche scatter
sig: scatter(n, size, seed=0, surface=False, on=None) -> Frames
what: Spread sites inside an ellipsoid or over a surface. Each accepted point is the best spaced of 16 Mitchell candidates; the result is deterministic for a given integer seed.
param n: integer from 0 to 4096
param size: three finite positive ellipsoid diameters, or a mesh part, list of parts, or group with mesh descendants
param surface: for an ellipsoid, sample area instead of volume; implicit for mesh inputs
param on: ellipsoid centre and axes only; refused for mesh inputs
toy: dist_tufts | Stones use sampled upward-facing sites; grass uses grid probes snapped to the same carrier.
limits: Ellipsoid candidates are uniform in volume or surface area, but their frame normals are radial, including on a non-spherical ellipsoid. Mesh candidates are area-weighted on closed manifold surfaces, with outward normals. Overlapping parts retain internal surfaces: join first for a union. Empty groups raise.
see: `snap`, `hull`, `tufts`
:::

Surface samples cover sides and undersides too. Filter once, for example with `f.normal.z > .9`, and use the surviving count. Frames are expressed in the meshes' shared parent space; group inputs use the group's parent space. Query before grouping the carrier with new parts, and keep mesh-local callback coordinates separate from sampled coordinates. For `dent` with these sites use `coords="parent"`.

Place a stone with `at(stone, on=site.offset(-d/4))` to sink its root a quarter diameter into the surface. `at` aligns it to the site normal; `lay(at(leaf, on=site), ground)` can then seat a flat piece on the surface. These geometry-derived sites follow changes in the carrier instead of relying on positions measured from a render.

::: fiche snap
sig: snap(targets, points, direction=None) -> Frames
what: Find the nearest surface point to each probe, or the first hit along a ray. Returned frames face out from the surface, in the targets' parent space.
param targets: target first: a mesh part, group or list, as for surface scatter
param points: probe points or Frames second; a Frame contributes its origin
param direction: None for nearest point; a named axis such as -Z or +X, or a nonzero (x, y, z) vector for rays
limits: Ray misses are dropped. Check if hits before hits[0], and do not assume a one-to-one output index after misses. Keep probes and targets in the same coordinate space.
see: [Example: A grid above the ground is projected down with direction="-Z". Tufts root exactly at the hits.](reference/distributions#scatter), `grid`, `scatter`, `tufts`
:::

## Many rooted pieces in one mesh {#rooted-pieces}

::: fiche tufts
sig: tufts(name, sites, height, width, blades=5, lean=20, direction=None, shape="blade", seed=0)
what: Build one mesh of pointed pieces for all sites, with each piece rooted exactly at its site's origin. Default growth follows site Z; use a direction field for combed fur or flat litter.
param sites: one Frame or an iterable of Frames in one shared parent space
param height, width: positive lengths, or (x, y, z, n) callbacks per site
param blades: positive integer pieces per site
param lean: maximum deviation in degrees, from 0 to 85; a number or site callback
param direction: nonzero vector in the sites' space or site callback; None uses the normals
param shape: blade gives a flat pointed ribbon, 2 triangles; cone gives a triangular double cone, 6 triangles; both are widest at mid-height and pointed at root and tip
param seed: nonnegative integer
limits: Triangle count is sites × blades × 2 or 6, independent of facets. Empty sites give an empty mesh. Sites are numeric snapshots: keep the carrier and tufts together when moving them, by grouping after querying.
see: [Example: Five blades at each snapped site, all in one grass mesh, over a visible ground carrier.](reference/distributions#scatter), `scatter`, `snap`, [Trees and vegetation](guides/trees)
:::

Callbacks may be scalar or vectorized. Vectorized x, y and z have shape `(N,)`, normals n have shape `(3, N)`; return `(N,)` for height, width or lean, and `(N, 3)` for directions. Values must be finite, and directions nonzero. A tangent field combs fur; every root remains on its site even with a tangent direction.

For lawns, use coloured ground for distant coverage and tufts for the silhouette. Start around 500–2,000 accepted sites per m² and 3–5 blades per site; in millimetres divide area by 1,000,000 to get m². Use `grid` plus `snap` beyond scatter's 4096-site limit. A 10 m² lawn at 1,000 sites/m² and 5 blades already costs 100,000 triangles before ground and props.

For moss edges, a short pile around 7 mm high with 3 blades and lean 45 is about 25,000 triangles at 4096 accepted sites. Filter with the same patch mask that shapes and colours the ground. Textile nap can use short wide cones for clumps or thin blades for bristles. Animal fur reads better as dense, thin, combed blades on a matte material; cones read as scales. Keep the carrier visible between clumps.

For leaf litter use one blade per site, two triangles per leaf, width about half the length and a near-tangent direction. Several independently seeded batches can populate larger areas, with a few larger modelled leaves for detail. Detailed ground, colour fields and complete recipes belong in [Trees](guides/trees) and [Terrain](guides/terrain).
