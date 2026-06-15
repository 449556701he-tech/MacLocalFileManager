from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from database import FileDatabase
from file_categories import CATEGORY_BILLS, CATEGORY_DOCUMENTS, CATEGORY_DRAWINGS, CATEGORY_IMAGES
from models import SearchResult
from ui.main_window import MainWindow


def main() -> int:
    app = QApplication.instance() or QApplication([])
    output_path = PROJECT_ROOT / "docs" / "ui" / "v8-ui-entry-mvp.png"
    home_output_path = PROJECT_ROOT / "docs" / "ui" / "v8-spotlight-home.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        db = FileDatabase(root / "preview.sqlite3")
        window = MainWindow(db)
        window.show()
        for _ in range(8):
            app.processEvents()
        window.grab().save(str(home_output_path))

        window.search_input.setText("付款截图")
        window.status_label.setText("预览：当前为 UI 初版，美工确认后继续接入快捷键和剪切板。")

        image_specs = [
            ("付款截图-样例.png", "#dbeafe", "付款"),
            ("合同照片-材料到场.png", "#dcfce7", "合同"),
            ("图纸现场-节点.png", "#fef3c7", "图纸"),
            ("表格截图-金额汇总.png", "#ede9fe", "表格"),
        ]
        image_paths = []
        for filename, color, label in image_specs:
            image_path = root / filename
            pixmap = QPixmap(640, 420)
            pixmap.fill(QColor(color))
            painter = QPainter(pixmap)
            painter.setPen(QColor("#111827"))
            painter.setFont(QFont("Arial", 54, QFont.Bold))
            painter.drawText(pixmap.rect(), Qt.AlignCenter, label)
            painter.end()
            pixmap.save(str(image_path))
            image_paths.append(image_path)

        now = time.time()
        results = [
            *[
                SearchResult(
                    id=index,
                    filename=image_path.name,
                    path=str(image_path),
                    parent_dir=str(root),
                    extension="png",
                    size=image_path.stat().st_size,
                    created_at=now,
                    modified_at=now,
                    indexed_at=now,
                    exists=1,
                    reason="图片文字语义命中",
                    rank=8.1,
                    match_type="图片语义",
                    snippet="付款凭证、转账截图、金额记录",
                    category=CATEGORY_IMAGES,
                )
                for index, image_path in enumerate(image_paths, start=1)
            ],
            SearchResult(
                id=10,
                filename="60亩精装合同台账.xlsx",
                path=str(root / "60亩精装合同台账.xlsx"),
                parent_dir=str(root),
                extension="xlsx",
                size=243000,
                created_at=now,
                modified_at=now,
                indexed_at=now,
                exists=1,
                reason="文件名包含",
                rank=3.0,
                match_type="文件名命中",
                snippet="合同金额、补充项、待确认范围",
                category=CATEGORY_BILLS,
            ),
            *[
                SearchResult(
                    id=11 + index,
                    filename=filename,
                    path=str(root / filename),
                    parent_dir=str(root),
                    extension=extension,
                    size=size,
                    created_at=now,
                    modified_at=now,
                    indexed_at=now,
                    exists=1,
                    reason=reason,
                    rank=rank,
                    match_type=match_type,
                    snippet=snippet,
                    category=category,
                )
                for index, (filename, extension, size, reason, rank, match_type, snippet, category) in enumerate(
                    [
                        ("一层平面图-付款节点.pdf", "pdf", 1080000, "PDF语义命中", 7.2, "语义命中", "付款节点对应施工图和清单范围", CATEGORY_DRAWINGS),
                        ("付款申请说明.docx", "docx", 51000, "内容包含", 5.0, "内容命中", "本次付款申请包含材料到场和隐蔽验收资料", CATEGORY_DOCUMENTS),
                        ("付款审批记录.docx", "docx", 73000, "内容包含", 5.1, "内容命中", "审批记录、付款条件、附件清单", CATEGORY_DOCUMENTS),
                        ("合同补充说明.pdf", "pdf", 520000, "内容包含", 5.2, "内容命中", "补充协议、付款比例、节点说明", CATEGORY_DOCUMENTS),
                        ("材料到货照片说明.docx", "docx", 68000, "内容包含", 5.3, "内容命中", "材料到货照片与付款截图对应关系", CATEGORY_DOCUMENTS),
                        ("付款节点汇总.xlsx", "xlsx", 95000, "文件名包含", 3.1, "文件名命中", "节点、金额、状态、经办人", CATEGORY_BILLS),
                        ("精装付款附件目录.pdf", "pdf", 210000, "路径包含", 4.0, "路径命中", "附件目录、发票、截图、合同页", CATEGORY_DOCUMENTS),
                    ]
                )
            ],
        ]
        window._show_search_results(results)
        window.show()
        for _ in range(8):
            app.processEvents()
        window.grab().save(str(output_path))
        window.close()

    print(home_output_path)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
