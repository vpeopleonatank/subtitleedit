"""sherpa-onnx backend: gipformer1.5 (Vietnamese RNN-T) with Silero VAD, number ITN and vibert-capu punctuation.

Pipeline ideas (gap-fill VAD, vibert-capu usage) ported from welcomyou/sherpa-vietnamese-asr
(MIT, commit 350f5a4; upstream license: "Copyright (c) 2025 [Your Name]" - the placeholder is verbatim).

Pack layout under ``--model-dir``: ``model/{encoder,decoder,joiner}.onnx``, ``model/tokens.txt``,
``punct/{vibert-capu.int8.onnx,vocab.txt,vocabulary/labels.txt}``, ``silero_vad.onnx``.

Steps: decode (16 kHz, peak-normalised) -> Silero VAD with gap-fill (VAD Off: fixed overlapping chunks instead) ->
batched transducer decode -> words (BPE tokens merged, end = last token + END_PAD_S capped at the next start) -> ITN ->
punctuation -> segments per window. Every tuned constant is a module constant; nothing reads the environment.
"""

import os

import numpy as np
import sherpa_onnx

import vi_itn
import vi_punct
import word_timing
from engine_errors import EngineError

ENGINE = "sherpa-onnx"
LANGUAGE = "vi"
SAMPLE_RATE = 16000

PAUSE_S = 0.7  # a gap this long after a VAD segment's last word forces a full stop
KEEP_BIAS = 0.3  # added to the $KEEP probability of vibert-capu
END_PAD_S = 0.12  # word end = last token start + this, capped at the next word start

VAD_THRESHOLD = 0.5
VAD_FILL_THRESHOLD = 0.2
VAD_FILL_GAP_S = 2.0
VAD_MIN_SILENCE_S = 0.25
VAD_MIN_SPEECH_S = 0.25
VAD_MAX_SPEECH_S = 20.0
VAD_BUFFER_S = 180

# VAD Off: fixed chunks. Windows are at most CHUNK_S + 2 * CHUNK_OVERLAP_S = VAD_MAX_SPEECH_S,
# i.e. no longer than what VAD On already produces.
CHUNK_S = 18.0
CHUNK_OVERLAP_S = 1.0

BATCH = 4
DECODE_PERCENT = 90.0  # decode batches map to 0..90 %, punctuation to 90..100 %
PEAK_TARGET = 0.95
PEAK_FLOOR = 0.5
MIN_WORD_S = 0.02

PACK_FILES = (
    os.path.join("model", "encoder.onnx"),
    os.path.join("model", "decoder.onnx"),
    os.path.join("model", "joiner.onnx"),
    os.path.join("model", "tokens.txt"),
    os.path.join("punct", vi_punct.MODEL_FILE),
    os.path.join("punct", vi_punct.VOCAB_FILE),
    os.path.join("punct", vi_punct.LABELS_FILE),
    "silero_vad.onnx",
)


def check_pack(model_dir):
    for name in PACK_FILES:
        if not os.path.isfile(os.path.join(model_dir, name)):
            raise EngineError("Model pack is incomplete: missing " + name.replace(os.sep, "/"))


def _decode_audio(path):
    from faster_whisper.audio import decode_audio  # PyAV, already bundled for the Whisper engine

    return decode_audio(path, sampling_rate=SAMPLE_RATE)


def make_recognizer(model_dir, threads):
    base = os.path.join(model_dir, "model")
    return sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=os.path.join(base, "encoder.onnx"),
        decoder=os.path.join(base, "decoder.onnx"),
        joiner=os.path.join(base, "joiner.onnx"),
        tokens=os.path.join(base, "tokens.txt"),
        num_threads=threads,
        sample_rate=SAMPLE_RATE,
        feature_dim=80,
        decoding_method="modified_beam_search",
        max_active_paths=8,
    )


def make_vad(model_dir, threshold, min_silence, max_speech):
    """-> (VoiceActivityDetector, window size in samples)."""
    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = os.path.join(model_dir, "silero_vad.onnx")
    config.silero_vad.threshold = threshold
    config.silero_vad.min_silence_duration = min_silence
    config.silero_vad.min_speech_duration = VAD_MIN_SPEECH_S
    config.silero_vad.max_speech_duration = max_speech
    config.sample_rate = SAMPLE_RATE
    vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=VAD_BUFFER_S)
    return vad, config.silero_vad.window_size


def make_punctuator(punct_dir, threads):
    return vi_punct.Punctuator(punct_dir, keep_bias=KEEP_BIAS, threads=threads)


def vad_segments(samples, vad_factory, threshold, max_speech=VAD_MAX_SPEECH_S):
    """Speech spans as (start, end) sample indices. ``vad_factory(threshold, min_silence, max_speech)`` -> (vad, window)."""
    vad, window = vad_factory(threshold, VAD_MIN_SILENCE_S, max_speech)
    spans = []

    def drain():
        while not vad.empty():
            front = vad.front
            spans.append((front.start, front.start + len(front.samples)))
            vad.pop()

    for index in range(0, len(samples), window):
        vad.accept_waveform(samples[index:index + window])
        drain()
    vad.flush()
    drain()
    return spans


def speech_segments(samples, vad_factory, threshold=VAD_THRESHOLD, fill_threshold=VAD_FILL_THRESHOLD, fill_gap=VAD_FILL_GAP_S):
    """VAD at ``threshold``; every uncovered stretch of at least ``fill_gap`` s is rescanned at ``fill_threshold``,
    so speech over loud background (where Silero stays under 0.5 for the whole clip) is not silently dropped."""
    spans = vad_segments(samples, vad_factory, threshold)
    if fill_threshold is None:
        return spans
    bounds = [0] + [edge for span in spans for edge in span] + [len(samples)]
    out = list(spans)
    for low, high in zip(bounds[::2], bounds[1::2]):
        if high - low >= fill_gap * SAMPLE_RATE:
            out += [(low + s, low + e) for s, e in vad_segments(samples[low:high], vad_factory, fill_threshold)]
    return sorted(out)


def windows_for(spans, total):
    """(start, end, keep_from, keep_to, speech_start) per span: no padding; a word belongs to the window whose
    half of the gap to the neighbouring span it starts in."""
    windows = []
    for index, (start, end) in enumerate(spans):
        low = (spans[index - 1][1] + start) // 2 if index else 0
        high = (end + spans[index + 1][0]) // 2 if index + 1 < len(spans) else total
        windows.append((start, end, low, high, start))
    return windows


def fixed_windows(total, chunk_s=CHUNK_S, overlap_s=CHUNK_OVERLAP_S):
    """VAD-off windows, same 5-tuples as ``windows_for``: keep ranges [c0, c1) tile [0, total); each window is padded by
    ``overlap_s`` on both sides so words cut at a chunk edge are decoded whole and kept by the window that owns their start."""
    chunk = int(chunk_s * SAMPLE_RATE)
    overlap = int(overlap_s * SAMPLE_RATE)
    windows = []
    for c0 in range(0, total, chunk):
        c1 = min(total, c0 + chunk)
        start = max(0, c0 - overlap)
        windows.append((start, min(total, c1 + overlap), c0, c1, start))
    return windows


def words_from(result, offset, segment_end, segment=0, end_pad=END_PAD_S):
    """Merge BPE tokens into words. A token starting with a space or ``▁`` opens a new word.

    Word start = first token time + ``offset``; end = min(last token time + ``end_pad``, next word start; the window
    end for the last word); ``p`` = mean token probability; ``seg_last`` marks the last word of the window.
    """
    tokens, stamps, log_probs = result.tokens, result.timestamps, result.ys_log_probs
    if not tokens:
        return []
    words = []
    for token, stamp, log_prob in zip(tokens, stamps, log_probs):
        if token.startswith((" ", "\u2581")) or not words:
            words.append({"text": token.lstrip(" \u2581"), "start": offset + stamp, "last": offset + stamp, "lps": [log_prob]})
        else:
            words[-1]["text"] += token
            words[-1]["last"] = offset + stamp
            words[-1]["lps"].append(log_prob)
    words = [word for word in words if word["text"]]
    out = []
    for index, word in enumerate(words):
        following = words[index + 1]["start"] if index + 1 < len(words) else segment_end
        out.append({
            "text": word["text"],
            "start": word["start"],
            "end": min(word["last"] + end_pad, following),
            "p": float(np.mean(np.exp(word["lps"]))),
            "seg": segment,
            "seg_last": index + 1 == len(words),
        })
    return out


def decode(recognizer, samples, windows, on_batch=None):
    """Batched transducer decode. Word starts are clamped to the VAD speech start, ends to start + MIN_WORD_S."""
    out = []
    for first in range(0, len(windows), BATCH):
        batch = windows[first:first + BATCH]
        streams = []
        for start, end, *_ in batch:
            stream = recognizer.create_stream()
            stream.accept_waveform(SAMPLE_RATE, samples[start:end])
            streams.append(stream)
        recognizer.decode_streams(streams)
        for offset, (window, stream) in enumerate(zip(batch, streams)):
            start, end, keep_from, keep_to, speech_start = window
            for word in words_from(stream.result, start / SAMPLE_RATE, end / SAMPLE_RATE, first + offset):
                if not keep_from / SAMPLE_RATE <= word["start"] < keep_to / SAMPLE_RATE:
                    continue
                word["start"] = max(word["start"], speech_start / SAMPLE_RATE)
                word["end"] = max(word["end"], word["start"] + MIN_WORD_S)
                out.append(word)
        if on_batch is not None:
            on_batch(min(first + BATCH, len(windows)), len(windows))
    return out


def group_segments(words):
    """Regroup words by VAD window index; segment bounds are its first and last word."""
    segments = []
    current = None
    for word in words:
        if current is None or word["seg"] != current["seg"]:
            current = {"seg": word["seg"], "words": []}
            segments.append(current)
        current["words"].append(word)
    return [{"start": s["words"][0]["start"], "end": s["words"][-1]["end"], "words": s["words"]} for s in segments]


def transcribe(args, manifest, emit, recognizer_factory=None, vad_factory=None, punctuator_factory=None, decode_audio=None):
    """Run the pipeline and return the normalized transcript. ``emit`` writes one JSON line.

    The factories are test seams: ``recognizer_factory(model_dir, threads)``, ``vad_factory(threshold, min_silence,
    max_speech) -> (vad, window)``, ``punctuator_factory(punct_dir, threads)``, ``decode_audio(path) -> float32 mono 16 kHz``.

    With ``args.start``/``args.end`` only that range of the decoded samples is recognized; word times are shifted back
    to media time and progress / duration refer to the range.
    """
    if args.language != LANGUAGE:
        raise EngineError("This model pack supports Vietnamese only.")
    model_dir = args.model_dir
    check_pack(model_dir)
    threads = args.threads if args.threads > 0 else min(4, os.cpu_count() or 1)

    samples = (decode_audio or _decode_audio)(args.input)
    offset = 0.0
    if args.start is not None:
        offset = args.start
        samples = samples[int(round(args.start * SAMPLE_RATE)):int(round(args.end * SAMPLE_RATE))]
        if not len(samples):
            raise EngineError("The range %s-%s s is outside the media." % (args.start, args.end))
    peak = float(np.abs(samples).max()) if len(samples) else 0.0
    if 0 < peak < PEAK_FLOOR:
        samples = samples * (PEAK_TARGET / peak)
    duration = len(samples) / SAMPLE_RATE
    emit({"type": "info", "engine": ENGINE, "device": "cpu", "compute_type": "float32", "duration": round(duration, 3)})

    if args.vad == "off":
        windows = fixed_windows(len(samples))
    else:
        if vad_factory is None:
            def vad_factory(threshold, min_silence, max_speech):
                return make_vad(model_dir, threshold, min_silence, max_speech)
        windows = None

    recognizer = (recognizer_factory or make_recognizer)(model_dir, threads)
    punctuator = (punctuator_factory or make_punctuator)(os.path.join(model_dir, "punct"), threads)

    def on_batch(done, total):
        emit({"type": "progress", "percent": round(DECODE_PERCENT * done / total, 1), "stage": "transcribe"})

    if windows is None:
        windows = windows_for(speech_segments(samples, vad_factory), len(samples))
    words = decode(recognizer, samples, windows, on_batch)
    for word in words:
        word["start"] += offset
        word["end"] += offset
    if words:
        words = vi_punct.punctuate(vi_itn.itn(words), punctuator, pause=PAUSE_S)
    emit({"type": "progress", "percent": 100.0, "stage": "transcribe"})

    return {
        "language": LANGUAGE,
        "duration": round(duration, 3),
        "segments": word_timing.normalize_segments(group_segments(words), LANGUAGE),
    }
