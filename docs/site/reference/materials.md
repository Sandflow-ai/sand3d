---
title: Materials and media
order: 7
lead: Set a surface look, colour faces from their position, or fill a closed solid with an absorbing or scattering medium.
---

::: fiche material
sig: material(ob, kind, color=None, roughness=None, metallic=None, opacity=None, emission=None, absorb=None, absorb_distance=None, thickness="auto", ior=None, transmission=None, scatter=None, scatter_distance=None, scatter_anisotropy=None)
what: Apply a named preset with optional overrides to a part, group, assembly or list. Returns ob and leaves the mesh unchanged.
param ob: A solid or parent of solids, not a profile or path.
param kind: One of the 34 presets below; an unknown name raises with suggestions.
param color: Surface sRGB tint, #rrggbb or RGB triple in [0, 1], or a colour function.
param roughness: 0 to 1, from smooth reflections to rough reflections.
param metallic: 0 to 1, from dielectric to metal.
param opacity: Alpha in [0, 1]; 1 opaque, 0 invisible. Separate from transmission and absorption.
param emission: Nonnegative strength multiplying the linear base colour.
param absorb: sRGB colour white light becomes after absorb_distance, hex or RGB.
param absorb_distance: Finite nonnegative length in program units; zero disables absorption.
param thickness: auto or finite nonnegative length assumed by glTF raster viewers; zero disables its volume extension.
param ior: Finite index of refraction in [1, 1000].
param transmission: Fraction transmitted in [0, 1], independent of opacity.
param scatter: sRGB colour the medium scatters, hex or RGB.
param scatter_distance: Finite nonnegative scattering length in program units; zero disables scattering.
param scatter_anisotropy: Finite value in [-1, 1]; negative backward, zero isotropic, positive forward scattering.
limits: None inherits the preset. Each call chooses a preset and overrides, rather than modifying the previous call's overrides. No textures or UVs are created.
see: [Colour functions](reference/materials#colour-functions), [Export](reference/export#formats), [Material comparison examples](reference/materials#presets)
:::

## Inheritance on an assembly {#inheritance}

The nearest material call on a mesh or its ancestors wins, regardless of call order. A material on an assembly reaches all descendants without their own material, including details attached later. Apply one look to the whole assembly, then override individual parts. The [lamp example](reference/assembly#Handle) gives its frame brass and its shade painted metal.

The tag survives edits that rebuild the mesh, including cut, hole and fillet, and survives copy. A consumed tool loses its material with its geometry. Join and merge retain the first object's material and colour function. Material names record the preset and overrides.

## All presets {#presets}

These are untextured average colours. Wood presets do not create grain; brushed steel does not create grooves. There is no wood or coral preset. Unless listed otherwise, metallic, emission, transmission, coat and sheen are zero, opacity is 1, IOR is 1.5, and absorption and scattering are off. Distances in this table are physical millimetres; preset distances convert to the program's unit.

| Preset | sRGB | Roughness | Other values |
|---|---|---|---|
| oak | `#b48a5a` | 0.55 | Defaults |
| walnut | `#5e3b25` | 0.45 | Defaults |
| pine | `#d9b27c` | 0.6 | Defaults |
| birch | `#e2c9a0` | 0.55 | Defaults |
| steel | `#a8abb0` | 0.3 | metallic=1.0 |
| brushed_steel | `#b4b7bb` | 0.35 | metallic=1.0 |
| chrome | `#e6e8ea` | 0.05 | metallic=1.0 |
| aluminium | `#c9ccd0` | 0.4 | metallic=1.0 |
| brass | `#c9a24a` | 0.25 | metallic=1.0 |
| copper | `#c47a52` | 0.25 | metallic=1.0 |
| painted_metal | `#2b2d30` | 0.4 | coat=0.3 |
| plastic | `#d8d8d8` | 0.5 | Defaults |
| glossy_plastic | `#d8d8d8` | 0.12 | coat=0.5 |
| rubber | `#202020` | 0.9 | Defaults |
| glass | `#ffffff` | 0.0 | transmission=1.0 |
| ceramic | `#f2f0ea` | 0.15 | coat=0.6 |
| fabric | `#8a8f96` | 0.85 | sheen=0.6 |
| velvet | `#2f4f5f` | 0.9 | sheen=1.0 |
| leather | `#6b3e26` | 0.5 | Defaults |
| marble | `#e8e6e1` | 0.15 | coat=0.4 |
| concrete | `#9a9893` | 0.85 | Defaults |
| bark | `#69503b` | 0.9 | Defaults |
| leaf | `#52703d` | 0.5 | coat=0.12 |
| moss | `#596344` | 0.95 | Defaults |
| grass | `#68794a` | 0.8 | Defaults |
| rock | `#85827b` | 0.9 | Defaults |
| soil | `#66503c` | 1.0 | Defaults |
| sand | `#c5b58e` | 0.9 | Defaults |
| water | `#f4f8f8` | 0.08 | transmission=1.0, ior=1.333, absorb=#b8e8ed, absorb_distance=1000.0 |
| snow | `#eef1f3` | 0.85 | coat=0.03 |
| foam | `#f5f5f2` | 0.95 | Defaults |
| smoke | `#ffffff` | 0.0 | transmission=1.0, ior=1.0, scatter=#ffffff, scatter_distance=625.0, scatter_anisotropy=0.3, absorb=#d6d6d6, absorb_distance=1000.0 |
| fog | `#ffffff` | 0.0 | transmission=1.0, ior=1.0, scatter=#ffffff, scatter_distance=10000.0, scatter_anisotropy=0.3 |
| light | `#fff1dc` | 0.5 | emission=12.0 |

::: example mat_presets
note: oak, walnut, pine, birch, steel, brushed_steel.
:::

::: example mat_presets_metals
note: chrome, aluminium, brass, copper, painted_metal, plastic.
:::

::: example mat_presets_surfaces
note: glossy_plastic, rubber, glass, ceramic, fabric, velvet.
:::

::: example mat_presets_natural
note: leather, marble, concrete, bark, leaf, moss.
:::

::: example mat_presets_ground
note: grass, rock, soil, sand, water, snow.
:::

::: example mat_presets_media
note: foam, smoke, fog, light. Smoke and fog have no visible scattering in this GLB-based render; see [the Cycles plume](guides/fire-smoke#scenes) for a scattering medium.
:::

## Colour functions {#colour-functions}

A callable `color(x, y, z[, n[, u]])` has exactly three, four or five positional parameters, with no variadic or keyword-only parameters. Coordinates are face centres in the mesh's local frame, before placement, in program units. `n` is the outward unit normal. Return sRGB, with no alpha: a hex string or an RGB triple in [0, 1] for scalar calls.

`u` is construction progression, averaged over a face's vertices: along loft sections, along wire or sweep arc length, or bottom to top on revolve, dome, sphere, cone and cylinder. Caps get their end value. A five-parameter function refuses a part without this label.

::: example colour_weathering
note: The stone uses local height for its colour gradient. Moving the stone preserves the pattern within it.
:::

### Vectorized functions {#vectorized}

Prefer NumPy expressions that accept whole arrays. x, y, z and u have shape (k,) and dtype float64; n has shape (3, k), so use `n[2]` for upwardness. Return a finite numeric array of shape **(k, 3)** in [0, 1]. Rows are faces even when k is 3. Hex arrays and arrays shaped (3, k) do not qualify.

```python
import numpy as np

def weathered(x, y, z):
    height = np.clip(z / 120, 0, 1)
    low = np.array([.12, .08, .04])
    high = np.array([.48, .38, .22])
    return low + height[:, None] * (high - low)
```

A probe on up to eight faces chooses the array path, then a call covers every face. If the probe raises or returns another shape, evaluation falls back to one call per face with scalars and a normal tuple. Invalid array values raise. Write one vectorized path; no type branch is needed. Functions must be pure: the probe is an extra call and every export evaluates them again.

### Colour is a surface property {#colour-resolution}

Use broad height and moisture bands, directional grime, visible seeded noise and dust on upward faces. Do not paint lighting, highlights or shadows through the normal: the renderer supplies those. Grass and soil can have different group tints; leaves and snow can use height or normal masks. For fine fur, a matte plastic surface around roughness .85 avoids fabric's sheen.

One RGB value is stored per face, without UVs or textures. Fine freckles vanish on coarse meshes. Choose patterns that read at the existing resolution; do not refine or displace solely for finer colour. Relief is justified when it changes silhouette or material structure. Colour is preferable to sub-millimetre displaced grain and veins.

Copy keeps the callable; join and merge keep the first object's. Functions live only in the current session, not in saved Blender files. Placement, copy, merge, displace, bend, twist, taper, scale, lay and interpolating mesh edits keep construction labels. Joins between parameterized parts transfer labels, taking the first operand's at shared intersections. Booleans with an unparameterized operand, blend, field and new topology drop them; merge fills missing labels with NaN. Check that progression exists before using u.

GLB always writes callable colour on face corners as COLOR_0. OBJ, URDF and USD use the area-weighted mean in linear colour space. See [colors=](reference/export#export) for plain colours on corners too.

## Absorption, scattering and light {#media}

A medium fills a closed mesh uniformly. Its surface hides it when opaque. Smoke and fog supply an unseen boundary: transmission 1, IOR 1, roughness 0. Build one closed envelope with one medium, not stacked alpha shells. A finely folded field is still a uniform mass, not a density field of filaments.

Absorption removes light along its path. After depth x, transmittance is `linear(absorb) ** (x / absorb_distance)`. Scattering redirects light: channel c has coefficient `linear(scatter)[c] / scatter_distance`. For white scatter, the distance is the mean travel before scattering. Their extinction coefficients add. Zero distance disables the corresponding effect. Anisotropy is the Henyey-Greenstein g: negative backward, zero every way equally, positive forward, as a glow against backlight.

Light smoke mostly scatters; black smoke only absorbs. Add scatter to water for murk. Fog, mist, steam and cloud use fog, with shorter scatter_distance for denser volumes. Foam is a rough diffuse surface, not white transmitting water.

::: example fire_plume
note: A shaped smoke envelope over logs. The image shows the medium; a GLB viewer cannot reproduce its scattering and will show a darker absorbing mass.
:::

The light preset emits in its own colour. Emission multiplies **linear** base colour: black emits nothing; increasing saturated orange's strength does not turn it into a pale core. Use lighter colour for hot cores. Start around .3–1 for embers, 2–4 for flame tongues and 8–12 for small hot cores. Put light on tapered flame geometry around visible fuel, not on the plume boundary.

### What renderers preserve {#renderers}

The review renderer adds emission without lighting neighbours or bloom. It approximates a medium with tinted opacity `1 - exp(-sigma_s * path_length)` plus absorption, without volumetric shadows, anisotropy, indirect light or multiple scattering. Its fixed lights can look different from Cycles.

Cycles uses real Volume Scatter and Absorption; emission lights neighbours. A clear non-emissive boundary with no metallic, coat or sheen becomes a transparent surface tinted by color for Cycles, allowing direct light into the volume and a volume shadow. GLB and EEVEE retain the Principled surface. Each boundary crossing spends a transparent bounce: Cycles defaults to 8. Folded envelopes can show black cracks; raise transparent_max_bounces if needed. Volume bounces default to zero, single scattering. sand3d changes no render settings; check lights, exposure and view transform. See [Fire and smoke](guides/fire-smoke).

## Transmission needs thickness {#thickness}

Start from glass or water. Colour is surface tint, opacity is alpha, and transmission is the fraction passing through the surface. For depth tint, use absorb, not opacity. Give water, ice and crystals closed sides and a bottom, outward normals, recognisable thickness and something behind them to see through. Avoid coincident transparent shells. Water against banks and a bottom reads as water; over nothing it looks like tinted glass.

Cycles traces actual mesh depth. `thickness="auto"` instead tells glTF raster viewers one constant depth per material, estimated at export as 2 × volume / area of the meshes wearing it, D/3 for a sphere. An explicit length overrides the estimate. Zero omits the volume extension and disables absorption there. It creates no geometry. The review renderer approximates refraction, Fresnel reflection and absorption; it is not a path tracer.

GLB exports volume, IOR and transmission extensions; attenuation distances are world metres, thickness is in mesh units. glTF has no ratified scattering: total extinction becomes volume attenuation, so smoke and fog look dark, including after reimport into Blender. USD Preview Surface retains IOR and coat but no volume or sheen; its opacity is opacity × (1 − transmission), so fully transmitting media can disappear. IFC retains colour and transparency max(1 − opacity, .85 × transmission), with GLASS reflectance. OBJ writes callable colours as an averaged MTL diffuse colour, but currently omits plain preset colours and writes no vertex colour. URDF carries colour and opacity; STL neither. See [format contents](reference/export#formats).

## Scene lights {#lights}

::: fiche light
sig: light(name, kind="point", lm=None, lux=None, color="#ffffff", angle=None, blend=None, shadow=True, size=None)
what: Create a named point, spot, sun or ambient light. Place it with `at`, or give it a parent with `group` or `assembly`. Spot and sun lights shine along their local -Z axis.
param lm: Lumens for point or spot, 800 by default. A spot uses the lumens of the corresponding point source.
param lux: Illuminance for sun or ambient, 100,000 and 10,000 by default, respectively.
param color: sRGB hex string or an RGB triple in [0, 1].
param angle: A spot's full cone angle, from 1 to under 180 degrees, 45 by default. For a sun, the apparent width, 0.53 degrees by default.
param blend: The fraction of the spot cone over which intensity fades inward from the edge, 0.15 by default.
param shadow: False lets a point, spot or sun act as fill without a shadow. Ambient never casts shadows.
param size: Point or spot bulb diameter in program units, defaulting to the equivalents of 60 and 30 mm respectively. Zero gives a sharp shadow edge.
limits: A light has no mesh or bounding box of its own and cannot take solid edits. GLB carries point, spot and sun lights, USDA carries all four kinds, and IFC carries points and spots.
see: [Export formats](reference/export#formats)
:::
