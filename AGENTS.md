# Mac 本地搜索项目规则

## 项目定位

本项目围绕 `MacLocalFileManager` 做 macOS 本地文件搜索、索引、UI 调试和后续搜索架构规划。

## 工作口径

- 默认使用中文沟通，命令、路径、API 名称保留原文。
- 主要源码入口是 `MacLocalFileManager/`；优先检查源码运行效果，再判断打包产物。
- 源码运行入口默认是：
  `cd "/Users/hjx/Documents/mac ai 搜索/MacLocalFileManager" && .venv/bin/python app.py`
- 如果 `dist` 或已打包 App 效果和源码不一致，先怀疑打包产物过期。
- SQLite 继续作为精确检索主干；Core Spotlight 只作为语义补充或系统集成补充。

## UI 与产品约束

- 当前方向是 Spotlight-like 本地搜索 UI：无边框半透明窗口、透明 root 背景、圆角搜索壳、filter chips 和结果面板。
- 折叠态搜索框位于上方 golden-ratio reading line 附近。
- 展开结果窗口在用户未手动拖拽前自动居中；用户拖拽后不再自动 reposition。
- 工程类 filters，例如 drawings、CAD、bills，默认隐藏，通过 settings 再开启。
- 不把工程类 filters 恢复成默认显眼项，除非用户明确要求。

## 交付与验证

- 正式输出放到 `outputs/`，临时脚本、截图、核查材料放到 `work/`。
- UI 变更优先用源码运行和截图验证；涉及打包时再重建 dist。
- 不提交本机索引数据库、虚拟环境、日志和隐私数据。
