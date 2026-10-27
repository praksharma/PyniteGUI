"""Capture native documentation screenshots using disposable example projects.

Run with the desktop development environment, not the docs-only environment.
The separate mesh viewport check supplies the three-storey 3D screenshot.
"""
import argparse
from contextlib import redirect_stdout
from io import StringIO
import os
from pathlib import Path
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow
from pynitegui.qt.examples import example_project
from pynitegui.qt.help_menu import AboutDialog, ShortcutsDialog
from pynitegui.qt.theme import configure_theme


def capture(output):
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    configure_theme(app, "light")

    def save(widget, name):
        app.processEvents()
        if not widget.grab().save(str(output / name)):
            raise RuntimeError(f"Could not save {name}")
        print(f"Captured {name}")

    with tempfile.TemporaryDirectory(prefix="pynitegui-docs-") as directory:
        root = Path(directory)
        settings = QSettings(str(root / "settings.ini"), QSettings.Format.IniFormat)
        window = MainWindow(root / "recovery", settings)
        window.resize(1280, 820)
        window.load_project(example_project("portal"))
        window.show()
        app.processEvents()
        window.view.fit()
        try:
            from pynitegui.qt.sections import SectionLibraryDialog
            section = SectionLibraryDialog(window, window.project)
            section.search.setText("W18X35")
            section.show()
            save(section, "section-dimensions.png")
            section.reject()
            section.deleteLater()

            from pynitegui.qt.example_browser import ExampleBrowser
            browser = ExampleBrowser(window)
            browser.search.setText("Gerber")
            browser.show()
            save(browser, "example-browser.png")
            browser.search.setText("official clamped")
            save(browser, "official-plate-browser.png")
            browser.reject()

            from pynitegui.qt.official_plate import example_definition, PLATE_EXAMPLES
            from pynitegui.qt.plate_workspace import PlateWorkspace
            plate = PlateWorkspace(window, "imperial", example_definition())
            plate.setWindowTitle(PLATE_EXAMPLES["official_plate_quad"] + " (Experimental)")
            plate.show()
            app.processEvents()
            plate.canvas.draw()
            save(plate, "official-quad-plate.png")
            plate.reject()
            plate.deleteLater()

            from pynitegui.qt.diagrams import DiagramDialog
            from pynitegui.qt.plot_export import export_plot
            with redirect_stdout(StringIO()):
                result = analyze(window.project)
            diagrams = DiagramDialog(window, window.project, result)
            diagrams.quantity.setCurrentIndex(1)
            diagrams.show_end_values.setChecked(False)
            diagrams.show()
            app.processEvents()
            diagrams.structure_canvas.draw()
            save(diagrams, "diagram-controls.png")
            export_plot(output / "snapshot-diagram.png", diagrams.structure_figure,
                        diagrams.structure_canvas.toolbar.metadata())
            diagrams.close()

            comparison_project = example_project("official_beam_point")
            with redirect_stdout(StringIO()):
                comparison_result = analyze(comparison_project)
            comparison = DiagramDialog(window, comparison_project, comparison_result)
            comparison.tabs.setCurrentWidget(comparison.comparison)
            comparison.comparison.quantity.setCurrentIndex(2)
            comparison.comparison.distance.setValue(84)
            comparison.show()
            app.processEvents()
            comparison.comparison.canvas.draw()
            save(comparison, "combination-comparison.png")
            comparison.close()

            drift_project = example_project("multistorey")
            with redirect_stdout(StringIO()):
                drift_result = analyze(drift_project)
            drift = DiagramDialog(window, drift_project, drift_result)
            drift.resize(1260, 680)
            drift.tabs.setCurrentWidget(drift.drift)
            for lower, upper in (("N1", "N2"), ("N2", "N5"), ("N4", "N3"), ("N3", "N6")):
                drift.drift.lower.setCurrentText(lower)
                drift.drift.upper.setCurrentText(upper)
                drift.drift.add.click()
            drift.show()
            save(drift, "storey-drift.png")
            drift.close()

            from pynitegui.qt.deformation_animation import StaticDeformationDialog
            animation = StaticDeformationDialog(window, drift_project, drift_result)
            animation.fraction.setValue(1.)
            animation.show()
            animation.canvas.draw()
            save(animation, "static-deformation-animation.png")
            animation.close()

            window.help_menu.popup(window.mapToGlobal(window.rect().center()))
            save(window.help_menu, "help-menu.png")
            window.help_menu.close()

            about = AboutDialog(window)
            about.show()
            save(about, "about.png")
            about.close()

            configure_theme(app, "dark")
            shortcuts = ShortcutsDialog(window)
            shortcuts.resize(560, 300)
            shortcuts.search.setText("fit")
            shortcuts.show()
            save(shortcuts, "shortcuts.png")
            shortcuts.close()
            configure_theme(app, "light")

            projects = root / "Demo Projects"
            projects.mkdir()
            example_project("portal").save(projects / "Portal.pynite.json")
            settings.setValue("recent_projects", [str(projects / name) for name in
                              ("Portal.pynite.json", "Slabs.pynite.json")])
            window.update_recent_menu()
            window.recent_menu.popup(window.mapToGlobal(window.rect().center()))
            save(window.recent_menu, "recent-projects.png")
            window.recent_menu.close()

            # This is a real topology finding: an unconnected joint inside M1.
            project = example_project("portal")
            project.node_at(0., 72.)
            window.load_project(project)
            window.check_model()
            window.resizeDocks([window.findings_dock], [210], Qt.Orientation.Vertical)
            app.processEvents()
            window.model_findings.list.setCurrentRow(0)
            window.model_findings.focus()
            save(window, "model-findings.png")

            window.load_project(example_project("p_delta_column"))
            window.findings_dock.hide()
            with redirect_stdout(StringIO()):
                result = analyze(window.project)
            window.analysis_revision = window.revision
            window.analysis_finished(result, "")
            window.deformed_action.setChecked(True)
            window.select(("nodes", "N9"))
            window.resizeDocks([window.results_dock], [260], Qt.Orientation.Vertical)
            app.processEvents()
            window.view.fit()
            window.view.scale(.85, .85)
            save(window, "p-delta-column.png")

            window.load_project(example_project("cantilever"))
            with redirect_stdout(StringIO()):
                result = analyze(window.project)
            window.analysis_revision = window.revision
            window.analysis_finished(result, "")
            window.deformed_action.setChecked(True)
            window.deformation_shape.setCurrentIndex(1)
            app.processEvents()
            window.view.fit()
            save(window, "straight-deformation-preview.png")

            window.workspaces.choose("results")
            window.workspaces.commands.trigger()
            app.processEvents()
            window.view.fit()
            save(window, "results-workspace.png")

            canvas_project = example_project("simple_beam")
            canvas_project.set_combination("Double", {"Case 1": 2.})
            window.load_project(canvas_project)
            with redirect_stdout(StringIO()):
                result = analyze(window.project)
            window.analysis_revision = window.revision
            window.analysis_finished(result, "")
            window.canvas_results.mode.setCurrentIndex(window.canvas_results.mode.findData("shear"))
            window.canvas_results.style.setCurrentIndex(1)
            window.canvas_results.member.setCurrentIndex(window.canvas_results.member.findData("M1"))
            window.canvas_results.distance.setValue(210.)
            window.resizeDocks([window.results_dock], [340], Qt.Orientation.Vertical)
            app.processEvents()
            window.view.fit()
            save(window, "canvas-colour-results.png")
        finally:
            # Do not show a save prompt or retain example recovery data.
            window.saved = window.project.to_dict()
            window.close()
            window.deleteLater()
            app.processEvents()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parents[1] / "docs/assets/screenshots")
    capture(parser.parse_args().output)
