---
title: Colour and weathering
order: 6
lead: Put weathering where it can be read: broad height gradients, moisture bands, directional grime and seeded patches. Colour is sampled per face, so its smallest useful scale depends on the mesh.
---

## A first height gradient {#gradient}

::: example colour_weathering
note: A dark lower band gives way slowly to a lighter brown. The displacement shapes the stone; the colour function adds no geometry.
:::

The function works in the part's local coordinates. It maps heights from 0 to 100 to a fraction between zero and one, then changes the rate of the blend: the first 40 percent of that height range covers only 20 percent of the colour change. Below 30 it returns the dark colour outright. These thresholds are in program units, millimetres in this toy, and moving the stone does not move the pattern within it.

The NumPy operations evaluate many face centres at once. The resulting array has one RGB triplet per face. The same function can dress bark with `s3d.material(part, "bark", color=weathered)`. See [material](reference/materials#material) for colour callbacks, coordinate and normal inputs, and return formats.

## Choose a visible scale {#scale}

A colour function is evaluated at face centres, not at every image pixel. A freckle smaller than a face may disappear entirely. Start with broad gradients and patches, then inspect the result at the intended image size.

- Height bands can darken a base or lighten an exposed top.
- Moisture bands can mark the region near soil or a waterline.
- Directional grime can use the face normal to distinguish upward surfaces from walls and undersides.
- Seeded noise can break the edges of those regions at a visible scale. Keep the callback deterministic, without advancing random state.

The [material reference](reference/materials#material) describes how to combine those inputs. [Noise](reference/paths#noise) supplies repeatable spatial variation.

## Spend geometry on shape {#geometry}

Never refine or displace a mesh only to carry finer colour. Widen the colour pattern instead. Relief earns its faces when it changes the silhouette or the material's structure, such as deep bark grooves or raised rock grain. Paint alone can describe a stain; it cannot make that stain cast a geometric shadow.


## Verbs used {#verbs}

::: chips material noise displace field
:::

Next: [Glass and ice](guides/glass) for colour that depends on the depth light travels through a solid.
