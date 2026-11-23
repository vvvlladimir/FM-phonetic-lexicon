"""Get eSpeak's own letter -> sound decisions via `espeak-ng -X` (rule trace).

For every word eSpeak prints which spelling rule it applied at each position, e.g.

    Translate 'philip'
      1   p        [p]
     22   ph       [f]
     46   _) ph (  [f]        <- highest score wins: "ph" -> f
    ...
    f'IlIp                    <- final phoneme string (eSpeak mnemonics)

Words taken from eSpeak's exception dictionary only print `Found: 'w' [phonemes]`
(no per-letter breakdown); those are aligned later by align.viterbi_align().
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field

RULE = re.compile(r"^\s*(\d+)\t(.+?)\s*\[([^\]]*)\]\s*$")
FOUND = re.compile(r"^Found: '(.+?)' \[([^\]]*)\]")
TRANSLATE = re.compile(r"^Translate '(.+?)'")
SUFFIX = re.compile(r"^\s+suffix \[([^\]]*)\]")
NON_FINAL_PREFIXES = ("Translate ", "Found:", "Unpronouncable?", "Flags:", "add e", "Replace", "Also")
STRIP = str.maketrans("", "", "',%=_|!")  # stress / pause marks, not phonemes


SWITCH = re.compile(r"\([a-z]{2,3}(-[a-z]+)?\)")  # language-switch flags like "(en)"


def clean_ph(ph: str) -> str:
    return SWITCH.sub("", ph).translate(STRIP)


@dataclass
class Trace:
    word: str                      # input word
    chunks: list[tuple[str, str]]  # (letters, rule phonemes), empty if not from rules
    final: str                     # final phoneme string (mnemonics, stress removed)
    dict_ph: str | None = None     # phonemes if taken from the exception dictionary
    notes: list[str] = field(default_factory=list)

    @property
    def rules_ok(self) -> bool:
        return bool(self.chunks) and "".join(g for g, _ in self.chunks) == self.word.lower()


def _rule_match(rule: str) -> str:
    """'_) ph (' -> 'ph';  'e (CC' -> 'e';  'y) ach' -> 'ach'."""
    if ")" in rule:
        rule = rule.split(")", 1)[1]
    if "(" in rule:
        rule = rule.split("(", 1)[0]
    return rule.strip()


def _parse_clause(word: str, lines: list[str], final: str) -> Trace:
    chunks: list[tuple[str, str]] = []
    block: list[tuple[int, str, str]] = []
    dict_ph = None
    notes = []
    active = False  # only rule lines after "Translate" count (skip the "Unpronouncable?" pass)

    def flush():
        if block:
            score, rule, ph = max(block, key=lambda b: b[0])  # first max wins on ties
            chunks.append((_rule_match(rule), clean_ph(ph)))
            block.clear()

    for line in lines:
        if not line.strip():
            if active:
                flush()
            continue
        if line.startswith("Unpronouncable?"):
            flush(); active = False; continue
        if TRANSLATE.match(line):
            # eSpeak may translate again (stem without suffix, or rest of a compound).
            # Keep going only while the letters covered so far are a proper prefix.
            flush()
            done = "".join(g for g, _ in chunks)
            active = done != word.lower()
            continue
        m = FOUND.match(line)
        if m:
            dict_ph = clean_ph(m.group(2)); continue
        m = SUFFIX.match(line)
        if m:
            flush()
            done = "".join(g for g, _ in chunks)
            rest = word.lower()[len(done):]
            if rest:
                chunks.append((rest, clean_ph(m.group(1))))
            notes.append("suffix")
            continue
        m = RULE.match(line)
        if m and active:
            block.append((int(m.group(1)), m.group(2), m.group(3)))
            continue
        if line.startswith("add e"):
            notes.append("add e")
    flush()
    if dict_ph is not None and not chunks:
        notes.append("dictionary")
    return Trace(word=word, chunks=chunks, final=clean_ph(final), dict_ph=dict_ph, notes=notes)


def _run(words: list[str], voice: str) -> list[Trace] | None:
    text = "".join(f"{w}.\n" for w in words)
    out = subprocess.run(["espeak-ng", "-v", voice, "-X", "-q"], input=text,
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace").stdout
    clauses: list[tuple[list[str], str]] = []
    cur: list[str] = []
    for line in out.split("\n"):
        is_final = (line and not line[0].isspace() and not RULE.match(line)
                    and not line.startswith(NON_FINAL_PREFIXES))
        if is_final:
            clauses.append((cur, line.strip()))
            cur = []
        else:
            cur.append(line)
    if len(clauses) != len(words):
        return None
    return [_parse_clause(w, ls, f) for w, (ls, f) in zip(words, clauses)]


def trace_words(words: list[str], voice: str, chunk: int = 2000) -> list[Trace]:
    """Batch-run eSpeak; if output can't be split 1:1 into words, retry on halves."""
    result: list[Trace] = []
    for i in range(0, len(words), chunk):
        result += _trace_safe(words[i:i + chunk], voice)
    return result


def _trace_safe(words: list[str], voice: str) -> list[Trace]:
    res = _run(words, voice)
    if res is not None:
        return res
    if len(words) == 1:
        return [Trace(word=words[0], chunks=[], final="", notes=["unparsed"])]
    mid = len(words) // 2
    return _trace_safe(words[:mid], voice) + _trace_safe(words[mid:], voice)
