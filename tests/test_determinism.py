"""Every public verb gives the same mesh in two fresh processes.

The cases run twice, in two new interpreters with different hash seeds, the
second in reverse order. Runs under whichever Python runs the tests, so the same
file checks whichever bpy it runs under.
"""
import ast
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MARK = "@@sand3d-digests "


def run_cases(*args, seed="0", **extra_env):
    env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": f"{ROOT / 'src'}", **extra_env}
    done = subprocess.run([sys.executable, str(HERE / "run_cases.py"), *args], env=env,
                          capture_output=True, text=True, timeout=1800)
    lines = [l for l in done.stdout.splitlines() if l.startswith(MARK)]
    if not lines:
        raise AssertionError(f"run_cases.py printed no digests:\n{done.stderr[-3000:]}")
    return json.loads(lines[-1][len(MARK):])


def public_verbs():
    """`__all__` of the package, read from its source."""
    tree = ast.parse((ROOT / "src/sand3d/__init__.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "__all__" for t in node.targets):
            return set(ast.literal_eval(node.value))
    raise AssertionError("no __all__ in sand3d/__init__.py")


def registered_verbs():
    """The verbs the cases declare they exercise, read from their decorators."""
    tree = ast.parse((HERE / "cases.py").read_text(encoding="utf-8"))
    verbs = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and getattr(dec.func, "id", None) == "case":
                    verbs |= {ast.literal_eval(a) for a in dec.args}
    return verbs


class Determinism(unittest.TestCase):

    def test_every_public_verb_has_a_case(self):
        missing = sorted(public_verbs() - registered_verbs())
        self.assertEqual(missing, [], f"public verbs no case exercises: {missing}")

    def test_two_fresh_processes_agree(self):
        first = run_cases(seed="0")["digests"]
        second = run_cases("--reverse", seed="1")["digests"]
        errors = {k: v for k, v in first.items() if v.startswith("error")}
        self.assertEqual(errors, {}, "cases that raised")
        differ = sorted(k for k in first if first[k] != second.get(k))
        self.assertEqual(differ, [], f"cases whose mesh differs between two processes: {differ}")

    def test_the_harness_catches_a_nondeterministic_case(self):
        runs = [run_cases("selftest_unseeded", seed=s, SAND3D_HARNESS_SELFTEST="1")["digests"] for s in "01"]
        self.assertNotEqual(runs[0]["selftest_unseeded"], runs[1]["selftest_unseeded"])


if __name__ == "__main__":
    unittest.main()
