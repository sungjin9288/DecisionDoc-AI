# Release Checklist

Use this checklist for each release.

## Pre-release

- [ ] Run offline tests: `python -m pytest -q`
- [ ] Verify golden snapshots: `python -m pytest -q -k golden`
- [ ] If templates changed, update snapshots locally:
  - `python -m pytest -q --update-golden -k golden`
  - commit snapshot updates
- [ ] (Optional) Run live workflow from GitHub Actions (`live` workflow_dispatch)

## Release prep

- [ ] Bump version in project metadata (when version file is introduced)
- [ ] Update `CHANGELOG.md` (`Unreleased` -> release section)
- [ ] Confirm no secrets are committed (`.env`, API keys, tokens)

## Publish

- [ ] Create release tag (example: `v0.1.1`)
- [ ] Push tag and create GitHub Release notes from changelog
