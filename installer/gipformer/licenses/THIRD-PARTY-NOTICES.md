# Third-party notices — Gipformer Vietnamese add-on

This add-on is a **private, not release-cleared** local artifact. Two obligations are unresolved
and must be settled before any public distribution:

1. **CaptionHelper source permission.** The engine source snapshotted into this add-on comes from a
   checkout with no `LICENSE`/`COPYING` file whose `package.json` is `private` and declares no
   license. No license is granted by this notice. See `SOURCE-PROVENANCE.md` in the repository.
2. **Bundled FFmpeg codecs.** PyAV ships FFmpeg shared libraries. The libraries in this build
   report LGPL v3-or-later through their license API, while the FFmpeg build also enables
   libx264/libx265 (GPL components). Which of those obligations apply depends on the exact FFmpeg
   build shipped in the wheel, and the wheel does not include FFmpeg's license texts or a
   corresponding-source offer. Treat redistribution of `runtime/_internal/av*` as blocked until the
   owner documents the applicable licenses and corresponding-source availability.

## Runtime components (shipped in `runtime/`)

| Component | Version | Declared license | License text shipped here |
|---|---|---|---|
| CPython | recorded in `BUILD-INFO.txt` | PSF License Agreement | `python/LICENSE.txt` |
| PyInstaller bootloader | recorded in `BUILD-INFO.txt` | GPL-2.0-or-later **with the bootloader exception** (frozen applications are not covered by the GPL) | `pyinstaller/` |
| sherpa-onnx | recorded in `BUILD-INFO.txt` | Apache-2.0 | `sherpa-onnx/` |
| sherpa-onnx-core | recorded in `BUILD-INFO.txt` | Apache-2.0 | not shipped by the wheel; see `sherpa-onnx/` |
| ONNX Runtime | recorded in `BUILD-INFO.txt` | MIT | not shipped by the wheel; upstream `LICENSE.txt` (MIT) applies |
| faster-whisper | recorded in `BUILD-INFO.txt` | MIT | `faster-whisper/LICENSE` |
| CTranslate2 | recorded in `BUILD-INFO.txt` | MIT | not shipped by the wheel; upstream `LICENSE` (MIT) applies |
| PyAV | recorded in `BUILD-INFO.txt` | BSD-3-Clause | `pyav-ffmpeg/` |
| FFmpeg shared libraries (via PyAV) | whatever the PyAV wheel links | LGPL v3-or-later reported by the libraries; build enables libx264/libx265 | **not shipped — unresolved, see above** |
| NumPy | recorded in `BUILD-INFO.txt` | BSD-3-Clause | `numpy/` |
| tokenizers | recorded in `BUILD-INFO.txt` | Apache-2.0 | not shipped by the wheel; upstream `LICENSE` (Apache-2.0) applies |

Build-only tools (not shipped): pip, setuptools, PyInstaller's Python package, pyinstaller-hooks-contrib,
huggingface_hub and its dependencies, pefile, altgraph, pywin32-ctypes. Versions are pinned in
`installer/gipformer/requirements-win.lock.txt` in the repository.

## Model pack (shipped in `pack/`)

| Component | Source | License | Notice |
|---|---|---|---|
| gipformer 1.5 68M RNN-T (Vietnamese ASR) | `g-group-ai-lab/gipformer1.5-68M-rnnt` @ `dd9227dcd8705c13f33bdbe59728d546ab94480f` | MIT | `pack/NOTICE.md`, `pack/model/LICENSE` |
| ViBERT-capu re-punctuation (int8) | `welcomyou/vibert-capu-onnx` @ `a7754d037f4a9e29f7f3224f27acb60149eab874` | CC-BY-SA-4.0 | `pack/punct/ATTRIBUTION.md` |
| Silero VAD v4 | `k2-fsa/sherpa-onnx` release asset `silero_vad.onnx` (sha256 `9e2449e1…`) | MIT | `pack/NOTICE.md` |

Pack bytes are shipped unmodified; model preparation and its pinned hashes live in
`installer/gipformer/engine/prepare_model.py` (snapshot of CaptionHelper's tool).

## Pipeline attribution

The VAD gap-fill and ViBERT-capu usage are ported from `welcomyou/sherpa-vietnamese-asr` (MIT,
commit `350f5a4`; that upstream declares `Copyright (c) 2025 [Your Name]` verbatim). The
recognition → ITN → punctuation → word-timing pipeline is CaptionHelper's, verbatim.
