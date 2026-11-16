# Mesh resolution and triangle cost

Resolution parameters buy triangles. Start coarse, inspect the silhouette, then
spend faces on visible shape. `detail(0.5)` halves automatic counts and doubles
automatic sampling lengths. It changes future geometry only. `detail()` reads
the effective density; `empty_scene()` resets the program setting after a build.
The default is 1, preserving existing meshes.

For re-export, set `SAND3D_DETAIL=0.5` in the exporting process. This positive,
finite override wins over `detail()` and scales explicit resolution numbers too.
It never scales dimensions, noise feature size, object counts, profile vertices,
law knots, gear teeth or helix turns. Existing safety budgets still apply; very
coarse sampling can lose thin features or fail a geometry check.

| Operation | Resolution vocabulary | Density behavior |
|---|---|---|
| `displace(..., size, step=None)` | `size` is noise feature size; `step` is maximum edge length | Auto keeps the historical size/4 target. Positive step decouples sampling; 0 moves existing vertices only (`refine=False` alias). Fixed facets still bound refinement. |
| `bend`, `twist` | `step=None`, positive axial slice spacing, or 0 for no added slices | Auto uses 48 slices, scaled by detail; fixed facets uses turn angle. |
| `lay` | `step=0` (legacy `refine=` length accepted) | Positive maximum edge length; explicit override only. Do not supply both aliases. |
| `field` | required `cell=` grid length | Explicit override only; fixed facets provides a coarser lower bound. |
| `facets(n)` | segments per turn, or `"auto"` | Fixed n scales only under the override; auto chord tolerance scales as 1/density² and count bounds scale with density. |
| circles, arcs, fillets, softening, revolutions | inherited facets | Use the shared turn sampler; minimum topology counts remain. |
| spline, superellipse, text | automatic curve samples | Counts scale with detail. Explicit polygon vertices remain exact. |
| sweep, loft, wire, body | automatic path samples, `rings=` extra samples | Auto path counts and chord error scale; extra rings scale only under override. Explicit station/law knots remain. |
| extrude with twist | automatic layers | Angular spacing scales with detail. |
| blend | `step=None` (auto voxel size r/5), or positive voxel length | Voxel length scales with detail; r remains the closing radius. |
| gear, thread, knurl | automatic involute / thread sampling; knurl has feature-locked teeth | Gear flank and thread samples scale, teeth and turns stay fixed; knurl keeps four samples per tooth to preserve its V ridges. |
| along, frames, copy, scatter | placement counts / supplied paths | No independent mesh refinement; instance counts do not scale. |
| hull, fill, booleans, chamfer, shell, taper, dent | input topology / feature geometry | No density setting removes explicit topology or changes feature dimensions. |

Colour callbacks return **one RGB per face**, without UVs or textures. A fine
colour pattern therefore needs fine faces too. Prefer colour for thin veins or
grain over displaced relief when that relief is sub-millimetre at render scale;
choose only enough faces to resolve the visible pattern. Increasing displacement
feature frequency must not silently dictate the entire mesh: use `step` to set
its cost separately.

```python
s3d.detail(0.5)
s3d.displace(leaf, 3.2, 1.6, noise=tissue_relief, step=2)
s3d.bend(leaf, 25, step=5)
```
