---
report: verification
status: integration-verified-quality-pending
created: 2026-10-29
---
# Verification — Gipformer Vietnamese STT integration

All results below were observed on this workstation (Windows 10.0.26200, x64, .NET SDK 10.0.403 at `C:\Users\Admin\.dotnet10`, Python 3.11.9 for the build only). Nothing here is estimated; unchecked gates are listed at the end and were not worked around.

## Toolchain provisioned for this run

- `dotnet --version` on PATH still reports "No .NET SDKs were found"; a private SDK was installed to `C:\Users\Admin\.dotnet10` (no system-wide change, no admin rights) and used explicitly for every build/test below.
- Build-only Python 3.11.9 venv at `x64/gipformer-addon-build/venv` with a hash-pinned lock (`x64/gipformer-addon-build/lock-report.json`). The installed runtime needs neither.

## 1. Add-on package (phase 1)

Build: `powershell -NoProfile -ExecutionPolicy Bypass -File installer/gipformer/build-addon-windows.ps1`.

| Item | Observed |
|---|---|
| Archive | `x64/gipformer-addon-build/gipformer-vi-win-x64.zip` |
| Archive SHA-256 | `f12a69cfb04e60f2bb300d509bc14f9eae115bbf56c699fd337907e3b365f67d` |
| Files in manifest | 841 |
| `Gipformer/addon.json` | 357082 bytes, SHA-256 `836c3f19d85a547c354a72aa63fcd995cf60bfbcdaa1ef83d1176ee0f039ce3b` |
| Pack size | 387 MB (386 966 030 bytes, 12 files) |
| Build time (UTC) | 2026-10-29T01:12:09Z |
| Distribution status in receipt | `private/not-release-cleared` |

Verification: `powershell -NoProfile -ExecutionPolicy Bypass -File installer/gipformer/verify-addon-windows.ps1 -Zip <zip> -Receipt <receipt> -SmokeWav <real Vietnamese clip> -RequireAccents` → **Verification passed: 60 checks**.

Covered by those 60 checks, in the tool's own groups:

- **Archive and receipt:** archive SHA-256 and `addon.json` size/hash match the receipt; the archive root is exactly `Gipformer/addon.json`.
- **Manifest identity:** `formatVersion` 1, `os` windows, `architecture` x64, `engineId` sherpa-onnx, `packId` gipformer1.5-vi, `addonId` gipformer-vi, languages exactly `[vi]`.
- **Packaged file map:** all 841 entries are safe relative paths and match size + SHA-256; no unlisted payload; the manifest does not list itself; every required runtime/pack file and every notice file present.
- **Native architecture:** all 170 native runtime binaries are AMD64; no CUDA runtime library; no model file leaked into `runtime/`.
- **Protocol (failure paths):** `--help` exits 0 and documents `--model-dir` with no import crash; wrong `--language` and missing/incomplete packs exit nonzero with one structured error each, naming the missing manifest/model file.
- **Real-pack transcription:** on `asr-comparison-20s-95s.wav` (75 s of Hanoi broadcast, 20–95 s) the extracted archive exits 0, emits only JSON lines, exactly one `info` and one `result`, progress reaches 100 before the result, no `error` message, `stderr` carries no result line, result language is `vi`, **272 timed words**, all with finite nonnegative starts and `end >= start`, nondecreasing starts, no empty text, and the transcript contains Vietnamese diacritics and punctuation.

Observed transcript (first words, same run):

```
Kính chào quý khán giả và các đồng chí đang theo dõi chương trình nha. Việt Nam Hà Nội đang bước vào
những ngày thu đẹp nhất trong năm, ... kỷ niệm 72 năm ngày giải phóng, mùng 10 tháng 10 năm 1954,
mùng 10 tháng 10 năm 2026, ...
```

## 2. Integration build and tests (phase 2)

| Command | Result |
|---|---|
| `dotnet build src/ui/UI.csproj -c Debug` | Build succeeded, no warnings |
| `dotnet build tests/UI/UITests.csproj -c Debug` | Build succeeded, no warnings |
| `dotnet test tests/UI/UITests.csproj --filter "FullyQualifiedName~Gipformer\|FullyQualifiedName~TimedWordSegmenter"` | 93 passed, 0 failed |
| `dotnet test tests/UI/UITests.csproj` (full suite) | 8058 total, **8009 passed, 0 failed**, 49 skipped (the FFmpeg live-player tests skip without a media session) |

Focused coverage (all new tests are behavioural, none assert source text or bare no-throw):

- `GipformerTranscriptTests` — success needs zero exit **and** exactly one result; `progress 100` alone fails; engine `error` and nonzero/unreadable exit codes fail even with a valid result; malformed line, message without a type, second result, error without a message, result for another language, unusable/negative/reversed/out-of-order word timing, word without text, segment without words, negative duration → protocol failure with no subtitle; cancelled discards output; empty result is `Succeeded` with zero cues; `stderr` can never create a result and is capped; `Reset` is clean; long token runs split at the length cap into ordered, non-overlapping cues.
- `GipformerEngineTests` — absent folder/manifest → `NotInstalled`; unparseable manifest, foreign platform/identity, missing file table, unsafe `..` manifest path → `InvalidManifest`; later `formatVersion` → `UnsupportedVersion`; missing/empty/truncated required file and missing `runtime/_internal` dll → `Incomplete` naming the file; pack manifest without `vi` → `InvalidManifest`; complete folder → `Ready`; advanced parameters accept only `--vad on|off` and `--threads N` (both syntaxes, quoted values) and reject reserved/unknown flags, bare flags, `--threads 0`, bad values and unterminated quotes; embedded help asset loads and documents the manual install.
- `SpeechToTextGipformerSelectionTests` — selecting the engine saves `WhisperChoice.Gipformer`, pins the single `vi` language, hides translation/download/settings/website and the model download button, keeps one model; the choice survives reopening the window; switching away and back keeps per-engine advanced parameters and restores the other engine's capabilities; the status hint contains the extraction folder; **the built window renders that hint and hides the website button**.
- `TimedWordSegmenterTests` (renamed from `Qwen3AsrWordSegmenterTests`, all prior cases kept) — added Vietnamese spacing/number/sentence cases (`3.5` not a sentence break, `Nam.` ends a cue) and a hard-pause break.

The only production rename is `Qwen3AsrWordSegmenter` → `TimedWordSegmenter`; no `Qwen3AsrWordSegmenter` reference remains in production or tests.

## 3. What is not verified

- **Clean Windows x64 environment:** the 60-check run used this workstation's extraction folder under `%TEMP%`; it ran without Python in the child process, but the machine has Python, .NET and developer paths installed. A fresh VM/Windows Sandbox run of the same ZIP is still required.
- **Actual desktop-app interaction:** this session cannot drive the Avalonia desktop window, so whole-file/batch/selected-line runs through the real UI were not exercised end to end. The window itself is covered headlessly (layout, hint, hidden buttons, engine list) and the sidecar is covered by the 60-check runtime proof; the process-lifecycle paths (`EOF`-safe completion, cancel, batch advance, empty-success message) are covered at the state-machine level, not by a manual UI run.
- **Release gate:** redistribution clearance for the CaptionHelper-derived runtime and the bundled model/native components is still unresolved (`distribution: private/not-release-cleared` in the receipt). The feature ships in the app; the archive must not be published publicly until that is documented.
- **Quality gate: closed as NOT MET (2026-10-29).** The reviewer judged the output worse than `large-v3-turbo` and decided to keep the engine as a secondary option; correction counts were not collected. See [quality-comparison.md](quality-comparison.md). No accuracy claim is made in the app, docs, help text or changelog.

## 4. Observations (not defects)

- A 40 s clip of the same source that turned out to contain English narration decoded to degraded English-like tokens instead of failing: the engine is Vietnamese-only and does not switch language. This is inherent to the confirmed scope and is documented as a limitation.
- Reading Vietnamese text produced by the sidecar through a PowerShell pipe mangles diacritics unless the output is redirected as raw bytes (`Start-Process -RedirectStandardOutput`) — a console-encoding artifact of the probe, not of the protocol (`UTF-8` JSON verified in the 60-check run).
