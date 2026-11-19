# Contributing to sand3d

Issues and pull requests are welcome. A shape no verb can say is a missing verb: open an issue
with the program you wanted to write. Before a pull request, read the principles below.

## Tests

```bash
uv venv -p 3.13 .venv && uv pip install -p .venv -r env/kit.lock   # Python 3.13, bpy 5.2
PYTHONPATH=src .venv/bin/python tests/run.py                         # the suite
```

The suite is `unittest`. Every public verb is built in two fresh processes, which must give
the same mesh. `tests/test_golden.py` compares the digests of every case, program and example
(vertices, faces, placement, every edge and face name) with `tests/golden/bpy-5.2.json`; the
recorded digests are Linux CI's, and a few differ on other platforms.

## Principles

- **Embedded Python, not a new language.** The pretraining prior is kept, and a
  program can always be flattened back to pure bpy by inlining the library.
- **`import sand3d as s3d`, never `import *`.** Verbs are common nouns (`hole`,
  `shell`, `ring`, `text`); a star import lets a program shadow them, and the
  prefix makes every escape to raw `bpy`/`bmesh` visible to a regex.
- **Two layers.** The assembly layer (frames, `at`, `assembly`, `attach`) carries
  modularity and is mandatory; geometry verbs are recommended. A program does
  not use `bpy` or `bmesh`: a shape no verb says is a missing verb, and an issue.
- **No B-rep selectors.** A verb names the edges and faces it creates (`top`,
  `side`, `rim`, `cut`); `fillet(ob, r, edges="top")` reads those names. A mesh
  has no stable topology to query.
- **Placement is relative.** Parts sit on frames (a face, an anchor, a point on
  a path), not on absolute coordinates.
- **Deterministic.** Every verb gives the same mesh in two fresh processes.
- **The vocabulary only grows**: no signature or meaning of an existing verb changes
  outside a major version; a version and a hash (`s3d.fingerprint()`) travel with every
  program run.
- **No category verbs** (`chair()`, `table()`), **no constraint solver, no cloth
  simulation.** A category generator is a program written *in* sand3d.

## Why a library and not raw bpy

Measured on 173 369 CAD → bpy translations written by an LLM: the operations a CAD
program uses most are exactly those it writes worst in raw bpy — valid rate per
1 000 against a base of 650: union 216, mirror 279, circular pattern 344, fillet 411;
on synthetic CadQuery sources (base 518): helix 205, sweep 278, revolve 362. Revolves
and lofts are hand-built in cos/sin, fillets become one bevel on the whole object,
small chamfers are dropped. The literature agrees that a domain vocabulary buys
validity and tokens, and that relations beat absolute coordinates — most of all after
fine-tuning a small model (LayoutVLM: 39.5 vs 6.8).

## Runtime

Blender as a Python module: `bpy` 5.2 on Python 3.13, and 4.5 LTS on Python 3.11. The
library imports only `bpy`, `bmesh`, `mathutils`, `numpy` (shipped with bpy) and the standard library, and uses no
5.x-only feature.

## Versioning

Semantic versioning, `MAJOR.MINOR.PATCH`, over the surface `docs/api.md` publishes.

| change | bump | PR title |
|---|---|---|
| a fix, no API change | patch | `fix:` |
| a new verb, a new parameter with a default, a default where there was none | minor | `feat:` |
| a name or parameter removed or renamed, a positional moved, a default changed, a new required parameter; a verb that builds something else, or names its edges and faces otherwise | major | `feat!:` |

PR titles are Conventional Commits and PRs are squash-merged, so the title is the
commit. Any change under `src/sand3d/` is at least a `fix:`, and so is a moved golden
digest: a fix that moves geometry rewrites the digests in the same PR
(`tests/run_golden.py --write`), and says which pieces moved and why.

## Layout

| path | what |
|---|---|
| `src/sand3d/` | the library: `profile`, `solids`, `edit`, `frames`, `assembly`, `parts/` — one flat `s3d.<verb>` surface |
| `tests/` | the suite; every public verb built in two fresh processes; the golden digests (`golden/`) |
| `programs/` | worked programs: a weight stack, a tufted chair, the spoon and the fork, a washing machine |
| `docs/` | `api.md` (the API, for a prompt), `guidelines.md` (how to write an assembly program), `examples/`, `readme/` (the README's figures and their numbers) |
| `env/` | `kit.in` and `kit.lock`: the test environment, bpy 5.2 |
