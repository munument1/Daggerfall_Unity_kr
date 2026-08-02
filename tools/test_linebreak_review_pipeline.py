from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("linebreak_review_pipeline.py")

ENGLISH = """Messages: 1
Quest: TEST0001
DisplayName: Test
QRC:

Message:  1000
<ce>Hello _name_.
<ce>This is a test.
<--->
<ce>Second choice.

QBN:
variable _done_
"""

KOREAN = """Messages: 1
Quest: TEST0001
DisplayName: 시험
QRC:

Message:  1000
<ce>안녕하세요, _name_ 님.
<ce>줄바꿈 시험입니다.
<--->
<ce>두 번째 선택지입니다.

QBN:
variable _done_
"""


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.official = root / "official"
        self.localized = root / "localized"
        self.output = root / "review.csv"
        self.applied = root / "applied"
        self.official.mkdir()
        self.localized.mkdir()
        (self.official / "TEST0001.txt").write_text(ENGLISH, encoding="utf-8")
        (self.localized / "TEST0001-LOC.txt").write_text(KOREAN, encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args, expected=0):
        result = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], text=True, capture_output=True)
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        return result

    def extract(self):
        self.run_cli("extract", "--official-dir", self.official, "--localized-dir", self.localized, "--output", self.output)
        with self.output.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(1, len(rows))
        return rows

    def save(self, rows):
        with self.output.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    def test_linebreak_only_review_is_applied(self):
        rows = self.extract()
        rows[0]["status"] = "완료"
        rows[0]["reviewed_korean"] = "<ce>안녕하세요, _name_ 님. 줄바꿈\n<ce>시험입니다.\n<--->\n<ce>두 번째\n<ce>선택지입니다."
        self.save(rows)
        self.run_cli("validate-sheet", "--localized-dir", self.localized, "--sheet", self.output)
        self.run_cli("apply", "--localized-dir", self.localized, "--sheet", self.output, "--output-dir", self.applied)
        applied = (self.applied / "TEST0001-LOC.txt").read_text(encoding="utf-8")
        self.assertIn("<ce>두 번째\n<ce>선택지입니다.", applied)

    def test_content_change_is_rejected(self):
        rows = self.extract()
        rows[0]["status"] = "완료"
        rows[0]["reviewed_korean"] = rows[0]["reviewed_korean"].replace("시험", "검사")
        self.save(rows)
        result = self.run_cli("validate-sheet", "--localized-dir", self.localized, "--sheet", self.output, expected=1)
        self.assertIn("non-whitespace Korean content changed", result.stderr)

    def test_unapproved_rows_are_not_written(self):
        self.extract()
        self.run_cli("apply", "--localized-dir", self.localized, "--sheet", self.output, "--output-dir", self.applied)
        self.assertFalse((self.applied / "TEST0001-LOC.txt").exists())


if __name__ == "__main__":
    unittest.main()
