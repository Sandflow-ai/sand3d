"""What programs already written against sand3d build, it still builds — to the bit.

`run_golden.py` builds the corpus in a fresh process; its digests must equal the ones
recorded for this bpy in `tests/golden/`. A change here is a change of behaviour: a fix
that moves geometry updates the file (`python tests/run_golden.py --write`, under every
bpy the suite runs on) in the same PR, where the diff shows which pieces moved.
"""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MARK = "@@sand3d-golden "


class Golden(unittest.TestCase):
    maxDiff = None   # a moved piece shows its recorded and built digests, whole

    def test_the_corpus_builds_as_recorded(self):
        env = {**os.environ, "PYTHONPATH": f"{ROOT / 'src'}"}
        done = subprocess.run([sys.executable, str(HERE / "run_golden.py")], env=env, capture_output=True,
                              text=True, timeout=1800)
        lines = [l for l in done.stdout.splitlines() if l.startswith(MARK)]
        if not lines:
            raise AssertionError(f"run_golden.py printed no digests:\n{done.stderr[-3000:]}")
        run = json.loads(lines[-1][len(MARK):])
        golden = Path(run["golden"])
        self.assertTrue(golden.is_file(), f"no golden digests for this bpy: run tests/run_golden.py --write "
                                          f"to create {golden.name}")
        recorded = json.loads(golden.read_text(encoding="utf-8"))["digests"]
        built = run["digests"]
        errors = sorted(k for k, v in built.items() if v.startswith("error"))
        self.assertEqual(errors, [], "pieces that raised")
        self.assertEqual(sorted(set(recorded) - set(built)), [], "pieces no longer built")
        new = sorted(set(built) - set(recorded))
        self.assertEqual(new, [], f"pieces not recorded in {golden.name}: " + ", ".join(f"{k}: {built[k]}" for k in new))
        moved = sorted(f"{k}: {recorded[k]} -> {built[k]}" for k in recorded if recorded[k] != built[k])
        self.assertEqual(moved, [], f"pieces that no longer build as recorded in {golden.name}")


if __name__ == "__main__":
    unittest.main()
