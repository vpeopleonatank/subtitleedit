---
phase: 3
title: "Integration proof, documentation and quality acceptance"
status: done
status-note: "quality gate closed as NOT MET by reviewer verdict; clean-VM run and desktop-UI interaction remain open"
priority: P2
effort: ""
dependencies: [1, 2]
---

# Phase 3: Integration proof, documentation and quality acceptance

## Goal

Prove the actual Windows add-on and Subtitle Edit surface, document the delivered install contract, and evaluate the user's quality goal without equating successful integration with better recognition.

## File ownership

| Action | Absolute target | Purpose |
|---|---|---|
| Modify | `D:/Project/subtitleedit/docs/features/speech-to-text.md` | Engine table, Windows/manual-install exception, supported controls/workflows/limitations |
| Modify | `D:/Project/subtitleedit/docs/third-party-components.md` | Exact extraction layout, data-folder lookup, component notices and redistribution status |
| Modify | `D:/Project/subtitleedit/change-log.txt` | Current-release entry after runtime proof; do not edit historical `Changelog.txt` |
| Create | `D:/Project/subtitleedit/plans/261028-1430-gipformer-vietnamese-stt/reports/verification.md` | Observed commands/runtime/UI/package results, versions and remaining gates |
| Create | `D:/Project/subtitleedit/plans/261028-1430-gipformer-vietnamese-stt/reports/quality-comparison.md` | Three clip IDs/settings, correction counts and user sign-off; no private transcripts/media |

The integration owner may correct in-scope defects in phase 1/2 files when proof exposes them, updating plan status/evidence honestly. Do not rename unrelated components or make production behavior match incidental wording/source-text tests.

## Prerequisites

- Windows x64 with .NET 10 SDK for build/tests; phase 1's add-on ZIP and phase 2's code.
- Subtitle Edit's usual FFmpeg/media dependencies, supported player setup and the large-v3-turbo model in an existing local Whisper engine. Do not bundle the baseline Whisper model into the Gipformer ZIP.
- A clean Windows x64 environment (fresh VM or Windows Sandbox if available) without Python, CaptionHelper, their venvs/Hugging Face caches or developer paths.
- User review at the final quality gate. If clean environment or reviewer is unavailable, finish reachable work, record missing evidence and leave the corresponding acceptance unchecked.

## 1. Build and focused regression pass

From the repository root, after both coding slices are integrated and not editing shared code:

```powershell
dotnet build src/ui/UI.csproj -c Debug
dotnet test tests/UI/UITests.csproj --filter "FullyQualifiedName~UITests.Features.Video.SpeechToText"
dotnet test tests/UI/UITests.csproj
```

The full UI suite is warranted by the shared helper rename, global settings and view-model lifecycle integration. Run each pass once at the completed integration point; if it fails, diagnose and fix the cause before rerunning the affected verification. New permanent tests must cover plausible user-visible bugs, not copied metadata/forwarding/wiring or English wording. Delete incidental wording/implementation-only tests if changes make them obsolete rather than re-pinning them. Do not erase legitimate behavioral coverage. Use existing `SettingsScope`/settings isolation conventions and no real models/network in unit tests.

Record exact commands, exit status and test counts from observed output. A missing SDK is a prerequisite, not a passing or failing implementation test.

## 2. Launch and exercise the actual app

```powershell
dotnet run --project src/ui/UI.csproj -c Debug
```

Alternatively launch the actual built `SubtitleEdit.exe` if its dependencies are configured. Observe the native desktop STT window, results and process state; use available desktop automation or an interactive user-assisted run, not a fabricated browser rendering. Capture safe screenshots/evidence when tools permit. If the runtime cannot inspect/drive this native surface, report the exact visual limit and obtain the user's actual GUI observations; headless tests do not replace this acceptance item.

| Scenario | Action | Observable pass condition |
|---|---|---|
| Missing add-on | Select Gipformer with no local files and click Transcribe | Manual extraction destination/error shown; no downloader, alternate engine or transcription starts |
| Incomplete pack/runtime | In an owned scratch installation remove one required model then one manifest-listed native dependency | Useful missing/incomplete message; no claimed successful/no-speech run; restore only scratch files |
| Manual install detection | Extract archive contents into the documented STT folder, then reselect/reopen | Engine/model readiness updates and transcription is available; no restart-only hidden dependency |
| Whole-file video | Use a real Vietnamese audio/video and explicitly choose its audio track | Progress advances, Vietnamese cues appear, normal editor export works, original media/sidecar subtitles unchanged |
| Direct WAV path | Use an existing 16 kHz WAV, including a Unicode/space-containing path | Same workflow completes without treating the original input as disposable temp data |
| Batch | Queue at least two speaking inputs plus a silence item, a controlled post-launch failure and a controlled process-start failure | Each result belongs to its file; statuses/logs distinguish outcomes; a failed launch marks that item and advances to the next; no stale previous transcript |
| Selected short line | Transcribe a selected line under 10 seconds | Text updated only for the originating line; existing start/end preserved |
| Selected long line | Transcribe a line over 10 seconds with multiple sentence cues at a nonzero media start | Replacements fall within the original media region, offset applied exactly once, style preserved by existing caller |
| Selected mixed outcome | Include a speaking clip, a silent clip and another speaking clip | Speaking lines mapped by clip identity, silent line text not blanked; existing apply/retry behavior preserved |
| Silence | Supply known silent audio | Valid empty final result+zero exit produces no-speech feedback distinct from failed/malformed output |
| Cancellation | Cancel during inference, during extraction and at a completion boundary; close the STT window in a separate run | No engine/extractor process tree left running; UI stays usable; cancelled batch does not start another item; late final results not applied |
| Completed clips on cancel | Finish one selected-line clip, then cancel a later clip once during inference and once during extraction | Both paths offer the existing completed-clips prompt once; no invented in-flight partial result; window close schedules no prompt |
| Error/EOF | Temporarily use a controlled throwaway sidecar harness in an owned test root: delayed final stdout, final result then nonzero exit, malformed/truncated/no result, duplicate result and JSON-looking stderr | No success before exit+EOF; stderr cannot create a result; each failure is explicit; exactly one finalization |
| Engine switching | Switch Whisper -> Gipformer -> Whisper, change advanced flags and reopen | Gipformer offers only vi; no translate/aligner/GPU/download controls; saved selection/parameters work; other engines retain correct controls and still transcribe |

Use temporary smoke/harness files only under owned scratch output. They support observed process behavior, not fake production inference. Keep the real-engine success scenarios separate. Remove temporary harnesses after proof. If a row cannot run, record it as unverified rather than deleting the acceptance criterion.

### Timing and cue invariants

For real output check text/punctuation/numbers before optional post-processing, finite nonnegative starts/ends, positive cue durations, sorted nonoverlapping cues after timing repair, and pause/sentence/length-based splitting. Do not assume a 20-second VAD segment is an acceptable subtitle. Subtitle Edit's optional timing/line settings can change final cue boundaries; compare against the chosen settings, not exact Premiere SRT layout.

### Cancellation mechanics

Inspect actual process IDs before/after cancellation/window close, including descendants, rather than checking only a task flag. Test a short job to expose result-vs-cancel races and a longer clip to observe live progress. Callbacks must be detached/drained before another attempt consumes state; use the controlled late-output harness to make this deterministic. No permanent arbitrary sleeps are permitted as an EOF fix.

## 3. Clean-machine package proof

1. Publish the main app as a self-contained Windows x64 test build with the normal asset extraction path:

   ```powershell
   dotnet publish src/ui/UI.csproj -c Release -r win-x64 --self-contained true -o x64/gipformer-clean-machine-app
   ```

2. Transfer only the built app, its usual media dependencies, the finished add-on ZIP and permitted local test media into the clean environment. Do not copy developer Python/venv/checkouts/caches. Use the actual Data Folder from the app, not the repository path.
3. Verify the transferred ZIP against the retained external build receipt, then extract exactly as documented. Check `addon.json` schema/identity and SHA-256 against the receipt; check every other payload file against the manifest, plus executable architecture and complete pack/notices. Do not treat the manifest as self-hashed or the receipt as a signature. A copied developer installation is not equivalent proof.
4. Disable network after transferring files. Run a real whole-file transcription from the app and standalone `--help`/real-pack run. Confirm no first-use download, no Python prerequisite and no read from CaptionHelper/Hugging Face caches; record environment and evidence.
5. Exercise missing/incomplete add-on and cancellation there. Check loader failures clearly identify the issue; do not install ad hoc developer DLLs to make the clean test pass without updating the ZIP/build.
6. Record installed/portable data-folder behavior if both are available; the contract resolves through `Se.SpeechToTextFolder` rather than hard-coded `%APPDATA%`.

No clean environment is currently verified. Obtaining one is execution work, not a reason to claim that the existing developer smoke proves portability.

## 4. Three-clip quality comparison

- Select three representative Vietnamese clips spanning the user's actual material. The repository currently has a Vietnamese news video under ignored `x64/`, and CaptionHelper has permitted local sample audio; neither is automatically proof of coverage for other speakers/dialects. Pick explicit clip IDs/ranges before running, and ask the user only if representative content cannot be determined from available media/context. Do not fetch media or commit it.
- Feed the exact same decoded audio/audio-track selection to Gipformer and an existing local Whisper engine with model **large-v3-turbo**, forced Vietnamese, transcription rather than translation. Record the actual baseline engine/version/model and compute settings, plus Gipformer source/pack/build identity.
- Match Subtitle Edit's line length, timing adjustment and post-processing settings for both final editable outputs. Record unavoidable backend differences (VAD/decoding); do not tune only the winner after seeing review results. Recognition equivalence with CaptionHelper is a separate pre-postprocessing smoke, not this baseline comparison.
- Ask the user to correct paired outputs to the same acceptable subtitle standard. Record correction counts per clip in three categories: text (replace/insert/delete one Vietnamese whitespace-delimited token = one correction), punctuation/casing (one affected token = one correction), timing (one cue start/end adjusted = one correction). Record category accounting before review; if one operation affects multiple categories, count it in each relevant category for both engines consistently. Optionally record editing time as context, not a new acceptance threshold.
- Use a comparison table in `reports/quality-comparison.md` with actual numbers only: clip ID, engine/model, text corrections, punctuation/casing corrections, timing corrections and total. Do not fill counts with estimates or zero as a placeholder. Until review exists, label results pending.
- **Pass:** sum of the three Gipformer totals is strictly less than sum of the three large-v3-turbo totals, and the user confirms the outputs need less editing overall. No new percentage target is invented. Do not claim superior WER from correction counts.
- **If not passed:** report technical integration separately and keep quality acceptance pending/unmet. Do not silently swap models, remove a difficult clip, disable timing comparison, make Gipformer the default or add a forced aligner. Present observed failures and ask before any change beyond the confirmed pipeline/scope.

## 5. Documentation after smoke proof

- Update `docs/features/speech-to-text.md`: engine/platform/language, manual-install exception to "Engines and models are downloaded automatically on first use", offline operation, whole-file/batch/selected-line behavior, supported flags, native word-end approximation, no translation/aligner/GPU and no universal quality claim.
- Update `docs/third-party-components.md`: one ZIP root, exact extraction destination under Data Folder, how to open that folder, runtime+pack layout, diagnosis of double nesting/missing `_internal`, licenses/notices and upgrade procedure. Upgrading replaces only the add-on's owned folder after closing running inference; do not prescribe deleting unrelated engines or user data.
- Add the feature under the current heading in `change-log.txt`, not the historical `Changelog.txt`. State optional Windows x64 Vietnamese STT/local add-on, not "better accuracy" without the quality result.
- Verify embedded help loads and canonical English localization keys agree with the delivered controls. Do not mass-edit translator-owned JSON files.
- Remove throwaway scripts and stale Qwen-specific helper aliases after a clean rename. Keep the reusable artifact build script and actual behavioral tests. Store screenshots/logs/transcripts locally in ignored output where sensitive; reports contain only necessary non-private evidence.

## Release/acceptance gates

Public redistribution remains blocked until source owner permission and bundled-native obligations are documented. User saying "continue" after cancelling the license question did not grant MIT permission. Do not modify the CaptionHelper checkout or fabricate license text. A self-contained local test ZIP can be built and exercised while that release gate is unresolved.

Technical verification, clean-machine verification and quality acceptance are separate checkboxes. A finished adapter with an unmet human quality/release gate is not "all done". Finish every reachable item and report exactly which gate remains and the evidence needed.

## Checklist

- [x] Run the integrated .NET 10 build, focused STT tests and full UI suite; record actual results. (build clean; 93 focused passed; full suite 8058 total / 8009 passed / 49 skipped / 0 failed)
- [ ] Exercise every actual-app scenario, including process EOF/cancel, selected-line offsets and another local engine. (blocked: no way to drive the desktop window in this session; headless window + state-machine coverage only - see reports/verification.md)
- [ ] Verify the actual ZIP offline in clean Windows x64 without developer/Python/CaptionHelper prerequisites. (blocked: no fresh VM/Sandbox available; the extraction ran on this workstation)
- [ ] Run the paired three-clip comparison and obtain recorded user correction counts/sign-off. (closed as NOT MET by the reviewer's verdict on 2026-10-29; counts not collected - reports/quality-comparison.md)
- [x] Update feature docs, third-party docs, embedded help/localization if needed, and active changelog after smoke proof. (`docs/features/speech-to-text.md`, `docs/third-party-components.md`, `change-log.txt`, English keys, embedded help)
- [x] Remove throwaway scaffolds, retain reusable build/tests, and record remaining release/quality gates accurately. (no scaffolds left; `installer/gipformer/` kept; gates recorded in reports/verification.md)
