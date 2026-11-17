# Emission, smoke and fog media, review rendering versus Cycles

## Flames

`material(flame, "light", color="#ff7b20", emission=4)` on actual tapered flame geometry: warm irregular
tongues around visible fuel, bright cores, dark char. Keep flames emissive and plume boundaries not.
Emission multiplies the **linear** base colour, near-linearly in strength: start at 0.3–1 for dim
embers, 2–4 for flame tongues, 8–12 for small hot cores. A black base emits nothing at any strength; a
saturated orange keeps its ratios until the display clips; a pale core needs a lighter base colour,
not only more strength.

## Smoke and fog

Build closed plume volumes with readable shape and density, not opaque grey balls:
`material(plume, "smoke", scatter="#b3aea8", scatter_distance=600)`; `fog` is lighter. A finely folded
`field` is still one uniform density, not filaments.

## Review renderer versus Cycles

The review renderer adds emission to the surface colour (it lights no neighbour, casts no volumetric
shadow, has no bloom) and shows a medium as tinted opacity `1 - exp(-sigma_s * path_length)` along its
ray path, combined with absorption, without anisotropy, indirect light or multiple scattering.

Cycles gets real Volume Scatter and Absorption nodes, and emission lights nearby surfaces. It stops
shadow rays at any refracting surface, IOR 1 included, so a clear non-emissive boundary around a medium
(no metallic, coat, sheen or emission) reaches Cycles as a transparent surface tinted by `color`: the
medium gets direct light and casts its shadow; GLB and EEVEE keep the Principled BSDF. Each boundary
crossing spends one transparent bounce (`scene.cycles.transparent_max_bounces`, default 8): a folded
envelope or noisy `field` can show black cracks along its outline; raise the limit.
`scene.cycles.volume_bounces` defaults to 0 (single scattering). sand3d changes no render setting;
exposure, lights and view transform change perceived brightness, so check both renderers.
