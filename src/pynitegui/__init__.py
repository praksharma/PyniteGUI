from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pynitegui")
except PackageNotFoundError:
    __version__ = "0+uninstalled"


def main() -> None:
    import sys
    if sys.argv[1:] == ["--version"]:
        print(f"PyniteGUI {__version__}")
        return
    from .qt.app import main as launch

    launch()
