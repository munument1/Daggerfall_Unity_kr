#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Sequence

TOKEN_RE = re.compile(r'(?:_{1,3}[A-Za-z0-9.$]+_|=[A-Za-z0-9.$]+_|%[A-Za-z0-9]+)')
UPPER_G_RE = re.compile(r'%G(2self|[1234]?)')
HEADER_RE = re.compile(r'^(?:QuestorOffer|RefuseQuest|AcceptQuest|QuestFail|QuestComplete|RumorsDuringQuest|RumorsPostfailure|RumorsPostsuccess|QuestorPostsuccess|QuestorPostfailure|QuestLogEntry|QuestTimeLapse|Message)\s*:')
FORMAT_ONLY_RE = re.compile(r'^\s*(?:<[-]+>|<ce>|%qdt:?|\[/[^]]+\]|\[[^]]+\])\s*$')
BOOK_FORMAT_RE = re.compile(r'^\s*\[/[^]]+\]')

# Korean phrase-break heuristics. These are deliberately conservative.
BAD_ENDINGS = (
    # Possessives, conjunctions, connective endings, and adnominal forms should
    # normally stay with the following noun/clause. Subject/object particles are
    # intentionally excluded: a break after a complete noun phrase is often fine.
    '의', '와', '과', '하며', '하고', '해서',
    '있는', '없는', '한', '할', '될', '된', '하는', '했던', '이라는', '라는', '이라고',
    '위한', '대한', '관한', '같은', '다른', '새', '세', '두', '첫', '마지막',
    '해야', '한다면', '이라면', '인데', '지만', '아서', '어서', '므로', '니까',
    '으며', '면서', '는데', '라고', '려고', '도록', '기에', '길래', '더니', '다가',
    '거나', '든지', '고서', '하고서', '해서는', '하면서', '보면', '라면',
)
BAD_START_WORDS = {
    '것', '것을', '것이', '것은', '수', '수가', '수를', '데', '곳', '사람', '물건', '작품',
    '때', '뒤', '후', '전', '중', '뿐', '만큼', '정도', '모양', '셈', '바', '줄', '채',
    '벡터', '목록', '도서관', '전문가', '연구', '결과', '위치', '구멍', '영지', '왕실',
    '길드', '성', '왕', '여왕', '공주', '왕자', '마법사', '사람들', '임무', '문제',
    '중', '중인', '중인데', '중입니다', '겁니다', '것입니다', '것이다', '것이었다',
    '있다', '있었다', '있습니다', '없다', '없었다', '없습니다', '된다', '됩니다',
    '주십시오', '주세요', '주시겠습니까', '드리겠습니다', '뿐입니다', '때문입니다',
}
PUNCT_STRONG = tuple('.!?…。！？…')
PUNCT_MEDIUM = tuple(',;:，；：')

MACRO_WIDTH = {
    '%pcn': 16, '%pcf': 10, '%pct': 14, '%ra': 10, '%reg': 14, '%rn': 14, '%rt': 12,
    '%g': 4, '%g1': 4, '%g2': 4, '%g2self': 8, '%g3': 4, '%g4': 4,
    '%G': 4, '%G1': 4, '%G2': 4, '%G2self': 8, '%G3': 4, '%G4': 4,
    '%god': 10, '%oth': 10, '%qdt': 24, '%qdat': 24,
}


# Small, screenshot-confirmed typos found while reviewing reflow output. Keep this
# list explicit so the display-QA pass does not silently become another translation
# rewrite.
TEXT_FIXES: dict[str, tuple[tuple[str, str], ...]] = {
    'N0B00Y17-LOC.txt': (
        ('나타나는면 흐름선', '나타나는 면 흐름선'),
        ('그럼에도이 _item_', '그럼에도 이 _item_'),
        ('사망 이후이 작품', '사망 이후 이 작품'),
    ),
    'S0000999-LOC.txt': (
        ('그 편지을 알아낸다면', '그 편지를 알아낸다면'),
        ('리산더스와과에 관한된 최근 사건', '리산더스와 관련된 최근 사건'),
    ),
}

@dataclass
class Change:
    path: str
    centered_blocks: int = 0
    journal_blocks: int = 0
    prose_blocks: int = 0
    book_paragraphs: int = 0
    uppercase_g: int = 0
    removed_trailing_blank_ce: int = 0
    textual_fixes: int = 0


def char_width(ch: str) -> int:
    if ch == '\t':
        return 4
    if ch.isspace():
        return 1
    if unicodedata.east_asian_width(ch) in {'W', 'F'}:
        return 2
    return 1


def token_width(token: str) -> int:
    if token in MACRO_WIDTH:
        return MACRO_WIDTH[token]
    if token.startswith('%'):
        return 8
    if token.startswith('='):
        # Timers and numeric substitutions are usually short.
        if re.search(r'time|day|gold|reward|amount|count|part', token, re.I):
            return 6
        return 12
    if token.startswith('___'):
        return 18  # province/location + building/dungeon names
    if token.startswith('__'):
        return 15
    if token.startswith('_'):
        return 14
    return sum(char_width(c) for c in token)


def display_width(text: str) -> int:
    total = 0
    pos = 0
    for m in TOKEN_RE.finditer(text):
        total += sum(char_width(c) for c in text[pos:m.start()])
        total += token_width(m.group(0))
        pos = m.end()
    total += sum(char_width(c) for c in text[pos:])
    return total


def words(text: str) -> list[str]:
    # Macros remain attached to their particles so they cannot be split internally.
    return re.findall(r'\S+', re.sub(r'\s+', ' ', text.strip()))


def break_penalty(prev_word: str, next_word: str | None, line_width: int, cap: int, is_last: bool) -> float:
    cost = (cap - line_width) ** 2
    if is_last:
        cost *= 0.28
        if line_width < min(18, cap * 0.34):
            cost += 650
    elif line_width < min(24, cap * 0.42):
        cost += 900

    clean_prev = re.sub(r'[\"\'”’」』】)>]+$', '', prev_word)
    clean_next = re.sub(r'^[\"\'“‘「『【(<]+', '', next_word or '')
    next_stem = re.sub(r'(?:은|는|이|가|을|를|의|에게|께|도|만|뿐|와|과|로|으로|에서|부터|까지)$', '', clean_next)

    if clean_prev.endswith(PUNCT_STRONG):
        cost -= 260
    elif clean_prev.endswith(PUNCT_MEDIUM):
        cost -= 70

    if not clean_prev.endswith(PUNCT_STRONG):
        if clean_prev.endswith(BAD_ENDINGS):
            cost += 520
        if clean_next in BAD_START_WORDS or next_stem in BAD_START_WORDS:
            cost += 540
        if clean_next and clean_next[0] in ',.;:!?)]}，。！？；：':
            cost += 1000

    # Avoid splitting a dynamic name from a following noun or honorific.
    if TOKEN_RE.fullmatch(clean_prev) and next_stem in {'님', '씨', '경', '왕', '여왕', '전문가', '마법사', '길드', '도서관'}:
        cost += 900
    if next_stem in {'왕', '여왕', '공주', '왕자', '경', '길드', '도서관', '사람들', '임무', '전문가'}:
        cost += 620
    if TOKEN_RE.search(clean_prev) and TOKEN_RE.search(clean_next):
        cost += 600
    if next_word and TOKEN_RE.fullmatch(re.sub(r'[은는이가을를의에게도만뿐와과로으로]+$', '', clean_next)):
        cost += 500
    return cost


def optimal_wrap(text: str, caps: Sequence[int]) -> list[str]:
    ws = words(text)
    if not ws:
        return ['']
    # Never split a complete sentence that already fits. The optimizer otherwise
    # tends to balance short Korean sentences into two unnecessary half-lines.
    if display_width(' '.join(ws)) <= caps[0]:
        return [' '.join(ws)]
    n = len(ws)
    # dp[(i, line_class)] = (cost, lines). line_class 0 = first cap, 1 = subsequent cap.
    from functools import lru_cache

    @lru_cache(None)
    def solve(i: int, line_no: int):
        if i >= n:
            return 0.0, ()
        cap = caps[min(line_no, len(caps) - 1)]
        best = None
        line = ''
        for j in range(i, n):
            candidate = ws[j] if not line else f'{line} {ws[j]}'
            width = display_width(candidate)
            if width > cap and j > i:
                break
            if width > cap * 1.22 and j == i:
                # A single dynamic token can exceed the estimate; keep it intact.
                pass
            next_word = ws[j + 1] if j + 1 < n else None
            rest_cost, rest_lines = solve(j + 1, min(line_no + 1, len(caps) - 1))
            cost = break_penalty(ws[j], next_word, width, cap, j + 1 == n) + rest_cost
            candidate_result = (cost, (candidate,) + rest_lines)
            if best is None or candidate_result[0] < best[0]:
                best = candidate_result
            line = candidate
        assert best is not None
        return best

    return list(solve(0, 0)[1])






def boundary_is_bad(prev_word: str, next_word: str | None) -> bool:
    if not next_word:
        return False
    clean_prev = re.sub(r'[\"\'”’」』】)>]+$', '', prev_word)
    clean_next = re.sub(r'^[\"\'“‘「『【(<]+', '', next_word)
    clean_next = re.sub(r'[\"\'”’」』】)>.,;:!?，。！？；：]+$', '', clean_next)
    next_stem = re.sub(r'(?:은|는|이|가|을|를|의|에게|께|도|만|뿐|와|과|로|으로|에서|부터|까지)$', '', clean_next)
    if clean_prev.endswith(PUNCT_STRONG):
        return False
    if clean_prev.endswith(BAD_ENDINGS):
        return True
    if clean_prev in {'그', '이', '저', '어떤', '모든', '각', '몇', '여러', '직접'}:
        return True
    if clean_next in BAD_START_WORDS or next_stem in BAD_START_WORDS:
        return True
    if clean_next.startswith(tuple(',.;:!?)]}，。！？；：')):
        return True
    if TOKEN_RE.fullmatch(clean_prev) and next_stem in {'님', '씨', '경', '왕', '여왕', '전문가', '마법사', '길드', '도서관'}:
        return True
    return False


def greedy_wrap(text: str, caps: Sequence[int]) -> list[str]:
    """Fill Korean UI lines left-to-right, then back off bad phrase breaks."""
    ws = words(text)
    if not ws:
        return ['']
    out: list[str] = []
    i = 0
    line_no = 0
    while i < len(ws):
        cap = caps[min(line_no, len(caps) - 1)]
        j = i
        best = i + 1
        while j < len(ws):
            candidate = ' '.join(ws[i:j + 1])
            if display_width(candidate) <= cap or j == i:
                best = j + 1
                j += 1
            else:
                break
        # Back up over connective endings, determiners, and inseparable noun phrases.
        while best > i + 1 and best < len(ws) and boundary_is_bad(ws[best - 1], ws[best]):
            shorter = ' '.join(ws[i:best - 1])
            if display_width(shorter) < cap * 0.20:
                break
            best -= 1
        out.append(' '.join(ws[i:best]))
        i = best
        line_no += 1
    return out

def split_sentences(text: str) -> list[str]:
    """Split Korean prose at real sentence boundaries without discarding punctuation.

    Quest UI lines are authored as hard line breaks. Keeping each sentence as an
    independent wrapping unit prevents the tail of one sentence from being packed
    together with the next, which is especially distracting in Korean.
    """
    text = re.sub(r'\s+', ' ', text.strip())
    if not text:
        return []
    # Include trailing quote/bracket marks in the sentence. Do not split on a bare
    # ellipsis unless it is followed by whitespace and a likely new sentence.
    pattern = re.compile(r'(.+?(?:[.!?。！？]+|…{2,})(?:[\"\'”’」』】)]*)?)(?=\s+|$)')
    out: list[str] = []
    pos = 0
    for m in pattern.finditer(text):
        if m.start() > pos:
            prefix = text[pos:m.start()].strip()
            if prefix:
                out.append(prefix)
        out.append(m.group(1).strip())
        pos = m.end()
    tail = text[pos:].strip()
    if tail:
        out.append(tail)
    return out or [text]


def wrap_sentences(text: str, first_cap: int, later_cap: int | None = None) -> list[str]:
    """Wrap one sentence at a time, while packing whole short sentences together.

    This prevents a line break from being optimized across a sentence boundary,
    but avoids wasting a full line on tiny interjections such as "응?".
    """
    later_cap = later_cap or first_cap
    result: list[str] = []
    current = ''
    line_no = 0

    def cap() -> int:
        return first_cap if line_no == 0 else later_cap

    def flush() -> None:
        nonlocal current, line_no
        if current:
            result.append(current)
            current = ''
            line_no += 1

    for sentence in split_sentences(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        combined = sentence if not current else f'{current} {sentence}'
        if display_width(combined) <= cap():
            current = combined
            continue

        # Do not split a sentence merely to fill the remainder of the previous
        # line. Start it cleanly on the next line, then wrap only that sentence.
        flush()
        sentence_cap = cap()
        if display_width(sentence) <= sentence_cap:
            current = sentence
            continue
        wrapped = greedy_wrap(sentence, [sentence_cap, later_cap])
        if wrapped:
            result.extend(wrapped[:-1])
            line_no += max(0, len(wrapped) - 1)
            current = wrapped[-1]

    flush()
    return result or ['']

def normalize_upper_g(text: str) -> tuple[str, int]:
    count = 0
    def repl(m: re.Match) -> str:
        nonlocal count
        count += 1
        return '%g' + m.group(1)
    text = UPPER_G_RE.sub(repl, text)
    # Korean has no capitalization distinction. Keep particles attached to the macro
    # so the quest macro parser cannot treat the intervening space as part of a
    # localized gender-form construct.
    text = re.sub(r'(%g(?:2self|[1234]?))\s+(은|는|이|가|을|를|에게|의|도|만|뿐|와|과|로|으로)', r'\1\2', text)
    return text, count


def safe_join(parts: Iterable[str]) -> str:
    out = ' '.join(p.strip() for p in parts if p.strip())
    out = re.sub(r'\s+', ' ', out)
    # Remove spaces before punctuation introduced by joining.
    out = re.sub(r'\s+([,.;:!?，。！？；：])', r'\1', out)
    return out.strip()


def reflow_ce_run(lines: list[str], cap: int) -> list[str]:
    texts = [line[4:] if line.startswith('<ce>') else line for line in lines]
    joined = safe_join(texts)
    if not joined:
        return ['<ce>']
    # Preserve signatures, compact headings, and ASCII-art/list-like runs.
    if len(lines) <= 2 and any(t.strip().startswith(('--', '—', '*', '품목 번호', '유형:')) for t in texts):
        return lines
    return ['<ce>' + s for s in wrap_sentences(joined, cap)]


def is_prose_line(line: str) -> bool:
    s = line.strip()
    if not s or HEADER_RE.match(s) or FORMAT_ONLY_RE.match(s):
        return False
    if s.startswith('--') or s in {'QRC:', 'QBN:'}:
        return False
    if re.match(r'^(?:Item|Person|Place|Clock|Foe|variable|task:|when |start |end |say |log |give |create |clicked |toting |killed |injured |prompt |have |clear |reveal |place |add |change |make |restore |unset |stop |restrain |remove |clicked)\b', s):
        return False
    return True


def reflow_quest(path: Path, mirror: Path | None, write: bool) -> Change:
    original = path.read_text(encoding='utf-8-sig')
    text, upper_count = normalize_upper_g(original)
    lines = text.splitlines()
    try:
        qbn_index = lines.index('QBN:')
    except ValueError:
        qbn_index = len(lines)
    try:
        qrc_index = lines.index('QRC:')
    except ValueError:
        qrc_index = -1

    out: list[str] = []
    i = 0
    change = Change(path=str(path), uppercase_g=upper_count)
    while i < len(lines):
        line = lines[i]
        if i >= qbn_index:
            out.extend(lines[i:])
            break

        # Centered display paragraph.
        if line.startswith('<ce>') and line.strip() != '<ce>':
            run = []
            while i < qbn_index and lines[i].startswith('<ce>') and lines[i].strip() != '<ce>':
                run.append(lines[i])
                i += 1
            new_run = reflow_ce_run(run, 64)
            out.extend(new_run)
            if new_run != run:
                change.centered_blocks += 1
            # Remove purely compensatory blank <ce> lines that immediately end a message.
            blanks = 0
            while i < qbn_index and lines[i].strip() == '<ce>':
                blanks += 1
                i += 1
            if blanks:
                # Keep one internal visual paragraph break only when followed by another <ce> line.
                if i < qbn_index and lines[i].startswith('<ce>'):
                    out.append('<ce>')
                    change.removed_trailing_blank_ce += max(0, blanks - 1)
                else:
                    change.removed_trailing_blank_ce += blanks
            continue

        # Quest journal paragraph. %qdt can be on its own line or prefix the text.
        if line.lstrip().startswith('%qdt') or line.lstrip().startswith('%qdat'):
            prefix_match = re.match(r'^(\s*%(?:qdt|qdat):?)\s*(.*)$', line)
            assert prefix_match
            prefix, first_text = prefix_match.groups()
            parts = [first_text] if first_text else []
            i += 1
            while i < qbn_index and lines[i].strip() and not HEADER_RE.match(lines[i]) and not lines[i].startswith('<ce>'):
                parts.append(lines[i])
                i += 1
            joined = safe_join(parts)
            if joined:
                # Date macros expand to a long localized prefix. Keep the first
                # source line shorter so the rendered date + prose stays inside
                # the journal panel; all following lines use the same Korean
                # readability width. Each sentence starts on a fresh source line.
                wrapped = wrap_sentences(joined, 58, 76)
                new = [prefix + (' ' + wrapped[0] if wrapped else '')] + wrapped[1:]
            else:
                new = [prefix]
            old = [line] + parts[1:] if first_text else [line] + parts
            out.extend(new)
            if new != old:
                change.journal_blocks += 1
            continue

        # Non-centered prose paragraph inside QRC (letters, item descriptions,
        # narration). Metadata and QBN commands are outside this guarded region.
        if i > qrc_index and is_prose_line(line):
            label_re = re.compile(r'^(?:유형|제작자|설명|수신|발신|제목|추신|품목 번호|Chapter|장|제\s*\d+장)\s*[:：]?', re.I)
            if label_re.match(line.strip()) or line.startswith(('  ', '\t')):
                out.append(line)
                i += 1
                continue
            run = [line]
            i += 1
            while i < qbn_index and lines[i].strip() and is_prose_line(lines[i]) and not lines[i].startswith('<ce>'):
                if label_re.match(lines[i].strip()) or lines[i].startswith(('  ', '\t')):
                    break
                run.append(lines[i])
                i += 1
            joined = safe_join(run)
            short_ratio = sum(display_width(r.strip()) < 28 for r in run) / len(run)
            punct_ratio = sum(r.rstrip().endswith(PUNCT_STRONG + ('”', '’', '"')) for r in run) / len(run)
            # Preserve verse, compact lists, signatures, and ASCII-like layouts.
            if (len(run) > 1 and short_ratio > 0.65 and punct_ratio < 0.35) or any(r.strip().startswith(('--', '*', '—')) for r in run):
                new = run
            elif len(run) > 1:
                new = wrap_sentences(joined, 76)
            else:
                new = run
            out.extend(new)
            if new != run:
                change.prose_blocks += 1
            continue

        out.append(line)
        i += 1

    result = '\n'.join(out)
    if original.endswith('\n'):
        result += '\n'

    # Apply only screenshot-confirmed typo/spacing fixes.
    for before, after in TEXT_FIXES.get(path.name, ()):
        occurrences = result.count(before)
        if occurrences:
            result = result.replace(before, after)
            change.textual_fixes += occurrences

    if write and result != original:
        path.write_text(result, encoding='utf-8', newline='\n')
        if mirror:
            mirror.write_bytes(path.read_bytes())
    return change


def looks_like_book_prose(s: str) -> bool:
    if not s.strip() or BOOK_FORMAT_RE.match(s):
        return False
    if s.lstrip().startswith(('--', '*')):
        return False
    return True


def reflow_book(path: Path, write: bool) -> Change:
    original = path.read_text(encoding='utf-8-sig')
    text, upper_count = normalize_upper_g(original)
    lines = text.splitlines()
    out: list[str] = []
    change = Change(path=str(path), uppercase_g=upper_count)
    in_content = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line == 'Content:':
            in_content = True
            out.append(line)
            i += 1
            continue
        if not in_content or not looks_like_book_prose(line):
            out.append(line)
            i += 1
            continue

        run = [line]
        i += 1
        while i < len(lines) and looks_like_book_prose(lines[i]):
            # A centered/format-prefixed line is always a deliberate standalone label.
            if BOOK_FORMAT_RE.match(lines[i]):
                break
            run.append(lines[i])
            i += 1

        # Join manual hard-wraps into one semantic paragraph. DaggerfallBookReaderWindow
        # wraps each content line automatically to page width.
        joined = safe_join(run)
        if len(run) > 1:
            # Preserve likely poetry or lists: many short lines and little sentence punctuation.
            short_ratio = sum(display_width(r.strip()) < 34 for r in run) / len(run)
            punct_ratio = sum(r.rstrip().endswith(PUNCT_STRONG + ('”', '’', '"')) for r in run) / len(run)
            if short_ratio > 0.65 and punct_ratio < 0.35:
                new = run
            else:
                leading = re.match(r'^\s*', run[0]).group(0)
                new = [leading + joined.lstrip()]
        else:
            new = run
        out.extend(new)
        if new != run:
            change.book_paragraphs += 1

    result = '\n'.join(out)
    if original.endswith('\n'):
        result += '\n'
    if write and result != original:
        path.write_text(result, encoding='utf-8', newline='\n')
    return change


def extract_structural_tokens(text: str) -> list[str]:
    # Upper/lower G are semantically equivalent for Korean; normalize for validation.
    toks = TOKEN_RE.findall(text)
    return [UPPER_G_RE.sub(lambda m: '%g' + m.group(1), t) for t in toks]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('root', type=Path)
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--report', type=Path)
    args = ap.parse_args()
    root = args.root.resolve()

    quest_dir = root / 'text' / 'Quests'
    root_quests = sorted((root / 'text').glob('*-LOC.txt'))
    # Only files with a matching mirror are quest LOC files.
    root_quests = [p for p in root_quests if (quest_dir / p.name).is_file()]
    books = sorted((root / 'text' / 'Books').glob('BOK*-LOC.txt'))

    before_tokens = {str(p.relative_to(root)): extract_structural_tokens(p.read_text(encoding='utf-8-sig')) for p in root_quests + books}
    changes: list[Change] = []
    for p in root_quests:
        changes.append(reflow_quest(p, quest_dir / p.name, args.write))
    for p in books:
        changes.append(reflow_book(p, args.write))

    blockers = []
    for p in root_quests + books:
        rel = str(p.relative_to(root))
        after = p.read_text(encoding='utf-8-sig')
        if args.write and extract_structural_tokens(after) != before_tokens[rel]:
            blockers.append({'path': rel, 'type': 'token-order-changed'})
        if '[undefined]' in after:
            blockers.append({'path': rel, 'type': 'literal-undefined'})

    mirror_mismatches = []
    for p in root_quests:
        m = quest_dir / p.name
        if p.read_bytes() != m.read_bytes():
            mirror_mismatches.append(p.name)
    if mirror_mismatches:
        blockers.append({'type': 'mirror-mismatch', 'files': mirror_mismatches})

    changed = [c for c in changes if any(getattr(c, f) for f in ('centered_blocks','journal_blocks','prose_blocks','book_paragraphs','uppercase_g','removed_trailing_blank_ce','textual_fixes'))]
    report = {
        'scope': 'Korean display reflow QA',
        'quest_files': len(root_quests),
        'book_files': len(books),
        'files_touched': len(changed),
        'centered_blocks_reflowed': sum(c.centered_blocks for c in changes),
        'journal_blocks_reflowed': sum(c.journal_blocks for c in changes),
        'quest_prose_blocks_reflowed': sum(c.prose_blocks for c in changes),
        'book_paragraphs_normalized': sum(c.book_paragraphs for c in changes),
        'uppercase_gender_macros_normalized': sum(c.uppercase_g for c in changes),
        'redundant_blank_center_lines_removed': sum(c.removed_trailing_blank_ce for c in changes),
        'screenshot_confirmed_textual_fixes': sum(c.textual_fixes for c in changes),
        'blockers': blockers,
        'changes': [asdict(c) for c in changed],
    }
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in {'changes'}}, ensure_ascii=False, indent=2))
    return 1 if blockers else 0

if __name__ == '__main__':
    raise SystemExit(main())
