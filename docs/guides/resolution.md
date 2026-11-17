# Mesh resolution and triangle cost

Budget the sum over all copies before detailing a prototype. Start coarse with
`facets(n)` and explicit `step`; build and run the coarse whole first. Use
`lay(..., step=0)` unless the carrier's curvature needs subdivision. Copies and
instances both multiply visible triangles. Spend faces on visible shape. Increase `step` to reduce added topology without
changing the noise feature size. Inspect the silhouette at the final render size.

| Operation | Automatic sampling (`step=None`) | Explicit sampling |
|---|---|---|
| `displace` | max(size/4, D/128), D the part's largest local box dimension | Positive maximum edge length; 0 moves existing vertices only |
| `bend`, `twist` | At least four segments, at most 3° each | Positive axial spacing; 0 adds no slices |
| `lay` | Existing vertices only | Positive maximum edge length before projection; 0 keeps topology |
| `blend` | Voxel spacing r/5 | Positive voxel spacing |

`facets(n)` sets angular counts and bounds automatic displacement sampling by
π D/n. Explicit displacement `step` still controls the requested edge length.
`field(cell=...)` sets volumetric sampling; `rings=n` adds longitudinal samples.
Existing fine geometry is retained; a larger step does not decimate it.

Colour is one RGB per face, without UVs or textures. Fine colour patterns need
fine faces too. Prefer colour over displaced relief for veins or grain too
small to affect the silhouette at the final image size.

```python
s3d.displace(leaf, amount=0.2, size=1.0, step=2.0)
s3d.bend(stem, 35, step=4.0)
s3d.lay(patch, terrain, step=3.0)
s3d.blend(rocks, r=4.0, step=1.0)
```

Indicative budgets at 1024 px (triangles, not a quality score):

| Subject | Budget |
|---|---:|
| Single piece | ~50,000 |
| Plant, bouquet or small group | ~150,000 |
| Full tree | ~200,000 |
| Scene with ground, water, fire or smoke | ~300,000 |

A six-sided sweep costs about 12 triangles per path interval, plus its caps.
`branches` samples curved axes by accumulated turn (3° by default, or `facets`);
`branches(step=...)` instead chooses longitudinal spacing. Make the path inside
its intended `facets` context: setting facets only around sweep does not remove
stations already in the path. `along(count=...)` chooses placements, not mesh
rings. Copies multiply the whole part's triangle cost; instancing does not reduce
that visible total. Smaller editing `step`, more cross-section facets and more
path rings all spend triangles. Per-face colour also spends faces when a pattern
must remain visible; choose the coarsest mesh that preserves it.

Build a spline and its `wire` inside the same `facets(...)` context. More rings
do not repair a self-crossing path: reduce diameter or soften curvature.
