"""Many rooted thin pieces in one mesh, with per-site fields."""
import numpy as np
import bpy

from . import _core
from .frames import Frame


def _field(value, points, normals, label, vector=False):
    count = len(points)
    shape = (count, 3) if vector else (count,)
    if callable(value):
        try:
            out = np.asarray(value(*points.T, normals.T), dtype=float)
            if out.shape != shape:
                raise ValueError('scalar callback')
        except Exception:
            try:
                out = np.asarray([value(*p, tuple(n)) for p, n in zip(points, normals)], dtype=float)
                out = out.reshape(shape)
            except Exception as exc:
                raise ValueError(f'tufts: invalid {label} callback: {exc}') from exc
    else:
        try:
            out = np.broadcast_to(np.asarray(value, dtype=float), shape)
        except (ValueError, TypeError) as exc:
            raise ValueError(f'tufts: invalid {label}') from exc
    if not np.isfinite(out).all():
        raise ValueError(f'tufts: {label} must be finite')
    return out


def tufts(name, sites, height, width, blades=5, lean=20, direction=None, shape="blade", seed=0):
    """One mesh, rooted at Frames in their shared parent space.

    height/width are positive lengths; lean is a maximum angle in [0, 85] degrees.
    Each accepts a scalar or (x,y,z,n) field; direction accepts a nonzero vector or
    field in the sites' space (default their Z). Array fields receive x/y/z (N,)
    and normals (3,N), returning (N,) or direction (N,3), like colour callbacks.
    Every blade has a vertex exactly at its site, even for tangential directions.
    blade: two triangles; cone: six triangles, a triangular double cone.
    """
    sites = [sites] if isinstance(sites, Frame) else list(sites)
    if not all(isinstance(f, Frame) for f in sites):
        raise TypeError('tufts: sites must be Frames')
    if isinstance(blades, bool) or not isinstance(blades, int) or blades < 1:
        raise ValueError('tufts: blades must be a positive integer')
    if shape not in ('blade', 'cone'):
        raise ValueError('tufts: shape must be "blade" or "cone"')
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError('tufts: seed must be a nonnegative integer')
    points = np.asarray([tuple(f.origin) for f in sites], dtype=float).reshape(-1, 3)
    normals = np.asarray([tuple(f.z) for f in sites], dtype=float).reshape(-1, 3)
    h = _field(height, points, normals, 'height')
    w = _field(width, points, normals, 'width')
    tilt = _field(lean, points, normals, 'lean')
    if np.any(h <= 0) or np.any(w <= 0) or np.any((tilt < 0) | (tilt > 85)):
        raise ValueError('tufts: height and width must be positive; lean must be in [0, 85] degrees')
    z = normals if direction is None else _field(direction, points, normals, 'direction', vector=True)
    lengths = np.linalg.norm(z, axis=1)
    if np.any(lengths == 0):
        raise ValueError('tufts: direction must be nonzero')
    z = z / lengths[:, None]
    # Stable transverse axes, also for combing exactly parallel to a site's normal.
    ref = np.zeros_like(z)
    ref[:, 2] = 1
    ref[np.abs(z[:, 2]) > .9] = (1, 0, 0)
    x = np.cross(ref, z)
    x /= np.linalg.norm(x, axis=1)[:, None]
    y = np.cross(z, x)
    rng = np.random.default_rng(seed)
    count = len(sites) * blades
    a = rng.uniform(0, 2 * np.pi, count)
    t = np.deg2rad(np.repeat(tilt, blades)) * rng.random(count)
    side = np.repeat(x, blades, axis=0) * np.cos(a)[:, None] + np.repeat(y, blades, axis=0) * np.sin(a)[:, None]
    axis = np.repeat(z, blades, axis=0) * np.cos(t)[:, None] + side * np.sin(t)[:, None]
    across = np.cross(axis, side)
    across /= np.linalg.norm(across, axis=1)[:, None]
    root = np.repeat(points, blades, axis=0)
    tip = root + axis * np.repeat(h, blades)[:, None]
    middle = (root + tip) / 2
    radius = np.repeat(w, blades)[:, None] / 2
    if shape == 'blade':
        vertices = np.stack((root, middle - across * radius, middle + across * radius, tip), axis=1)
        template = np.array([(0, 2, 1), (1, 2, 3)])
    else:
        other = np.cross(axis, across)
        ring = [middle + radius * (across * np.cos(a) + other * np.sin(a))
                for a in (0, 2*np.pi/3, 4*np.pi/3)]
        vertices = np.stack((root, *ring, tip), axis=1)
        template = np.array([(0, 2, 1), (0, 3, 2), (0, 1, 3), (4, 1, 2), (4, 2, 3), (4, 3, 1)])
    faces = (template[None, :, :] + np.arange(count)[:, None, None] * vertices.shape[1]).reshape(-1, 3)
    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(vertices.size // 3)
    mesh.vertices.foreach_set('co', vertices.ravel())
    mesh.loops.add(faces.size)
    mesh.loops.foreach_set('vertex_index', faces.ravel())
    mesh.polygons.add(len(faces))
    mesh.polygons.foreach_set('loop_start', np.arange(len(faces), dtype=np.int32) * 3)
    mesh.polygons.foreach_set('loop_total', np.full(len(faces), 3, dtype=np.int32))
    mesh.update(calc_edges=True)
    ob = _core.link(bpy.data.objects.new(name, mesh))
    ob[_core.NAME] = name
    return ob
