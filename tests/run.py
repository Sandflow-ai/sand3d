"""Run the suite under the Python that runs this file, then exit hard.

    python tests/run.py [-k PATTERN]

unittest, not pytest: the suite needs nothing beyond bpy. `os._exit` because
bpy 4.5 hangs at shutdown once a boolean has run in the process.
"""
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "src")]
# Tests that build in a fresh process start `sys.executable`: give it the library too.
os.environ["PYTHONPATH"] = os.pathsep.join(filter(None, [str(HERE.parent / "src"), os.environ.get("PYTHONPATH")]))

if __name__ == "__main__":
    argv = sys.argv[1:]
    loader = unittest.TestLoader()
    if "-k" in argv:
        loader.testNamePatterns = [f"*{argv[argv.index('-k') + 1]}*"]
    suite = loader.discover(str(HERE), pattern="test_*.py", top_level_dir=str(HERE))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if result.wasSuccessful() else 1)
