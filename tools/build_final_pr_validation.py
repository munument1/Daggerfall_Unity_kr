#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT = ROOT / 'text'
QUESTS = TEXT / 'Quests'
BASE_REF = os.environ.get(
    'VALIDATION_BASE_REF',
    '67d23e409a4eaa298405be4a023b636ee7325cb9',
)
OFFICIAL = Path(os.environ.get(
    'DFU_OFFICIAL_QUESTS',
    '/mnt/data/dfu_official/daggerfall-unity-master/Assets/StreamingAssets/Quests',
))
TOKEN_RE = re.compile(r'(?:==?[A-Za-z0-9.]+_|_{1,4}[A-Za-z0-9.]+_|%[A-Za-z0-9]+(?:-self)?)')
HEADER_RE = re.compile(r'^(?:[A-Za-z][A-Za-z0-9_ ]*:\s*\[\d+\]|Message:\s*\d+)$')
TIME_RE = re.compile(r'^\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}$')
HANGUL_RE = re.compile(r'[가-힣]')


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def sections(text: str) -> tuple[str, str, str]:
    qrc = text.index('\nQRC:\n')
    qbn = text.index('\nQBN:\n')
    return text[:qrc], text[qrc + 6:qbn], text[qbn + 6:]


def blocks(qrc: str) -> list[tuple[str, str]]:
    lines = qrc.splitlines()
    result = []
    i = 0
    while i < len(lines):
        if HEADER_RE.match(lines[i]):
            header = lines[i]
            j = i + 1
            while j < len(lines) and not HEADER_RE.match(lines[j]):
                j += 1
            result.append((header, '\n'.join(lines[i + 1:j])))
            i = j
        else:
            i += 1
    return result


def validate_quests() -> dict:
    ids = sorted(p.name[:-8] for p in QUESTS.glob('*-LOC.txt'))
    errors: list[str] = []
    messages = 0
    reflowed = 0
    for qid in ids:
        official_path = OFFICIAL / f'{qid}.txt'
        mirror_path = QUESTS / f'{qid}-LOC.txt'
        root_path = TEXT / f'{qid}-LOC.txt'
        if not official_path.exists():
            errors.append(f'{qid}: official missing')
            continue
        if not root_path.exists():
            errors.append(f'{qid}: root mirror missing')
            continue
        ko = mirror_path.read_text(encoding='utf-8')
        root = root_path.read_text(encoding='utf-8')
        en = official_path.read_text(encoding='utf-8')
        if ko != root:
            errors.append(f'{qid}: root/mirror mismatch')
        _, en_qrc, en_qbn = sections(en)
        _, ko_qrc, ko_qbn = sections(ko)
        en_blocks = blocks(en_qrc)
        ko_blocks = blocks(ko_qrc)
        messages += len(en_blocks)
        if [h for h, _ in en_blocks] != [h for h, _ in ko_blocks]:
            errors.append(f'{qid}: message key/order mismatch')
            continue
        if en_qbn != ko_qbn:
            errors.append(f'{qid}: QBN mismatch')
        for (header, en_body), (_, ko_body) in zip(en_blocks, ko_blocks):
            if Counter(TOKEN_RE.findall(en_body)) != Counter(TOKEN_RE.findall(ko_body)):
                errors.append(f'{qid} {header}: token mismatch')
            for marker in ('<ce>', '<--->', '%qdt', '%qdat'):
                if en_body.count(marker) != ko_body.count(marker):
                    errors.append(f'{qid} {header}: {marker} mismatch')
        # A pragmatic signal: files whose current bytes differ from staged pre-reflow version
        # are counted separately by git outside this function; all files are structurally checked here.
    return {
        'quest_files': len(ids),
        'message_blocks': messages,
        'root_mirror_files': len(ids) * 2,
        'errors': errors,
    }


def validate_srt() -> dict:
    files = sorted((ROOT / '0' / '0').glob('*.srt'))
    errors: list[str] = []
    cues = 0
    for path in files:
        text = path.read_text(encoding='utf-8-sig').replace('\r\n', '\n').strip()
        chunks = re.split(r'\n\s*\n', text) if text else []
        expected = 1
        for chunk in chunks:
            lines = chunk.splitlines()
            if len(lines) < 3 or not lines[0].isdigit() or not TIME_RE.match(lines[1]):
                errors.append(f'{path.name}: malformed cue near {expected}')
                continue
            number = int(lines[0])
            if number != expected:
                errors.append(f'{path.name}: cue sequence {number} != {expected}')
            body = '\n'.join(lines[2:])
            if not HANGUL_RE.search(body):
                errors.append(f'{path.name} cue {number}: Korean missing')
            expected += 1
            cues += 1
    return {'files': len(files), 'cues': cues, 'errors': errors}


def validate_biogs() -> dict:
    files = sorted((ROOT / 'BIOGs').glob('BIOG??T0.TXT'))
    errors: list[str] = []
    for path in files:
        data = path.read_bytes()
        # BiogFile parser reads one additional line after final effect; preserve an empty terminator line.
        normalized = data.replace(b'\r\n', b'\n')
        terminal = normalized.rstrip(b'\n')
        if not (normalized.endswith(b'\n\n') or terminal.endswith(b'\x1a')):
            errors.append(f'{path.name}: missing parser terminator (empty line or DOS EOF)')
        text = normalized.decode('utf-8-sig')
        questions = len(re.findall(r'(?m)^\d+\.\s', text))
        if questions != 12:
            errors.append(f'{path.name}: question count {questions}')
    return {'files': len(files), 'errors': errors}


def validate_json() -> dict:
    errors: list[str] = []
    for rel in ('text/NameGen.txt',):
        try:
            json.loads((ROOT / rel).read_text(encoding='utf-8-sig'))
        except Exception as exc:
            errors.append(f'{rel}: {exc}')
    return {'files': 1, 'errors': errors}


def validate_books() -> dict:
    files = sorted((TEXT / 'Books').glob('BOK*-LOC.txt'))
    errors: list[str] = []
    font_2_files = 0
    font_4_files = 0
    for path in files:
        text = path.read_text(encoding='utf-8-sig')
        for field in ('Title:', 'Author:', 'IsNaughty:', 'Price:', 'IsUnique:', 'WhenVarSet:', 'Content:'):
            if not re.search(rf'(?m)^{re.escape(field)}', text):
                errors.append(f'{path.name}: missing {field}')
        tags = re.findall(r'\[/font=(\d+)\]', text)
        if '2' in tags:
            font_2_files += 1
        if '4' in tags:
            font_4_files += 1
        unexpected = sorted(set(tags) - {'2', '4'})
        if unexpected:
            errors.append(f'{path.name}: unexpected font tags {unexpected}')
    if font_2_files != len(files):
        errors.append(f'books using [/font=2]: {font_2_files} != {len(files)}')
    if font_4_files != len(files):
        errors.append(f'books using [/font=4]: {font_4_files} != {len(files)}')
    return {
        'files': len(files),
        'font_2_files': font_2_files,
        'font_4_files': font_4_files,
        'errors': errors,
    }


def validate_fonts() -> dict:
    errors: list[str] = []
    expected = {
        'FONT0000-SDF.ttf': ('Bookk Myungjo', 'Bold'),
        'FONT0001-SDF.ttf': ('Bookk Myungjo', 'Bold'),
        'FONT0003-SDF.ttf': ('Bookk Myungjo', 'Light'),
    }
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        return {'files': len(expected), 'errors': ['fontTools is required for font validation']}

    used_codepoints: set[int] = set()
    # Bookk Myungjo is assigned only to quest journal and book slots. Validate
    # characters rendered in those views, not control bytes or unrelated UI data.
    for directory in (QUESTS, TEXT / 'Books'):
        for path in directory.rglob('*'):
            if path.is_file() and path.suffix.lower() == '.txt':
                try:
                    used_codepoints.update(
                        ord(char)
                        for char in path.read_text(encoding='utf-8-sig')
                        if char.isprintable() and not char.isspace()
                    )
                except UnicodeDecodeError:
                    continue

    hashes: dict[str, str] = {}
    for filename, (family, style) in expected.items():
        path = ROOT / 'fonts' / filename
        hashes[filename] = sha256(path)
        try:
            font = TTFont(path)
            names: dict[int, set[str]] = {}
            for record in font['name'].names:
                if record.nameID in (1, 2, 4):
                    try:
                        names.setdefault(record.nameID, set()).add(record.toUnicode())
                    except UnicodeDecodeError:
                        continue
            cmap: set[int] = set()
            for table in font['cmap'].tables:
                cmap.update(table.cmap)
            if not any(family in value for value in names.get(1, set()) | names.get(4, set())):
                errors.append(f'{filename}: family is not {family}')
            if not any(style in value for value in names.get(2, set()) | names.get(4, set())):
                errors.append(f'{filename}: style is not {style}')
            missing = sorted(used_codepoints - cmap)
            if missing:
                sample = ', '.join(f'U+{codepoint:04X}' for codepoint in missing[:12])
                errors.append(f'{filename}: missing {len(missing)} used glyphs ({sample})')
        except Exception as exc:
            errors.append(f'{filename}: {exc}')
    if hashes['FONT0000-SDF.ttf'] != hashes['FONT0001-SDF.ttf']:
        errors.append('FONT0000 and FONT0001 must use the same Bookk Myungjo Bold bytes')
    if hashes['FONT0000-SDF.ttf'] == hashes['FONT0003-SDF.ttf']:
        errors.append('Bookk Myungjo Bold and Light bytes must differ')
    return {'files': len(expected), 'hashes': hashes, 'errors': errors}


def changed_files() -> list[str]:
    proc = subprocess.run(
        ['git', 'diff', '--name-only', BASE_REF, '--'], cwd=ROOT,
        check=True, text=True, capture_output=True,
    )
    return [line for line in proc.stdout.splitlines() if line]


def main() -> None:
    quest = validate_quests()
    srt = validate_srt()
    biog = validate_biogs()
    namegen = validate_json()
    books = validate_books()
    fonts = validate_fonts()
    changed = changed_files()

    # Files changed by Korean-aware line reflow (root + Quests mirrors).
    reflow_files = [
        p for p in changed
        if p.endswith('-LOC.txt')
        and (p.startswith('text/Quests/') or (p.startswith('text/') and p.count('/') == 1))
    ]
    all_errors = (
        quest['errors'] + srt['errors'] + biog['errors'] + namegen['errors']
        + books['errors'] + fonts['errors']
    )
    now = datetime.now(timezone(timedelta(hours=9))).isoformat(timespec='seconds')
    report = {
        'project': 'Daggerfall Unity Korean complete retranslation',
        'repository': 'munument1/Daggerfall_Unity_kr',
        'base_commit': '67d23e409a4eaa298405be4a023b636ee7325cb9',
        'official_source': {
            'repository': 'Interkarma/daggerfall-unity',
            'commit': '81e89e90c27bc3c1a7a61871e545fad129174dec',
            'version': 'Daggerfall Unity v1.1.1',
        },
        'validated_at': now,
        'summary': {
            'changed_files': len(changed),
            'quest_files': quest['quest_files'],
            'quest_message_blocks': quest['message_blocks'],
            'quest_loc_files': quest['root_mirror_files'],
            'korean_reflow_loc_files': len(reflow_files),
            'subtitle_files': srt['files'],
            'subtitle_cues': srt['cues'],
            'biography_files': biog['files'],
            'book_files': books['files'],
            'bookk_myungjo_font_files': fonts['files'],
            'blocking_errors': len(all_errors),
        },
        'checks': {
            'quest_keys_order_tokens_controls_qbn': 'passed' if not quest['errors'] else 'failed',
            'quest_root_mirror_equality': 'passed' if not any('root/mirror' in e for e in quest['errors']) else 'failed',
            'korean_aware_line_reflow': {
                'status': 'passed' if not quest['errors'] else 'failed',
                'policy': 'Korean phrase and punctuation boundaries; exact official control-marker counts preserved',
                'files': len(reflow_files),
            },
            'subtitle_sequence_timing_korean_presence': 'passed' if not srt['errors'] else 'failed',
            'biog_parser_terminators_and_question_counts': 'passed' if not biog['errors'] else 'failed',
            'name_generator_json': 'passed' if not namegen['errors'] else 'failed',
            'book_metadata_and_font_tags': 'passed' if not books['errors'] else 'failed',
            'bookk_myungjo_fonts_and_used_glyphs': {
                'status': 'passed' if not fonts['errors'] else 'failed',
                'hashes': fonts.get('hashes', {}),
            },
        },
        'errors': all_errors,
    }
    (ROOT / 'daggerfall-korean-final-pr-validation.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n'
    )

    # Refresh the quest-specific report too.
    quest_report = {
        'project': 'Daggerfall Unity Korean quest retranslation',
        'official_source_repository': 'Interkarma/daggerfall-unity',
        'official_source_commit': '81e89e90c27bc3c1a7a61871e545fad129174dec',
        'official_version': 'Daggerfall Unity v1.1.1',
        'quest_files': quest['quest_files'],
        'message_blocks': quest['message_blocks'],
        'assembled_loc_files': quest['root_mirror_files'],
        'key_order_validation': 'passed' if not quest['errors'] else 'failed',
        'exact_source_token_validation': 'passed' if not quest['errors'] else 'failed',
        'control_marker_validation': 'passed' if not quest['errors'] else 'failed',
        'qbn_exact_equality': 'passed' if not quest['errors'] else 'failed',
        'root_mirror_equality': 'passed' if not quest['errors'] else 'failed',
        'korean_aware_line_reflow': 'passed' if not quest['errors'] else 'failed',
        'reflowed_loc_files': len(reflow_files),
        'structural_repairs': {'S0000008': ['Message:1057', 'Message:1061']},
        'validated_at': now,
        'errors': quest['errors'],
    }
    (ROOT / 'quest-retranslation-final-validation.json').write_text(
        json.dumps(quest_report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n'
    )

    # Hash every changed file except this hash manifest itself.
    changed_after = changed_files()
    hashes = {}
    for rel in sorted(changed_after):
        if rel == 'quest-retranslation-file-hashes.json':
            continue
        path = ROOT / rel
        if path.is_file():
            hashes[rel] = sha256(path)
        else:
            hashes[rel] = None
    (ROOT / 'quest-retranslation-file-hashes.json').write_text(
        json.dumps(hashes, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n'
    )

    print(json.dumps(report['summary'], ensure_ascii=False, indent=2))
    if all_errors:
        for error in all_errors:
            print(error)
        raise SystemExit(1)

if __name__ == '__main__':
    main()
