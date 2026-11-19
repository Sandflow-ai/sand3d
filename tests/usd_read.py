"""A USD stage read back by USD's own library, as JSON on stdout: what `test_export_usd`
compares with the URDF of the same program.

    .cache/venv-usd/bin/python tests/usd_read.py X.usda

Runs under a Python with `usd-core` (`pip install usd-core`), never under bpy: sand3d does not
take `pxr`. The physics is read by UsdPhysics' own parser, the stage checked by every
validator USD registers. Matrices are 4×4 rows acting on columns; quaternions (w, x, y, z).
"""
import json
import sys

from pxr import Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade, UsdValidation


def rows(m):
    """A Gf.Matrix4d (row vectors) as rows acting on columns."""
    return [[m[c][r] for c in range(4)] for r in range(4)]


def pose(position, orientation):
    q = orientation
    return {"position": list(position), "orientation": [q.GetReal(), *q.GetImaginary()]}


def main(path):
    stage = Usd.Stage.Open(path)
    cache = UsdGeom.XformCache()
    validators = UsdValidation.ValidationRegistry().GetOrLoadAllValidators()
    errors = [f"{e.GetName()}: {e.GetMessage()}" for e in UsdValidation.ValidationContext(validators).Validate(stage)]
    out = {"defaultPrim": stage.GetDefaultPrim().GetName(), "upAxis": UsdGeom.GetStageUpAxis(stage),
           "metersPerUnit": UsdGeom.GetStageMetersPerUnit(stage), "errors": errors,
           "articulations": [], "bodies": {}, "joints": {}, "meshes": {}, "materials": {}, "lights": {}}
    parsed = UsdPhysics.UsdPhysicsLoadStageFromPrimRange(stage, ["/"])
    for kind, (paths, descs) in parsed.items():
        for p, d in zip(paths, descs):
            if kind == UsdPhysics.ObjectType.Articulation:
                out["articulations"].append({"path": str(p), "roots": sorted(map(str, d.rootPrims)),
                                             "bodies": sorted(map(str, d.articulatedBodies)),
                                             "joints": sorted(map(str, d.articulatedJoints))})
            elif kind == UsdPhysics.ObjectType.RigidBody:
                out["bodies"][str(p)] = {"world": rows(cache.GetLocalToWorldTransform(stage.GetPrimAtPath(p)))}
            elif kind in (UsdPhysics.ObjectType.RevoluteJoint, UsdPhysics.ObjectType.PrismaticJoint):
                prim = stage.GetPrimAtPath(p)
                joint = {"type": "revolute" if kind == UsdPhysics.ObjectType.RevoluteJoint else "prismatic",
                         "body0": str(d.body0), "body1": str(d.body1), "axis": str(d.axis),
                         "local0": pose(d.localPose0Position, d.localPose0Orientation),
                         "local1": pose(d.localPose1Position, d.localPose1Orientation),
                         "limit": [d.limit.lower, d.limit.upper] if d.limit.enabled else None,
                         "articulated": not d.excludeFromArticulation, "mimic": None}
                schemas = prim.GetMetadata("apiSchemas")         # NewtonMimicAPI: a schema usd-core does not know
                if schemas is not None and "NewtonMimicAPI" in schemas.GetAddedOrExplicitItems():
                    joint["mimic"] = {"joint": str(prim.GetRelationship("newton:mimicJoint").GetTargets()[0]),
                                      "coef0": prim.GetAttribute("newton:mimicCoef0").Get(),
                                      "coef1": prim.GetAttribute("newton:mimicCoef1").Get()}
                out["joints"][str(p)] = joint
            elif kind not in (UsdPhysics.ObjectType.Scene,):
                out.setdefault("other", []).append(str(p))
    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.Mesh):
            mesh = UsdGeom.Mesh(prim)
            normals = mesh.GetNormalsAttr()
            bound = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]
            out["meshes"][str(prim.GetPath())] = {
                "world": rows(cache.GetLocalToWorldTransform(prim)),
                "points": [list(v) for v in mesh.GetPointsAttr().Get()],
                "counts": list(mesh.GetFaceVertexCountsAttr().Get()),
                "indices": list(mesh.GetFaceVertexIndicesAttr().Get()),
                "normals": [list(n) for n in normals.Get()], "interpolation": mesh.GetNormalsInterpolation(),
                "subdivision": mesh.GetSubdivisionSchemeAttr().Get(),
                "material": str(bound.GetPath()) if bound else None}
        elif prim.HasAPI(UsdLux.LightAPI):
            out["lights"][str(prim.GetPath())] = {
                "type": prim.GetTypeName(), "world": rows(cache.GetLocalToWorldTransform(prim)),
                "schemas": [s for s in prim.GetAppliedSchemas() if s != "LightAPI"],
                **{a.GetName(): (list(v) if hasattr(v, "__len__") else v)
                   for a in prim.GetAuthoredAttributes() if not a.GetName().startswith("xformOp")
                   for v in [a.Get()]}}
        elif prim.IsA(UsdShade.Shader):
            shader = UsdShade.Shader(prim)
            out["materials"][str(prim.GetParent().GetPath())] = {
                "id": shader.GetIdAttr().Get(),
                **{i.GetBaseName(): (list(v) if hasattr(v, "__len__") else v)
                   for i in shader.GetInputs() for v in [i.Get()]}}
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main(sys.argv[1])
