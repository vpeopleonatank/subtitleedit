"""Vietnamese inverse text normalisation: spoken numbers -> digits on timed words.

Words in:  [{"text", "start", "end", "p", "seg", "seg_last"}] (ASR output; any case, no punctuation).
Words out: same keys, lower-cased and NFC. A merged number keeps the first word's start and ``seg``, the last word's
end and ``seg_last``, and the lowest ``p``. Keys other than ``text`` are optional on input.

Ported from the bench prototype (scratch/sherpa-bench/postprocess.py).
"""

import unicodedata

UNITS = {"không": 0, "một": 1, "mốt": 1, "hai": 2, "ba": 3, "bốn": 4, "tư": 4, "năm": 5, "lăm": 5, "nhăm": 5,
         "sáu": 6, "bảy": 7, "bẩy": 7, "tám": 8, "chín": 9}
# After mười/mươi "năm" is excluded (Vietnamese says "lăm"), so "mười năm" stays "ten years"; "một" only after mười.
AFTER_TENS = {"mốt": 1, "hai": 2, "ba": 3, "bốn": 4, "tư": 4, "lăm": 5, "nhăm": 5, "sáu": 6, "bảy": 7, "bẩy": 7,
              "tám": 8, "chín": 9}
AFTER_MUOI = dict(AFTER_TENS, **{"một": 1})
COLLOQUIAL_ONES = {"mốt": 1, "tư": 4, "lăm": 5, "nhăm": 5}  # "chín trăm bốn lăm" = 945
SCALES = {"nghìn": 1000, "ngàn": 1000, "triệu": 10 ** 6, "tỷ": 10 ** 9, "tỉ": 10 ** 9}


def _below_100(w, i):
    """-> (value, next_i) or None."""
    if i < len(w) and w[i] == "mười":
        if i + 1 < len(w) and w[i + 1] in AFTER_MUOI:
            return 10 + AFTER_MUOI[w[i + 1]], i + 2
        return 10, i + 1
    if i < len(w) and w[i] in UNITS and w[i] != "không":
        u = UNITS[w[i]]
        if w[i] in ("mốt", "lăm", "nhăm", "tư"):
            return None  # never start a number with these forms
        if i + 1 < len(w) and w[i + 1] == "mươi" and u >= 2:
            if i + 2 < len(w) and w[i + 2] in AFTER_TENS:
                return u * 10 + AFTER_TENS[w[i + 2]], i + 3
            return u * 10, i + 2
        return u, i + 1
    return None


def _below_1000(w, i):
    if i + 1 < len(w) and w[i] in UNITS and w[i + 1] == "trăm" and w[i] not in COLLOQUIAL_ONES:
        v, j = UNITS[w[i]] * 100, i + 2
        if j + 1 < len(w) and w[j] in ("linh", "lẻ") and w[j + 1] in UNITS:
            return v + UNITS[w[j + 1]], j + 2
        if j + 1 < len(w) and w[j] in UNITS and w[j + 1] in COLLOQUIAL_ONES and w[j] not in COLLOQUIAL_ONES:
            return v + UNITS[w[j]] * 10 + COLLOQUIAL_ONES[w[j + 1]], j + 2
        if (j + 1 < len(w) and w[j] in UNITS and w[j] not in COLLOQUIAL_ONES and UNITS[w[j]] >= 1
                and w[j + 1] in AFTER_TENS):
            # colloquial tens without "mươi": "không trăm hai sáu" = 026, "chín trăm bốn lăm" = 945
            return v + UNITS[w[j]] * 10 + AFTER_TENS[w[j + 1]], j + 2
        r = _below_100(w, j)
        if r:
            return v + r[0], r[1]
        return v, j
    return _below_100(w, i)


def parse_number(w, i):
    """Parse the number starting at ``w[i]`` -> (value, next_i) or None."""
    total, j, last_scale = 0, i, None
    while True:
        g = _below_1000(w, j)
        if g is None:
            break
        val, k = g
        if k < len(w) and w[k] in SCALES and (last_scale is None or SCALES[w[k]] < last_scale):
            total += val * SCALES[w[k]]
            last_scale = SCALES[w[k]]
            j = k + 1
            if j + 1 < len(w) and w[j] in ("linh", "lẻ") and w[j + 1] in UNITS:
                total += UNITS[w[j + 1]]
                j += 2
                break
            continue
        total += val
        j = k
        break
    if j == i:
        return None
    return total, j


def fmt_number(v):
    if v < 10000:
        return str(v)
    return "{:,}".format(v).replace(",", ".")


def _carry(word, text, start, end, last, probabilities):
    merged = {"text": text, "start": start, "end": end, "seg_last": last}
    if "seg" in word:
        merged["seg"] = word["seg"]
    if probabilities:
        merged["p"] = min(probabilities)
    return merged


def itn(words):
    low = [unicodedata.normalize("NFC", x["text"]).lower() for x in words]
    out, i = [], 0
    while i < len(words):
        r = parse_number(low, i)
        if r and (r[1] - i >= 2 or r[0] >= 10) and not (r[1] < len(low) and low[r[1]] == "rưỡi"):
            v, j = r
            text = fmt_number(v)
            if j + 1 < len(low) and low[j] == "phần" and low[j + 1] == "trăm":
                text += "%"
                j += 2
            probabilities = [w["p"] for w in words[i:j] if w.get("p") is not None]
            out.append(_carry(words[i], text, words[i]["start"], words[j - 1]["end"],
                              words[j - 1].get("seg_last", False), probabilities))
            i = j
        else:
            probabilities = [words[i]["p"]] if words[i].get("p") is not None else []
            out.append(_carry(words[i], low[i], words[i]["start"], words[i]["end"],
                              words[i].get("seg_last", False), probabilities))
            i += 1
    return out
