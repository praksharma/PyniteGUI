"""Release version is provided by installed metadata without loading Qt."""
import importlib.metadata
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
import tomllib
import unittest

import pynitegui
import brecon


class ReleaseMetadataTests(unittest.TestCase):
    def test_installed_version_matches_project_metadata(self):
        root = Path(__file__).resolve().parents[1]
        project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
        self.assertEqual(pynitegui.__version__, project["version"])
        self.assertEqual(pynitegui.__version__, importlib.metadata.version("brecon"))
        self.assertEqual(brecon.__version__, pynitegui.__version__)
        self.assertIs(brecon.main, pynitegui.main)

    def test_version_entrypoint_does_not_import_qt(self):
        source = "import sys, brecon; sys.argv=['brecon','--version']; brecon.main(); assert 'PySide6' not in sys.modules"
        output = subprocess.check_output([sys.executable, "-B", "-c", source], text=True)
        self.assertEqual(output.strip(), f"Brecon {pynitegui.__version__}")

    def publishing_metadata(self, name, version, tag):
        root = Path(__file__).resolve().parents[1]
        workflow = (root/".github/workflows/publish.yml").read_text()
        # Execute the actual workflow's metadata gate without GitHub or upload access.
        code = textwrap.dedent(re.search(r"python3 - <<'PY'\n(.*?)\n\s+PY", workflow, re.S).group(1))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path/"pyproject.toml").write_text(f'[project]\nname="{name}"\nversion="{version}"\n')
            environment = dict(os.environ, RELEASE_TAG=tag, GITHUB_ENV=str(path/"env"), GITHUB_OUTPUT=str(path/"output"))
            result = subprocess.run([sys.executable, "-c", code], cwd=path, env=environment, text=True, capture_output=True)
            return result, {name: (path/name).read_text() if (path/name).exists() else None for name in ("env", "output")}

    def test_publisher_selects_brecon_artifacts(self):
        result, files = self.publishing_metadata("brecon", "1.0.0rc4", "v1.0.0rc4")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(files["env"], "WHEEL=brecon-1.0.0rc4-py3-none-any.whl\nSDIST=brecon-1.0.0rc4.tar.gz\n")
        self.assertEqual(files["output"], "distribution=brecon\n")

    def test_publisher_rejects_old_distribution_and_mismatched_tag(self):
        for name, version, tag in (("pynitegui", "1.0.0rc2", "v1.0.0rc2"),
                                   ("pynitegui", "1.0.0rc3", "v1.0.0rc3"),
                                   ("brecon", "1.0.0rc4", "v1.0.0rc3")):
            with self.subTest(name=name, tag=tag):
                result, files = self.publishing_metadata(name, version, tag)
                self.assertNotEqual(result.returncode, 0)
                self.assertIsNone(files["env"])
                self.assertIsNone(files["output"])
