---
title: For LLMs
order: 1
lead: Give the model the API and assembly guidelines as its base prompt. Add a short task guide only when the requested object needs that technique.
---

## The base prompt {#base}

sand3d writes 3D objects as Python programs over Blender's bpy: profiles, solids, edits, frames, joints and assemblies. Programs use `import sand3d as s3d`, name their parts and use millimetres unless they select another unit. Export supports GLB, URDF, USDA, IFC, OBJ and STL.

The repository's [llms.txt](https://github.com/Sandflow-ai/sand3d/blob/main/llms.txt) is the entry point. It points to the documents and examples; it is not a substitute for the API text. Use these documents in the base prompt and add task guides as needed.

| File | What to give the model |
|---|---|
| [API](api.md) | The vocabulary, conventions, signatures and worked examples |
| [Assembly guidelines](guidelines.md) | Eight rules for multi-part programs and guidance on natural forms |
| [Guide index](https://github.com/Sandflow-ai/sand3d/blob/main/docs/guides/index.md) | The guide selector |

## Add guides on demand {#guides}

Read the index, then select by the task. Do not load every guide for every object.

| Guide source on GitHub | When to include it |
|---|---|
| [water.md](https://github.com/Sandflow-ai/sand3d/blob/main/docs/guides/water.md) | Filling basins, depth tint, waves on the surface, falls, foam and banks |
| [fire-smoke.md](https://github.com/Sandflow-ai/sand3d/blob/main/docs/guides/fire-smoke.md) | Flames, emission, smoke and fog media, and differences between the review renderer and Cycles |
| [trees-vegetation.md](https://github.com/Sandflow-ai/sand3d/blob/main/docs/guides/trees-vegetation.md) | Branches, foliage, crown cost, grass, lawns, moss carpets and textile fur |
| [terrain-ground.md](https://github.com/Sandflow-ai/sand3d/blob/main/docs/guides/terrain-ground.md) | Ground, scattered stones, leaf litter, gravel, snow, contact, sand, dunes and wind ripples |
| [organic-forms.md](https://github.com/Sandflow-ai/sand3d/blob/main/docs/guides/organic-forms.md) | Faceted rocks, field holes and folds, coral, fungi and choosing a form-building verb |
| [surface-colour-weathering.md](https://github.com/Sandflow-ai/sand3d/blob/main/docs/guides/surface-colour-weathering.md) | Per-face colour, broad weathering and a vectorized colour example |
| [glass-ice-crystals.md](https://github.com/Sandflow-ai/sand3d/blob/main/docs/guides/glass-ice-crystals.md) | Transmission, index of refraction, absorption, thickness and closed crystal geometry |
| [resolution.md](https://github.com/Sandflow-ai/sand3d/blob/main/docs/guides/resolution.md) | Triangle budgets and the cost of resolution |

## Assemble the prompt {#prompt}

Supply the actual file contents, not only links, unless the agent can read those links or the repository. Keep the API, guidelines and guides from the same revision as the installed library.

1. Put the full API and guidelines in the system or developer context available to your application.
2. Give the guide index to the agent. Let it read relevant guides, or append those guides yourself.
3. State the object, dimensions and units, required parts and motion, materials, style, seed and any face budget in the task.
4. Ask for a builder returning the object at rest. Run it, inspect its exported model, and feed back concrete failures or visual mismatches.

For example, after loading the two base documents, a pond task can request the water and terrain guides, specify the garden dimensions and water level, and ask for a seeded builder plus a GLB export. A mechanism task instead needs its parts, parent-child connections, pivots, axes and joint ranges. The guides supplement the API; they do not replace its signatures.

## Examples to include when relevant {#examples}

[programs/tufted_chair.py](https://github.com/Sandflow-ai/sand3d/blob/main/programs/tufted_chair.py) demonstrates lofts, tufts and rows of nails attached through anchors.

The worked examples include [bracket.py](https://github.com/Sandflow-ai/sand3d/blob/main/docs/examples/bracket.py), [lamp.py](https://github.com/Sandflow-ai/sand3d/blob/main/docs/examples/lamp.py), [rack.py](https://github.com/Sandflow-ai/sand3d/blob/main/docs/examples/rack.py), [chair.py](https://github.com/Sandflow-ai/sand3d/blob/main/docs/examples/chair.py) and [gate.py](https://github.com/Sandflow-ai/sand3d/blob/main/docs/examples/gate.py). Choose one that demonstrates the required structure rather than loading every program.

For human inspection, the [documentation website](https://sand3d.sandflow.ai/) provides code with renders, an articulated gallery and the API. This site's [Writing an assembly](start/assembly) shows the source programs as scenes; [Concepts](start/concepts) explains the rules behind them.
