"""Maintainer tool: lay out a model folder that scripts/make-model-zip.js can pack.

faster-whisper (the one model pack for Windows and macOS), pinned Hugging Face revision:

    python engine/prepare_model.py --engine faster-whisper --out scratch/prepared/large-v3-turbo-ct2
    node scripts/make-model-zip.js --dir scratch/prepared/large-v3-turbo-ct2 \
        --id large-v3-turbo --name "Whisper large-v3-turbo" --source <printed source>

sherpa-onnx (Vietnamese pack: gipformer 1.5 + ViBERT-capu punctuation + Silero VAD), pinned revisions
and pinned file hashes:

    python engine/prepare_model.py --engine sherpa-onnx --out build/prepared-gipformer
    node scripts/make-model-zip.js --engine sherpa-onnx --dir build/prepared-gipformer \
        --id gipformer1.5-vi --name "gipformer 1.5 (Vietnamese only)" --source <printed source>

``--source-dir`` reuses a folder that was already downloaded from the pinned repo (no network); the
folder is verified against the pinned revision recorded in its ``.cache/huggingface`` metadata, or the
caller must pass ``--trust-source-dir`` for a folder without that metadata. For sherpa-onnx the folder
holds ``gipformer/``, ``vibert/`` (both Hugging Face downloads) and ``silero_vad.onnx``.

"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.request

FASTER_WHISPER_REPO = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
FASTER_WHISPER_REVISION = "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf"
FASTER_WHISPER_FILES = ("model.bin", "config.json", "tokenizer.json", "vocabulary.json", "preprocessor_config.json")

# sherpa-onnx pack: fp32 gipformer 1.5 (RNN-T), int8 ViBERT-capu punctuation, Silero VAD.
GIPFORMER_REPO = "g-group-ai-lab/gipformer1.5-68M-rnnt"
GIPFORMER_REVISION = "dd9227dcd8705c13f33bdbe59728d546ab94480f"
GIPFORMER_FILES = {
    "encoder.onnx": "96b3c83c9c39afc4421f8fd2914d26b53ae837e56788a7bd5aece61580937c36",
    "decoder.onnx": "ea584ee86d6f74191f934f8b950013adcb2c33483785aa8b1b44fff3a7b30069",
    "joiner.onnx": "d146a1cff4a0060d7031e5eb91295773661bc52c356c952dd1e2759e60ffa94d",
    "tokens.txt": "f536d03c2e95ebd2930cf0abec88e823bd17d3c1933da7ae6a82db3b80605e15",
}
VIBERT_REPO = "welcomyou/vibert-capu-onnx"
VIBERT_REVISION = "a7754d037f4a9e29f7f3224f27acb60149eab874"
VIBERT_FILES = {
    "vibert-capu.int8.onnx": "67278b23502bbd744538e2bd9a6748b61cce171cfba6c671c2e2a46f892166fa",
    "vocab.txt": "b32ccb4ca8bee5eda7a0f55f7adebaa515be742c9f765151ffefcd29fcb542a1",
    "vocabulary/labels.txt": "a31075cfa185b5d24c3b65c009ad0740636b286090f78419eaba2d34202c2b45",
}
SILERO_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx"
SILERO_SHA256 = "9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6"


class PrepareError(Exception):
    pass


def source_label(repo, revision):
    return "%s@%s" % (repo, revision)


def download_snapshot(repo, revision, out_dir, files):
    """Download exactly ``files`` of ``repo`` at ``revision`` into ``out_dir``."""
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:  # pragma: no cover - environment problem
        raise PrepareError("huggingface_hub is not installed (pip install -r engine/requirements-win.txt)") from exc
    snapshot_download(repo_id=repo, revision=revision, local_dir=out_dir, allow_patterns=list(files))


def recorded_revisions(folder):
    """Revisions recorded by huggingface_hub in <folder>/.cache/huggingface/download/*.metadata."""
    meta_dir = os.path.join(folder, ".cache", "huggingface", "download")
    revisions = set()
    if not os.path.isdir(meta_dir):
        return revisions
    for name in os.listdir(meta_dir):
        if not name.endswith(".metadata"):
            continue
        with open(os.path.join(meta_dir, name), "r", encoding="utf-8") as handle:
            first = handle.readline().strip()
        if first:
            revisions.add(first)
    return revisions


def verify_source_dir(folder, revision, trust):
    if not os.path.isdir(folder):
        raise PrepareError("--source-dir is not a folder: %s" % folder)
    revisions = recorded_revisions(folder)
    if revisions:
        if revisions != {revision}:
            raise PrepareError(
                "--source-dir was downloaded from revision(s) %s, expected %s" % (sorted(revisions), revision)
            )
    elif not trust:
        raise PrepareError("--source-dir has no Hugging Face revision metadata; pass --trust-source-dir to use it anyway")


def copy_files(src_dir, out_dir, files):
    missing = [name for name in files if not os.path.isfile(os.path.join(src_dir, name))]
    if missing:
        raise PrepareError("missing files in %s: %s" % (src_dir, ", ".join(missing)))
    os.makedirs(out_dir, exist_ok=True)
    for name in files:
        shutil.copyfile(os.path.join(src_dir, name), os.path.join(out_dir, name))


def check_ct2_folder(folder):
    """Sanity-check a CTranslate2 folder: required files exist and config.json parses."""
    for name in FASTER_WHISPER_FILES:
        path = os.path.join(folder, name)
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            raise PrepareError("%s is missing or empty in %s" % (name, folder))
    with open(os.path.join(folder, "config.json"), "r", encoding="utf-8") as handle:
        json.load(handle)


def prepare_faster_whisper(out_dir, source_dir=None, trust_source_dir=False,
                           repo=FASTER_WHISPER_REPO, revision=FASTER_WHISPER_REVISION):
    if os.path.isdir(out_dir) and os.listdir(out_dir):
        raise PrepareError("--out must be empty or missing: %s" % out_dir)
    if source_dir:
        verify_source_dir(source_dir, revision, trust_source_dir)
        copy_files(source_dir, out_dir, FASTER_WHISPER_FILES)
    else:
        os.makedirs(out_dir, exist_ok=True)
        download_snapshot(repo, revision, out_dir, FASTER_WHISPER_FILES)
        # snapshot_download leaves a .cache folder beside the files; the zip builder ignores dot entries.
    check_ct2_folder(out_dir)
    return source_label(repo, revision)


MIT_TEXT = """Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

GIPFORMER_LICENSE = (
    "Licensed under the MIT License per the model card declaration (`license: mit`) at\n"
    "https://huggingface.co/%s/blob/%s/README.md\n"
    "Upstream publishes no LICENSE file.\n\n"
    "MIT License\n\n"
    + MIT_TEXT
) % (GIPFORMER_REPO, GIPFORMER_REVISION)

VIBERT_ATTRIBUTION = """# ViBERT-capu ONNX (punctuation and capitalization), unmodified

- Title: ViBERT-capu ONNX (INT8)
- Author: welcomyou (ONNX conversion) of the original model dragonSwing/vibert-capu by dragonSwing,
  which is fine-tuned from the base model FPTAI/vibert-base-cased
- Source: https://huggingface.co/%(repo)s/tree/%(rev)s
- License: Creative Commons Attribution-ShareAlike 4.0 International (CC-BY-SA-4.0),
  https://creativecommons.org/licenses/by-sa/4.0/ - declared as `license: cc-by-sa-4.0` in the model
  card at https://huggingface.co/%(repo)s/blob/%(rev)s/README.md; upstream publishes no LICENSE file
- Changes: none (unmodified). `vibert-capu.int8.onnx`, `vocab.txt` and `vocabulary/labels.txt` are
  byte-identical to the files at the source revision above.
"""

NOTICE = """# Third-party notices: gipformer 1.5 Vietnamese model pack

This pack bundles the following components, each unmodified.

Neither Hugging Face repository below ships a LICENSE file. The licenses stated here are the ones declared
in the pinned model cards (README.md front matter and text) at the listed revisions.

## gipformer 1.5 (speech recognition) - MIT (model card declaration)
- Files: `model/encoder.onnx`, `model/decoder.onnx`, `model/joiner.onnx`, `model/tokens.txt`
- Source: https://huggingface.co/%(gip_repo)s @ %(gip_rev)s
- Author: G-Group AI Lab. License text: `model/LICENSE`.

## ViBERT-capu ONNX (punctuation and capitalization) - CC-BY-SA-4.0 (model card declaration)
- Files: `punct/vibert-capu.int8.onnx`, `punct/vocab.txt`, `punct/vocabulary/labels.txt`
- Source: https://huggingface.co/%(vib_repo)s @ %(vib_rev)s
- Original model: dragonSwing/vibert-capu; base model: FPTAI/vibert-base-cased
- License: https://creativecommons.org/licenses/by-sa/4.0/ - see `punct/ATTRIBUTION.md`.

## Silero VAD (voice activity detection) - MIT
- File: `silero_vad.onnx` (sha256 %(silero_sha)s)
- Source: %(silero_url)s
- Upstream: https://github.com/snakers4/silero-vad

```
MIT License

Copyright (c) 2020-present Silero Team

""" + MIT_TEXT + """```

## Pipeline ideas
The decoding pipeline of the Caption Helper engine (VAD gap fill, RNN-T segment batching, punctuation
restoration) ports ideas from welcomyou/sherpa-vietnamese-asr (MIT),
https://github.com/welcomyou/sherpa-vietnamese-asr.
"""


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_hashes(folder, expected):
    """Raise PrepareError unless every file in ``expected`` (name -> sha256) exists under ``folder`` with that hash."""
    missing = [name for name in expected if not os.path.isfile(os.path.join(folder, name))]
    if missing:
        raise PrepareError("missing files in %s: %s" % (folder, ", ".join(missing)))
    for name, digest in expected.items():
        actual = sha256_file(os.path.join(folder, name))
        if actual != digest:
            raise PrepareError("sha256 mismatch for %s: expected %s, got %s" % (os.path.join(folder, name), digest, actual))


def fetch_silero(dest, url=SILERO_URL):
    with urllib.request.urlopen(url, timeout=120) as response, open(dest, "wb") as handle:
        shutil.copyfileobj(response, handle)


def check_sherpa_folder(folder):
    """Sanity-check a prepared sherpa-onnx pack: required files exist and are non-empty, tokens/labels parse."""
    required = (
        ["silero_vad.onnx", "NOTICE.md", os.path.join("model", "LICENSE"), os.path.join("punct", "ATTRIBUTION.md")]
        + [os.path.join("model", name) for name in GIPFORMER_FILES]
        + [os.path.join("punct", name) for name in VIBERT_FILES]
    )
    for name in required:
        path = os.path.join(folder, name)
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            raise PrepareError("%s is missing or empty in %s" % (name, folder))
    with open(os.path.join(folder, "model", "tokens.txt"), "r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            parts = line.rstrip("\n").rsplit(" ", 1)
            if len(parts) != 2 or not parts[1].isdigit():
                raise PrepareError("model/tokens.txt line %d is not '<token> <id>'" % number)
    with open(os.path.join(folder, "punct", "vocabulary", "labels.txt"), "r", encoding="utf-8") as handle:
        if not [line for line in handle.read().splitlines() if line.strip()]:
            raise PrepareError("punct/vocabulary/labels.txt has no labels")


def sherpa_source_label():
    return "%s@%s + %s@%s + silero_vad.onnx@%s" % (
        GIPFORMER_REPO, GIPFORMER_REVISION, VIBERT_REPO, VIBERT_REVISION, SILERO_SHA256[:8]
    )


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def prepare_sherpa(out_dir, source_dir=None, trust_source_dir=False):
    """Lay out the sherpa-onnx pack in ``out_dir``; returns the source label for make-model-zip.js."""
    if os.path.isdir(out_dir) and os.listdir(out_dir):
        raise PrepareError("--out must be empty or missing: %s" % out_dir)
    with tempfile.TemporaryDirectory(prefix="sherpa-src-") as scratch:
        if source_dir:
            gip_dir = os.path.join(source_dir, "gipformer")
            vib_dir = os.path.join(source_dir, "vibert")
            silero = os.path.join(source_dir, "silero_vad.onnx")
            verify_source_dir(gip_dir, GIPFORMER_REVISION, trust_source_dir)
            verify_source_dir(vib_dir, VIBERT_REVISION, trust_source_dir)
            if not os.path.isfile(silero):
                raise PrepareError("missing files in %s: silero_vad.onnx" % source_dir)
        else:
            gip_dir = os.path.join(scratch, "gipformer")
            vib_dir = os.path.join(scratch, "vibert")
            silero = os.path.join(scratch, "silero_vad.onnx")
            download_snapshot(GIPFORMER_REPO, GIPFORMER_REVISION, gip_dir, tuple(GIPFORMER_FILES))
            download_snapshot(VIBERT_REPO, VIBERT_REVISION, vib_dir, tuple(VIBERT_FILES))
            fetch_silero(silero)
        verify_hashes(gip_dir, GIPFORMER_FILES)
        verify_hashes(vib_dir, VIBERT_FILES)
        verify_hashes(os.path.dirname(silero), {os.path.basename(silero): SILERO_SHA256})
        os.makedirs(out_dir, exist_ok=True)
        shutil.copyfile(silero, os.path.join(out_dir, "silero_vad.onnx"))
        for name in GIPFORMER_FILES:
            copy_files(gip_dir, os.path.join(out_dir, "model"), [name])
        for name in VIBERT_FILES:
            target = os.path.join(out_dir, "punct", name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(os.path.join(vib_dir, name), target)
    write_text(os.path.join(out_dir, "model", "LICENSE"), GIPFORMER_LICENSE)
    write_text(os.path.join(out_dir, "punct", "ATTRIBUTION.md"),
               VIBERT_ATTRIBUTION % {"repo": VIBERT_REPO, "rev": VIBERT_REVISION})
    write_text(os.path.join(out_dir, "NOTICE.md"), NOTICE % {
        "gip_repo": GIPFORMER_REPO, "gip_rev": GIPFORMER_REVISION,
        "vib_repo": VIBERT_REPO, "vib_rev": VIBERT_REVISION,
        "silero_sha": SILERO_SHA256, "silero_url": SILERO_URL,
    })
    check_sherpa_folder(out_dir)
    return sherpa_source_label()


ENGINES = {"faster-whisper": prepare_faster_whisper, "sherpa-onnx": prepare_sherpa}


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Prepare a model folder for scripts/make-model-zip.js")
    parser.add_argument("--engine", required=True, choices=tuple(ENGINES))
    parser.add_argument("--out", required=True, help="empty or new folder that receives the model files")
    parser.add_argument("--source-dir",
                        help="reuse an already downloaded copy of the pinned repo(s) instead of downloading "
                             "(sherpa-onnx: a folder with gipformer/, vibert/ and silero_vad.onnx)")
    parser.add_argument("--trust-source-dir", action="store_true",
                        help="accept --source-dir without Hugging Face revision metadata")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        source = ENGINES[args.engine](args.out, args.source_dir, args.trust_source_dir)
    except PrepareError as exc:
        sys.stderr.write("prepare_model: %s\n" % exc)
        return 1
    print(json.dumps({"engine": args.engine, "dir": args.out, "source": source}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
