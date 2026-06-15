# MacLocalFileManager

MacLocalFileManager 是一个免费开源的 macOS 本地聚合搜索工具，目标是做成更接近 Spotlight 的轻量入口：打开即搜，输入后展开结果，尽量不打扰当前工作流。

当前版本聚焦本机文件、图片、文档、剪切板方向的本地检索体验，不依赖在线 AI，不上传文件内容。

A free and open-source Spotlight-like local search tool for macOS.

## 当前亮点

- macOS Spotlight 风格的无边框半透明窗口。
- 折叠态在屏幕上方黄金分割阅读位打开，输入后展开并居中。
- 支持手动拖动窗口；拖动后不再自动改变用户摆放的位置。
- 搜索本地文件名、路径、文档内容、PDF、Office 文档和图片 OCR 文本。
- 图片结果优先以缩略图展示，其他文件以列表展示。
- 支持分类筛选：图片、文档、应用、压缩包、网页、其他。
- 工程类筛选（图纸 / CAD / 清单）默认隐藏，可在设置中打开。
- 支持本地离线语义索引基础链路，不调用在线服务。
- 默认跳过系统目录、应用目录、用户 Library、外接盘和开发依赖目录。
- 不删除文件，只维护本地 SQLite 索引。

## 安装使用

目前发布的是初始可用版，macOS 上可直接使用本地打包产物：

```text
MacLocalFileManager/dist/MacLocalFileManager.dmg
```

打开 DMG 后将 App 拖到 Applications。由于当前未做 Apple notarization，第一次打开可能需要右键 App 选择“打开”。

## 源码运行

```bash
cd MacLocalFileManager
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

索引数据库保存在：

```text
~/Library/Application Support/MacLocalFileManager/file_index.sqlite3
```

## 打包

生成 macOS App：

```bash
cd MacLocalFileManager
packaging/build_macos_app.sh
```

生成 DMG：

```bash
cd MacLocalFileManager
packaging/build_dmg.sh
```

## 测试

```bash
cd MacLocalFileManager
.venv/bin/python -m unittest discover -s tests
```

## 开源协议

本项目采用 MIT License，免费开源。

## 支持项目

如果这个工具对你有帮助，欢迎给项目一个 Star。

如果愿意支持后续开发，也欢迎自愿打赏。二维码收款图会在后续版本补充到这里。

## 状态说明

这是一个早期初始版，当前优先打磨 macOS 本地搜索体验。后续计划包括全局快捷键、菜单栏入口、更加稳定的索引刷新机制和更完善的本地图片理解能力。
