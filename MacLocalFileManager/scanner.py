from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from config import FULL_DISK_SKIPPED_CHILDREN, IGNORED_NAMES, protected_paths
from database import FileDatabase
from models import FileRecord, ScanStats


def is_protected_path(path: Path) -> bool:
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        resolved = path.expanduser().absolute()

    for protected in protected_paths():
        if resolved == protected or protected in resolved.parents:
            return True
    return False


def should_ignore_path(path: Path) -> bool:
    if path.name in IGNORED_NAMES:
        return True
    return any(part in IGNORED_NAMES for part in path.parts)


class DirectoryScanner:
    def __init__(self, db: FileDatabase) -> None:
        self.db = db

    def scan(self, roots: list[str | Path], progress_callback: Callable[[str], None] | None = None) -> ScanStats:
        resolved_roots = [Path(root).expanduser().resolve() for root in roots]
        records: list[FileRecord] = []
        seen_paths: set[str] = set()
        skipped_dirs = 0
        indexed_at = time.time()
        self._progress(progress_callback, f"开始扫描 {len(resolved_roots)} 个管理目录")

        for root in resolved_roots:
            if not root.exists() or not root.is_dir():
                continue
            if is_protected_path(root) or should_ignore_path(root):
                skipped_dirs += 1
                continue
            self._progress(progress_callback, f"正在扫描目录：{root}")

            for current_dir, dir_names, file_names in self._walk(root):
                dir_path = Path(current_dir)
                kept_dirs = []
                for dir_name in dir_names:
                    child = dir_path / dir_name
                    if should_skip_full_disk_child(root, child) or is_protected_path(child) or should_ignore_path(child):
                        skipped_dirs += 1
                    else:
                        kept_dirs.append(dir_name)
                dir_names[:] = kept_dirs

                for file_name in file_names:
                    file_path = dir_path / file_name
                    if should_ignore_path(file_path) or is_protected_path(file_path):
                        continue
                    try:
                        if not file_path.is_file():
                            continue
                        record = FileRecord.from_path(file_path, indexed_at)
                    except OSError:
                        continue
                    records.append(record)
                    seen_paths.add(record.path)
                    if len(records) % 100 == 0:
                        self._progress(progress_callback, f"正在扫描文件：已发现 {len(records)} 个")

        self._progress(progress_callback, f"文件发现完成：{len(records)} 个，正在写入索引")
        updated_files = self.db.upsert_files(records)
        self._progress(progress_callback, "正在检查已不存在的文件")
        missing_files = self.db.mark_missing_under_roots(resolved_roots, seen_paths)
        self._progress(progress_callback, f"文件扫描完成：更新 {updated_files} 个，缺失标记 {missing_files} 个")
        return ScanStats(
            scanned_files=len(records),
            updated_files=updated_files,
            missing_files=missing_files,
            skipped_dirs=skipped_dirs,
        )

    @staticmethod
    def _walk(root: Path):
        import os

        return os.walk(root)

    @staticmethod
    def _progress(progress_callback: Callable[[str], None] | None, message: str) -> None:
        if progress_callback is not None:
            progress_callback(message)


def should_skip_full_disk_child(root: Path, child: Path) -> bool:
    return root == Path("/") and child.parent == Path("/") and child.name in FULL_DISK_SKIPPED_CHILDREN
