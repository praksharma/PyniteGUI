"""Build the Zensical manual from maintained Markdown, without importing the app."""
import argparse
from html.parser import HTMLParser
import os
from pathlib import Path
import posixpath
import re
import shutil
import subprocess
import sys
import tomllib
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SECTION_PAGES = {
    "PyniteGUI Guide": ("reference/version-scope.md", "Version and Scope"),
    "Run": ("start/install.md", "Installation"),
    "Experimental Surface Meshing": ("surfaces/meshing.md", "Surface Mesh Generators"),
    "Surfaces in the Main 3D Model": ("surfaces/main-model.md", "Slab Placement and Main-Model Surfaces"),
    "Experimental Rectangular Plates": ("surfaces/plates.md", "Rectangular Plate Analysis"),
    "Optional MCP Automation": ("automation/mcp.md", "Optional MCP Server"),
    "Optional Live Recalculation": ("analysis/live.md", "Live Recalculation"),
    "Platform Checks": ("start/platforms.md", "Platform Validation"),
    "Spatial Frames": ("modeling/3d.md", "3D Frames and Trusses"),
    "Graphics Recovery": ("start/graphics.md", "3D Graphics Recovery"),
    "NVIDIA Hardware Rendering on Linux": ("start/nvidia.md", "NVIDIA and Wayland"),
    "Workflow": ("modeling/index.md", "Modeling Workflows"),
    "Help and Workspace": ("start/help.md", "Help, Shortcuts and Workspace Layout"),
    "Examples and Appearance": ("start/examples.md", "Examples, Themes and Preferences"),
    "Drawing and Selection": ("modeling/drawing.md", "Drawing and Selection"),
    "Model Tables": ("modeling/tables.md", "Model Tables"),
    "Topology and Model Checks": ("modeling/topology.md", "Topology and Model Checks"),
    "Member End Releases": ("modeling/releases.md", "Member End Releases"),
    "Autosave and Recovery": ("reference/recovery.md", "Autosave and Recovery"),
    "Supports and Springs": ("modeling/supports.md", "Supports and Springs"),
    "Moving Nodes": ("modeling/moving.md", "Moving Nodes"),
    "Point and Distributed Loads": ("analysis/loads.md", "Point, Angled and Distributed Loads"),
    "Load Cases and Combinations": ("analysis/combinations.md", "Load Cases and Combinations"),
    "Materials and Sections": ("modeling/properties.md", "Materials and Sections"),
    "Analysis and Force Diagrams": ("analysis/solve.md", "Analysis, Deformation and Force Diagrams"),
    "Combination Envelopes": ("results/envelopes.md", "Combination Envelopes"),
    "CSV and Printable Reports": ("results/reports.md", "CSV and Printable Reports"),
    "Result Snapshots": ("results/snapshots.md", "Result Snapshots"),
    "Saving and History": ("reference/saving.md", "Saving and Undo History"),
    "Construction Connections": ("modeling/construction.md", "Construction Connections"),
    "Linked Results": ("results/linked.md", "Linked Results and Equilibrium"),
    "Units": ("reference/units.md", "Units and Conversions"),
    "Engineering Scope": ("reference/engineering.md", "Engineering Scope and Limits"),
    "Automatic Self-Weight": ("analysis/self-weight.md", "Automatic Self-Weight"),
    "Release Formulation": ("reference/releases.md", "Release Formulation"),
    "Axial-Only Trusses": ("modeling/trusses.md", "Axial-Only Trusses"),
    "Stability Diagnostics": ("analysis/stability.md", "Stability Diagnostics"),
    "Material Library Reference": ("reference/materials.md", "Material Library Reference"),
    "Section Library Reference": ("reference/sections.md", "Section Library Reference"),
    "Project File Formats": ("reference/formats.md", "Project File Formats"),
    "Diagram Sign Conventions": ("results/conventions.md", "Diagram Sign Conventions"),
    "Architecture": ("development/architecture.md", "Architecture"),
    "Development": ("development/testing.md", "Testing and Development"),
    "Spatial Performance Checks": ("development/performance.md", "Spatial Performance Checks"),
    "Additional Regression Coverage": ("development/regressions.md", "Regression Coverage"),
    "Documentation Site": ("development/documentation.md", "Maintaining the Documentation"),
}
PROJECT_PAGES = {"TODO.md": "project/roadmap.md", "TODO_SECONDARY.md": "project/secondary.md",
                 "CHANGELOG.md": "project/changelog.md", "RELEASE.md": "project/releases.md"}
ASSETS = {"PyniteGUI Structural Frame Logo.png": "logo.png", "structure.png": "structure.png", "SFD.png": "sfd.png"}


def sections(text):
    """Split the GUIDE's explicit headings, preserving every body line and fence."""
    result, current, fence = [], None, None
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            if current:
                current[2].append(line)
            continue
        heading = re.match(r"^(#{1,3}) (.+?)\s*$", line) if fence is None else None
        if heading:
            current = [len(heading[1]), heading[2], []]
            result.append(current)
        elif current:
            current[2].append(line)
        elif line.strip():
            raise ValueError("GUIDE content must start with a heading.")
    if fence is not None:
        raise ValueError("Unclosed Markdown fence in GUIDE.md.")
    titles = [item[1] for item in result]
    if len(titles) != len(set(titles)):
        raise ValueError("GUIDE headings must be unique for deterministic topic pages.")
    return [(level, title, "".join(lines)) for level, title, lines in result]


def slug(title):
    return re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-")


def relative(target, page):
    return posixpath.relpath(target, posixpath.dirname(page) or ".")


def rewrite_links(text, page):
    def replacement(match):
        target = match[1]
        name, _, anchor = target.partition("#")
        if name in PROJECT_PAGES:
            destination = relative(PROJECT_PAGES[name], page)
            return "](" + destination + ("#"+anchor if anchor else "") + ")"
        if name == "GUIDE.md":
            guide_target = next((value[0] for key, value in SECTION_PAGES.items() if slug(key) == anchor), None)
            if anchor and guide_target is None:
                raise ValueError(f"Unmapped GUIDE anchor: {anchor}")
            return "](" + relative(guide_target or SECTION_PAGES["PyniteGUI Guide"][0], page) + ")"
        return match[0]
    return re.sub(r"\]\(([^\s)]+)\)", replacement, text)


def page_sources(root=ROOT):
    guide = sections((root/"GUIDE.md").read_text(encoding="utf-8"))
    actual = {title for _, title, _ in guide}
    if actual != set(SECTION_PAGES):
        raise ValueError(f"Update documentation topic mapping. Missing: {actual-set(SECTION_PAGES)}; stale: {set(SECTION_PAGES)-actual}")
    output = {}
    for index, (level, title, body) in enumerate(guide):
        page, display_title = SECTION_PAGES[title]
        if not body.strip():
            children = []
            for child_level, child_title, _ in guide[index+1:]:
                if child_level <= level:
                    break
                destination, label = SECTION_PAGES[child_title]
                children.append(f"- [{label}]({relative(destination, page)})")
            body = "\n".join(children)+"\n"
        footer = f"\n\n---\n\nSource: [GUIDE.md](https://github.com/praksharma/PyniteGUI/blob/master/GUIDE.md#{slug(title)}). "
        footer += "This manual follows the current repository; the published rc1 wheel has a smaller feature set.\n"
        output[page] = f"# {display_title}\n\n" + rewrite_links(body.strip(), page) + footer
    for source, page in PROJECT_PAGES.items():
        prefix = ""
        if source == "RELEASE.md":
            prefix = "> Release preparation and validation record, not a claim that all platform gates are complete.\n\n"
        output[page] = prefix + rewrite_links((root/source).read_text(encoding="utf-8"), page)
    return output


def navigation_paths(nav):
    result = []
    for entry in nav:
        if not isinstance(entry, dict):
            raise ValueError("Documentation navigation entries must be title/value maps.")
        for value in entry.values():
            if isinstance(value, list):
                result.extend(navigation_paths(value))
            elif isinstance(value, str) and not urlsplit(value).scheme:
                result.append(value)
    return result


def prepare(root=ROOT):
    pages = page_sources(root)
    config = tomllib.loads((root/"zensical.toml").read_text(encoding="utf-8"))["project"]
    authored = {p.relative_to(root/"docs").as_posix(): p for p in (root/"docs").rglob("*") if p.is_file()}
    if set(pages) & set(authored):
        raise ValueError("Authored docs must not overwrite generated GUIDE/project pages.")
    expected = set(pages) | {name for name in authored if name.endswith(".md")}
    paths = navigation_paths(config["nav"])
    if set(paths) != expected or len(paths) != len(set(paths)):
        raise ValueError(f"Navigation must include every page once. Unlisted: {expected-set(paths)}; unknown: {set(paths)-expected}")
    destination = root/config["docs_dir"]
    if destination.resolve() != (root/".docs-build/docs").resolve() or not destination.resolve().is_relative_to(root.resolve()):
        raise ValueError("Generated documentation must stay in the repository's .docs-build/docs directory.")
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for name, content in pages.items():
        path = destination/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    for name, source in authored.items():
        target = destination/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    (destination/"assets").mkdir(exist_ok=True)
    for source, name in ASSETS.items():
        shutil.copyfile(root/"assets"/source, destination/"assets"/name)
    print(f"Prepared {len(expected)} documentation pages from GUIDE, project records and authored introductions.")
    return destination


class PageLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.links = set(), []

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if attributes.get("id"):
            self.ids.add(attributes["id"])
        for key in ("href", "src"):
            if attributes.get(key):
                self.links.append(attributes[key])


def check_site(site, base_path="/PyniteGUI/"):
    site = site.resolve()
    pages = {}
    for path in site.rglob("*.html"):
        parser = PageLinks()
        parser.feed(path.read_text(encoding="utf-8"))
        pages[path] = parser
    if not pages:
        raise ValueError("No built documentation HTML found.")
    errors = []
    for path, parser in pages.items():
        for link in parser.links:
            url = urlsplit(link)
            if url.scheme or url.netloc:
                continue
            name = unquote(url.path)
            if name.startswith(base_path):
                target = site/name[len(base_path):]
            elif name.startswith("/"):
                target = site/name.lstrip("/")
            else:
                target = path.parent/name if name else path
            target = target.resolve()
            if target.is_dir():
                target /= "index.html"
            if not target.is_relative_to(site) or not target.exists():
                errors.append(f"{path.relative_to(site)}: missing {link}")
            elif url.fragment and target in pages and unquote(url.fragment) not in pages[target].ids:
                errors.append(f"{path.relative_to(site)}: missing anchor {link}")
    if errors:
        raise ValueError("\n".join(errors[:40]))
    print(f"PASS: local links, images, assets and anchors across {len(pages)} built HTML pages.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "build", "check", "serve"))
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    os.chdir(ROOT)
    if args.command == "check":
        check_site(ROOT/"site")
        return
    prepare()
    if args.command == "prepare":
        return
    command = [sys.executable, "-m", "zensical"]
    if args.command == "serve":
        subprocess.run([*command, "serve", "--dev-addr", f"127.0.0.1:{args.port}"], check=True)
    else:
        subprocess.run([*command, "build", "--clean", "--strict"], check=True)
        check_site(ROOT/"site")


if __name__ == "__main__":
    main()
