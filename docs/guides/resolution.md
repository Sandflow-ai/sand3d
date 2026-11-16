# Mesh resolution and triangle cost

Spend faces on visible shape. Increase `step` to reduce added topology without
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
