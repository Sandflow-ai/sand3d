# Terrain, strewn stones, leaf litter, gravel, snow, contact, sand and dunes

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

## Leaf litter, gravel and snow

Covers belong to the ground: a dark ground colour under them reads as depth, so fill the view, not
every gap.

- **Leaf litter**: one-blade `tufts` laid flat, 2 triangles a leaf: width about half the length, a
  `direction` field tangent to the ground with a random azimuth and a slight lift. Dense: a few
  `scatter` calls of 4096 on dark soil (three gave about 5,500 leaves on 0.64 m², 14k triangles), plus a few
  twigs at their site's height (`cylinder` turned `ry=90`). Sparse: a few dozen leaves. One mesh,
  2–3 autumn tones by noise.

  ```python
  import numpy as np
  def flat(x, y, z, n):                    # random azimuth on the surface, slightly lifted
      a = 6 * np.pi * (.5 + .5 * s3d.noise(x / 9.7, y / 9.7, 0, seed=1))
      t = np.stack([np.cos(a), np.sin(a), 0 * a], 1)
      n = np.asarray(n).T
      return t - np.sum(t * n, 1)[:, None] * n + .12 * n
  sites = s3d.Frames(f for f in s3d.scatter(4096, ground, seed=10) if f.normal.z > .7)
  leaves = s3d.tufts("leaves", sites, height=42, width=24, blades=1, lean=12, direction=flat, seed=20)
  s3d.material(leaves, "leaf", color=lambda x, y, z, n: np.where(
      (s3d.noise(x / 23, y / 23, 0, seed=2) > 0)[:, None], [.70, .45, .12], [.42, .20, .06]))
  ```
- **Gravel**: the bed is the ground with fine relief (features about three grains wide) and a dark
  per-face speckle, plus pebbles: each a `hull` of 8 surface points (≈ 12 triangles) seated by
  `at(p, on=site.offset(-d * .15))`, one material on their group. Pebbles under about 1/25 of the
  patch's width vanish at render size: 450 of 30–60 mm on 800 mm cost 25k with the bed. Sparse: 20–30
  larger pebbles on soil.
- **Snow**: a blanket is the ground in `snow`, not a separate layer: drifts from a 0..1 callable
  (`perlin` seldom reaches its `amount`: two features across 800 mm rose at most 10 of 45), soil
  colour kept on the sides below the snow line, slopes tinted blue-grey by normal (flat white hides
  relief). Snow on objects: colour by `n[2]`. A dusting is colour only: soil mixed toward white by
  noise × `n[2]`⁴; the face size sets its grain.

  ```python
  import numpy as np
  drift = lambda x, y, z: (.5 + .5 * s3d.noise(x / 160, y / 160, 0, seed=0)) ** 2   # 0..1 mounds
  s3d.displace(ground, 110, 160, noise=drift, faces="top", direction="+Z", step=16)
  s3d.material(ground, "snow", color=lambda x, y, z, n: np.where((z < 40)[:, None], [.25, .18, .11],
               [.55, .62, .74] + np.clip(n[2], 0, 1)[:, None] ** 4 * [.35, .30, .21]))   # soil sides
  ```

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
