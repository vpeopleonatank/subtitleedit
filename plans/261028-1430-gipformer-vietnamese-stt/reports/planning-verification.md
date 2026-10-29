# Planning verification

Date: 2026-10-28. Planning only; no integration code exists yet and no build/test/publish command was run for it.

## Observed command results

| Command / check | Observed result | What it does not prove |
|---|---|---|
| `ak plan create ... --basedir D:/Project/subtitleedit/plans --json` | Created `261028-1430-gipformer-vietnamese-stt`, then two `add-phase` calls created phases 2 and 3 | Implementation |
| `ak plan validate D:/Project/subtitleedit/plans/261028-1430-gipformer-vietnamese-stt --json` | `valid: true`, no format errors | Correctness of future C#/Python implementation |
| Local plan-file/link check | Four Markdown plan/phase files; three relative phase links resolve; six unchecked tasks per phase; pending frontmatter and no generated stubs | Runtime integration |
| `ak plan reindex --apply --path D:/Project/subtitleedit --json` | Recognized one plan with three phases, store id `subtitleedit/261028-1430` | Acceptance/completion |
| `ak plan use ... --json` | Pinned worktree-private current-plan path | Permission to implement/ship |
| `dotnet --version` | Exit 145, `No .NET SDKs were found` | .NET build/test success; .NET 10 remains prerequisite |
| C# LSP status | No configured language servers | References were checked using scoped code searches; refresh at implementation |
| Bundled FFmpeg DLL license APIs | `avutil_license()` and `avcodec_license()` returned `LGPL version 3 or later`; configuration enables x264/x265 and both DLLs are present | Full binary/component redistribution clearance |
| Earlier advisory real-engine smoke | Existing CaptionHelper executable transcribed 90-second WAV, CPU, progress and final word result, observed 9.83 seconds | Accuracy, current-source binary parity, clean-machine install |

## Fact and contract sample

Thirty source claims were checked across the three phases. These are source facts, not claims that future behavior has been exercised. Proposed new files are explicitly marked in the phase ownership tables and excluded from existing-file checks.

### Phase 1 — packaging (10)

1. `caption_engine.py:1-19` defines stdout JSON-lines contract and CLI.
2. `caption_engine.py:125-160` emits final result, reports structured exceptions/nonzero exit, and calls freeze support.
3. `sherpa_backend.py:69-72` imports faster-whisper audio decode; removing it is not safe dependency pruning.
4. `sherpa_backend.py:75-87` constructs the transducer recognizer from encoder/decoder/joiner/tokens.
5. `sherpa_backend.py:232-288` enforces Vietnamese and emits CPU information/normalized words.
6. `requirements-win.txt:1-4` pins four direct dependency versions; it is not a transitive lock.
7. `caption_engine.spec:20-48` includes both backends, collects native libraries and excludes CUDA prefixes.
8. `scripts/build-engine-windows.ps1:38-67` requires Python 3.11 and builds/freezes a complete onedir runtime.
9. `prepare_model.py:272-312` verifies and copies the ASR/punctuation/VAD files and writes notices, returning the pinned source label.
10. `build/pack-gipformer/model.json:1-23` supplies pack id/engine/source/files/languages. `make-model-zip.js:104-113` supplies the existing manifest shape used by the packaging plan.

CaptionHelper paths in this subsection are relative to `D:/Project/AdobePlugin/CaptionHelper`.

### Phase 2 — integration (10)

1. `ISpeechToTextEngine.cs:8-80` supplies existing engine/model/install/parameter/help methods; no capability interface expansion is required.
2. `WhisperChoice.cs:5-39` stores stable string engine identities.
3. `SeAudioToText.cs:12-38` stores engine/model/language and per-engine parameters.
4. `SpeechToTextViewModel.cs:273-323,421-442` registers engines and restores saved selection.
5. Same file `:532-580` has an auto-language whitelist and a translation exclusion predicate that must account for Gipformer.
6. Same file `:4106-4227` enters generic engine/model download prompts without a manual-local engine exemption.
7. Same file `:4596-4635` combines stdout/stderr in one callback; the protocol needs separate handlers.
8. Same file `:898-920,969-992` disposes before special result handling and uses SRT/Whisper JSON for the generic route.
9. `MainViewModel.cs:11161-11196` maps by clip identity and applies original start only when replacing a long line with multiple cues.
10. `Qwen3AsrWordSegmenter.cs:13-46,91-130` contains reusable cue logic. Scoped search found one production consumer file (`SpeechToTextViewModel.cs:1395-1421`) and one test consumer file (`Qwen3AsrWordSegmenterTests.cs`); migration is explicit. No compatibility shim planned.

Source roots: `src/ui/Features/Video/SpeechToText/`, `src/ui/Features/Main/`, `src/ui/Logic/Config/`, and `src/libuilogic/AudioToText/` under `D:/Project/subtitleedit`.

### Phase 3 — verification/docs (10)

1. `src/ui/UI.csproj:4` targets net10.0.
2. `tests/UI/UITests.csproj:5,17-27` targets net10.0 and references xUnit/Avalonia headless/UI project.
3. `tests/UI/README.md:29-38` documents `dotnet test tests/UI/UITests.csproj` and solution tests.
4. `tests/UI/SettingsScope.cs:7-20,46-61,83-90` snapshots/restores changed static settings.
5. `SpeechToTextViewModel.cs:2077-2181` applies batch results/exports and advances jobs, cleaning previous temp files.
6. Same file `:2194-2270` delivers completed selected clips and retains prior completed clips after cancellation.
7. Same file `:6261-6311` owns window-close cancellation and process-tree termination.
8. `src/ui/UI.csproj:75-76` embeds speech-to-text Python/text assets; explicit new help filename needs no manual per-file inclusion.
9. `docs/features/speech-to-text.md:27,95-105` claims automatic downloads and describes existing STT UI, requiring the manual add-on exception.
10. `docs/third-party-components.md:13-21,29-39` documents actual data-folder variants; `change-log.txt:6-17` is current beta changelog, unlike historical `Changelog.txt`.

### Whole-plan self-check

- Verified sampled source claims: 30. Failed source claims in authored plan: 0. Runtime claims intentionally unverified: all future implementation/clean-machine/quality behavior.
- Contract-sensitive changes are isolated: no ISpeechToTextEngine signature change; helper rename migrates the verified consumer files; parser state is per attempt; source checkout remains read-only.
- Direct binding verification after draft creation resolved the only conditional UI edit: `SpeechToTextWindow.cs:168-177` binds the hint solely to a button tooltip, so the plan now requires a visible local-install hint.
- Independent review is complete: three reviewers, nine raw findings, eight unique after merging the duplicate lock requirement. User approved six corrections and two rejected recommendations on 2026-10-29; dispositions and evidence are in plan.md.

## Final approved-plan checks — 2026-10-29

- Reread `plan.md`, `phase-01-start.md`, `phase-02-engine-and-workflows.md` and `phase-03-verification-and-quality.md` after review edits. Six accepted corrections and the two rejected recommendations were reconciled across the relevant contracts, scenarios and index. Unresolved contradictions: 0.
- `ak plan validate D:/Project/subtitleedit/plans/261028-1430-gipformer-vietnamese-stt --json` returned `valid: true`, `errors: null` after all approved edits.
- Final local check passed: four plan/phase files, five resolvable Markdown links, eighteen unchecked phase items, all implementation statuses pending, dependency graph acyclic (`1,2 -> 3`), no generated stubs, and approved review requirements present.
- Changes remain planning artifacts only. No integration build/tests were run; no claim of implementation, public-release clearance, clean-machine acceptance or three-clip quality acceptance is made.
