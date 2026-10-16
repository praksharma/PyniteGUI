"""Documentation coverage, generation and local HTML validation need no app imports."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("docs_site", ROOT/"scripts/docs.py")
docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs)


class DocsTests(unittest.TestCase):
    def test_every_guide_topic_and_body_is_preserved(self):
        pages = docs.page_sources()
        sections = docs.sections((ROOT/"GUIDE.md").read_text())
        self.assertEqual({title for _, title, _ in sections}, set(docs.SECTION_PAGES))
        self.assertGreater(len(sections), 40)
        for _, title, body in sections:
            path, _ = docs.SECTION_PAGES[title]
            if body.strip():
                self.assertIn(docs.rewrite_links(body.strip(), path), pages[path])
        for path in docs.PROJECT_PAGES.values():
            self.assertIn(path, pages)

    def test_fenced_headings_are_content_and_bad_heading_structure_fails(self):
        text = '# Root\n\n```python\n## Not a page\n```\n\n## Child\nbody\n'
        result = docs.sections(text)
        self.assertEqual([title for _, title, _ in result], ['Root', 'Child'])
        self.assertIn('## Not a page', result[0][2])
        for bad in ('unheaded text', '# A\n## A\n', '# A\n```python\n'):
            with self.assertRaises(ValueError):
                docs.sections(bad)

    def test_document_and_guide_anchor_links_are_rebased(self):
        text = '[Roadmap](TODO.md#pynite-capability-coverage) [Slab](GUIDE.md#surfaces-in-the-main-3d-model) [External](https://example.com/a)'
        actual = docs.rewrite_links(text, 'analysis/loads.md')
        self.assertIn('../project/roadmap.md#pynite-capability-coverage', actual)
        self.assertIn('../surfaces/main-model.md', actual)
        self.assertIn('https://example.com/a', actual)
        with self.assertRaisesRegex(ValueError, 'Unmapped'):
            docs.rewrite_links('[Bad](GUIDE.md#missing)', 'index.md')

    def test_prepare_is_deterministic_and_never_changes_canonical_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('GUIDE.md', 'zensical.toml', *docs.PROJECT_PAGES):
                shutil.copyfile(ROOT/name, root/name)
            shutil.copytree(ROOT/'docs', root/'docs')
            shutil.copytree(ROOT/'assets', root/'assets')
            originals = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            output = docs.prepare(root)
            first = {p.relative_to(output): p.read_bytes() for p in output.rglob('*') if p.is_file()}
            (output/'stale.md').write_text('# Stale')
            docs.prepare(root)
            second = {p.relative_to(output): p.read_bytes() for p in output.rglob('*') if p.is_file()}
            self.assertEqual(first, second)
            for name, content in originals.items():
                self.assertEqual((root/name).read_bytes(), content)
            self.assertEqual((output/'assets/logo.png').read_bytes(), (ROOT/'assets/PyniteGUI Structural Frame Logo.png').read_bytes())
            with (root/'GUIDE.md').open('a') as stream:
                stream.write('\n## Unmapped new feature\nDetails\n')
            with self.assertRaisesRegex(ValueError, 'mapping'):
                docs.prepare(root)

    def test_local_link_checker_handles_base_path_anchors_and_url_encoding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'topic').mkdir()
            (root/'assets').mkdir()
            (root/'assets/my image.png').write_bytes(b'image fixture')
            (root/'topic/index.html').write_text('<h1 id="details">Topic</h1><a href="../">Home</a>')
            index = root/'index.html'
            valid = '<a href="/PyniteGUI/topic/#details">Topic</a><img src="assets/my%20image.png"><a href="https://example.com/">Remote</a>'
            index.write_text(valid)
            docs.check_site(root)
            for invalid in ('<a href="topic/#missing">Bad</a>', '<img src="lost.png">', '<a href="../outside">Outside</a>'):
                index.write_text(valid+invalid)
                with self.assertRaises(ValueError):
                    docs.check_site(root)

    def test_docs_dependency_is_not_a_runtime_dependency_or_extra(self):
        config = tomllib.loads((ROOT/'pyproject.toml').read_text())
        self.assertTrue(any('zensical' in value for value in config['dependency-groups']['docs']))
        self.assertFalse(any('zensical' in value for value in config['project']['dependencies']))
        self.assertNotIn('docs', config['project']['optional-dependencies'])
        nav = tomllib.loads((ROOT/'zensical.toml').read_text())['project']['nav']
        self.assertEqual(len(docs.navigation_paths(nav)), len(set(docs.navigation_paths(nav))))


if __name__ == '__main__':
    unittest.main()
