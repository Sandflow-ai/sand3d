"""A picture of a scene under its own lights: what each light lights, and the shadows it casts."""
import math
import os

import bpy
from mathutils import Vector

from . import _core
from .lights import LUMENS_PER_WATT, ambient
from .materials import _hex, _linear

#: Threads a picture is traced on: a few, so that a machine building other scenes stays usable.
THREADS = 4


def render(root, path, eye, target=(0, 0, 0), fov=40, size=(960, 640), background=None, exposure=1.0, samples=48):
    """Writes a picture (.png, .jpg) of `root`'s tree, lit by the lights it holds and by nothing else.

    The camera stands at `eye` and looks at `target`, both in the program's unit, upright;
    `fov` is its vertical angle of view in degrees, `size` the picture in pixels. Only what
    is under `root` is seen and only its lights shine: a scene with no light is black.

    Lights are counted in lumens and lux, lengths in the program's unit: the picture is
    traced with distances in metres, so a bulb lights a room as it would. `exposure`
    multiplies the picture's brightness: at 1, a white matte face that receives about 3 lux
    (π) comes out white — the scale three.js and the GLB viewers show a scene on, where a
    sun of 3 lux is a full key light. A room lit by real bulbs (hundreds of lux) wants a
    smaller one. `background` is the colour behind the scene ("#rrggbb" or (r, g, b)); None
    shows the sky an ambient light gives, black without one. `samples` trades grain for
    time. Shadows, soft shadows (`light(size=)`), light bounced from one face to another
    and the look of each material are traced: this is Blender's Cycles.

    Nothing of the scene is changed: the camera and the sky made for the picture are
    removed, and every setting put back."""
    from .assembly import Handle
    root = root.root if isinstance(root, Handle) else root
    if not isinstance(root, bpy.types.Object):
        raise TypeError(f"render: the root of a scene is expected first, not {root!r}")
    suffix = os.path.splitext(str(path))[1].lower()
    if suffix not in (".png", ".jpg", ".jpeg"):
        raise ValueError(f"render: {suffix or 'a path with no extension'} is not a picture sand3d writes: "
                         f"name the file .png or .jpg")
    eye, target = _point("eye", eye), _point("target", target)
    if (target - eye).length < 1e-9:
        raise ValueError("render: eye and target are the same point: the camera looks nowhere")
    if isinstance(fov, bool) or not isinstance(fov, (int, float)) or not 0 < fov < 180:
        raise ValueError(f"render: fov is the vertical angle of view, above 0 and under 180 degrees, not {fov!r}")
    if (not isinstance(size, (tuple, list)) or len(size) != 2
            or any(isinstance(v, bool) or not isinstance(v, int) or not 0 < v <= 8192 for v in size)):
        raise ValueError(f"render: size is (width, height) in pixels, each from 1 to 8192, not {size!r}")
    if isinstance(exposure, bool) or not isinstance(exposure, (int, float)) or not exposure > 0:
        raise ValueError(f"render: exposure is a number above 0, not {exposure!r}")
    if isinstance(samples, bool) or not isinstance(samples, int) or not 1 <= samples <= 4096:
        raise ValueError(f"render: samples is a whole number from 1 to 4096, not {samples!r}")
    try:
        behind = None if background is None else _linear(_hex(background, "background"))[:3]
    except ValueError as exc:
        raise ValueError(str(exc).replace("material:", "render:", 1)) from exc

    scene = bpy.context.scene
    mine = {root, *root.children_recursive}
    gain = LUMENS_PER_WATT * exposure                  # 1 lux on a white face -> 1 / π in the picture
    metres = _core.MM / 1000                           # one unit of the program, in metres
    sky, soil = Vector((0, 0, 0)), Vector((0, 0, 0))
    for ob in mine:
        said = ambient(ob)
        if said is not None:                           # a face turned up gets π x the sky's radiance
            lux, above, below = said
            sky += Vector(above) * lux / (LUMENS_PER_WATT * math.pi)
            soil += Vector(below) * lux / (LUMENS_PER_WATT * math.pi)
    behind = sky * gain if behind is None else Vector(behind)   # shown as given, whatever the exposure

    hidden = {ob: ob.hide_render for ob in scene.objects}
    lamps = {ob.data: ob.data.energy for ob in mine if ob.type == "LIGHT" and ob.data.type in ("POINT", "SPOT")}
    look, cycles = scene.view_settings, scene.cycles
    was = {(holder, key): getattr(holder, key) for holder, key in (
        (scene, "camera"), (scene, "world"), (scene.render, "engine"), (scene.render, "resolution_x"),
        (scene.render, "resolution_y"), (scene.render, "resolution_percentage"), (scene.render, "filepath"),
        (scene.render, "film_transparent"), (scene.render, "threads_mode"), (scene.render, "threads"),
        (scene.render.image_settings, "file_format"), (scene.render.image_settings, "color_mode"),
        (look, "view_transform"), (look, "look"), (look, "exposure"), (look, "gamma"))}
    traced = {key: getattr(cycles, key) for key in ("samples", "use_denoising", "device", "seed",
                                                     "use_adaptive_sampling")}
    camera = world = lens = None
    try:
        scene.render.engine = "CYCLES"
        for ob in scene.objects:
            ob.hide_render = ob not in mine
        for data, watts in lamps.items():              # Blender counts a lamp's distance in its own unit
            data.energy = watts / metres ** 2
        lens = bpy.data.cameras.new("s3d~camera")
        lens.sensor_fit, lens.angle_y = "VERTICAL", math.radians(fov)
        reach = max((_core.world(ob).translation - eye).length for ob in mine) + 1
        lens.clip_start, lens.clip_end = reach / 1e5, reach * 100
        camera = bpy.data.objects.new("s3d~camera", lens)
        camera.location = eye
        camera.rotation_euler = (target - eye).to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(camera)
        world = _sky(sky, soil, behind / gain)
        scene.camera, scene.world = camera, world
        scene.render.resolution_x, scene.render.resolution_y = size
        scene.render.resolution_percentage, scene.render.film_transparent = 100, False
        scene.render.threads_mode, scene.render.threads = "FIXED", min(THREADS, os.cpu_count() or 1)
        scene.render.image_settings.file_format = "PNG" if suffix == ".png" else "JPEG"
        scene.render.image_settings.color_mode = "RGB"
        look.view_transform, look.look, look.gamma = "Standard", "None", 1.0
        look.exposure = math.log2(gain)
        cycles.samples, cycles.device, cycles.seed, cycles.use_adaptive_sampling = samples, "CPU", 0, False
        try:
            cycles.use_denoising = True
        except Exception:                              # a Blender built without a denoiser: more grain, same picture
            pass
        scene.render.filepath = os.path.abspath(str(path))
        bpy.ops.render.render(write_still=True)
    finally:
        for (holder, key), value in was.items():
            setattr(holder, key, value)
        for key, value in traced.items():
            setattr(cycles, key, value)
        for data, watts in lamps.items():
            data.energy = watts
        for ob, flag in hidden.items():
            ob.hide_render = flag
        if camera is not None:
            bpy.data.objects.remove(camera)
        if lens is not None:
            bpy.data.cameras.remove(lens)
        if world is not None:
            bpy.data.worlds.remove(world)
    return path


def _point(what, value):
    if (not isinstance(value, (tuple, list, Vector)) or len(value) != 3
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value)):
        raise ValueError(f"render: {what} is a point (x, y, z), not {value!r}")
    return Vector(value)


def _sky(above, below, behind):
    """A world that lights with `above` from the upper half and `below` from the lower one (radiances), and shows
    `behind` to the camera."""
    world = bpy.data.worlds.new("s3d~sky")
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputWorld")
    way = nodes.new("ShaderNodeTexCoord")                       # the direction a ray leaves in
    axes = nodes.new("ShaderNodeSeparateXYZ")
    up = nodes.new("ShaderNodeMath")
    up.operation = "GREATER_THAN"
    up.inputs[1].default_value = 0.0
    half = nodes.new("ShaderNodeMixRGB")
    half.inputs[1].default_value, half.inputs[2].default_value = (*below, 1), (*above, 1)
    path = nodes.new("ShaderNodeLightPath")
    seen = nodes.new("ShaderNodeMixRGB")
    seen.inputs[2].default_value = (*behind, 1)
    glow = nodes.new("ShaderNodeBackground")
    glow.inputs["Strength"].default_value = 1.0
    links.new(way.outputs["Generated"], axes.inputs[0])
    links.new(axes.outputs["Z"], up.inputs[0])
    links.new(up.outputs[0], half.inputs[0])
    links.new(half.outputs[0], seen.inputs[1])
    links.new(path.outputs["Is Camera Ray"], seen.inputs[0])
    links.new(seen.outputs[0], glow.inputs["Color"])
    links.new(glow.outputs[0], out.inputs["Surface"])
    return world
