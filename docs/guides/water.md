# Water, foam, waves, falls and banks

- **Water follows a relief through `fill`**, not a copy of the terrain: the existing banks and bottom
  bound it. Dig the basin, channel or bowl into a closed solid, then fill it to a level; its free
  surface is the face `top`. Tint by depth with `absorb` and `absorb_distance` (program units;
  transmission and IOR stay the preset's); murky water adds `scatter`. Ripples go on the surface
  alone, so the shore stays on the banks:

  ```python
  s3d.cut(bank, s3d.at(hollow, z=depth - dig))
  water = s3d.fill("water", bank, depth - margin)
  s3d.material(water, "water", absorb="#5f9c8a", absorb_distance=800)
  f = s3d.waves(wavelength, direction=30, sharpness=.5, spread=15, seed=seed + 3)
  s3d.displace(water, swell, wavelength / 8, noise=f, direction="+Z", faces="top")
  ```

- **Depth needs geometry behind it**: banks, an underwater bottom and contact at the shore.
- **Rings on still water** are `waves(centers=…, decay=…)`.
- **A falling sheet** (waterfall, fountain jet) is its own closed solid, swept or lofted along the
  fall, broken into sheets, with foam at the impact: `waves` has no horizontal motion, overturning or
  breaking.
- **Foam** (crests, spray, suds) is the rough diffuse `foam` preset, not water painted white.
- **The review renderer** approximates refraction and the tinted medium along its ray path; it has no
  caustics, volumetric shadows, anisotropy or multiple scattering. Cycles renders the volume.
