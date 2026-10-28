"""Release version is provided by installed metadata without loading Qt."""
import importlib.metadata
from pathlib import Path
import subprocess
import sys
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
