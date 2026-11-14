# Curved branches, parent attachment, foliage and crown cost.

- **Attach to the actual parent.** Strawberry's crown reads a surface frame with
  `snap`; its achenes snap again after denting. `LeafMapleFactory.py:petiole`
  returns the path end from `along(path, count=2)[-1]` for the blade.
  `KelpMonocotFactory.py:fronds` and `TreeFactory.py:structure` place children
  using `along(..., spin=137.508, span=(...))`. Derive placement from geometry,
  not offsets measured on a render. A child's anchor must follow seed changes.

- **Curved branching.** `BushBaseCoralFactory.py:crown` and
  `TreeFactory.py:bough` use `branches(wander=..., droop=..., seed=...)`.
  Wander bounds heading changes; positive droop bends toward the carrier's -Z,
  negative droop rises. Axis paths are already in their carrying frame: do not
  apply `on` a second time. Use their paths for wire/sweep and their tips for buds.

branches creates paths and along creates frames, not geometry. Build trunks and branches from tapering wire/sweep paths. along(path, count=13, spin=137.508, span=(.12,.92)) follows arc length; turn(ry=60) departs from the tangent. Place organs built from their base along local +Z; angular jitter preserves attachment, position jitter can detach leaves. scatter(n, size, seed=seed, surface=False) distributes frames in an ellipsoid; scatter(n, mesh, seed=seed) samples a surface. Vary foliage scale, orientation and clusters with derived seeds. Budget crown cost as leaf count times faces per leaf plus twigs: thousands of finely tessellated leaves dominate. Prefer simple broad leaf geometry that reads at review scale, expose branch structure and keep roots in ground contact.
