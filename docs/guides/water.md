# Water, foam, absorption, fill, waves, falls and banks.

- **Water is a closed volume.** Never a single plane: model its bottom and sides
  too. Dig the basin, channel or bowl into a closed solid, then `fill` it to a
  level; the result's free surface is its face `top`. Tint by depth with `absorb`
  and `absorb_distance`; `foam` is a white diffuse preset for crests, spray and
  suds. Ripples go on the surface alone, so the shore stays on the banks:

  ```python
  s3d.cut(bank, s3d.at(hollow, z=depth - dig))
  water = s3d.fill("water", bank, depth - margin)
  s3d.material(water, "water", absorb="#5f9c8a", absorb_distance=800)
  f = s3d.waves(wavelength, direction=30, sharpness=.5, spread=15, seed=seed + 3)
  s3d.displace(water, swell, wavelength / 8, noise=f, direction="+Z", faces="top")
  ```

  A tilted channel needs closed ends below its level; a falling sheet of water
  (waterfall, fountain jet) is its own closed solid, swept or lofted along the fall.

Use material(ob, "water", absorb="#3f7f86", absorb_distance=150): distance is in program units; transmission and ior inherit the preset. Foam is a rough diffuse white surface, not water painted white. A closed basin can use fill("water", basin, level); fill finds bounded voids below a height or Frame. Default clearance overlaps 0.04 mm for contact; zero is exact contact. Give a river real banks and a bottom. waves(wavelength, direction=25, sharpness=.8, spread=15, seed=seed) returns a bounded scalar/array field, not geometry. Pass it to displace(water, amount, size, noise=wave, direction="+Z", faces="top") to leave walls fixed. Use circular centers plus decay for ripples; centers excludes direction/spread. A waterfall needs falling geometry, broken sheets and foam at impact; waves alone has no horizontal motion, overturning or breaking.

At 3ca794c the water preset has transmission=1, ior=1.333, roughness=.08,
absorb="#b8e8ed" at 1000 mm. Override absorb and absorb_distance independently of
surface color and opacity. material accepts thickness="auto" or a nonnegative
program-unit distance, ior, transmission, scatter, scatter_distance and
scatter_anisotropy. Add scattering for murky water; zero scatter_distance disables
it, while anisotropy ranges -1..1 (forward above zero).
Cycles sees absorption/scattering volume nodes and refracting boundaries;
skyscene review approximates their ray path and tinted medium opacity, omitting
caustics, volumetric shadows, anisotropy and multiple scattering. Foam remains a
rough diffuse surface. Keep banks, underwater bottom and contact at the shore:
water cannot read as depth without geometry behind it.
