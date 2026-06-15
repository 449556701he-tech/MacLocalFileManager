from __future__ import annotations

import os

os.environ["MACLOCALFILEMANAGER_LANG"] = "en"

from app import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())

