from __future__ import annotations

from pathlib import Path


CATEGORY_ALL = "all"
CATEGORY_SMART = "smart"
CATEGORY_IMAGES = "images"
CATEGORY_DOCUMENTS = "documents"
CATEGORY_DRAWINGS = "drawings"
CATEGORY_CAD = "cad"
CATEGORY_BILLS = "bills"
CATEGORY_APPS = "apps"
CATEGORY_VIDEOS = "videos"
CATEGORY_AUDIO = "audio"
CATEGORY_FOLDERS = "folders"
CATEGORY_WEB = "web"
CATEGORY_ARCHIVES = "archives"
CATEGORY_OTHER = "other"


CATEGORY_LABELS = {
    CATEGORY_ALL: "全部",
    CATEGORY_SMART: "语义搜索",
    CATEGORY_IMAGES: "图片",
    CATEGORY_DOCUMENTS: "文档",
    CATEGORY_DRAWINGS: "图纸",
    CATEGORY_CAD: "CAD",
    CATEGORY_BILLS: "清单",
    CATEGORY_APPS: "应用",
    CATEGORY_VIDEOS: "视频",
    CATEGORY_AUDIO: "音频",
    CATEGORY_FOLDERS: "文件夹",
    CATEGORY_WEB: "网页",
    CATEGORY_ARCHIVES: "压缩包",
    CATEGORY_OTHER: "其他",
}

IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "heic", "heif", "webp", "gif", "bmp", "tiff", "tif"}
CAD_EXTENSIONS = {"dwg", "dxf", "dwt", "dws", "dgn", "ifc", "rvt", "rfa", "skp", "3dm", "step", "stp", "iges", "igs"}
BILL_EXTENSIONS = {"gcfx", "sgcfx"}
DRAWING_KEYWORDS = {
    "图纸",
    "平面图",
    "总平",
    "总图",
    "立面图",
    "剖面图",
    "节点图",
    "详图",
    "大样",
    "施工图",
    "竣工图",
    "建筑图",
    "结构图",
    "机电图",
    "暖通",
    "给排水",
    "强电",
    "弱电",
    "幕墙",
}
BILL_KEYWORDS = {"清单", "工程量", "预算", "招标控制价", "造价", "计价", "结算", "签证"}
DOCUMENT_EXTENSIONS = {
    "txt",
    "md",
    "csv",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "pdf",
    "pages",
    "numbers",
    "key",
    "rtf",
}
APP_EXTENSIONS = {"app", "ipa", "dmg", "pkg"}
VIDEO_EXTENSIONS = {"mp4", "mov", "m4v", "avi", "mkv", "webm", "flv", "wmv", "3gp", "ts"}
AUDIO_EXTENSIONS = {"mp3", "m4a", "wav", "aac", "flac", "aiff", "ogg", "wma", "mid", "midi"}
WEB_EXTENSIONS = {"html", "htm", "webloc", "url", "webarchive"}
ARCHIVE_EXTENSIONS = {"zip", "7z", "rar", "tar", "gz", "tgz", "bz2", "xz"}


def classify_file(path: str, extension: str) -> str:
    if Path(path).suffix.lower() == ".app" or extension.lower() in APP_EXTENSIONS:
        return CATEGORY_APPS
    ext = extension.lower()
    name = Path(path).name.casefold()
    if ext in CAD_EXTENSIONS:
        return CATEGORY_CAD
    if ext in BILL_EXTENSIONS:
        return CATEGORY_BILLS
    if any(keyword in name for keyword in BILL_KEYWORDS):
        return CATEGORY_BILLS
    if any(keyword in name for keyword in DRAWING_KEYWORDS):
        return CATEGORY_DRAWINGS
    if ext in IMAGE_EXTENSIONS:
        return CATEGORY_IMAGES
    if ext in DOCUMENT_EXTENSIONS:
        return CATEGORY_DOCUMENTS
    if ext in VIDEO_EXTENSIONS:
        return CATEGORY_VIDEOS
    if ext in AUDIO_EXTENSIONS:
        return CATEGORY_AUDIO
    if ext in WEB_EXTENSIONS:
        return CATEGORY_WEB
    if ext in ARCHIVE_EXTENSIONS:
        return CATEGORY_ARCHIVES
    return CATEGORY_OTHER


def category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, CATEGORY_LABELS[CATEGORY_OTHER])
