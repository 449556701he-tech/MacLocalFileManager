# v8 Spotlight Glass UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the busy manager-style home screen with a macOS-like aggregate search surface: collapsed by default, glass-like search shell, simplified filters, and results that expand only after typing.

**Architecture:** Keep the existing `MainWindow`, search workers, and result rendering. Change only the UI composition/state and stylesheet: hide maintenance controls from the home surface, expose a compact filter row only during search, keep hidden semantic state for existing search plumbing, and hide engineering categories unless a later settings toggle enables them.

**Tech Stack:** Python, PySide6, unittest, offscreen Qt screenshot rendering.

---

## Files

- Modify `MacLocalFileManager/ui/main_window.py`
  - Collapse homepage to one glass search shell.
  - Hide result/filter panels until query text is present.
  - Remove visible semantic chip.
  - Hide engineering categories: drawings, CAD, bills.
  - Move maintenance buttons off the main surface by keeping actions in menu/settings.
- Modify `MacLocalFileManager/tests/test_main_window_runtime.py`
  - Replace first UI draft assertions with Spotlight-style assertions.
  - Assert default collapsed state and expanded state after query.
- Modify `MacLocalFileManager/tools/render_ui_preview.py`
  - Keep typed-query preview for expanded-state screenshot.

## Task 1: Red Tests

- [ ] Add a test asserting the default homepage is collapsed:

```python
def test_v8_spotlight_home_is_collapsed_until_query(self) -> None:
    self.assertEqual(self.window.search_shell.objectName(), "searchShell")
    self.assertEqual(self.window.search_input.placeholderText(), "搜索本机文件、图片、文档、剪切板")
    self.assertFalse(self.window.filter_bar.isVisible())
    self.assertFalse(self.window.result_panel.isVisible())
    self.assertFalse(self.window.semantic_button.isVisible())
```

- [ ] Add a test asserting only general categories are visible after query:

```python
def test_v8_search_expands_with_general_categories_only(self) -> None:
    self.window.search_input.setText("付款截图")
    self.window.run_search()
    self.app.processEvents()

    visible_filters = [
        button.text()
        for button in self.window.category_buttons.values()
        if button.isVisible()
    ]
    self.assertIn("全部", visible_filters)
    self.assertIn("图片", visible_filters)
    self.assertIn("文档", visible_filters)
    self.assertNotIn("语义搜索", visible_filters)
    self.assertNotIn("图纸", visible_filters)
    self.assertNotIn("CAD", visible_filters)
    self.assertNotIn("清单", visible_filters)
```

Run each focused test with `.venv/bin/python -m unittest ...` and verify failure before implementation.

## Task 2: Implementation

- [ ] Change `_build_ui()` so the top-level shell is named `searchShell`.
- [ ] Hide utility controls from the main header; keep menu actions for scanning/settings.
- [ ] Store filter widget as `self.filter_bar` and hide it at startup.
- [ ] Store result panel as `self.result_panel` and hide it at startup.
- [ ] Build visible filters from only `all`, `images`, `documents`, `apps`, `archives`, `web`, `other`.
- [ ] Create `self.semantic_button` as a hidden checkable button for existing semantic search state.
- [ ] In `run_search()`, when the query is blank, call a helper that hides filters/results and returns home mode.
- [ ] In `_start_search()` or `run_search()`, show filters/results when the query is nonblank.

## Task 3: Style and Preview

- [ ] Update stylesheet selectors from `searchHeader` to `searchShell`.
- [ ] Use a translucent glass-like surface: `rgba`, subtle border, light shadow-friendly contrast, 16px radius or less.
- [ ] Keep homepage text minimal; no long visible explanatory copy.
- [ ] Regenerate `docs/ui/v8-ui-entry-mvp.png` through `tools/render_ui_preview.py`.

## Verification

Run:

```bash
cd /Users/hjx/Documents/mac\ ai\ 搜索/MacLocalFileManager
.venv/bin/python -m unittest tests.test_main_window_runtime tests.test_semantic_ui_settings
.venv/bin/python tools/render_ui_preview.py
```

Expected:

- Unit tests pass.
- Screenshot exists at `docs/ui/v8-ui-entry-mvp.png`.
- Screenshot shows expanded search results without visible semantic, drawing, CAD, or bills chips.

## Stop Point

Stop after the screenshot is generated and show it to the user for visual approval before implementing settings toggles, menu bar, global hotkey, clipboard persistence, or real semantic backends.
