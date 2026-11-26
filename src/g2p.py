"""Letter-group <-> sound alignment and the "sound -> spellings" table.

A *sound* is a piece of eSpeak's final phoneme string (eSpeak mnemonics, stress
removed) aligned to a group of letters; see docs/decisions/0004 and 0005.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict

from .espeak_trace import Trace

VOWEL_CHARS = set("aeiouyAEIOUY@0369&VWQ")  # rough: eSpeak vowel mnemonics use these
MAX_GRAPHEME_LEN = 4                         # longer chunks are compound parts ('hand')


def _has_vowel(s: str) -> bool:
    return any(c in VOWEL_CHARS for c in s)


def _edit_cost(a: str, b: str, vowel_chunk: bool) -> float:
    """Edit distance on mnemonic characters; vowel<->vowel edits are cheap."""
    n, m = len(a), len(b)
    d = [[0.0] * (m + 1) for _ in range(n + 1)]

    def ins(c: str) -> float:
        return 1.0 if (vowel_chunk or c not in VOWEL_CHARS) else 1.5

    for i in range(1, n + 1):
        d[i][0] = d[i - 1][0] + 1.0
    for j in range(1, m + 1):
        d[0][j] = d[0][j - 1] + ins(b[j - 1])
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            x, y = a[i - 1], b[j - 1]
            sub = 0.0 if x == y else (1.0 if (x in VOWEL_CHARS) == (y in VOWEL_CHARS) else 2.0)
            d[i][j] = min(d[i - 1][j - 1] + sub, d[i - 1][j] + 1.0, d[i][j - 1] + ins(y))
    return d[n][m]


def align_to_final(chunks: list[tuple[str, str]], final: str) -> list[str] | None:
    """Split `final` into len(chunks) substrings that best match each rule's phonemes.

    eSpeak changes sounds after applying spelling rules (e.g. Russian unstressed
    o -> V), so the *final* sound of a letter group can differ from its rule output.
    """
    n, m = len(chunks), len(final)
    INF = float("inf")
    dp = [[INF] * (m + 1) for _ in range(n + 1)]
    back = [[0] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for i in range(1, n + 1):
        ph = chunks[i - 1][1]
        vowel_chunk = _has_vowel(ph)
        for j in range(m + 1):
            if dp[i - 1][j] == INF:
                continue
            for k in range(j, min(m, j + len(ph) + 3) + 1):
                c = dp[i - 1][j] + _edit_cost(ph, final[j:k], vowel_chunk)
                if c < dp[i][k]:
                    dp[i][k], back[i][k] = c, j
    if dp[n][m] == INF:
        return None
    out, k = [], m
    for i in range(n, 0, -1):
        j = back[i][k]
        out.append(final[j:k])
        k = j
    return out[::-1]


def position(i: int, n: int) -> str:
    """B = word start, E = word end, M = middle."""
    return "B" if i == 0 else ("E" if i == n - 1 else "M")


class Table:
    """by_sound[(sound, pos)][letters] counts; sound '' = silent letters."""

    def __init__(self):
        self.by_sound: dict[tuple[str, str], Counter] = defaultdict(Counter)
        self.by_graph: dict[str, Counter] = defaultdict(Counter)
        self.by_graph_pos: dict[tuple[str, str], Counter] = defaultdict(Counter)

    def add(self, pairs: list[tuple[str, str]]) -> None:
        n = len(pairs)
        for i, (g, s) in enumerate(pairs):
            if len(g) > MAX_GRAPHEME_LEN:
                continue
            pos = position(i, n)
            self.by_graph[g][s] += 1
            self.by_graph_pos[(g, pos)][s] += 1
            self.by_sound[(s, pos)][g] += 1

    @classmethod
    def from_rows(cls, rows) -> "Table":
        """Rebuild from stored `sound_spelling` rows (sound, position, letters, count)."""
        t = cls()
        for s, pos, g, k in rows:
            t.by_sound[(s, pos)][g] += k
            t.by_graph[g][s] += k
            t.by_graph_pos[(g, pos)][s] += k
        return t

    def alternatives(self, s: str, pos: str, min_count: int = 3, min_p: float = 0.01):
        c = self.by_sound.get((s, pos))
        if not c:
            return []
        total = sum(c.values())
        return [(g, k / total) for g, k in c.most_common() if k >= min_count and k / total >= min_p]

    def silent_letters(self, pos: str, min_ratio: float = 0.5, k: int = 3) -> list[tuple[str, float]]:
        """Letters that are *usually* silent at this position (French final -s/-t/-e).

        Filters alignment noise: German final 'n' is sometimes aligned to nothing,
        but it is pronounced in most words, so it is not offered as a silent letter.
        """
        out = []
        for g, p in self.alternatives("", pos):
            c = self.by_graph_pos.get((g, pos))
            if c and c[""] / sum(c.values()) >= min_ratio:
                out.append((g, p))
        return out[:k]

    def sound_counts(self) -> Counter:
        total = Counter()
        for (s, _), c in self.by_sound.items():
            total[s] += sum(c.values())
        return total

    def sounds(self, min_count: int = 1) -> set[str]:
        total = Counter()
        for (s, _), c in self.by_sound.items():
            if s:
                total[s] += sum(c.values())
        return {s for s, k in total.items() if k >= min_count}

    def rows(self):
        """(sound, position, letters, count, prob) for storage."""
        for (s, pos), c in self.by_sound.items():
            total = sum(c.values())
            for g, k in c.items():
                yield s, pos, g, k, k / total

    def viterbi_align(self, word: str, final: str, max_g: int = 4, max_s: int = 5):
        """Align letters to phonemes for words eSpeak took from its exception list."""
        w, F = word.lower(), final
        n, m = len(w), len(F)
        NEG = -float("inf")
        dp = [[NEG] * (m + 1) for _ in range(n + 1)]
        back: dict = {}
        dp[0][0] = 0.0
        for i in range(n):
            for j in range(m + 1):
                if dp[i][j] == NEG:
                    continue
                for gl in range(1, min(max_g, n - i) + 1):
                    g = w[i:i + gl]
                    cg = self.by_graph.get(g)
                    for sl in range(0, min(max_s, gl + 2, m - j) + 1):
                        s = F[j:j + sl]
                        if cg and cg[s]:
                            sc = math.log(cg[s] / sum(cg.values()))
                        else:
                            sc = -5.0 * gl - 2.0 * abs(gl - sl)  # unseen: allowed, expensive
                        v = dp[i][j] + sc
                        if v > dp[i + gl][j + sl]:
                            dp[i + gl][j + sl] = v
                            back[(i + gl, j + sl)] = (i, j)
        if dp[n][m] == NEG:
            return None
        out, ij = [], (n, m)
        while ij != (0, 0):
            pi, pj = back[ij]
            out.append((w[pi:ij[0]], F[pj:ij[1]]))
            ij = (pi, pj)
        return out[::-1]


def build_alignments(traces: list[Trace]) -> tuple[dict, Table, Counter]:
    """Return ({word: (method, [(letters, sound)])}, table, stats)."""
    stats = Counter()
    aligned: dict[str, tuple[str, list[tuple[str, str]]]] = {}
    pending = []
    for t in traces:
        if t.rules_ok:
            segs = align_to_final(t.chunks, t.final)
            if segs is not None:
                aligned[t.word] = ("rules", list(zip([g for g, _ in t.chunks], segs)))
                stats["rules"] += 1
                continue
        if t.final:
            pending.append(t)
        else:
            stats["failed"] += 1

    table = Table()
    for _, pairs in aligned.values():
        table.add(pairs)
    for t in pending:  # dictionary words: learn from the rule-based alignments
        al = table.viterbi_align(t.word, t.final)
        if al is None:
            stats["failed"] += 1
        else:
            aligned[t.word] = ("viterbi", al)
            stats["viterbi"] += 1
    return aligned, table, stats
