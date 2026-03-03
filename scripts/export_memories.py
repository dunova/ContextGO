#!/usr/bin/env python3
"""Export memory observations to JSON."""

from __future__ import annotations

from datetime import datetime
import argparse
import json
from pathlib import Path

try:
    from memory_index import search_index, sync_index_from_storage
except Exception:  # pragma: no cover
    from .memory_index import search_index, sync_index_from_storage  # type: ignore[import-not-found]


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Context Mesh memories.")
    parser.add_argument("query", help="Search query. Use empty string for all.", nargs="?", default="")
    parser.add_argument("output", help="Output JSON path.")
    parser.add_argument("--limit", type=int, default=5000, help="Max observations to export.")
    parser.add_argument("--source-type", default="all", choices=["all", "history", "conversation"])
    args = parser.parse_args()

    sync_info = sync_index_from_storage()
    target = max(1, min(args.limit, 50000))
    rows = []
    offset = 0
    page = 200
    while len(rows) < target:
        batch = search_index(
            query=args.query,
            limit=min(page, target - len(rows)),
            offset=offset,
            source_type=args.source_type,
        )
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < page:
            break
        offset += len(batch)

    payload = {
        "exported_at": datetime.now().isoformat(),
        "query": args.query,
        "source_type": args.source_type,
        "sync": sync_info,
        "total_observations": len(rows),
        "observations": rows,
    }

    output_path = Path(args.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"exported observations={len(rows)} -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
