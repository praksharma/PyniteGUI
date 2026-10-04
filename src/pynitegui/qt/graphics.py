"""Process-start graphics selection; never changes system graphics or sandboxing."""
import argparse
import os
import shlex


MODES = ("auto", "software")
SOFTWARE_FLAGS = ("--use-gl=angle", "--use-angle=swiftshader", "--disable-gpu-compositing")
CONFLICTING_FLAGS = {"--use-gl", "--use-angle", "--use-vulkan", "--disable-gpu",
                     "--disable-gpu-compositing", "--disable-software-rasterizer", "--disable-webgl", "--disable-webgl2"}


def graphics_mode(value):
    return value if isinstance(value, str) and value in MODES else "auto"


def launch_options(argv, saved="auto"):
    parser = argparse.ArgumentParser(description="PyniteGUI structural frame editor")
    parser.add_argument("--graphics", choices=MODES, default=None,
                        help="3D rendering backend for this launch (auto or software)")
    parser.add_argument("--software-rendering", action="store_const", const="software", dest="graphics",
                        help="use CPU rendering when GPU/WebGL startup fails")
    # Qt's own engine arguments must not be consumed as application options.
    boundary = argv.index("--webEngineArgs") if "--webEngineArgs" in argv else len(argv)
    options, remaining = parser.parse_known_args(argv[1:boundary])
    return graphics_mode(options.graphics if options.graphics is not None else saved), [argv[0], *remaining, *argv[boundary:]]


def configure_graphics(mode, environment=None):
    environment = os.environ if environment is None else environment
    mode = graphics_mode(mode)
    if mode == "software":
        flags = shlex.split(environment.get("QTWEBENGINE_CHROMIUM_FLAGS", ""))
        flags = [flag for flag in flags if flag.split("=", 1)[0] not in CONFLICTING_FLAGS]
        # CPU compositing avoids sharing GL textures with an incompatible desktop driver.
        environment["QTWEBENGINE_CHROMIUM_FLAGS"] = shlex.join([*flags, *SOFTWARE_FLAGS])
        environment["QT_OPENGL"] = "software"
    return mode
