"""faster-whisper (CTranslate2) backend for Windows and macOS (Apple Silicon: CPU int8, no Metal backend)."""

import itertools
import os
import sys

import word_timing
from engine_errors import EngineError

ENGINE = "faster-whisper"

ZH_PROMPTS = {
    "hans": "以下是普通话的句子。",
    "hant": "以下是普通話的句子。",
}

CPU_COMPUTE_TYPES = ("int8", "float32")

SAMPLE_RATE = 16000


GPU_PACK_ENV = "CAPTIONHELPER_GPU_DIR"


def gpu_pack_dirs(env=None, platform=None, executable=None, frozen=None):
    """Folders that may hold the separately installed GPU pack (flat cuBLAS/cuDNN DLLs), best match first.

    1. ``CAPTIONHELPER_GPU_DIR`` (override), 2. ``%APPDATA%\\CaptionHelper\\gpu`` (where install-windows.ps1 puts it),
    3. ``gpu`` next to the frozen executable. See docs/gpu-pack.md.
    """
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    executable = sys.executable if executable is None else executable
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if platform != "win32":
        return []
    folders = []
    if env.get(GPU_PACK_ENV):
        folders.append(env[GPU_PACK_ENV])
    if env.get("APPDATA"):
        folders.append(os.path.join(env["APPDATA"], "CaptionHelper", "gpu"))
    if frozen:
        folders.append(os.path.join(os.path.dirname(executable), "gpu"))
    return folders


def _add_cuda_dll_dirs():
    """Make cuBLAS/cuDNN visible to ctranslate2: the GPU pack folders, or (development) the pip nvidia-* packages."""
    if sys.platform != "win32":
        return
    folders = [folder for folder in gpu_pack_dirs() if os.path.isdir(folder)]
    for entry in list(sys.path):
        for package in ("cublas", "cudnn"):
            folders.append(os.path.join(entry, "nvidia", package, "bin"))
    for folder in folders:
        if os.path.isdir(folder):
            os.add_dll_directory(folder)
            os.environ["PATH"] = folder + os.pathsep + os.environ.get("PATH", "")


def _whisper_model_class():
    from faster_whisper import WhisperModel  # lazy: keeps import-time cost out of dispatch/tests

    return WhisperModel


def _model_path(model_dir):
    path = os.path.join(model_dir, "model")
    return path if os.path.isdir(path) else model_dir


def pick_language(all_language_probs, candidates):
    """The ``(code, probability)`` with the highest probability among ``candidates`` (None: any language)."""
    for code, probability in sorted(all_language_probs, key=lambda item: item[1], reverse=True):
        if candidates is None or code in candidates:
            return code, probability
    raise EngineError("Language detection returned none of the selected languages.")


def _decode_audio(path):
    from faster_whisper.audio import decode_audio  # lazy: keeps import-time cost out of dispatch/tests

    return decode_audio(path, sampling_rate=SAMPLE_RATE)


def range_audio(path, start, end):
    """Decoded samples of media time [start, end) s. Raises EngineError when the range holds no audio."""
    samples = _decode_audio(path)[int(round(start * SAMPLE_RATE)):int(round(end * SAMPLE_RATE))]
    if not len(samples):
        raise EngineError("The range %s-%s s is outside the media." % (start, end))
    return samples


def _open_stream(model_class, model_path, audio, language, zh_script, candidates, device, compute_type, threads, vad_filter):
    """Load the model, resolve ``auto`` to a language, and start transcription. Primes the generator.

    Returns ``(info, stream, language, probability)``; ``probability`` is None unless the language was detected.

    faster-whisper is lazy: a broken CUDA runtime (the Quadro M4000 case, ``cudaErrorInvalidDevice``)
    only fails when the first segment is decoded, so pull one item here to surface it.
    """
    model = model_class(model_path, device=device, compute_type=compute_type, cpu_threads=threads)
    probability = None
    if language == "auto":
        if isinstance(audio, str):
            audio = _decode_audio(audio)
        _, _, all_language_probs = model.detect_language(audio, vad_filter=vad_filter)
        language, probability = pick_language(all_language_probs, candidates)
        sys.stderr.write(
            "[caption-engine] detected %s (%.3f) among %d candidates\n"
            % (language, probability, len(candidates) if candidates else len(all_language_probs))
        )
        sys.stderr.flush()
    segments, info = model.transcribe(
        audio,
        language=language,
        word_timestamps=True,
        vad_filter=vad_filter,
        beam_size=5,
        condition_on_previous_text=False,
        initial_prompt=ZH_PROMPTS[zh_script] if language == "zh" else None,
    )
    iterator = iter(segments)
    sentinel = object()
    first = next(iterator, sentinel)
    if first is sentinel:
        return info, iter(()), language, probability
    return info, itertools.chain([first], iterator), language, probability


def resolve_attempts(device, compute_type, platform=None):
    """Ordered (device, compute_type) attempts. macOS has no CUDA: every device choice resolves to cpu/int8."""
    platform = sys.platform if platform is None else platform
    if platform == "darwin":
        return [("cpu", "int8")]
    attempts = []
    if device in ("auto", "cuda"):
        attempts.append(("cuda", "float32" if compute_type == "auto" else compute_type))
    if device in ("auto", "cpu"):
        attempts.append(("cpu", compute_type if compute_type in CPU_COMPUTE_TYPES else "int8"))
    return attempts


def transcribe(args, manifest, emit, model_class=None):
    """Run the model and return the normalized transcript. ``emit`` writes one JSON line.

    With ``args.start``/``args.end`` only that range is decoded and fed to the model; times are shifted back to media
    time and progress / duration refer to the range.
    """
    if model_class is None:
        _add_cuda_dll_dirs()
        model_class = _whisper_model_class()

    model_path = _model_path(args.model_dir)
    candidates = args.detect_among
    threads = max(args.threads, 0)
    offset = args.start if args.start is not None else 0.0
    audio = range_audio(args.input, args.start, args.end) if args.start is not None else args.input

    attempts = resolve_attempts(args.device, args.compute_type)

    fallback_reason = None
    info = stream = device = None
    for index, (device, compute_type) in enumerate(attempts):
        try:
            info, stream, language, probability = _open_stream(
                model_class, model_path, audio, args.language, args.zh_script, candidates,
                device, compute_type, threads, args.vad == "on",
            )
            break
        except Exception as error:  # noqa: BLE001 - ctranslate2 raises plain RuntimeError
            if index + 1 == len(attempts):
                raise
            fallback_reason = "%s failed: %s" % (device, error)
            sys.stderr.write("[caption-engine] %s; retrying on cpu/int8\n" % fallback_reason)
            sys.stderr.flush()

    duration = float(info.duration) if info.duration else 0.0
    message = {"type": "info", "engine": ENGINE, "device": device, "compute_type": compute_type, "duration": round(duration, 3)}
    if probability is not None:
        message["language"] = language
        message["language_probability"] = round(probability, 3)
    if fallback_reason:
        message["fallback_reason"] = fallback_reason
    emit(message)

    raw_segments = []
    for segment in stream:
        words = [
            {"text": word.word, "start": word.start + offset, "end": word.end + offset, "p": word.probability}
            for word in (segment.words or [])
        ]
        raw_segments.append({"start": segment.start + offset, "end": segment.end + offset, "words": words})
        percent = min(100.0, segment.end / duration * 100.0) if duration > 0 else 0.0
        emit({"type": "progress", "percent": round(percent, 1), "stage": "transcribe"})

    return {
        "language": language,
        "duration": round(duration, 3),
        "segments": word_timing.normalize_segments(raw_segments, language),
    }
