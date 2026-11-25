"""Construction labels, in program units, independent of later placement."""
import sys

import numpy as np

NAMES = ('.s3d_s', '.s3d_x', '.s3d_y', '.s3d_extent')
def height_coordinates(ob, height):
    layers = [ob.data.attributes.new(name=n, type='FLOAT', domain='POINT') for n in NAMES]
    for v in ob.data.vertices:
        for a,value in zip(layers,(v.co.z,v.co.x,v.co.y,height)):
            a.data[v.index].value = value

def face_u(mesh):
    s,e = mesh.attributes.get(NAMES[0]),mesh.attributes.get(NAMES[-1])
    if s is None or e is None:
        return None
    coordinate = np.empty(len(mesh.vertices), dtype=np.float64)
    extent = np.empty_like(coordinate)
    s.data.foreach_get('value', coordinate)
    e.data.foreach_get('value', extent)
    ratio = np.full_like(coordinate, np.nan)
    np.divide(coordinate, extent, out=ratio, where=extent != 0)
    vertices = np.empty(len(mesh.loops), dtype=np.int32)
    sizes = np.empty(len(mesh.polygons), dtype=np.int32)
    mesh.loops.foreach_get('vertex_index', vertices)
    mesh.polygons.foreach_get('loop_total', sizes)
    sums = np.zeros(len(sizes), dtype=np.float64)
    if sys.version_info < (3, 12):
        np.add.at(sums, np.repeat(np.arange(len(sizes)), sizes), ratio[vertices])
    else:
        # Python 3.12+ sum uses compensated addition. Keep its operation order,
        # vectorising across faces rather than changing the reduction per face.
        starts = np.empty(len(sizes), dtype=np.int32)
        mesh.polygons.foreach_get('loop_start', starts)
        for width in np.unique(sizes):
            ids = np.flatnonzero(sizes == width)
            hi, lo = np.zeros(len(ids)), np.zeros(len(ids))
            for corner in range(int(width)):
                x = ratio[vertices[starts[ids] + corner]]
                total = hi + x
                lo += np.where(np.abs(hi) >= np.abs(x), (hi-total)+x, (x-total)+hi)
                hi = total
            sums[ids] = hi + np.where(np.isfinite(lo), lo, 0)

    return (sums / sizes).tolist()
