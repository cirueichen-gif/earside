# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

block_cipher = None

# 專案根目錄
project_dir = Path(SPECPATH).resolve()

# 需要打包進 dist 的資料檔 (source, target_dir)
datas = [
    (str(project_dir / "personas"), "personas"),
    (str(project_dir / "presets"), "presets"),
    (str(project_dir / "config.example.toml"), "."),
    (str(project_dir / "models"), "models"),
]

# 動態載入或可選依賴所需的 hiddenimports
hiddenimports = [
    "sounddevice",
    "pyttsx3",
    "pyttsx3.drivers",
    "pyttsx3.drivers.sapi5",
    "mss",
    "soxr",
    "cv2",
    "onnxruntime",
    "silero_vad",
    "pystray",
    "PIL",
]

# 排除大型但未使用的科學計算/機器學習庫以縮減體積
excludes = [
    "matplotlib",
    "scipy",
    "pandas",
    "torch",
    "torchvision",
    "torchaudio",
    "IPython",
    "jupyter",
    "pytest",
]

a = Analysis(
    [str(project_dir / "launcher.py")],
    pathex=[str(project_dir / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

# 只留 CPU onnxruntime：砍 CUDA/TensorRT 的 DLL，dist 才不會 1.8GB。
_CUDA = (
    "onnxruntime_providers_cuda",
    "onnxruntime_providers_tensorrt",
    "cublas",
    "cudnn",
    "cufft",
    "curand",
    "cusolver",
    "cusparse",
    "nvrtc",
    "nvapi",
    "tensorrt",
)
a.binaries = [
    item for item in a.binaries if not any(p in item[0].lower() for p in _CUDA)
]

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="earside",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
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
    upx=False,
    upx_exclude=[],
    name="earside",
)
