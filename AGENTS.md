# Repository Instructions

## Git Commits

Every Git commit created or amended by Codex in this repository must include
this exact trailer in the commit message, separated from the body by a blank line:

```text
Co-authored-by: Codex <codex@openai.com>
```

Apply this rule to documentation-only commits as well as code commits. Do not
rewrite existing commit history unless the user explicitly requests it.

## Documentation

- Keep `README.md` short: project overview, logo, quick start, and useful links.
- Maintain detailed workflows, engineering limitations, architecture, and test
  instructions in `GUIDE.md`.
- Update `TODO.md` as features are implemented or new work is identified.
- Commit completed, verified changes in coherent groups with their tests.
- The Zensical site generates topic pages from `GUIDE.md` and the project records.
  Do not edit `.docs-build/` or `site/`. Update `scripts/docs.py` topic mapping and
  `zensical.toml` navigation for new GUIDE headings; keep `docs/features.md` and
  authored tutorials in sync. Run the strict docs build and local-link check.

## Test Selection

- Use `python -B scripts/test.py --list` to choose focused groups. For purely
  visual/native UI changes, start with `smoke ui` and the affected feature tests;
  do not run unrelated solver/slab benchmarks for a label, spacing or colour edit.
- Combine groups when a change crosses responsibilities. Changes to supports,
  loads, units or model/solver contracts also need the relevant engineering tests.
  Surface work uses `surfaces`; MCP work uses `mcp` with the optional extra.
- Run the full Python suite (`scripts/test.py all`, with the MCP extra) for shared
  infrastructure/model/solver changes and before releases. Viewport checks and
  strict docs builds are separate, explicit checks when those areas change.
- Keep every test class assigned in `tests/groups.toml`; `scripts/test.py --check`
  checks coverage without importing app dependencies. Existing unittest discovery
  remains supported. Focused selection never permits ignoring a known failure.
