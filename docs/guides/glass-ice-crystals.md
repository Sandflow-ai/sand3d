# Transmission, IOR, absorption, thickness and closed crystals

Start from `glass` or `water`; override `transmission`, `ior` or `roughness` only when needed. Give ice
and crystals closed thickness, recognisable facets and a background or bank to see through. Tint with
`absorb`, not opacity: alpha is not absorption, and colour, opacity and transmission are separate.
Cycles uses the ray length through the mesh. glTF raster readers with volume support use the
material's `thickness` (`"auto"` estimates 2 × volume / area at export). A thickness of 0 disables the
medium in both. Avoid stacked coincident transparent shells.
