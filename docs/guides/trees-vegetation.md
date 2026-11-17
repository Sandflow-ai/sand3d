# Curved branches, parent attachment, foliage and crown cost.

- **Attach to the actual parent.** Strawberry's crown reads a surface frame with
  `snap`; its achenes snap again after denting. `LeafMapleFactory.py:petiole`
  returns the path end from `along(path, count=2)[-1]` for the blade.
  `KelpMonocotFactory.py:fronds` and `TreeFactory.py:structure` place children
  using `along(..., spin=137.508, span=(...))`. Derive placement from geometry,
  not offsets measured on a render. A child's anchor must follow seed changes.

- **Curved branching.** `BushBaseCoralFactory.py:crown` and
  `TreeFactory.py:bough` use `branches(wander=..., droop=..., seed=...)`.
  Wander bounds heading changes; positive droop bends toward the carrier's -Z,
  negative droop rises. Axis paths are already in their carrying frame: do not
  apply `on` a second time. Use their paths for wire/sweep and their tips for buds.

branches creates paths and along creates frames, not geometry. Build trunks and branches from tapering wire/sweep paths. along(path, count=13, spin=137.508, span=(.12,.92)) follows arc length; turn(ry=60) departs from the tangent. Place organs built from their base along local +Z; angular jitter preserves attachment, position jitter can detach leaves. scatter(n, size, seed=seed, surface=False) distributes frames in an ellipsoid; scatter(n, mesh, seed=seed) samples a surface. Vary foliage scale, orientation and clusters with derived seeds. Budget crown cost as leaf count times faces per leaf plus twigs: thousands of finely tessellated leaves dominate. Prefer simple broad leaf geometry that reads at review scale, expose branch structure and keep roots in ground contact.

## Parameter tables for repeated leaf tiers

Use one construction loop over a parameter table instead of copying each stage.
Keep table order, random-draw order and fusion order stable when refactoring.
Derive one seed per item and pass it to that item's helper; do not restart every
item at the same seed. The helper below is a program-local function you define,
not an extra library verb. The same pattern covers leaf tiers, flame layers,
smoke columns and layered fungi.

```python
layers = [(0, 1.0, 0), (80, .75, 23), (140, .45, -17)]
parts = []
for i, (height, scale, turn) in enumerate(layers):
    part = make_layer(scale=scale, seed=seed + 100 + i)
    parts.append(s3d.at(part, z=height, rz=turn))
```

Keep the brief's requested facets level, including smooth=False for flat faces.
A face budget is a ceiling, not a target: break the outline before adding detail.

Resolution costs triangles: use `step` to separate displacement feature size
from mesh sampling (see `resolution`).
Colour callbacks assign one RGB per face without UVs or textures, so fine colour
patterns need fine faces. Prefer colour for thin veins or grain over displaced
relief that is sub-millimetre at render scale.

## Grass, lawns and fur

A lawn is a supported ground with green per-face colour, plus `tufts` for its
silhouette. Do not build one object per tuft. Sample the ground, keep upward sites,
and pass those Frames directly to `tufts`; every blade roots at its site.
Start at 500–2,000 tufts/m², 3–5 blades/tuft; count the accepted sites. With mm
units, area in m² is area_mm² / 1,000,000. Use green ground for distant coverage,
not enough blades to hide every gap. `scatter` returns at most 4096 candidate
sites per call; filter before building and use grid + snap for larger lawns.

Triangles = sites × blades × 2 (`shape="blade"`), or × 6 (`"cone"`). A 10 m² lawn
at 1,000 tufts/m² and 5 blades costs 100,000 triangles before ground and props;
reserve those in a 150k–300k whole-asset budget. Cones cost three times as much.
Neither shape needs a subdivision step. Width is widest at mid-height, tips and
roots are pointed. All roots coincide at each site; no random root offsets can
float above a curved carrier. Height, width and lean callbacks vary by site;
`direction(x,y,z,n)` combs in the sites' space, including tangent to the carrier.

```python
ground = s3d.box("ground", 1000, 1000, 50)
s3d.material(ground, "grass", color=lambda x,y,z,n: (.12,.24,.04))
sites = s3d.Frames(f for f in s3d.scatter(3500, ground, seed=7) if f.normal.z > .9)[:1000]
grass = s3d.tufts("grass", sites, height=45, width=3, blades=5, lean=25, seed=8)
s3d.material(grass, "grass", color=lambda x,y,z,n: (.18,.35,.05))
```

For textile nap, scatter on the fabric carrier, filter its visible side, then
use short wide cones for clumps or thin blades for bristles. Root them on the
carrier and keep it visible between clumps. Use a tangent `direction` field to
comb fur; the default site normal gives standing pile. Add the carrier and tufts
to one group after querying: their frames must share a parent space.
