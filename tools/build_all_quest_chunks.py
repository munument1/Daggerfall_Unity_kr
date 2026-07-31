#!/usr/bin/env python3
"""Build batches and translation chunks for every unfinished quest file."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from quest_chunk_pipeline import blocks, count, read, sections, TOKEN, CONTROL


def load_completed(path: Path) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return set(data["completed"])


def quest_ids(localized_dir: Path) -> list[str]:
    suffix = "-LOC.txt"
    return sorted(p.name[:-len(suffix)] for p in localized_dir.glob(f"*{suffix}"))


def inspect_quest(official_dir: Path, localized_dir: Path, qid: str) -> dict:
    en_path = official_dir / f"{qid}.txt"
    ko_path = localized_dir / f"{qid}-LOC.txt"
    if not en_path.exists():
        raise FileNotFoundError(f"official source missing: {en_path}")
    _, en_qrc, _ = sections(read(en_path))
    _, ko_qrc, _ = sections(read(ko_path))
    en_blocks = blocks(en_qrc)
    ko_blocks = blocks(ko_qrc)
    if [x[0] for x in en_blocks] != [x[0] for x in ko_blocks]:
        raise ValueError(f"message key mismatch: {qid}")
    return {
        "quest_id": qid,
        "blocks": len(en_blocks),
        "chars": len(en_qrc) + len(ko_qrc),
        "english": en_blocks,
        "korean": ko_blocks,
    }


def make_batches(items: list[dict], max_files: int, max_chars: int) -> list[list[dict]]:
    batches: list[list[dict]] = []
    current: list[dict] = []
    size = 0
    for item in items:
        if current and (len(current) >= max_files or size + item["chars"] > max_chars):
            batches.append(current)
            current, size = [], 0
        current.append(item)
        size += item["chars"]
    if current:
        batches.append(current)
    return batches


def records_for(batch: list[dict]) -> list[dict]:
    records = []
    for item in batch:
        qid = item["quest_id"]
        for (_, header, en_body), (key, _, ko_body) in zip(item["english"], item["korean"]):
            records.append({
                "quest_id": qid,
                "key": key,
                "header": header,
                "english": en_body,
                "korean": ko_body,
                "translation": "",
                "tokens": dict(count(TOKEN, en_body)),
                "controls": dict(count(CONTROL, en_body)),
            })
    return records


def write_chunks(records: list[dict], output_dir: Path, max_chars: int) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[list[dict]] = []
    current: list[dict] = []
    size = 0
    for record in records:
        item_size = len(record["english"]) + len(record["korean"]) + 300
        if current and size + item_size > max_chars:
            chunks.append(current)
            current, size = [], 0
        current.append(record)
        size += item_size
    if current:
        chunks.append(current)
    for index, chunk in enumerate(chunks, 1):
        path = output_dir / f"chunk-{index:03d}.jsonl"
        with path.open("w", encoding="utf-8", newline="\n") as stream:
            for row in chunk:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(chunks)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--official-dir", type=Path, required=True)
    parser.add_argument("--localized-dir", type=Path, required=True)
    parser.add_argument("--completed", type=Path, default=Path("tools/quest_retranslation_status.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("work/all-quests"))
    parser.add_argument("--max-files", type=int, default=6)
    parser.add_argument("--max-batch-chars", type=int, default=70000)
    parser.add_argument("--max-chunk-chars", type=int, default=16000)
    args = parser.parse_args()

    completed = load_completed(args.completed)
    all_ids = quest_ids(args.localized_dir)
    remaining = [qid for qid in all_ids if qid not in completed]
    items = [inspect_quest(args.official_dir, args.localized_dir, qid) for qid in remaining]
    batches = make_batches(items, args.max_files, args.max_batch_chars)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    queue = {
        "total_files": len(all_ids),
        "completed_files": len([qid for qid in all_ids if qid in completed]),
        "remaining_files": len(remaining),
        "batch_count": len(batches),
        "settings": {
            "max_files": args.max_files,
            "max_batch_chars": args.max_batch_chars,
            "max_chunk_chars": args.max_chunk_chars,
        },
        "batches": [],
    }

    for index, batch in enumerate(batches, 1):
        batch_id = f"batch-{index:03d}"
        chunk_count = write_chunks(records_for(batch), args.output_dir / batch_id, args.max_chunk_chars)
        queue["batches"].append({
            "batch": batch_id,
            "quest_ids": [item["quest_id"] for item in batch],
            "files": len(batch),
            "blocks": sum(item["blocks"] for item in batch),
            "chars": sum(item["chars"] for item in batch),
            "chunks": chunk_count,
            "status": "pending",
        })

    (args.output_dir / "queue.json").write_text(
        json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{len(remaining)} remaining quests -> {len(batches)} batches")


if __name__ == "__main__":
    main()
