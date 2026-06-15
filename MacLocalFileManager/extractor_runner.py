from __future__ import annotations

import json
import sys
from pathlib import Path

from config import MAX_EXTRACTED_TEXT_CHARS
from extractors.registry import ExtractorRegistry


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(json.dumps({"ok": False, "error": "usage: extractor_runner.py <path>"}))
        return 2

    path = Path(argv[0])
    extractor = ExtractorRegistry().extractor_for(path)
    if extractor is None:
        print(json.dumps({"ok": False, "error": f"unsupported extension: {path.suffix}"}))
        return 1

    try:
        result = extractor.extract(path)
        print(
            json.dumps(
                {
                    "ok": True,
                    "content_text": result.content_text[:MAX_EXTRACTED_TEXT_CHARS],
                    "metadata": result.metadata,
                },
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - callers record extraction failures.
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
