"""Named plate load combinations, full gravity, migrations and snapshot gates."""
from copy import deepcopy
from dataclasses import replace
import unittest
from unittest.mock import patch
import numpy as np
from Pynite import FEModel3D

from pynitegui.qt.model import Material
from pynitegui.qt.plate_model import (PlateDefinition, analyze_plate, plate_signature,
                                     select_plate_combination)


class PlateLoadTests(unittest.TestCase):
    def test_named_pressure_combinations_linearity_in_all_planes_and_families(self):
        for family in ("Quad", "Rect"):
            for plane in ("XY", "XZ", "YZ"):
                with self.subTest(family=family, plane=plane):
                    definition = PlateDefinition(element_type=family, plane=plane, mesh_size=30.,
                        pressure=-1e-7, load_case="Dead", additional_pressures={"Live": -2e-7, "Uplift": 5e-8},
                        combinations={"Service": {"Dead": 1.2, "Live": 1.6, "Uplift": 1.},
                                      "Reverse": {"Dead": -2.}, "Zero": {"Dead": 1., "Live": -.5}})
                    result = analyze_plate(definition)
                    self.assertEqual(result["combination"], "Plate")
                    self.assertEqual(set(result["solutions"]), {"Plate", "Service", "Reverse", "Zero"})
                    for name, ratio in (("Service", 3.9), ("Reverse", -2.), ("Zero", 0.)):
                        selected = select_plate_combination(result, name)
                        self.assertEqual(selected["snapshot_id"], result["snapshot_id"])
                        self.assertEqual(selected["model_signature"], plate_signature(definition))
                        for key in ("displacement", "reactions", "moments", "shears"):
                            if result[key] is not None:
                                np.testing.assert_allclose(selected[key], ratio*result[key], rtol=1e-8, atol=1e-12)
                        self.assertEqual(len(selected["equilibrium"]), 6)
                        self.assertTrue(all(abs(row["residual"]) <= row["tolerance"] for row in selected["equilibrium"]))
                    with self.assertRaisesRegex(ValueError, "Unknown"):
                        select_plate_combination(result, "not solved")

    def test_horizontal_self_weight_matches_independent_navier_and_factoring(self):
        for family in ("Quad", "Rect"):
            definition = PlateDefinition(element_type=family, plane="XZ", width=60., height=60., mesh_size=3.75,
                pressure=.00001, load_case="Dead", load_factor=.7,
                material=Material("Concrete", E=3600., nu=.2, rho=.00009),
                additional_pressures={"Live": -.00005}, combinations={"Service": {"Dead": 1.2, "Live": 1.5}},
                self_weight_case="Dead", self_weight_factor=1.3)
            result = analyze_plate(definition)
            self.assertEqual(definition.normal.tolist(), [0., -1., 0.])
            pressure = .00001+.00009*1.*1.3
            D = 3600./(12*(1-.2**2))
            for name, q in (("Plate", pressure*.7), ("Service", pressure*1.2-.00005*1.5)):
                selected = select_plate_combination(result, name)
                self.assertAlmostEqual(selected["pressure"], q, places=14)
                expected = .00406235*q*60**4/D
                self.assertAlmostEqual(max(selected["displacement"])/expected, 1., delta=.01)
                self.assertAlmostEqual(selected["reactions"].sum(), -q*60*60, places=8)

    def test_opening_removes_pressure_and_weight_with_independent_first_moments(self):
        definition = PlateDefinition(plane="XZ", origin=[17., -31., 49.], mesh_size=30.,
            material=Material("Concrete", E=3600., nu=.2, rho=.00009), self_weight_case="Dead", load_case="Dead",
            additional_pressures={"Live": -.00005}, combinations={"Factored": {"Dead": 1.2, "Live": 1.6}},
            openings=[dict(name="OffCentre", x_left=30., y_bott=15., width=30., height=60.)])
        result = select_plate_combination(analyze_plate(definition), "Factored")
        q = (-.00001+.00009)*1.2-.00005*1.6
        area = 120**2-30*60
        first_x = 120**2*60-30*60*45
        first_z = 120**2*60-30*60*45
        rows = {row["component"]: row for row in result["equilibrium"]}
        self.assertAlmostEqual(result["applied"], q*area, places=12)
        self.assertAlmostEqual(rows["FY"]["applied"], -q*area, places=12)
        self.assertAlmostEqual(rows["MX"]["applied"], q*first_z, places=9)
        self.assertAlmostEqual(rows["MZ"]["applied"], -q*first_x, places=9)

    def test_v1_v2_migrate_without_changing_inputs_or_adding_gravity(self):
        definition = PlateDefinition(material=Material("Concrete", E=3600., nu=.2, rho=.00009))
        loading = ("additional_pressures", "combinations", "self_weight_case", "self_weight_factor")
        geometry = ("element_type", "origin", "x_control", "y_control", "openings", "kx_mod", "ky_mod", "node_start", "element_start", "mesh_name")
        for version in (1, 2):
            data = definition.to_dict()
            for key in (*loading, *(geometry if version == 1 else ())):
                data.pop(key)
            data["version"] = version
            before = deepcopy(data)
            restored = PlateDefinition.from_dict(data)
            self.assertEqual(restored, definition)
            self.assertEqual(data, before)
            self.assertIsNone(restored.self_weight_case)
            self.assertEqual(restored.load_combinations, {"Plate": {"Case 1": 1.}})
        for key in loading:
            broken = definition.to_dict()
            broken.pop(key)
            with self.assertRaises(ValueError):
                PlateDefinition.from_dict(broken)

    def test_invalid_references_bounds_and_vertical_gravity_rejected(self):
        base = PlateDefinition()
        for changes in ({"additional_pressures": {"Case 1": 1.}}, {"additional_pressures": {"Bad": True}},
                        {"additional_pressures": {"Bad": float("nan")}}, {"additional_pressures": []},
                        {"combinations": {"Plate": {"Case 1": 2.}}}, {"combinations": {"Mix": {"missing": 1.}}},
                        {"combinations": {"Mix": {"Case 1": True}}}, {"combinations": {"Mix": {"Case 1": 1e7}}},
                        {"self_weight_case": "missing"}, {"self_weight_case": "Case 1", "plane": "YZ"},
                        {"self_weight_case": "Case 1", "plane": "XY"}, {"self_weight_factor": 0.}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(base, **changes).validate()

    def test_any_combination_force_moment_or_nonfinite_failure_rejects_every_result(self):
        definition = PlateDefinition(mesh_size=60., combinations={"Factored": {"Case 1": 2.}})
        original = FEModel3D.analyze_linear
        for component, increment, message in (("RxnFZ", .001, "Factored.*FZ"),
                                               ("RxnMX", .01, "Factored.*MX"),
                                               ("DZ", float("nan"), "nonfinite")):
            def tamper(model, *args, **kwargs):
                original(model, *args, **kwargs)
                values = getattr(next(iter(model.nodes.values())), component)
                values["Factored"] += increment
            with patch.object(FEModel3D, "analyze_linear", tamper), self.assertRaisesRegex(ValueError, message):
                analyze_plate(definition)

    def test_primary_case_rename_preserves_named_combinations_and_weight(self):
        definition = PlateDefinition(plane="XZ", load_case="Dead", self_weight_case="Dead",
            additional_pressures={"Live": -.00002}, combinations={"Service": {"Dead": 1., "Live": .7}})
        definition.rename_case("Dead", "Permanent")
        self.assertEqual(definition.combinations["Service"], {"Permanent": 1., "Live": .7})
        self.assertEqual(definition.self_weight_case, "Permanent")
        self.assertEqual(definition.load_combinations["Plate"], {"Permanent": 1.})
        definition.validate()
        self.assertEqual(PlateDefinition.from_dict(definition.to_dict()), definition)
        self.assertEqual(plate_signature(definition), plate_signature(replace(definition, unit_system="si")))


if __name__ == "__main__":
    unittest.main()
