#!/usr/bin/env python3
"""Export, validate, and apply human line-break reviews for DFU quest QRC text."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

HEADER_RE = re.compile(
    r"^(QuestorOffer|RefuseQuest|AcceptQuest|QuestFail|QuestComplete|"
    r"RumorsDuringQuest|RumorsPostfailure|RumorsPostsuccess|"
    r"QuestorPostsuccess|QuestorPostfailure|QuestLogEntry|QuestTimeLapse|Message):"
    r"\s*(?:\[(\d+)\]|(\d+))?\s*$"
)
TOKEN_RE = re.compile(r"(?:==?[A-Za-z0-9.$]+_|_{1,4}[A-Za-z0-9.$]+_|%[A-Za-z0-9]+(?:-self)?)")
STRUCTURAL_RE = re.compile(r"<--->|%qdt|%qdat")
SYMBOLS_MARKER = "-- Symbols used in the QRC file:"
EDITORIAL_NOTE_RE = re.compile(r"^-\s*(?:moved|corrected|lowered|changed)\b", re.IGNORECASE)
APPROVED_STATUSES = {"완료", "승인", "approved", "done"}
MACRO_WIDTH = {
    "%pcn": 16, "%pcf": 10, "%pct": 14, "%ra": 10, "%reg": 14,
    "%rn": 14, "%rt": 12, "%g": 4, "%g1": 4, "%g2": 4,
    "%g2self": 8, "%g3": 4, "%g4": 4, "%G": 4, "%G1": 4,
    "%G2": 4, "%G2self": 8, "%G3": 4, "%G4": 4, "%god": 10,
    "%oth": 10, "%qdt": 24, "%qdat": 24,
}
CSV_COLUMNS = [
    "record_id", "category", "source_file", "quest_id", "key", "header",
    "english", "current_korean", "reviewed_korean", "status", "notes",
    "source_hash", "content_signature", "token_sequence",
    "structural_sequence", "current_lines", "current_max_width",
]
REQUIRED_COLUMNS = CSV_COLUMNS


@dataclass(frozen=True)
class Block:
    key: str
    header: str
    body: str
    trailer: str = ""


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")


def split_sections(text: str) -> tuple[str, str, str]:
    if "QRC:" not in text or "QBN:" not in text:
        raise ValueError("missing QRC: or QBN: section")
    pre, rest = text.split("QRC:", 1)
    qrc, qbn = rest.split("QBN:", 1)
    return pre + "QRC:\n", qrc.strip("\n"), "QBN:" + qbn


def split_qrc_suffix(qrc: str) -> tuple[str, str]:
    """Separate trailing symbol comments so they are never treated as message text."""
    marker = qrc.find(SYMBOLS_MARKER)
    if marker < 0:
        return qrc.rstrip("\n"), ""
    suffix_start = marker
    while suffix_start > 0 and qrc[suffix_start - 1] == "\n":
        suffix_start -= 1
    return qrc[:suffix_start].rstrip("\n"), qrc[suffix_start:]


def parse_blocks(qrc: str) -> list[Block]:
    lines = qrc.splitlines()
    starts = [i for i, line in enumerate(lines) if HEADER_RE.match(line)]
    blocks: list[Block] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(lines)
        header = lines[start]
        match = HEADER_RE.match(header)
        assert match is not None
        number = match.group(2) or match.group(3) or str(index)
        key = f"{match.group(1)}:{number}"
        body_lines = lines[start + 1:end]
        pos = len(body_lines) - 1
        while pos >= 0 and not body_lines[pos].strip():
            pos -= 1
        comment_end = pos
        while pos >= 0 and (
            body_lines[pos].lstrip().startswith("--")
            or EDITORIAL_NOTE_RE.match(body_lines[pos].strip())
        ):
            pos -= 1
        seen_comment = pos < comment_end
        if seen_comment:
            while pos >= 0 and not body_lines[pos].strip():
                pos -= 1
            trailer_start = pos + 1
            trailer_lines = body_lines[trailer_start:]
            body_lines = body_lines[:trailer_start]
        else:
            trailer_lines = []
        while body_lines and not body_lines[-1].strip():
            body_lines.pop()
        trailer = ("\n" + "\n".join(trailer_lines)) if trailer_lines else ""
        blocks.append(Block(key=key, header=header, body="\n".join(body_lines), trailer=trailer))
    return blocks


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_content(text: str) -> str:
    """Ignore only layout whitespace and flexible <ce> line markers."""
    without_ce = text.replace("<ce>", "")
    return re.sub(r"\s+", "", without_ce)


def sequence(pattern: re.Pattern[str], text: str) -> list[str]:
    return pattern.findall(text)


def char_width(char: str) -> int:
    if char == "\u2060" or unicodedata.combining(char):
        return 0
    if char == "\t":
        return 4
    if char.isspace():
        return 1
    return 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1


def token_width(token: str) -> int:
    if token in MACRO_WIDTH:
        return MACRO_WIDTH[token]
    if token.startswith("%"):
        return 8
    if token.startswith("="):
        return 7 if re.search(r"time|day|gold|reward|amount|count|part", token, re.I) else 12
    if token.startswith("____"):
        return 20
    if token.startswith("___"):
        return 18
    if token.startswith("__"):
        return 15
    if token.startswith("_"):
        return 14
    return sum(char_width(char) for char in token)


def visual_width(text: str) -> int:
    total = 0
    position = 0
    for match in TOKEN_RE.finditer(text):
        total += sum(char_width(char) for char in text[position:match.start()])
        total += token_width(match.group(0))
        position = match.end()
    return total + sum(char_width(char) for char in text[position:])


def body_metrics(body: str) -> tuple[int, int]:
    visible_lines = []
    for raw in body.splitlines():
        line = raw.strip()
        if line == "<--->":
            continue
        if line.startswith("<ce>"):
            line = line[4:]
        visible_lines.append(line)
    return len(visible_lines), max((visual_width(line) for line in visible_lines), default=0)


def centered_line_errors(body: str) -> list[str]:
    """Require every visible line in a centered panel to carry its own <ce> marker."""
    errors: list[str] = []
    for line_number, raw in enumerate(body.splitlines(), 1):
        line = raw.strip()
        if not line or line == "<--->":
            continue
        if not line.startswith("<ce>"):
            errors.append(f"centered panel line {line_number} is missing <ce>")
    return errors


def is_centered_panel(body: str) -> bool:
    """Return true only when every visible non-separator line is centered."""
    visible = [
        raw.strip() for raw in body.splitlines()
        if raw.strip() and raw.strip() != "<--->"
    ]
    return bool(visible) and all(line.startswith("<ce>") for line in visible)


def classify(block: Block) -> str:
    if block.key.startswith("QuestLogEntry:") or "%qdt" in block.body or "%qdat" in block.body:
        return "퀘스트 일지"
    if is_centered_panel(block.body):
        return "가운데 정렬 패널"
    return "일반 메시지"


def quest_ids(localized_dir: Path, requested: list[str]) -> list[str]:
    if requested:
        return sorted(dict.fromkeys(requested))
    return sorted(path.name.removesuffix("-LOC.txt") for path in localized_dir.glob("*-LOC.txt"))


def paired_paths(official_dir: Path, localized_dir: Path, quest_id: str) -> tuple[Path, Path]:
    return official_dir / f"{quest_id}.txt", localized_dir / f"{quest_id}-LOC.txt"


def verify_pair(quest_id: str, english: list[Block], korean: list[Block]) -> None:
    en_keys = [block.key for block in english]
    ko_keys = [block.key for block in korean]
    if en_keys != ko_keys:
        raise ValueError(f"{quest_id}: English/Korean QRC keys differ")


def make_record(quest_id: str, source_file: str, en: Block, ko: Block) -> dict[str, str | int]:
    lines, max_width = body_metrics(ko.body)
    return {
        "record_id": f"quest:{quest_id}:{ko.key}",
        "category": classify(ko),
        "source_file": source_file,
        "quest_id": quest_id,
        "key": ko.key,
        "header": ko.header,
        "english": en.body,
        "current_korean": ko.body,
        "reviewed_korean": ko.body,
        "status": "미검수",
        "notes": "",
        "source_hash": sha256_text(ko.body),
        "content_signature": sha256_text(canonical_content(ko.body)),
        "token_sequence": json.dumps(sequence(TOKEN_RE, ko.body), ensure_ascii=False),
        "structural_sequence": json.dumps(sequence(STRUCTURAL_RE, ko.body), ensure_ascii=False),
        "current_lines": lines,
        "current_max_width": max_width,
    }


def export_csv(args: argparse.Namespace) -> None:
    records: list[dict[str, str | int]] = []
    ids = quest_ids(args.localized_dir, args.quest_ids)
    for qid in ids:
        en_path, ko_path = paired_paths(args.official_dir, args.localized_dir, qid)
        if not en_path.is_file() or not ko_path.is_file():
            raise FileNotFoundError(f"missing pair for {qid}: {en_path} / {ko_path}")
        _, en_qrc, _ = split_sections(read_text(en_path))
        _, ko_qrc, _ = split_sections(read_text(ko_path))
        en_message_qrc, _ = split_qrc_suffix(en_qrc)
        ko_message_qrc, _ = split_qrc_suffix(ko_qrc)
        en_blocks, ko_blocks = parse_blocks(en_message_qrc), parse_blocks(ko_message_qrc)
        verify_pair(qid, en_blocks, ko_blocks)
        source_file = f"text/Quests/{ko_path.name}"
        for en, ko in zip(en_blocks, ko_blocks):
            if classify(ko) == "가운데 정렬 패널":
                source_errors = centered_line_errors(ko.body)
                if source_errors:
                    raise ValueError(f"{qid} {ko.key}: {source_errors[0]}")
            records.append(make_record(qid, source_file, en, ko))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    print(f"exported {len(ids)} quests / {len(records)} review rows -> {args.output}")


def load_sheet(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [name for name in REQUIRED_COLUMNS if name not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: sheet is missing columns: {', '.join(missing)}")
        rows = list(reader)
    seen: set[str] = set()
    for row in rows:
        record_id = row["record_id"]
        if not record_id:
            raise ValueError(f"{path}: empty record_id")
        if record_id in seen:
            raise ValueError(f"{path}: duplicate record_id: {record_id}")
        seen.add(record_id)
    return rows


def load_sheets(paths: Iterable[Path]) -> list[dict[str, str]]:
    """Combine category-tab CSV exports while rejecting duplicate review rows."""
    rows: list[dict[str, str]] = []
    locations: dict[str, Path] = {}
    for path in paths:
        for row in load_sheet(path):
            record_id = row["record_id"]
            previous = locations.get(record_id)
            if previous is not None:
                raise ValueError(
                    f"duplicate record_id across sheets: {record_id} ({previous} / {path})"
                )
            locations[record_id] = path
            rows.append(row)
    return rows


def approved(row: dict[str, str]) -> bool:
    return row["status"].strip().casefold() in APPROVED_STATUSES


def validate_review(row: dict[str, str], current: Block) -> list[str]:
    errors: list[str] = []
    reviewed = row["reviewed_korean"].rstrip()
    if not reviewed:
        return ["reviewed_korean is empty"]
    if row["source_hash"] != sha256_text(current.body):
        errors.append("source text changed after export; regenerate the sheet")
    if row["content_signature"] != sha256_text(canonical_content(reviewed)):
        errors.append("non-whitespace Korean content changed")
    expected_tokens = json.loads(row["token_sequence"] or "[]")
    if expected_tokens != sequence(TOKEN_RE, reviewed):
        errors.append("token sequence changed")
    expected_structural = json.loads(row["structural_sequence"] or "[]")
    if expected_structural != sequence(STRUCTURAL_RE, reviewed):
        errors.append("<--->/%qdt/%qdat sequence changed")
    if classify(current) == "가운데 정렬 패널":
        errors.extend(centered_line_errors(reviewed))
    return errors


def rows_by_quest(rows: Iterable[dict[str, str]]) -> dict[str, dict[str, dict[str, str]]]:
    grouped: dict[str, dict[str, dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["quest_id"], {})[row["key"]] = row
    return grouped


def validate_sheet(args: argparse.Namespace) -> None:
    rows = load_sheets(args.sheets)
    grouped = rows_by_quest(rows)
    errors: list[str] = []
    approved_count = 0
    for qid, quest_rows in sorted(grouped.items()):
        ko_path = args.localized_dir / f"{qid}-LOC.txt"
        if not ko_path.is_file():
            errors.append(f"{qid}: localized file not found")
            continue
        _, qrc, _ = split_sections(read_text(ko_path))
        message_qrc, _ = split_qrc_suffix(qrc)
        blocks = {block.key: block for block in parse_blocks(message_qrc)}
        for key, row in quest_rows.items():
            if not approved(row):
                continue
            approved_count += 1
            block = blocks.get(key)
            if block is None:
                errors.append(f"{qid} {key}: block no longer exists")
                continue
            errors.extend(f"{qid} {key}: {message}" for message in validate_review(row, block))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        raise SystemExit(1)
    print(f"validated {approved_count} approved review rows")


def apply_sheet(args: argparse.Namespace) -> None:
    rows = load_sheets(args.sheets)
    grouped = rows_by_quest(rows)
    errors: list[str] = []
    changed_files = 0
    applied_rows = 0
    report: list[dict[str, str | int]] = []

    for qid, quest_rows in sorted(grouped.items()):
        source = args.localized_dir / f"{qid}-LOC.txt"
        if not source.is_file():
            errors.append(f"{qid}: localized file not found")
            continue
        pre, qrc, qbn = split_sections(read_text(source))
        message_qrc, qrc_suffix = split_qrc_suffix(qrc)
        blocks = parse_blocks(message_qrc)
        rendered: list[str] = []
        file_applied = 0
        for block in blocks:
            row = quest_rows.get(block.key)
            body = block.body
            if row and approved(row):
                row_errors = validate_review(row, block)
                if row_errors:
                    errors.extend(f"{qid} {block.key}: {message}" for message in row_errors)
                else:
                    body = row["reviewed_korean"].rstrip()
                    file_applied += 1
                    applied_rows += 1
            rendered.append(block.header + "\n" + body + block.trailer)

        missing_keys = sorted(set(quest_rows) - {block.key for block in blocks})
        errors.extend(f"{qid} {key}: block no longer exists" for key in missing_keys if approved(quest_rows[key]))
        if file_applied:
            target = args.output_dir / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(pre + "\n\n".join(rendered) + qrc_suffix + "\n\n" + qbn, encoding="utf-8", newline="\n")
            changed_files += 1
            report.append({"quest_id": qid, "applied_rows": file_applied, "output": target.as_posix()})

    if errors:
        print("\n".join(errors), file=sys.stderr)
        raise SystemExit(1)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / "linebreak-review-apply-report.json"
    report_path.write_text(
        json.dumps({"changed_files": changed_files, "applied_rows": applied_rows, "files": report}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"applied {applied_rows} rows to {changed_files} files -> {args.output_dir}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("extract", help="export quest messages to a Google Sheets-compatible CSV")
    export.add_argument("--official-dir", type=Path, required=True)
    export.add_argument("--localized-dir", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("quest_ids", nargs="*")
    export.set_defaults(func=export_csv)

    check = sub.add_parser("validate-sheet", help="validate approved sheet rows without writing files")
    check.add_argument("--localized-dir", type=Path, required=True)
    check.add_argument("--sheet", dest="sheets", type=Path, nargs="+", required=True)
    check.set_defaults(func=validate_sheet)

    apply_cmd = sub.add_parser("apply", help="apply approved sheet rows to a separate output directory")
    apply_cmd.add_argument("--localized-dir", type=Path, required=True)
    apply_cmd.add_argument("--sheet", dest="sheets", type=Path, nargs="+", required=True)
    apply_cmd.add_argument("--output-dir", type=Path, required=True)
    apply_cmd.set_defaults(func=apply_sheet)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.func(args)
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
