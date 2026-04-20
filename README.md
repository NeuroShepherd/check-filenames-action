# Check Filenames Action

Opinionated GitHub Action to validate file and folder naming conventions with an emphasis on adhering to website path naming conventions. See Google's [URL structure best practices](https://developers.google.com/search/docs/crawling-indexing/url-structure) for an overview.

## What It Checks

- Enforces lowercase kebab-case names
- Enforces letters and dashes only in names
- Optionally allows one date fragment in file stems
- Enforces lowercase-only file extensions
- Warns on long relative paths (default limit: 65)
- Warns on deep file nesting (default max depth: 2)
- Lets users filter by file types (for example: `html,md`)
- Supports ignore patterns via `.filenameignore`
- Supports configurable dotfile handling

## Naming Rule

Names must match:

- `^[a-z]+(?:-[a-z]+)*$`

This allows lowercase letters with single dashes between words.

Examples:

- Valid: `readme.md`, `my-folder/my-file.html`
- Invalid: `MyFile.md`, `my_file.md`, `my-file2.md`

Optional date mode:

- Enable `allow-dates-in-file-names: "true"` to allow one date fragment in each file stem.
- The default date format is `%Y-%m-%d`.
- Use `date-format` to change the expected format (for example `%Y%m%d` or `%d-%m-%Y`).

Examples when enabled with matching format:

- `2020-05-01-filename.html` with `%Y-%m-%d`
- `2022-12-filename.css` with `%Y-%m`
- `something-30-12-2025.md` with `%d-%m-%Y`
- `20220511-name.html` with `%Y%m%d`

## Inputs

- `max-path-length`: warn when path is longer than this value (default: `65`)
- `max-depth`: warn when nesting is deeper than this value (default: `2`)
- `file-types`: comma-separated extensions to check, or `all` (default: `all`)
- `ignore-file`: ignore file path relative to repository root (default: `.filenameignore`)
- `dotfile-mode`: dotfile handling mode, either `strip-leading-dot` or `ignore` (default: `strip-leading-dot`)
- `allow-dates-in-file-names`: allow one date fragment in file stems (default: `false`)
- `date-format`: date format for allowed filename date fragments (default: `%Y-%m-%d`)

## Usage

```yaml
name: Filename Checks

on:
  workflow_dispatch:
  pull_request:
  push:
    branches:
      - main

jobs:
  check-names:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Check filenames
        uses: NeuroShepherd/check-filenames-action@v1
        with:
          max-path-length: "65"
          max-depth: "2"
          file-types: "html,md"
          ignore-file: ".filenameignore"
          dotfile-mode: "strip-leading-dot"
          allow-dates-in-file-names: "false"
          date-format: "%Y-%m-%d"
```

Dotfile modes:

- `strip-leading-dot`: evaluate names after removing one leading `.`
- `ignore`: skip dot-prefixed files and directories entirely

## .filenameignore

Use `.filenameignore` in repository root to skip specific files or folders.

Supported patterns include exact names, globs, and folder prefixes.

Example:

```text
# Ignore one file
docs/legacy-file.md

# Ignore all markdown files in docs
docs/*.md

# Ignore a folder and everything under it
vendor/
```

## Exit Behavior

- Errors (naming violations) fail the workflow.
- Warnings (path length and depth) do not fail the workflow.

## Publishing To Marketplace

1. Push this repository to GitHub.
2. Tag a release, for example `v1.0.0`.
3. Create a major version tag `v1` that points to the latest v1 release.
4. Add clear branding in `action.yml`.
5. Publish the action by creating a GitHub release.

After release, users can reference `owner/repo@v1`.
