"""Extract, execute and audit a relocated native desktop preview."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tarfile
import zipfile


REQUIRED_CHECKS = ('examples save/open/analyze/export', 'Frozen background worker',
                   'Bundled Qt WebEngine', 'Bundled Qt print support', 'Frozen plate worker',
                   'Bundled authenticated MCP')


def layout(app):
    if app.suffix == '.app':
        return 'macOS', app/'Contents/MacOS/Brecon', app/'Contents/Resources'
    if (app/'Brecon.exe').is_file():
        return 'Windows', app/'Brecon.exe', app/'_internal'
    return 'Linux', app/'Brecon', app/'_internal'


def audit(app, report):
    app = app.resolve()
    target, executable, resources = layout(app)
    assert executable.is_file()
    for path in app.rglob('*'):
        if path.is_symlink():
            assert path.exists() and path.resolve().is_relative_to(app), f'Invalid bundle symlink: {path}'
    provenance = json.loads((resources/'notices/build-info.json').read_text())
    assert provenance['target']==target, 'Wrong target in bundle provenance'
    if target == 'macOS':
        metadata = plistlib.loads((app/'Contents/Info.plist').read_bytes())
        assert metadata['CFBundleIdentifier']=='io.github.praksharma.brecon'
        assert metadata['CFBundleExecutable']=='Brecon'
        assert metadata['LSMinimumSystemVersion']==provenance['minimum_macos_from_wheel_tags']
    source = resources/'notices'/provenance['source_archive']
    assert hashlib.sha256(source.read_bytes()).hexdigest()==provenance['source_sha256'], 'Missing or mismatched corresponding source archive'
    for name in ('LICENSE', 'CITATION.md', 'CITATION.cff'):
        assert (resources/'notices'/name).is_file(), 'Missing notice: '+name
    assert (resources/'pynitegui/qt/viewport3d/vendor/LICENSE').is_file()
    assert (resources/'pynitegui/qt/viewport3d/viewer.js').is_file()
    assert list(app.rglob('QtWebEngineProcess.exe' if target=='Windows' else 'QtWebEngineProcess')), 'Missing browser helper'
    assert list(resources.glob('brecon-*.dist-info/METADATA')), 'Missing distribution version metadata'
    record = json.loads(report.read_text())
    assert record.get('ok') is True and record.get('frozen') is True, record.get('error', record)
    assert Path(record['executable']).resolve()==executable.resolve(), 'Report came from a different app location'
    assert record['version']==provenance['version']
    assert Path(record['bundled_import']).resolve().is_relative_to(app), 'Report imported external code'
    assert all(any(value in check for check in record['checks']) for value in REQUIRED_CHECKS), record['checks']
    for name in ('app.png', 'viewport.png', 'plate.png', 'results.pdf'):
        assert (report.parent/name).stat().st_size>1000, 'Missing or empty check artifact: '+name
    if target == 'macOS':
        subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
    print(f"PASS: relocated {target} Brecon {record['version']}, resources, notices, symlinks and frozen checks")


def check_archive(archive, output):
    """Run only trusted build artifacts. No external Python executable is available."""
    archive, output = archive.resolve(), output.resolve()
    expected = next(line.split()[0] for line in (archive.parent/'SHA256SUMS').read_text().splitlines()
                    if line.split(maxsplit=1)[-1].strip()==archive.name)
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==expected, 'Archive checksum mismatch'
    output.mkdir(parents=True, exist_ok=False)
    relocated = output/'relocated'
    relocated.mkdir()
    if sys.platform == 'darwin':
        subprocess.run(['ditto', '-x', '-k', str(archive), str(relocated)], check=True)
    elif sys.platform == 'win32':
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(relocated)
    else:
        with tarfile.open(archive, 'r:gz') as bundle:
            bundle.extractall(relocated, filter='data')
    app = relocated/('Brecon.app' if sys.platform=='darwin' else 'Brecon')
    target, executable, _ = layout(app)
    assert target == {'darwin':'macOS','win32':'Windows','linux':'Linux'}[sys.platform], 'Build on the target OS'
    environment = dict(os.environ)
    for key in ('PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV'):
        environment.pop(key, None)
    environment['PATH'] = (str(Path(environment['SystemRoot'])/'System32')+os.pathsep+environment['SystemRoot']
                           if sys.platform=='win32' else '/usr/bin:/bin:/usr/sbin:/sbin')
    subprocess.run([str(executable), '--desktop-check', str(output/'evidence')], env=environment, check=True, timeout=600)
    audit(app, output/'evidence/desktop-check.json')


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', type=Path, nargs='?')
    parser.add_argument('report', type=Path, nargs='?')
    parser.add_argument('--archive', type=Path, help='Trusted native archive to extract and execute')
    parser.add_argument('--output', type=Path, help='New directory for relocated app and evidence')
    args = parser.parse_args()
    if args.archive and args.output and not args.app and not args.report:
        check_archive(args.archive, args.output)
    elif args.app and args.report and not args.archive and not args.output:
        audit(args.app, args.report)
    else:
        parser.error('Provide APP REPORT, or --archive ARCHIVE --output NEW_DIRECTORY')
