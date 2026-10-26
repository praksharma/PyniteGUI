"""Run focused unittest groups without importing unrelated application tests."""
import argparse
import ast
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
import tomllib
import traceback
import unittest

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Inventory:
    selectors: set
    classes: set


def inventory(root):
    selectors, classes = set(), set()
    for path in sorted((root/"tests").glob("test*.py")):
        module = path.stem
        selectors.add(module)
        for node in ast.parse(path.read_text(), filename=str(path)).body:
            if not isinstance(node, ast.ClassDef):
                continue
            methods = [item.name for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test_")]
            if methods:
                name = f"{module}.{node.name}"
                classes.add(name)
                selectors.add(name)
                selectors.update(f"{name}.{method}" for method in methods)
    return Inventory(selectors, classes)


def matches(selector, name):
    return name == selector or name.startswith(selector+".")


def configuration(root):
    config = tomllib.loads((root/"tests/groups.toml").read_text())
    found = inventory(root)
    groups, profiles, external = (config.get(key, {}) for key in ("groups", "profiles", "external"))
    names = [*groups, *profiles, *external]
    if len(names) != len(set(names)) or "all" in names:
        raise ValueError("Group names must be unique; all is reserved.")
    for section in (groups, profiles):
        for name, entry in section.items():
            selectors = entry.get("tests")
            if not isinstance(selectors, list) or not selectors or any(item not in found.selectors for item in selectors):
                raise ValueError(f"Group {name}: missing, empty or unknown test selector.")
    for name, entry in groups.items():
        if any(selector.count(".") > 1 for selector in entry["tests"]):
            raise ValueError(f"Primary group {name} must own complete modules or classes; use a profile for individual methods.")
    for name in sorted(found.classes):
        owners = [group for group, entry in groups.items() if any(matches(selector, name) for selector in entry["tests"])]
        if len(owners) != 1:
            raise ValueError(f"Test class {name} must belong to exactly one primary group; found {owners}.")
    for name, entry in external.items():
        scripts = entry.get("scripts")
        if not isinstance(scripts, list) or not scripts:
            raise ValueError(f"External group {name} has no scripts.")
        for script in scripts:
            path = (root/script).resolve()
            if not path.is_relative_to((root/"tests").resolve()) or not path.is_file() or path.suffix != ".cjs":
                raise ValueError(f"External group {name}: unknown viewport test script {script}.")
    return config, found


def plan(config, found, names):
    selectors, scripts = set(), []
    for name in names:
        if name == "all":
            for entry in config["groups"].values():
                selectors.update(entry["tests"])
        elif name in config["groups"] or name in config.get("profiles", {}):
            entry = config["groups"].get(name, config.get("profiles", {}).get(name))
            selectors.update(entry["tests"])
        elif name in config.get("external", {}):
            scripts.extend(config["external"][name]["scripts"])
        elif name in found.selectors:
            selectors.add(name)
        else:
            raise ValueError(f"Unknown group/test {name!r}; use --list to see groups.")
    # A module/class already includes its narrower selectors. Repeated groups,
    # profiles and explicit tests must not execute the same case twice.
    selectors = sorted(item for item in selectors if not any(other != item and matches(other, item) for other in selectors))
    return selectors, list(dict.fromkeys(scripts))


def cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from cases(item)
        else:
            yield item


def python_suite(selectors):
    loader = unittest.TestLoader()
    selected = loader.loadTestsFromNames(selectors)
    return unittest.TestSuite({test.id():test for test in cases(selected)}.values()), loader.errors


def main(argv=None, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__, epilog="Default: smoke. all runs every Python test; viewport and strict docs builds remain explicit.")
    parser.add_argument("groups", nargs="*", help="Group names or dotted unittest selectors; combine groups freely.")
    parser.add_argument("--list", action="store_true", help="List group definitions without importing application tests.")
    parser.add_argument("--check", action="store_true", help="Check that every test class has exactly one primary group; no test imports.")
    parser.add_argument("--dry-run", action="store_true", help="Print selected tests/scripts without importing or running them.")
    parser.add_argument("--collect-only", action="store_true", help="Import only selected Python tests and print case IDs without running them.")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--failfast", action="store_true")
    args = parser.parse_args(argv)
    try:
        config, found = configuration(root)
        if args.list:
            for section in ("groups", "profiles", "external"):
                for name, entry in config.get(section, {}).items():
                    print(f"{name}: {entry['description']}")
                    for selector in entry.get("tests", entry.get("scripts", [])):
                        print(f"  {selector}")
            print("all: every Python test once (viewport scripts and strict docs build are separate)")
            return 0
        if args.check:
            print(f"PASS: {len(found.classes)} test classes assigned to {len(config['groups'])} primary groups.")
            return 0
        names = args.groups or ["smoke"]
        selectors, scripts = plan(config, found, names)
    except (ValueError, KeyError, OSError, SyntaxError, tomllib.TOMLDecodeError) as error:
        parser.error(str(error))
    print(f"Selected: {', '.join(names)}", flush=True)
    if args.dry_run:
        for selector in selectors:
            print(f"python: {selector}")
        for script in scripts:
            print(f"node: {script}")
        return 0
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
    original_path, original_cwd = list(sys.path), Path.cwd()
    try:
        sys.path.insert(0, str(root/"tests"))
        os.chdir(root)
        success = True
        if selectors:
            suite, load_errors = python_suite(selectors)
            if "all" in names and not load_errors:
                # An explicit full run also catches dynamically supplied tests or
                # inherited cases not visible to the dependency-free AST check.
                discovered = unittest.TestLoader().discover(str(root/"tests"))
                actual = {test.id() for test in cases(suite)}
                expected = {test.id() for test in cases(discovered)}
                if actual != expected:
                    raise RuntimeError("Full group coverage differs from unittest discovery. "
                                       f"Missing: {sorted(expected-actual)}; unexpected: {sorted(actual-expected)}")
            if args.collect_only:
                for test in cases(suite):
                    print(test.id())
                if load_errors:
                    for error in load_errors:
                        print(error, file=sys.stderr)
                    success = False
            else:
                result = unittest.TextTestRunner(verbosity=2 if args.verbose else 1, failfast=args.failfast).run(suite)
                success = result.wasSuccessful()
        if args.collect_only:
            for script in scripts:
                print(f"node: {script}")
            return 0 if success else 1
        for script in scripts:
            if args.failfast and not success:
                break
            try:
                completed = subprocess.run(["node", str(root/script)], cwd=root, check=False)
                success = completed.returncode == 0 and success
            except OSError as error:
                print(f"Cannot run {script}: {error}. Install Node and the separately documented Playwright test tools.", file=sys.stderr)
                success = False
        return 0 if success else 1
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        sys.path[:] = original_path
        os.chdir(original_cwd)


if __name__ == "__main__":
    raise SystemExit(main())
