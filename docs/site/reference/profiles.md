---
title: Profiles and outlines
order: 1
lead: Draw a flat region, then give it thickness or use it as a section. Profiles live in XY; paths describe a route. The examples give profiles a thin extrusion so their outlines are visible.
---

## Centred shapes {#basic-shapes}

Lengths use the program's unit, millimetres by default. `extrude` lifts a profile along Z; `box` is the extrusion of a `rect`. Use `at` to place a profile or its solid.

::: fiche rect circle ellipse slot polygon
sig: rect(w, d, r=0, chamfer=0)
sig: circle(d)
sig: ellipse(w, d)
sig: slot(l, d)
sig: polygon(n, d)
what: These profiles are centred on the origin. Choose a rectangle, circle, ellipse, round-ended slot or regular polygon, then extrude it.
param w, d: Width along X and depth along Y; for circle and polygon, d is a diameter.
param r, chamfer: Rectangle corner radius or corner cut distance; both default to zero.
param l: Slot's overall length along X; d is its width. If l is at most d, the result is a circle of diameter d.
param n: Polygon side count. Corners lie on a circle of diameter d, with one corner on +X.
toy: profiles_basics | Rectangle, circle and ellipse in the first row; slot and hexagon in the second. Each is extruded 3 mm.
limits: Corner rounding or cutting must fit on the adjacent sides.
see: `poly`, `extrude`
:::

## Draw an outline {#drawing}

::: fiche poly arc tangent_arc
sig: poly(pts, fillet=0, chamfer=0)
sig: arc(center=(0, 0), r=1, start=0, end=360, *, through=None, to=None)
sig: tangent_arc(to)
what: poly joins XY points with straight lines and closes the outline. Mix points with arc, tangent_arc and open spline runs to draw curved portions without listing sampled points yourself.
param pts: An ordered sequence of points and curved runs. The last point joins back to the first; repeating the first point is optional.
param fillet, chamfer: Round or cut corners between two straight segments only. Supply one value for all eligible corners or a list indexed by input item; zero leaves a corner alone.
param center, r: Arc centre and radius, or (rx, ry) for an elliptical arc.
param start, end: Arc angles in degrees. Increasing angles run anticlockwise; decreasing angles run clockwise.
param through, to: Inside poly, arc(through=p, to=q) starts at the previous point, passes through p and ends at q. Give both, without the centre/radius/angle form.
param to: tangent_arc ends here, leaving the previous point tangent to the preceding outline.
toy: profiles_runs | Straight sides, a tangent corner, a three-point arc and a spline form one closed plate.
limits: These outlines are planar. A tangent arc needs a preceding point and an incoming direction; a through arc needs a preceding point. Corner fillets and chamfers that exceed a side raise an error.
see: `spline`, `stroke`, `wire`
:::

An `arc` is also a path on its own: `s3d.arc(r=20)` draws a full circle path. Feed it to `wire` or `sweep` for a solid. A point list for `poly` need not be centred: it is drawn where its coordinates say. For an irregular outline, points can also come from frame origins, for example `s3d.poly([tuple(f.origin)[:2] for f in s3d.ring(8, 20).jitter(x=2, y=2, seed=3)])`.

::: fiche spline
sig: spline(pts, closed=False, tangents=None, loop=False)
what: Interpolate a smooth curve through 2D or 3D points. The default is an open path; closed=True makes a planar profile, while loop=True makes a smoothly closed path that may travel through 3D space.
param pts: Points the curve passes through, in order.
param tangents: Optional (start, end) directions for an open curve. Either can be None; only direction matters, not magnitude.
param closed: Return a flat profile for extrude, revolve or loft.
param loop: Join the last point smoothly to the first as a path for wire, sweep or along.
toy: profiles_spline | The same points as an extruded closed profile, a loop path made into a wire, and an open path made into a wire.
limits: closed and loop are mutually exclusive. Neither accepts end tangents; a loop needs at least three points. A supplied tangent must be nonzero and point along the curve, not backwards across it.
see: `poly`, `wire`, `sweep`, [Paths and fields](reference/paths#other-paths)
:::

Build a spline and the `wire` or `sweep` using it inside the same `facets(...)` context. Increasing facets only around the solid does not remove stations already sampled in its path. Fixed facets controls turns across sections and along paths. More `rings` cannot repair a self-crossing: reduce the wire diameter or soften the curvature. Sweep and loft caps are named `start` and `end`, not `bottom` and `top`.

## Sections for lofting {#sections}

::: fiche superellipse station
sig: superellipse(w, d, n=2, taper=0)
sig: station(z, w, d, x=0, y=0, n=2, taper=0)
what: superellipse moves from an ellipse at n=2 toward a rounded rectangle at n=4. station makes that same profile and places it at a height and XY centre, ready to become a loft section.
param w, d: Section width along X and depth along Y.
param n: Shape exponent; lower values make a more diamond-like outline, higher values a squarer one.
param taper: Narrows the +Y side and widens the -Y side, producing an egg-like outline.
param z, x, y: Section height and centre, as in at(superellipse(w, d, n=n, taper=taper), x=x, y=y, z=z).
toy: profiles_sections | Ellipse, rounded rectangle, tapered ellipse, then a loft through three stations with changing width, depth and centre.
see: `loft`, `body`, `displace`
limits: Use positive n and nonzero depth for an ordinary outline. A zero width and depth together make a pole, not an area to extrude.
:::

For a soft mass, extrude or loft ellipse-like sections, then displace at the scale of the outline before adding fine grain. The [organic forms guide](guides/organic) develops that technique.

## Letters {#lettering}

::: fiche text
sig: text(s, size, font=None)
what: Turn text into a profile centred on its visible ink. Extrude the outline for raised letters, or use its solid as a cutting tool.
param s: Text to outline.
param size: Font em size in program units; this is not the exact visible letter height.
param font: Path to a .ttf or .otf file; None uses Blender's built-in font.
toy: profiles_text | S3D outlined at an em size of 28 mm and extruded 4 mm.
limits: Text with no outline, such as an empty string, raises an error.
see: `extrude`, `cut`
:::

## Change a profile {#profile-operations}

Profiles support `+` for union and `-` for difference. These are 2D operations before extrusion.

::: fiche offset
sig: offset(p, t)
what: Grow a profile all around by t, with rounded outward corners. A negative t shrinks it; placement of a placed profile is preserved.
param p: The original profile.
param t: Signed offset distance in program units.
toy: profiles_offset | The same rectangle shrunk by 3 mm, unchanged, and grown by 3 mm.
see: `stroke`, `wrap`
limits: Large offsets can cross narrow features; this operation does not resolve self-intersections into a new outline.
:::

::: fiche stroke
sig: stroke(path, t)
what: Turn a flat open path into a closed band of width t, centred on the path. Ends are square and corners are mitred; extrude the band for a strap, bracket or wall.
param path: An open spline, arc or XY point sequence with the same curved runs as poly.
param t: Positive width, half on either side of the path.
toy: profiles_stroke | A circular arc becomes a curved strap; an angular point path becomes a mitred bracket.
limits: Closed paths and profiles are refused. The band must not cross itself: use a thinner band or a less tightly turning path. Draw in XY, then place the resulting profile with at.
see: `arc`, `offset`, `extrude`, `revolve`
:::

For a band around a closed profile `p`, use `s3d.offset(p, thickness) - p` instead.

::: fiche wrap
sig: wrap(*profiles)
what: Draw the convex outline around profiles and XY points. Placed profiles keep their in-plane positions; straight spans meet curved portions tangentially, and explicit points keep their corners.
param profiles: Profiles, points, or lists of them. Together they must span an area.
toy: profiles_wrap | A belt made from offset(outline, 3) - outline wraps two wheels of different diameters.
limits: At least three non-collinear sampled points are needed. Convex wrapping fills concavities.
see: `offset`, `hull`
:::

::: fiche mirror
sig: mirror(p, flip="x")
what: Return the union of a profile and its reflected image. Draw one half to make a symmetric whole, including any in-plane placement before reflection.
param p: Profile to combine with its image.
param flip: Coordinate whose sign changes: x by default, or y.
toy: profiles_mirror | The original half on the left and its union with the reflection on the right.
limits: This verb takes profiles. For a solid's image, use s3d.transform(s3d.copy(ob), mirror="x").
see: `transform`, `copy`
:::
