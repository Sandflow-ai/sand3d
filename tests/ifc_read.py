"""An IFC file read back by IfcOpenShell, as JSON on stdout: what `test_export_ifc` holds
the export to.

    .cache/venv-ifc/bin/python tests/ifc_read.py X.ifc

Runs under a Python with IfcOpenShell (`pip install ifcopenshell`), never under bpy: sand3d
does not take it. The file is checked against the schema and its where-rules (EXPRESS
rules on), and every product with a body built by IfcOpenShell's geometry kernel, its
volume in cubic metres.
"""
import json
import logging
import sys

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.shape
import ifcopenshell.validate


def main(path):
    f = ifcopenshell.open(path)
    log = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(f, log, express_rules=True)
    errors = [f"{e.get('instance')}: {e.get('message')}" for e in log.statements
              if e["level"].lower() in ("error", "warning")]
    settings = ifcopenshell.geom.settings()
    solids = {}
    for product in f.by_type("IfcProduct"):
        if product.Representation is None:
            continue
        shape = ifcopenshell.geom.create_shape(settings, product)
        solids[product.Name] = ifcopenshell.util.shape.get_volume(shape.geometry)
    json.dump({"schema": f.schema, "errors": errors, "solids": solids}, sys.stdout)


if __name__ == "__main__":
    logging.disable(logging.WARNING)
    main(sys.argv[1])
