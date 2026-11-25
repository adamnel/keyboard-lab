"""Keeps the repository small. Runs on every commit; a failure means delete something,
or change a limit here in the same commit and say why in its message."""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP_LEVEL = {
    ".githooks", ".gitignore", "AGENTS.md", "README.md", "keymap.txt", "pinned.txt",
    "docs", "firmware", "keyboard_lab", "recovery", "scripts", "tests",
}
PROSE = {"README.md": 200, "AGENTS.md": 200}  # the only prose files, and their word limits
PROSE_SUFFIXES = {".md", ".mdx", ".rst", ".adoc", ".org", ".txt", ".doc", ".docx", ".pdf", ".html"}
DATA_TEXT = {"keymap.txt", "pinned.txt"}
MAX_FILES = 32  # decision records are not counted; they are never deleted
MAX_AGENTS_LINES = 40
RECORD_NAME = r"docs/decisions/(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md"
RECORD_WORDS = 150  # body only
STATUS = r"proposed|accepted|rejected|deprecated|superseded by ADR-\d{4}"
FRONTMATTER = rf"---\nstatus: ({STATUS})\ndate: \d{{4}}-\d\d-\d\d\npaths:\n((?:  - \S+\n)+)---\n"
SECTIONS = ("## Context and Problem Statement", "## Considered Options", "## Decision Outcome")
MAX_CODE_LINE = 120


def files():
    """Tracked files plus new ones not yet ignored, so a stray file fails before it is staged."""
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    return [name for name in listed if (ROOT / name).exists()]


class Repository(unittest.TestCase):
    def test_nothing_new_at_the_top_level(self):
        self.assertEqual({name.split("/")[0] for name in files()} - TOP_LEVEL, set())

    def test_no_prose_beyond_the_two_short_documents(self):
        prose = {name for name in files() if Path(name).suffix.lower() in PROSE_SUFFIXES}
        records = {name for name in files() if re.fullmatch(RECORD_NAME, name)}
        self.assertEqual({name for name in files() if name.startswith("docs/")} - records, set())
        self.assertEqual(prose - set(PROSE) - DATA_TEXT - records, set())
        self.assertLessEqual(len((ROOT / "AGENTS.md").read_text().splitlines()), MAX_AGENTS_LINES)
        for name, limit in PROSE.items():
            self.assertLessEqual(len((ROOT / name).read_text().split()), limit, f"{name} is over {limit} words")

    def test_file_count_only_grows_on_purpose(self):
        self.assertLessEqual(len([name for name in files() if not name.startswith("docs/decisions/")]), MAX_FILES)

    def test_decision_records_are_short_valid_and_never_deleted(self):
        records = sorted(name for name in files() if re.fullmatch(RECORD_NAME, name))
        numbers = [int(re.fullmatch(RECORD_NAME, name)[1]) for name in records]
        self.assertEqual(numbers, list(range(1, len(records) + 1)), "records are numbered 0001.. with no gaps")
        for name in records:
            text = (ROOT / name).read_text()
            front = re.match(FRONTMATTER, text)
            self.assertIsNotNone(front, f"{name}: frontmatter needs status, date, then a paths list")
            body = text[front.end():]
            self.assertLessEqual(len(body.split()), RECORD_WORDS, f"{name} is over {RECORD_WORDS} words")
            for section in SECTIONS:
                self.assertIn(section, body, name)
            if front[1] == "accepted":
                for glob in re.findall(r"  - (\S+)", front[2]):
                    self.assertTrue(list(ROOT.glob(glob)), f"{name}: no file matches {glob}")

    def test_code_is_not_packed_into_long_lines(self):
        for name in files():
            if name.endswith((".py", ".swift")):
                longest = max(map(len, (ROOT / name).read_text().splitlines()), default=0)
                self.assertLessEqual(longest, MAX_CODE_LINE, name)
