# Build the human documentation

From the repository root, run these commands with Python 3.11 or later:

```sh
python3 tools/site/build.py
python3 tools/site/check_links.py
```

Commit the edited sources and regenerated files together. GitHub Pages serves
`site/` directly from release tags. The build reads `sand3d.__version__` and the
public vocabulary from the package source without importing Blender.

## Sources and output

- `index.md`, `start/`, `reference/`, `guides/` and `llms.md` are the new pages.
- `tools/site/` holds the generator and the shared CSS and JavaScript for the new pages.
- `site/assets/examples/` holds the checked-in renders used as build inputs.
  Each WebP and optional GLB shares a stem with its example. These renders come
  from the self-contained sand3d demonstrations in `toys/` and the existing
  programs in `docs/examples/` and `programs/`. The HTML build uses the ready-to-serve
  assets as-is, so it needs neither Blender nor an image converter.
- The five legacy HTML pages are kept with their existing anchors. The build
  refreshes their release labels in place. `CNAME`, `.nojekyll`, the raw LLM
  documents and the legacy assets are static inputs in `site/`.

The 3D viewer loads [three.js r170](https://github.com/mrdoob/three.js/tree/r170)
(MIT) and the bundled [Draco decoder](https://github.com/google/draco)
(Apache-2.0) from jsDelivr when a reader opens a model.

## Page format

Use front matter with `title`, optional `nav`, `order`, `lead` and a `hero` asset
stem. Body text supports headings, paragraphs, lists, notes, tables and fences.
Use site-relative links such as `reference/edits#cut` and section IDs such as
`## A section {#section}`. Inline code naming an API entry links to its fiche.

```markdown
::: fiche cut join intersect
sig: cut(ob, *tools)
what: Cut the tools out of a solid.
param ob: The solid to edit.
toy: edits_booleans | A plate with holes and a notch.
see: `split`
:::
```

Repeat `sig` or `toy` for sibling operations. `limits` explains constraints.
Indented lines continue the previous field. A Python fence inside a fiche adds
a short example.

- `::: example <stem>` shows an asset and the source from `toys/<stem>.py`.
- `::: scene <stem>` shows an asset and a folded full program. Set `title`,
  `program` (repository-relative path) and `note`. Without `program`, it uses
  `toys/<stem>.py`.
- `::: figure <stem>` shows an asset alone. Add `hero` for a wide figure.
- `::: chips <names>` links to related API entries.

Close each directive with `:::`.
