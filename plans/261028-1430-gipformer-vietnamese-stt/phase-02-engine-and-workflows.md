---
phase: 2
title: "Engine adapter and all STT workflows"
status: done
priority: P2
effort: ""
dependencies: []
---

# Phase 2: Engine adapter and all STT workflows

## Goal

Expose Gipformer in the existing STT surface and consume its actual result protocol safely across whole-file, batch and selected-line jobs. This phase can be implemented against the fixed plan.md contract while phase 1 produces the real ZIP; integration proof requires both phases.

## File ownership

All paths below are absolute. New files/types are **proposed**, not existing APIs.

| Action | Target | Purpose |
|---|---|---|
| Create | `D:/Project/subtitleedit/src/ui/Features/Video/SpeechToText/Engines/GipformerEngine.cs` | Engine/model metadata, local add-on paths and install validation |
| Create | `D:/Project/subtitleedit/src/ui/Features/Video/SpeechToText/GipformerTranscript.cs` | Narrow protocol/result DTOs and parsing/completion state; not a second job manager |
| Modify | `D:/Project/subtitleedit/src/libuilogic/AudioToText/WhisperChoice.cs` | Stable `Gipformer` choice |
| Modify | `D:/Project/subtitleedit/src/ui/Logic/Config/SeAudioToText.cs` | Per-engine advanced parameters, matching existing convention |
| Modify | `D:/Project/subtitleedit/src/ui/Features/Video/SpeechToText/Engines/WhisperEngineFactory.cs` | Construct registered engine by StaticName |
| Modify | `D:/Project/subtitleedit/src/ui/Features/Video/SpeechToText/SpeechToTextViewModel.cs` | Registration/install gates/launch/protocol/drain/completion/routing |
| Modify | `D:/Project/subtitleedit/src/ui/Features/Video/SpeechToText/SpeechToTextWindow.cs` | Show local-install status independently of the hidden download-button tooltip |
| Rename and modify | `D:/Project/subtitleedit/src/ui/Features/Video/SpeechToText/Qwen3AsrWordSegmenter.cs` -> `D:/Project/subtitleedit/src/ui/Features/Video/SpeechToText/TimedWordSegmenter.cs` | Reuse actual sentence/pause/length rules without Qwen-specific naming |
| Rename and modify | `D:/Project/subtitleedit/tests/UI/Features/Video/SpeechToText/Qwen3AsrWordSegmenterTests.cs` -> `D:/Project/subtitleedit/tests/UI/Features/Video/SpeechToText/TimedWordSegmenterTests.cs` | Preserve all behavior assertions for the shared helper |
| Create | `D:/Project/subtitleedit/src/ui/Assets/SpeechToText/GipformerVietnamese.txt` | Pack layout, supported flags and limitations/help |
| Modify | `D:/Project/subtitleedit/src/ui/Logic/Config/Language/Video/LanguageAudioToText.cs` | English defaults for manual-install/invalid-add-on/engine-failure/no-speech messages |
| Modify | `D:/Project/subtitleedit/src/ui/Assets/Languages/English.json` | Corresponding canonical language keys; leave translator-owned locales unchanged |
| Create | `D:/Project/subtitleedit/tests/UI/Features/Video/SpeechToText/GipformerTranscriptTests.cs` | Consumer-visible protocol/timing/failure boundaries |
| Create | `D:/Project/subtitleedit/tests/UI/Features/Video/SpeechToText/Engines/GipformerEngineTests.cs` | Incomplete-install behavior and saved-engine/control transitions |

No `Se.GipformerFolder` property or new settings class is required; use the existing `Se.SpeechToTextFolder`. No changes are planned to `ISpeechToTextEngine` or `WhisperModel` contracts. A third new service, general capability layer or generic subprocess manager is not justified.

## Steps

### 1. Metadata and install validation

- Add `WhisperChoice.Gipformer = "Gipformer"` and `GipformerEngine.StaticName`/Name for **Gipformer — Vietnamese**. Register only when `OperatingSystem.IsWindows()` and process architecture is x64; do not offer unsupported packages on ARM64/non-Windows.
- Expose exactly one model (`gipformer1.5-vi`) and one language (`vi`, Vietnamese). Follow the existing engine folder/model methods; resolve `<Se.SpeechToTextFolder>/Gipformer/runtime/caption-engine.exe` and `.../pack`. Resolve help using the explicit embedded URI `GipformerVietnamese.txt` instead of deriving a resource name from a display name containing punctuation.
- `CanBeDownloaded=false`, `DownloadsOwnModels=false`, `SupportsCustomModels=false`; do not fake an installed model or advertise a downloader. Implement `GetModelForCmdLine` as the actual pack directory, not a Whisper weights filename.
- Add `CommandLineParameterGipformer` to `SeAudioToText`, initially empty; existing saved `WhisperChoice`, `WhisperModel`, `WhisperLanguageCode` hold selection. Reuse the existing advanced-parameter editing surface, not a new UI. No telemetry, server config or custom location setting.
- Provide a single narrow installation-check routine in the engine that accepts an explicit root for isolated tests. Validate `addon.json` format/platform/arch/identity and required relative files; reject traversal/rooted paths in metadata before using them. Validate `pack/model.json` id/engine/languages and required nonempty ASR/punctuation/VAD files. Distinguish absent runtime, incomplete runtime, invalid pack and unsupported add-on version. Never execute a path selected by untrusted metadata.
- Avoid full hashing in `IsEngineInstalled`/model combo rendering. Hash verification belongs to the archive build/explicit verification, not repeated UI work. Recheck existence/completeness just before a run so a removed DLL/pack is not hidden by cached install status. Do not cache failures across manual extraction; reselecting/reopening checks again.

### 2. UI/preflight gates

- Register the engine in `SpeechToTextViewModel` and the existing factory. Existing constructor selection restore matches stable `Choice`; keep other engines' choice/model settings behavior.
- Auto-language is already a whitelist (`:532-575`): do not add Gipformer. Explicitly exclude Gipformer in `IsTranslateAvailable` (`:577-580`), so switching from Whisper clears `DoTranslateToEnglish` through existing visibility logic. Do not expose Crisp controls/forced aligners/speakers/GPU.
- Hide model download controls for Gipformer in `EngineChanged` and short-circuit `DownloadModel`/engine-download entry points if invoked programmatically. A single installed bundled model is not an import/download feature. Do not set `DownloadsOwnModels=true` to bypass gates.
- Add Gipformer preflight **before** generic missing-engine/model download prompts (`:4106-4227`). Show precise manual-extraction destination and missing/incompatible component; remain usable and do not launch another engine, downloader or extraction process.
- In `UpdateEngineStatusUi`, set an actionable local-add-on hint before the `!canDownload` early return. Keep download/re-download/settings-gear actions hidden; this is not a new installer. The current `EngineDownloadHint` is bound only to the hidden download button's tooltip (`SpeechToTextWindow.cs:168-177`), so make the local-install hint visible independently near the existing engine row, with accessible text and no new installation screen.
- Refresh current status and existing combo status dots when the engine is reselected/reopened or preflight observes a newly installed add-on. No filesystem watcher/polling service.

### 3. Safe process invocation and message boundary

- Keep the engine process in `_whisperProcess` so existing cancel/window-close cleanup remains authoritative. Add a Gipformer-specific launch branch before generic Whisper argument generation; use hidden-window/working-directory/UTF-8 setup equivalent to `StartEngineProcess`.
- Pass fixed reserved arguments with `ProcessStartInfo.ArgumentList`: `--model-dir <pack> --input <audio> --language vi --device cpu`; default VAD follows source (`on`). Do not pass translation/task/Whisper model flags, source offsets, or GPU switches.
- Preserve existing advanced CLI editing behavior with correct Windows argument tokenization. Support the existing sidecar tuning flags `--vad on|off` and `--threads N`; reject reserved input/model/language/device/range/compute-type flags rather than allowing extra parameters to redirect input/pack or violate CPU/Vietnamese scope. Reuse an existing command-line tokenizer if found; otherwise a narrowly scoped token parser, not shell execution. Never split quoted paths with `Split(' ')` or launch through cmd.exe. Invalid parameters must surface as user-facing errors, not be silently ignored.
- Give stdout and stderr **distinct** handlers. The current helper attaches one handler to both (`:4615-4623`), which is unsuitable for a protocol stream; keep the change scoped to Gipformer rather than altering all engines. Stderr remains diagnostic and cannot impersonate a JSON result. Do not forward recognized transcript JSON into generic `OutputHandler` or write it to tools logs by default.
- `GipformerTranscript` owns one attempt's parse/result/error state. Accept recognized message types, validate required fields/types and finite numeric values; permit future extra object fields without rewriting the engine. Parse the final result once and materialize the necessary timed words; do not retain duplicate full JSON/transcript strings. Validate language `vi`, usable word text and nonnegative ordered start/end. Reject malformed final data rather than dropping the bad word and claiming success.
- For `info`, record actual CPU/duration; for `progress`, advance displayed percentage in `[0,100]`; for `error`, retain the explicit message and mark the attempt failed. An unknown well-formed message type may be ignored; malformed stdout JSON or missing required fields is a protocol failure. Exactly one final result is required; duplicate results are a protocol failure, not merged outputs.

### 4. Completion and attempt lifetime

- The current timer observes `HasExited` and disposes the process (`:898-914`) before special result handling. Insert Gipformer completion **before that disposal**, or restructure only its branch so final stdout/stderr EOF is awaited without holding `_lockObj` or blocking the Avalonia UI thread.
- Wait for process exit **and** both redirected streams to finish. Use an attempt-owned completion signal and a single finalize guard; detach/stop the timer for that attempt before scheduling completion. A timer tick, stdout callback, cancellation and close can race; only one result/failure is applied. Ignore late messages from an old process after the next batch job starts. Reset parse/error/result/progress state per `TranscribeViaWhisper` invocation, not only once in `Transcribe()`.
- Completion precedence: cancelled/closed attempt discards the in-flight final result; otherwise any error/protocol failure/nonzero exit fails; otherwise exactly one valid final result succeeds. Receiving result or progress 100 before exit does not override later crash/error. A zero exit without result is not silence.
- Source emits the full transcript only at the end; do not invent streaming partial-word results. Preserve already completed selected-line clips using existing `OfferTranscribedAudioClipsAfterCancel`; do not offer an empty/new partial transcript as completed work.
- Cancellation/window-close must terminate the process tree and drain/detach handlers safely. Tolerate cancel after exit or disposal without an unhandled exception. Do not resurrect progress/results on a closed window or start the next batch item after cancellation.
- Include the extraction-cancel path in this Gipformer lifecycle: `OnTimerAudioExtractOnElapsed` currently kills FFmpeg and returns (`:2959-2969`) without offering prior completed clips. For Gipformer selected-line jobs, dispatch the existing completed-clips offer exactly once after extraction cancellation, unless `_windowClosing` is set. Keep other engines unchanged; no new cancellation manager.

### 5. Cues and output routing

- Rename `Qwen3AsrWord` to neutral `TimedWord` and `Qwen3AsrWordSegmenter` to `TimedWordSegmenter`, including the file and test class/file. Preserve its existing spacing/sentence/pause/length algorithm exactly; remove obsolete Qwen-only aliases/comments, but retain Qwen-specific filtering at its existing caller. Keep the same cue-building signature/limits. If C# LSP is available at execution time, run references/rename through LSP first; it was unavailable during planning.
- Verified consumer map: one production caller (`SpeechToTextViewModel.cs:1395-1421`) and one test consumer file (`Qwen3AsrWordSegmenterTests.cs`). A fresh references scan is required before exported symbol changes; no shims or stale re-exports. The factory has one current test caller in `WhisperEngineWhisperXTests.cs`; preserve it while adding the new factory branch.
- Flatten Gipformer's normalized `segments[].words[]` into timed words in emitted order. Preserve punctuation/numbers/accented text and original word timestamps; do not insert forced alignment, reconstruct recognition from VAD segments, add confidence thresholds or convert to an SRT file merely to reread it.
- Build cues with `TimedWordSegmenter.BuildSubtitle` and the existing `SpeechToTextPostProcessor.GetParagraphMaxChars()` cap. Apply existing `SpeechToTextTimingFixer.SortAndRemoveOverlaps`, normal `PostProcess`, quality report and `MakeResult` once. Post-processing may intentionally adjust cues; recognition parity is evaluated before it.
- Match selected-clip results by the original `_videoFileName`/`AudioClip.AudioFileName`, not the extracted temporary audio name or list index. Assign the postprocessed subtitle before `MakeResult` advances the job. The caller adds media start once; keep clip results relative to zero. Do not change `MainViewModel` just to add another offset.
- Batch failures must record the real reason, mark the item failed and continue under existing non-cancelled batch behavior. Never reuse a previous job's result. For a successful empty transcript, single-file UI says no speech found; batch/selected-line status follows existing empty-item rules but diagnostic text distinguishes silence from engine failure. Do not fall into `_loadedFromStdOut`'s misleading "No result file generated by Whisper" path.
- Handle Gipformer launch failures before a process/completion signal exists. `TranscribeViaWhisper` catches start exceptions and returns false (`:4568-4577`); its extraction caller (`:3049-3054`) and direct-WAV/initial job caller otherwise stop instead of advancing. For Gipformer, route these failures to one attempt-owned failure finalizer that records the reason, calls the existing batch advance with no subtitle when non-cancelled, and shows an error for single-file runs. Preserve the original process exception and guard against caller/finalizer double delivery.
- Add an explicit Gipformer empty-success UI branch: current `MakeResult` handles empty single-file output only for Crisp ASR (`:2893-2924`). On a validated empty result with zero exit, show no-speech feedback and leave the window usable; failed/missing-result output instead shows its actual error. Do not assume generic `MakeResult(empty)` supplies this feedback.

## Targeted permanent tests

Keep tests behavioral, deterministic, isolated and free of actual models/network. Use `SettingsScope` for every changed static setting and fresh temporary roots; do not create/overwrite a real engine directory under the user's data folder. Avoid tests of factory forwarding, literal help text, copied constants or source text. Proposed tests:

1. An absent/incomplete/incompatible add-on returns actionable manual-install failure without invoking download or launching a process; rechecking a corrected temporary root succeeds structurally.
2. Protocol sequences distinguish result+zero exit, result+nonzero exit, error+result, no result, malformed/truncated result, duplicate result and successful empty result. Exercise Vietnamese punctuation/numbers and precise times, not just nonempty output.
3. Cues preserve text and sentence boundaries, do not split decimal numbers incorrectly, and remain ordered/nonoverlapping under existing segmentation settings. Retain all Qwen tests when renaming the helper.
4. Switching Whisper -> Gipformer -> Whisper hides/clears unsupported translation and offers only Vietnamese, restores saved choice and keeps unrelated engine parameters isolated. This is a transition test, not a test of an incidental default string.
5. Attempt state reset and cancel/late-result precedence prevent a previous batch result from being attached to the next clip. Prefer testing the narrow attempt state rather than mocking an entire process; actual EOF/cancel/UI proof belongs to phase 3.

## Verification after integration

Run from `D:/Project/subtitleedit` with .NET 10 available:

```powershell
dotnet build src/ui/UI.csproj -c Debug
dotnet test tests/UI/UITests.csproj --filter "FullyQualifiedName~UITests.Features.Video.SpeechToText"
```

These commands are planned, not run during planning. Phase 3 then launches the actual app and exercises the real ZIP/runtime. Compilation or mocked parser tests alone do not prove the process lifecycle.

## Checklist

- [x] Implement narrow engine metadata/install checks, saved choice/parameters and explicit help resource. (`GipformerEngine`, `WhisperChoice.Gipformer`, `CommandLineParameterGipformer`, `Assets/SpeechToText/GipformerVietnamese.txt`)
- [x] Integrate manual-install preflight/status and hide unsupported model/language/translation actions. (status hint, guarded download/re-download/website commands, single `vi` language, no model download)
- [x] Implement isolated stdout/stderr protocol handling with EOF-safe, single-finalization attempt lifetime. (`GipformerTranscript` + `Interlocked` completion + `WaitForExit` before finalize)
- [x] Reuse neutral timed-word segmentation and migrate every existing Qwen production/test consumer. (`Qwen3AsrWordSegmenter` renamed to `TimedWordSegmenter`, no old references remain)
- [x] Deliver success/empty/error/cancel results through the existing batch/clip/postprocess flow. (failure marks the batch item and advances; empty result shows the no-speech message; cancel offers finished clips)
- [x] Add focused regression coverage for protocol boundaries, state transitions and incomplete installations. (`GipformerTranscriptTests`, `GipformerEngineTests`, `SpeechToTextGipformerSelectionTests`)
