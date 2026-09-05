#!/usr/bin/env python3
"""Build deterministic SEG release archives and checksums."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Dict, Iterable
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = Path("plugins/skill-evaluation-graph")
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
EXCLUDED_DIRS = {
    ".git",
    ".audit_receipts",
    ".seg_backup",
    ".venv",
    ".pytest_cache",
    "__pycache__",
    "dist",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".swp", ".log"}
EXCLUDED_FILES = {".DS_Store"}


def _excluded(relative: Path) -> bool:
    for part in relative.parts[:-1]:
        if part in EXCLUDED_DIRS or part.startswith("dist-") or ".seg_backup-" in part:
            return True
    name = relative.name
    return name in EXCLUDED_FILES or relative.suffix in EXCLUDED_SUFFIXES or name.startswith("._")


def _files_under(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_file():
            relative = path.relative_to(root)
            if not _excluded(relative):
                yield path


def _write_zip(source_root: Path, output: Path, prefix: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source in _files_under(source_root):
            relative = source.relative_to(source_root).as_posix()
            info = zipfile.ZipInfo(f"{prefix}/{relative}", date_time=FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_release_artifacts(repo_root: Path, version: str, output_dir: Path) -> Dict[str, Path]:
    """Build installable Skill, exact repository archive, and checksum manifest."""
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    plugin_root = repo_root / PLUGIN
    if not plugin_root.is_dir() or not (plugin_root / "SKILL.md").is_file():
        raise ValueError(f"Canonical SEG package not found at {plugin_root}")
    if not version or any(ch.isspace() for ch in version):
        raise ValueError("Version must be a non-empty semantic version string")

    output_dir.mkdir(parents=True, exist_ok=True)
    skill_zip = output_dir / "skill.zip"
    repository_zip = output_dir / f"skill-evaluation-graph-v{version}.zip"
    checksums = output_dir / "SHA256SUMS.txt"

    _write_zip(plugin_root, skill_zip, "skill-evaluation-graph")
    _write_zip(repo_root, repository_zip, f"skill-evaluation-graph-v{version}")

    checksum_lines = [
        f"{_sha256(path)}  {path.name}"
        for path in sorted((skill_zip, repository_zip), key=lambda item: item.name)
    ]
    checksums.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8", newline="\n")

    return {
        "skill_zip": skill_zip,
        "repository_zip": repository_zip,
        "checksums": checksums,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="Release version without the v prefix")
    parser.add_argument("--repo", type=Path, default=ROOT, help="Repository root")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist", help="Artifact output directory")
    args = parser.parse_args()
    artifacts = build_release_artifacts(args.repo, args.version, args.output_dir)
    for name, path in artifacts.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
