# Transmission, IOR, absorption, thickness and closed crystals

Start from `glass` or `water`; override `transmission`, `ior` or `roughness` only when needed. Give ice
and crystals closed thickness, recognisable facets and a background or bank to see through. Tint with
`absorb`, not opacity: alpha is not absorption, and colour, opacity and transmission are separate.
`thickness` only informs glTF raster viewers (`"auto"`: 2 × volume / area at export); Cycles follows the
real mesh. Avoid stacked coincident transparent shells. The review renderer approximates refraction,
Fresnel reflection and absorption; it is not a path tracer.
