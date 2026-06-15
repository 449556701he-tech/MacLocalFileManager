from __future__ import annotations

from config import normalize_text


SEMANTIC_TERMS = {
    "海边": ["海", "海岸", "海滩", "沙滩", "浪", "海浪", "海景", "船", "游艇", "三亚", "旅游", "beach", "sea", "ocean"],
    "旅行": ["旅游", "攻略", "行程", "酒店", "机票", "出行", "vlog", "trip", "travel"],
    "图纸": ["平面图", "立面图", "大样", "节点", "施工图", "竣工图", "dwg", "dxf", "cad"],
    "合同": ["协议", "签约", "甲方", "乙方", "盖章", "contract"],
    "付款": ["支付", "转账", "收款", "回单", "发票", "请款", "payment"],
    "照片": ["图片", "截图", "相册", "photo", "image", "jpg", "png"],
    "视频": ["录像", "影片", "宣传片", "vlog", "movie", "video", "mp4", "mov"],
    "音频": ["录音", "音乐", "语音", "audio", "music", "mp3", "m4a", "wav"],
    "压缩包": ["zip", "7z", "rar", "tar", "备份", "归档"],
}


def expand_query(query: str) -> list[str]:
    normalized = normalize_text(query)
    if not normalized:
        return []

    expanded: list[str] = []
    for key, values in SEMANTIC_TERMS.items():
        normalized_key = normalize_text(key)
        if normalized_key in normalized or any(normalize_text(value) in normalized for value in values):
            expanded.extend(normalize_text(value) for value in values)

    tokens = [token for token in expanded if token and token != normalized]
    seen = set()
    unique_tokens = []
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        unique_tokens.append(token)
    return unique_tokens[:24]
