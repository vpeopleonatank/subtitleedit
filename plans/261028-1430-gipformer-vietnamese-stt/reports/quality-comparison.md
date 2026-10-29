---
report: quality-comparison
status: NOT-PASSED (reviewer verdict, 2026-10-29)
created: 2026-10-29
---
# Recognition quality comparison (not passed)

This report is the plan's human quality gate: three Vietnamese clips, transcribed with Gipformer - Vietnamese and with the user's existing large-v3-turbo Whisper baseline, then counted by the reviewer. **Outcome: the gate was closed as NOT MET by the reviewer's verdict on 2026-10-29** - the Gipformer output was judged worse, counts were not collected, and the engine stays in the app as a secondary option. Nothing here is inferred from WER or from the integration tests.

## Method (fixed by the plan)

1. Pick three real clips from the reviewer's own material: one clean narration/interview, one with background music or noise, one with fast speech, dialect or numbers (the clips where a small Vietnamese-first model should differ most from a multilingual one).
2. For each clip, transcribe once with `Gipformer — Vietnamese` (default settings, `--vad on`) and once with the local Whisper engine using `large-v3-turbo`, same audio, same language (Vietnamese), translation off.
3. The reviewer edits both outputs to acceptable subtitles, counting four kinds of corrections per clip: text (words), punctuation/casing, timing, and the total.
4. Record only the counts below - no transcripts, no media, no private text.

## Results

Correction counts were **not collected**: the reviewer compared the two outputs directly and judged the Gipformer transcription worse on the first clip, then decided (2026-10-29) to keep the engine as a secondary/optional engine and record this gate as **not met** rather than spend the review on counted edits. No numbers are invented here.

| Clip (ID only) | Engine / model | Text | Punctuation/casing | Timing | Total |
|---|---|---|---|---|---|
| reviewed clip | Gipformer - Vietnamese / `gipformer1.5-vi` | not counted | not counted | not counted | not counted |
| reviewed clip | Whisper / `large-v3-turbo` | not counted | not counted | not counted | not counted |

**Pass rule:** the sum of the three Gipformer totals is strictly lower than the sum of the three Whisper totals, and the reviewer confirms the Gipformer output needs less editing overall.

**Verdict:** not met. The reviewer's judgement is that `large-v3-turbo` is better; the shipped pack is a 68M-parameter model against roughly 809M, and the fixed pipeline has no prompt/beam/hotword lever to change that.

## Reviewer feedback so far (no counts yet)

- On a first try the reviewer judged the output **worse than `large-v3-turbo`**. That matches the pack that is actually shipped: Gipformer 1.5 is a 68M-parameter fp32 RNN-T (encoder 261 MB) against roughly 809M parameters for large-v3-turbo, and the pipeline exposes no prompt, beam-size or hotword control to close that gap - only VAD on/off and thread count. No accuracy claim is made in the docs or changelog, and the pass rule below therefore stays **unmet** unless the counted table shows otherwise.
- VAD is present (Silero, on by default); it is not a quality lever here - turning it off decodes fixed chunks and makes long-pause behaviour worse.

## Status

- Technical integration: verified separately in [verification.md](verification.md).
- Quality claim: **not made**. A successful integration, a clean protocol and native timings do not establish better recognition; only the counts above, if the pass rule holds, support "needs less editing on these three clips".
- Reviewer decision (2026-10-29): keep the engine as a secondary option; quality gate closed as **not met**. No accuracy claim is made anywhere in docs, help text or changelog.

## Observed behaviour worth knowing before reviewing

- The engine is Vietnamese-only. Audio in another language is still decoded (no error), but produces degraded text; the reviewer should compare only Vietnamese clips.
- Word ends are approximated by the sidecar (last token time padded by 0.12 s, capped at the next word), so timing corrections should be judged with that in mind - cue ends are close, not frame-exact.
- Numbers arrive already normalized to digits by the engine's ITN, so digit formatting corrections and wrong-number corrections are both "text corrections".
