import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


class PackagingSpecTest(unittest.TestCase):
    def test_pyinstaller_spec_includes_semantic_modules(self) -> None:
        spec_text = (PROJECT_ROOT / "MacLocalFileManager.spec").read_text(encoding="utf-8")

        for module in [
            "semantic.indexer",
            "semantic.search",
            "semantic.vector_store",
            "semantic.backends.deterministic",
        ]:
            self.assertIn(f'"{module}"', spec_text)


if __name__ == "__main__":
    unittest.main()
