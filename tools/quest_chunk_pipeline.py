#!/usr/bin/env python3
"""Quest QRC chunk extractor, applier, and structural validator."""
from __future__ import annotations
import argparse, json, re, sys
from collections import Counter
from pathlib import Path

HEADER = re.compile(r"^(QuestorOffer|RefuseQuest|AcceptQuest|QuestFail|QuestComplete|RumorsDuringQuest|RumorsPostfailure|RumorsPostsuccess|QuestorPostsuccess|QuestorPostfailure|QuestLogEntry|Message):\s*(?:\[(\d+)\]|(\d+))?\s*$")
TOKEN = re.compile(r"(?:%[A-Za-z0-9]+|=[A-Za-z0-9.]+_|_{1,3}[A-Za-z0-9.]+_)")
CONTROL = re.compile(r"<ce>|<--->|%qdt")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def sections(text: str):
    pre, rest = text.split("QRC:", 1)
    qrc, qbn = rest.split("QBN:", 1)
    return pre + "QRC:\n", qrc.strip("\n"), "QBN:" + qbn


def blocks(qrc: str):
    lines = qrc.splitlines()
    starts = [i for i, line in enumerate(lines) if HEADER.match(line)]
    out = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        header = lines[start]
        match = HEADER.match(header)
        key = f"{match.group(1)}:{match.group(2) or match.group(3) or n}"
        body = lines[start + 1:end]
        while body and not body[-1].strip(): body.pop()
        out.append((key, header, "\n".join(body)))
    return out


def count(pattern, text): return Counter(pattern.findall(text))


def pair(official: Path, localized: Path, quest_id: str):
    return official / f"{quest_id}.txt", localized / f"{quest_id}-LOC.txt"


def extract(args):
    records = []
    for qid in args.quest_ids:
        en_path, ko_path = pair(args.official_dir, args.localized_dir, qid)
        _, en_qrc, _ = sections(read(en_path)); _, ko_qrc, _ = sections(read(ko_path))
        en, ko = blocks(en_qrc), blocks(ko_qrc)
        if [x[0] for x in en] != [x[0] for x in ko]: raise ValueError(f"key mismatch: {qid}")
        for (_, header, en_body), (key, _, ko_body) in zip(en, ko):
            records.append({"quest_id": qid, "key": key, "header": header, "english": en_body,
                            "korean": ko_body, "translation": "",
                            "tokens": dict(count(TOKEN, en_body)), "controls": dict(count(CONTROL, en_body))})
    args.output_dir.mkdir(parents=True, exist_ok=True)
    chunks, current, size = [], [], 0
    for record in records:
        item_size = len(record["english"]) + len(record["korean"]) + 300
        if current and size + item_size > args.max_chars: chunks.append(current); current, size = [], 0
        current.append(record); size += item_size
    if current: chunks.append(current)
    for i, chunk in enumerate(chunks, 1):
        with (args.output_dir / f"chunk-{i:03d}.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for row in chunk: f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{len(args.quest_ids)} quests, {len(records)} blocks, {len(chunks)} chunks")


def load_results(path: Path):
    result = {}
    for file in sorted(path.glob("chunk-*.jsonl")):
        for line in file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line); result[(row["quest_id"], row["key"])] = row
    return result


def apply(args):
    result = load_results(args.result_dir); args.output_dir.mkdir(parents=True, exist_ok=True)
    for qid in args.quest_ids:
        source = args.localized_dir / f"{qid}-LOC.txt"; pre, qrc, qbn = sections(read(source)); rendered = []
        for key, header, _ in blocks(qrc):
            row = result[(qid, key)]; text = row["translation"].rstrip()
            if not text: raise ValueError(f"empty translation: {qid} {key}")
            if count(TOKEN, text) != Counter(row["tokens"]): raise ValueError(f"token mismatch: {qid} {key}")
            if count(CONTROL, text) != Counter(row["controls"]): raise ValueError(f"control mismatch: {qid} {key}")
            rendered.append(header + "\n" + text)
        (args.output_dir / source.name).write_text(pre + "\n\n".join(rendered) + "\n\n" + qbn, encoding="utf-8", newline="\n")


def validate(args):
    errors = []
    for qid in args.quest_ids:
        en_path, ko_path = pair(args.official_dir, args.localized_dir, qid)
        _, en_qrc, en_qbn = sections(read(en_path)); _, ko_qrc, ko_qbn = sections(read(ko_path))
        if en_qbn != ko_qbn: errors.append(f"{qid}: QBN differs")
        en, ko = blocks(en_qrc), blocks(ko_qrc)
        if [x[0] for x in en] != [x[0] for x in ko]: errors.append(f"{qid}: keys differ"); continue
        for (key, _, a), (_, _, b) in zip(en, ko):
            if count(TOKEN, a) != count(TOKEN, b): errors.append(f"{qid} {key}: tokens differ")
            if count(CONTROL, a) != count(CONTROL, b): errors.append(f"{qid} {key}: controls differ")
    if errors: print("\n".join(errors), file=sys.stderr); raise SystemExit(1)
    print(f"validated {len(args.quest_ids)} quests")


def main():
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract"); e.add_argument("--official-dir", type=Path, required=True); e.add_argument("--localized-dir", type=Path, required=True); e.add_argument("--output-dir", type=Path, required=True); e.add_argument("--max-chars", type=int, default=16000); e.add_argument("quest_ids", nargs="+"); e.set_defaults(func=extract)
    a = sub.add_parser("apply"); a.add_argument("--localized-dir", type=Path, required=True); a.add_argument("--result-dir", type=Path, required=True); a.add_argument("--output-dir", type=Path, required=True); a.add_argument("quest_ids", nargs="+"); a.set_defaults(func=apply)
    v = sub.add_parser("validate"); v.add_argument("--official-dir", type=Path, required=True); v.add_argument("--localized-dir", type=Path, required=True); v.add_argument("quest_ids", nargs="+"); v.set_defaults(func=validate)
    args = p.parse_args(); args.func(args)


if __name__ == "__main__": main()
