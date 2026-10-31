"""Map a paragraph draft back onto source runs, or decide to rebuild it."""
from __future__ import annotations

import unicodedata
from typing import Mapping, Sequence

from engine.records import RunRecord

Segment = tuple[str | None, str]


def line_segments(runs: Sequence[RunRecord], effective: Mapping[str, str]) -> list[Segment]:
    """Runs with the same synthetic gap spaces the paragraph text shows."""
    out: list[Segment] = []
    for run in runs:
        text = effective.get(run.run_id, run.display_text)
        if out and not out[-1][1].endswith(' ') and not text.startswith(' '):
            out.append((None, ' '))
        out.append((run.run_id, text))
    return out


def line_ops(segments: Sequence[Segment], new_text: str) -> list[tuple[str, str]] | None:
    """Per-run text changes for one line. `None` means the edit needs a paragraph rebuild:
    the line has no runs, or the edit deletes only synthetic gap spaces."""
    if not any(run_id for run_id, _ in segments):
        return None
    old = ''.join(text for _, text in segments)
    if old == new_text:
        return []
    start = 0
    while start < min(len(old), len(new_text)) and old[start] == new_text[start]:
        start += 1
    while 0 < start < len(old) and unicodedata.combining(old[start]):
        start -= 1  # never split a letter from its combining marks
    end_old, end_new = len(old), len(new_text)
    while end_old > start and end_new > start and old[end_old - 1] == new_text[end_new - 1]:
        end_old -= 1
        end_new -= 1
    runs: list[tuple[str, int, int]] = []
    pos = 0
    for run_id, text in segments:
        if run_id:
            runs.append((run_id, pos, pos + len(text)))
        pos += len(text)
    touched = [r for r in runs if r[1] < end_old and r[2] > start]
    if not touched:
        if end_old > start:  # deletes only gap spaces: no run can absorb it
            return None
        # shortcut: emptied runs keep their space, rebuild when users report holes.
        # Pure insertion, or a change inside a gap: the run at or before it.
        touched = [next((r for r in reversed(runs) if r[1] <= start), runs[0])]
    first, last = touched[0], touched[-1]
    head = old[first[1]:start] if start > first[1] else ''
    tail = old[end_old:last[2]] if end_old < last[2] else ''
    return [(first[0], head + new_text[start:end_new] + tail)] + [(r[0], '') for r in touched[1:]]


def rebuild_text(old_line_count: int, new_lines: Sequence[str]) -> str:
    return (' ' if len(new_lines) == old_line_count else '\n').join(new_lines)
