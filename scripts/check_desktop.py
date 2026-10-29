"""Audit a relocated macOS development app and its frozen execution report."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import subprocess


REQUIRED_CHECKS = ('examples save/open/analyze/export', 'Frozen background worker',
                   'Bundled Qt WebEngine', 'Bundled Qt print support', 'Frozen plate worker',
                   'Bundled authenticated MCP')


def audit(app, report):
    app = app.resolve()
    metadata = plistlib.loads((app/'Contents/Info.plist').read_bytes())
    assert metadata['CFBundleIdentifier']=='io.github.praksharma.brecon'
    assert metadata['CFBundleExecutable']=='Brecon'
    executable = app/'Contents/MacOS/Brecon'
    assert executable.is_file()
    for path in app.rglob('*'):
        if path.is_symlink():
            assert path.exists() and path.resolve().is_relative_to(app), f'Invalid bundle symlink: {path}'
    resources = app/'Contents/Resources'
    provenance = json.loads((resources/'notices/build-info.json').read_text())
    assert metadata['LSMinimumSystemVersion']==provenance['minimum_macos_from_wheel_tags']
    source = resources/'notices'/provenance['source_archive']
    assert hashlib.sha256(source.read_bytes()).hexdigest()==provenance['source_sha256'], 'Missing or mismatched corresponding source archive'
    for name in ('LICENSE', 'CITATION.md', 'CITATION.cff'):
        assert (resources/'notices'/name).is_file(), 'Missing notice: '+name
    assert (resources/'pynitegui/qt/viewport3d/vendor/LICENSE').is_file()
    assert (resources/'pynitegui/qt/viewport3d/viewer.js').is_file()
    assert list(app.rglob('QtWebEngineProcess')), 'Missing browser helper'
    assert list(resources.glob('brecon-*.dist-info/METADATA')), 'Missing distribution version metadata'
    record = json.loads(report.read_text())
    assert record.get('ok') is True and record.get('frozen') is True, record.get('error', record)
    assert Path(record['executable']).resolve()==executable.resolve(), 'Report came from a different app location'
    assert record['version']==provenance['version']
    assert Path(record['bundled_import']).resolve().is_relative_to(app), 'Report imported external code'
    assert all(any(value in check for check in record['checks']) for value in REQUIRED_CHECKS), record['checks']
    for name in ('app.png', 'viewport.png', 'plate.png', 'results.pdf'):
        assert (report.parent/name).stat().st_size>1000, 'Missing or empty check artifact: '+name
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
    print(f"PASS: relocated Brecon {record['version']} app, resources, notices, symlinks, ad-hoc signature and frozen checks")


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', type=Path)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    audit(args.app, args.report)
