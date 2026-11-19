"""Build the golden corpus in one unit and dump every piece, in millimetres, as JSON.

    python tests/run_units.py OUT.json [--unit mm|cm|m]

Under `--unit` other than mm the programs, written in millimetres, run through
`unitshim` (every length they pass × the unit's size) with `s3d.units` set to match:
the library builds in that unit, and the dump converts back to millimetres — vertex
positions and placements × the unit's size in mm; what a piece returns is converted
by the shim already. `test_units` compares a millimetre dump with another unit's.
Exits through `os._exit`: bpy 4.5 hangs at shutdown once a boolean has run.
"""
import json
import os
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "src")]

import bpy  # noqa: E402
import sand3d as s3d  # noqa: E402
from harness import world  # noqa: E402
from run_golden import corpus  # noqa: E402

MARK = "@@sand3d-units "
#: The units' sizes in millimetres. `p2` is not public: 1 024 mm, a power of two, so that
#: scaling is exact in floating point and the two builds must agree to the last bit.
MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "p2": 1024.0}
#: Pieces that are no program in millimetres: a GLB is in metres whatever the unit, and
#: `metre_bracket` sets its own.
SKIPPED = {"case:export_glb", "case:export_articulated", "case:export_meshes", "case:metre_bracket"}


def plain(value):
    """`value` as JSON: matrices and vectors as lists, library objects by their fields."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in sorted(value.items())}
    if isinstance(value, bpy.types.ID):
        return f"<{type(value).__name__}>"
    if hasattr(value, "__dict__") and not isinstance(value, type):
        skip = ("part", "_basis") if type(value).__name__ == "Frame" else ()   # where it was read: no value
        return {type(value).__name__: {k: plain(getattr(value, k)) for k in sorted(vars(value)) if k not in skip}}
    try:
        return [plain(v) for v in value]
    except TypeError:
        return repr(value)


def dump(ob, f):
    """One object: its given name, placement and mesh, lengths × f."""
    m = world(ob)
    out = {"name": ob.get("s3d_name", ob.name.split(".")[0]), "type": ob.type,
           "world": [[m[r][c] * (f if c == 3 and r < 3 else 1) for c in range(4)] for r in range(4)]}
    if ob.type == "MESH":
        me = ob.data
        out["verts"] = [[c * f for c in v.co] for v in me.vertices]
        out["edges"] = [list(e.vertices) for e in me.edges]
        out["faces"] = [list(p.vertices) for p in me.polygons]
        out["tags"] = {a.name: [i for i, d in enumerate(a.data) if d.value] for a in me.attributes
                       if a.name.startswith(("s3d_face:", "s3d_edge:"))}
    if "s3d~joints" in ob:
        out["joints"] = joints(ob, f)
    return out


def joints(ob, f):
    """An object's joints, lengths × f: the pivot's translation, and a prismatic joint's
    range and value; a ratio across kinds is a length per degree or a degree per length."""
    from sand3d.joints import joints_of, leader_of
    out = []
    for k, j in enumerate(joints_of(ob)):
        j = dict(j)
        j["pivot"] = [v * f if i in (3, 7, 11) else v for i, v in enumerate(j["pivot"])]
        slide = j["kind"] == "prismatic"
        if slide:
            j["range"] = None if j["range"] is None else [v * f for v in j["range"]]
            j["value"] *= f
        if j["follows"] is not None:
            lead = joints_of(leader_of(ob, k))[j["follows"]]["kind"] == "prismatic"
            j["ratio"] *= f if slide and not lead else (1 / f if lead and not slide else 1)
        out.append(j)
    return out


def main(argv):
    target = Path(argv[0])
    unit = argv[argv.index("--unit") + 1] if "--unit" in argv else "mm"
    f = MM[unit]
    if unit != "mm":
        import unitshim
        unitshim.install(1 / f)
    if unit == "p2":
        from sand3d import _core
        _core.UNITS["p2"] = f
    out = {}
    for name, fn in corpus().items():
        if name in SKIPPED:
            continue
        s3d.empty_scene()
        if hasattr(s3d, "units"):
            s3d.units(unit)
        try:
            returned = fn()
            out[name] = {"objects": [dump(ob, f) for ob in sorted(bpy.data.objects, key=lambda o: o.name)],
                         "returned": plain(returned)}
        except Exception:
            out[name] = {"error": traceback.format_exc(limit=-3).strip().splitlines()[-1]}
            traceback.print_exc()
    target.write_text(json.dumps({"unit": unit, "bpy": bpy.app.version_string, "pieces": out}), encoding="utf-8")
    print(MARK + str(target), flush=True)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
        code = 0
    except BaseException:
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
