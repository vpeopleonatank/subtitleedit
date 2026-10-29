# Gipformer add-on — source provenance

The local add-on ZIP contains a frozen build of CaptionHelper's caption engine. This file records
exactly which source bytes that build came from, so the runtime can be reproduced and audited
without access to the CaptionHelper checkout.

## Repository

| Item | Value |
|---|---|
| Repository | `D:/Project/AdobePlugin/CaptionHelper` (read-only input; nothing here is modified by the build) |
| Commit | `95eeed679638044d44826f630cb4c98d69e1e224` (2026-10-20) |
| Working tree | Not clean: the engine files below carry uncommitted local changes (range support). Digests below are of the **working files actually snapshotted**, not of the commit. |
| Snapshot date | 2026-10-29 |

## Snapshotted files (SHA-256 of the bytes under `engine/`)

| File | SHA-256 |
|---|---|
| `caption_engine.py` | `60883256f38f53e8a6f44d6d1cac5242880b08ac06ff776e49810e7ec8b134cc` |
| `engine_errors.py` | `e4eb8f48b771c8a643f57ff4b3815a2a37fbe85d6cf384e9d621872b81086d42` |
| `vi_itn.py` | `a8d95cca9de525d10d093a91ab4ad74f25db6929fffb95bde70785fc73f6d100` |
| `vi_punct.py` | `6ecb368d7ec6708083a7af9c507bf936f4d1d33a71c853e4f2b67a5bd839bef8` |
| `word_timing.py` | `e33abe0106ab3130f41f102996db0f4da7f58ae40921fe9abf823a48977ce6a7` |
| `prepare_model.py` | `c86d500ca4db5cf4ad493e0f7e6b7c4c98ee67ab76dddf6f766df9338f1f1b3e` |
| `backends/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (empty file) |
| `backends/sherpa_backend.py` | `3497ac178f81769907b2777407233c8bae1a3bcad5688c683ee2cacd158a9987` |
| `backends/faster_whisper_backend.py` | `51ba1489957e637c5dacd3bbac7b18e9f8bb97bac7bcafbe2be63c8b4e1469c3` |
| Source `caption_engine.spec` (reference only) | `6165747f2507c47b148c3c1b3d4f5a3233065c484abdc33cafe02fc87b504255` |
| Source `requirements-win.txt` (reference only) | `aae991fa47afad124210b928894c69178b994da48cfe35f05cb76b95b36c33d8` |

Verification: `sha256sum installer/gipformer/engine/*.py installer/gipformer/engine/backends/*.py`
must reproduce the table above. The copied files are byte-identical to the CaptionHelper working
files; no source edits were made while copying.

## Uncommitted delta carried in the snapshot

The upstream checkout has one uncommitted change set in the engine, all of it the optional
`--start/--end` media-range support:

- `caption_engine.py`: adds `--start`, `--end` and `check_range()`; a bad pair raises `EngineError`
  ("--start and --end must be given together" / "Invalid range ... expected end > start >= 0")
  which `main()` reports as a JSON `error` line with a nonzero exit.
- `backends/sherpa_backend.py`: slices the decoded samples to the range, keeps word times in media
  time, and makes `duration`/progress refer to the range.
- `backends/faster_whisper_backend.py`: equivalent range decoding (`range_audio`).

Subtitle Edit never passes `--start`/`--end` (selected-line jobs give the sidecar already-extracted
clips, and the caller applies the media offset once), so the range flags are inert here. They stay
in the snapshot because removing them would be a source delta beyond the accepted pipeline.

## Why faster-whisper stays in the closure

`sherpa_backend.py` decodes audio through `faster_whisper.audio.decode_audio` (PyAV). The existing
CaptionHelper spec therefore bundles both backends plus `faster_whisper`, `ctranslate2`, `av`,
`onnxruntime` and `sherpa_onnx`. The add-on keeps that closure unchanged; it does not slim the
runtime or replace the decoder. Only the Vietnamese `sherpa-onnx` pack is shipped, so the frozen
faster-whisper backend is present but never selected by a `model.json` in this add-on.

## Allowed local deltas in this repository

Only packaging, never inference behavior:

1. `engine/caption_engine.spec` is a relocated copy: same `collect_all` package list, same CUDA
   filter, same hidden imports, paths anchored at `installer/gipformer/engine`.
2. `requirements-win.lock.txt` replaces CaptionHelper's unpinned `requirements-win.txt` +
   `pyinstaller` install with a fully hashed lock (`--require-hashes --only-binary=:all:`).
3. `build-addon-windows.ps1` and `verify-addon-windows.ps1` are new packaging/verification tools.
4. No backend constant, normalization step, punctuation/vocabulary file or CLI contract is changed.

## Licensing / redistribution status

- **CaptionHelper source**: the checkout has no `LICENSE`/`COPYING` file, `package.json` is marked
  `private` and declares no license. **Redistribution permission is not granted.** The add-on
  build is therefore a *private, not release-cleared* artifact until the owner documents a license.
  No license text is invented here.
- **Model pack**: gipformer 1.5 (MIT, per its upstream model LICENSE), ViBERT-capu re-punctuation
  (CC-BY-SA-4.0, see `pack/punct/ATTRIBUTION.md`), Silero VAD (MIT). Pack notice bytes are shipped
  unmodified in `pack/`.
- **Bundled native libraries**: see `licenses/` in the add-on and `docs/third-party-components.md`.
  PyAV/FFmpeg DLLs report LGPL v3-or-later and the build enables libx264/libx265; that is not a
  clearance. Do not distribute publicly until source permission and the native obligations are
  documented by the owner.
