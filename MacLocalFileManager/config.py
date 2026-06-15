import sys
import os
from pathlib import Path
import unicodedata


APP_NAME = "MacLocalFileManager"
PROJECT_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
SOURCE_ROOT = Path(__file__).resolve().parent
USER_DATA_DIR = Path.home() / "Library" / "Application Support" / APP_NAME
USER_LOG_DIR = Path.home() / "Library" / "Logs" / APP_NAME
DATA_DIR = Path(os.environ.get("MACLOCALFILEMANAGER_DATA_DIR", USER_DATA_DIR)).expanduser()
LOG_DIR = Path(os.environ.get("MACLOCALFILEMANAGER_LOG_DIR", USER_LOG_DIR)).expanduser()
DEFAULT_DB_PATH = DATA_DIR / "file_index.sqlite3"
MAX_CONTENT_FILE_SIZE_BYTES = 50 * 1024 * 1024
MAX_EXTRACTED_TEXT_CHARS = 1_000_000
CONTENT_EXTRACTION_TIMEOUT_SECONDS = 20
SUBPROCESS_EXTRACT_EXTENSIONS = {"docx", "xlsx", "pdf"}

IGNORED_NAMES = {
    ".git",
    "node_modules",
    "__pycache__",
    "pycache",
    ".DS_Store",
    ".DocumentRevisions-V100",
    ".Spotlight-V100",
    ".TemporaryItems",
    ".Trashes",
    ".Trash",
    ".fseventsd",
    ".vol",
}

FULL_DISK_SKIPPED_CHILDREN = {
    "Applications",
    "Library",
    "System",
    "Volumes",
    "bin",
    "cores",
    "dev",
    "etc",
    "opt",
    "private",
    "sbin",
    "tmp",
    "usr",
    "var",
}


def protected_paths() -> set[Path]:
    home = Path.home()
    return {
        Path("/System").resolve(),
        Path("/Library").resolve(),
        (home / "Library").resolve(),
        Path("/Applications").resolve(),
    }


def ensure_app_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def default_managed_dirs() -> list[Path]:
    return [Path("/")]


def normalize_text(value: str) -> str:
    """Normalize text for deterministic Chinese substring search."""
    value = unicodedata.normalize("NFC", value or "")
    return value.casefold().strip()
