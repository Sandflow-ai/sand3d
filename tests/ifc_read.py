"""An IFC file read back by IfcOpenShell, as JSON on stdout: what `test_export_ifc` holds
the export to.

    .cache/venv-ifc/bin/python tests/ifc_read.py X.ifc

Runs under a Python with IfcOpenShell (`pip install ifcopenshell`), never under bpy: sand3d
does not take it. The file is checked against the schema and its where-rules (EXPRESS
rules on), every product with a body built by IfcOpenShell's geometry kernel, its
volume in cubic metres, and every light source as IfcOpenShell reads it.
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
    solids, lights = {}, {}
    for product in f.by_type("IfcProduct"):
        if product.Representation is None:
            continue
        kinds = {r.RepresentationIdentifier for r in product.Representation.Representations}
        if "Body" in kinds:
            shape = ifcopenshell.geom.create_shape(settings, product)
            solids[product.Name] = ifcopenshell.util.shape.get_volume(shape.geometry)
        for r in product.Representation.Representations:
            for item in r.Items if r.RepresentationIdentifier == "Lighting" else ():
                place = item.Position
                spread = item.LightDistributionDataSource
                lights[product.Name] = {
                    "product": product.is_a(), "type": product.PredefinedType, "source": item.is_a(),
                    "name": item.Name, "lm": item.LuminousFlux, "kelvin": item.ColourTemperature,
                    "colour": [item.LightColour.Red, item.LightColour.Green, item.LightColour.Blue],
                    "at": list(place.Location.Coordinates), "z": list(place.Axis.DirectionRatios),
                    "x": list(place.RefDirection.DirectionRatios), "curve": spread.LightDistributionCurve,
                    "planes": [[d.MainPlaneAngle, list(d.SecondaryPlaneAngle), list(d.LuminousIntensity)]
                               for d in spread.DistributionData]}
    units = sorted(u.UnitType for u in f.by_type("IfcProject")[0].UnitsInContext.Units)
    json.dump({"schema": f.schema, "errors": errors, "solids": solids, "lights": lights, "units": units}, sys.stdout)


if __name__ == "__main__":
    logging.disable(logging.WARNING)
    main(sys.argv[1])
