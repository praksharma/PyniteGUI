# Citing Brecon

Brecon was formerly named PyniteGUI. Cite the name/version actually used;
historical PyniteGUI release names and repository links remain valid.

If you use Brecon in research, cite the software and identify the exact release
or full Git commit used. The repository is the citation destination while the
project continues to evolve; no DOI has been assigned by this citation file.

Suggested project citation:

> Sharma, P. Brecon [Computer software].
> https://github.com/praksharma/PyniteGUI

Author: **[Prakhar Sharma](https://orcid.org/0000-0002-7635-1857)**.
ORCID: **0000-0002-7635-1857**.

For a released version, add its version and release date and link to its GitHub
release. For unreleased development code, add the full commit hash, a link to
that commit, and your access date. Cite the version you actually used, rather
than assuming that the package version identifies every development commit.

GitHub's **Cite this repository** action uses [CITATION.cff](CITATION.cff).
Its project-level metadata intentionally omits a version and release date so
that it does not mislabel later development work as the last packaged release.
Add the release or commit information to exported citations when needed.

## Solver attribution and reproducibility

Brecon is a desktop interface built on the separate
[PyNite solver](https://github.com/JWock82/Pynite). When reporting structural
analysis, also acknowledge and cite PyNite following its own citation guidance.
Record both software versions, the model file, units, load combinations,
analysis settings and any experimental features used alongside the results.

## AI-assisted development acknowledgement

Brecon was developed with substantial assistance from **OpenAI Codex**, the
AI coding assistant used for this project. Codex was used to
generate and revise source code, tests and documentation, and to assist with
debugging, verification workflows and release preparation. Prakhar Sharma
directs the project and retains responsibility for accepting changes,
validation decisions and releases.

Codex is acknowledged as a development tool and is not listed as a
bibliographic author in CITATION.cff. Git commit co-author trailers mentioning
Codex record development provenance; they do not change the software citation's
authorship. This acknowledgement does not replace attribution to PyNite or
other upstream software.

For a paper describing this software, disclose AI assistance according to the
venue's rules, stating the tool/provider and the tasks it performed. Record
model versions and dates where known rather than inferring them from the
product name. Research-publishing guidance such as
[COPE's position on authorship and AI tools](https://doi.org/10.24318/cCVRZBms)
distinguishes AI-use disclosure from human authorship and accountability.

## Future archival DOI

DOI archiving is deferred until the stable 1.0 release is ready. No archive or
publication is created by adding these files.

If Zenodo is adopted, use its **concept DOI** for the evolving project and its
**version DOI** for an exact archived release. Subsequent releases can be archived
as new versions under the same concept DOI. Keep the repository link, version
history and citation metadata current when preparing releases.

References: [GitHub citation files](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-citation-files)
and [Zenodo DOI versioning](https://zenodo.org/help/versioning).
