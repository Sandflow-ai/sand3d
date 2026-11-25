# Changelog

## 1.7.0 (2026-11-24)

### Features

* Organic modelling: implicit fields, deformers (`displace`, `bend`, `twist`, `taper`,
  `dent`, `blend`), seeded scatter, branching and phyllotaxis, `snap` and `lay` onto another
  surface, rooted blades and fur with `tufts`, colour functions, optical media, and task
  guides for nature (#44)
* Lights in lumens and lux, written by every export that can carry them (#43, fixes #38)
* A corner radius too large for its side is clamped with a warning, and a loft section that
  crosses itself says where (#42, fixes #41)
* `export` writes a trace of what was built beside the file (#31)
* A cut, hole or pocket that misses warns by default; strict mode raises (#36)
* `copy(ob, name=…)` names a copy, and the parts and joints it holds (#30)
* `facets` sets the segments of a full circle (#19)
* `export` writes `.ifc`, and names it for Revit's `.rvt` (#12)

### Fixes

* `export` says which meshes it writes (#47)
* Binary STL headers no longer start with `solid` (#45)
* Text files are read and written as UTF-8 (#34)
* An empty intersection warns (#18, fixes #14)
* A solid with a long name builds, and keeps its face and edge names (#20, fixes #13)

### Behaviour changes

* `facets(n)` also sets the steps along lofts and sweeps, and parts built under a fixed
  count are flat-shaded
* `snap` returns the outward normal
* Some published examples change topology, such as the spoon

Thanks to @BLTC-520, @usman7384, @Kaktusava, @wyddy7, @andrealoy, @dzyuan, @iyuzhang,
@abbigupta and @lmanhes for their contributions, and to @alaabenfatma for the review of #44.

## 1.6.3 (2026-11-06)

### Fixes

* A GLB holds only the root's tree, in metres: the rest of the scene no longer comes
  along, and a placed or mirrored root keeps its offset and its mirror (#11)

## 1.6.2 (2026-11-04)

### Fixes

* The README's images show on PyPI

## 1.6.1 (2026-11-04)

First public release of sand3d: profiles, solids, edits, frames, joints and an
assembly layer over Blender's `bpy`, with export to GLB, URDF, USD (`.usda`,
UsdPhysics), OBJ and STL. `pip install sand3d` brings the `bpy` its Python takes:
bpy 4.5 on Python 3.11, bpy 5.2 on Python 3.13. The API is described in
[docs/api.md](docs/api.md).
