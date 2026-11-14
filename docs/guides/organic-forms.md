# Outline, hull rocks, holes, folds, brain coral and scalar fields.

- **Outline first, surface second.** A natural form reads as irregular by its
  silhouette and proportions before its skin. Small noise on a symmetric base gives
  a rough skin on a regular shape. Break the outline first (uneven points for
  `hull`, uneven lengths with `vary`, a lean with `bend`, `twist` or `taper`, a
  `displace` whose features are about as large as the part), then add grain:

  ```python
  form = s3d.hull("form", sites.jitter(x=lean, y=lean, seed=seed))   # uneven proportions
  s3d.bend(form, tilt)                                               # the whole form leans
  s3d.displace(form, swell, size=width, seed=seed + 1)              # the outline moves
  s3d.displace(form, grain, size=grain_size, seed=seed + 2)         # then the skin
  ```

- **Faceted rock.** `BoulderFactory.py:stone` builds `hull` from seeded
  `scatter(..., surface=True).jitter(...)` points. Hull point count sets the
  large facets; broad displacement breaks convexity, fine displacement adds grain.

- **Holes and folds.** The field examples `field/BrainCoralFactory.py`,
  `field/DiffGrowthBaseCoralFactory.py` and
  `field/ReactionDiffusionBaseCoralFactory.py` define volumes with `field` and
  seeded `noise`. Use density for cavities, tunnels and folded sheets; use
  `displace` for relief on an existing surface. Keep callbacks deterministic,
  vectorize with numpy, leave one cell of boundary margin and choose a cell
  small enough for the narrowest feature. Start coarse to fit the build budget.

field(name, size, density, cell=..., level=0) makes a closed isosurface of density(x,y,z)<level, centered XY with Z=0..h. Use pure numpy array callbacks for the fast path. Cell controls smallest feature and cost; halving it roughly quadruples surface faces. Combine smooth density fields with noise or waves for brain-coral ridges, fungal lobes and rock masses. waves supplies periodic/radial scalar patterns, not only water. blend(ob,*others,r=...) fuses on voxels of r/5; displace adds relief, dent makes local depressions, hull wraps convex masses and loses concavities. Choose the verb matching structure before adding noise. Preserve attached coral branches, fungal stems and meaningful rock silhouettes; avoid fine fields merely to add colour.
