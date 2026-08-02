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

-- Symbols used in the QRC file:
-- _name_ occurs 1 time.

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

-- Symbols used in the QRC file:
-- _name_ occurs 1 time.

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

    def test_centered_line_without_ce_is_rejected(self):
        rows = self.extract()
        rows[0]["status"] = "완료"
        rows[0]["reviewed_korean"] = rows[0]["reviewed_korean"].replace(
            "<ce>줄바꿈 시험입니다.", "줄바꿈 시험입니다."
        )
        self.save(rows)
        result = self.run_cli(
            "validate-sheet", "--localized-dir", self.localized, "--sheet", self.output, expected=1
        )
        self.assertIn("is missing <ce>", result.stderr)

    def test_symbol_comment_suffix_is_preserved(self):
        rows = self.extract()
        self.assertNotIn("Symbols used", rows[0]["current_korean"])
        rows[0]["status"] = "완료"
        self.save(rows)
        self.run_cli("apply", "--localized-dir", self.localized, "--sheet", self.output, "--output-dir", self.applied)
        applied = (self.applied / "TEST0001-LOC.txt").read_text(encoding="utf-8")
        self.assertIn("-- Symbols used in the QRC file:", applied)
        self.assertIn("-- _name_ occurs 1 time.", applied)

    def test_content_change_is_rejected(self):
        rows = self.extract()
        rows[0]["status"] = "완료"
        rows[0]["reviewed_korean"] = rows[0]["reviewed_korean"].replace("시험", "검사")
        self.save(rows)
        result = self.run_cli("validate-sheet", "--localized-dir", self.localized, "--sheet", self.output, expected=1)
        self.assertIn("non-whitespace Korean content changed", result.stderr)

    def test_multiple_tab_csvs_are_combined(self):
        rows = self.extract()
        rows[0]["status"] = "완료"
        self.save(rows)
        empty_tab = self.output.with_name("empty-tab.csv")
        with empty_tab.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
        self.run_cli(
            "validate-sheet", "--localized-dir", self.localized,
            "--sheet", self.output, empty_tab,
        )

    def test_duplicate_rows_across_tabs_are_rejected(self):
        rows = self.extract()
        duplicate_tab = self.output.with_name("duplicate-tab.csv")
        with duplicate_tab.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        result = self.run_cli(
            "validate-sheet", "--localized-dir", self.localized,
            "--sheet", self.output, duplicate_tab, expected=1,
        )
        self.assertIn("duplicate record_id across sheets", result.stderr)

    def test_unapproved_rows_are_not_written(self):
        self.extract()
        self.run_cli("apply", "--localized-dir", self.localized, "--sheet", self.output, "--output-dir", self.applied)
        self.assertFalse((self.applied / "TEST0001-LOC.txt").exists())

    def test_quest_time_lapse_header_is_exported(self):
        english = ENGLISH.replace("Messages: 1", "Messages: 2").replace(
            "\n-- Symbols used in the QRC file:",
            "\n\nQuestTimeLapse:  [1045]\n<ce>Time passes.\n\n-- Symbols used in the QRC file:",
        )
        korean = KOREAN.replace("Messages: 1", "Messages: 2").replace(
            "\n-- Symbols used in the QRC file:",
            "\n\nQuestTimeLapse:  [1045]\n<ce>시간이 흐른다.\n\n-- Symbols used in the QRC file:",
        )
        (self.official / "TEST0001.txt").write_text(english, encoding="utf-8")
        (self.localized / "TEST0001-LOC.txt").write_text(korean, encoding="utf-8")
        self.run_cli("extract", "--official-dir", self.official, "--localized-dir", self.localized, "--output", self.output)
        with self.output.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(["Message:1000", "QuestTimeLapse:1045"], [row["key"] for row in rows])

    def test_journal_with_centered_continue_marker_is_not_treated_as_centered_panel(self):
        english = ENGLISH.replace(
            "<ce>Hello _name_.\n<ce>This is a test.\n<--->\n<ce>Second choice.",
            "%qdt\nA journal letter.\n\n<ce>(Continue)",
        )
        korean = KOREAN.replace(
            "<ce>안녕하세요, _name_ 님.\n<ce>줄바꿈 시험입니다.\n<--->\n<ce>두 번째 선택지입니다.",
            "%qdt\n일지 편지입니다.\n\n<ce>(계속)",
        )
        (self.official / "TEST0001.txt").write_text(english, encoding="utf-8")
        (self.localized / "TEST0001-LOC.txt").write_text(korean, encoding="utf-8")
        rows = self.extract()
        self.assertEqual("퀘스트 일지", rows[0]["category"])

    def test_mixed_centered_and_plain_choices_are_general_message(self):
        english = ENGLISH.replace(
            "<ce>Hello _name_.\n<ce>This is a test.\n<--->\n<ce>Second choice.",
            "Plain choice.\n<--->\n<ce>Centered choice.",
        )
        korean = KOREAN.replace(
            "<ce>안녕하세요, _name_ 님.\n<ce>줄바꿈 시험입니다.\n<--->\n<ce>두 번째 선택지입니다.",
            "일반 선택지.\n<--->\n<ce>가운데 선택지.",
        )
        (self.official / "TEST0001.txt").write_text(english, encoding="utf-8")
        (self.localized / "TEST0001-LOC.txt").write_text(korean, encoding="utf-8")
        rows = self.extract()
        self.assertEqual("일반 메시지", rows[0]["category"])

    def test_trailing_developer_comment_is_excluded_and_preserved(self):
        english = ENGLISH.replace(
            "\n-- Symbols used in the QRC file:",
            "\n\n-- developer note\n\n-- Symbols used in the QRC file:",
        )
        korean = KOREAN.replace(
            "\n-- Symbols used in the QRC file:",
            "\n\n-- 개발자 주석\n\n-- Symbols used in the QRC file:",
        )
        (self.official / "TEST0001.txt").write_text(english, encoding="utf-8")
        (self.localized / "TEST0001-LOC.txt").write_text(korean, encoding="utf-8")
        rows = self.extract()
        self.assertNotIn("개발자 주석", rows[0]["current_korean"])
        rows[0]["status"] = "완료"
        self.save(rows)
        self.run_cli("apply", "--localized-dir", self.localized, "--sheet", self.output, "--output-dir", self.applied)
        applied = (self.applied / "TEST0001-LOC.txt").read_text(encoding="utf-8")
        self.assertIn("-- 개발자 주석", applied)

    def test_single_hyphen_editorial_note_is_excluded_and_preserved(self):
        english = ENGLISH.replace(
            "\n-- Symbols used in the QRC file:",
            "\n\n-moved line down from %qdt line.\n\n-- Symbols used in the QRC file:",
        )
        korean = KOREAN.replace(
            "\n-- Symbols used in the QRC file:",
            "\n\n-moved line down from %qdt line.\n\n-- Symbols used in the QRC file:",
        )
        (self.official / "TEST0001.txt").write_text(english, encoding="utf-8")
        (self.localized / "TEST0001-LOC.txt").write_text(korean, encoding="utf-8")
        rows = self.extract()
        self.assertNotIn("moved line down", rows[0]["current_korean"])
        rows[0]["status"] = "완료"
        self.save(rows)
        self.run_cli("apply", "--localized-dir", self.localized, "--sheet", self.output, "--output-dir", self.applied)
        applied = (self.applied / "TEST0001-LOC.txt").read_text(encoding="utf-8")
        self.assertIn("-moved line down from %qdt line.", applied)

    def test_extended_token_forms_are_preserved(self):
        english = ENGLISH.replace("_name_", "____place_").replace("Second choice.", "==giver_ choice.")
        korean = KOREAN.replace("_name_", "____place_").replace("두 번째 선택지입니다.", "==giver_ 선택지입니다.")
        (self.official / "TEST0001.txt").write_text(english, encoding="utf-8")
        (self.localized / "TEST0001-LOC.txt").write_text(korean, encoding="utf-8")
        rows = self.extract()
        rows[0]["status"] = "완료"
        rows[0]["reviewed_korean"] = rows[0]["reviewed_korean"].replace("____place_", "___place_")
        self.save(rows)
        result = self.run_cli("validate-sheet", "--localized-dir", self.localized, "--sheet", self.output, expected=1)
        self.assertIn("token sequence changed", result.stderr)

    def test_generated_warning_column_is_optional(self):
        rows = self.extract()
        with self.output.open("w", encoding="utf-8-sig", newline="") as handle:
            fieldnames = list(rows[0].keys()) + ["자동 경고"]
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                row["자동 경고"] = ""
                writer.writerow(row)
        self.run_cli("validate-sheet", "--localized-dir", self.localized, "--sheet", self.output)


if __name__ == "__main__":
    unittest.main()
