from __future__ import annotations

import shutil
import time
import uuid
from pathlib import Path

from database import FileDatabase
from models import MoveResult, OrganizeSuggestion
from organizer import unique_path


class SafeFileMover:
    def __init__(self, db: FileDatabase) -> None:
        self.db = db

    def execute_batch(self, suggestions: list[OrganizeSuggestion]) -> list[MoveResult]:
        batch_id = uuid.uuid4().hex
        results: list[MoveResult] = []

        for suggestion in suggestions:
            move_time = time.time()
            source = Path(suggestion.source_path).expanduser()
            preferred_target = Path(suggestion.target_path).expanduser()

            if not source.exists() or not source.is_file():
                message = "源文件不存在"
                self.db.log_move(batch_id, source, preferred_target, move_time, "failed", message)
                results.append(MoveResult(str(source), str(preferred_target), "failed", message))
                continue

            try:
                target = unique_path(preferred_target, db=self.db)
                if source.resolve() == target.resolve():
                    self.db.log_move(batch_id, source, target, move_time, "skipped", "源路径和目标路径相同")
                    results.append(MoveResult(str(source), str(target), "skipped", "源路径和目标路径相同"))
                    continue

                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(target))
                self.db.update_file_after_move(source, target)
                self.db.log_move(batch_id, source, target, move_time, "moved")
                results.append(MoveResult(str(source), str(target), "moved"))
            except Exception as exc:  # noqa: BLE001 - surface the failure without crashing the app.
                self.db.log_move(batch_id, source, preferred_target, move_time, "failed", str(exc))
                results.append(MoveResult(str(source), str(preferred_target), "failed", str(exc)))

        return results

    def undo_last_batch(self) -> list[MoveResult]:
        batch_id = self.db.latest_moved_batch_id()
        if batch_id is None:
            return []

        return self._undo_rows(list(reversed(self.db.fetch_move_logs(batch_id=batch_id, status="moved"))))

    def undo_all_batches(self) -> list[MoveResult]:
        return self._undo_rows(list(reversed(self.db.fetch_move_logs(status="moved"))))

    def _undo_rows(self, rows) -> list[MoveResult]:
        undo_batch_id = f"undo-{uuid.uuid4().hex}"
        results: list[MoveResult] = []

        for row in rows:
            source = Path(row["new_path"]).expanduser()
            preferred_target = Path(row["old_path"]).expanduser()
            move_time = time.time()

            if not source.exists() or not source.is_file():
                message = "撤销失败：移动后的文件不存在"
                self.db.update_move_log_status(row["id"], "undo_failed", message)
                self.db.log_move(undo_batch_id, source, preferred_target, move_time, "undo_failed", message)
                results.append(MoveResult(str(source), str(preferred_target), "undo_failed", message))
                continue

            try:
                target = unique_path(preferred_target, db=self.db)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(target))
                self.db.update_file_after_move(source, target)
                self.db.update_move_log_status(row["id"], "undone")
                self.db.log_move(undo_batch_id, source, target, move_time, "undo_moved")
                results.append(MoveResult(str(source), str(target), "undo_moved"))
            except Exception as exc:  # noqa: BLE001
                self.db.update_move_log_status(row["id"], "undo_failed", str(exc))
                self.db.log_move(undo_batch_id, source, preferred_target, move_time, "undo_failed", str(exc))
                results.append(MoveResult(str(source), str(preferred_target), "undo_failed", str(exc)))

        return results
