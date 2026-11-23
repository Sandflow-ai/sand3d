"""What a part is made of: a named preset, its values changed where a program says so.

`material` tags an object — a part, or the root of a group or an assembly — and
never touches a mesh. Every mesh then takes the material of its nearest tagged
ancestor-or-self: a call on an assembly reaches every part under it that names
none of its own, in whatever order the calls come, and a detail attached later
inherits. The tag lives on the object, so it goes through every edit that rebuilds
the mesh (`cut`, `hole`, `fillet`…) and with `copy`; a tool's tag is used up with
the tool, and `join` keeps its first object's.

`resolve` turns the tags into Blender materials: one Principled BSDF of flat values
per distinct look — what a GLB carries (base colour, metallic, roughness, alpha,
transmission, clearcoat, sheen, emission). It runs after every public verb once a
program has set a material, so the scene is right whoever reads it; a program that
sets none never runs it, and builds and exports exactly as before.
"""
import difflib
import json

import bpy

from . import _core

#: Custom property holding an object's tag, and a material's look.
TAG = "s3d_material"

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
    # a surface that gives light, in its own colour
    "light":          dict(color="#fff1dc", roughness=0.5, emission=12.0),
}


def material(ob, kind, color=None, roughness=None, metallic=None, opacity=None, emission=None):
    """Kind: oak walnut pine birch steel brushed_steel chrome aluminium brass copper
    painted_metal plastic glossy_plastic rubber glass ceramic fabric velvet leather marble
    concrete light; color "#rrggbb".

    `ob` — a part, a group, an assembly or a list — made of `kind`, one of the presets,
    its colour (sRGB: "#rrggbb" or (r, g, b) in 0..1), roughness, metallic, opacity (1
    opaque, 0 invisible) or emission (the light it gives, in its own colour) changed where
    given. On a group or an assembly, every part under it that names none of its own: the
    nearest call wins, in whatever order the calls come. Returns `ob`."""
    from .assembly import Handle
    from .edit import _flat
    if kind not in PRESETS:
        near = difflib.get_close_matches(str(kind), PRESETS, n=2)
        raise ValueError(f"material: no preset named {kind!r}" + (f" — did you mean {' or '.join(map(repr, near))}?"
                                                                  if near else "")
                         + f"; the presets: {', '.join(PRESETS)}")
    given = {"color": None if color is None else _hex(color)}
    for name, value, top in (("roughness", roughness, 1), ("metallic", metallic, 1), ("opacity", opacity, 1),
                             ("emission", emission, None)):
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0 or (top and value > top):
                raise ValueError(f"material: {name}={value!r} is not a number "
                                 + ("between 0 and 1" if top else "of 0 or more")
                                 + (" — 1 is opaque, 0 invisible" if name == "opacity" else ""))
        given[name] = None if value is None else float(value)
    tag = json.dumps({"kind": kind, **{k: v for k, v in given.items() if v is not None}}, sort_keys=True)
    targets = [t.root if isinstance(t, Handle) else t for t in _flat([ob])]
    for target in targets:                  # all checked before any is tagged
        if not isinstance(target, bpy.types.Object):
            raise TypeError(f"material: {target!r} is not a part, a group or an assembly — a profile or a path "
                            "becomes one through extrude, revolve, sweep or loft")
        if target.type == "LIGHT":
            raise TypeError(f"material: {_core.given_name(target)!r} is a light object, not a solid: its colour is "
                            f"light(color=)")
    for target in targets:
        target[TAG] = tag
    _core.dressed = True
    return ob


def _hex(color):
    """`color` as '#rrggbb', lower case: one spelling per colour, so one material."""
    if isinstance(color, str):
        h = color[1:] if color.startswith("#") else ""
        if len(h) == 6 and all(c in "0123456789abcdefABCDEF" for c in h):
            return "#" + h.lower()
    elif (isinstance(color, (tuple, list)) and len(color) == 3
          and all(isinstance(c, (int, float)) and not isinstance(c, bool) and 0 <= c <= 1 for c in color)):
        return "#" + "".join(f"{round(c * 255):02x}" for c in color)
    raise ValueError(f"material: color={color!r} is not a colour — write '#rrggbb' or (r, g, b) in 0..1")


def _linear(hex_color):
    """'#rrggbb' (sRGB) → linear RGBA, what Blender's colour sockets hold."""
    srgb = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return (*(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb), 1.0)


def look(tag):
    """The values a tag stands for: its preset, changed where the call said."""
    spec = json.loads(tag)
    values = dict(metallic=0.0, opacity=1.0, transmission=0.0, coat=0.0, sheen=0.0, emission=0.0)
    values.update(PRESETS[spec.pop("kind")])
    values.update(spec)
    return values


def _name(tag):
    """A material's name: its preset, and what the program changed in it."""
    spec = json.loads(tag)
    kind = spec.pop("kind")
    return " ".join([kind, *(v if k == "color" else f"{k}={v:g}" for k, v in sorted(spec.items()))])


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
                          ("Alpha", v["opacity"]), ("Transmission Weight", v["transmission"]),
                          ("Coat Weight", v["coat"]), ("Sheen Weight", v["sheen"]),
                          ("Emission Color", rgba), ("Emission Strength", v["emission"])):
        bsdf.inputs[socket].default_value = value
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


def resolve():
    """Give every mesh the material of its nearest tagged ancestor-or-self; take ours off
    a mesh that has none any more. Nothing to do in a program that sets no material."""
    if not _core.dressed:
        return
    made = {m[TAG]: m for m in bpy.data.materials if TAG in m}
    for ob in sorted(bpy.data.objects, key=lambda o: o.name):
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
        if any(p.material_index for p in ob.data.polygons):
            ob.data.polygons.foreach_set("material_index", [0] * len(ob.data.polygons))


def dressed():
    """Whether any mesh of the scene wears one of our materials."""
    return _core.dressed and any(ob.type == "MESH" and any(m is not None and TAG in m for m in ob.data.materials)
                                 for ob in bpy.data.objects)
