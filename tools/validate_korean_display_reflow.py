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

BAD_ENDINGS = (
    '의', '와', '과', '하며', '하고', '해서', '있는', '없는', '한', '할', '될', '된',
    '하는', '했던', '이라는', '라는', '이라고', '위한', '대한', '관한', '같은', '다른',
    '새', '세', '두', '첫', '마지막', '해야', '한다면', '이라면', '인데', '지만',
    '아서', '어서', '므로', '니까', '으며', '면서', '는데', '라고', '려고', '도록',
    '기에', '길래', '더니', '다가', '거나', '든지', '고서', '하고서', '해서는',
    '하면서', '보면', '라면',
)
BAD_START_WORDS = {
    '것', '것을', '것이', '것은', '수', '수가', '수를', '데', '곳', '사람', '물건',
    '작품', '때', '뒤', '후', '전', '중', '뿐', '만큼', '정도', '모양', '셈', '바',
    '줄', '채', '벡터', '목록', '도서관', '전문가', '연구', '결과', '위치', '구멍',
    '영지', '왕실', '길드', '성', '왕', '여왕', '공주', '왕자', '마법사', '사람들',
    '임무', '문제', '중인', '중인데', '중입니다', '겁니다', '것입니다', '것이다',
    '것이었다', '있다', '있었다', '있습니다', '없다', '없었다', '없습니다', '된다',
    '됩니다', '주십시오', '주세요', '주시겠습니까', '드리겠습니다', '뿐입니다',
    '때문입니다',
}
COMMAND_RE = re.compile(
    r'^(?:Item|Person|Place|Clock|Foe|variable|task:|when |start |end |say |log |give '
    r'|create |clicked |toting |killed |injured |prompt |have |clear |reveal |place '
    r'|add |change |make |restore |unset |stop |restrain |remove |clicked)\b'
)

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


def boundary_is_bad(previous: str, following: str) -> bool:
    clean_previous = re.sub(r'["\'”’」』】)>]+$', '', previous)
    clean_following = re.sub(r'^["\'“‘「『【(<]+', '', following)
    clean_following = re.sub(r'["\'”’」』】)>.,;:!?，。！？；：]+$', '', clean_following)
    following_stem = re.sub(
        r'(?:은|는|이|가|을|를|의|에게|께|도|만|뿐|와|과|로|으로|에서|부터|까지)$',
        '',
        clean_following,
    )
    if clean_previous.endswith(('.', '!', '?', '。', '！', '？', '…')):
        return False
    if clean_previous.endswith(BAD_ENDINGS):
        return True
    if clean_previous in {'그', '이', '저', '어떤', '모든', '각', '몇', '여러', '직접'}:
        return True
    if clean_following in BAD_START_WORDS or following_stem in BAD_START_WORDS:
        return True
    if clean_following.startswith(tuple(',.;:!?)]}，。！？；：')):
        return True
    return False


def plain_qrc_prose(line: str) -> bool:
    value = line.strip()
    if not value or HEADER_RE.match(value):
        return False
    if value.startswith(('<', '%', '--', '[')) or value in {'QRC:', 'QBN:'}:
        return False
    if COMMAND_RE.match(value):
        return False
    return True


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

        # Independent readability audit: detect split modifiers/noun phrases and
        # short orphan fragments even when every individual line is under width.
        for index in range(len(current_lines) - 1):
            first, second = current_lines[index], current_lines[index + 1]
            first_value = first[4:] if first.startswith('<ce>') else first
            second_value = second[4:] if second.startswith('<ce>') else second
            centered_pair = (
                first.startswith('<ce>') and second.startswith('<ce>')
                and first.strip() != '<ce>' and second.strip() != '<ce>'
            )
            prose_pair = plain_qrc_prose(first) and plain_qrc_prose(second)
            if not (centered_pair or prose_pair):
                continue
            first_words = first_value.split()
            second_words = second_value.split()
            if not first_words or not second_words:
                continue
            # Known intentional comic repetition; retained deliberately.
            if qid == 'C0B00Y02' and '친절하고' in first_value and '친절하고' in second_value:
                continue
            if boundary_is_bad(first_words[-1], second_words[0]):
                blockers.append({
                    'type': 'unnatural-line-boundary',
                    'quest': qid,
                    'line': index + 1,
                    'before': first_value,
                    'after': second_value,
                })
            # Closing quotes/brackets can follow sentence punctuation. Strip only
            # those closers before deciding whether a short line is an orphan.
            terminal_value = re.sub(r'[\"\'”’」』】)>]+$', '', first_value.rstrip())
            if (
                display_width(first_value) < 18
                and not terminal_value.endswith(('.', '!', '?', '。', '！', '？', '…', ':', '：'))
            ):
                blockers.append({
                    'type': 'short-orphan-line',
                    'quest': qid,
                    'line': index + 1,
                    'text': first_value,
                })

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
            'readability_boundaries': 'passed' if not any(x['type'] in {'unnatural-line-boundary', 'short-orphan-line'} for x in blockers) else 'failed',
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
