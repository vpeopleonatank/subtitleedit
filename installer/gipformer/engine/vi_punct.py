"""Vietnamese punctuation and casing on timed words with vibert-capu (a GECToR seq2labels model run on onnxruntime).

Pipeline ideas (vibert-capu usage) ported from welcomyou/sherpa-vietnamese-asr (MIT, commit 350f5a4).
The ONNX model files are used unmodified.

Words in:  [{"text", "start", "end", "p", "seg", "seg_last"}] (lower-case, as returned by ``vi_itn.itn``).
Words out: the same dicts with cased, punctuated ``text`` and an ``eos`` flag (sentence-final "." or "?").
"""

import os

import numpy as np

from engine_errors import EngineError

KEEP_BIAS = 0.3
PAUSE_S = 0.7
CHUNK = 56
OVERLAP = 16
ITERATIONS = 3

MODEL_FILE = "vibert-capu.int8.onnx"
VOCAB_FILE = "vocab.txt"
LABELS_FILE = os.path.join("vocabulary", "labels.txt")


def _require(path):
    if not os.path.isfile(path):
        raise EngineError("Model pack is incomplete: missing " + path)
    return path


def _read_session(path, threads):
    import onnxruntime as ort  # lazy: keeps import-time cost out of tests and dispatch

    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    return ort.InferenceSession(path, options, providers=["CPUExecutionProvider"])


class Punctuator:
    def __init__(self, punct_dir, keep_bias=KEEP_BIAS, chunk=CHUNK, overlap=OVERLAP, threads=4, session_factory=None):
        vocab_path = _require(os.path.join(punct_dir, VOCAB_FILE))
        labels_path = _require(os.path.join(punct_dir, LABELS_FILE))
        model_path = _require(os.path.join(punct_dir, MODEL_FILE))
        with open(vocab_path, encoding="utf-8") as handle:
            vocab = handle.read().split("\n")
        self.vocab = {token: index for index, token in enumerate(vocab)}
        self.start_id = len(vocab)  # "$START" is appended after the BERT vocab
        self.unk = self.vocab["[UNK]"]
        with open(labels_path, encoding="utf-8") as handle:
            self.labels = handle.read().split()
        self.keep_bias, self.chunk, self.overlap = keep_bias, chunk, overlap
        self.sess = (session_factory or _read_session)(model_path, threads)

    def _wordpiece(self, word):
        if word in self.vocab:
            return [self.vocab[word]]
        ids, start = [], 0
        while start < len(word):
            end, current = len(word), None
            while start < end:
                piece = word[start:end] if start == 0 else "##" + word[start:end]
                if piece in self.vocab:
                    current = self.vocab[piece]
                    break
                end -= 1
            if current is None:
                return [self.unk]
            ids.append(current)
            start = end
        return ids

    def _predict(self, words):
        """-> one label per word."""
        ids, offsets = [self.start_id], [0]
        for word in words:
            offsets.append(len(ids))
            ids += self._wordpiece(word)
        ids = np.array([ids], dtype=np.int64)
        logits, _ = self.sess.run(None, {
            "input_ids": ids,
            "attention_mask": np.ones_like(ids),
            "token_type_ids": np.zeros_like(ids),
            "input_offsets": np.array([offsets], dtype=np.int64),
        })
        probabilities = np.exp(logits[0] - logits[0].max(-1, keepdims=True))
        probabilities /= probabilities.sum(-1, keepdims=True)
        probabilities[:, 0] += self.keep_bias
        return [self.labels[index] for index in probabilities.argmax(-1)[1:]]

    def labels_for(self, words):
        """Label every word; long input is cut into overlapping chunks and stitched on the middle half of the overlap."""
        count, out = len(words), [None] * len(words)
        stride = self.chunk - self.overlap
        start = 0
        while start < count:
            end = min(count, start + self.chunk)
            labels = self._predict(words[start:end])
            low = 0 if start == 0 else self.overlap // 2
            high = end - start if end == count else end - start - self.overlap // 2
            for index in range(low, high):
                out[start + index] = labels[index]
            if end == count:
                break
            start += stride
        return out


def cap_first(text):
    return text[:1].upper() + text[1:]


CASE = {
    "$TRANSFORM_CASE_CAPITAL": cap_first,
    "$TRANSFORM_CASE_UPPER": str.upper,
    "$TRANSFORM_CASE_UPPER_-1": lambda text: text[:-1].upper() + text[-1:],
    "$TRANSFORM_CASE_CAPITAL_1": lambda text: text[:1] + text[1:2].upper() + text[2:],
}


def punctuate(words, punctuator, iterations=ITERATIONS, pause=PAUSE_S, boundary_only=True):
    """GECToR-style iterations: punctuation from earlier passes is fed back as its own token.

    Only APPEND and the CASE transforms are applied; ``$APPEND_:`` becomes ",". A gap of at least ``pause`` seconds
    after a word forces a full stop (only after the last word of a VAD segment when ``boundary_only``).
    The final word always ends a sentence. Each output word gets ``eos``.
    """
    text = [word["text"] for word in words]
    punct = [""] * len(words)
    gaps = [max(0.0, words[i + 1]["start"] - words[i]["end"]) for i in range(len(words) - 1)] + [1.0]
    for _ in range(iterations):
        tokens, owner = [], []
        for index, token in enumerate(text):
            tokens.append(token)
            owner.append(index)
            if punct[index]:
                tokens.append(punct[index])
                owner.append(-1)
        changed = 0
        for label, index in zip(punctuator.labels_for(tokens), owner):
            if index < 0:
                continue
            if label.startswith("$APPEND_") and not punct[index]:
                punct[index] = "," if label == "$APPEND_:" else label[len("$APPEND_"):]
                changed += 1
            elif label in CASE and CASE[label](text[index]) != text[index]:
                text[index] = CASE[label](text[index])
                changed += 1
        if not changed:
            break
    for index in range(len(words) - 1):
        if (pause is not None and gaps[index] >= pause and punct[index] in ("", ",")
                and (not boundary_only or words[index].get("seg_last"))):
            punct[index] = "."
    if words and punct[-1] not in (".", "?"):
        punct[-1] = "."
    out, capitalise = [], True
    for word, token, mark in zip(words, text, punct):
        merged = dict(word)
        merged["text"] = (cap_first(token) if capitalise else token) + mark
        merged["eos"] = mark in (".", "?")
        out.append(merged)
        capitalise = mark in (".", "?")
    return out
