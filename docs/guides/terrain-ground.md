# Strewn stones and leaves, snap, lay, displacement and contact.

- **Things strewn on uneven ground.** Never compute where a stone lands from the
  terrain's own formula. Sample the ground itself, keep the sites a plain
  condition allows, and seat each object on its site. `scatter(n, ground)` covers
  the whole closed surface, sides and underside included: ask for about ten times
  the sites you keep, filter on `f.normal` (slope) and `f.origin` (where), and
  check how many remain.

  ```python
  sites = s3d.scatter(10 * n, ground, seed=seed + 4)
  level = math.cos(math.radians(steepest))
  sites = s3d.Frames([f for f in sites if f.normal.z > level and abs(f.origin.y) > channel])[:n]
  rocks = [s3d.at(stone(f"stone{k}", d, seed * 100 + k), on=site.offset(-d / 4))
           for k, (site, d) in enumerate(zip(sites, s3d.vary(size, size / 3, n, seed=seed + 5)))]
  ```

  `at(ob, on=site)` stands an object along the local normal (`site.offset(-d/4)`
  sinks it a quarter); `lay(at(leaf, on=site), ground)` seats a flat piece on the
  surface under it; `snap(ground, [(x, y, above)], direction="-Z")` finds the
  ground under a chosen spot, and `Frame(hit.origin)` keeps an upright post upright.

Make terrain as a supported solid and displace its top. displace accepts named or callable noise and direction="+Z"; amount is displacement, size is feature scale, refine controls added topology. noise accepts scalar or broadcastable arrays, values in [-1,1]; ridged/turbulence transform gradient noise. snap(targets, points, direction="-Z") finds contact points in their shared frame. lay(ob, over, refine=0, reach=None) seats a placed piece along its own Z while preserving height above local Z=0. Derive vegetation and rock contact from terrain rather than guessing world Z. Give composition ground enough area to support the subject; avoid hidden floating islands.
