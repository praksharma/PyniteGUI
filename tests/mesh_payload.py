"""Deterministic real-generator fixtures for the offline mesh viewport checks."""
import json
from pynitegui.qt.mesh_model import GENERATORS, MeshDefinition, generate_mesh
from pynitegui.qt.mesh_preview import mesh_payload

if __name__ == "__main__":
    payloads = {}
    for generator, (_, parameters) in GENERATORS.items():
        definition = MeshDefinition(generator=generator, parameters=dict(parameters), origin=[12., -7., 21.])
        payloads[generator] = mesh_payload(definition, generate_mesh(definition))
    print(json.dumps(payloads, allow_nan=False))
