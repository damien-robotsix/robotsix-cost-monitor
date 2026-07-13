## Change Summary

<!-- Describe what this PR changes and why. -->

## Related issue

<!-- Link to the issue this fixes, if applicable (e.g. `fix #123`). -->

## Checklist

- [ ] The PR title follows [Conventional Commits](https://www.conventionalcommits.org/) — it will be used in the changelog
- [ ] Tests cover the new behaviour, and `uv run pytest` passes locally
- [ ] `uv run ruff check . && uv run ruff format --check .` passes
- [ ] `uv run mypy src/` passes (no new type errors)
- [ ] If the change affects runtime behaviour, I added a changelog entry under `## [Unreleased]` with the appropriate category header (`### Added`, `### Changed`, `### Fixed`, etc.) in `CHANGELOG.md`
