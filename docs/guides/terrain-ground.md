# Terrain, strewn stones and leaves, contact, sand and dunes

- **Terrain** is a supported solid with its top displaced, wide enough to carry the subject; no hidden
  floating islands.
- **Things strewn on uneven ground**: never compute where a stone lands from the terrain's formula.
  Sample the ground itself, keep the sites a plain condition allows, seat each object on its site.
  `scatter(n, ground)` covers the whole closed surface, sides and underside included: ask for about ten
  times the sites you keep, filter on `f.normal` (slope) and `f.origin` (where), and check how many
  remain.

  ```python
  sites = s3d.scatter(10 * n, ground, seed=seed + 4)
  level = math.cos(math.radians(steepest))
  sites = s3d.Frames([f for f in sites if f.normal.z > level and abs(f.origin.y) > channel])[:n]
  rocks = [s3d.at(stone(f"stone{k}", d, seed * 100 + k), on=site.offset(-d / 4))
           for k, (site, d) in enumerate(zip(sites, s3d.vary(size, size / 3, n, seed=seed + 5)))]
  ```

  `at(ob, on=site)` stands an object along the local normal (`site.offset(-d/4)` sinks it a quarter);
  `lay(at(leaf, on=site), ground)` seats a flat piece on the surface under it;
  `snap(ground, [(x, y, above)], direction="-Z")` finds the ground under a chosen spot, and
  `Frame(hit.origin)` keeps an upright post upright.

## Sand and dunes

Displace the top faces of a supported solid with low-frequency noise for broad relief; keep the
underside flat. Wind makes asymmetric dunes: a long gentle windward slope and a short slip face near
32° (rise / run ≈ 0.625); a symmetric sine gives ripples, not that profile. Keep the small ripples
separate from the large dune field. A straight crest reads as a ramp: bend it (the sine on x below).

```python
import numpy as np
sand = s3d.box("sand", 3000, 2000, 100)
s3d.displace(sand, 15, 500, seed=4, faces="top", direction="+Z", step=80)
def dune(x, y, z):
    q = ((x + 180 * np.sin(y / 420) + 800) % 1600) / 1600   # sinuous crest
    return np.where(q < .8, q / .8, (1-q) / .2)
s3d.displace(sand, 200, 80, noise=dune, faces="top", direction="+Z", step=60)
s3d.displace(sand, 8, 120, noise=s3d.waves(110, direction=10),
             faces="top", direction="+Z", step=30)
s3d.material(sand, "sand", color=lambda x,y,z,n:
             np.where(((n[2] > .95) & (z > 220))[:, None], [.82,.68,.43], [.64,.49,.28]))
```

About 35k triangles; the 200-high dune's 320-long slip face gives about 32°. Ripple relief under about
1/400 of the scene's width vanishes at render size (3 mm on 3 m did). Colour crests by normal and
height together, not every upward face. `sand` gives the rough response: model no grains. Budget
ripple sampling across the whole ground.
