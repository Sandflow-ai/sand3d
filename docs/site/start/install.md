---
title: Install and a first program
order: 1
lead: Build a small plate with two mounting holes, export it, and inspect the mesh in a 3D viewer.
---

## Install {#install}

Use Python 3.13 with bpy 5.2, or Python 3.11 with bpy 4.5. The repository recommends 3.13 and tests on bpy 5.2. Its package metadata selects the matching bpy dependency. NumPy comes with bpy; no separate Blender application is needed to run the Python program.

For a new uv project:

```bash
uv init --python 3.13 first-sand3d
cd first-sand3d
uv add sand3d
```

In an existing uv project, use `uv add sand3d`; with pip, use `pip install sand3d` in a compatible Python environment. There is no bpy wheel for Python 3.12. On an Intel Mac, use Python 3.11: bpy 5.2 no longer provides an Intel Mac wheel.

To work directly from a repository checkout, run the repository's environment commands from its root:

```bash
uv venv -p 3.13 .venv
uv pip install -p .venv -r env/kit.lock
PYTHONPATH=src .venv/bin/python tests/run.py
```

These install the pinned development environment, not the published package. Run your own script in that checkout with `PYTHONPATH=src .venv/bin/python first.py`.

## Write the first program {#program}

Save the following toy's code as `first.py`. The dimensions are millimetres. The rounded rectangle is a profile; extrusion turns it into a plate 6 mm thick. A grid gives the two hole positions, and the maker's `top` edge name selects the edges to round. The material makes the result readable in a viewer.

::: example start_first
note: An 80 × 40 mm plate, two 6.6 mm holes on a 50 mm pitch, and a rounded top edge.
:::

Append this line to the file, outside the function:

```python
s3d.export(bracket(), "bracket.glb")
```

## Run and inspect {#inspect}

From your uv project:

```bash
uv run python first.py
```

This writes `bracket.glb` in the current directory. Open it in a GLB viewer, or import it into Blender with File → Import → glTF 2.0. Orbit the plate, look through both holes and inspect the rounded rim. The interactive model above lets you inspect the same toy without installing anything.

The extension chooses the export format. GLB carries mesh and materials; export converts program lengths to metres, so the plate is 0.08 m wide. See [Export and settings](reference/export) for the other formats.

Next: [Concepts](start/concepts) explains frames, names and edits; [Writing an assembly](start/assembly) scales this pattern to several parts.
