# Working on sand3d

Rules for anyone changing this repository, people and coding agents alike.
[CONTRIBUTING.md](CONTRIBUTING.md) explains the why.

## Commits and pull requests

- A pull request's title is a Conventional Commit: `fix:` (no API change), `feat:` (a new verb,
  a new parameter with a default), `feat!:` (anything that breaks a program already written).
  Any change under `src/sand3d/` is at least a `fix:`.
- Pull requests are squash-merged: the title becomes the commit on `main`.
- Do not add tool-attribution lines or links, nor co-author trailers for tools, to commits or
  pull requests. `Co-authored-by` names people.
- Do not edit `__version__` or `CHANGELOG.md`: releases set them.

## Tests

```bash
uv venv -p 3.13 .venv && uv pip install -p .venv -r env/kit.lock   # Python 3.13, bpy 5.2
PYTHONPATH=src .venv/bin/python tests/run.py                         # the suite
```

- The USD export test reads files back with `usd-core` in a separate Python, named by
  `SAND3D_USD_PYTHON`; without one, it is skipped.
- The IFC export test validates files with IfcOpenShell (and `pytest`, which its EXPRESS
  rules need) in a separate Python, named by `SAND3D_IFC_PYTHON`; without one, that test is
  skipped.
- `tests/test_golden.py` compares the digest of every case, program and example with
  `tests/golden/bpy-<version>.json`. The recorded digests are Linux CI's; a few differ on
  other platforms.
- A change that moves geometry re-records the digests in the same pull request, under each bpy
  in `tests/golden/`: `PYTHONPATH=src .venv/bin/python tests/run_golden.py --write`. The pull
  request says which pieces moved and why.

## Code

- The library imports only `bpy`, `bmesh`, `mathutils` and the standard library.
- Programs use `import sand3d as s3d`, never `from sand3d import *`.
- Every public verb is deterministic: built in two fresh processes, it gives the same mesh, and
  it has that test.
- No geometric edge selectors. Edges and faces are reached by the names the creating verb gave
  them, or a face by its direction.
- Every verb returns a named object in its own frame; placement goes through `at` and frames.
  Nothing reads `bpy.context.active_object` or the selection.
- No Blender feature that only 5.x has: the library also runs under bpy 4.5.
- The vocabulary only grows: no signature or meaning of an existing verb changes outside a major
  version.
- Lengths are in the program's unit: millimetres, or what `s3d.units` sets before the first verb;
  `export` scales to metres. An absolute tolerance is written in millimetres and converted
  (`_core.mm`).

## What does not belong here

- Nothing that cannot be redistributed under this repository's licence: third-party code, data
  or assets come with their source and their licence named.
- No credentials, private hostnames, storage buckets or local paths.
- No names of customers or partners, nor of their projects.
