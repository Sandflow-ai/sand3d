"""Mesh descendants shared by surface edits."""
def meshes(ob):
    from .assembly import Handle
    if isinstance(ob, Handle):
        ob = ob.root
    roots = ob if isinstance(ob, (list, tuple)) else [ob]
    result = []
    for root in roots:
        if isinstance(root, (list, tuple)):
            parts = meshes(root)
        else:
            parts = [p for p in [root, *root.children_recursive] if p.type == "MESH"]
        result.extend(p for p in parts if p not in result)
    return result


def _surface(mesh):
    """Triangulated attribute source in the receiving object's local frame."""
    from mathutils.bvhtree import BVHTree
    from ._coordinates import NAMES
    mesh.calc_loop_triangles()
    triangles = [tuple(t.vertices) for t in mesh.loop_triangles]
    points = [v.co.copy() for v in mesh.vertices]
    values = [[mesh.attributes[n].data[i].value for n in NAMES] for i in range(len(points))]
    return BVHTree.FromPolygons(points, triangles, all_triangles=True), triangles, points, values


def _project(bm, sources, operand):
    """Interpolate construction labels on each boolean operand's surface.

    This transfers vertex attributes to newly intersected vertices; no centreline is
    reconstructed. At a shared intersection the first operand owns the label.
    """
    from mathutils import Vector, geometry
    from ._coordinates import NAMES
    layers = [bm.verts.layers.float.get(n) for n in NAMES]
    for v in bm.verts:
        owner = min((f[operand] for f in v.link_faces),default=0)
        tree, triangles, points, values = sources[owner]
        hit, _, index, _ = tree.find_nearest(v.co)
        if hit is None:
            continue
        ids = triangles[index]
        weights = geometry.barycentric_transform(hit, *(points[i] for i in ids),
                      Vector((1,0,0)),Vector((0,1,0)),Vector((0,0,1)))
        for k,layer in enumerate(layers):
            v[layer] = sum(w*values[i][k] for w,i in zip(weights,ids))
