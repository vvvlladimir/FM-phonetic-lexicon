"""Phonetic comparison helpers: similarity (PanPhon), Russian vowel reduction, sound IPA."""
from __future__ import annotations

import functools
import subprocess
import unicodedata
import warnings

IPA_VOWELS = set("aɐʌɑɒeɛəɜɘiɪɨoɔɵuʊʉyʏøœæɯɤ")
_MARKS = set("ˈˌːˑ ")


@functools.lru_cache(maxsize=1)
def _panphon():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # panphon emits SyntaxWarnings on import
        import panphon.distance
    return panphon.distance.Distance()


def similarity(a: str, b: str) -> float:
    """1 - PanPhon feature edit distance / max length (in segments). 1.0 = identical.

    Substituting /p/ by /b/ costs ~0.04, inserting or deleting a whole sound costs 1.
    """
    if a == b:
        return 1.0
    a2, b2 = a.replace(" ", ""), b.replace(" ", "")
    d = _panphon().feature_edit_distance_div_maxlen(a2, b2)
    return max(0.0, 1.0 - d)


def _similarity_pair(pair: tuple[str, str]) -> float:  # picklable for multiprocessing
    return similarity(*pair)


# --- Russian: unstressed vowels merge (akanye / ikanye) -------------------------
RU_VOWEL_LETTERS = "аеёиоуыэюя"
RU_REDUCTION = [set("оа"), set("еия")]  # spellings that sound alike when unstressed


def stressed_vowel_index(ipa_with_stress: str) -> int:
    """0-based index of the stressed vowel in eSpeak IPA with stress marks (ˈ)."""
    if "ˈ" not in ipa_with_stress:
        return 0
    before = ipa_with_stress.split("ˈ", 1)[0]
    return sum(1 for ch in before if ch in IPA_VOWELS)


def _consonants(ipa: str) -> str:
    return "".join(ch for ch in ipa if ch not in IPA_VOWELS and ch not in _MARKS)


def ru_equivalent(orig: str, variant: str, orig_ipa: str, var_ipa: str, stress_idx: int) -> bool:
    """Does `variant` sound like `orig` to a Russian listener?

    eSpeak guesses stress for unknown words and then reduces the wrong vowels, so
    we compare (a) consonants via eSpeak and (b) vowel letters ourselves: the
    stressed vowel must be identical, unstressed о/а and е/и/я may be swapped.
    """
    if _consonants(orig_ipa) != _consonants(var_ipa):
        return False
    vo = [c for c in orig.lower() if c in RU_VOWEL_LETTERS]
    vv = [c for c in variant.lower() if c in RU_VOWEL_LETTERS]
    if len(vo) != len(vv):
        return False
    for i, (x, y) in enumerate(zip(vo, vv)):
        if x == y:
            continue
        if i == stress_idx:
            return False
        if not any(x in grp and y in grp for grp in RU_REDUCTION):
            return False
    return True


# --- eSpeak mnemonic -> IPA (approximate, per sound) ------------------------------
def sound_to_ipa(sounds: list[str], voice: str) -> dict[str, str]:
    """Convert eSpeak phoneme mnemonics to IPA by asking eSpeak to speak `[[s]]`.

    The sound is spoken between two "a" vowels ([[aba]]) and the vowels are cut off
    again; spoken alone, German/Russian voiced consonants would be devoiced (b -> p).
    One call per sound (empty outputs would otherwise break batch alignment).
    Approximate; used for display and for finding similar sounds.
    """
    out = {}
    for s in sounds:
        r = subprocess.run(["espeak-ng", "-v", voice, "-q", "--ipa", f"[[a{s}a]]"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        x = r.stdout.strip().replace("ˈ", "").replace("ˌ", "")
        x = x[1:-1] if len(x) >= 2 else ""
        if x.startswith("ː"):  # length mark belonged to the leading vowel
            x = x[1:]
        out[s] = x
    return out


def _is_one_shorter(short: str, long: str) -> bool:
    """`short` is `long` with exactly one sound dropped (pf -> f, ts -> s, aɪ -> a)."""
    return len(long) == len(short) + 1 and any(long[:i] + long[i + 1:] == short for i in range(len(long)))


def sound_neighbours(sound_ipa: dict[str, str], max_dist: float = 0.3, k: int = 2,
                     freq: dict[str, int] | None = None) -> dict[str, list[str]]:
    """Similar sounds, from two buckets (see docs/decisions/0007):

    * substitution: same length, both vowels or both consonants, PanPhon distance
      <= max_dist (p~b 0.04, e~ɛ 0.08, m~n 0.13)
    * simplification: one sound dropped (pf -> f); PanPhon charges 1.0 for a deletion,
      so these would otherwise always lose against unrelated substitutions (pf -> kv).
    """
    d = _panphon()
    freq = freq or {}
    # several eSpeak mnemonics can have the same IPA (alignment fragments like ':f');
    # keep only the most frequent mnemonic per IPA as a neighbour candidate
    best: dict[str, str] = {}
    for s, i in sound_ipa.items():
        if i and (i not in best or freq.get(s, 0) > freq.get(best[i], 0)):
            best[i] = s
    items = [(s, i) for s, i in sound_ipa.items() if i]
    targets = [(s, i) for i, s in best.items()]
    res: dict[str, list[str]] = {}
    for s, i in items:
        subst, drop = [], []
        for s2, i2 in targets:
            if s2 == s or i2 == i:
                continue
            if len(i2) == len(i) and (i[0] in IPA_VOWELS) == (i2[0] in IPA_VOWELS):
                dist = d.feature_edit_distance(i, i2)
                if dist <= max_dist:
                    subst.append((dist, s2))
            elif _is_one_shorter(i2, i):
                drop.append((-freq.get(s2, 0), s2))
        res[s] = [s2 for _, s2 in sorted(subst)[:k]] + [s2 for _, s2 in sorted(drop)[:k]]
    return res


# --- diacritics ---------------------------------------------------------------------
EXTRA_ASCII = {"ı": "i", "İ": "I", "ł": "l", "Ł": "L", "ß": "ss", "ø": "o", "Ø": "O",
               "æ": "ae", "œ": "oe", "đ": "d"}


def strip_diacritics(ch: str) -> str:
    """'ş' -> 's', 'ü' -> 'u', 'ı' -> 'i', 'ł' -> 'l'. Non-Latin letters are kept (й stays й)."""
    if ch in EXTRA_ASCII:
        return EXTRA_ASCII[ch]
    if not unicodedata.name(ch, "").startswith("LATIN"):
        return ch
    base = "".join(c for c in unicodedata.normalize("NFD", ch) if not unicodedata.combining(c))
    return unicodedata.normalize("NFC", base) or ch
