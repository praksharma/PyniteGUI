"""Deterministic real-generator fixtures for the offline mesh viewport checks."""
import json
from pynitegui.qt.mesh_model import GENERATORS, MeshDefinition, generate_mesh
from pynitegui.qt.mesh_preview import mesh_payload

if __name__ == "__main__":
    payloads = {}
    for generator, (_, parameters) in GENERATORS.items():
        definition = MeshDefinition(generator=generator, parameters=dict(parameters), origin=[12., -7., 21.])
        payloads[generator] = mesh_payload(definition, generate_mesh(definition))
    from PySide6.QtWidgets import QApplication
    from pynitegui.qt.app import MainWindow
    from pynitegui.qt.examples import example_project
    from pynitegui.qt.spatial_surfaces import put_surface
    from pynitegui.qt.spatial_view import viewport_payload
    from pynitegui.qt.mesh_workspace import MeshWorkspace
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    project = example_project("3d_space_frame")
    put_surface(project, MeshDefinition(name="Floor", plane="XZ", origin=[0., 144., 0.],
                                       parameters={"width": 240., "height": 180.}, mesh_size=30.))
    put_surface(project, MeshDefinition(name="Tower", generator="cylinder", origin=[360., 0., 0.],
                                       parameters=dict(GENERATORS["cylinder"][1])))
    window.load_project(project)
    placement_dialog = MeshWorkspace(placement_project=project, auto_place=True)
    payloads["placement_preview"] = placement_dialog.preview.render_payload()
    placement_dialog.saved = placement_dialog.definition.to_dict()
    placement_dialog.reject()
    payloads["mixed"] = {**viewport_payload(window), "labels": False, "plane": "XZ"}
    window.surface_visibility_action.setChecked(False)
    payloads["mixed_hidden"] = {**viewport_payload(window), "labels": False, "plane": "XZ"}
    project.nodes.clear()
    project.members.clear()
    project.loads.clear()
    project.self_weight_case = None
    window.load_project(project)
    window.surface_visibility_action.setChecked(True)
    payloads["surface_only"] = {**viewport_payload(window), "labels": False, "plane": "XZ"}
    import contextlib
    import io
    from pynitegui.qt.analysis import analyze
    window.load_project(example_project("3d_slab_frame"))
    with contextlib.redirect_stdout(io.StringIO()):
        result = analyze(window.project)
    window.analysis_revision = window.revision
    window.analysis_finished(result, "")
    window.deformed_action.setChecked(True)
    payloads["coupled"] = {**viewport_payload(window), "labels": False, "plane": "XZ"}
    window.load_project(example_project("3d_multistorey_slabs"))
    with contextlib.redirect_stdout(io.StringIO()):
        result = analyze(window.project)
    window.analysis_revision = window.revision
    window.analysis_finished(result, "")
    window.deformed_action.setChecked(True)
    payloads["multistorey"] = {**viewport_payload(window), "labels": False, "plane": "XZ"}
    window.saved = window.project.to_dict()
    window.close()
    print(json.dumps(payloads, allow_nan=False))
