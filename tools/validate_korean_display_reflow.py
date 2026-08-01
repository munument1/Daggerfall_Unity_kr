#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

TOKEN_RE = re.compile(r'(?:_{1,3}[A-Za-z0-9.$]+_|=[A-Za-z0-9.$]+_|%[A-Za-z0-9]+)')
UPPER_G_RE = re.compile(r'%G(2self|[1234]?)')
HEADER_RE = re.compile(r'^(?:QuestorOffer|RefuseQuest|AcceptQuest|QuestFail|QuestComplete|RumorsDuringQuest|RumorsPostfailure|RumorsPostsuccess|QuestorPostsuccess|QuestorPostfailure|QuestLogEntry|QuestTimeLapse|Message)\s*:')
BOOK_FORMAT_RE = re.compile(r'\[/[^]]+\]')
TIME_RE = re.compile(r'^\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}$')

MACRO_WIDTH = {
    '%pcn': 16, '%pcf': 10, '%pct': 14, '%ra': 10, '%reg': 14,
    '%g': 4, '%g1': 4, '%g2': 4, '%g2self': 8, '%g3': 4, '%g4': 4,
    '%qdt': 24, '%qdat': 24,
}


def char_width(ch: str) -> int:
    if ch.isspace():
        return 1
    return 2 if unicodedata.east_asian_width(ch) in {'W', 'F'} else 1


def token_width(token: str) -> int:
    if token in MACRO_WIDTH:
        return MACRO_WIDTH[token]
    if token.startswith('%'):
        return 8
    if token.startswith('='):
        return 8
    if token.startswith('___'):
        return 18
    if token.startswith('__'):
        return 15
    return 14


def display_width(text: str) -> int:
    total = 0
    pos = 0
    for match in TOKEN_RE.finditer(text):
        total += sum(char_width(ch) for ch in text[pos:match.start()])
        total += token_width(match.group(0))
        pos = match.end()
    total += sum(char_width(ch) for ch in text[pos:])
    return total


def normalized_tokens(text: str) -> list[str]:
    return [UPPER_G_RE.sub(lambda m: '%g' + m.group(1), token) for token in TOKEN_RE.findall(text)]


def qrc_qbn(text: str) -> tuple[str, str]:
    qrc_marker = '\nQRC:\n'
    qbn_marker = '\nQBN:\n'
    qrc_start = text.index(qrc_marker) + len(qrc_marker)
    qbn_start = text.index(qbn_marker)
    return text[qrc_start:qbn_start], text[qbn_start + len(qbn_marker):]


def headers(qrc: str) -> list[str]:
    return [line for line in qrc.splitlines() if HEADER_RE.match(line)]


def validate(root: Path, baseline: Path) -> dict:
    text = root / 'text'
    base_text = baseline / 'text'
    quest_dir = text / 'Quests'
    quest_ids = sorted(p.name[:-8] for p in quest_dir.glob('*-LOC.txt'))
    books = sorted((text / 'Books').glob('BOK*-LOC.txt'))
    blockers: list[dict] = []
    notes: list[dict] = []
    message_blocks = 0
    centered_lines_before = 0
    centered_lines_after = 0
    journal_lines_before = 0
    journal_lines_after = 0
    changed_root_quests = 0
    changed_books = 0

    for qid in quest_ids:
        current = text / f'{qid}-LOC.txt'
        mirror = quest_dir / f'{qid}-LOC.txt'
        base = base_text / f'{qid}-LOC.txt'
        if not current.exists() or not mirror.exists() or not base.exists():
            blockers.append({'type': 'missing-quest-file', 'quest': qid})
            continue
        if current.read_bytes() != mirror.read_bytes():
            blockers.append({'type': 'root-mirror-mismatch', 'quest': qid})
        current_text = current.read_text(encoding='utf-8-sig')
        base_value = base.read_text(encoding='utf-8-sig')
        if current_text != base_value:
            changed_root_quests += 1
        try:
            current_qrc, current_qbn = qrc_qbn(current_text)
            base_qrc, base_qbn = qrc_qbn(base_value)
        except ValueError:
            blockers.append({'type': 'missing-qrc-qbn', 'quest': qid})
            continue
        if current_qbn != base_qbn:
            blockers.append({'type': 'qbn-changed', 'quest': qid})
        current_headers = headers(current_qrc)
        base_headers = headers(base_qrc)
        message_blocks += len(current_headers)
        if current_headers != base_headers:
            blockers.append({'type': 'message-header-order-changed', 'quest': qid})
        if normalized_tokens(current_qrc) != normalized_tokens(base_qrc):
            blockers.append({'type': 'macro-token-order-changed', 'quest': qid})
        for marker in ('<--->', '%qdt', '%qdat'):
            if current_qrc.count(marker) != base_qrc.count(marker):
                blockers.append({'type': 'control-marker-count-changed', 'quest': qid, 'marker': marker})
        if '[undefined]' in current_text:
            blockers.append({'type': 'literal-undefined', 'quest': qid})
        if UPPER_G_RE.search(current_qrc):
            blockers.append({'type': 'uppercase-gender-macro-remains', 'quest': qid})

        base_lines = base_qrc.splitlines()
        current_lines = current_qrc.splitlines()
        centered_lines_before += sum(line.startswith('<ce>') and line.strip() != '<ce>' for line in base_lines)
        centered_lines_after += sum(line.startswith('<ce>') and line.strip() != '<ce>' for line in current_lines)
        journal_lines_before += sum(bool(line.strip()) for line in base_lines if line.startswith(('%qdt', '%qdat')))
        journal_lines_after += sum(bool(line.strip()) for line in current_lines if line.startswith(('%qdt', '%qdat')))

        in_journal = False
        for number, line in enumerate(current_lines, 1):
            if HEADER_RE.match(line) or not line.strip():
                in_journal = False
            if line.startswith(('%qdt', '%qdat')):
                in_journal = True
                prose = re.sub(r'^%(?:qdt|qdat):?\s*', '', line)
                if display_width(prose) > 60:
                    blockers.append({'type': 'journal-first-line-over-width', 'quest': qid, 'line': number, 'width': display_width(prose)})
            elif line.startswith('<ce>') and line.strip() != '<ce>':
                prose = line[4:]
                if display_width(prose) > 66:
                    blockers.append({'type': 'centered-line-over-width', 'quest': qid, 'line': number, 'width': display_width(prose)})
            elif in_journal and line.strip():
                if display_width(line) > 78:
                    blockers.append({'type': 'journal-line-over-width', 'quest': qid, 'line': number, 'width': display_width(line)})

    for book in books:
        base = baseline / 'text' / 'Books' / book.name
        if not base.exists():
            blockers.append({'type': 'missing-baseline-book', 'book': book.name})
            continue
        current_text = book.read_text(encoding='utf-8-sig')
        base_value = base.read_text(encoding='utf-8-sig')
        if current_text != base_value:
            changed_books += 1
        current_meta, _, current_content = current_text.partition('\nContent:\n')
        base_meta, _, base_content = base_value.partition('\nContent:\n')
        if current_meta != base_meta:
            blockers.append({'type': 'book-metadata-changed', 'book': book.name})
        if BOOK_FORMAT_RE.findall(current_content) != BOOK_FORMAT_RE.findall(base_content):
            blockers.append({'type': 'book-format-token-order-changed', 'book': book.name})
        if normalized_tokens(current_content) != normalized_tokens(base_content):
            blockers.append({'type': 'book-macro-token-order-changed', 'book': book.name})
        if '[undefined]' in current_text:
            blockers.append({'type': 'literal-undefined', 'book': book.name})

    # Unchanged release areas are still checked for basic parse integrity.
    biogs = sorted((root / 'BIOGs').glob('BIOG??T0.TXT'))
    for path in biogs:
        data = path.read_bytes().replace(b'\r\n', b'\n')
        if not (data.endswith(b'\n\n') or data.rstrip(b'\n').endswith(b'\x1a')):
            blockers.append({'type': 'biog-terminator', 'file': path.name})
        if len(re.findall(r'(?m)^\d+\.\s', data.decode('utf-8-sig'))) != 12:
            blockers.append({'type': 'biog-question-count', 'file': path.name})

    srt_files = sorted((root / '0' / '0').glob('*.srt'))
    cue_count = 0
    for path in srt_files:
        chunks = re.split(r'\n\s*\n', path.read_text(encoding='utf-8-sig').replace('\r\n', '\n').strip())
        for expected, chunk in enumerate(chunks, 1):
            lines = chunk.splitlines()
            if len(lines) < 3 or not lines[0].isdigit() or not TIME_RE.match(lines[1]):
                blockers.append({'type': 'srt-structure', 'file': path.name, 'cue': expected})
            cue_count += 1

    try:
        json.loads((root / 'text' / 'NameGen.txt').read_text(encoding='utf-8-sig'))
    except Exception as exc:
        blockers.append({'type': 'namegen-json', 'error': str(exc)})

    # This repeated phrase is an intentional joke, not a malformed break.
    notes.append({'type': 'intentional-repetition', 'file': 'C0B00Y02-LOC.txt', 'message': 'repeated 친절하고 wording retained'})

    return {
        'scope': 'Daggerfall Unity Korean display reflow validation',
        'baseline_commit': 'c3d0b83e6f62ec7ea1fe5d68718d1fe3dd2f7c48',
        'official_reference': {'version': 'Daggerfall Unity v1.1.1', 'commit': '81e89e90c27bc3c1a7a61871e545fad129174dec'},
        'summary': {
            'quest_files': len(quest_ids),
            'quest_message_blocks': message_blocks,
            'quest_loc_files': len(quest_ids) * 2,
            'changed_root_quests': changed_root_quests,
            'changed_quest_loc_files': changed_root_quests * 2,
            'books': len(books),
            'changed_books': changed_books,
            'biogs': len(biogs),
            'subtitle_files': len(srt_files),
            'subtitle_cues': cue_count,
            'centered_lines_before': centered_lines_before,
            'centered_lines_after': centered_lines_after,
            'blocking_errors': len(blockers),
        },
        'checks': {
            'quest_headers_and_order': 'passed' if not any(x['type'] == 'message-header-order-changed' for x in blockers) else 'failed',
            'quest_macro_token_order': 'passed' if not any(x['type'] == 'macro-token-order-changed' for x in blockers) else 'failed',
            'quest_qbn_exact': 'passed' if not any(x['type'] == 'qbn-changed' for x in blockers) else 'failed',
            'quest_root_mirror': 'passed' if not any(x['type'] == 'root-mirror-mismatch' for x in blockers) else 'failed',
            'runtime_undefined_absent': 'passed' if not any(x['type'] == 'literal-undefined' for x in blockers) else 'failed',
            'uppercase_gender_macros_absent': 'passed' if not any(x['type'] == 'uppercase-gender-macro-remains' for x in blockers) else 'failed',
            'display_width_limits': 'passed' if not any('over-width' in x['type'] for x in blockers) else 'failed',
            'book_metadata_and_format_tokens': 'passed' if not any(x['type'].startswith('book-') for x in blockers) else 'failed',
            'biog_srt_namegen': 'passed' if not any(x['type'].startswith(('biog-', 'srt-', 'namegen-')) for x in blockers) else 'failed',
        },
        'notes': notes,
        'blockers': blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = validate(args.root.resolve(), args.baseline.resolve())
    output = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.report:
        args.report.write_text(output, encoding='utf-8')
    print(json.dumps(report['summary'], ensure_ascii=False, indent=2))
    if report['blockers']:
        print(json.dumps(report['blockers'][:50], ensure_ascii=False, indent=2))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
