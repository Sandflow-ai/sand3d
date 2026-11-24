---
title: Paths and fields
order: 3
lead: Paths describe where a solid travels. Scalar fields return a number at each position: use them to move an existing surface or define a new solid by its density.
---

## Coils and spirals {#coils}

::: fiche helix spiral
sig: helix(d, pitch, h, left=False)
sig: spiral(d, d2, turns, h=0, left=False)
what: helix makes a constant-diameter coil rising along Z. spiral changes diameter geometrically while height changes linearly; both start on +X at z=0 and return paths for wire or sweep.
param d: Starting centre-line diameter; helix keeps it throughout.
param pitch, h: A helix rises pitch per turn, to height h. For spiral, h is total rise, zero by default and allowed to be negative.
param d2, turns: Spiral end diameter and number of turns. At halfway its diameter is the geometric mean of d and d2.
param left: Reverse turning direction. By default the path turns anticlockwise about +Z; left changes turning, not rise.
toy: paths_coils | A constant-diameter helix and an expanding spiral, each made visible with a 2 mm wire.
limits: spiral requires positive finite diameters and turns, finite h and a boolean left. It stays open even when its endpoints meet.
see: `wire`, `sweep`, `along`
:::

## Other paths {#other-paths}

- [spline](reference/profiles#spline): open by default, or a smoothly closed path with loop=True, in 2D or 3D. closed=True instead returns a planar profile.
- [arc](reference/profiles#arc): a circular or elliptical path; arc(r=r) is a circle path.
- [ob.edge](reference/frames#ob-edge): a named edge of an existing solid, usable as a path.
- `wire` also takes a list of 3D points. `poly` is a planar profile, not a spatial wire route.

Create paths inside the same `facets(...)` context as their consuming solid. More `rings` cannot fix a wire crossing itself: reduce its diameter or soften the path's curvature. Sweep and loft caps are `start` and `end`.

## Scalar fields {#scalar-fields}

::: fiche waves
sig: waves(wavelength, direction=None, centers=None, sharpness=0, spread=0, decay=None, phase=0, seed=0)
what: Return a pure function f(x, y, z), bounded to [-1, 1], with no mesh. It describes waves in local XY, independent of z, and accepts scalars or broadcast arrays, returning a float or float64 array.
param wavelength: Positive period in program units, measured along the direction of travel.
param direction: Phase gradient, perpendicular to the crests. Defaults to +X; accepts +X, -X, +Y, -Y or degrees anticlockwise from +X toward +Y.
param sharpness: From 0 to 1. Changes cos(t) into cos(t + sharpness * sin(t)), narrowing crests and broadening troughs without changing bounds or period; the mean can become negative.
param spread: Half-angle from 0 to 90 degrees for four seeded satellite waves around the primary. Zero gives one exact cosine; seed affects spread only.
param centers: Nonempty (x, y) pairs for circular sources with the same wavelength, sharpness and phase. Excludes direction and nonzero spread.
param decay: Positive e-folding length for circular sources only. Without decay, sources are averaged; with decay, weighted sources are divided by max(sum of envelopes, 1).
param phase, seed: Phase in degrees, zero putting a crest at the origin of the primary directional wave or at each circular source; seed is an integer.
toy: paths_waves | Directional crests and circular rings with distance decay, used to displace only the top of two plates.
limits: Finite inputs only; evaluated distance divided by component wavelength must have magnitude at most 2**50. Waves are heights: no horizontal motion, overturning or breaking, and no thickness-preserving bend.
see: `displace`, `field`, [Water](guides/water)
:::

With decay, a lone source retains its exponential envelope: it is not normalised back up to full amplitude. A shore is a spatial mask, not `decay`.

::: fiche noise
sig: noise(x, y, z, seed=0, kind="perlin")
what: Evaluate deterministic noise in [-1, 1], independently of displace. Scalars return a float; broadcastable inputs return a float64 array of the broadcast shape, reproducible across runs and platforms.
param x, y, z: Dimensionless coordinates. Divide positions by a chosen feature length to set their scale.
param kind: perlin is gradient noise; ridged and turbulence transform it; cells uses nearest-cell distance.
param seed: Integer selecting the realization.
toy: paths_noise | Perlin and cells in the first row, ridged and turbulence in the second, each evaluated at a 12 mm coordinate scale.
limits: Coordinates must be finite and have magnitude at most 2**50. This realization is not the one obtained with displace's named noise modes.
see: `displace`, `field`, `material`
:::

## Use a field {#use-fields}

For an existing surface, pass the function as the `noise` of `displace`. The callable receives three float64 coordinate arrays in the part's local frame and program units by default. Return a same-shaped finite array within [-1, 1]; values multiply `amount` and fade directly, without automatic centring. Coordinates are not divided by `size`.

Keep `octaves=1` and `seed=0` on `displace` when supplying a callable. Put seeds, coordinate scaling, layers and domain warps inside the function. With `coords="path"`, the arguments instead describe construction coordinates: arc length in program units, transported angle in degrees, and construction radius. Named noise modes are refused with path coordinates; see [displace](reference/edits#displace).

The wave's wavelength belongs to `waves`; `displace`'s `size` controls refinement and the boundary ramp. Give the shortest component at least 16 samples per period, more for sharp crests, or set `step` explicitly. Changing step does not change the field's feature size. Use a fixed direction such as +Z for a height surface; normal displacement on a curved mesh can cross itself. On filled water use faces="top" to leave the shore fixed. A tilted fill has local XY in its free surface, so waves follow that plane.

For a new solid, use `noise` or `waves` in the `density` callable of `field`. Density below `level` is solid, inside the supplied bounding size. For example, `density=lambda x, y, z: s3d.noise(x / 12, y / 12, z / 12, seed=5)` makes a porous region at the default level zero. A wave-based height density can be `lambda x, y, z: z - (20 + 3 * f(x, y, z))`. Density need not stay in [-1, 1]; the bounded requirement belongs to displacement. Resolve its features with `cell`, starting coarse for cost; see [field](reference/solids#field).

### Compose bounded functions {#composition}

Multiply a field by a 0..1 mask to restrict it spatially. A shore ramp can be `f(x,y,z) * np.clip((x-shore)/width, 0, 1)`. Noise can modulate amplitude with `.7 + .3*s3d.noise(x/500, y/500, z/500)`. Clip sums such as `np.clip(f(x,y,z) + .2*g(x,y,z), -1, 1)` before displacement. These expressions use `import numpy as np`.

A 0..1 noise mask is `.5 + .5*s3d.noise(x/160, y/160, 0, seed=5)`. The same scalar field can drive patch density, displacement and colour without moving their features apart. Colour functions can threshold a field too: `np.where((f(x,y,z) > .7)[:, None], [1.,1.,1.], [.02,.15,.2])` colours crests, but does not model foam.

Wavelength and sharpness also describe sand ripples, broad dunes and corrugated sheets as heights. Recipes stay in [Water](guides/water), [Terrain and ground](guides/terrain), [Organic forms](guides/organic) and [Trees and vegetation](guides/trees).
