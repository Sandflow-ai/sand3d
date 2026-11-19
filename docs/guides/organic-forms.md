# Faceted rock, holes, folds, coral and fungi

- **Faceted rock**: `hull` over seeded `scatter(..., surface=True).jitter(...)` points. The point count
  sets the large facets; broad displacement breaks convexity, fine displacement adds grain.
- **Holes and folds**: `field` density, with seeded `noise` or `waves`, for cavities, tunnels, folded
  sheets, brain-coral ridges, fungal lobes and rock masses; `displace` for relief on an existing
  surface. Start coarse to fit the build budget.
- **Choose the verb by structure before adding noise**: `blend` fuses masses, `displace` adds relief,
  `dent` makes local hollows, `hull` wraps a convex mass and loses concavities.
- Keep attached coral branches, fungal stems and meaningful rock silhouettes; never refine a field only
  to carry colour.
