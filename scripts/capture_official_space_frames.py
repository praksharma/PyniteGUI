"""Capture reference results from hash-checked pinned official space-frame sources.

Download Space Frame - Nodal Loads 1/2.py at SOURCE_COMMIT into --source-dir
as space1.py and space2.py. Only allowlisted FEModel3D construction/analysis
calls and literal numeric expressions are interpreted; no renderer/import/user
code is executed. Tests consume the committed JSON offline and also compare an
independently assembled Euler-Bernoulli stiffness solution.
"""
import argparse
import ast
import contextlib
import hashlib
from importlib.metadata import version
import io
import json
import operator
from pathlib import Path

from Pynite import FEModel3D
from pynitegui.qt.official_examples import SOURCE_COMMIT

HASHES = {1: "a1d0690999c3e49dbd3f7cb5c53edf803cd33d35bca4c27036c47d74b03f0cd3",
          2: "f92ada61f097288872966b5f718b4ae2aa02886b92274e2c4a954e7384661674"}
CALLS = {"add_node", "def_support", "add_section", "add_material", "add_member", "add_node_load", "analyze"}


def capture(source_dir):
    references = {}
    for number, expected_hash in HASHES.items():
        data = (source_dir/f"space{number}.py").read_bytes()
        if hashlib.sha256(data).hexdigest() != expected_hash:
            raise ValueError(f"Source {number} does not match the pinned SHA256.")
        model, values = FEModel3D(), {}
        def literal(node):
            if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool)):
                return node.value
            if isinstance(node, ast.Name) and node.id in values:
                return values[node.id]
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
                return (-1 if isinstance(node.op, ast.USub) else 1)*literal(node.operand)
            if isinstance(node, ast.BinOp) and type(node.op) in (ast.Add, ast.Sub, ast.Mult, ast.Div):
                return {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}[type(node.op)](literal(node.left), literal(node.right))
            raise ValueError("Unexpected reference-source expression.")
        with contextlib.redirect_stdout(io.StringIO()):
            for statement in ast.parse(data).body:
                if isinstance(statement, ast.Assign) and len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name) and not isinstance(statement.value, (ast.Call, ast.Attribute)):
                    values[statement.targets[0].id] = literal(statement.value)
                if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
                    call = statement.value
                    if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name) and call.func.value.id == "frame":
                        if call.func.attr not in CALLS or any(k.arg is None for k in call.keywords):
                            raise ValueError("Unexpected reference-source model call.")
                        getattr(model, call.func.attr)(*[literal(arg) for arg in call.args], **{k.arg: literal(k.value) for k in call.keywords})
        combo = "Combo 1"
        references[str(number)] = {
            "source_sha256": expected_hash,
            "displacements": {name: [getattr(node, axis)[combo] for axis in ("DX", "DY", "DZ", "RX", "RY", "RZ")] for name, node in model.nodes.items()},
            "reactions": {name: [getattr(node, "Rxn"+axis)[combo] for axis in ("FX", "FY", "FZ", "MX", "MY", "MZ")] for name, node in model.nodes.items()},
            "member_end_forces": {name: member.f(combo).flatten().tolist() for name, member in model.members.items()}}
    return {"source_commit": SOURCE_COMMIT, "engine": version("pynitefea"), "units": "in-kip", "examples": references}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1]/"tests/fixtures/official_space_frames.json")
    args = parser.parse_args()
    args.output.write_text(json.dumps(capture(args.source_dir), indent=2, allow_nan=False)+"\n")
    print(f"Captured {args.output}")
