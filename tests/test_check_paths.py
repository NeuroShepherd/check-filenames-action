import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "check-paths.py"


spec = importlib.util.spec_from_file_location("check_paths_module", SCRIPT_PATH)
check_paths = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = check_paths
spec.loader.exec_module(check_paths)


class ParseFileTypesTests(unittest.TestCase):
    def test_all_and_empty_map_to_none(self) -> None:
        self.assertIsNone(check_paths.parse_file_types(""))
        self.assertIsNone(check_paths.parse_file_types("all"))
        self.assertIsNone(check_paths.parse_file_types("*"))

    def test_mixed_separator_and_dot_prefix(self) -> None:
        result = check_paths.parse_file_types("html, .md;TXT")
        self.assertEqual(result, {"html", "md", "txt"})


class IgnorePatternTests(unittest.TestCase):
    def test_load_ignore_patterns_preserves_dot_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            ignore_file = root / ".filenameignore"
            ignore_file.write_text(
                "\n".join(
                    [
                        "# comment",
                        "./docs/*.md",
                        "/vendor/",
                        ".venv",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            patterns = check_paths.load_ignore_patterns(root, ".filenameignore")
            self.assertEqual(patterns, ["docs/*.md", "vendor/", ".venv"])

    def test_is_ignored_with_glob_and_folder_prefix(self) -> None:
        patterns = ["docs/*.md", "vendor/", ".venv"]

        self.assertTrue(check_paths.is_ignored("docs/readme.md", patterns))
        self.assertTrue(check_paths.is_ignored("vendor/lib/file.py", patterns))
        self.assertTrue(check_paths.is_ignored(".venv", patterns))
        self.assertFalse(check_paths.is_ignored("src/main.py", patterns))


class NameValidationTests(unittest.TestCase):
    def test_file_name_validation(self) -> None:
        good = check_paths.check_file_name(Path("good-file.md"), "strip-leading-dot")
        bad = check_paths.check_file_name(Path("bad_file.md"), "strip-leading-dot")

        self.assertEqual(good, [])
        self.assertEqual(
            bad,
            ["filename stem must use lowercase kebab-case with letters and dashes only"],
        )

    def test_dotfile_name_strip_mode(self) -> None:
        issues = check_paths.check_file_name(Path(".env"), "strip-leading-dot")
        self.assertEqual(issues, [])

    def test_directory_name_strip_mode(self) -> None:
        issues = check_paths.check_directory_name(".github", "strip-leading-dot")
        self.assertEqual(issues, [])


class CLITests(unittest.TestCase):
    def run_checker(self, root: Path, dotfile_mode: str) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(SCRIPT_PATH),
            "--root",
            str(root),
            "--file-types",
            "py",
            "--dotfile-mode",
            dotfile_mode,
        ]
        return subprocess.run(command, check=False, capture_output=True, text=True)

    def test_dotfile_mode_ignore_skips_dot_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".venv").mkdir()
            (root / ".venv" / "bad_file.py").write_text("x = 1\n", encoding="utf-8")
            (root / "good-folder").mkdir()
            (root / "good-folder" / "good-file.py").write_text("x = 1\n", encoding="utf-8")

            result = self.run_checker(root, "ignore")

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("Checked 1 files. Errors: 0. Warnings: 0.", result.stdout)

    def test_dotfile_mode_strip_leading_dot_validates_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".BadFolder").mkdir()
            (root / ".BadFolder" / "good-file.py").write_text("x = 1\n", encoding="utf-8")

            result = self.run_checker(root, "strip-leading-dot")

            self.assertEqual(result.returncode, 1, msg=result.stdout + result.stderr)
            self.assertIn("::error file=.BadFolder::", result.stdout)
            self.assertIn("::group::Failed Paths", result.stdout)


if __name__ == "__main__":
    unittest.main()
