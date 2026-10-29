"""One-folder macOS application built from an installed, verified wheel."""
from importlib.metadata import distributions, version
from pathlib import Path
import os
from packaging.version import Version

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
data = collect_data_files('pynitegui') + collect_data_files('Pynite')
for distribution in distributions():
    data += copy_metadata(distribution.metadata['Name'])
data += [(str(root/name), 'notices') for name in ('LICENSE', 'CITATION.md', 'CITATION.cff')]
data += [(os.environ['BRECON_DESKTOP_PROVENANCE'], 'notices')]
data += [(os.environ['BRECON_DESKTOP_SOURCE'], 'notices')]
a = Analysis([str(root/'desktop/entry.py')], pathex=[str(root/'desktop')],
    binaries=[], datas=data,
    hiddenimports=collect_submodules('pynitegui') + collect_submodules('uvicorn') +
                  ['PySide6.QtWebEngineWidgets', 'matplotlib.backends.backend_qtagg'],
    hookspath=[], runtime_hooks=[],
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'tkinter', 'matplotlib.backends.backend_tkagg',
              'vtk', 'vtkmodules', 'pyvista', 'IPython', 'pytest'],
    hooksconfig={'matplotlib': {'backends': ['QtAgg', 'Agg']}}, noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Brecon', debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    argv_emulation=False, target_arch=None, codesign_identity=None, entitlements_file=None)
collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Brecon')
release = '.'.join(str(part) for part in Version(version('brecon')).release)
app = BUNDLE(collection, name='Brecon.app', icon=os.environ.get('BRECON_DESKTOP_ICON'),
    bundle_identifier='io.github.praksharma.brecon',
    info_plist={'CFBundleShortVersionString': release, 'CFBundleVersion': release,
                'CFBundleGetInfoString': 'Brecon '+version('brecon'),
                'LSMinimumSystemVersion': os.environ['BRECON_DESKTOP_MIN_MACOS'],
                'NSHighResolutionCapable': True})
