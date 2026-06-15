# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


block_cipher = None
project_root = Path.cwd()


a = Analysis(
    ["app_en.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        ("rules", "rules"),
    ],
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "yaml",
        "docx",
        "openpyxl",
        "pypdf",
        "Foundation",
        "Vision",
        "Quartz",
        "objc",
        "semantic",
        "semantic.backends",
        "semantic.backends.base",
        "semantic.backends.deterministic",
        "semantic.chunker",
        "semantic.config",
        "semantic.indexer",
        "semantic.models",
        "semantic.scheduler",
        "semantic.search",
        "semantic.vector_store",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MacLocalFileManager-English",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MacLocalFileManager-English",
)
app = BUNDLE(
    coll,
    name="MacLocalFileManager-English.app",
    icon=None,
    bundle_identifier="local.maclocalfilemanager.english",
    info_plist={
        "CFBundleName": "MacLocalFileManager-English",
        "CFBundleDisplayName": "MacLocalFileManager English",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "NSHighResolutionCapable": True,
    },
)
