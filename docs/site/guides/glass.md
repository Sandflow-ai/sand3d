---
title: Glass and ice
order: 7
lead: Transparent objects need thickness and something to see through them. Build closed crystals or ice masses, preserve their facets, then use absorption to tint light as it travels through the material.
hero: glass_crystals
---

## Two closed crystals {#crystals}

::: example glass_crystals
note: Two hexagonal crystals share one absorption colour and distance. Their different widths give light different depths to travel through. The pale base provides a visible background.
:::

A hull around two rings and a tip closes each crystal. Its planar faces give the transparent surface a readable outline and changing reflections. A thin open sheet does not provide the same enclosed depth.

## Build the shape, then the medium {#method}

1. Give the ice or crystal a closed volume and recognisable facets. Choose the silhouette before the tint.
2. Put a background, ground or bank behind it. Refraction and absorption need something visible through the object.
3. Start from the `glass` or `water` preset of [material](reference/materials#material). Keep its transmission, index of refraction and roughness unless the intended appearance needs an override.
4. Set `absorb` and `absorb_distance` for the depth tint. The absorption colour describes what white light becomes after travelling that distance in program units.

Colour, opacity and transmission are separate controls. Surface colour tints the surface; transmission lets light pass through it. Lowering opacity does not make a depth-dependent absorbing medium. Use absorption for coloured glass or ice instead of alpha.

See [material](reference/materials#material) for the controls and their ranges. Avoid stacked coincident transparent shells: use deliberate closed volumes with clear boundaries.

## Thickness in different viewers {#thickness}

The `thickness` material parameter informs glTF raster viewers. Its default, `"auto"`, is estimated at export as twice the volume divided by the surface area. It is a viewing hint, not an operation that thickens the mesh. Cycles follows the actual depth of the closed geometry instead.

The review renderer approximates refraction, Fresnel reflection and absorption. Use Cycles to assess full light transport.


## Verbs used {#verbs}

::: chips hull ring material at
:::

Next: [Resolution and cost](guides/resolution) to keep the geometry budget proportional to the visible shape.
