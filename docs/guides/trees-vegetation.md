# Branches, foliage, crown cost, grass, lawns and fur

- **Trunks and branches** are tapering `wire` or `sweep` along `branches` paths; its tips carry buds.
- **Foliage**: vary scale, orientation and clusters with derived seeds. Prefer simple broad leaves
  that read at review scale, show the branch structure, keep roots in ground contact.
- **Crown cost** = leaf count × faces per leaf, plus twigs: thousands of finely tessellated leaves
  dominate the budget.

## Grass, lawns and fur

A lawn is a supported ground with green per-face colour, plus `tufts` for its silhouette. Sample the
ground, keep upward sites, pass those Frames to `tufts`. Start at 500–2,000 tufts/m², 3–5 blades a
tuft, and count the accepted sites (in mm, m² = mm² / 1,000,000). Green ground covers the distance; do
not add blades to hide every gap. `scatter` gives at most 4096 sites a call: use `grid` + `snap` for
larger lawns. A 10 m² lawn at 1,000 tufts/m² and 5 blades costs 100,000 triangles before ground and
props: reserve them in a 150k–300k whole-asset budget.

```python
ground = s3d.box("ground", 1000, 1000, 50)
s3d.material(ground, "grass", color="#1f3d0a")
sites = s3d.Frames(f for f in s3d.scatter(3500, ground, seed=7) if f.normal.z > .9)[:1000]
grass = s3d.tufts("grass", sites, height=45, width=3, blades=5, lean=25, seed=8)
s3d.material(grass, "grass", color="#2e590d")
```

Textile nap: scatter on the fabric carrier, keep its visible side, then short wide cones for clumps or
thin blades for bristles, the carrier visible between clumps. A tangent `direction` field combs fur;
the default site normal gives standing pile. Group carrier and tufts after querying: their frames share
one parent space.
