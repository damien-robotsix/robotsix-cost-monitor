"""Contract test: @anthropic-ai/claude-code version consistency.

Ensures that the claude-code version is identical across:
- package.json (devDependencies — Dependabot-tracked source)
- Dockerfile (CLAUDE_CODE_VERSION ARG default — production image)
- Dockerfile.dev (CLAUDE_CODE_VERSION ARG default — dev/CI image)

A Dependabot bump of package.json that misses the Dockerfile ARG defaults
is caught at ``pytest`` time rather than at deploy time.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_JSON = REPO_ROOT / "package.json"
DOCKERFILE = REPO_ROOT / "Dockerfile"
DOCKERFILE_DEV = REPO_ROOT / "Dockerfile.dev"


def _extract_claude_code_version_from_package_json(path: Path) -> str:
    """Return the ``@anthropic-ai/claude-code`` version from package.json."""
    data: dict[str, dict[str, str]] = json.loads(path.read_text())
    return data["devDependencies"]["@anthropic-ai/claude-code"]


_CLAUDECODE_ARG_RE = re.compile(r"^ARG\s+CLAUDE_CODE_VERSION=(\S+)", re.MULTILINE)


def _extract_claude_code_version_from_dockerfile(path: Path) -> str:
    """Return the ``CLAUDE_CODE_VERSION`` ARG default from a Dockerfile."""
    text = path.read_text()
    m = _CLAUDECODE_ARG_RE.search(text)
    if m is None:
        raise AssertionError(f"CLAUDE_CODE_VERSION ARG not found in {path.name}")
    return m.group(1)


# ============================================================================
# 1. All three files reference the same version
# ============================================================================


class TestClaudeCodeVersionConsistency:
    """The version pinned in package.json must match both Dockerfiles."""

    def test_package_json_and_dockerfile_match(self) -> None:
        pkg_ver = _extract_claude_code_version_from_package_json(PACKAGE_JSON)
        docker_ver = _extract_claude_code_version_from_dockerfile(DOCKERFILE)
        assert pkg_ver == docker_ver, (
            f"package.json has @anthropic-ai/claude-code {pkg_ver!r}, "
            f"but Dockerfile has CLAUDE_CODE_VERSION={docker_ver!r}"
        )

    def test_package_json_and_dockerfile_dev_match(self) -> None:
        pkg_ver = _extract_claude_code_version_from_package_json(PACKAGE_JSON)
        docker_dev_ver = _extract_claude_code_version_from_dockerfile(DOCKERFILE_DEV)
        assert pkg_ver == docker_dev_ver, (
            f"package.json has @anthropic-ai/claude-code {pkg_ver!r}, "
            f"but Dockerfile.dev has CLAUDE_CODE_VERSION={docker_dev_ver!r}"
        )

    def test_both_dockerfiles_match(self) -> None:
        docker_ver = _extract_claude_code_version_from_dockerfile(DOCKERFILE)
        docker_dev_ver = _extract_claude_code_version_from_dockerfile(DOCKERFILE_DEV)
        assert docker_ver == docker_dev_ver, (
            f"Dockerfile has CLAUDE_CODE_VERSION={docker_ver!r}, "
            f"but Dockerfile.dev has CLAUDE_CODE_VERSION={docker_dev_ver!r}"
        )
