"""caption-engine: local speech-to-text sidecar that emits JSON lines on stdout.

Contract (see plans/.../phase-02-core-transcription-pipeline.md):

    caption-engine --model-dir <add-on dir> --input <media> --language <whisper code, e.g. vi|en|zh|fr|ja>|auto [--detect-among vi,en,...]
                   [--zh-script hans|hant] [--device auto|cuda|cpu] [--compute-type auto|float32|float16|int8] [--threads N]
                   [--vad on|off] [--start <seconds> --end <seconds>]

    --start/--end (media time, given together, end > start >= 0) recognize only that range of the audio; word and
    segment times stay media time, "duration" (info and transcript) is the length of the range.

    {"type":"info","engine":...,"device":...,"duration":...}   (+ "language", "language_probability" when --language auto)
    {"type":"progress","percent":37.5,"stage":"transcribe"}
    {"type":"result","transcript":{language,duration,segments:[{start,end,words:[{text,start,end,p,eos?}]}]}}
    {"type":"error","message":"..."}          exit code != 0

The backend named by ``<model-dir>/model.json`` ``engine`` is imported lazily: ``faster-whisper`` (multilingual Whisper)
and ``sherpa-onnx`` (Vietnamese-only gipformer pack; sets ``eos`` on sentence-final words). Both run on Windows, macOS
and Linux.
"""

import argparse
import importlib
import json
import math
import os
import sys

from engine_errors import EngineError

# Registry: engine name -> (module, platforms the backend can run on).
BACKENDS = {
    "faster-whisper": ("backends.faster_whisper_backend", ("win32", "linux", "darwin")),
    "sherpa-onnx": ("backends.sherpa_backend", ("win32", "linux", "darwin")),
}

# Every language of the multilingual Whisper large-v3 / large-v3-turbo models; keep in sync with ENGINE_LANGUAGES in core/language-map.js.
LANGUAGES = (
    "en", "zh", "de", "es", "ru", "ko", "fr", "ja", "pt", "tr", "pl", "ca", "nl", "ar", "sv", "it", "id", "hi", "fi", "vi",
    "he", "uk", "el", "ms", "cs", "ro", "da", "hu", "ta", "no", "th", "ur", "hr", "bg", "lt", "la", "mi", "ml", "cy", "sk",
    "te", "fa", "lv", "bn", "sr", "az", "sl", "kn", "et", "mk", "br", "eu", "is", "hy", "ne", "mn", "bs", "kk", "sq", "sw",
    "gl", "mr", "pa", "si", "km", "sn", "yo", "so", "af", "oc", "ka", "be", "tg", "sd", "gu", "am", "yi", "lo", "uz", "fo",
    "ht", "ps", "tk", "nn", "mt", "sa", "lb", "my", "bo", "tl", "mg", "as", "tt", "haw", "ln", "ha", "ba", "jw", "su", "yue",
)


def emit(message):
    """Write one JSON object per line and flush so the Node side sees it immediately."""
    sys.stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def configure_stdio():
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def parse_language_list(value):
    codes = tuple(code for code in (part.strip() for part in value.split(",")) if code)
    if not codes:
        raise argparse.ArgumentTypeError("expected a comma-separated list of language codes")
    unknown = [code for code in codes if code not in LANGUAGES]
    if unknown:
        raise argparse.ArgumentTypeError("unsupported language code(s): %s" % ", ".join(unknown))
    return codes


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="caption-engine", description="Local word-level transcription")
    parser.add_argument("--model-dir", required=True, help="model add-on directory containing model.json")
    parser.add_argument("--input", required=True, help="audio or video file")
    parser.add_argument("--language", required=True, choices=LANGUAGES + ("auto",))
    parser.add_argument("--detect-among", type=parse_language_list, default=None, metavar="CODES",
                        help="comma-separated Whisper codes Auto may pick from (default: every language)")
    parser.add_argument("--zh-script", choices=("hans", "hant"), default="hans")
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    parser.add_argument("--compute-type", choices=("auto", "float32", "float16", "int8"), default="auto")
    parser.add_argument("--threads", type=int, default=0)
    parser.add_argument("--vad", choices=("on", "off"), default="on")
    parser.add_argument("--start", type=float, default=None, metavar="SECONDS", help="range start (media time); needs --end")
    parser.add_argument("--end", type=float, default=None, metavar="SECONDS", help="range end (media time); needs --start")
    return parser.parse_args(argv)


def check_range(start, end):
    """Validate the optional ``--start``/``--end`` pair. Raises EngineError unless both are absent or end > start >= 0."""
    if start is None and end is None:
        return
    if start is None or end is None:
        raise EngineError("--start and --end must be given together")
    if not (math.isfinite(start) and math.isfinite(end) and end > start >= 0):
        raise EngineError("Invalid range --start %s --end %s: expected end > start >= 0" % (start, end))


def load_manifest(model_dir):
    path = os.path.join(model_dir, "model.json")
    if not os.path.isfile(path):
        raise EngineError("model.json not found in " + model_dir)
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            manifest = json.load(handle)
    except (OSError, ValueError) as error:
        raise EngineError("model.json is not valid: " + str(error))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("engine"), str):
        raise EngineError("model.json has no 'engine' field")
    return manifest


def load_backend(engine, platform=None):
    """Import only the backend that is needed. Raises EngineError when unavailable on this OS."""
    platform = platform or sys.platform
    if engine not in BACKENDS:
        raise EngineError("Unknown engine '%s' in model.json" % engine)
    module_name, platforms = BACKENDS[engine]
    if platform not in platforms:
        raise EngineError("Engine '%s' is not available on this OS (%s)" % (engine, platform))
    try:
        return importlib.import_module(module_name)
    except ImportError as error:
        raise EngineError("Engine '%s' is not installed: %s" % (engine, error))


def run(args, backend_loader=load_backend):
    check_range(args.start, args.end)
    if not os.path.isfile(args.input):
        raise EngineError("Input file not found: " + args.input)
    manifest = load_manifest(args.model_dir)
    backend = backend_loader(manifest["engine"])
    transcript = backend.transcribe(args, manifest, emit)
    emit({"type": "result", "transcript": transcript})


def main(argv=None):
    configure_stdio()
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as exit_request:
        # argparse already wrote usage to stderr; make stdout say it too.
        if exit_request.code not in (0, None):
            emit({"type": "error", "message": "Invalid arguments (see stderr)"})
        return int(exit_request.code or 0)
    try:
        run(args)
    except EngineError as error:
        emit({"type": "error", "message": str(error)})
        return 1
    except Exception as error:  # noqa: BLE001 - last resort: surface as a JSON error line
        emit({"type": "error", "message": "%s: %s" % (type(error).__name__, error)})
        return 1
    return 0


if __name__ == "__main__":
    # Frozen builds: multiprocessing children re-execute this binary.
    # PyInstaller's freeze_support runs them and exits before argparse writes an error line to the shared stdout.
    import multiprocessing
    multiprocessing.freeze_support()
    sys.exit(main())
