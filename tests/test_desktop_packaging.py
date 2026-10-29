"""Desktop artifact identity, source provenance and frozen-process boundaries."""
from contextlib import redirect_stdout
from email.message import EmailMessage
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import runpy
import sys
import tarfile
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DesktopPackagingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.builder = script('build_desktop')
        self.checker = script('check_desktop')

    def test_minimum_macos_uses_python_and_matching_native_wheel_tags(self):
        dependencies = [SimpleNamespace(read_text=lambda _: 'Tag: cp312-cp312-macosx_14_0_arm64\n'),
                        SimpleNamespace(read_text=lambda _: 'Tag: py3-none-macosx_15_0_x86_64\n')]
        with patch.object(self.builder.metadata, 'distributions', return_value=dependencies), \
             patch.object(self.builder.platform, 'machine', return_value='arm64'), \
             patch.object(self.builder.sysconfig, 'get_config_var', return_value='12.0'):
            self.assertEqual(self.builder.minimum_macos(), '14.0')
        with patch.object(self.builder.metadata, 'distributions', return_value=[]), \
             patch.object(self.builder.sysconfig, 'get_config_var', return_value='15.0'):
            self.assertEqual(self.builder.minimum_macos(), '15.0')

    def test_build_rejects_runtime_versions_outside_the_reviewed_lock(self):
        (self.root/'uv.lock').write_text('[[package]]\nname="PySide6"\nversion="6.11.2"\n')
        dependency = SimpleNamespace(metadata={'Name':'pyside6'}, version='6.12.0')
        with patch.object(self.builder,'ROOT',self.root), patch.object(self.builder.metadata,'distributions',return_value=[dependency]):
            with self.assertRaisesRegex(ValueError,'differs from uv.lock'):
                self.builder.verify_locked_runtime()
            dependency.version = '6.11.2'
            self.builder.verify_locked_runtime()
            dependency.metadata = {'Name':'unreviewed-runtime'}
            with self.assertRaisesRegex(ValueError, 'Unreviewed distribution'):
                self.builder.verify_locked_runtime()

    def wheel(self, name='brecon', version='1.0.0rc5.dev0'):
        site = self.root/'environment/site-packages'
        site.mkdir(parents=True, exist_ok=True)
        self.module = SimpleNamespace(__file__=str(site/'pynitegui/__init__.py'), __version__=version)
        self.runtime = {'pynitegui/__init__.py':b'VERSION = "test"\n', 'pynitegui/qt/viewport3d/viewer.js':b'// offline\n',
                        'brecon/__init__.py':b'# entry\n'}
        message = EmailMessage()
        message['Name'], message['Version'] = name, version
        wheel = self.root/'brecon.whl'
        with zipfile.ZipFile(wheel, 'w') as archive:
            for key, value in self.runtime.items():
                archive.writestr(key, value)
                path = site/key
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(value)
            archive.writestr('brecon.dist-info/METADATA', message.as_bytes())
        return wheel

    def test_wheel_gate_accepts_installed_bytes_and_rejects_stale_code_or_editable_imports(self):
        wheel = self.wheel()
        with patch.dict(sys.modules, pynitegui=self.module), patch.object(sys, 'prefix', str(self.root/'environment')):
            self.assertEqual(self.builder.verify_wheel(wheel), '1.0.0rc5.dev0')
            Path(self.module.__file__).write_bytes(b'# stale install\n')
            with self.assertRaisesRegex(ValueError, 'differs from wheel'):
                self.builder.verify_wheel(wheel)
            self.module.__file__ = str(self.root/'source/pynitegui/__init__.py')
            with self.assertRaisesRegex(ValueError, 'editable/source'):
                self.builder.verify_wheel(wheel)

    def test_wheel_gate_rejects_wrong_distribution_and_version(self):
        for name, installed_version in (('pynitegui', '1.0.0rc5.dev0'), ('brecon', '1.0.0rc4')):
            wheel = self.wheel(name)
            self.module.__version__ = installed_version
            with patch.dict(sys.modules, pynitegui=self.module), patch.object(sys, 'prefix', str(self.root/'environment')):
                with self.assertRaisesRegex(ValueError, 'name/version'):
                    self.builder.verify_wheel(wheel)

    def test_corresponding_source_gate_checks_runtime_and_build_recipe(self):
        wheel = self.wheel()
        source_root = self.root/'source'
        source_root.mkdir()
        recipe = source_root/'desktop'
        recipe.mkdir()
        (recipe/'entry.py').write_text('freeze_support()\n')
        (source_root/'scripts').mkdir()
        for name in ('build_desktop.py', 'check_desktop.py'):
            (source_root/'scripts'/name).write_text('# builder\n')
        source = self.root/'source.tar.gz'
        def archive(runtime):
            with tarfile.open(source, 'w:gz') as output:
                for key, value in runtime.items():
                    item = tarfile.TarInfo('brecon/src/'+key)
                    item.size = len(value)
                    output.addfile(item, io.BytesIO(value))
                for path in (*recipe.glob('*'), *(source_root/'scripts').glob('*')):
                    output.add(path, arcname='brecon/'+path.relative_to(source_root).as_posix())
        archive(self.runtime)
        with patch.object(self.builder, 'ROOT', source_root):
            self.builder.verify_source(source, wheel)
            (recipe/'entry.py').write_text('# changed recipe\n')
            with self.assertRaisesRegex(ValueError, 'stale desktop recipe'):
                self.builder.verify_source(source, wheel)
            archive({**self.runtime, 'pynitegui/__init__.py':b'# wrong source\n'})
            with self.assertRaisesRegex(ValueError, 'differs from wheel'):
                self.builder.verify_source(source, wheel)

    def test_worker_dispatch_occurs_before_app_or_check_imports(self):
        entry = ROOT/'desktop/entry.py'
        for arguments in (['Brecon','--multiprocessing-fork'], ['Brecon','--desktop-check','output']):
            with patch.dict(sys.modules, multiprocessing=SimpleNamespace(freeze_support=lambda: sys.exit(37))), patch.object(sys,'argv',arguments):
                with self.assertRaises(SystemExit) as stopped:
                    runpy.run_path(str(entry), run_name='__main__')
                self.assertEqual(stopped.exception.code,37)

    def fixture(self, target='macOS'):
        app = self.root/'Relocated'/('Brecon.app' if target=='macOS' else 'Brecon')
        contents = app/'Contents'
        resources = contents/'Resources' if target=='macOS' else app/'_internal'
        resources.mkdir(parents=True)
        if target=='macOS':
            (contents/'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'io.github.praksharma.brecon','CFBundleExecutable':'Brecon','LSMinimumSystemVersion':'14.0'}))
        executable = contents/'MacOS/Brecon' if target=='macOS' else app/('Brecon.exe' if target=='Windows' else 'Brecon')
        executable.parent.mkdir(exist_ok=True)
        executable.write_bytes(b'executable')
        required = ['notices/LICENSE','notices/CITATION.md','notices/CITATION.cff',
                    'pynitegui/qt/viewport3d/vendor/LICENSE','pynitegui/qt/viewport3d/viewer.js',
                    'brecon-1.0.0rc5.dev0.dist-info/METADATA', 'QtWebEngineProcess.exe' if target=='Windows' else 'QtWebEngineProcess']
        for name in required:
            path = resources/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('bundled')
        source = resources/'notices/source.tar.gz'
        source.write_bytes(b'source archive')
        (resources/'notices/build-info.json').write_text(json.dumps({'version':'1.0.0rc5.dev0','target':target,
            'minimum_macos_from_wheel_tags':'14.0',
            'source_archive':source.name,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}))
        report = self.root/'report/desktop-check.json'
        report.parent.mkdir()
        record = dict(ok=True, frozen=True, executable=str(executable), version='1.0.0rc5.dev0',
                      bundled_import=str(resources/'pynitegui/__init__.py'), checks=list(self.checker.REQUIRED_CHECKS))
        report.write_text(json.dumps(record))
        for name in self.checker.EVIDENCE_FILES:
            (report.parent/name).write_bytes(b'X'*1001)
        return app, report, record

    def test_bundle_audit_requires_relocated_execution_and_rejects_escaping_symlinks(self):
        app, report, record = self.fixture()
        with patch.object(self.checker.subprocess,'run') as sign, redirect_stdout(io.StringIO()):
            self.checker.audit(app,report)
            sign.assert_called_once()
            record['executable'] = '/a/different/Brecon.app/Contents/MacOS/Brecon'
            report.write_text(json.dumps(record))
            with self.assertRaisesRegex(AssertionError,'different app location'):
                self.checker.audit(app,report)

    @unittest.skipIf(sys.platform=='win32', 'Windows portable bundles contain no symlinks')
    def test_bundle_audit_rejects_escaping_symlinks(self):
        app, report, _ = self.fixture()
        outside = self.root/'outside.txt'
        outside.write_text('outside bundle')
        (app/'Contents/Resources/escape').symlink_to(outside)
        with self.assertRaisesRegex(AssertionError,'Invalid bundle symlink'):
            self.checker.audit(app,report)

    def test_portable_layouts_require_native_helpers_and_matching_target_without_codesign(self):
        for target in ('Windows','Linux'):
            with self.subTest(target=target), TemporaryDirectory() as directory:
                self.root = Path(directory)
                app, report, record = self.fixture(target)
                with patch.object(self.checker.subprocess, 'run') as command, redirect_stdout(io.StringIO()):
                    self.checker.audit(app, report)
                    command.assert_not_called()
                    resources = app/'_internal'
                    (resources/('QtWebEngineProcess.exe' if target=='Windows' else 'QtWebEngineProcess')).unlink()
                    with self.assertRaisesRegex(AssertionError,'Missing browser helper'):
                        self.checker.audit(app,report)

    def test_host_names_and_windows_archive_round_trip(self):
        for machine, expected in [('AMD64','x86_64'),('aarch64','arm64'),('arm64','arm64')]:
            with patch.object(self.builder.platform,'machine',return_value=machine):
                self.assertEqual(self.builder.architecture(),expected)
        app = self.root/'Brecon'
        (app/'_internal').mkdir(parents=True)
        (app/'Brecon.exe').write_bytes(b'program')
        (app/'_internal/library.dll').write_bytes(b'library')
        with patch.object(self.builder.sys,'platform','win32'), patch.object(self.builder.platform,'machine',return_value='AMD64'):
            archive = self.builder.archive_app(app,self.root,'1.2.3')
        self.assertEqual(archive.name,'Brecon-1.2.3-Windows-x86_64.zip')
        with zipfile.ZipFile(archive) as bundle:
            self.assertEqual(bundle.read('Brecon/Brecon.exe'),b'program')
            self.assertEqual(bundle.read('Brecon/_internal/library.dll'),b'library')

    @unittest.skipIf(sys.platform=='win32', 'POSIX executable bits and links')
    def test_linux_archive_preserves_executable_and_symlink_after_relocation(self):
        app = self.root/'Brecon'
        app.mkdir()
        executable = app/'Brecon'
        executable.write_bytes(b'program')
        executable.chmod(0o755)
        (app/'linked').symlink_to('Brecon')
        with patch.object(self.builder.sys,'platform','linux'):
            archive = self.builder.archive_app(app,self.root,'1.2.3')
        with tarfile.open(archive) as bundle:
            bundle.extractall(self.root/'relocated',filter='data')
        relocated = self.root/'relocated/Brecon'
        self.assertTrue((relocated/'Brecon').stat().st_mode & 0o111)
        self.assertTrue((relocated/'linked').is_symlink())
        self.assertEqual((relocated/'linked').resolve(),(relocated/'Brecon').resolve())

    def test_archive_check_rejects_bad_checksum_before_extraction_or_execution(self):
        archive = self.root/'Brecon.zip'
        archive.write_bytes(b'tampered archive')
        (self.root/'SHA256SUMS').write_text('wrong  Brecon.zip\n')
        with patch.object(self.checker.subprocess,'run') as command:
            with self.assertRaisesRegex(AssertionError,'checksum mismatch'):
                self.checker.check_archive(archive,self.root/'output')
            command.assert_not_called()
        self.assertFalse((self.root/'output').exists())

    def test_clean_launch_environment_accepts_windows_uppercase_systemroot(self):
        supplied = dict(SYSTEMROOT='C:/Windows', PATH='/build/python', PYTHONPATH='/source',
                        PYTHONHOME='/runtime', VIRTUAL_ENV='/build', QT_QPA_PLATFORM='windows')
        with patch.dict(self.checker.os.environ,supplied,clear=True), patch.object(self.checker.sys,'platform','win32'):
            environment = self.checker.clean_environment()
        self.assertEqual(environment['PATH'],str(Path('C:/Windows')/'System32')+os.pathsep+'C:/Windows')
        self.assertEqual(environment['QT_QPA_PLATFORM'],'windows')
        for key in ('PYTHONHOME','PYTHONPATH','VIRTUAL_ENV'):
            self.assertNotIn(key,environment)

    def test_bundle_audit_rejects_failed_checks_missing_evidence_and_wrong_source(self):
        app, report, record = self.fixture()
        with patch.object(self.checker.subprocess,'run'), redirect_stdout(io.StringIO()):
            record['ok'] = False
            report.write_text(json.dumps(record))
            with self.assertRaises(AssertionError):
                self.checker.audit(app,report)
            record['ok'] = True
            report.write_text(json.dumps(record))
            (report.parent/'viewport.png').write_bytes(b'')
            with self.assertRaisesRegex(AssertionError,'empty check artifact'):
                self.checker.audit(app,report)
            (app/'Contents/Resources/notices/source.tar.gz').write_bytes(b'wrong source')
            with self.assertRaisesRegex(AssertionError,'corresponding source'):
                self.checker.audit(app,report)
