---
phase: 1
title: "Runtime and local add-on packaging"
status: done
status-note: "artifact built; public release still gated by redistribution clearance"
priority: P2
effort: ""
dependencies: []
---

# Phase 1: Runtime and local add-on packaging

## Goal

Produce one independently usable Windows x64 CPU add-on ZIP from a recorded CaptionHelper source snapshot and verified model pack. Build tools may use network; the installed runtime must not.

## Inputs and evidence

CaptionHelper is read-only. Existing inputs:

- `D:/Project/AdobePlugin/CaptionHelper/engine/caption_engine.py:1-19,125-160`: CLI/protocol and freeze support.
- `D:/Project/AdobePlugin/CaptionHelper/engine/backends/sherpa_backend.py:69-87,232-288`: decoder dependency and recognition pipeline.
- `D:/Project/AdobePlugin/CaptionHelper/engine/caption_engine.spec:20-48`: collects both backends and native libraries; excludes CUDA DLLs.
- `D:/Project/AdobePlugin/CaptionHelper/scripts/build-engine-windows.ps1:38-67,65-100`: Python 3.11, PyInstaller build and frozen smoke pattern.
- `D:/Project/AdobePlugin/CaptionHelper/engine/requirements-win.txt:1-4`: faster-whisper 1.2.1, ctranslate2 4.8.2, onnxruntime 1.31.0, sherpa-onnx 1.13.8.
- `D:/Project/AdobePlugin/CaptionHelper/engine/prepare_model.py:36-53,272-312`: exact model revisions/hashes, prepared tree and notices.
- `D:/Project/AdobePlugin/CaptionHelper/build/pack-gipformer/model.json:1-23`: existing local pack manifest. Treat as input to verify, not a blanket trust grant.
- `D:/Project/subtitleedit/src/ui/Logic/Config/Se.cs:207`: `[Data Folder]/SpeechToText`.

## File ownership

All listed target paths are **proposed new files**, except `.gitignore`. Keep the copied Python source outside the UI source/resource tree; it is add-on source, not an embedded main-app dependency.

| Action | Absolute target | Purpose |
|---|---|---|
| Create | `D:/Project/subtitleedit/installer/gipformer/engine/caption_engine.py` | Snapshot CLI unchanged initially |
| Create | `D:/Project/subtitleedit/installer/gipformer/engine/backends/__init__.py` | Snapshot package marker |
| Create | `D:/Project/subtitleedit/installer/gipformer/engine/backends/sherpa_backend.py` | Snapshot Vietnamese backend |
| Create | `D:/Project/subtitleedit/installer/gipformer/engine/backends/faster_whisper_backend.py` | Preserve current spec's import closure; no slimming |
| Create | `D:/Project/subtitleedit/installer/gipformer/engine/engine_errors.py` | Snapshot shared error |
| Create | `D:/Project/subtitleedit/installer/gipformer/engine/vi_itn.py` | Snapshot number normalization |
| Create | `D:/Project/subtitleedit/installer/gipformer/engine/vi_punct.py` | Snapshot punctuation |
| Create | `D:/Project/subtitleedit/installer/gipformer/engine/word_timing.py` | Snapshot timing normalization |
| Create | `D:/Project/subtitleedit/installer/gipformer/engine/prepare_model.py` | Reuse pinned model preparation/hashes/notices |
| Create | `D:/Project/subtitleedit/installer/gipformer/engine/caption_engine.spec` | Same dependency collection, relocated build paths |
| Create | `D:/Project/subtitleedit/installer/gipformer/requirements-win.lock.txt` | Resolved/pinned build and runtime dependencies |
| Create | `D:/Project/subtitleedit/installer/gipformer/SOURCE-PROVENANCE.md` | Source revision, exact file hashes, allowed local deltas, permission status |
| Create | `D:/Project/subtitleedit/installer/gipformer/build-addon-windows.ps1` | Build, verify, stage and archive without source-checkout writes |
| Modify only if needed | `D:/Project/subtitleedit/.gitignore` | Narrow ignores for generated add-on builds/venv if not already ignored |

License/notice files under `installer/gipformer/licenses/` are created from the actual identified components during implementation, not fabricated. Do not add an MIT license for CaptionHelper's own source until ownership/permission is documented. Public release is gated; local build/adapter work can continue.

## Implementation steps

1. **Record exact source bytes.** Capture the CaptionHelper commit using `git -C D:/Project/AdobePlugin/CaptionHelper rev-parse HEAD`, and SHA-256 every copied source/spec/preparation file. A commit alone does not describe local uncommitted changes: record working-file digests and differences without including private data. Copy the explicit source closure above; do not copy the checkout, `.venv`, node_modules, models or scratch media. Explain why faster-whisper remains: the sherpa decoder imports `faster_whisper.audio.decode_audio`, and the existing spec explicitly bundles both backends.
2. **Make a clean isolated build environment.** Require Windows x64 Python 3.11; record patch version. Check the selected interpreter and venv report 64-bit pointers and an AMD64/win-amd64 target; reject x86/ARM64 before installing dependencies. Resolve the four existing direct pins, PyInstaller/hooks and all transitive dependencies as a deliberate lock-generation step, then check in exact versions and wheel SHA-256 hashes in `requirements-win.lock.txt`. The normal build must install exclusively from that lock using `pip install --require-hashes --only-binary=:all: -r <lock>` against the designated HTTPS package index, with no extra unpinned PyInstaller/hooks install or alternate resolver path. Include every build/preparation/runtime dependency actually used. Do not claim `pip freeze` alone is hash locking or reuse the old development venv. Keep CUDA out of the installed add-on; do not install the separate GPU pack or ship its DLLs. CPU packaging does not require CaptionHelper's CUDA-pack build step.
3. **Keep inference behavior unchanged.** Preserve the original backend constants, normalization, punctuation model and CLI emission/UTF-8/freeze support. Adjust build paths only. The currently frozen executable is stale relative to source; rebuild rather than shipping it. Do not replace the decoder or remove dependencies to reduce size. Keep source/spec deltas explicit in provenance.
4. **Verify model inputs.** Accept a prepared local `-ModelPack` directory or document preparation with the vendored `prepare_model.py --engine sherpa-onnx --out <folder>`. Model acquisition is a maintainer step, not runtime downloading. Verify encoder/decoder/joiner/tokens, ViBERT model/vocab/labels and Silero against the pinned constants, not only hashes supplied by the same local manifest. Preserve NOTICE, ATTRIBUTION and LICENSE bytes. Create canonical `pack/model.json` with `formatVersion:1`, id `gipformer1.5-vi`, engine `sherpa-onnx`, languages `[vi]`, pinned source revisions and per-file digests. Do not pull in the Node/CEP model registry solely to write JSON.
5. **Build the frozen runtime.** Use the existing PyInstaller onedir spec pattern with Windows x64 CPU dependencies. Stage `caption-engine.exe` and the complete `_internal` tree under `Gipformer/runtime`. Inspect the PE Machine field of the executable and bundled native EXE/DLL/PYD files; require AMD64 (`0x8664`) before writing x64 metadata. A staged copy must load Sherpa, ONNX Runtime and PyAV without the build venv on PATH. Check no CUDA or model files leaked into runtime; put models only under `Gipformer/pack`.
6. **Write add-on metadata.** Match the fixed layout in plan.md. `addon.json` includes format version 1, add-on version, OS `windows`, architecture `x64`, engine id, pack id, source digests and a files map of relative paths/lengths/hashes. Exclude `addon.json` itself from its files map to avoid a self-hash cycle. Reject absolute/traversing manifest paths; never use manifest paths to execute arbitrary alternative binaries. `BUILD-INFO.txt` records Python/build/native-library versions and model revisions; no local usernames, tokens or private source paths. Metadata is provenance, not authentication.
7. **Resolve redistribution inventory.** Keep component-specific notices: Python, PyInstaller bootloader terms, sherpa-onnx Apache-2.0, ONNX Runtime, faster-whisper/CTranslate2, PyAV/FFmpeg and packaged codecs, Gipformer MIT declaration, ViBERT CC-BY-SA-4.0, Silero MIT, upstream pipeline attribution. The local DLLs report LGPL v3-or-later but include x264/x265: inspect the actual dependency licenses/build metadata and corresponding-source obligations. Do not infer legal clearance from package names or change to a new decoder silently. Source owner permission and unresolved binary obligations block public distribution; mark the artifact private/not release-cleared until resolved.
8. **Create one archive.** Proposed build-script contract: `-Python <python3.11.exe> -ModelPack <prepared-dir> -Output <zip-path>`. Use unique staging inside ignored build output and checked exit codes. Default output is `x64/gipformer-addon-build/gipformer-vi-win-x64.zip`, already beneath ignored `x64/`. ZIP root is `Gipformer/`, so extracting into `[Data Folder]/SpeechToText` matches the documented path. Emit archive SHA-256 and build metadata beside it. Do not change the main Subtitle Edit installer or add release hosting. Do not overwrite user-installed engines or delete arbitrary folders; cleanup only newly owned staging.
9. **Prove the assembled archive.** Emit an external build receipt beside the ZIP containing SHA-256 of both the final ZIP and final `addon.json` bytes; the receipt is not in the manifest's file map. Extract into a different scratch directory. Validate manifest schema/identity/path rules and compare its bytes to the retained receipt; verify every other payload file's size/hash against its manifest entry, rejecting missing/unlisted payload files. This explicitly excludes the manifest from its own hash map without leaving it unchecked. Verify ZIP SHA-256 against the retained receipt before transfer/extraction; these checks detect build/transfer drift, not authenticity if a party replaces the ZIP and receipt together. Run the extracted executable with the extracted real pack and a known short Vietnamese WAV; validate progress, final result and exit. This proves the package, not merely the build tree.

## Intended commands after implementation

Run from `D:/Project/subtitleedit`. The first command targets a **proposed script**, not an existing command already executed:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File installer/gipformer/build-addon-windows.ps1 -Python <python3.11.exe> -ModelPack <verified-pack-dir> -Output x64/gipformer-addon-build/gipformer-vi-win-x64.zip
```

Against an extracted archive (replace placeholders with real paths):

```powershell
& <extract>/Gipformer/runtime/caption-engine.exe --help
& <extract>/Gipformer/runtime/caption-engine.exe --model-dir <extract>/Gipformer/pack --input <sample.wav> --language vi --device cpu --vad on
```

Use a temporary verification script to parse all output lines and assert the actual protocol/exit contract; do not infer success solely from displayed progress. Remove throwaway scripts afterward. Keep a permanent packaging command only where it belongs to the reusable artifact build, not duplicate smoke scaffolds.

## Verification and acceptance

- `--help` works and reflects the rebuilt source. Wrong language and missing model file return structured error plus nonzero exit, not an ImportError/loader crash hidden by the wrapper.
- The real pack returns Vietnamese accented words, punctuation, finite ordered timestamps and a final result after progress. Same decoded audio/settings must preserve the source pipeline's normalized recognition result; cue layout parity is not required.
- Archive re-extraction passes all recorded file hashes and contains all model/native dependencies/notices.
- A missing dependency is detected by manifest/preflight or reported explicitly at launch. An isolated developer smoke is not clean-machine proof; phase 3 supplies that.
- Build tools, model acquisition, source checkout paths and caches are not required at runtime. No model download happens on first use.
- Distribution permission is recorded or the public-release gate remains blocked; never mark it implicitly approved.

## Checklist

- [x] Snapshot the exact source closure and provenance without changing CaptionHelper. (`installer/gipformer/SOURCE-PROVENANCE.md`, engine snapshot under `installer/gipformer/engine/`; CaptionHelper untouched)
- [x] Lock a fresh Python 3.11 Windows x64 build environment, including hashes/build tools. (`x64/gipformer-addon-build/lock-report.json`, Python 3.11.9 x64)
- [x] Build the unchanged CPU pipeline and verify pinned model input bytes/notices. (build script rejects drifted model digests before staging)
- [x] Produce the fixed-layout ZIP, `addon.json`, dependency inventory and archive checksum. (841 files, manifest + `BUILD-INFO.txt` + receipt with SHA-256)
- [x] Re-extract the ZIP and exercise real successful and explicit-failure runs. (`verify-addon-windows.ps1`: 60 checks, 272 timed words on real Vietnamese audio)
- [x] Record source/native redistribution clearance or retain the explicit release block. (clearance still unresolved: receipt says `private/not-release-cleared`; public release remains gated)
