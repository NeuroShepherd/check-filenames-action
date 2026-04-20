#!/usr/bin/env python3

"""Opinionated filename and folder naming checks for GitHub Actions."""

from __future__ import annotations

import argparse
from datetime import datetime
import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path
import re
import sys


VALID_NAME_PATTERN = re.compile(r"^[a-z]+(?:-[a-z]+)*$")
VALID_EXTENSION_PATTERN = re.compile(r"^[a-z]+$")
DEFAULT_DATE_FORMAT = "%Y-%m-%d"
SUPPORTED_DATE_DIRECTIVES: dict[str, str] = {
    "%Y": r"\d{4}",
    "%m": r"(?:0[1-9]|1[0-2])",
    "%d": r"(?:0[1-9]|[12]\d|3[01])",
    "%H": r"(?:[01]\d|2[0-3])",
    "%M": r"[0-5]\d",
    "%S": r"[0-5]\d",
}


@dataclass
class Finding:
    severity: str
    path: str
    message: str


def group_findings_by_path(
    findings: list[Finding], severity: str
) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = {}
    for finding in findings:
        if finding.severity != severity:
            continue
        grouped.setdefault(finding.path, set()).add(finding.message)
    return grouped


def print_grouped_findings(title: str, marker: str, grouped: dict[str, set[str]]) -> None:
    if not grouped:
        return

    print(f"::group::{title}")
    for path in sorted(grouped):
        print(f"{marker} {path}")
        for message in sorted(grouped[path]):
            print(f"  - {message}")
    print("::endgroup::")


def append_step_summary(
    checked_file_count: int,
    error_count: int,
    warning_count: int,
    error_groups: dict[str, set[str]],
    warning_groups: dict[str, set[str]],
) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    lines: list[str] = []
    lines.append("## Filename Check Results")
    lines.append("")
    lines.append(f"- Checked files: {checked_file_count}")
    lines.append(f"- Errors: {error_count}")
    lines.append(f"- Warnings: {warning_count}")
    lines.append("")

    if error_groups:
        lines.append("### Failed Paths")
        lines.append("")
        for path in sorted(error_groups):
            lines.append(f"- {path}")
            for message in sorted(error_groups[path]):
                lines.append(f"  - {message}")
        lines.append("")

    if warning_groups:
        lines.append("### Warnings")
        lines.append("")
        for path in sorted(warning_groups):
            lines.append(f"- {path}")
            for message in sorted(warning_groups[path]):
                lines.append(f"  - {message}")
        lines.append("")

    with open(summary_path, "a", encoding="utf-8") as summary_file:
        summary_file.write("\n".join(lines) + "\n")


def parse_file_types(raw_file_types: str) -> set[str] | None:
    if not raw_file_types:
        return None

    normalized = raw_file_types.strip().lower()
    if normalized in {"all", "*"}:
        return None

    file_types: set[str] = set()
    for token in raw_file_types.replace(";", ",").split(","):
        ext = token.strip().lower()
        if not ext:
            continue
        if ext.startswith("."):
            ext = ext[1:]
        if ext in {"all", "*"}:
            return None
        file_types.add(ext)

    return file_types if file_types else None


def load_ignore_patterns(root: Path, ignore_file: str) -> list[str]:
    ignore_path = root / ignore_file
    if not ignore_path.exists():
        return []

    patterns: list[str] = []
    for line in ignore_path.read_text(encoding="utf-8").splitlines():
        pattern = line.strip()
        if not pattern or pattern.startswith("#"):
            continue

        # Normalize separators and root-relative prefixes without stripping
        # leading dots from dotfile names (for example: .venv).
        pattern = pattern.replace("\\", "/")
        if pattern.startswith("./"):
            pattern = pattern[2:]
        elif pattern.startswith("/"):
            pattern = pattern[1:]

        if pattern:
            patterns.append(pattern)
    return patterns


def is_ignored(relative_path: str, patterns: list[str]) -> bool:
    rel = relative_path.replace("\\", "/")
    base_name = Path(rel).name

    for pattern in patterns:
        if pattern.endswith("/"):
            prefix = pattern.rstrip("/")
            if rel == prefix or rel.startswith(prefix + "/"):
                return True

        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(base_name, pattern):
            return True

    return False


def check_kebab_case(name: str) -> bool:
    return bool(VALID_NAME_PATTERN.fullmatch(name))


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y", "on"}:
        return True
    if normalized in {"false", "0", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(
        "expected a boolean value (true/false, yes/no, 1/0)"
    )


def build_date_pattern(date_format: str) -> re.Pattern[str]:
    pattern_parts: list[str] = []
    index = 0

    while index < len(date_format):
        char = date_format[index]
        if char == "%":
            token = date_format[index : index + 2]
            if len(token) < 2 or token not in SUPPORTED_DATE_DIRECTIVES:
                raise ValueError(
                    "date-format contains unsupported directive; "
                    "supported directives are %Y, %m, %d, %H, %M, %S"
                )
            pattern_parts.append(SUPPORTED_DATE_DIRECTIVES[token])
            index += 2
            continue

        pattern_parts.append(re.escape(char))
        index += 1

    return re.compile("".join(pattern_parts))


def _is_date_boundary_valid(stem: str, start: int, end: int) -> bool:
    before_ok = start == 0 or stem[start - 1] == "-"
    after_ok = end == len(stem) or stem[end] == "-"
    return before_ok and after_ok


def contains_valid_date_fragment(
    stem: str, date_format: str, date_pattern: re.Pattern[str]
) -> bool:
    for match in date_pattern.finditer(stem):
        start, end = match.span()
        if not _is_date_boundary_valid(stem, start, end):
            continue

        try:
            datetime.strptime(match.group(0), date_format)
        except ValueError:
            continue

        normalized = f"{stem[:start]}date{stem[end:]}"
        if check_kebab_case(normalized):
            return True

    return False


def normalize_dot_name(name: str, dotfile_mode: str) -> str:
    if dotfile_mode == "strip-leading-dot" and name.startswith("."):
        return name[1:]
    return name


def check_file_name(
    path: Path,
    dotfile_mode: str,
    allow_dates_in_file_names: bool,
    date_format: str,
    date_pattern: re.Pattern[str],
) -> list[str]:
    issues: list[str] = []
    stem = normalize_dot_name(path.stem, dotfile_mode)

    stem_is_valid = check_kebab_case(stem)
    if not stem_is_valid and allow_dates_in_file_names:
        stem_is_valid = contains_valid_date_fragment(stem, date_format, date_pattern)

    if not stem_is_valid:
        issues.append(
            "filename stem must use lowercase kebab-case with letters and dashes only"
        )

    for suffix in path.suffixes:
        ext = suffix.lstrip(".")
        if not VALID_EXTENSION_PATTERN.fullmatch(ext):
            issues.append("file extension must use lowercase letters only")
            break

    return issues


def check_directory_name(name: str, dotfile_mode: str) -> list[str]:
    name = normalize_dot_name(name, dotfile_mode)
    if check_kebab_case(name):
        return []
    return [
        "directory name must use lowercase kebab-case with letters and dashes only"
    ]


def relative_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(description="Check filenames and folder names.")
    parser.add_argument("--root", default=".", help="Repository root path")
    parser.add_argument(
        "--max-path-length",
        type=int,
        default=65,
        help="Warn when a relative path is longer than this value",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=2,
        help="Warn when file nesting depth is greater than this value",
    )
    parser.add_argument(
        "--file-types",
        default="all",
        help="Comma-separated extensions to check, for example: html,md",
    )
    parser.add_argument(
        "--ignore-file",
        default=".filenameignore",
        help="Path to ignore file relative to root",
    )
    parser.add_argument(
        "--dotfile-mode",
        default="strip-leading-dot",
        choices=["strip-leading-dot", "ignore"],
        help="How to handle dot-prefixed names: strip-leading-dot or ignore",
    )
    parser.add_argument(
        "--allow-dates-in-file-names",
        type=parse_bool,
        default=False,
        help="Allow one date fragment in a filename stem (default: false)",
    )
    parser.add_argument(
        "--date-format",
        default=DEFAULT_DATE_FORMAT,
        help="Date format for allowed filename date fragments (default: %Y-%m-%d)",
    )

    args = parser.parse_args()
    if args.max_path_length < 1:
        print("::error::max-path-length must be at least 1")
        return 2
    if args.max_depth < 0:
        print("::error::max-depth must be at least 0")
        return 2

    root = Path(args.root).resolve()
    if not root.exists() or not root.is_dir():
        print(f"::error::root path does not exist or is not a directory: {root}")
        return 2

    try:
        date_pattern = build_date_pattern(args.date_format)
    except ValueError as error:
        print(f"::error::{error}")
        return 2

    file_types = parse_file_types(args.file_types)
    ignore_patterns = load_ignore_patterns(root, args.ignore_file)

    findings: list[Finding] = []
    checked_file_count = 0
    checked_directory_paths: set[str] = set()

    for dir_path, dir_names, file_names in os.walk(root):
        current_dir = Path(dir_path)

        kept_dirs: list[str] = []
        for directory in dir_names:
            if directory == ".git":
                continue
            if args.dotfile_mode == "ignore" and directory.startswith("."):
                continue
            full_dir = current_dir / directory
            rel_dir = relative_posix(full_dir, root)
            if is_ignored(rel_dir, ignore_patterns):
                continue
            kept_dirs.append(directory)
        dir_names[:] = kept_dirs

        for file_name in file_names:
            if args.dotfile_mode == "ignore" and file_name.startswith("."):
                continue

            file_path = current_dir / file_name
            rel_file = relative_posix(file_path, root)

            if is_ignored(rel_file, ignore_patterns):
                continue

            if file_types is not None:
                ext = file_path.suffix.lower().lstrip(".")
                if ext not in file_types:
                    continue

            checked_file_count += 1

            for issue in check_file_name(
                file_path,
                args.dotfile_mode,
                args.allow_dates_in_file_names,
                args.date_format,
                date_pattern,
            ):
                findings.append(Finding("error", rel_file, issue))

            parent = file_path.relative_to(root).parent
            if parent != Path("."):
                running = Path()
                for part in parent.parts:
                    running /= part
                    rel_dir = running.as_posix()
                    if rel_dir in checked_directory_paths:
                        continue
                    checked_directory_paths.add(rel_dir)

                    for issue in check_directory_name(part, args.dotfile_mode):
                        findings.append(Finding("error", rel_dir, issue))

                    if len(rel_dir) > args.max_path_length:
                        findings.append(
                            Finding(
                                "warning",
                                rel_dir,
                                f"directory path is {len(rel_dir)} characters long (limit: {args.max_path_length})",
                            )
                        )

            depth = len(file_path.relative_to(root).parts) - 1
            if depth > args.max_depth:
                findings.append(
                    Finding(
                        "warning",
                        rel_file,
                        f"file nesting depth is {depth} (limit: {args.max_depth})",
                    )
                )

            if len(rel_file) > args.max_path_length:
                findings.append(
                    Finding(
                        "warning",
                        rel_file,
                        f"file path is {len(rel_file)} characters long (limit: {args.max_path_length})",
                    )
                )

    error_count = 0
    warning_count = 0

    for finding in findings:
        if finding.severity == "error":
            error_count += 1
            print(f"::error file={finding.path}::{finding.message}")
        else:
            warning_count += 1
            print(f"::warning file={finding.path}::{finding.message}")

    error_groups = group_findings_by_path(findings, "error")
    warning_groups = group_findings_by_path(findings, "warning")

    print_grouped_findings("Failed Paths", "FAILED", error_groups)
    print_grouped_findings("Warning Paths", "WARN", warning_groups)

    append_step_summary(
        checked_file_count,
        error_count,
        warning_count,
        error_groups,
        warning_groups,
    )

    if checked_file_count == 0:
        print("::warning::No files matched the selected file-types filter.")

    print(
        f"Checked {checked_file_count} files. "
        f"Errors: {error_count}. Warnings: {warning_count}."
    )

    return 1 if error_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
