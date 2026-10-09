"""Independent resultants, signed distributions, spatial axes and result status."""
import contextlib
import io
import os
import unittest
from dataclasses import replace
from unittest.mock import patch
import numpy as np
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('PYNITEGUI_NO_WEBENGINE', '1')
from PySide6.QtWidgets import QApplication, QMessageBox
from pynitegui.qt.analysis import analyze
from pynitegui.qt.analysis_jobs import CANCELLED
from pynitegui.qt.app import MainWindow
from pynitegui.qt.equilibrium import check_equilibrium
from pynitegui.qt.examples import EXAMPLES, example_project
from pynitegui.qt.model import Project, Load
from pynitegui.qt.spatial_model import SpatialProject, SpatialLoad
from pynitegui.qt.units import UNIT_SYSTEMS


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


def cantilever():
    project = Project()
    project.add_member((0, 0), (120, 0))
    project.nodes['N1'].support = 'fixed'
    return project


def values(check, kind='applied'):
    return {row.component: getattr(row, kind) for row in check.rows}


class EquilibriumTests(unittest.TestCase):
    def test_partial_trapezoid_and_nodal_couple(self):
        project = cantilever()
        project.loads['D'] = Load('D', 'M1', 'FY', -1, .25, 'distributed', -3, .75)
        project.loads['M'] = Load('M', 'N2', 'MZ', 7)
        check = check_equilibrium(project, solve(project))
        actual = values(check)
        self.assertEqual(actual['FX'], 0)
        self.assertAlmostEqual(actual['FY'], -120)
        self.assertAlmostEqual(actual['MZ'], -7793)
        self.assertTrue(check.passed)

    def test_zero_resultant_distribution_retains_moment(self):
        project = cantilever()
        project.loads['D'] = Load('D', 'M1', 'FY', 1, 0, 'distributed', -1, 1)
        check = check_equilibrium(project, solve(project))
        self.assertAlmostEqual(values(check)['FY'], 0)
        self.assertAlmostEqual(values(check)['MZ'], -2400)
        self.assertTrue(check.passed)

    def test_oblique_local_force_and_reference_translation(self):
        project = Project()
        project.add_member((1e8, -2e8), (1e8 + 120, -2e8 + 90))
        project.nodes['N1'].support = 'fixed'
        project.loads['P'] = Load('P', 'M1', 'Local y', 4, .25)
        check = check_equilibrium(project, solve(project))
        self.assertEqual(check.origin, (1e8, -2e8, 0))
        self.assertAlmostEqual(values(check)['FX'], -2.4)
        self.assertAlmostEqual(values(check)['FY'], 3.2)
        self.assertAlmostEqual(values(check)['MZ'], 150)
        self.assertTrue(check.passed)
        project.members['M1'].start, project.members['M1'].end = 'N2', 'N1'
        project.loads['P'].position = .75
        project.loads['P'].magnitude = -4
        reversed_check = check_equilibrium(project, solve(project))
        for component, value in values(check).items():
            self.assertAlmostEqual(values(reversed_check)[component], value)

    def test_factor_omission_sign_and_self_weight(self):
        project = cantilever()
        project.set_load_case('Weight')
        project.set_load_case('Unused')
        project.self_weight_case = 'Weight'
        project.self_weight_factor = 1.3
        project.loads['P'] = Load('P', 'N2', 'FY', -2)
        project.set_combination('Reverse', {'Case 1': -2, 'Weight': .5})
        project.set_combination('Empty', {'Unused': 1})
        result = solve(project)
        reverse = check_equilibrium(project, result.for_combination('Reverse'))
        self.assertAlmostEqual(values(reverse)['FY'], 4 - .5 * project.self_weight_total())
        self.assertAlmostEqual(values(reverse)['MZ'], 480 - .5 * project.self_weight_total() * 60)
        self.assertTrue(reverse.passed)
        self.assertEqual(list(values(check_equilibrium(project, result.for_combination('Empty'))).values()), [0, 0, 0])

    def test_spatial_oblique_rolled_local_loads_match_solver_resultant(self):
        project = SpatialProject()
        project.add_member((23, -9, 17), (143, 81, -43))
        project.nodes['N1'].support = 'fixed'
        project.members['M1'].roll = 37
        project.loads['L1'] = SpatialLoad('L1', 'M1', 'Fy', -.2, .1, 'distributed', .4, .8)
        project.loads['L2'] = SpatialLoad('L2', 'M1', 'Mz', 7, .4)
        project.loads['L3'] = SpatialLoad('L3', 'N2', 'Angle', 3, angle=30, elevation=-20)
        result = solve(project)
        check = check_equilibrium(project, result)
        self.assertTrue(check.passed)
        # Locked PyNite's independent global equivalent-load vector provides a
        # reference for transformation, integration and all three moment signs.
        vector = (result.solver.P(result.combination) - result.solver.FER(result.combination)).reshape(-1, 6)
        force = vector[:, :3].sum(axis=0)
        moment = sum((row[3:] + np.cross(np.array((node.X, node.Y, node.Z)) - check.origin, row[:3])
                      for node, row in zip(result.solver.nodes.values(), vector)), np.zeros(3))
        np.testing.assert_allclose(list(values(check).values()), [*force, *moment], atol=1e-10)

    def test_example_springs_trusses_releases_and_all_combinations(self):
        for key in EXAMPLES:
            project = example_project(key)
            result = solve(project)
            for combo in project.combinations:
                with self.subTest(example=key, combo=combo):
                    self.assertTrue(check_equilibrium(project, result.for_combination(combo)).passed)

    def test_stale_nonfinite_and_out_of_balance_results(self):
        project = cantilever()
        project.loads['P'] = Load('P', 'N2', 'FY', -10)
        result = solve(project)
        reactions = dict(result.reactions)
        reactions['N1'] = (0, 9, 1200)
        check = check_equilibrium(project, replace(result, reactions=reactions))
        self.assertFalse(check.passed)
        self.assertAlmostEqual(values(check, 'residual')['FY'], -1)
        reactions['N1'] = (0, float('nan'), 1200)
        with self.assertRaisesRegex(ValueError, 'finite'):
            check_equilibrium(project, replace(result, reactions=reactions))
        project.loads['P'].magnitude = -11
        with self.assertRaisesRegex(ValueError, 'snapshot'):
            check_equilibrium(project, result)


class EquilibriumPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.load_project(example_project('elastic'))
        self.window.analysis_revision = self.window.revision
        self.window.analysis_finished(solve(self.window.project), '')

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_all_units_residuals_and_selection_preserve_equilibrium_tab(self):
        panel = self.window.results_panel
        self.window.select(('nodes', 'N1'))
        panel.tabs.setCurrentIndex(4)
        snapshot = self.window.result.snapshot_id
        for key, units in UNIT_SYSTEMS.items():
            self.window.set_units(key)
            self.assertEqual(panel.tabs.currentIndex(), 4)
            self.assertEqual(self.window.result.snapshot_id, snapshot)
            self.assertTrue(panel.equilibrium.passed)
            self.assertEqual(panel.equilibrium_table.item(1, 0).text(), f'FY ({units.force})')
            self.assertAlmostEqual(float(panel.equilibrium_table.item(1, 2).text()), units.to_display(10, 'force'))
        self.window.select(('members', 'M1'))
        self.assertIs(panel.tabs.currentWidget(), panel.tables['members'])

    def test_pending_failure_cancel_and_invalidation_states(self):
        panel = self.window.results_panel
        previous = self.window.result.snapshot_id
        panel.set_analysis_state('Analyzing', 'Solving')
        self.window.set_units('si')
        self.assertEqual(panel.analysis_state, 'Analyzing')
        self.assertIn('Showing previous', panel.snapshot.text())
        with patch.object(QMessageBox, 'warning'):
            self.window.analysis_finished(None, 'Failed solver')
        self.assertEqual(panel.analysis_state, 'Failed')
        self.assertEqual(self.window.result.snapshot_id, previous)
        self.assertIn('Failed solver', panel.snapshot.toolTip())
        self.window.analysis_finished(None, CANCELLED)
        self.assertEqual(panel.analysis_state, 'Cancelled')
        self.window.edit('Move', lambda p: setattr(p.nodes['N2'], 'x', 144))
        self.assertEqual(panel.analysis_state, 'Outdated')
        self.assertIsNone(panel.equilibrium)
        self.assertEqual(panel.equilibrium_table.rowCount(), 0)
        self.window.analysis_finished(None, '')
        self.assertEqual(panel.analysis_state, 'Outdated')

    def test_spatial_equilibrium_has_six_global_components(self):
        self.window.load_project(example_project('3d_cantilever'))
        self.window.analysis_revision = self.window.revision
        self.window.analysis_finished(solve(self.window.project), '')
        panel = self.window.results_panel
        self.assertEqual(panel.equilibrium_table.rowCount(), 6)
        self.assertEqual(panel.equilibrium_table.item(3, 0).text(), 'MX (kip-in)')
        self.assertTrue(panel.equilibrium.passed)
