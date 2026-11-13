"""Build the golden corpus in this process and print its digests as one JSON line.

    python tests/run_golden.py [--write]

The corpus is what programs already written against sand3d build: every determinism
case, the example programs and the worked examples. Each starts
from an empty scene and is hashed by the determinism harness — vertices, faces, edges,
placement and every named attribute, so the provenance names too. `--write` records
the digests as `tests/golden/bpy-<major.minor>.json`, which `test_golden.py` holds
every later commit to. Exits through `os._exit`: bpy 4.5 hangs at shutdown once a
boolean has run.
"""
import importlib.util
import json
import os
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(HERE), str(ROOT / "src")]

import bpy  # noqa: E402
import sand3d as s3d  # noqa: E402
import cases  # noqa: E402,F401 — registers the cases
from harness import CASES, digest  # noqa: E402

MARK = "@@sand3d-golden "
GOLDEN = HERE / "golden"
# Cases whose digest changes with every edit of the source, by design.
UNPINNED = {"library_fingerprint"}
PROGRAMS = {"programs/weight_stack.py": ["weight_stack"], "programs/tufted_chair.py": ["tufted_chair"],
            "programs/cutlery.py": ["spoon", "fork"], "programs/washing_machine.py": ["washer", "washer_open"],
            "docs/examples/bracket.py": ["bracket"], "docs/examples/lamp.py": ["lamp"], "docs/examples/rack.py": ["rack"],
            "docs/examples/chair.py": ["chair"], "docs/examples/gate.py": ["gate"]}


def golden_path():
    return GOLDEN / f"bpy-{bpy.app.version[0]}.{bpy.app.version[1]}.json"


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def corpus():
    """name -> a function that builds it and returns what the case returns."""
    out = {f"case:{name}": fn for name, (fn, _) in CASES.items() if name not in UNPINNED}
    for rel, functions in PROGRAMS.items():
        for function in functions:
            out[f"program:{Path(rel).stem}.{function}"] = \
                lambda rel=rel, function=function: getattr(load(ROOT / rel), function)()
    return out


def main(argv):
    out = {}
    for name, fn in corpus().items():
        s3d.empty_scene()
        s3d.units("mm")   # a case may have set another
        try:
            out[name] = digest(fn())
        except Exception:
            out[name] = "error: " + traceback.format_exc(limit=-3).strip().splitlines()[-1]
            traceback.print_exc()
    if "--write" in argv:
        GOLDEN.mkdir(exist_ok=True)
        golden_path().write_text(json.dumps({"bpy": bpy.app.version_string, "digests": out}, indent=1) + "\n", encoding="utf-8")
    print(MARK + json.dumps({"digests": out, "golden": str(golden_path())}), flush=True)


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
