"""Audit the two release artifacts and generate their SHA-256 manifest."""
import argparse
from email.parser import BytesParser
import hashlib
from pathlib import Path
import tarfile
import tomllib
import zipfile
from packaging.requirements import Requirement


def check(wheel, source):
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    version = project["version"]
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        prefix = f"pynitegui-{version}.dist-info/"
        metadata = BytesParser().parsebytes(archive.read(prefix + "METADATA"))
        assert metadata["Name"] == "pynitegui" and metadata["Version"] == version
        assert metadata["Requires-Python"] == project["requires-python"]
        assert metadata["License-Expression"] == project["license"]
        assert "mcp" in metadata.get_all("Provides-Extra", [])
        requirements = [Requirement(value) for value in metadata.get_all("Requires-Dist", [])]
        assert any(value.name == "mcp" and value.marker and value.marker.evaluate({"extra": "mcp"})
                   and not value.marker.evaluate({"extra": ""}) for value in requirements)
        assert prefix + "licenses/LICENSE" in names
        assert "pynitegui = pynitegui:main" in archive.read(prefix + "entry_points.txt").decode()
        for path in (root / "src/pynitegui").rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                name = path.relative_to(root / "src").as_posix()
                assert name in names, f"Missing wheel asset: {name}"
                assert archive.read(name) == path.read_bytes(), f"Wheel asset differs: {name}"
        assert not any(name.startswith(("tests/", ".venv/", "scripts/")) for name in names)
    with tarfile.open(source, "r:gz") as archive:
        prefix = f"pynitegui-{version}/"
        names = {item.name for item in archive.getmembers()}
        required = ["pyproject.toml", "README.md", "LICENSE", "uv.lock", "GUIDE.md", "TODO.md",
                    "TODO_SECONDARY.md", "CHANGELOG.md", "RELEASE.md", "scripts/check_dist.py",
                    "scripts/smoke_installed.py", "tests/test_qt_automation_server.py",
                    "assets/structure.png", "assets/SFD.png", "assets/PyniteGUI Structural Frame Logo.png"]
        for name in required:
            assert prefix + name in names, f"Missing source file: {name}"
            content, expected = archive.extractfile(prefix + name).read(), (root / name).read_bytes()
            if name == "pyproject.toml":
                # uv normalizes TOML formatting when preparing the source distribution.
                assert tomllib.loads(content.decode()) == tomllib.loads(expected.decode()), "Stale source metadata"
            else:
                assert content == expected, f"Stale source file: {name}"
        for path in (root / "src/pynitegui").rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                name = path.relative_to(root).as_posix()
                assert prefix + name in names, f"Missing source asset: {name}"
                assert archive.extractfile(prefix + name).read() == path.read_bytes(), f"Stale source asset: {name}"
        assert not any("/.venv/" in name or "/__pycache__/" in name for name in names)
        metadata = BytesParser().parsebytes(archive.extractfile(prefix + "PKG-INFO").read())
        assert metadata["Version"] == version
    manifest = wheel.parent / "SHA256SUMS"
    manifest.write_text("".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
                                for path in (wheel, source)), encoding="ascii")
    print(f"PASS: {version} wheel/source metadata, runtime assets, licenses and source contents")
    print(f"Checksums: {manifest}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    check(args.wheel, args.source)
