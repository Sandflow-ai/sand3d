---
title: Water
order: 1
lead: Still water, ripples, rivers, falls and foam. In sand3d water is a solid: dig a hollow into a closed solid, fill it to a level, tint it by depth, and put waves on its surface only.
---

## A first basin {#basin}

::: example solids_fill
note: A bowl cut into a stone and filled 15 mm under the rim. Three rings of waves move the free surface only, and the water is tinted by depth.
:::

## How water is made {#method}

Water fills the space the banks and the bottom enclose; the shore is where its surface meets them.

1. Dig the basin, channel or bowl into a closed solid with `cut`.
2. Fill it to a level with `fill`. The result is a new solid; its free surface is the face `top`.
3. Give it the `water` preset of `material`. `absorb` sets the colour the water takes with depth and `absorb_distance` how deep, in program units, it takes to reach it. Transmission and index of refraction stay the preset's. Add `scatter` for murky water.
4. Put ripples on the face `top` only, with `waves` as the noise of `displace`. The shore stays on the banks.

```python
s3d.cut(bank, s3d.at(hollow, z=depth - dig))
water = s3d.fill("water", bank, depth - margin)
s3d.material(water, "water", absorb="#5f9c8a", absorb_distance=800)
f = s3d.waves(wavelength, direction=30, sharpness=.5, spread=15, seed=seed + 3)
s3d.displace(water, swell, wavelength / 8, noise=f, direction="+Z", faces="top")
```

### Depth needs a bottom {#bottom}

The depth tint reads only if there is geometry behind the water: banks, a bottom under the surface, and contact at the shore. Water over nothing looks like tinted glass.

### Rings on still water {#rings}

Rings, as from rain or a dropped stone, are `waves` with `centers=` and `decay=`: each centre sends rings that fade with distance.

### Falls and jets {#falls}

A falling sheet, such as a waterfall or the jet of a fountain, is its own closed solid, swept or lofted along the fall and broken into several sheets, with foam where it lands. `waves` only moves a surface up and down: it has no horizontal motion, no overturning and no breaking.

### Foam {#foam}

Crests, spray and suds use the rough, diffuse `foam` preset. Water painted white does not read as foam.

### What the review renderer shows {#renderer}

The fast review renderer approximates refraction and the tinted medium along each ray. It has no caustics, no volumetric shadows, no anisotropy and no multiple scattering. Cycles renders the volume in full.

## A pond to adapt {#scenes}

::: scene start_pond
title: A garden pond
program: docs/examples/pond.py
note: A basin cut into the lawn gives the water a bottom and a shoreline. The swell parameter adds directional waves.
:::


## Verbs used {#verbs}

::: chips fill waves displace cut material
:::

Next: [Terrain and ground](guides/terrain) for the banks and beds the water rests on.
