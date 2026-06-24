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
            "macos_integration",
            "AppKit",
            "semantic.backends.deterministic",
            "semantic.backends.apple_vision",
        ]:
            self.assertIn(f'"{module}"', spec_text)

    def test_release_specs_are_v1_1_and_include_macos_integration(self) -> None:
        for spec_name in ["MacLocalFileManager.spec", "MacLocalFileManager-English.spec"]:
            spec_text = (PROJECT_ROOT / spec_name).read_text(encoding="utf-8")

            self.assertIn('"CFBundleShortVersionString": "1.1.0"', spec_text)
            self.assertIn('"CFBundleVersion": "1.1.0"', spec_text)
            self.assertIn('"macos_integration"', spec_text)


if __name__ == "__main__":
    unittest.main()
