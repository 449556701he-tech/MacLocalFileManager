# MacLocalFileManager

MacLocalFileManager 是一个 no-LLM 的 macOS 本地中文文件搜索工具。当前实现到 v8 初始可用版，重点转向 macOS Spotlight 风格的本地聚合搜索体验。

对于中文文件名、Office/PDF 正文、图片 OCR、分类筛选和工程资料检索这类场景，它比 Apple Spotlight 和 Finder 搜索更直接、更好用。

## 已实现功能

- 默认扫描 Mac 内置磁盘文件，建立 SQLite 索引。
- 设置入口可管理扫描位置；U 盘和外接硬盘会提示确认后再加入扫描。
- 外接磁盘提示会跳过只包含安装器 App/PKG 的临时安装镜像卷。
- 支持中文文件名和路径子串搜索。
- 搜索排序由程序控制：
  1. 文件名完全匹配
  2. 文件名开头匹配
  3. 文件名包含
  4. 路径包含
  5. 同级别内按最近修改时间优先
- 搜索结果显示文件名、路径、扩展名、大小、修改时间、命中原因。
- 支持打开文件、在 Finder 中显示、复制完整路径、刷新文件索引。
- 支持 no-LLM 文档内容提取和搜索：`txt`、`md`、`csv`、`docx`、`xlsx`、`pdf`。
- 搜索结果区分文件名命中、路径命中、内容命中。
- 内容命中排在文件名命中和路径命中之后。
- 内容命中显示摘要；Excel 内容会尽量显示 `[Sheet 行号]`。
- Word/PDF 内容命中显示片段。
- 内容索引失败不会导致程序崩溃，会记录到 `file_contents.error`。
- 支持图片 OCR 搜索：`png`、`jpg`、`jpeg`、`heic`。
- OCR 使用 macOS Vision 系统能力；图片视觉语义当前使用离线确定性后端打通索引和搜索链路，真实 Core ML 图片理解模型尚未接入。
- OCR 文本写入 `file_ocr.ocr_text`。
- 搜索结果区分 OCR 命中，OCR 命中排在文件名、路径、文档内容之后。
- OCR 默认关闭，可在设置中打开并手动扫描；开启后才会识别图片文字。
- 支持增量索引：文件大小和修改时间没变时，不重复提取文档内容和 OCR。
- GUI 的“刷新文件索引”按钮只刷新文件名、路径、大小和修改时间，保证搜索主路径响应快。
- GUI 的“索引文档内容”和“扫描 OCR”是独立慢任务，不会跟随启动自动运行。
- 扫描状态会显示内容/OCR 的索引、跳过、失败数量。
- 扫描在后台线程运行，文稿目录文件较多时窗口仍可继续响应。
- 扫描时显示阶段进度：文件发现、写入索引、内容索引、OCR 识别。
- 扫描过程中也可以输入搜索，结果来自当前已完成的索引。
- 启动后不会自动执行重型扫描，避免输入搜索时和后台索引任务抢资源。
- 搜索会先由 SQLite 筛选候选结果，再由程序排序，避免大目录下点击搜索卡住界面。
- 文件名和路径支持模糊匹配，例如 `60图资` 可以匹配 `60亩图纸资料`。
- 支持按文件分类筛选：图片、文档、应用、网页、压缩包、其他。
- 支持工程文件分类筛选：图纸、CAD、清单；`dwg/dxf/dwt/dgn/ifc/rvt/skp` 等 CAD 文件单独归类，`gcfx/sgcfx` 单独归入清单。工程分类默认隐藏，可在设置中打开。
- 搜索结果按分类展示；图片结果会优先显示缩略图横排，其他文件显示列表。
- 支持本地语义搜索开关：通过本地同义词扩展和离线确定性向量匹配文件名、路径、文档内容、PDF 内容、OCR 文本和图片视觉索引，不调用在线 AI。
- 设置页提供离线语义索引开关、PDF/图片分项开关，以及语义索引数量和错误数量统计。
- `zip/7z/rar/tar/gz` 等压缩包在同等级搜索结果中会优先显示。
- 首次启动如果没有管理目录，会自动加入 Mac 全盘 `/`，但会跳过系统目录和外接磁盘。
- 文档内容提取有单文件大小限制、文本长度限制和 Office/PDF 超时保护；坏文件会记录到 `file_contents.error` 并继续处理后续文件。
- OCR 失败记录不会被永久跳过；下次扫描会重试失败图片。
- v6 已从界面移除整理功能，主线聚焦本地分类搜索。

## 安全边界

- 默认扫描 Mac 内置磁盘 `/`。
- 不扫描 `/System`、`/Library`、`~/Library`、`/Applications`。
- 默认全盘扫描会跳过 `/Volumes`；U 盘和外接硬盘需要用户在设置中确认加入。
- 忽略 `.git`、`node_modules`、`__pycache__`、`pycache`、`.DS_Store`。
- 当前版本不做 AI 问答。
- 不删除任何文件。
- 文件缺失时只把 `exists` 标记为 `0`，不会删除索引记录。
- 文档内容提取只读取本地文件，不调用在线服务。
- OCR 只读取本地图片，不调用在线服务；未安装 OCR 可选依赖时会记录错误，不会导致程序崩溃。

## 分类规则

规则文件位于 `rules/categories.yaml`。当前内置示例：

- 工资表：文件名包含“工资、工资表、薪资”，扩展名为 `xlsx/xls/csv`。
- 考勤表：文件名包含“考勤、打卡、出勤”，扩展名为 `xlsx/xls/csv`。
- 合同：文件名包含“合同、协议”，扩展名为 `pdf/docx`。
- 图纸：扩展名为 `dwg/dxf/pdf`，或文件名包含“图纸、平面图、立面图、大样”。
- 付款截图：文件名包含“付款、转账、收款”，扩展名为 `png/jpg/jpeg/heic`。

## 启动

开发方式启动：

```bash
cd MacLocalFileManager
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

首次扫描 Mac 内置磁盘只建立文件名和路径索引，优先保证中文文件名搜索可用。系统目录、用户 Library、应用目录和外接磁盘默认跳过。需要搜索文档正文时，手动点击“索引文档内容”；需要识别图片文字时，勾选“启用 OCR”后点击“扫描 OCR”。扫描会在后台执行，不会阻塞窗口。第二次及以后扫描会使用增量索引，文件大小和修改时间没变时会跳过内容提取和 OCR。

索引数据库保存到：

```text
~/Library/Application Support/MacLocalFileManager/file_index.sqlite3
```

打包后的 `.app` 可以直接双击运行，不需要从终端启动。

## 打包成 macOS App

```bash
cd MacLocalFileManager
packaging/build_macos_app.sh
```

构建完成后会生成：

```text
dist/MacLocalFileManager.app
```

可以直接双击运行，也可以拖到 `/Applications`。索引数据库仍会写入 `~/Library/Application Support/MacLocalFileManager/`，不会写进 `.app` 包内部。

生成可分享安装包：

```bash
cd MacLocalFileManager
packaging/build_dmg.sh
```

构建完成后会生成：

```text
dist/MacLocalFileManager.dmg
```

英文界面版本可通过 `MacLocalFileManager-English.spec` 构建，并打包为：

```text
dist/MacLocalFileManager-English.dmg
```

这是未公证的本地打包文件，分享给朋友后，对方第一次打开可能需要右键 App 选择“打开”。

依赖包括：

- `PySide6`：GUI。
- `PyYAML`：整理规则。
- `python-docx`：Word `.docx` 内容提取。
- `openpyxl`：Excel `.xlsx` 内容提取。
- `pypdf`：PDF 内容提取。

OCR 是可选能力。在 macOS 上要使用系统 Vision OCR，可额外安装：

```bash
cd MacLocalFileManager
source .venv/bin/activate
pip install -r requirements-ocr-macos.txt
```

如果不安装 OCR 可选依赖，普通文件名搜索和文档内容搜索仍可正常使用。扫描 OCR 时会记录 OCR 错误而不是崩溃。

如果已经创建过虚拟环境：

```bash
cd MacLocalFileManager
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## 运行测试

```bash
cd MacLocalFileManager
python3 -m unittest discover -s tests
```

使用项目虚拟环境运行：

```bash
cd MacLocalFileManager
.venv/bin/python -m unittest discover -s tests
```

## 版本边界

- v4 已实现图片 OCR 搜索开关和索引流程。
- v5 已实现增量索引、手动刷新和慢任务拆分。
- v6 已实现分类筛选、图片缩略图结果、后台搜索和本地语义扩展搜索。
- v7-1 已实现离线语义索引基础设施：语义表、向量存储、确定性测试后端、任务队列。
- v7-2 已实现 PDF 语义索引基础链路：PDF 内容分块、确定性向量索引、PDF 语义命中合并搜索。
- v7-3 已实现图片 OCR 语义索引基础链路：OCR 文本向量索引、图片文字语义命中合并搜索。
- v7-4 已实现图片视觉语义索引基础链路：图片文件向量索引、增量跳过、图片视觉语义命中合并搜索。
- v7-5 已实现语义设置页集成、语义索引统计展示、PyInstaller 语义模块打包配置检查。
- v7-6 已完成隔离数据目录运行验证、安装镜像卷过滤、搜索框后台回填 UI 测试，并重新生成 `.app` 和 `.dmg`。
- v7-7 已新增图纸/CAD/清单分类，移除主界面左侧扫描范围栏，默认启动补齐全盘扫描，并调整为更扁平的浅色半透明界面。
- v8 初始版已改为类 Spotlight 的无边框透明窗口：折叠态位于屏幕上方黄金分割阅读位，输入后展开居中；支持拖动后保持手动位置；语义搜索入口从首页移入设置；图纸/CAD/清单默认隐藏，可在设置中开启。
- 真正的 Core ML 图片视觉模型、视频抽帧识别、音频转写索引尚未实现，后续可接入本地模型或系统框架，不接入在线 AI。
- 已验证打包后的 `.app` 可用隔离数据目录启动；Computer Use 当前只能读取窗口状态，无法向该 Qt 输入框写入文本，因此输入交互通过 PySide 自动化测试覆盖。
- 文件系统事件监听尚未实现，后续可用于自动刷新索引。
- 菜单栏常驻尚未实现，后续可作为 macOS 日常入口。
- 全局快捷键打开搜索框尚未实现，后续可作为快速检索入口。
