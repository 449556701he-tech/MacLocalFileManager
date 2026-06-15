from __future__ import annotations

import os


def current_language() -> str:
    return os.environ.get("MACLOCALFILEMANAGER_LANG", "zh").strip().lower()


def is_english() -> bool:
    return current_language().startswith("en")


EN_TRANSLATIONS = {
    "本地聚合搜索": "Local Search",
    "本机文件 · 图片 · 文档 · 剪切板": "Files · Images · Documents · Clipboard",
    "设置": "Settings",
    "扫描、索引和工程分类设置": "Scan, index, and engineering filter settings",
    "关闭": "Close",
    "搜索本机文件、图片、文档、剪切板": "Search local files, images, documents, clipboard",
    "搜索": "Search",
    "文件": "File",
    "扫描设置": "Scan Settings",
    "扫描范围": "Scan Scope",
    "刷新文件索引": "Refresh File Index",
    "语义搜索": "Semantic",
    "索引文档内容": "Index Document Content",
    "启用图片识别": "Enable Image Recognition",
    "图片识别会执行 OCR、图片标签和相似图片索引，适合后台慢慢跑。": "Image recognition runs OCR, image labels, and similar-image indexing in the background.",
    "扫描图片识别": "Scan Image Recognition",
    "已启用图片识别，点击“扫描图片识别”后开始索引": "Image recognition enabled. Click Scan Image Recognition to index.",
    "已关闭图片识别": "Image recognition disabled",
    "图片": "Images",
    "打开文件": "Open File",
    "在 Finder 中显示": "Show in Finder",
    "复制完整路径": "Copy Full Path",
    "查找相似图片": "Find Similar Images",
    "就绪": "Ready",
    "默认全盘扫描": "Default Full-Disk Scan",
    "默认扫描": "Default Scan",
    "默认全盘扫描不能移除。": "The default full-disk scan cannot be removed.",
    "外接磁盘": "External Drive",
    "没有发现未加入扫描的外接磁盘。": "No unmanaged external drive was found.",
    "发现外接磁盘": "External Drive Found",
    "是否将外接磁盘加入扫描？": "Add this external drive to scanning?",
    "无法添加扫描位置": "Cannot Add Scan Location",
    "默认扫描 Macintosh HD 的用户文件，自动跳过系统、应用、缓存、安装镜像和开发依赖目录。U 盘和外接硬盘可在这里确认加入。": "Scans user files on Macintosh HD by default and skips system, app, cache, installer, and dependency folders. External drives can be added here.",
    "加入外接磁盘": "Add External Drive",
    "移除选中外接磁盘": "Remove Selected Drive",
    "完成": "Done",
    "离线语义索引": "Offline Semantic Index",
    "PDF 语义": "PDF Semantic",
    "图片语义": "Image Semantic",
    "显示选项": "Display Options",
    "工程模式：显示图纸 / CAD / 清单分类": "Engineering mode: show drawings / CAD / bills filters",
    "全部": "All",
    "文档": "Documents",
    "图纸": "Drawings",
    "清单": "Bills",
    "应用": "Apps",
    "视频": "Videos",
    "音频": "Audio",
    "文件夹": "Folders",
    "网页": "Web",
    "压缩包": "Archives",
    "其他": "Other",
    "名称": "Name",
    "类型": "Type",
    "路径": "Path",
    "修改日期": "Modified",
    "大小": "Size",
    "命中": "Match",
    "内容摘要": "Snippet",
    "预览：当前为 UI 初版，美工确认后继续接入快捷键和剪切板。": "Preview: UI draft. Shortcuts and clipboard integration will follow after visual review.",
    "正在完成当前搜索，完成后关闭": "Finishing the current search, then closing",
    "正在后台扫描，请稍候": "Background scan is running, please wait",
    "正在后台运行": "Running in background: ",
    "窗口可以继续操作": "you can keep using the window",
    "正在搜索，继续输入不会卡住": "Searching. You can keep typing.",
    "正在搜索，窗口可以继续操作": "Searching. You can keep using the window.",
    "智能识别到": "Detected",
    "张图片": "images",
    "搜索到": "Found",
    "个文件": "files",
    "已复制完整路径": "Full path copied",
    "请先选中一张图片": "Select an image first",
    "相似图片只支持图片文件": "Similar image search only supports image files",
    "请先在设置中启用语义搜索并扫描图片语义": "Enable semantic search in Settings and scan image semantics first",
    "查找相似图片失败": "Find similar images failed",
    "相似图片": "Similar Images",
    "条结果": "results",
}


def tr(text: str) -> str:
    if not is_english():
        return text
    return EN_TRANSLATIONS.get(text, text)
