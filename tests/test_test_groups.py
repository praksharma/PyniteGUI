"""The focused runner must select faithfully, preserve coverage and report failures."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pynitegui_test_runner", ROOT/"scripts/test.py")
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)


class TestGroupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        (self.root/"tests").mkdir()
        self.module = "test_fixture_"+uuid.uuid4().hex
        (self.root/"tests"/f"{self.module}.py").write_text('''import unittest
class UI(unittest.TestCase):
    def test_good(self):
        print("UI ran")
class Engineering(unittest.TestCase):
    def test_failure(self):
        raise AssertionError("engineering failed")
''')
        (self.root/"tests/viewport.spec.cjs").write_text("// fixture, never executed")
        self.manifest = f'''[groups.ui]
description = "UI"
tests = ["{self.module}.UI"]
[groups.engineering]
description = "Engineering"
tests = ["{self.module}.Engineering"]
[profiles.smoke]
description = "Smoke"
tests = ["{self.module}.UI.test_good"]
[external.viewport]
description = "Viewport"
scripts = ["tests/viewport.spec.cjs"]
'''
        self.write_manifest(self.manifest)

    def tearDown(self):
        sys.modules.pop(self.module, None)
        self.directory.cleanup()

    def write_manifest(self, text):
        (self.root/"tests/groups.toml").write_text(text)

    def run_main(self, *arguments):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = runner.main(list(arguments), root=self.root)
        return code, output.getvalue(), errors.getvalue()

    def test_repository_coverage_and_ui_excludes_structural_and_mcp_suites(self):
        config, found = runner.configuration(ROOT)
        selectors, scripts = runner.plan(config, found, ["ui"])
        self.assertTrue(selectors)
        self.assertEqual(scripts, [])
        self.assertFalse(any(any(word in item for word in ("coupled", "automation", "benchmarks", "plate_model")) for item in selectors))
        smoke, _ = runner.plan(config, found, ["smoke"])
        self.assertEqual(len(smoke), 3)
        self.assertTrue(any("test_canvas_drawing_and_undo" in item for item in smoke))

    def test_unassigned_duplicate_or_invalid_selectors_fail_coverage(self):
        invalid = [self.manifest.replace(f'tests = ["{self.module}.Engineering"]', 'tests = ["missing_test"]'),
                   self.manifest.replace(f'tests = ["{self.module}.Engineering"]', f'tests = ["{self.module}.UI"]'),
                   self.manifest.replace(f'tests = ["{self.module}.Engineering"]', f'tests = ["{self.module}"]')]
        for text in invalid:
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.write_manifest(text)
                runner.configuration(self.root)
        self.write_manifest(self.manifest)
        (self.root/"tests/test_unassigned.py").write_text("class NewTests:\n    async def test_new(self): pass\n")
        with self.assertRaisesRegex(ValueError, "NewTests"):
            runner.configuration(self.root)

    def test_all_covers_each_class_and_overlapping_profiles_are_deduplicated(self):
        config, found = runner.configuration(self.root)
        selected, external = runner.plan(config, found, ["ui", "ui", "smoke", f"{self.module}.UI.test_good"])
        self.assertEqual(selected, [f"{self.module}.UI"])
        self.assertEqual(external, [])
        selected, _ = runner.plan(config, found, ["all"])
        self.assertTrue(all(any(runner.matches(selector, cls) for selector in selected) for cls in found.classes))
        with self.assertRaisesRegex(ValueError, "Unknown"):
            runner.plan(config, found, ["typo"])

    def test_full_collection_detects_dynamic_tests_missing_from_class_selectors(self):
        path = self.root/"tests"/f"{self.module}.py"
        with path.open("a") as stream:
            stream.write("\ndef load_tests(loader, tests, pattern):\n    tests.addTest(unittest.FunctionTestCase(lambda: None))\n    return tests\n")
        code, output, errors = self.run_main("all", "--collect-only")
        self.assertEqual(code, 1)
        self.assertIn("Full group coverage differs", errors)
        self.assertNotIn("UI ran", output)

    def test_focused_execution_does_not_run_engineering_and_restores_process_paths(self):
        original_cwd, original_path = Path.cwd(), list(sys.path)
        code, output, errors = self.run_main("ui", "smoke")
        self.assertEqual(code, 0, errors)
        self.assertIn("UI ran", output)
        self.assertIn("Ran 1 test", errors)
        self.assertNotIn("engineering failed", errors)
        self.assertEqual(Path.cwd(), original_cwd)
        self.assertEqual(sys.path, original_path)

    def test_test_failures_return_nonzero_and_default_is_smoke(self):
        code, _, errors = self.run_main("engineering")
        self.assertEqual(code, 1)
        self.assertIn("engineering failed", errors)
        code, output, errors = self.run_main()
        self.assertEqual(code, 0, errors)
        self.assertIn("Selected: smoke", output)

    def test_listing_dry_run_and_check_never_import_selected_modules(self):
        path = self.root/"tests"/f"{self.module}.py"
        path.write_text('raise RuntimeError("Must not import")\n'+path.read_text())
        for arguments in (("--list",), ("--check",), ("ui", "--dry-run")):
            with self.subTest(arguments=arguments):
                code, _, errors = self.run_main(*arguments)
                self.assertEqual(code, 0, errors)
                self.assertNotIn(self.module, sys.modules)
        code, _, errors = self.run_main("ui", "--collect-only")
        self.assertEqual(code, 1)
        self.assertIn("Must not import", errors)

    def test_viewport_exit_status_deduplication_and_missing_node(self):
        with patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)) as run:
            code, _, _ = self.run_main("viewport", "viewport")
            self.assertEqual(code, 1)
            self.assertEqual(run.call_count, 1)
        with patch.object(runner.subprocess, "run", side_effect=FileNotFoundError("node")):
            code, _, errors = self.run_main("viewport")
            self.assertEqual(code, 1)
            self.assertIn("Install Node", errors)

    def test_coverage_checks_require_no_application_or_optional_dependencies(self):
        source = '''import importlib.abc, runpy, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'PySide6','numpy','scipy','matplotlib','Pynite','mcp','uvicorn','zensical'}:
            raise AssertionError('Unexpected dependency import: '+fullname)
sys.meta_path.insert(0, Block())
sys.argv = ['scripts/test.py','--check']
runpy.run_path('scripts/test.py', run_name='__main__')
'''
        result = subprocess.run([sys.executable, "-B", "-c", source], cwd=ROOT, text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("test classes assigned", result.stdout)
