"""What a part is made of: a named preset, its values changed where a program says so.

`material` tags an object — a part, or the root of a group or an assembly — and
leaves the mesh untouched. Every mesh then takes the material of its nearest tagged
ancestor-or-self: a call on an assembly reaches every part under it that names
none of its own, in whatever order the calls come, and a detail attached later
inherits. The tag lives on the object, so it goes through every edit that rebuilds
the mesh (`cut`, `hole`, `fillet`…) and with `copy`; a tool's tag is used up with
the tool, and `join` keeps its first object's.

`resolve` turns the tags into Blender materials: one Principled BSDF of flat values
per distinct look — what a GLB carries (base colour, metallic, roughness, alpha,
transmission, IOR, volume absorption, clearcoat, sheen, emission). It runs after every public verb once a
program has set a material, so the scene is right whoever reads it; a program that
sets none never runs it, and builds and exports exactly as before.
"""
import difflib
import json
import inspect
import math
from contextlib import contextmanager

import bpy
import numpy as np

from . import _core

#: Custom property holding an object's tag, and a material's look.
TAG = "s3d_material"
FUNCTIONS = {}
FUNCTION = "function"

#: The presets: sRGB colour, roughness, and what else sets the look apart.
PRESETS = {
    # woods
    "oak":            dict(color="#b48a5a", roughness=0.55),
    "walnut":         dict(color="#5e3b25", roughness=0.45),
    "pine":           dict(color="#d9b27c", roughness=0.6),
    "birch":          dict(color="#e2c9a0", roughness=0.55),
    # metals
    "steel":          dict(color="#a8abb0", roughness=0.3, metallic=1.0),
    "brushed_steel":  dict(color="#b4b7bb", roughness=0.35, metallic=1.0),
    "chrome":         dict(color="#e6e8ea", roughness=0.05, metallic=1.0),
    "aluminium":      dict(color="#c9ccd0", roughness=0.4, metallic=1.0),
    "brass":          dict(color="#c9a24a", roughness=0.25, metallic=1.0),
    "copper":         dict(color="#c47a52", roughness=0.25, metallic=1.0),
    "painted_metal":  dict(color="#2b2d30", roughness=0.4, coat=0.3),
    # plastics, rubber, glass, ceramic
    "plastic":        dict(color="#d8d8d8", roughness=0.5),
    "glossy_plastic": dict(color="#d8d8d8", roughness=0.12, coat=0.5),
    "rubber":         dict(color="#202020", roughness=0.9),
    "glass":          dict(color="#ffffff", roughness=0.0, transmission=1.0),
    "ceramic":        dict(color="#f2f0ea", roughness=0.15, coat=0.6),
    # soft goods, stone
    "fabric":         dict(color="#8a8f96", roughness=0.85, sheen=0.6),
    "velvet":         dict(color="#2f4f5f", roughness=0.9, sheen=1.0),
    "leather":        dict(color="#6b3e26", roughness=0.5),
    "marble":         dict(color="#e8e6e1", roughness=0.15, coat=0.4),
    "concrete":       dict(color="#9a9893", roughness=0.85),
    # natural materials: flat average colours, no texture
    "bark":           dict(color="#69503b", roughness=0.9),
    "leaf":           dict(color="#52703d", roughness=0.5, coat=0.12),
    "moss":           dict(color="#596344", roughness=0.95),
    "grass":          dict(color="#68794a", roughness=0.8),
    "rock":           dict(color="#85827b", roughness=0.9),
    "soil":           dict(color="#66503c", roughness=1.0),
    "sand":           dict(color="#c5b58e", roughness=0.9),
    "water":          dict(color="#f4f8f8", roughness=0.08, transmission=1.0,
                           ior=1.333, absorb="#b8e8ed", absorb_distance=1000.0),
    "snow":           dict(color="#eef1f3", roughness=0.85, coat=0.03),
    "foam":           dict(color="#f5f5f2", roughness=0.95),
    # media: an unseen boundary around light that scatters inside
    "smoke":          dict(color="#ffffff", roughness=0.0, transmission=1.0, ior=1.0,
                           scatter="#ffffff", scatter_distance=625.0, scatter_anisotropy=0.3,
                           absorb="#d6d6d6", absorb_distance=1000.0),
    "fog":            dict(color="#ffffff", roughness=0.0, transmission=1.0, ior=1.0,
                           scatter="#ffffff", scatter_distance=10000.0, scatter_anisotropy=0.3),
    # a surface that gives light, in its own colour
    "light":          dict(color="#fff1dc", roughness=0.5, emission=12.0),
}


def material(ob, kind, color=None, roughness=None, metallic=None, opacity=None, emission=None,
             absorb=None, absorb_distance=None, thickness="auto", ior=None, transmission=None,
             scatter=None, scatter_distance=None, scatter_anisotropy=None):
    """Kind: oak walnut pine birch steel brushed_steel chrome aluminium brass copper
    painted_metal plastic glossy_plastic rubber glass ceramic fabric velvet leather marble
    concrete bark leaf moss grass rock soil sand water snow foam smoke fog light; color "#rrggbb".

    `ob` — a part, a group, an assembly or a list — made of `kind`, one of the presets,
    its colour (sRGB: "#rrggbb" or (r, g, b) in 0..1), roughness, metallic, opacity (1
    opaque, 0 invisible) or emission (the light it gives, in its own colour) changed where
    given. On a group or an assembly, every part under it that names none of its own: the
    nearest call wins, in whatever order the calls come. Returns `ob`.

    absorb is the sRGB colour white light becomes after absorb_distance (in program
    units), following Beer-Lambert attenuation. Zero distance disables absorption.
    thickness is the constant depth glTF viewers assume: "auto" (the default) estimates
    it at export from the meshes that wear the material, 2 x volume / area; a length
    sets it. Cycles uses the closed mesh's actual depth. ior is 1..1000, transmission 0..1.
    None inherits the preset. Water absorbs over one metre with IOR 1.333.

    scatter is the sRGB colour the medium inside the closed mesh sends light back in:
    channel c scatters linear(scatter)[c] / scatter_distance per program unit, so white
    light travels scatter_distance on average before it scatters. Zero distance disables
    scattering. scatter_anisotropy, -1..1, sends that light backwards (< 0), every way
    (0) or forwards (> 0: a glow against the light). Absorption and scattering add up.
    The surface stays what its values say and hides the medium when opaque: smoke and
    fog are media behind an unseen boundary (transmission 1, IOR 1, roughness 0). glTF
    has no scattering: GLB carries the total attenuation (absorption plus scattering)
    in KHR_materials_volume, so a scattering medium shows there as a dark one.

    color may be a deterministic callable declaring exactly three, four or five
    positional parameters, no variadics or keyword-only parameters:
    color(x, y, z[, n[, u]]), at local face centres in program units. Scalar calls
    receive an outward unit normal tuple and lengthwise u, returning sRGB hex or
    an RGB tuple/list in [0, 1]. Array calls receive float64 x/y/z/u of shape (k,)
    and n of shape (3, k), returning a numeric NumPy RGB array of shape (k, 3) in [0, 1].
    A probe on up to eight faces selects array evaluation; an exception or wrong
    shape falls back to scalar calls in face index order. Array evaluation then
    calls once for all faces of the part. The probe is an extra call: functions
    must be pure, without side effects or random state, and agree in both forms.
    Each export evaluates anew; corner and mean readers share the result within
    that export, and identical instances can share it too. Functions are session-local, not serialised in Blender files;
    copy keeps the reference, join and merge keep the first object's.
    """
    from .assembly import Handle
    from .edit import _flat
    if kind not in PRESETS:
        near = difflib.get_close_matches(str(kind), PRESETS, n=2)
        raise ValueError(f"material: no preset named {kind!r}" + (f" — did you mean {' or '.join(map(repr, near))}?"
                                                                  if near else "")
                         + f"; the presets: {', '.join(PRESETS)}")
    function = None
    if callable(color):
        arity(color)
        function = str(len(FUNCTIONS))
        FUNCTIONS[function] = color
    given = {"color": None if color is None or function is not None else _hex(color, "color")}
    for name, value, top in (("roughness", roughness, 1), ("metallic", metallic, 1), ("opacity", opacity, 1),
                             ("emission", emission, None)):
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0 or (top and value > top):
                raise ValueError(f"material: {name}={value!r} is not a number "
                                 + ("between 0 and 1" if top else "of 0 or more")
                                 + (" — 1 is opaque, 0 invisible" if name == "opacity" else ""))
        given[name] = None if value is None else float(value)
    for name, value in (("absorb", absorb), ("scatter", scatter)):
        if value is not None:
            given[name] = _hex(value, name)
    if thickness != "auto":
        if (isinstance(thickness, bool) or not isinstance(thickness, (int, float))
                or not math.isfinite(thickness) or thickness < 0):
            raise ValueError(f'material: thickness must be "auto" or a finite length of 0 or more, not {thickness!r}')
        given["thickness"] = float(thickness)
    for name, value, low, high in (("absorb_distance", absorb_distance, 0, None),
                                    ("ior", ior, 1, 1000), ("transmission", transmission, 0, 1),
                                    ("scatter_distance", scatter_distance, 0, None),
                                    ("scatter_anisotropy", scatter_anisotropy, -1, 1)):
        if value is not None:
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value < low or (high is not None and value > high)):
                raise ValueError(f"material: {name} must be finite and "
                                 + (f"between {low} and {high}" if high is not None else "0 or more"))
            given[name] = float(value)
    tag = json.dumps({"kind": kind, **({FUNCTION: function} if function is not None else {}), **{k: v for k, v in given.items() if v is not None}}, sort_keys=True)
    targets = [t.root if isinstance(t, Handle) else t for t in _flat([ob])]
    for target in targets:                  # all checked before any is tagged
        if not isinstance(target, bpy.types.Object):
            raise TypeError(f"material: {target!r} is not a part, a group or an assembly — a profile or a path "
                            "becomes one through extrude, revolve, sweep or loft")
    for target in targets:
        target[TAG] = tag
    _core.dressed = True
    return ob


def _hex(color, name="color"):
    """`color` as '#rrggbb', lower case: one spelling per colour, so one material."""
    if isinstance(color, str):
        h = color[1:] if color.startswith("#") else ""
        if len(h) == 6 and all(c in "0123456789abcdefABCDEF" for c in h):
            return "#" + h.lower()
    elif (isinstance(color, (tuple, list)) and len(color) == 3
          and all(isinstance(c, (int, float)) and not isinstance(c, bool) and 0 <= c <= 1 for c in color)):
        return "#" + "".join(f"{round(c * 255):02x}" for c in color)
    raise ValueError(f"material: {name}={color!r} is not a colour — write '#rrggbb' or (r, g, b) in 0..1")


def _linear(hex_color):
    """'#rrggbb' (sRGB) → linear RGBA, what Blender's colour sockets hold."""
    srgb = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)] if isinstance(hex_color, str) else hex_color
    return (*(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb), 1.0)


def look(tag):
    """The values a tag stands for: its preset, changed where the call said."""
    spec = json.loads(tag)
    spec.pop(FUNCTION, None)
    values = dict(metallic=0.0, opacity=1.0, transmission=0.0, coat=0.0, sheen=0.0, emission=0.0)
    kind = spec.pop("kind")
    values.update(ior=1.5, absorb="#ffffff", absorb_distance=0.0, thickness="auto",
                  scatter="#ffffff", scatter_distance=0.0, scatter_anisotropy=0.0)
    values.update(PRESETS[kind])
    for name in ("absorb_distance", "scatter_distance"):    # presets are written in millimetres
        if name in PRESETS[kind]:
            values[name] = _core.mm(values[name])
    values.update(spec)
    return values


def _name(tag):
    """A material's name: its preset, and what the program changed in it."""
    spec = json.loads(tag)
    kind = spec.pop("kind")
    if FUNCTION in spec:
        spec.pop(FUNCTION, None)
        kind += " face colours"
    return " ".join([kind, *(str(v) if k == "color" else f"absorb={v}" if k == "absorb" else f"{k}={v}" if isinstance(v, str) else f"{k}={v:g}" for k, v in sorted(spec.items()))])


def _material(tag, made):
    """The Blender material of a tag: one per distinct tag, made once."""
    if tag in made:
        return made[tag]
    v = look(tag)
    mat = bpy.data.materials.new(_name(tag))
    mat[TAG] = tag
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    rgba = _linear(v["color"])
    for socket, value in (("Base Color", rgba), ("Roughness", v["roughness"]), ("Metallic", v["metallic"]),
                          ("IOR", v["ior"]), ("Alpha", v["opacity"]), ("Transmission Weight", v["transmission"]),
                          ("Coat Weight", v["coat"]), ("Sheen Weight", v["sheen"]),
                          ("Emission Color", rgba), ("Emission Strength", v["emission"])):
        bsdf.inputs[socket].default_value = value
    medium = v["absorb_distance"] > 0 or v["scatter_distance"] > 0
    if medium and (v["thickness"] == "auto" or v["thickness"] > 0):
        node = mat.node_tree.nodes.new("ShaderNodeVolumeAbsorption")
        node.name = "Absorption"
        # Cycles uses sigma = (1 - colour) * density, not -log(colour)/distance.
        sigma = ([-math.log(max(c, 1e-6)) / v["absorb_distance"] for c in _linear(v["absorb"])[:3]]
                 if v["absorb_distance"] > 0 else [0.0] * 3)
        density = max(sigma)
        node.inputs["Density"].default_value = density
        node.inputs["Color"].default_value = (*(1 - c / density if density else 1 for c in sigma), 1)
        volume = node.outputs["Volume"]
        if v["scatter_distance"] > 0:
            scatter = mat.node_tree.nodes.new("ShaderNodeVolumeScatter")
            scatter.name = "Scatter"
            # Cycles scatters sigma = colour * density.
            sigma = [c / v["scatter_distance"] for c in _linear(v["scatter"])[:3]]
            density = max(sigma)
            scatter.inputs["Density"].default_value = density
            scatter.inputs["Color"].default_value = (*(c / density if density else 0 for c in sigma), 1)
            scatter.inputs["Anisotropy"].default_value = v["scatter_anisotropy"]
            both = mat.node_tree.nodes.new("ShaderNodeAddShader")
            both.name = "Medium"
            mat.node_tree.links.new(volume, both.inputs[0])
            mat.node_tree.links.new(scatter.outputs["Volume"], both.inputs[1])
            volume = both.outputs["Shader"]
        mat.node_tree.links.new(volume, mat.node_tree.nodes["Material Output"].inputs["Volume"])
        group = bpy.data.node_groups.get("glTF Material Output")
        if group is None:
            group = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
            group.interface.new_socket(name="Thickness", in_out="INPUT", socket_type="NodeSocketFloat")
            # Also prevents Blender 5.2 from inlining away this export-only group.
            socket = group.interface.new_socket(name="Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
            socket.default_value = 1.0
            group.nodes.new("NodeGroupInput")
            group.nodes.new("NodeGroupOutput")
        output = mat.node_tree.nodes.new("ShaderNodeGroup")
        output.node_tree = group
        # "auto" is estimated from the meshes at export; Cycles never reads it.
        output.inputs["Thickness"].default_value = 0.0 if v["thickness"] == "auto" else v["thickness"]
    if v["coat"]:
        bsdf.inputs["Coat Roughness"].default_value = 0.05
    if v["opacity"] < 1:
        mat.surface_render_method = "BLENDED"
    mat.diffuse_color = (*rgba[:3], v["opacity"])       # what Workbench and the viewport show
    mat.metallic, mat.roughness = v["metallic"], v["roughness"]
    made[tag] = mat
    return mat


def _nearest(ob):
    while ob is not None:
        if TAG in ob:
            return ob[TAG]
        ob = ob.parent
    return None


def _separate_materials():
    """Partition shared data only where inherited material tags disagree."""
    groups = {}
    for ob in bpy.data.objects:
        if ob.type == "MESH":
            groups.setdefault(ob.data, {}).setdefault(_nearest(ob), []).append(ob)
    for mesh, tags in groups.items():
        for parts in list(tags.values())[1:]:
            own = mesh.copy()
            for ob in parts:
                ob.data = own


def resolve(objects=None):
    """Give every mesh the material of its nearest tagged ancestor-or-self; take ours off
    a mesh that has none any more. Nothing to do in a program that sets no material."""
    if not _core.dressed:
        return
    if objects is None:              # tags and hierarchy change only on the whole-scene path
        _separate_materials()
    made = {m[TAG]: m for m in bpy.data.materials if TAG in m}
    for ob in sorted(bpy.data.objects if objects is None else objects, key=lambda o: o.name):
        if ob.type != "MESH":
            continue
        tag = _nearest(ob)
        have = list(ob.data.materials)
        if tag is None:
            if any(m is not None and TAG in m for m in have):
                ob.data.materials.clear()
            continue
        want = _material(tag, made)
        if have != [want]:
            ob.data.materials.clear()
            ob.data.materials.append(want)
        if ob.data.attributes.get("material_index") is not None:
            indices = np.empty(len(ob.data.polygons), dtype=np.int32)
            ob.data.polygons.foreach_get("material_index", indices)
            if indices.any():
                ob.data.polygons.foreach_set("material_index", np.zeros(len(indices), dtype=np.int32))


def dressed():
    """Whether any mesh of the scene wears one of our materials."""
    return _core.dressed and any(ob.type == "MESH" and any(m is not None and TAG in m for m in ob.data.materials)
                                 for ob in bpy.data.objects)


def arity(fn):
    """Explicit positional parameters select coordinates, normal and lengthwise u."""
    try:
        params = list(inspect.signature(fn).parameters.values())
        if len(params) in (3, 4, 5) and all(p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD) for p in params):
            return len(params)
    except (ValueError, TypeError):
        pass
    raise ValueError("material: color callable must declare three or four or five positional parameters")


def face_colors(ob):
    """Linear RGBA per polygon, or None; evaluate in local space."""
    tag = _nearest(ob)
    key = json.loads(tag).get(FUNCTION) if tag else None
    if key is None:
        return None
    fn = FUNCTIONS[key]
    count = arity(fn)
    mesh = ob.data
    from ._coordinates import face_u
    parameter = face_u(mesh)
    if count == 5 and (parameter is None or any(not math.isfinite(u) for u in parameter)):
        raise ValueError(f"material: {_core.given_name(ob)!r} has no lengthwise u; "
                         "use loft, wire, sweep, revolve, dome, sphere, cone or cylinder")
    # Blender stores these coordinates as floats; widen before calling the function,
    # exactly as tuple(face.center) does in the scalar path.
    centres = np.empty((len(mesh.polygons), 3), dtype=np.float64)
    mesh.polygons.foreach_get('center', centres.ravel())
    args = tuple(centres.T)
    if count >= 4:
        normals = np.empty_like(centres)
        mesh.polygons.foreach_get('normal', normals.ravel())
        args += (normals.T,)
    if count == 5:
        args += (np.asarray(parameter, dtype=np.float64),)
    size = min(8, len(centres))
    vectorized = False
    try:
        probe = fn(*(a[..., :size] for a in args))
        vectorized = isinstance(probe, np.ndarray) and probe.shape == (size, 3)
    except Exception:
        # Scalar functions may reject arrays in arbitrary user code.
        pass
    if vectorized:
        try:
            values = np.asarray(fn(*args))
            if values.shape != (len(centres), 3):
                raise ValueError(f"expected RGB array shape ({len(centres)}, 3), got {values.shape}")
            if values.dtype.kind not in 'fiu':
                raise ValueError("expected a numeric RGB array")
            values = values.astype(np.float64)
            if not np.all(np.isfinite(values) & (values >= 0) & (values <= 1)):
                raise ValueError("RGB array values must be finite and in [0, 1]")
        except Exception as exc:
            raise ValueError(f"material: invalid colour array: {exc}") from exc
        # Python's float pow keeps the scalar conversion bit-identical in float64.
        linear = np.fromiter((c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4
                              for c in map(float, values.ravel())), np.float64,
                             values.size).reshape(-1, 3)
        return [(*rgb, 1.) for rgb in linear.tolist()]
    result = []
    for face in mesh.polygons:
        centre = tuple(face.center)
        args = (*centre, tuple(face.normal)) if count >= 4 else centre
        if count == 5:
            args += (parameter[face.index],)
        try:
            value = fn(*args)
            if isinstance(value, str):
                rgba = _linear(_hex(value))
            else:
                if not isinstance(value, (tuple, list)) or len(value) != 3 or not all(
                        isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) and 0 <= c <= 1 for c in value):
                    raise ValueError("not a colour")
                rgba = (*(c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4 for c in value), 1.)
            result.append(rgba)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError(f"material: invalid colour at face centre {centre}; "
                             "expected scalar hex/RGB in [0, 1] or numeric RGB array shape (k, 3)") from exc
    return result


def mean_tag(ob, colors=None):
    """Area-weighted linear mean, encoded as sRGB for single-colour readers."""
    tag = _nearest(ob)
    if colors is None:
        colors = face_colors(ob)
    if colors is None:
        return tag
    mesh = ob.data
    total = sum(p.area for p in mesh.polygons)
    rgb = [sum(p.area*c[i] for p,c in zip(mesh.polygons, colors))/total if total else 0 for i in range(3)]
    spec = json.loads(tag)
    spec.pop(FUNCTION, None)
    spec['color'] = tuple(12.92*c if c <= .0031308 else 1.055*c**(1/2.4)-.055 for c in rgb)
    return json.dumps(spec, sort_keys=True)


COLOR_ATTRIBUTE = "Colour"


def put_colors(mesh, colors):
    """One linear colour on every corner of a polygon."""
    attr = mesh.color_attributes.get(COLOR_ATTRIBUTE)
    if attr is None:
        attr = mesh.color_attributes.new(name=COLOR_ATTRIBUTE, type='FLOAT_COLOR', domain='CORNER')
    sizes = np.empty(len(mesh.polygons), dtype=np.int32)
    mesh.polygons.foreach_get("loop_total", sizes)
    corners = np.repeat(np.asarray(colors, dtype=np.float32).reshape(-1, 4), sizes, axis=0)
    attr.data.foreach_set("color", corners.ravel())
    mesh.color_attributes.active_color = attr
    mesh.color_attributes.render_color_index = list(mesh.color_attributes).index(attr)


@contextmanager
def exporting(root, mode="material"):
    """Lend one corner-coloured mesh per source and material.

    A surface that gives light keeps its colour in its material, where its emission
    reads it — the mean of a colour function's — so two glows of different colours
    are two materials; every other colour goes to the corners, on a white base."""
    from .meshfile import _meshes
    saved, made = [], {}
    shared = {}
    parts = _meshes(root)
    before = set(bpy.data.materials)
    was_dressed = _core.dressed
    try:
        for ob in parts:
            key = (ob.data, _nearest(ob))
            if key in shared:
                original = ob.data
                ob.data = shared[key]
                saved.append((ob, original, ob.data))
                continue
            colors = face_colors(ob)
            if colors is None and mode == "material":
                continue
            source = _nearest(ob) or '{"kind":"plastic", "color":"#cccccc"}'
            v = look(source)
            glow = json.loads(mean_tag(ob, colors))["color"] if colors is not None else v["color"]
            if colors is None:
                colors = [_linear(v['color'])] * len(ob.data.polygons)
            original = ob.data
            mesh = original.copy()
            shared[key] = mesh
            saved.append((ob, original, mesh))
            ob.data = mesh
            put_colors(mesh, colors)
            spec = {"kind": "plastic", **v} if mode == "vertex" else json.loads(source)
            spec.pop(FUNCTION, None)
            spec['color'] = glow if v['emission'] else '#ffffff'
            tag = json.dumps(spec, sort_keys=True)
            mat = _material(tag, made)
            if mode == "vertex":
                mat.name = "Surface " + str(list(made).index(tag) + 1)
            bsdf = mat.node_tree.nodes['Principled BSDF']
            if mat.node_tree.nodes.get('Face Colour') is None:      # the base colour is the corners'
                node = mat.node_tree.nodes.new('ShaderNodeVertexColor')
                node.name = 'Face Colour'
                node.layer_name = COLOR_ATTRIBUTE
                mat.node_tree.links.new(node.outputs['Color'], bsdf.inputs['Base Color'])
            mesh.materials.clear()
            mesh.materials.append(mat)
        if saved:
            _core.dressed = True
        yield
    finally:
        _core.dressed = was_dressed
        for ob, original, mesh in reversed(saved):
            ob.data = original
        bpy.data.batch_remove([*shared.values(), *(set(bpy.data.materials) - before)])


@contextmanager
def volume_export():
    """Lend glTF's attenuation parameters; restore Cycles even on export failure.

    The exporter copies colour and reciprocal density literally. Distance is in
    world metres; thickness remains in mesh units (the export root scales it).
    glTF has no scattering: a scattering medium lends its total attenuation,
    absorption plus scattering, over the distance that dims its densest channel to 1/e.
    """
    saved = []
    try:
        for mat in bpy.data.materials:
            if TAG not in mat or not mat.use_nodes:
                continue
            node = mat.node_tree.nodes.get("Absorption")
            if node is None:
                continue
            v = look(mat[TAG])
            color, density = node.inputs["Color"], node.inputs["Density"]
            saved.append((color, tuple(color.default_value)))
            saved.append((density, density.default_value))
            metres = _core.MM / 1000
            if v["scatter_distance"] > 0:
                sigma = [(-math.log(max(a, 1e-6)) / (v["absorb_distance"] * metres) if v["absorb_distance"] > 0 else 0)
                         + s / (v["scatter_distance"] * metres)
                         for a, s in zip(_linear(v["absorb"])[:3], _linear(v["scatter"])[:3])]
                top = max(sigma)
                color.default_value = (*(math.exp(-s / top) if top else 1 for s in sigma), 1)
                density.default_value = top
            else:
                color.default_value = _linear(v["absorb"])
                density.default_value = 1 / (v["absorb_distance"] * metres)
            if v["thickness"] == "auto":
                output = next(n for n in mat.node_tree.nodes
                              if n.type == "GROUP" and n.node_tree and n.node_tree.name == "glTF Material Output")
                socket = output.inputs["Thickness"]
                saved.append((socket, socket.default_value))
                socket.default_value = _auto_thickness(mat)
        yield
    finally:
        for socket, value in saved:
            socket.default_value = value


def _auto_thickness(mat):
    """2 x volume / area of the meshes wearing `mat`, in mesh units: a slab's thickness.

    Summed over every mesh with the material, so one value per material; a mesh
    without volume (open or empty) contributes nothing. Falls back to one metre."""
    import bmesh
    volume = area = 0.0
    for me in sorted({ob.data for ob in bpy.data.objects
                      if ob.type == "MESH" and any(s.material == mat for s in ob.material_slots)},
                     key=lambda m: m.name):
        bm = bmesh.new()
        bm.from_mesh(me)
        v = abs(bm.calc_volume(signed=False))
        if v > 0:
            volume += v
            area += sum(f.calc_area() for f in bm.faces)
        bm.free()
    return 2 * volume / area if volume > 0 and area > 0 else _core.mm(1000)
