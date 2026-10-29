# -*- mode: python ; coding: utf-8 -*-
# PyInstaller onedir spec for the caption engine sidecar, as shipped in the Gipformer Vietnamese
# add-on. Copied unchanged from CaptionHelper except for this header: dependency collection, CUDA
# filtering and hidden imports are identical, and all paths stay relative to this spec's own folder
# (installer/gipformer/engine), so the frozen output lands in the add-on staging tree.
#   build-addon-windows.ps1 -> <venv>/Scripts/pyinstaller engine/caption_engine.spec --noconfirm --clean
# Output: <distpath>/caption-engine/caption-engine.exe + _internal/
#
# faster-whisper + CTranslate2 + PyAV + onnxruntime (Silero VAD, silero_vad_v6.onnx ships in the faster-whisper wheel)
# and sherpa-onnx (gipformer ASR + Silero VAD via sherpa's own onnxruntime build; vibert-capu punctuation runs on onnxruntime)
# on both Windows and macOS. On Windows the NVIDIA cuBLAS/cuDNN DLLs are deliberately NOT collected (2 GiB): they
# ship as the separate "GPU pack" (docs/gpu-pack.md). macOS runs CPU int8 and has no CUDA runtime.
import os
import sys

from PyInstaller.utils.hooks import collect_all

ENGINE_DIR = os.path.abspath(os.path.join(SPECPATH))

datas = []
binaries = []
hiddenimports = ["word_timing", "engine_errors", "vi_itn", "vi_punct"]

# One import/data set for both OSes. These libraries use importlib/plugin discovery and ship native libraries or data files.
hiddenimports.append("backends.faster_whisper_backend")  # imported lazily through importlib
hiddenimports.append("backends.sherpa_backend")  # imported lazily through importlib
# sherpa_onnx: the pip package sherpa-onnx-core installs its native libraries (libonnxruntime, libsherpa-onnx-c-api) into the
# same sherpa_onnx/lib folder, so it is not a separate import package (`pip show -f sherpa-onnx-core`): one collect_all covers both.
for package in ("faster_whisper", "ctranslate2", "av", "onnxruntime", "sherpa_onnx"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

CUDA_PREFIXES = ("cublas", "cublaslt", "cudnn", "nvblas", "nvrtc", "cudart")

a = Analysis(
    [os.path.join(ENGINE_DIR, "caption_engine.py")],
    pathex=[ENGINE_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "matplotlib", "IPython", "nvidia", "triton"],
    noarchive=False,
    optimize=0,
)
a.binaries = [entry for entry in a.binaries if not os.path.basename(entry[0]).lower().startswith(CUDA_PREFIXES)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="caption-engine",
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
    a.datas,
    strip=False,
    upx=False,
    name="caption-engine",
)
