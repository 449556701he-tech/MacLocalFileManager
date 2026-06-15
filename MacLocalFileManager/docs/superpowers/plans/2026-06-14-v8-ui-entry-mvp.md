# v8 UI Entry MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a first visual UI draft for review: a search-first main window with less toolbar clutter, clearer result zones, and visible placeholders for quick search, semantic image search, and clipboard entry.

**Architecture:** Keep the existing PySide6 `MainWindow` and database/search flow. Change the UI composition, object names, and stylesheet only enough to produce a reviewable first draft, while leaving model backends and global hotkey implementation for later tasks.

**Tech Stack:** Python, PySide6, unittest, offscreen Qt rendering.

---

## File Structure

- Modify `MacLocalFileManager/ui/main_window.py`
  - Rebuild the top region into a search hero, compact mode chips, and a utility toolbar.
  - Add visible quick-entry placeholders: "快速入口", "剪切板", and semantic status text.
  - Make image results use a larger grid area.
  - Update stylesheet to a restrained macOS utility look with stable dimensions.
- Modify `MacLocalFileManager/tests/test_main_window_runtime.py`
  - Add UI structure tests that instantiate the window offscreen and assert expected object names, labels, placeholder text, and dimensions.
- Create `MacLocalFileManager/tools/render_ui_preview.py`
  - Render the main window offscreen into `MacLocalFileManager/docs/ui/v8-ui-entry-mvp.png` for visual review.
- Create `MacLocalFileManager/docs/ui/`
  - Store the generated screenshot for user confirmation.

## Task 1: UI Structure Test

**Files:**
- Modify: `MacLocalFileManager/tests/test_main_window_runtime.py`
- Modify later: `MacLocalFileManager/ui/main_window.py`

- [ ] **Step 1: Write the failing test**

Add this test method to `MainWindowRuntimeTest`:

```python
    def test_v8_search_first_layout_exposes_reviewable_ui_sections(self) -> None:
        self.assertEqual(self.window.search_input.placeholderText(), "搜索文件、图片内容、截图文字、合同、图纸")
        self.assertEqual(self.window.hero_title.text(), "本地聚合搜索")
        self.assertIn("⌘K", self.window.quick_entry_label.text())
        self.assertEqual(self.window.quick_search_button.text(), "快速入口")
        self.assertEqual(self.window.clipboard_button.text(), "剪切板")
        self.assertEqual(self.window.semantic_status_label.text(), "图片语义：待接入真实本地模型")
        self.assertGreaterEqual(self.window.image_list.iconSize().width(), 148)
        self.assertGreaterEqual(self.window.image_list.maximumHeight(), 220)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/hjx/Documents/mac\ ai\ 搜索/MacLocalFileManager
python3 -m unittest tests.test_main_window_runtime.MainWindowRuntimeTest.test_v8_search_first_layout_exposes_reviewable_ui_sections
```

Expected: FAIL because `hero_title`, `quick_entry_label`, `quick_search_button`, `clipboard_button`, or the new placeholder text does not exist yet.

- [ ] **Step 3: Implement minimal UI structure**

In `ui/main_window.py`, replace the current top-row construction in `_build_ui()` with:

```python
        header = QWidget()
        header.setObjectName("searchHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setSpacing(10)

        title_row = QHBoxLayout()
        self.hero_title = QLabel("本地聚合搜索")
        self.hero_title.setObjectName("heroTitle")
        self.quick_entry_label = QLabel("⌘K 快速调取 · 本机索引 · 不调用在线 AI")
        self.quick_entry_label.setObjectName("quickEntryHint")
        title_row.addWidget(self.hero_title)
        title_row.addStretch(1)
        title_row.addWidget(self.quick_entry_label)
        header_layout.addLayout(title_row)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchField")
        self.search_input.setPlaceholderText("搜索文件、图片内容、截图文字、合同、图纸")
        self.search_input.setMinimumHeight(48)
        self.search_input.textChanged.connect(lambda: self.search_timer.start(260))
        self.search_input.returnPressed.connect(self.run_search)
        self.search_button = QPushButton("搜索")
        self.search_button.setObjectName("primarySearchButton")
        self.search_button.setMinimumHeight(42)
        self.search_button.clicked.connect(self.run_search)
        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(self.search_button)
        header_layout.addLayout(search_row)

        utility_row = QHBoxLayout()
        utility_row.setSpacing(8)
        self.quick_search_button = QPushButton("快速入口")
        self.quick_search_button.setProperty("utilityButton", True)
        self.quick_search_button.setToolTip("后续接入菜单栏和全局快捷键。")
        self.clipboard_button = QPushButton("剪切板")
        self.clipboard_button.setProperty("utilityButton", True)
        self.clipboard_button.setToolTip("后续读取当前剪切板文本、文件 URL 和路径。")
        self.rescan_button = QPushButton("刷新文件索引")
        self.content_button = QPushButton("索引文档内容")
        self.ocr_checkbox = QCheckBox("启用 OCR")
        self.ocr_checkbox.setToolTip("OCR 是慢任务；开启后点击“扫描 OCR”才会识别图片文字。")
        self.ocr_scan_button = QPushButton("扫描 OCR")
        self.settings_button = QPushButton("设置")
        self.semantic_status_label = QLabel("图片语义：待接入真实本地模型")
        self.semantic_status_label.setObjectName("semanticStatus")
        for button in [self.rescan_button, self.content_button, self.ocr_scan_button, self.settings_button]:
            button.setProperty("utilityButton", True)
            button.setMinimumHeight(32)
        self.rescan_button.clicked.connect(self.rescan_index)
        self.content_button.clicked.connect(self.rescan_content_index)
        self.ocr_checkbox.toggled.connect(self.set_ocr_enabled)
        self.ocr_scan_button.clicked.connect(self.rescan_ocr_index)
        self.settings_button.clicked.connect(self.open_settings_dialog)
        utility_row.addWidget(self.quick_search_button)
        utility_row.addWidget(self.clipboard_button)
        utility_row.addWidget(self.rescan_button)
        utility_row.addWidget(self.content_button)
        utility_row.addWidget(self.ocr_checkbox)
        utility_row.addWidget(self.ocr_scan_button)
        utility_row.addWidget(self.settings_button)
        utility_row.addStretch(1)
        utility_row.addWidget(self.semantic_status_label)
        header_layout.addLayout(utility_row)
        root_layout.addWidget(header)
```

Also update image grid settings in `_build_result_panel()`:

```python
        self.image_list.setIconSize(QSize(156, 112))
        self.image_list.setSpacing(12)
        self.image_list.setMaximumHeight(240)
```

- [ ] **Step 4: Run test to verify it passes**

Run the same focused test. Expected: PASS.

## Task 2: Visual Styling

**Files:**
- Modify: `MacLocalFileManager/ui/main_window.py`
- Test: `MacLocalFileManager/tests/test_main_window_runtime.py`

- [ ] **Step 1: Write the failing style test**

Add this test method:

```python
    def test_v8_visual_style_uses_search_header_and_compact_utilities(self) -> None:
        style = self.window.styleSheet()
        self.assertIn("QWidget#searchHeader", style)
        self.assertIn("QLabel#heroTitle", style)
        self.assertIn("QPushButton[utilityButton=\"true\"]", style)
        self.assertIn("QLabel#semanticStatus", style)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/hjx/Documents/mac\ ai\ 搜索/MacLocalFileManager
python3 -m unittest tests.test_main_window_runtime.MainWindowRuntimeTest.test_v8_visual_style_uses_search_header_and_compact_utilities
```

Expected: FAIL because stylesheet does not include the new selectors.

- [ ] **Step 3: Add styling**

Extend `_apply_macos_style()` with selectors for:

```css
QWidget#searchHeader
QLabel#heroTitle
QLabel#quickEntryHint
QPushButton#primarySearchButton
QPushButton[utilityButton="true"]
QLabel#semanticStatus
```

Use a light neutral background, blue only for active actions, 8-12px radii on controls, and stable sizes so toolbar text does not jump.

- [ ] **Step 4: Run style test**

Expected: PASS.

## Task 3: Render Preview Screenshot

**Files:**
- Create: `MacLocalFileManager/tools/render_ui_preview.py`
- Create output: `MacLocalFileManager/docs/ui/v8-ui-entry-mvp.png`

- [ ] **Step 1: Create screenshot script**

The script should:

```python
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
app = QApplication.instance() or QApplication([])
db = FileDatabase(tempfile.TemporaryDirectory().name + "/preview.sqlite3")
window = MainWindow(db)
window.resize(1280, 820)
window.show()
app.processEvents()
pixmap = window.grab()
pixmap.save(str(output_path))
```

- [ ] **Step 2: Run screenshot script**

Run:

```bash
cd /Users/hjx/Documents/mac\ ai\ 搜索/MacLocalFileManager
python3 tools/render_ui_preview.py
```

Expected: creates `docs/ui/v8-ui-entry-mvp.png`.

- [ ] **Step 3: Run relevant tests**

Run:

```bash
cd /Users/hjx/Documents/mac\ ai\ 搜索/MacLocalFileManager
python3 -m unittest tests.test_main_window_runtime tests.test_semantic_ui_settings
```

Expected: PASS.

- [ ] **Step 4: Stop for user review**

Send the screenshot path and ask the user to confirm visual direction before implementing menu bar, global hotkey, clipboard persistence, or real model backends.

## Self-Review

- Spec coverage: This plan covers the requested first UI confirmation milestone only. Real image/text semantic models, menu bar implementation, global hotkey implementation, and clipboard persistence remain future phases by design.
- Placeholder scan: No placeholder implementation steps are left; open product choices are intentionally deferred until visual confirmation.
- Type consistency: New attributes are `hero_title`, `quick_entry_label`, `quick_search_button`, `clipboard_button`, and `semantic_status_label`, all on `MainWindow`.
