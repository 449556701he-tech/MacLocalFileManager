from __future__ import annotations

import subprocess
from pathlib import Path


def open_file(path: str | Path) -> None:
    subprocess.run(["open", str(path)], check=False)


def reveal_in_finder(path: str | Path) -> None:
    subprocess.run(["open", "-R", str(path)], check=False)

