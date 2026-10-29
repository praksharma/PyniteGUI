"""Build an unsigned macOS app from a reviewed installed wheel, without publishing."""
import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def minimum_macos():
    """Conservative lower bound from Python and the installed native wheel tags."""
    deployment = str(sysconfig.get_config_var('MACOSX_DEPLOYMENT_TARGET') or '10.13')
    versions = [tuple(int(part) for part in deployment.split('.')[:2])]
    for distribution in metadata.distributions():
        tags = re.findall(r'macosx_(\d+)_(\d+)_(arm64|x86_64|universal2)', distribution.read_text('WHEEL') or '')
        matching = [(int(major), int(minor)) for major, minor, arch in tags if arch in (platform.machine(), 'universal2')]
        if matching:
            versions.append(min(matching))
    return '.'.join(str(part) for part in max(versions))


def verify_locked_runtime():
    """Standalone previews use the project's reviewed lock, not floating wheels."""
    from packaging.utils import canonicalize_name
    locked = {}
    for package in tomllib.loads((ROOT/'uv.lock').read_text())['package']:
        locked.setdefault(canonicalize_name(package['name']), set()).add(package['version'])
    for distribution in metadata.distributions():
        name = canonicalize_name(distribution.metadata['Name'])
        if name not in locked and name not in {'pyinstaller', 'pyinstaller-hooks-contrib', 'altgraph', 'macholib', 'setuptools', 'pip', 'wheel'}:
            raise ValueError('Unreviewed distribution in desktop environment: '+name+'. Start with a fresh build environment.')
        if name in locked and distribution.version not in locked[name]:
            raise ValueError('Standalone runtime differs from uv.lock: '+name+'. Install a fresh environment from uv export --locked.')


def verify_wheel(wheel):
    """Fail before building if editable/stale runtime bytes could be packaged."""
    import pynitegui
    installed = Path(pynitegui.__file__).resolve()
    if not installed.is_relative_to(Path(sys.prefix).resolve()):
        raise ValueError('Install the reviewed wheel into an isolated build environment; editable/source installs are not supported.')
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.startswith(('brecon/', 'pynitegui/')) and not name.endswith('/'):
                path = installed.parent.parent/name
                if not path.is_file() or path.read_bytes() != archive.read(name):
                    raise ValueError('Installed runtime differs from wheel: '+name)
        info = next(name for name in archive.namelist() if name.endswith('.dist-info/METADATA'))
        from email.parser import BytesParser
        declared = BytesParser().parsebytes(archive.read(info))
        if declared['Name'] != 'brecon' or declared['Version'] != pynitegui.__version__:
            raise ValueError('Wheel name/version does not match the installed Brecon distribution.')
    return pynitegui.__version__


def icon(work):
    """Render the existing vector mark; keep the wordmark in its original asset."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    application = QGuiApplication.instance() or QGuiApplication(['brecon-build'])
    renderer = QSvgRenderer(str(ROOT/'assets/brecon.svg'))
    target = work/'Brecon.iconset'
    target.mkdir()
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            pixels = size*scale
            image = QImage(pixels, pixels, QImage.Format.Format_ARGB32)
            image.fill(0)
            painter = QPainter(image)
            # Crop the existing mountain/frame mark, without redrawing it.
            painter.setClipRect(0, 0, pixels, pixels)
            renderer.render(painter, QRectF(0, 0, pixels*660/210, pixels*180/210))
            painter.end()
            suffix = '@2x' if scale == 2 else ''
            assert image.save(str(target/f'icon_{size}x{size}{suffix}.png'))
    destination = work/'Brecon.icns'
    subprocess.run(['iconutil', '-c', 'icns', str(target), '-o', str(destination)], check=True)
    return destination


def verify_source(source, wheel):
    """Bundle the corresponding source and the exact recipe used to freeze it."""
    with tarfile.open(source, 'r:gz') as archive, zipfile.ZipFile(wheel) as binary:
        prefix = archive.getnames()[0].split('/')[0]+'/'
        for name in binary.namelist():
            if name.startswith(('brecon/', 'pynitegui/')) and not name.endswith('/'):
                if archive.extractfile(prefix+'src/'+name).read()!=binary.read(name):
                    raise ValueError('Source archive differs from wheel: '+name)
        for path in [*(ROOT/'desktop').glob('*'), ROOT/'scripts/build_desktop.py', ROOT/'scripts/check_desktop.py']:
            if path.is_file() and archive.extractfile(prefix+path.relative_to(ROOT).as_posix()).read()!=path.read_bytes():
                raise ValueError('Source archive has a stale desktop recipe: '+path.name)


def build(wheel, source, output):
    if sys.platform != 'darwin':
        raise ValueError('This first desktop target is macOS only; build on a Mac. Windows/Linux packaging remains pending.')
    if sys.version_info[:2] != (3, 12):
        raise ValueError('The validated standalone profile uses Python 3.12; create the build environment with --python 3.12.')
    version = verify_wheel(wheel)
    verify_source(source, wheel)
    verify_locked_runtime()
    from packaging.requirements import Requirement
    for line in (ROOT/'desktop/requirements.txt').read_text().splitlines():
        if line.strip() and not line.startswith('#'):
            required = Requirement(line)
            if metadata.version(required.name) not in required.specifier:
                raise ValueError('Install the pinned desktop/requirements.txt build tools: '+required.name)
    metadata.distribution('mcp')  # The supported standalone profile includes MCP.
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='brecon-desktop-build-') as directory:
        work = Path(directory)
        record = {'application': 'Brecon', 'version': version, 'target': 'macOS',
            'architecture': platform.machine(), 'verified_os': platform.mac_ver()[0],
            'minimum_macos_from_wheel_tags': minimum_macos(),
            'python': platform.python_version(), 'wheel': wheel.name,
            'wheel_sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(),
            'source_archive': source.name,
            'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'source': 'https://github.com/praksharma/PyniteGUI',
            'signing': 'ad-hoc only; no Developer ID or notarization',
            'build_environment': dict(sorted((d.metadata['Name'], d.version) for d in metadata.distributions()))}
        provenance = work/'build-info.json'
        provenance.write_text(json.dumps(record, indent=2)+'\n')
        import os
        environment = dict(os.environ, BRECON_DESKTOP_PROVENANCE=str(provenance),
                           BRECON_DESKTOP_SOURCE=str(source),
                           BRECON_DESKTOP_MIN_MACOS=record['minimum_macos_from_wheel_tags'],
                           BRECON_DESKTOP_ICON=str(icon(work)))
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
            '--distpath', str(output), '--workpath', str(work/'analysis'), str(ROOT/'desktop/brecon.spec')],
            cwd=work, env=environment, check=True)
    app = output/'Brecon.app'
    archive = output/f'Brecon-{version}-macOS-{platform.machine()}.zip'
    subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(app), str(archive)], check=True)
    (output/'build-info.json').write_text(json.dumps(record, indent=2)+'\n')
    (output/'SHA256SUMS').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
    print('Built:', app)
    print('Archive (preserves bundle symlinks):', archive)
    print('Run Contents/MacOS/Brecon --desktop-check OUTPUT_DIRECTORY before distributing.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT/'dist/desktop')
    args = parser.parse_args()
    build(args.wheel.resolve(), args.source.resolve(), args.output.resolve())
