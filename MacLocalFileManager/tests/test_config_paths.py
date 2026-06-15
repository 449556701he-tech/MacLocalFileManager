import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ConfigPathsTest(unittest.TestCase):
    def test_data_dir_can_be_overridden_for_isolated_runtime_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            env["MACLOCALFILEMANAGER_DATA_DIR"] = temp_dir
            output = subprocess.check_output(
                [
                    sys.executable,
                    "-c",
                    "import json, config; print(json.dumps(str(config.DEFAULT_DB_PATH)))",
                ],
                cwd=PROJECT_ROOT,
                env=env,
                text=True,
            )

        self.assertEqual(json.loads(output), str(Path(temp_dir) / "file_index.sqlite3"))


if __name__ == "__main__":
    unittest.main()
