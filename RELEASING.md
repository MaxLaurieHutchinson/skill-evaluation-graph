# Releasing SEG

SEG uses Release Please so publication has one human decision and deterministic mechanics.

## Release flow

1. Merge normal changes to `main` using Conventional Commit prefixes.
2. `Test and Validate SEG` runs on the exact `main` commit.
3. After that workflow succeeds, `Release SEG` creates or updates the Release Please PR.
4. Review the proposed version and changelog. **Merging that Release Please PR grants publication authority.**
5. The merged release tree must pass `Test and Validate SEG` on `main` again.
6. `Release SEG` creates the `vMAJOR.MINOR.PATCH` tag and GitHub Release, checks out that exact tag, reruns the full validation suite, builds deterministic assets, and uploads:
   - `skill.zip`
   - `skill-evaluation-graph-vMAJOR.MINOR.PATCH.zip`
   - `SHA256SUMS.txt`

There is no manual tag, ZIP, checksum, or GitHub Release step.

## Versioning

Release Please derives the next version from Conventional Commits:

- `fix:` -> patch release
- `feat:` -> minor release
- `feat!:` or a `BREAKING CHANGE:` footer -> major release

`version.txt` is the release version file used by the `simple` Release Please strategy. The release PR updates it together with SEG's runtime `__version__` and the Codex, Claude, and Gemini manifests. `scripts/validate_release.py` independently rejects version drift.

For a one-off forced version, use a `Release-As: X.Y.Z` commit footer rather than a persistent `release-as` setting.

## Credentials

The workflow works with GitHub's built-in `GITHUB_TOKEN` and requires no repository secret for publication mechanics.

If you want Release Please-created PRs themselves to trigger normal pull-request workflows, configure a `RELEASE_PLEASE_TOKEN` with the required repository permissions. When that secret is absent, the workflow falls back to `GITHUB_TOKEN`; the merged release tree is still tested on `main` before a release is created.

Repository settings must allow GitHub Actions to create pull requests when using the built-in token.

## Local release checks

Run the same canonical checks before changing release infrastructure:

```bash
python -m unittest discover -s plugins/skill-evaluation-graph/tests
python -m unittest discover -s plugins/skill-evaluation-graph/scripts
python plugins/skill-evaluation-graph/scripts/audit_skill.py plugins/skill-evaluation-graph --verbose
python scripts/validate_release.py
```

To exercise packaging without publishing anything:

```bash
python scripts/build_release.py --version 1.2.3 --output-dir dist
```

The builder is deterministic: identical source bytes and version input produce byte-identical ZIPs and checksum output.
