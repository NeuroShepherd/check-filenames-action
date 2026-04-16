#!/usr/bin/env python3

"""Opinionated filename and folder naming checks for GitHub Actions."""

from __future__ import annotations

import argparse
import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path
import re
import sys


VALID_NAME_PATTERN = re.compile(r"^[a-z]+(?:-[a-z]+)*$")
VALID_EXTENSION_PATTERN = re.compile(r"^[a-z]+$")


@dataclass
class Finding:
	severity: str
	path: str
	message: str


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
		patterns.append(pattern.replace("\\", "/").lstrip("./"))
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


def check_file_name(path: Path) -> list[str]:
	issues: list[str] = []
	stem = path.stem

	if not check_kebab_case(stem):
		issues.append("filename stem must use lowercase kebab-case with letters only")

	for suffix in path.suffixes:
		ext = suffix.lstrip(".")
		if not VALID_EXTENSION_PATTERN.fullmatch(ext):
			issues.append("file extension must use lowercase letters only")
			break

	return issues


def check_directory_name(name: str) -> list[str]:
	if check_kebab_case(name):
		return []
	return ["directory name must use lowercase kebab-case with letters only"]


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
			full_dir = current_dir / directory
			rel_dir = relative_posix(full_dir, root)
			if is_ignored(rel_dir, ignore_patterns):
				continue
			kept_dirs.append(directory)
		dir_names[:] = kept_dirs

		for file_name in file_names:
			file_path = current_dir / file_name
			rel_file = relative_posix(file_path, root)

			if is_ignored(rel_file, ignore_patterns):
				continue

			if file_types is not None:
				ext = file_path.suffix.lower().lstrip(".")
				if ext not in file_types:
					continue

			checked_file_count += 1

			for issue in check_file_name(file_path):
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

					for issue in check_directory_name(part):
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

	if checked_file_count == 0:
		print("::warning::No files matched the selected file-types filter.")

	print(
		f"Checked {checked_file_count} files. "
		f"Errors: {error_count}. Warnings: {warning_count}."
	)

	return 1 if error_count > 0 else 0


if __name__ == "__main__":
	sys.exit(main())
