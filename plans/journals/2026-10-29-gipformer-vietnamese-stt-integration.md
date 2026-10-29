---
title: Gipformer Vietnamese STT integration
date: 2026-10-29
summary: "Added the Gipformer - Vietnamese offline engine with a manually installed Windows x64 add-on, an EOF-safe JSON-lines adapter, shared timed-word segmentation, and docs/tests; quality and clean-VM gates open"
---

# Gipformer Vietnamese STT integration

## What happened

- Provisioned a private .NET 10 SDK (10.0.403) under `C:\Users\Admin\.dotnet10`; PATH dotnet still has no SDK, so every build used the explicit path.
- Built the add-on ZIP `x64/gipformer-addon-build/gipformer-vi-win-x64.zip` (841 files, pack 387 MB, SHA-256 `f12a69cf…`). `verify-addon-windows.ps1` re-extracted it and passed 60 checks, including a real 75 s Hanoi broadcast clip: 272 timed words, Vietnamese diacritics and punctuation, one `info`, one `result`, nonzero-exit failure paths.
- Added `GipformerEngine` (structural readiness: manifest identity, required files, sizes, `_internal` dll), `GipformerTranscript` (one attempt = one object; success only on zero exit + exactly one result; 100 % progress is not completion; empty result is silence), and wired a single finalization path that waits for process EOF before deciding.
- Renamed `Qwen3AsrWordSegmenter` to `TimedWordSegmenter` and migrated every consumer/test; added Vietnamese segmentation cases.
- UI: engine registered only on Windows x64, saved choice/parameters, `vi`-only language, no translation, no model download, hidden website/settings/download buttons, install hint naming the extraction folder, guarded download/re-download/web commands, no-speech message, and the #15497 "finished clips after cancel" offer for a cancel during ffmpeg extraction.
- Docs: `docs/features/speech-to-text.md` (new section), `docs/third-party-components.md` (extraction layout, notices, redistribution status), `change-log.txt`, English keys and an embedded help asset.
- Tests: 93 focused (Gipformer + segmenter) pass; full UI suite 8058 total / 8009 passed / 49 skipped / 0 failed.

## Decision

Keep the engine manual-install only (never downloadable), keep the sidecar's JSON-lines contract fixed (`--language vi`, `--device cpu`, `--model-dir`, `--input` owned by the app; only `--vad`/`--threads` user-settable), and refuse to treat crashes, malformed output, duplicate results or a missing result as "no speech". Redistribution clearance stays unresolved, so the archive is marked `private/not-release-cleared` and public release remains gated.

## Next steps

- Run the same ZIP on a clean Windows x64 VM/Sandbox (no Python, no developer paths).
- Drive the desktop app through whole-file, batch and selected-line runs (`EOF`, cancel, clip offsets, another local engine in the same session).
- Obtain the three-clip correction-count comparison against `large-v3-turbo` and the reviewer's sign-off (`plans/261028-1430-gipformer-vietnamese-stt/reports/quality-comparison.md`).
- Resolve source/native redistribution permission before publishing the archive.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
