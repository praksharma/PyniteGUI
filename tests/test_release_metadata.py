"""Release version is provided by installed metadata without loading Qt."""
import importlib.metadata
from pathlib import Path
import subprocess
import sys
import tomllib
import unittest

import pynitegui


class ReleaseMetadataTests(unittest.TestCase):
    def test_installed_version_matches_project_metadata(self):
        root = Path(__file__).resolve().parents[1]
        project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
        self.assertEqual(pynitegui.__version__, project["version"])
        self.assertEqual(pynitegui.__version__, importlib.metadata.version("pynitegui"))

    def test_version_entrypoint_does_not_import_qt(self):
        source = "import sys, pynitegui; sys.argv=['pynitegui','--version']; pynitegui.main(); assert 'PySide6' not in sys.modules"
        output = subprocess.check_output([sys.executable, "-B", "-c", source], text=True)
        self.assertEqual(output.strip(), f"PyniteGUI {pynitegui.__version__}")
