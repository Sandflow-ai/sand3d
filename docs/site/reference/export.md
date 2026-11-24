---
title: Export and settings
order: 9
lead: Choose the program's length unit before building, control resolution as you build, then export the assembly in metres.
---

::: fiche export
sig: export(root, path, colors="material")
what: Write the root and its descendants. GLB, URDF and USDA also include parts hanging from it through joints. The filename extension selects the format; every format is scaled to metres.
param root: Root object or Handle, not the whole scene implicitly.
param path: Output filename ending in .glb, .urdf, .usda, .ifc, .obj or .stl.
param colors: material keeps plain colours in materials. vertex is GLB-only: plain and callable colours go on face corners, sharing white materials for the same non-colour look.
limits: Callable colours always use face corners in GLB. Emissive materials retain their colour, or the area-weighted mean of a colour function, because emission reads that colour. Other colors values, or vertex with another format, raise.
see: `material`, `units`, `pose`
```python
import sand3d as s3d
part = s3d.box("part", 20, 30, 10)
for suffix in ("glb", "urdf", "usda", "ifc", "obj", "stl"):
    s3d.export(part, "part." + suffix)
```
:::

## What each format contains {#formats}

| Format | Pose | Contents |
|---|---|---|
| .glb | Current | Materials, joint-nested nodes and joint descriptions in extras; callable colour as COLOR_0 |
| .urdf | Rest | A link per moving part, joint tree and limits, colour and opacity; OBJ meshes in a sibling stem_meshes directory |
| .usda | Rest | URDF's link and joint tree in UsdGeom and UsdPhysics, materials, Z up; OpenUSD text |
| .ifc | Current | IFC4 project, assemblies and proxies, triangulated face sets, surface materials; no joints |
| .obj | Current | Meshes, Y up; callable colours averaged into a sibling .mtl file; no mechanism |
| .stl | Current | Binary triangle meshes, Z up; no materials or joints |

For IFC, OBJ and STL, put every required part under the exported root with group or assembly: a part connected only by a joint but outside that object tree is omitted.

Posing a door open changes GLB, IFC, OBJ and STL geometry. URDF and USDA keep the same rest mechanism whatever pose was displayed. Joint extras in GLB describe the mechanism; they are not a baked animation. The [gate](reference/assembly#gate) is an example to export in either state.

IFC GlobalIds can change with geometry or placement and can repeat across models. They are not durable cross-model identifiers. Revit's native .rvt and related formats are refused: export IFC and open or link it in Revit. For binary USD or a USD package, write .usda and convert with USD tools; .usd, .usdc and .usdz are not written directly.

These formats describe geometry and kinematics. Masses, friction, effort limits and drives belong to dynamics and are not specified here. STL's numbers are metres even though STL does not declare a unit; check the importing application's interpretation.

### Materials across formats {#materials}

GLB carries transmission, KHR_materials_ior and KHR_materials_volume; distances are world metres, thickness mesh units. Scattering becomes total extinction, not real scattering. USD Preview Surface retains IOR and coat, no volume or sheen, and maps transmission to opacity × (1 − transmission); fully transmitting parts may disappear. IFC uses surface colour, GLASS reflectance and transparency max(1 − opacity, .85 × transmission).

OBJ, URDF and USD replace colour functions with their area-weighted linear mean. OBJ writes the callable mean as an MTL diffuse colour, not vertex colour; plain preset colours are currently omitted. URDF stores colour and opacity; STL stores none. See [media and thickness](reference/materials#thickness) before choosing a format for glass, water or smoke.

## Resolution while building {#resolution}

::: fiche facets
sig: facets(n=None, smooth=...)
what: Read the current segments per full turn, or set an integer count of at least 3 or auto. As a context manager, restore the previous count and shading configuration on exit, including on error.
param n: None reads the setting; auto is the default, using a 0.05 mm chord tolerance, usually 24–64 segments per turn.
param smooth: Fixed counts shade flat unless True is chosen at the first setting call. Later calls inherit that choice; use smooth(ob) to override one part.
limits: Explicit smooth=True requires a fixed count. Changing the program's chosen fixed-count shading later raises. Counts affect subsequent construction, not already-built meshes.
see: `smooth`, [Resolution guide](guides/resolution)
:::

`facets(8)` remains active until changed. `with facets(8):` confines it to the block. Build a spline and its wire or sweep in the same block: changing the count on the solid does not remove stations already sampled into a path. A quarter-circle gets roughly n/4 segments; straight spans keep their stations. Gear teeth and knurl and thread turns use their own sampling.

Fixed counts control turns across and along sweep, loft, wire, body and spline paths. On axisless surfaces the target edge is L = π D / n, where D is the largest local bounding-box dimension. Field uses max(cell, L); displace uses max(size/4, D/128, L) unless step is explicit. Blend keeps its voxel closing then targets 4 × area / (√3 L²) triangles, at least four, retaining the original if collapse breaks manifoldness. Hull keeps its explicit points. Increase n if thin branches or cavities disappear.

Budget all copies before detailing a prototype. Start coarse and inspect the silhouette at final display size. Facets and rings are counts; cell and step are lengths. Increasing either kind of resolution costs faces. `smooth` changes shading, persists through edits and copies, and does not add geometry.

## Fresh scene and units {#settings}

::: fiche empty_scene
sig: empty_scene()
what: Start a fresh empty Blender scene and clear session colour functions. After something was built, reset units to mm and facets to auto.
limits: Settings made before this call are preserved if nothing has been built since. Existing scene contents are removed.
see: `units`, `facets`
```python
import sand3d as s3d
s3d.empty_scene()
```
:::

::: fiche units
sig: units(name=None)
what: Set the unit used by every program length, or read it without an argument. The choices are mm, cm and m; default mm.
param name: Set before the first building verb. Export always converts to metres.
limits: Changing units after building raises. Start again with empty_scene, then set the new unit before making even a profile.
see: `export`, `empty_scene`
```python
import sand3d as s3d
s3d.units("cm")
part = s3d.box("part", 2, 3, 1)
```
:::

```python
import sand3d as s3d

s3d.empty_scene()
s3d.units("m")
with s3d.facets(12):
    part = s3d.cylinder("column", .2, 1.5)
s3d.material(part, "concrete")
s3d.export(part, "column.glb")
```

## Record the library used {#reproducibility}

::: fiche fingerprint
sig: fingerprint()
what: Return a digest of the installed library's Python source, not of the scene or the user's program. Record it beside __version__, units() and facets() to identify the implementation used for a run.
limits: This is the first 16 hexadecimal characters of a SHA-256 over sorted source paths and contents. A changed source can change it without a released version changing.
```python
import sand3d as s3d
print(s3d.fingerprint())
```
:::
