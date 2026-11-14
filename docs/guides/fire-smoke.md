# Emission, smoke/fog media and review rendering versus Cycles.

Use material(flame, "light", color="#ff7b20", emission=4) on actual tapered flame geometry. Layer warm irregular tongues around visible fuel, with bright cores and dark char. Emission adds linear colour to the review image; it does not illuminate nearby geometry, cast volumetric shadows or create bloom. Smoke and fog presets are invisible boundaries containing scattering media: build closed plume volumes. material(plume, "smoke", scatter="#b3aea8", scatter_distance=600) controls scattering per unit; fog is lighter by preset. Zero scatter_distance disables scattering. The raster review approximates opacity by 1-exp(-sigma_s*path_length), tinted per channel; anisotropy and multiple scattering are not simulated. Use readable plume shape and density, not opaque grey balls.

At sand3d 3ca794c, smoke/fog set transmission=1, ior=1 and roughness=0 to expose
their volume. Smoke presets scatter_distance=625 mm, scatter_anisotropy=.3,
absorb="#d6d6d6" at 1000 mm; fog scatters at 10000 mm. Explicit distances use
program units. sigma_s[c]=linear(scatter)[c]/scatter_distance; absorption adds
extinction independently. Black smoke can absorb without scattering. The density
is constant within each envelope: a finely folded field is not filamentary density.
Keep flames emissive and plume boundaries non-emissive.

Review renderer versus Cycles: skyscene adds emission to the surface colour and
approximates a medium as tinted opacity 1-exp(-sigma_s*l) along its peeled ray
path, combined with absorption. It has no volumetric shadow, anisotropy, indirect
lighting or multiple scattering. Cycles receives actual Volume Scatter and
Absorption nodes. For a clear non-emissive smoke/fog boundary sand3d substitutes
a colour-tinted transparent surface in Cycles, allowing direct light and volume
shadows; GLB/EEVEE keep Principled. Each boundary crossing spends a transparent
bounce (Cycles default 8): folded envelopes can show black edge cracks; raise
transparent_max_bounces if needed. volume_bounces defaults to 0, so multiple
scattering needs an explicit scene setting. sand3d does not change render settings.
