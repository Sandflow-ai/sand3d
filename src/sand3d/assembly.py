"""The assembly layer: groups, handles and their anchors, details, export, the unit."""
import os

import bpy

from . import _core, _guard, materials


def group(name, *children):
    """Parent of children.

    One parent for `children`, which keep their placements in its frame."""
    from .edit import _flat
    root = _core.link(bpy.data.objects.new(name, None))
    for child in _flat(children):
        child.parent = root
    return root


class Handle:
    """Root and anchors.

    What an assembly publishes: its root object and named anchors — numbers
    and points, never geometry — that details attach to. An anchor that is a frame
    built by hand is read on the assembly: a joint can hang on it."""

    def __init__(self, root, **anchors):
        self.root = root
        self.__dict__.update({k: _read_on_root(v, root) for k, v in anchors.items()})


def _read_on_root(anchor, root):
    """A frame with no part, as a frame read on `root`, in its own space; a list of them
    likewise. Anything else as it is."""
    from mathutils import Matrix
    from .frames import Frame, Frames
    if isinstance(anchor, Frame) and anchor.part is None and isinstance(root, bpy.types.Object):
        import copy
        return copy.deepcopy(anchor)._read_on(root, Matrix.Identity(4))
    if isinstance(anchor, (list, tuple)) and anchor and all(isinstance(f, Frame) for f in anchor):
        frames = [_read_on_root(f, root) for f in anchor]
        return Frames(frames) if isinstance(anchor, Frames) else type(anchor)(frames)
    return anchor


def assembly(name, *children, **anchors):
    """Parts and anchors.

    The architecture of an object: its main parts, and the anchors it publishes."""
    return Handle(group(name, *children), **anchors)


def attach(handle, name, *children):
    """A detail, under a handle.

    A detail: `children`, placed in `handle`'s frame, grouped under `name`.
    Nothing reads it back, so deleting the call deletes the detail and only it."""
    detail = group(name, *children)
    detail.parent = handle.root
    return detail


def export(root, path):
    """root and what hangs on it by its joints, in metres: .glb at the current pose, joints
    in extras; .urdf a link per moving part, at rest, meshes beside it; .usda the URDF's
    tree as OpenUSD text, with the materials; .obj and .stl its meshes at the current pose.

    The program's unit to metres, then one file, its extension the format: a GLB — with
    the materials the program set, if it set any; nested by the joints, each in its
    node's extras, if it has any — or a URDF, the mechanism at rest whatever its pose,
    its meshes as OBJ in `<stem>_meshes/` beside it, the colours `material` set — or a
    USD layer as text, the URDF's links, joints and names in UsdGeom and UsdPhysics, Z up,
    with the materials (`.usdc` is binary: convert the `.usda`) — or the meshes alone, as
    OBJ (Y up) or binary STL (Z up), at the current pose. Limits only: masses,
    frictions, efforts and drives are dynamics, which sand3d does not say."""
    from . import meshfile, urdf, usd
    from .assembly import Handle
    root = root.root if isinstance(root, Handle) else root
    suffix = os.path.splitext(str(path))[1].lower()
    if suffix in (".usd", ".usdc", ".usdz"):
        tool = "usdzip" if suffix == ".usdz" else f"usdcat x.usda -o x{suffix}"
        raise ValueError(f"export: {suffix} is written by USD's own library, which sand3d does not take: write "
                         f".usda, USD as text, and convert it with USD's tools ({tool})")
    if suffix not in (".glb", ".obj", ".stl", ".urdf", ".usda"):
        raise ValueError(f"export: {suffix or 'a path with no extension'} is not a format sand3d writes: "
                         f"name the file .glb, .obj, .stl, .urdf or .usda")
    if suffix in (".obj", ".stl"):
        (meshfile.write_obj if suffix == ".obj" else meshfile.write_stl)(root, path)
        return
    materials.resolve()
    if suffix == ".urdf":
        urdf.write_urdf(root, path)
        return
    if suffix == ".usda":
        usd.write_usda(root, path)
        return
    lent = _lend_meshes()
    try:
        name = root.name                                   # the GLB's scene: the exporter names it after coll
        coll = bpy.data.collections.new("s3d~export")      # the exporter writes this, not the whole scene
        bpy.context.scene.collection.children.link(coll)
        state = urdf.glb_tree(root, coll)
        dressed = materials.dressed()           # asked before the tags come off: it reads them
        tags = {m: m.pop(materials.TAG) for m in bpy.data.materials if materials.TAG in m}   # extras: joints only
        clash = bpy.data.collections.get(name)  # a collection of the program's, lent its name meanwhile
        try:
            if clash is not None:
                clash.name = "s3d~export~lent"
            coll.name = name
            bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", collection=coll.name,
                                      export_extras=True,
                                      export_materials="EXPORT" if dressed else "NONE")
        finally:
            coll.name = "s3d~export"
            if clash is not None:
                clash.name = name
            for m, tag in tags.items():
                m[materials.TAG] = tag
            urdf.undo(state, coll)
    finally:
        _return_meshes(lent)


def _lend_meshes():
    """Give each mesh object of the scene, for the exporter, a mesh of its own: a copy
    rewritten through bmesh, which shares no array with anything. The exporter runs
    `Mesh.validate()` on what it exports; on the program's own mesh it would edit the
    scene, and under bpy 4.5 also the copies sharing that mesh's arrays. The copy takes
    the mesh's name, which the GLB carries."""
    import bmesh
    objects, copies = [], {}
    for ob in bpy.context.scene.objects:
        if ob.type != "MESH":
            continue
        mesh = ob.data
        if mesh not in copies:
            name, own = mesh.name, mesh.copy()
            bm = bmesh.new()
            bm.from_mesh(own)
            bm.to_mesh(own)
            bm.free()
            mesh.name = "s3d~lent"
            own.name = name
            copies[mesh] = (own, name)
        objects.append((ob, mesh))
        ob.data = copies[mesh][0]
    return objects, copies


def _return_meshes(lent):
    objects, copies = lent
    for ob, mesh in objects:
        ob.data = mesh
    for mesh, (own, name) in copies.items():
        bpy.data.meshes.remove(own)
        mesh.name = name


def empty_scene():
    """Fresh scene.

    A fresh, empty scene: what a program starts from. Once anything was built, the
    unit goes back to millimetres and the facets to "auto", so a program that sets
    none never inherits the last one's; what was set just before, with nothing built
    since, holds."""
    built = _core.settled or len(bpy.data.objects) > 0
    _guard.reset()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _guard.reset()
    if built:
        _core.UNIT, _core.MM = "mm", _core.UNITS["mm"]
        _core.FACETS = None
    _core.settled = False
    _core.dressed = False


def units(name=None):
    """Length unit: "mm" (default), "cm", "m".

    Set the unit every length of the program is in — "mm" (the default), "cm" or
    "m" — before its first verb; `export` scales it to metres. Without `name`, the
    unit in force: what a program records beside `__version__` and `fingerprint()`."""
    if name is None:
        return _core.UNIT
    if name not in _core.UNITS:
        raise ValueError(f"units: {name!r} is none of {sorted(_core.UNITS)}")
    if name != _core.UNIT and _core.settled:
        raise ValueError(f"units: set {name!r} before the first verb — this scene is already built in "
                         f"{_core.UNIT!r} (s3d.empty_scene() starts over)")
    _core.UNIT, _core.MM = name, _core.UNITS[name]
    return name


def facets(n=None):
    """Segments of a full circle: a whole number from 3, or "auto" (default).

    Set how many straight pieces a full circle gets — in every circle, arc, revolve,
    helix, fillet, wire corner and superellipse — before the program's first verb:
    `facets(8)` builds an octagonal cylinder and a quarter-round fillet in 2, for
    low-poly or faceted assets. "auto", the default, sets the count by the size, to a
    chord tolerance of 0.05 mm (24 to 64 a turn). Lengthwise sampling (a loft's steps,
    a body's sections) is not a circle and stays, and so do the teeth of `gear` and the
    turns of `knurl` and `thread`, which sample their own. Without `n`, the setting in force:
    what a program records beside `units()`."""
    if n is None:
        return "auto" if _core.FACETS is None else _core.FACETS
    if n == "auto":
        value = None
    elif isinstance(n, int) and not isinstance(n, bool) and n >= 3:
        value = n
    else:
        raise ValueError(f"facets: {n!r} is neither a whole number from 3 nor \"auto\"")
    if value != _core.FACETS and _core.settled:
        raise ValueError(f"facets: set {n!r} before the first verb — this scene is already built with "
                         f"{facets()!r} (s3d.empty_scene() starts over)")
    _core.FACETS = value
    return n
