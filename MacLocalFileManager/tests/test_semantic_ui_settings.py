import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from semantic.config import MODALITY_IMAGE, MODALITY_IMAGE_OCR_TEXT, MODALITY_IMAGE_SIMILARITY, MODALITY_PDF_TEXT
from ui.main_window import format_semantic_summary, is_scannable_external_volume


class SemanticUiSettingsTest(unittest.TestCase):
    def test_format_semantic_summary_includes_all_current_modalities(self) -> None:
        summary = {
            MODALITY_PDF_TEXT: {"items": 2, "errors": 1},
            MODALITY_IMAGE_OCR_TEXT: {"items": 3, "errors": 0},
            MODALITY_IMAGE: {"items": 4, "errors": 2},
            MODALITY_IMAGE_SIMILARITY: {"items": 5, "errors": 1},
        }

        text = format_semantic_summary(summary)

        self.assertIn("PDF语义 2 项，错误 1 项", text)
        self.assertIn("图片文字语义 3 项，错误 0 项", text)
        self.assertIn("图片视觉语义 4 项，错误 2 项", text)
        self.assertIn("相似图片 5 项，错误 1 项", text)

    def test_installer_like_volume_is_not_prompted_as_external_disk(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            volume = Path(temp_dir)
            (volume / "Install Example.app").mkdir()

            self.assertFalse(is_scannable_external_volume(volume))

    def test_regular_writable_volume_can_be_prompted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            volume = Path(temp_dir)
            (volume / "资料").mkdir()

            self.assertTrue(is_scannable_external_volume(volume))


if __name__ == "__main__":
    unittest.main()
