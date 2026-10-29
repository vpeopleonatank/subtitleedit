---
title: "Gipformer Vietnamese STT integration"
description: "Add an offline Windows x64 Gipformer engine to Subtitle Edit using a manually installed self-contained add-on."
status: in-progress
status-note: "phases 1-3 done; quality gate closed NOT MET; clean-VM run and desktop-UI interaction still open"
priority: P2
effort: ""
branch: main
tags: [feature, frontend, backend]
blockedBy: []
blocks: []
created: 2026-10-28
---

# Gipformer Vietnamese STT integration

## Overview

Add **Gipformer — Vietnamese** to Subtitle Edit's existing Speech to text window. Reuse CaptionHelper's CPU inference pipeline as a private executable and adapt its JSON-lines protocol to Subtitle Edit. Ship one local add-on ZIP, installed by manual extraction. Preserve every existing engine and all three standard workflows. This document authorizes planning only; implementation starts through an explicitly invoked cook workflow.

Scope mode: **HOLD SCOPE**. Planning depth: hard, because packaging, native dependencies, process lifecycle, timing and UI gates cross several boundaries. Architecture was confirmed during the advisory interview; do not reopen it without contradictory evidence. No generic STT framework, downloader integration or dependency slimming is needed.

## Confirmed requirements

1. Windows x64 CPU only; optional engine, not a replacement/default change.
2. A separate add-on ZIP contains the entire frozen runtime, complete Gipformer 1.5 Vietnamese model pack, provenance and third-party notices.
3. Users manually extract the ZIP under the actual Subtitle Edit STT data directory. No installed Python, CaptionHelper checkout, GPU runtime or network is needed for transcription.
4. Preserve CaptionHelper's recognition, Silero VAD, inverse text normalization, punctuation/casing and word timestamps before Subtitle Edit cue building and optional post-processing. Exact Premiere caption breaks are not required.
5. Whole-file, batch-file and selected-line workflows support progress, cancellation, remembered engine selection and normal subtitle editing/export.
6. Missing/incomplete installations, protocol failures and engine failures are explicit. Never silently fall back to another engine or accept a crashed run as silence.
7. Gipformer offers Vietnamese only. Do not expose language detection, speech translation, forced alignment, speaker detection or GPU choices.
8. Quality acceptance is fewer total manual text, punctuation and timing corrections than **Whisper large-v3-turbo** across **three representative Vietnamese clips**, reviewed by the user under matching subtitle settings.

## Non-goals and repository boundary

No native C# inference rewrite; no Premiere code/UI; no in-app add-on installer, model import workflow, release hosting or automatic engine/model download; no new forced aligner; no GPU, macOS, Linux or Windows ARM64 package. Do not change unrelated engines/settings or translate other locales on behalf of translators. Do not commit media, model weights, virtual environments or generated executables.

The CaptionHelper checkout at `D:/Project/AdobePlugin/CaptionHelper` is read-only. All implementation, vendored runtime snapshot, build scripts and documentation belong to `D:/Project/subtitleedit`. Do not commit/push/open a PR or publish artifacts without a separate delivery request. If shipping is later requested, follow the repository's dedicated-branch/PR/review rules.

## Architecture and contracts

- Adapter: a new `GipformerEngine` implementing existing `ISpeechToTextEngine`; one model identity `gipformer1.5-vi`, language `vi`, stable saved choice `Gipformer`.
- Protocol: existing UTF-8 newline-delimited `info`, `progress`, `result`, `error` messages. Only stdout is protocol; stderr is diagnostic. Parse the large final result once, do not log/store repeated copies of the transcript.
- Completion: accept only after successful exit, stdout/stderr fully drained, exactly one valid final result and no error. Progress 100 is not completion. Silence is a valid empty result, not malformed output.
- Audio: use existing local audio extraction and track selection. Do not use sidecar `--start/--end` for selected-line jobs: inputs are already extracted clips.
- Time: engine input starts at zero for extracted clips. `MainViewModel.cs:11178-11183` already adds the selected line start when replacing a long line with multiple cues. Do not offset again in the adapter; short-line text replacement preserves original line timing.
- Cues: reuse existing `Qwen3AsrWordSegmenter` rules via a narrowly renamed neutral helper/type, preserving Qwen3 behavior and migrating its production/test consumers. No alternate Node/CEP segmentation pipeline.
- Lifecycle: retain `_whisperProcess` ownership for cancel/window-close cleanup, but give Gipformer dedicated stdout/stderr handling and completion synchronization. Do not send JSON into the generic Whisper console regex/result-file fallback.
- No public interface extension is planned. Explicit Gipformer UI/preflight branches are narrower than adding capabilities to every engine. `DownloadsOwnModels` remains false; pretending it downloads models would hide a real missing pack.

### Add-on contract

Extract the archive's **contents into `[Data Folder]/SpeechToText`**, creating exactly:

```text
Gipformer/
  addon.json                    # version/platform/source/file hash manifest
  runtime/
    caption-engine.exe
    _internal/...
  pack/
    model.json
    NOTICE.md
    model/{encoder.onnx,decoder.onnx,joiner.onnx,tokens.txt,LICENSE}
    punct/{vibert-capu.int8.onnx,vocab.txt,ATTRIBUTION.md,vocabulary/labels.txt}
    silero_vad.onnx
  licenses/...
  BUILD-INFO.txt
```

`addon.json` is local provenance/completeness metadata, not a remotely signed trust claim. Define one format version and reject incompatible architecture/version. List packaged files using slash-separated relative paths, sizes and SHA-256. Build verification checks all hashes. Runtime installation checks are lightweight: manifest identity, executable, packaged native dependencies and required non-empty model files; avoid hashing hundreds of MiB on every engine-picker render. Missing native dependencies must additionally surface as launch/loader errors. Do not reuse `.installed.sha256` without a registered download hash key; this manually installed add-on has no download service entry.

Trust boundary: users install and explicitly run trusted local executable code, as with other native STT engines. Structural readiness checks and co-delivered hashes do not authenticate it against an attacker who replaces the package or installed files. Document obtaining the add-on from a trusted source and comparing its archive checksum to a separately retained build receipt. No signing/update trust infrastructure or claimed malware protection is part of this manual-local integration; revisit that design if automatic distribution/installation is requested.

## Phases and ownership

| Phase | Deliverable | Dependencies | Status |
|---|---|---|---|
| 1 — [Runtime and add-on packaging](phase-01-start.md) | Pinned source snapshot, frozen executable, complete local ZIP and provenance | None | Done (release still gated) |
| 2 — [Engine and workflows](phase-02-engine-and-workflows.md) | Engine metadata, protocol adapter, cues, install gates and all workflows | None; consumes the fixed add-on/protocol contract above | Done |
| 3 — [Verification and quality](phase-03-verification-and-quality.md) | Runtime/UI proof, regression results, docs and three-clip acceptance | Phases 1 and 2 | Done; quality gate NOT MET, 2 evidence gates open |

Phases 1 and 2 have disjoint implementation ownership; phase 2 need not wait for redistribution permission or a finished ZIP to implement the accepted protocol. Execute in one worktree conservatively; parallel coding is not required. Phase 3 is the integration owner. Run the focused build/test verification after integration, not concurrently with incomplete sibling edits. Build script's own frozen-engine smoke is part of producing phase 1's artifact.

## Known prerequisites and release gates

- **Build prerequisite:** `dotnet --version` returned "No .NET SDKs were found" on this workstation. UI and UI tests target `net10.0`. Locate/provision .NET 10 before compilation; no C# build/test result is claimed here.
- Build host needs Windows x64 Python 3.11, a fresh isolated virtual environment and the pinned build dependencies. Python is a maintainer prerequisite only.
- **Source redistribution unresolved:** no root `LICENSE*`/`COPYING*` was found in CaptionHelper; `package.json:4` marks it private and has no license field. The licensing question was cancelled; user said continue. That is NOT MIT authorization. Record provenance honestly, continue reachable implementation/planning, and block public distribution until owner permission is documented. Do not invent a LICENSE.
- **Native component licensing:** bundled `avutil` and `avcodec` report "LGPL version 3 or later" via their license APIs. Build configuration also enables libx264/libx265 and corresponding DLLs are present. This disproves inferring a blanket GPL classification from names alone, but is not redistribution clearance. Inventory actual bundled binaries/licenses/source obligations; do not label everything MIT or blanket-LGPL. Escalate unresolved rights before public distribution; no decoder rewrite is pre-authorized.
- **Acceptance prerequisite:** clean Windows x64 environment and user review of paired three-clip outputs are still required. Do not mark quality accepted when only technical integration passes.

## Evidence map

All repository paths below are existing; proposed files are listed in phase files.

| Evidence | Verified conclusion |
|---|---|
| `src/ui/Features/Video/SpeechToText/Engines/ISpeechToTextEngine.cs:8-80` | Existing engine metadata/install/model/help/parameter contract |
| `src/ui/Features/Video/SpeechToText/SpeechToTextViewModel.cs:273-323,421-442` | Engine registration and saved-choice restore |
| Same file `:532-580,5619-5704` | Auto-language whitelist, permissive translation predicate and model/UI setup |
| Same file `:4106-4227,5725-5747` | Missing engines/models currently reach download paths; non-downloadable engine hint is suppressed |
| Same file `:4461-4635,5238-5367` | Local launch helper merges stdout/stderr and generic handler treats data as console text |
| Same file `:898-920,969-992,2843-2925` | Timer disposes process before result handling; special engine completion route is needed |
| Same file `:2077-2181,2194-2270,6261-6311` | Batch/selected-line delivery, cancellation and window-close process ownership |
| `src/ui/Features/Main/MainViewModel.cs:11161-11196` | Clip-to-line identity and single application of media offsets |
| `src/ui/Features/Video/SpeechToText/Qwen3AsrWordSegmenter.cs:13-46,91-130` | Existing word-to-cue sentence/pause/length logic |
| CaptionHelper `engine/caption_engine.py:1-19,125-160` | JSON-lines protocol, result/error exit semantics and frozen multiprocessing support |
| CaptionHelper `engine/backends/sherpa_backend.py:69-87,232-288` | Audio decode dependency, Vietnamese-only CPU pipeline and normalized word result |
| CaptionHelper `engine/caption_engine.spec:20-48` and `scripts/build-engine-windows.ps1:38-67` | Both backends/native dependencies bundled; CUDA DLLs filtered; Python 3.11 |
| CaptionHelper `build/pack-gipformer/model.json:1-23` | Pack identity, pinned revisions and file hashes |
| `src/ui/UI.csproj:4,75-76`; `tests/UI/UITests.csproj:5,17-27` | .NET 10, embedded help assets, headless xUnit tests |
| `docs/features/speech-to-text.md:27,95-105`; `change-log.txt:6-17` | Manual-install docs exception and active changelog target |

Earlier advisory smoke evidence: existing frozen CaptionHelper executable ran `scratch/vad-off-smoke-90s.wav` with the real pack and `--language vi --vad on`; exit succeeded, progress reached 100, a timed-word result was returned, observed wall time 9.83 seconds. No accuracy comparison or clean-machine proof. Its `--help` lacks the source's range flags, so do not ship that stale binary without rebuilding.

## Done means

- [ ] Phase 1 produces a complete ZIP that operates on clean Windows x64 without Python/CaptionHelper/network; source/native redistribution permission is documented before public distribution. *ZIP built and verified (60 checks, real audio); clean-machine run and redistribution permission still open.*
- [x] Phase 2 supports whole-file, batch and selected-line jobs, including correct timing, completion/error distinction, cancellation and remembered selection; other engines remain usable.
- [ ] Phase 3 records real UI/runtime proof and relevant regression results; missing packs, process/protocol failures and no-speech are observably distinct. *Runtime proof and regression results recorded; desktop-UI interaction not exercised.*
- [x] Documentation, active changelog and third-party notices match the actual archive and behavior; no obsolete Qwen-specific helper aliases or throwaway smoke scaffolds remain.
- [ ] User review records fewer total corrections than large-v3-turbo over the same three clips. An unmet quality gate remains unchecked and is reported separately, never silently waived. *Closed as NOT MET on 2026-10-29: reviewer judged the output worse than large-v3-turbo and chose to keep the engine as a secondary option (counts not collected). Recorded in [quality-comparison](reports/quality-comparison.md); no accuracy claim anywhere.*

## Validation log

Implementation (2026-10-29): phases 1 and 2 executed end to end; evidence in [verification](reports/verification.md). Phase 3 is partially blocked - the desktop window cannot be driven from this session, no clean VM was available, and the human quality comparison is pending. Details and exact gate wording in the phase 3 checklist.

Scope/architecture reused from the user's explicit advisory confirmation. Source permission remains unresolved after cancelled question followed by "continue". Source paths and lifecycle contracts checked directly; no C# LSP configured, so consumer lookup used scoped text searches. On 2026-10-29 the user selected **Approve reviewed draft**, approving the six corrections and two rejected recommendations below. This approves the plan only, not implementation, publication or redistribution rights.

### Verification results

- Tier: Standard (Fact Checker + Contract Verifier); 30 sampled source claims checked. Verified: 30; failed source claims: 0. Future implementation, clean-machine behavior and quality remain unverified, not passing results.
- AgentKit format validation returned `valid: true` before review; final format/link/invariant validation follows the consistency sweep. Detailed observations: [planning verification](reports/planning-verification.md).
- Three independent reviewers produced nine findings, reduced to eight unique findings by merging the duplicate hash-lock recommendation. Six accepted corrections are requirements in the phase files, not claims that implementation exists.

## Red Team Review

| Finding | Approved disposition | Evidence and plan change |
|---|---|---|
| Launch failure stops batch | Accept | `SpeechToTextViewModel.cs:3049-3054,4568-4577,5173-5174`; phase 2 requires single-finalization failure/advance handling, phase 3 exercises process-start failure |
| Empty success has no feedback | Accept | Same file `:2893-2924`; phase 2 requires explicit Gipformer no-speech feedback, phase 3 checks silence |
| Extraction cancel strands completed clips | Accept | Same file `:2959-2969`; phase 2 offers prior completed clips once unless closing, phase 3 exercises both extraction/inference cancellation |
| x64 architecture merely asserted | Accept | CaptionHelper `scripts/build-engine-windows.ps1:38-51` checks version, not architecture; phase 1 verifies interpreter/venv and native PE Machine before metadata |
| Hashed lock not enforced by build | Accept; duplicate merged | Same script `:45-46`; phase 1 requires exclusive hash-enforced locked-wheel installation including build/preparation dependencies |
| Manifest excluded from its own hash proof | Accept | Phase 1 explicitly excludes `addon.json` from its map; external receipt covers final manifest and ZIP bytes, phase 3 verifies retained receipt |
| Require authenticated signatures before launch | Reject; trust limit explicit | Sidecar `caption_engine.py:97-108` does not authenticate the package. Confirmed scope is manual installation of trusted local executable code, not a new distribution/signing system. Readiness/checksum checks make no malware/authenticity claim; revisit for automatic distribution |
| Bound threads by CPU count/fixed cap | Reject | Sidecar `caption_engine.py:80`, `sherpa_backend.py:245` intentionally allow local thread tuning. No remote settings channel is introduced; a CPU-count cap changes accepted tuning semantics without an evidenced requirement. Invalid CLI syntax remains an actionable error |

### Whole-plan consistency sweep

- Decision deltas: six accepted corrections plus two explicit rejection/trust-boundary decisions. Architecture, source permissions, quality target, phase ownership and dependencies remain unchanged.
- Reconciled phase 1 build/receipt contract, phase 2 launch/empty/cancel routes, phase 3 actual-app scenarios and clean-machine receipt verification. No self-hash requirement, silent batch-stop assumption or implicit empty-feedback assumption remains authoritative.
- Final reread/format/link/invariant results are recorded in [planning verification](reports/planning-verification.md). No unresolved product decision remains. Build prerequisites and release/human-quality gates remain explicit execution constraints.

## Execution handoff

Invoke `/ak:cook D:/Project/subtitleedit/plans/261028-1430-gipformer-vietnamese-stt/plan.md` when implementation is authorized. Do not infer autonomous execution, commits, publication or a license grant from plan creation. Stop for unexplained blocking failures, destructive/irreversible changes, work beyond the confirmed repository/scope, unresolved redistribution permission at the release boundary, or final human quality acceptance. Continue other reachable tasks when a gate blocks only one deliverable.

<!-- slug: gipformer-vietnamese-stt -->
