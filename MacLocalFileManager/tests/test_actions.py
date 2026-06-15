import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from actions import open_file, reveal_in_finder


class ActionsTest(unittest.TestCase):
    def test_open_file_uses_macos_open(self) -> None:
        with patch("actions.subprocess.run") as run:
            open_file("/tmp/中文文件.txt")
        run.assert_called_once_with(["open", "/tmp/中文文件.txt"], check=False)

    def test_reveal_in_finder_uses_open_dash_r(self) -> None:
        with patch("actions.subprocess.run") as run:
            reveal_in_finder("/tmp/中文文件.txt")
        run.assert_called_once_with(["open", "-R", "/tmp/中文文件.txt"], check=False)


if __name__ == "__main__":
    unittest.main()

