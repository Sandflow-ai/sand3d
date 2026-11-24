---
title: Fire and smoke
order: 2
lead: Build the flame as a solid and the smoke as a closed volume. Shape, colour and density do different jobs; emission alone does not make a fire.
hero: fire_tongues
---

## A first fire {#first-fire}

::: example fire_tongues
note: Three tapered tongues above dark logs. Smaller, paler cores distinguish the hottest parts from the orange outer flame.
:::

## Shape before brightness {#flames}

Keep the fuel visible. Build irregular, tapering tongues with [wire](reference/solids#wire) or a loft, place bright cores near their bases, and leave dark char between them. A single glowing lump loses both the fuel and the flame silhouette.

Apply the `light` preset with [material](reference/materials#material): `s3d.material(flame, "light", color="#ff7b20", emission=4)`. Keep the flames emissive and the smoke boundary non-emissive.

Emission multiplies the **linear** base colour. These are starting strengths, not promises about the rendered brightness:

| Part | Starting strength |
|---|---|
| Dim embers | 0.3–1 |
| Flame tongues | 2–4 |
| Small hot cores | 8–12 |

A black base emits nothing, however high the strength. Saturated orange keeps its channel ratios until the display clips. Give a pale core a lighter base colour; increasing orange's strength alone is not a colour change. Before clipping and display transforms, emitted light scales with strength.

## A volume for smoke and fog {#media}

Make a closed envelope with a readable plume shape, then give its interior a scattering medium. Opaque grey balls describe a surface, not smoke. For example, `s3d.material(plume, "smoke", scatter="#b3aea8", scatter_distance=600)` gives light a distance over which to scatter; the `fog` preset is lighter. See [material](reference/materials#material) for colour, distance and anisotropy controls.

A [field](reference/solids#field) can make a bent, uneven envelope. Folding that envelope finely does not produce density filaments: the density inside is still uniform. Choose the silhouette and the optical depth separately.



## Review and final rendering {#renderers}

The fast review renderer adds emission to the surface colour. It does not light neighbours, produce bloom or cast volumetric shadows. Its medium is tinted opacity along a ray: `1 - exp(-sigma_s * path_length)`, combined with absorption. It does not model anisotropy, indirect light or multiple scattering.

Cycles receives Volume Scatter and Volume Absorption nodes, and emission lights nearby surfaces. Its shadow rays stop at refracting surfaces even at an index of refraction of 1. To let direct light reach a medium, sand3d supplies a Cycles-only transparent boundary when the surface has transmission 1, IOR 1, roughness 0, and no metallic, coat, sheen or emission. That boundary is tinted by the base colour, with opacity taken into account. The medium can then receive light and cast its shadow. GLB and EEVEE retain the Principled BSDF.

### Dark cracks on the outline {#bounces}

Every boundary crossing consumes a transparent bounce. Blender's `scene.cycles.transparent_max_bounces` starts at 8; a folded envelope or noisy field may cross too many boundaries and show black cracks. Raise this render setting when needed. `scene.cycles.volume_bounces` starts at 0, meaning single scattering.

sand3d does not change render settings. Exposure, lighting and the view transform change perceived brightness, so check both the review and Cycles render. The live renderer used for the plume image raises the transparent-bounce limit itself. GLB has no scattering representation: its exported attenuation is not a substitute for the Cycles image.

## Scenes {#scenes}

::: scene fire_plume
title: Smoke above a hearth
program: docs/site/toys/fire_plume.py
note: A closed field bends the plume above visible logs and a stone ring. This image uses the live Cycles scene; the GLB viewer cannot reproduce its scattering medium.
:::

## Verbs used {#verbs}

::: chips wire cone field material group
:::

Next: [Trees, grass and fur](guides/trees) for branching shapes and surface cover.
