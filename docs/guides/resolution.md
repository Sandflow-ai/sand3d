# Triangle budgets and cost

Budget the sum over all copies before detailing a prototype: copies and instances both multiply visible
triangles. Start coarse with `facets(n)` and explicit `step`, build the coarse whole first, spend faces
on visible shape, and inspect the silhouette at the final render size. Use `lay(..., step=0)` unless the
carrier's curvature needs subdivision. A larger `step` reduces added topology without changing the
noise feature size.

```python
s3d.displace(leaf, amount=0.2, size=1.0, step=2.0)
s3d.bend(stem, 35, step=4.0)
s3d.lay(patch, terrain, step=3.0)
s3d.blend(*rocks, r=4, step=1)
```

Indicative budgets at 1024 px (triangles, not a quality score):

| Subject | Budget |
|---|---:|
| Single piece | ~50,000 |
| Plant, bouquet or small group | ~150,000 |
| Full tree | ~200,000 |
| Scene with ground, water, fire or smoke | ~300,000 |

A six-sided sweep costs about 12 triangles per path interval, plus its caps. Make a path inside its
intended `facets` context: setting facets only around the sweep does not remove stations already in the
path. `along(count=...)` chooses placements, not mesh rings. Smaller editing `step`, more section facets
and more path rings all spend triangles; a per-face colour pattern needs the coarsest mesh that keeps it
visible.
