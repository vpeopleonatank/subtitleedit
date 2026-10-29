"""Shared word post-processing for every caption-engine backend.

Input and output are the normalized transcript segments of the engine contract:

    [{"start": float, "end": float, "words": [{"text": str, "start": float, "end": float, "p": float, "eos": bool}]}]

Backends may hand over words whose ``start``/``end`` are ``None``. Premiere's transcript spec needs
a time on every word, so this module guarantees on its output:

* every word has non-empty, stripped text and a ``start``/``end`` pair;
* times are rounded to 3 decimals, never negative, never go backwards and never overlap,
  across segment borders too;
* every segment contains its words (segment bounds are widened when a word sticks out);
* segments without words are dropped;
* ``eos`` (the word ends a sentence; optional on input) is always a bool, ``False`` when missing. When a zh word is
  split into characters, ``eos`` goes on the last character only.
"""

import unicodedata

PRECISION = 3


def _is_missing(value):
    return value is None


def _is_cjk_punctuation_or_symbol(char):
    category = unicodedata.category(char)
    return category.startswith("P") or category.startswith("S") or category.startswith("Z")


def _split_zh_word(word):
    """Split one word into per-character units; punctuation sticks to the previous character."""
    text = word["text"]
    units = []
    leading = ""
    for char in text:
        if _is_cjk_punctuation_or_symbol(char):
            if units:
                units[-1] += char
            else:
                leading += char
        else:
            units.append(leading + char)
            leading = ""
    if leading:  # punctuation-only token
        units = [leading]
    if len(units) <= 1:
        return [word]

    start, end, p = word.get("start"), word.get("end"), word.get("p")
    count = len(units)
    pieces = []
    for index, unit in enumerate(units):
        piece = {"text": unit, "start": None, "end": None, "p": p, "eos": bool(word.get("eos")) and index == count - 1}
        if not _is_missing(start) and not _is_missing(end):
            span = end - start
            piece["start"] = start + span * index / count
            piece["end"] = start + span * (index + 1) / count
        else:
            if index == 0:
                piece["start"] = start
            if index == count - 1:
                piece["end"] = end
        pieces.append(piece)
    return pieces


def _attach_zh_punctuation(words):
    """Merge punctuation-only tokens into the previous word (or the next one at the start)."""
    merged = []
    pending = ""
    for word in words:
        text = word["text"]
        if all(_is_cjk_punctuation_or_symbol(char) for char in text):
            if merged:
                merged[-1]["text"] += text
                merged[-1]["eos"] = bool(merged[-1].get("eos")) or bool(word.get("eos"))
                if not _is_missing(word.get("end")):
                    merged[-1]["end"] = word["end"] if _is_missing(merged[-1].get("end")) else max(
                        merged[-1]["end"], word["end"]
                    )
            else:
                pending += text
            continue
        if pending:
            word = dict(word, text=pending + text)
            pending = ""
        merged.append(word)
    if pending and not merged:
        return []
    return merged


def _clean_words(words, zh):
    cleaned = []
    for word in words or []:
        text = (word.get("text") or "").strip()
        if not text:
            continue
        cleaned.append(
            {
                "text": text,
                "start": word.get("start"),
                "end": word.get("end"),
                "p": word.get("p"),
                "eos": bool(word.get("eos")),
            }
        )
    if not zh:
        return cleaned
    cleaned = _attach_zh_punctuation(cleaned)
    result = []
    for word in cleaned:
        result.extend(_split_zh_word(word))
    return result


def _fill_missing_times(words, seg_start, seg_end):
    """Give every word a start and end. Mutates ``words``."""
    count = len(words)
    if count == 0:
        return

    # Words with a single known time: borrow the neighbour's adjacent time.
    for index, word in enumerate(words):
        if _is_missing(word["end"]) and not _is_missing(word["start"]):
            if index + 1 < count and not _is_missing(words[index + 1]["start"]):
                word["end"] = max(word["start"], words[index + 1]["start"])
        if _is_missing(word["start"]) and not _is_missing(word["end"]):
            if index > 0 and not _is_missing(words[index - 1]["end"]):
                word["start"] = min(word["end"], words[index - 1]["end"])

    def complete(word):
        return not _is_missing(word["start"]) and not _is_missing(word["end"])

    index = 0
    while index < count:
        if complete(words[index]):
            index += 1
            continue
        run_start = index
        while index < count and not complete(words[index]):
            index += 1
        run_end = index  # exclusive

        lower = words[run_start - 1]["end"] if run_start > 0 else seg_start
        upper = words[run_end]["start"] if run_end < count else seg_end
        if _is_missing(upper) or upper < lower:
            upper = lower
        span = upper - lower
        length = run_end - run_start
        for offset in range(length):
            words[run_start + offset]["start"] = lower + span * offset / length
            words[run_start + offset]["end"] = lower + span * (offset + 1) / length


def normalize_segments(segments, language):
    """Return clean segments (see module docstring). ``language`` is ``"zh"`` for per-character splitting."""
    zh = language in ("zh", "zh-hans", "zh-hant")
    result = []
    previous_end = 0.0

    for segment in segments or []:
        words = _clean_words(segment.get("words"), zh)
        if not words:
            continue

        seg_start = segment.get("start")
        seg_end = segment.get("end")
        known_times = [w["start"] for w in words if not _is_missing(w["start"])] + [
            w["end"] for w in words if not _is_missing(w["end"])
        ]
        if _is_missing(seg_start):
            seg_start = min(known_times) if known_times else previous_end
        if _is_missing(seg_end):
            seg_end = max(known_times) if known_times else seg_start
        if seg_end < seg_start:
            seg_end = seg_start

        _fill_missing_times(words, seg_start, seg_end)

        out_words = []
        for word in words:
            start = round(max(word["start"], 0.0), PRECISION)
            end = round(max(word["end"], 0.0), PRECISION)
            start = max(start, previous_end)
            end = max(end, start)
            previous_end = end
            probability = word["p"]
            out_words.append(
                {
                    "text": word["text"],
                    "start": start,
                    "end": end,
                    "p": 1.0 if probability is None else float(probability),
                    "eos": word["eos"],
                }
            )

        result.append(
            {
                "start": round(max(min(max(seg_start, 0.0), out_words[0]["start"]), 0.0), PRECISION),
                "end": round(max(seg_end, out_words[-1]["end"]), PRECISION),
                "words": out_words,
            }
        )
    return result
