# v8 本地智能搜索与 macOS 快速入口设计

## 背景

`MacLocalFileManager` 当前已具备中文文件名/路径搜索、文档内容索引、图片 OCR、离线语义索引表结构、确定性测试向量后端、图片缩略图结果和语义设置入口。v7 的核心价值是把搜索链路打通，但图片视觉语义仍是确定性后端，文档语义也不是实际本地 embedding 模型；菜单栏、全局快捷键、剪切板入口和更直观的搜索界面尚未完成。

v8 的目标是把项目从“功能可验证”推进到“日常可用”：搜索入口更像 macOS 原生工具，图片搜索接近照片相册的直观体验，文档和截图搜索更聪明，同时继续坚持本地运行、不接在线 AI、不做音视频识别。

## 范围

### 做

- 接入真实本地图片语义后端，用于按内容搜索图片和截图。
- 接入真实本地文本语义后端，用于 PDF、Office、OCR 文本和文件名路径的语义搜索。
- 保留并增强 macOS Vision OCR。
- 增加 macOS 快速入口：菜单栏常驻、全局快捷键、轻量 Spotlight 式搜索窗。
- 重做主界面信息架构，让搜索框、分类、图片网格和命中原因更直接。
- 增加剪切板入口，读取当前剪切板文本、文件 URL 和路径文本，作为快速搜索条件或临时搜索范围。
- 保持慢任务可控：用户显式开启、显式扫描、可看到进度和失败数。

### 不做

- 不做视频抽帧识别。
- 不做音频转写。
- 不调用在线 AI 服务。
- 不依赖 Photos.app 私有搜索索引。
- 不自动整理、移动或删除用户文件。
- 不默认在首次启动时跑重型语义模型。

## Apple 能力边界

公开可依赖的系统能力：

- PhotoKit 可读取照片库资源、相册和元数据，适合把用户授权的照片资源纳入索引，但不能作为“直接调用苹果照片 App 搜索结果”的稳定方案。
- Vision `VNRecognizeTextRequest` 可继续用于图片 OCR。
- Vision FeaturePrint 可生成图片特征并计算图片相似度，适合“找相似图片/截图”，但它不是中文自然语言搜图的完整替代。
- Core ML 可承载本地图文模型，例如 CLIP 类模型，用于“用中文描述搜索图片内容”。

因此，v8 的图片搜索采用组合方案：

1. OCR 解决图片中文字。
2. FeaturePrint 解决相似图片。
3. Core ML/本地 CLIP 类图文向量解决自然语言搜图。

## 产品结构

### 主窗口

主窗口改成搜索优先：

- 顶部一个清晰的大搜索框，占据主要视觉焦点。
- 搜索框下方是紧凑分类：全部、图片、文档、图纸、CAD、清单、剪切板、语义。
- 图片结果用更大的缩略图网格展示，文件名和命中原因放在缩略图下方。
- 文档、图纸、CAD、清单保留紧凑列表，突出文件名、路径、修改时间和命中片段。
- 命中原因明确区分：文件名、路径、正文、OCR、图片语义、相似图片、剪切板。

### 快速搜索窗

新增轻量弹窗，用全局快捷键唤起：

- 只显示搜索框、分类切换和前若干条结果。
- 回车打开第一条结果。
- 方向键切换结果。
- 支持复制路径、Finder 中显示、打开文件。
- 不承担设置和管理任务，避免变成第二个主窗口。

### 设置页

设置页按任务归类：

- 扫描范围：管理目录、外接盘提示。
- 索引能力：文档内容、OCR、图片语义、文本语义。
- 快速入口：菜单栏开关、全局快捷键、开机启动预留。
- 剪切板：是否启用当前剪切板读取、是否记录 App 运行期间的剪切板历史。
- 维护：重建语义索引、清空失败状态、查看索引统计。

## 技术架构

```text
macOS Entry
  | menu bar, global hotkey, clipboard reader
  v
UI Layer
  | main window, quick search window, settings
  v
Hybrid Searcher
  | filename/path exact and fuzzy
  | document/OCR keyword
  | text semantic
  | image semantic
  | image similarity
  | clipboard scope
  v
SQLite Index
  | files
  | file_contents
  | file_ocr
  | semantic_items
  | semantic_embeddings
  | semantic_models
  | semantic_jobs
  | clipboard_items
  v
Local Recognition Backends
  | Vision OCR
  | Vision FeaturePrint
  | local text embedding
  | local image-text embedding
```

### 后端接口

现有 `BaseEmbeddingBackend` 保留，并拆清用途：

- `TextEmbeddingBackend.embed_text(text)`：文档、OCR、查询文本。
- `ImageTextEmbeddingBackend.embed_text(text)`：把自然语言查询嵌入到图文向量空间。
- `ImageTextEmbeddingBackend.embed_image(path)`：把图片嵌入到图文向量空间。
- `ImageSimilarityBackend.embed_image(path)`：Vision FeaturePrint 或等价后端。

确定性后端继续用于单元测试和无模型环境，但生产默认不能再宣称“图片视觉语义已完成”，必须在 UI 中显示真实后端状态。

### 模型策略

第一阶段优先选择低风险本地方案：

- 文本语义：先接本地可运行的轻量 embedding 后端，保留后端可替换能力。
- 图片语义：优先预留 Swift/Core ML helper 边界；如果模型转换和打包成本过高，先用 Python helper 验证召回质量，再固化到 Core ML。
- 相似图片：优先 Vision FeaturePrint，因为它是系统公开能力，适合快速提升图片体验。

所有模型必须记录：

- `model_key`
- `version`
- `dimensions`
- `modality`
- `created_at`

模型变更时，设置页提示重建对应语义索引。

### 索引和任务

语义索引继续走独立慢任务：

- 文件名/路径索引保持最快路径。
- 文档内容索引、OCR、语义索引不随首次启动自动重型运行。
- 语义索引支持状态统计：待处理、完成、失败、跳过。
- 失败不阻断后续文件，错误写入数据库。
- 增量依据仍以文件大小、修改时间和模型版本为主。

新增 `clipboard_items` 表用于 App 运行期间的剪切板历史：

- `id`
- `kind`: text, file_url, path
- `content`
- `normalized_content`
- `created_at`
- `source_app` 可选
- `expires_at` 可选

默认只读取当前剪切板；历史记录需要用户显式开启。

## 搜索排序

排序原则：精确命中优先，语义补充，不让语义结果压过明确文件名命中。

推荐顺序：

1. 文件名完全匹配。
2. 文件名开头匹配。
3. 文件名包含或模糊匹配。
4. 路径包含或模糊匹配。
5. 文档正文/OCR 关键词命中。
6. 剪切板当前内容关联命中。
7. 文本语义命中。
8. 图片 OCR 语义命中。
9. 图片内容语义命中。
10. 相似图片命中。

图片分类下可调整权重，让图片内容语义和相似图片更靠前；全部分类下仍保守排序。

## 分期

### v8-1 架构和入口骨架

- 写清后端接口边界。
- 增加菜单栏常驻入口。
- 增加全局快捷键设置和快速搜索窗骨架。
- 增加剪切板当前内容读取。
- 调整 README 和设置页文案，明确真实模型状态。

### v8-2 图片搜索增强

- 接入 Vision FeaturePrint 相似图片后端。
- 新增相似图片索引和搜索理由。
- 增加图片结果网格改版。
- 用小型 fixture 验证相似图片排序。

### v8-3 真实图文语义

- 增加本地图文 embedding 后端。
- 支持自然语言搜图片内容。
- 模型版本变化触发重建提示。
- 对截图、合同照片、付款截图、图纸照片建立验证集。

### v8-4 真实文本语义

- 增加本地文本 embedding 后端。
- 覆盖 PDF、Office、OCR 文本。
- 让中文近义搜索、合同/清单/付款类搜索更稳定。

### v8-5 主界面收敛

- 搜索优先重构主窗口。
- 设置页分组。
- 图片网格、文档列表、命中原因统一。
- 增加快捷键和菜单栏的端到端 UI 测试。

## 验证

自动化测试：

- 后端接口测试：确定性后端、FeaturePrint 后端、文本后端可替换。
- 向量存储测试：模型版本变化后不会误用旧 embedding。
- 搜索排序测试：文件名命中仍高于语义命中。
- 图片搜索测试：相似图片和图片语义命中返回正确原因。
- 剪切板测试：文本、路径、文件 URL 都能进入搜索流程。
- UI 测试：快速搜索窗可输入、选择、打开结果。

人工验证：

- 搜“付款截图”能找到 OCR 或图片语义相关截图。
- 搜“海边/建筑/合同照片/表格截图”能返回合理图片。
- 快捷键唤起窗口速度可接受。
- 主窗口在大量结果下不拥挤、不遮挡、不误导。

## 风险和缓解

- Core ML 图文模型打包体积过大：先用 helper 验证，再决定是否内置或用户可选下载。
- PyObjC 调系统框架能力不完整：必要时用 Swift helper 暴露稳定命令行接口。
- 语义索引耗时：默认关闭重型任务，设置页明确进度和失败数。
- 剪切板隐私敏感：默认只读当前剪切板，不默认记录历史。
- 图片语义召回不稳定：保留 OCR、文件名、路径、相似图片多路混合，不把单一模型当唯一入口。

## 开放问题

- 全局快捷键默认值建议使用 `Option+Space` 还是用户首次设置时再指定。
- 图片语义模型是否允许单独下载，还是必须随 App 打包。
- 剪切板历史是否需要加保留时长，例如 24 小时或仅本次运行。
- 是否把 Photos Library 作为一个可选扫描源，默认不启用，用户授权后只索引图片和元数据。

## 参考

- Apple PhotoKit: `https://developer.apple.com/documentation/photokit/fetching-assets`
- Apple Vision OCR: `https://developer.apple.com/documentation/vision/recognizing-text-in-images`
- Apple Vision FeaturePrint: `https://developer.apple.com/documentation/Vision/analyzing-image-similarity-with-feature-print`
