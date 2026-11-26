"""Generate spelling variants of a word from its letter<->sound alignment.

Kinds of change (a variant can combine several):
  respell  : letters replaced by other letters for the same sound   (ph -> f)
  silent   : silent letters added / removed / swapped               (Philippe -> Philipe)
  near     : letters of a *similar* sound (PanPhon neighbour)       (pf -> f, d -> t)
  deaccent : diacritics dropped                                      (Şahin -> Sahin)

Score = sum of log P(letters | sound, position) over changed letter groups, plus a
fixed penalty per near-sound change; higher = more typical.  See docs/decisions/0006.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .g2p import Table, position
from .phonetic import strip_diacritics

NEAR_PENALTY = -2.0       # log-score penalty for using letters of a neighbouring sound
DEACCENT_LOGP = math.log(0.2)


@dataclass(frozen=True)
class Candidate:
    text: str
    score: float              # sum of log P over changed letter groups (+ near penalty)
    kinds: tuple[str, ...]
    n_changes: int = 1        # number of changed letter groups


def _apply_case(template: str, s: str) -> str:
    return s[:1].upper() + s[1:] if template[:1].isupper() else s


def _options(i: int, n: int, g: str, s: str, table: Table, neighbours: dict[str, list[str]],
             max_alts: int) -> list[tuple[str, float, str | None]]:
    """(letters, logp, kind) choices for one aligned letter group; kind None = unchanged."""
    pos = position(i, n)
    opts: list[tuple[str, float, str | None]] = [(g, 0.0, None)]
    if s:
        for g2, p in table.alternatives(s, pos)[:max_alts]:
            if g2 != g:
                opts.append((g2, math.log(p), "respell"))
        for s2 in neighbours.get(s, []):
            for g2, p in table.alternatives(s2, pos)[:2]:
                if g2 != g:
                    opts.append((g2, math.log(p) + NEAR_PENALTY, "near"))
    else:  # silent letters: drop them or use other silent letters
        opts.append(("", math.log(0.3), "silent"))
        for g2, p in table.silent_letters(pos):
            if g2 != g:
                opts.append((g2, math.log(p), "silent"))
    return opts


def generate(word: str, pairs: list[tuple[str, str]], table: Table,
             neighbours: dict[str, list[str]] | None = None, k: int = 40,
             max_changes: int = 3, beam: int = 300, max_alts: int = 6) -> list[Candidate]:
    neighbours = neighbours or {}
    n = len(pairs)
    # state: (prefix, score, n_changes, kinds, used_near)
    states = [("", 0.0, 0, (), False)]
    for i, (g, s) in enumerate(pairs):
        opts = _options(i, n, g, s, table, neighbours, max_alts)
        nxt = []
        for pref, sc, ch, kinds, near in states:
            for g2, lp, kind in opts:
                if kind is None:
                    nxt.append((pref + g2, sc, ch, kinds, near))
                elif ch < max_changes and not (kind == "near" and near):  # max 1 near change
                    nxt.append((pref + g2, sc + lp, ch + 1,
                                kinds + ((kind,) if kind not in kinds else ()), near or kind == "near"))
        nxt.sort(key=lambda x: -x[1])
        states = nxt[:beam]
    # silent letter appended at the end (French -s/-t/-e etc.)
    if pairs and pairs[-1][1]:
        extra = []
        for g2, p in table.silent_letters("E"):
            for pref, sc, ch, kinds, near in states[:50]:
                if ch < max_changes:
                    extra.append((pref + g2, sc + math.log(p) + math.log(0.3), ch + 1,
                                  kinds + (("silent",) if "silent" not in kinds else ()), near))
        states += extra

    seen = {word.lower()}
    out: list[Candidate] = []
    for text, sc, ch, kinds, _ in sorted(states, key=lambda x: -x[1]):
        if ch and text and text not in seen:
            seen.add(text)
            out.append(Candidate(_apply_case(word, text), sc, kinds, ch))
        if len(out) >= k:
            break
    out += deaccent_variants(word)
    # final dedupe on the exact output string (casing rules like Turkish İ/i can
    # make two different lower-case forms produce the same text)
    unique: dict[str, Candidate] = {}
    for c in out:
        if c.text != word and (c.text not in unique or c.score > unique[c.text].score):
            unique[c.text] = c
    return list(unique.values())


def deaccent_variants(word: str) -> list[Candidate]:
    """All diacritics dropped, plus each diacritic letter dropped on its own."""
    plain = "".join(strip_diacritics(c) for c in word)
    if plain == word:
        return []
    out = {plain: DEACCENT_LOGP}
    idx = [i for i, c in enumerate(word) if strip_diacritics(c) != c]
    if len(idx) > 1:
        for i in idx:
            v = word[:i] + strip_diacritics(word[i]) + word[i + 1:]
            out.setdefault(v, DEACCENT_LOGP)
    return [Candidate(v, sc, ("deaccent",)) for v, sc in out.items()]


UNSEEN_LOGP = -8.0  # letters never observed for this sound (or a sound dropped)
OTHER_POSITION_FACTOR = 0.5  # letters seen for this sound, but only at other positions


def _any_position(table: Table, s: str) -> dict[str, float]:
    """P(letters | sound) pooled over B/M/E (e.g. English 'pp' exists, but never word-final)."""
    from collections import Counter
    c = Counter()
    for pos in ("B", "M", "E"):
        c.update(table.by_sound.get((s, pos), Counter()))
    total = sum(c.values())
    return {g: k / total for g, k in c.items()} if total else {}


def explain_variant(variant: str, pairs: list[tuple[str, str]], table: Table,
                    neighbours: dict[str, list[str]] | None = None) -> tuple[float, int]:
    """Best (logp, n_changes) explaining `variant` as a respelling of an aligned word.

    Works for any string, e.g. an STT output: each aligned letter group of the
    original is matched to 0-4 letters of the variant (DP over both strings).
    Same letters cost 0; letters of the same sound cost log P(letters | sound, pos);
    letters of a neighbouring sound cost log P + NEAR_PENALTY; anything else UNSEEN_LOGP.
    """
    neighbours = neighbours or {}
    v = variant.lower()
    n, m = len(pairs), len(v)
    NEG = (-float("inf"), 0)
    dp = [[NEG] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = (0.0, 0)

    def better(a, b):  # higher logp, then fewer changes
        return a if (a[0], -a[1]) > (b[0], -b[1]) else b

    silent_any = _any_position(table, "")  # extra silent letters, e.g. 2nd p of "pp"
    for i in range(n + 1):
        if i < n:
            g, s = pairs[i]
            pos = position(i, n)
            alts = dict(table.alternatives(s, pos, min_count=1, min_p=0.0)) if s else \
                dict(table.silent_letters(pos))
            pooled = _any_position(table, s) if s else {}
            near_alts = {}
            for s2 in neighbours.get(s, []):
                for g2, p in table.alternatives(s2, pos, min_count=1, min_p=0.0):
                    near_alts.setdefault(g2, math.log(p) + NEAR_PENALTY)
        for j in range(m + 1):
            if dp[i][j] == NEG:
                continue
            lp0, ch0 = dp[i][j]
            # insert 1-2 extra silent letters without consuming a sound (Philip -> Philipp)
            for L in (1, 2):
                g2 = v[j:j + L]
                if len(g2) == L and g2 in silent_any:
                    cand = (lp0 + math.log(silent_any[g2] * OTHER_POSITION_FACTOR), ch0 + 1)
                    dp[i][j + L] = better(dp[i][j + L], cand)
            if i == n:
                continue
            for L in range(0, min(4, m - j) + 1):
                g2 = v[j:j + L]
                if g2 == g:
                    cand = (lp0, ch0)
                elif not s and g2 == "":
                    cand = (lp0 + math.log(0.3), ch0 + 1)          # silent letters dropped
                elif g2 in alts:
                    cand = (lp0 + math.log(alts[g2]), ch0 + 1)
                elif g2 in pooled:
                    cand = (lp0 + math.log(pooled[g2] * OTHER_POSITION_FACTOR), ch0 + 1)
                elif g2 in near_alts:
                    cand = (lp0 + near_alts[g2], ch0 + 1)
                else:
                    cand = (lp0 + UNSEEN_LOGP, ch0 + 1)
                dp[i + 1][j + L] = better(dp[i + 1][j + L], cand)
    lp, ch = dp[n][m]
    if lp == -float("inf"):
        return UNSEEN_LOGP * max(1, abs(m - sum(len(g) for g, _ in pairs))), 1
    return lp, ch
