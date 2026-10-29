"""Verify a prepared sherpa-onnx pack and write its canonical ``model.json``.

The pinned revisions and file hashes come from the vendored ``engine/prepare_model.py``, so a pack
is accepted only when its ASR, punctuation and VAD bytes match the pinned upstream artifacts - not
merely its own local manifest. Run with any CPython 3.9+ (the add-on build uses the locked 3.11
venv):

    python installer/gipformer/make_pack_manifest.py --pack <prepared-pack-dir>

Writes ``<pack>/model.json`` (formatVersion 1) describing every other file in the pack and prints
the source label. Exit code 1 with a readable message when verification fails.
"""

import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "engine"))

import prepare_model  # noqa: E402  (path set up above)

PACK_ID = "gipformer1.5-vi"
PACK_NAME = "gipformer 1.5 (Vietnamese only)"
LANGUAGE = "vi"

# Top-level entries that belong to the pack; anything else is an unexpected extra.
ALLOWED_TOP_LEVEL = {"model", "punct", "silero_vad.onnx", "NOTICE.md", "model.json"}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def pack_files(pack):
    """Every file under the pack except the manifest itself, as sorted slash-separated paths."""
    out = []
    for root, _, names in os.walk(pack):
        for name in names:
            path = os.path.join(root, name)
            relative = os.path.relpath(path, pack).replace(os.sep, "/")
            if relative == "model.json":
                continue
            out.append(relative)
    return sorted(out)


def verify(pack):
    """Raise PrepareError unless the pack matches the pinned upstream artifacts."""
    extras = set(os.listdir(pack)) - ALLOWED_TOP_LEVEL
    if extras:
        raise prepare_model.PrepareError("unexpected top-level entries in pack: %s" % ", ".join(sorted(extras)))
    # Pinned bytes, independent of whatever the local model.json claims.
    prepare_model.verify_hashes(os.path.join(pack, "model"), prepare_model.GIPFORMER_FILES)
    prepare_model.verify_hashes(os.path.join(pack, "punct"), prepare_model.VIBERT_FILES)
    prepare_model.verify_hashes(pack, {"silero_vad.onnx": prepare_model.SILERO_SHA256})
    # Structure, non-empty required files, and parseable tokens/labels.
    prepare_model.check_sherpa_folder(pack)


def write_manifest(pack):
    files = {relative: sha256(os.path.join(pack, relative)) for relative in pack_files(pack)}
    manifest = {
        "formatVersion": 1,
        "id": PACK_ID,
        "name": PACK_NAME,
        "engine": "sherpa-onnx",
        "source": prepare_model.sherpa_source_label(),
        "files": files,
        "languages": [LANGUAGE],
    }
    path = os.path.join(pack, "model.json")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify a sherpa-onnx pack and write its model.json")
    parser.add_argument("--pack", required=True, help="prepared pack folder (NOTICE.md, model/, punct/, silero_vad.onnx)")
    parser.add_argument("--check-only", action="store_true", help="verify without rewriting model.json")
    args = parser.parse_args(argv)

    pack = os.path.abspath(args.pack)
    if not os.path.isdir(pack):
        print("Pack folder not found: %s" % pack, file=sys.stderr)
        return 1
    try:
        verify(pack)
    except prepare_model.PrepareError as error:
        print("Pack verification failed: %s" % error, file=sys.stderr)
        return 1

    if args.check_only:
        print(len(pack_files(pack)))
        return 0

    manifest = write_manifest(pack)
    print("%s (%d files) %s" % (manifest["id"], len(manifest["files"]), manifest["source"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
