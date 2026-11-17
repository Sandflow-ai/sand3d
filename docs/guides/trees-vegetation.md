# Branches, foliage, crown cost, grass, lawns, moss and fur

- **Trunks and branches** are tapering `wire` or `sweep` along `branches` paths; its tips carry buds.
- **Foliage**: vary scale, orientation and clusters with derived seeds. Prefer simple broad leaves
  that read at review scale, show the branch structure, keep roots in ground contact.
- **Crown cost** = leaf count × faces per leaf, plus twigs: thousands of finely tessellated leaves
  dominate the budget.

## Grass, lawns, moss and fur

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

Moss carpets the ground itself: cushions a few mm high from `displace` with features about a tenth
of the patch, two greens by noise, and a short pile (`tufts` height ≈ 7 mm, 3 blades, lean 45) for its
fuzzy edge: 4096 sites on 0.64 m² cost about 25k triangles. Patches: one 0..1 noise mask drives the
cushions, the colour and which sites keep pile, soil between them; a full carpet drops the mask.

```python
import numpy as np
patch = lambda x, y: np.clip((s3d.noise(x / 160, y / 160, 0, seed=5) - .2) * 4, 0, 1)   # 0..1 mask
s3d.displace(ground, 10, 60, faces="top", direction="+Z", step=14,
             noise=lambda x, y, z: patch(x, y) * (.6 + .4 * s3d.noise(x / 30, y / 30, 0, seed=6)))
s3d.material(ground, "soil", color=lambda x, y, z, n:
             np.where((patch(x, y) > .3)[:, None], [.26, .40, .08], [.22, .16, .10]))
keep = lambda f: f.normal.z > .85 and patch(f.origin.x, f.origin.y) > .3
pile = s3d.tufts("moss", s3d.Frames(f for f in s3d.scatter(4096, ground, seed=3) if keep(f)),
                 height=7, width=3, blades=3, lean=45, seed=4)
s3d.material(pile, "moss", color="#5a6e1c")
```

Textile nap: scatter on the fabric carrier, keep its visible side, then short wide cones for clumps or
thin blades for bristles, the carrier visible between clumps. A tangent `direction` field combs fur;
the default site normal gives standing pile. Animal fur: dense short thin blades combed
along the body on a matte material (`plastic`, roughness ≈ .85); cones read as scales, and `fabric`'s
white sheen greys dark fur. Group carrier and tufts after querying: their frames share
one parent space.

```python
import numpy as np
def comb(x, y, z, n):                    # toward -X, laid on the surface, slightly lifted
    n = np.asarray(n).T                  # (N, 3)
    t = np.array([-1.0, 0, -.25])
    return t - (n @ t)[:, None] * n + .3 * n
sites = s3d.Frames(f for f in s3d.scatter(4096, body, seed=2) if f.normal.z > -.5)
fur = s3d.tufts("fur", sites, height=34, width=6, blades=7, lean=14, direction=comb, seed=6)
s3d.material(fur, "plastic", color="#6b4423", roughness=.85)
```
