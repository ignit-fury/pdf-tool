"""Map a paragraph draft back onto source runs, or decide to rebuild it."""
from __future__ import annotations

import base64
import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any, Mapping, Sequence

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


import base64
import hashlib
import json
from pathlib import Path
from typing import Any


def styled_runs(old_lines: Sequence[Sequence[Segment]], new_text: str,
                styles: Mapping[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-character owners survive the edit, so a rebuild keeps each word's style."""
    old = ''
    owners_old: list[str | None] = []
    for n, segments in enumerate(old_lines):
        if n:
            old += ' '
            owners_old.append(None)
        for run_id, text in segments:
            old += text
            owners_old.extend([run_id] * len(text))
    last = next((o for o in owners_old if o), None)
    filled: list[str | None] = []
    for owner in owners_old:  # gaps and line joins belong to the run on their left
        last = owner or last
        filled.append(last)
    probe = new_text.replace('\n', ' ')
    start = 0
    while start < min(len(old), len(probe)) and old[start] == probe[start]:
        start += 1
    end_old, end_new = len(old), len(probe)
    while end_old > start and end_new > start and old[end_old - 1] == probe[end_new - 1]:
        end_old -= 1
        end_new -= 1
    inserted = filled[start - 1] if start else (filled[0] if filled else None)
    owners = filled[:start] + [inserted] * (end_new - start) + filled[end_old:]
    out: list[dict[str, Any]] = []
    for ch, owner in zip(new_text, owners):
        style = dict(styles.get(owner, {})) if owner else {}
        if out and out[-1]['style'] == style:
            out[-1]['text'] += ch
        else:
            out.append({'text': ch, 'style': style})
    return out


def prepare_paragraph_edit(path: Path, source: bytes, payload: dict[str, Any], scratch: Path, *,
                           password: str = '') -> dict[str, object]:
    from engine.index import RunIndex
    from engine.paragraphs import page_paragraphs
    from engine.recipe import RecipeOp, RecipeTooLargeError, apply_recipe, parse_recipe
    from engine.source_text_box import prepare_source_text_box
    from engine.text_boxes import TextBoxError
    keys = {'operation', 'paragraph_id', 'source_run_ids', 'page_index', 'lines', 'style',
            'recipe', 'rect', 'allow_rebuild', 'run_styles'}
    lines, page = payload.get('lines'), payload.get('page_index')
    if (set(payload) != keys or payload['operation'] != 'replace-paragraph'
            or not isinstance(lines, list) or not all(isinstance(x, str) for x in lines)
            or type(page) is not int or not isinstance(payload['style'], dict)
            or type(payload['allow_rebuild']) is not bool or not isinstance(payload['recipe'], list)):
        raise TextBoxError('INVALID_TEXT_BOX')
    try:
        prior = parse_recipe(json.dumps(payload['recipe'], allow_nan=False).encode())
    except (ValueError, TypeError, RecipeTooLargeError):
        raise TextBoxError('INVALID_TEXT_BOX') from None
    with RunIndex(path, password=password) as index:
        try:
            page_data = index.page(page)
        except (IndexError, KeyError, ValueError):
            raise TextBoxError('INVALID_TEXT_BOX') from None
        paragraph = next((p for p in page_paragraphs(page, page_data)
                          if p.paragraph_id == payload['paragraph_id']), None)
    if paragraph is None or list(paragraph.run_ids) != payload['source_run_ids']:
        raise TextBoxError('PARAGRAPH_STALE')
    effective = {op.run_id: op.new_text for op in prior}
    style = payload['style'] or None
    if len(lines) == len(paragraph.lines):
        acc: dict[str, str] = {}
        changes: dict[str, str] | None = acc
        for line, line_text in zip(paragraph.lines, lines):
            ops = line_ops(line_segments(line, effective), line_text)
            if ops is None:  # e.g. a deleted gap space: only a rebuild can close it
                changes = None
                break
            acc.update(ops)
    else:
        changes = None
    if changes is not None:
        if style:
            for run_id in paragraph.run_ids:
                changes.setdefault(run_id, effective.get(run_id, next(
                    r.display_text for line in paragraph.lines for r in line if r.run_id == run_id)))
        new_ops = {run_id: RecipeOp(run_id, text, style) for run_id, text in changes.items()}  # type: ignore[arg-type]
        recipe = tuple(new_ops.pop(op.run_id, op) for op in prior) + tuple(new_ops.values())
        output = scratch / 'paragraph-lines.pdf'
        try:
            report = apply_recipe(path, recipe, output, password=password)
        except (ValueError, RecipeTooLargeError):
            report = None  # refused line plan: fall through to the rebuild consent path
        if report is not None and report.ok and output.exists():
            return {'ok': True, 'plan': 'lines', 'pdf': base64.b64encode(output.read_bytes()).decode(),
                    'recipe': [{'run_id': op.run_id, 'new_text': op.new_text, **({'style': op.style} if op.style else {})}
                               for op in recipe],
                    'source_hash': hashlib.sha256(source).hexdigest()}
    if not payload['allow_rebuild']:
        raise TextBoxError('PARAGRAPH_NEEDS_REBUILD')
    run_styles = payload['run_styles']
    if not isinstance(run_styles, dict) or set(run_styles) != set(paragraph.run_ids) \
            or not all(isinstance(v, dict) for v in run_styles.values()):
        raise TextBoxError('INVALID_TEXT_BOX')
    text = rebuild_text(len(paragraph.lines), lines)
    styles = {run_id: {**value, **payload['style']} for run_id, value in run_styles.items()}
    runs = styled_runs([line_segments(line, effective) for line in paragraph.lines], text, styles)
    if not runs:
        raise TextBoxError('TEXT_BOX_UNSUPPORTED_TEXT')  # an emptied paragraph has nothing to draw
    first_style = styles[paragraph.run_ids[0]]
    rebuild = {'operation': 'replace-source', 'paragraph_id': paragraph.paragraph_id,
               'source_run_ids': list(paragraph.run_ids), 'recipe': payload['recipe'],
               'page_index': page, 'text': text, 'runs': runs,
               'rect': payload['rect'], 'auto_expand': True,
               'style': {'font_family': 'Sans', **first_style}}
    result = prepare_source_text_box(path, source, rebuild, scratch / 'paragraph-base.pdf', password=password)
    return {**result, 'plan': 'rebuild'}
