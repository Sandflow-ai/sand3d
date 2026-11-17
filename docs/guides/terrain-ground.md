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

Make terrain as a supported solid and displace its top. displace accepts named or callable noise and direction="+Z"; amount is displacement, size is feature scale, step controls added topology. noise accepts scalar or broadcastable arrays, values in [-1,1]; ridged/turbulence transform gradient noise. snap(targets, points, direction="-Z") finds contact points in their shared frame. lay(ob, over, step=0, reach=None) seats a placed piece along its own Z while preserving height above local Z=0. Derive vegetation and rock contact from terrain rather than guessing world Z. Give composition ground enough area to support the subject; avoid hidden floating islands.

## Select sites once, place through one helper

Filter the frames returned by scatter or phyllotaxis with one predicate, then
reuse a placement helper for all accepted sites. Do not duplicate nearly identical
loops for two plant or stone populations. Record the achieved count: filtering
can yield fewer than the requested number. Increasing samples or changing the
predicate changes the distribution and random draws; it is not an equivalent
refactor. `keep_site(frame)` and `place_item(frame, seed)` below are local helpers
you write, not API verbs.

```python
def keep_site(frame):
    x, y, z = frame.origin
    return z > 5 and x*x + y*y > 400

def place_item(site, seed):
    return s3d.at(make_stone(seed=seed), on=site)

sites = s3d.scatter(120, terrain, seed=seed + 1)
selected = [site for site in sites if keep_site(site)]
parts = [place_item(site, seed=seed + 100 + i)
         for i, site in enumerate(selected)]
```

Respect frames: a sampled mesh site's frame is in that mesh's parent space.
Use on=site for its full orientation; adding translations manually is only valid
for aligned axes. Offsets after on= run along that frame's axes. Do not mix local
callback coordinates, parent-space sites and world-space positions. Choose the
actual parent surface before snap/lay and preserve the return/prototype-consumption
contract of at when placing a prototype on multiple frames.

Resolution costs triangles: use `step` to separate displacement feature size
from mesh sampling (see `resolution`).
Colour callbacks assign one RGB per face without UVs or textures, so fine colour
patterns need fine faces. Prefer colour for thin veins or grain over displaced
relief that is sub-millimetre at render scale.

## Sand and dunes

Start with a supported solid. Displace top faces with low-frequency noise for
broad relief; keep the underside flat. Wind makes asymmetric dunes: a long gentle
windward slope and a short slip face near 32° (rise / run ≈ 0.625). A symmetric
sine gives ripples, not that dune profile. Keep small ripple relief separate from
the large dune field. `waves()` is a general XY height field, not water-only:
pass it as `noise` to `displace(..., faces="top", direction="+Z")`.

```python
import numpy as np
sand = s3d.box("sand", 3000, 2000, 100)
s3d.displace(sand, 15, 500, seed=4, faces="top", direction="+Z", step=80)
def dune(x, y, z):
    q = ((x + 800) % 1600) / 1600
    return np.where(q < .8, q / .8, (1-q) / .2)
s3d.displace(sand, 200, 80, noise=dune, faces="top", direction="+Z", step=80)
s3d.displace(sand, 3, 120, noise=s3d.waves(120, direction=0),
             faces="top", direction="+Z", step=40)
s3d.material(sand, "sand", color=lambda x,y,z,n:
             (.82,.68,.43) if n[2] > .95 and z > 220 else (.64,.49,.28))
```

The 200-high dune's 320-long slip face gives about 32° before noise and ripples;
selected-face boundaries taper displacement to zero. Normal-based colour marks
flatter crests versus slopes; combine normal and height rather than colouring
all upward faces as crests. `sand` supplies the rough material response; avoid
modelling individual grains. Budget ripple sampling across the whole ground.
