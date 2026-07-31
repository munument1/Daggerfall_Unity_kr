#!/usr/bin/env python3
"""Build batches and translation chunks for every unfinished quest file."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from quest_chunk_pipeline import CONTROL, TOKEN, blocks, count, read, sections


def load_completed(path: Path) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    completed = data.get("completed")
    if not isinstance(completed, list) or not all(isinstance(item, str) for item in completed):
        raise ValueError(f"invalid completed list: {path}")
    return set(completed)


def quest_ids(localized_dir: Path) -> list[str]:
    suffix = "-LOC.txt"
    return sorted(path.name[:-len(suffix)] for path in localized_dir.glob(f"*{suffix}"))


def inspect_quest(official_dir: Path, localized_dir: Path, quest_id: str) -> dict:
    english_path = official_dir / f"{quest_id}.txt"
    korean_path = localized_dir / f"{quest_id}-LOC.txt"
    if not english_path.exists():
        raise FileNotFoundError(f"official source missing: {english_path}")

    _, english_qrc, _ = sections(read(english_path))
    _, korean_qrc, _ = sections(read(korean_path))
    english_blocks = blocks(english_qrc)
    korean_blocks = blocks(korean_qrc)

    if [item[0] for item in english_blocks] != [item[0] for item in korean_blocks]:
        raise ValueError(f"message key mismatch: {quest_id}")

    return {
        "quest_id": quest_id,
        "blocks": len(english_blocks),
        "chars": len(english_qrc) + len(korean_qrc),
        "english": english_blocks,
        "korean": korean_blocks,
    }


def make_batches(items: list[dict], max_files: int, max_chars: int) -> list[list[dict]]:
    batches: list[list[dict]] = []
    current: list[dict] = []
    current_chars = 0

    for item in items:
        exceeds_limit = len(current) >= max_files or current_chars + item["chars"] > max_chars
        if current and exceeds_limit:
            batches.append(current)
            current = []
            current_chars = 0
        current.append(item)
        current_chars += item["chars"]

    if current:
        batches.append(current)
    return batches


def records_for(batch: list[dict]) -> list[dict]:
    records: list[dict] = []
    for item in batch:
        quest_id = item["quest_id"]
        for (_, header, english_body), (key, _, korean_body) in zip(item["english"], item["korean"]):
            records.append(
                {
                    "quest_id": quest_id,
                    "key": key,
                    "header": header,
                    "english": english_body,
                    "korean": korean_body,
                    "translation": "",
                    "tokens": dict(count(TOKEN, english_body)),
                    "controls": dict(count(CONTROL, english_body)),
                }
            )
    return records


def write_chunks(records: list[dict], output_dir: Path, max_chars: int) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[list[dict]] = []
    current: list[dict] = []
    current_chars = 0

    for record in records:
        record_chars = len(record["english"]) + len(record["korean"]) + 300
        if current and current_chars + record_chars > max_chars:
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(record)
        current_chars += record_chars

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
    parser.add_argument(
        "--completed",
        type=Path,
        default=Path("tools/quest_retranslation_status.json"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("work/all-quests"))
    parser.add_argument("--max-files", type=int, default=6)
    parser.add_argument("--max-batch-chars", type=int, default=70000)
    parser.add_argument("--max-chunk-chars", type=int, default=16000)
    args = parser.parse_args()

    if args.max_files < 1 or args.max_batch_chars < 1 or args.max_chunk_chars < 1:
        parser.error("batch and chunk limits must be positive")

    completed = load_completed(args.completed)
    all_quest_ids = quest_ids(args.localized_dir)
    unknown_completed = completed.difference(all_quest_ids)
    if unknown_completed:
        unknown = ", ".join(sorted(unknown_completed))
        raise ValueError(f"completed quest IDs not found in localized directory: {unknown}")

    remaining_ids = [quest_id for quest_id in all_quest_ids if quest_id not in completed]
    items = [inspect_quest(args.official_dir, args.localized_dir, quest_id) for quest_id in remaining_ids]
    batches = make_batches(items, args.max_files, args.max_batch_chars)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    queue = {
        "official_source": {
            "repository": "Interkarma/daggerfall-unity",
            "commit": "81e89e90c27bc3c1a7a61871e545fad129174dec",
            "version": "Daggerfall Unity v1.1.1",
        },
        "total_files": len(all_quest_ids),
        "completed_files": len(completed),
        "remaining_files": len(remaining_ids),
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
        chunk_count = write_chunks(
            records_for(batch),
            args.output_dir / batch_id,
            args.max_chunk_chars,
        )
        queue["batches"].append(
            {
                "batch": batch_id,
                "quest_ids": [item["quest_id"] for item in batch],
                "files": len(batch),
                "blocks": sum(item["blocks"] for item in batch),
                "chars": sum(item["chars"] for item in batch),
                "chunks": chunk_count,
                "status": "pending",
            }
        )

    (args.output_dir / "queue.json").write_text(
        json.dumps(queue, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"{len(all_quest_ids)} total, {len(completed)} completed, "
        f"{len(remaining_ids)} remaining -> {len(batches)} batches"
    )


if __name__ == "__main__":
    main()
