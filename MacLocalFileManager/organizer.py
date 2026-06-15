from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from config import PROJECT_ROOT, normalize_text
from database import FileDatabase
from models import OrganizeSuggestion


DEFAULT_RULE_PATH = PROJECT_ROOT / "rules" / "categories.yaml"


class RuleOrganizer:
    def __init__(self, db: FileDatabase, rule_path: Path | str = DEFAULT_RULE_PATH) -> None:
        self.db = db
        self.rule_path = Path(rule_path)

    def generate_suggestions(self) -> list[OrganizeSuggestion]:
        rules = self.load_rules()
        managed_dirs = [Path(path) for path in self.db.list_managed_dirs()]
        suggestions: list[OrganizeSuggestion] = []
        reserved_targets: set[str] = set()

        for row in self.db.fetch_existing_files():
            matched = self.match_rule(row, rules)
            if matched is None:
                continue

            root = self._find_root(Path(row["path"]), managed_dirs)
            relative_parent = self._relative_parent(Path(row["path"]), root, matched["target_dir"])
            target_dir = root / matched["target_dir"] / relative_parent
            preferred_target = target_dir / row["filename"]
            if Path(row["path"]).resolve() == preferred_target.resolve():
                continue

            target_path = unique_path(preferred_target, reserved_targets, self.db)
            reserved_targets.add(str(target_path))

            suggestions.append(
                OrganizeSuggestion(
                    file_id=row["id"],
                    filename=row["filename"],
                    source_path=row["path"],
                    target_path=str(target_path),
                    category=matched["name"],
                    reason=matched["reason"],
                )
            )

        suggestions.sort(key=lambda item: (item.category, item.filename, item.source_path))
        return suggestions

    def load_rules(self) -> list[dict[str, Any]]:
        if not self.rule_path.exists():
            return []
        data = yaml.safe_load(self.rule_path.read_text(encoding="utf-8")) or {}
        categories = data.get("categories", [])
        if not isinstance(categories, list):
            return []
        return [rule for rule in categories if isinstance(rule, dict) and rule.get("name")]

    def match_rule(self, row: Any, rules: list[dict[str, Any]]) -> dict[str, str] | None:
        filename = normalize_text(row["filename"])
        path = normalize_text(row["path"])
        extension = normalize_text(row["extension"])

        for rule in rules:
            name = str(rule.get("name", "")).strip()
            target_dir = str(rule.get("target_dir") or name).strip()
            filename_keywords = [normalize_text(str(value)) for value in rule.get("filename_keywords", [])]
            path_keywords = [normalize_text(str(value)) for value in rule.get("path_keywords", [])]
            extensions = [normalize_text(str(value).lstrip(".")) for value in rule.get("extensions", [])]
            match_mode = str(rule.get("match_mode", "keyword_and_extension"))

            filename_hits = [keyword for keyword in filename_keywords if keyword and keyword in filename]
            path_hits = [keyword for keyword in path_keywords if keyword and keyword in path]
            extension_hit = extension in extensions if extensions else False
            keyword_hit = bool(filename_hits or path_hits)

            if not self._is_match(match_mode, keyword_hit, extension_hit, bool(extensions)):
                continue

            parts = []
            if filename_hits:
                parts.append("文件名关键词：" + "、".join(filename_hits))
            if path_hits:
                parts.append("路径关键词：" + "、".join(path_hits))
            if extension_hit:
                parts.append(f"扩展名：{extension}")
            reason = "；".join(parts) if parts else "规则匹配"

            return {
                "name": name,
                "target_dir": target_dir,
                "reason": reason,
            }

        return None

    @staticmethod
    def _is_match(match_mode: str, keyword_hit: bool, extension_hit: bool, has_extensions: bool) -> bool:
        if match_mode == "any":
            return keyword_hit or extension_hit
        if has_extensions:
            return keyword_hit and extension_hit
        return keyword_hit

    @staticmethod
    def _find_root(path: Path, managed_dirs: list[Path]) -> Path:
        resolved = path.resolve()
        matching_roots = []
        for root in managed_dirs:
            root_resolved = root.expanduser().resolve()
            if resolved == root_resolved or root_resolved in resolved.parents:
                matching_roots.append(root_resolved)
        if not matching_roots:
            return resolved.parent
        return max(matching_roots, key=lambda item: len(str(item)))

    @staticmethod
    def _relative_parent(path: Path, root: Path, target_dir: str) -> Path:
        try:
            relative_parent = path.resolve().parent.relative_to(root.resolve())
        except ValueError:
            relative_parent = Path()

        parts = relative_parent.parts
        if parts and parts[0] == target_dir:
            return Path(*parts[1:]) if len(parts) > 1 else Path()
        return relative_parent


def unique_path(preferred: Path, reserved_targets: set[str] | None = None, db: FileDatabase | None = None) -> Path:
    reserved_targets = reserved_targets or set()
    preferred = preferred.expanduser()
    if not _path_taken(preferred, reserved_targets, db):
        return preferred

    stem = preferred.stem
    suffix = preferred.suffix
    parent = preferred.parent
    counter = 1
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not _path_taken(candidate, reserved_targets, db):
            return candidate
        counter += 1


def _path_taken(path: Path, reserved_targets: set[str], db: FileDatabase | None) -> bool:
    resolved = str(path.expanduser().resolve())
    if resolved in reserved_targets:
        return True
    if path.exists():
        return True
    if db is not None and db.path_exists_in_index(path):
        return True
    return False
