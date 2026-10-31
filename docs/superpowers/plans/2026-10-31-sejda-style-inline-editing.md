# Sejda-style Inline Paragraph Editing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Click a paragraph, type in place, and click away to commit, with no Preview/Apply step. Edits keep per-line original styles when they fit and rebuild the paragraph as a wrapped native text box when they do not.

**Architecture:** The server groups each page's runs into paragraphs, reusing `engine/blocks.py`, and returns them with the page runs. A new `replace-paragraph` operation on the existing `/jobs/{id}/text-box` endpoint tries per-line recipe edits first. If any line refuses, it falls back to N-run source removal plus native text-box insertion, which generalises `engine/source_text_box.py`. The client draws hover outlines, opens a contenteditable paragraph editor at the click point, and commits on blur through the existing text-box controller and history.

**Tech Stack:** Python 3.13, pikepdf, playa-pdf (through `RunIndex`), pytest, FastAPI worker; React 19, pdfjs-dist, `node --test`.

**Spec:** `docs/superpowers/specs/2026-10-31-sejda-style-inline-editing-design.md`

## Deviations from the spec (deliberate, smaller)

1. **Endpoint.** `replace-paragraph` goes through `POST /jobs/{id}/text-box`, not `/edit`. Only that endpoint can return a rebuilt native box, and `replace-source` already lives there.
2. **Line mapping.** The editor keeps one DOM line per original PDF line. The new text arrives as `lines: list[str]`.
   - Same line count: each line is mapped onto its runs with a prefix/suffix diff (`line_ops`).
   - Different line count (the user pressed Enter or deleted a break): the paragraph is rebuilt.
   - The text is never redistributed across lines. That would be reflow, which the project rules forbid without a rebuild.
3. **Mixed-style warning.** The toolbar warns as soon as the draft would need a rebuild (line count changed). For other overflow, the refusal message offers **Rebuild as text box**, which is the explicit consent.

## Global Constraints

- Content-stream editing only. No white-box overlays. No silent clipping.
- No new dependencies (Python or npm). No AGPL anywhere.
- Every commit is atomic: the current PDF bytes and history stay unchanged on any refusal or failure.
- One successful commit equals exactly one Undo/Redo entry.
- Run IDs address the original immutable bytes. The paragraph ID is `"p_" + sha256("\0".join(run_ids)).hexdigest()[:16]`.
- Existing worker isolation, 20 s CPU limit, stream limits, collision checks and signature acknowledgement stay unchanged.
- Bundled fonts only: `Sans`, `Serif`, `Mono` (Liberation).
- Every UI action keeps its `Server` location label (per-operation disclosure).
- Python commands run from the repo root with `uv run`. Client tests run from `client/` with `npm test`.
- Commit messages: conventional (`feat:`, `test:`, `docs:`), ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## File map

| File | Responsibility |
|---|---|
| Create `engine/paragraphs.py` | `Paragraph` dataclass + `page_paragraphs()` built from `blocks._page` |
| Create `engine/paragraph_edit.py` | Pure `line_ops`, `rebuild_text`; orchestrator `prepare_paragraph_edit` |
| Modify `engine/source_text_box.py` | Accept `source_run_ids` of any length when they form one validated paragraph |
| Modify `server/worker.py` | `paragraphs` in page response; `replace-paragraph` dispatch |
| Modify `server/errors.py` | `PARAGRAPH_STALE`, `PARAGRAPH_UNSAFE` codes |
| Create `client/src/viewer/paragraphs.mjs` | Pure: effective lines, payload, hit test |
| Create `client/src/viewer/ParagraphEditor.jsx` | Contenteditable paragraph overlay + hover outlines |
| Modify `client/src/viewer/InlineEditor.jsx` | Compact `TextToolbar` |
| Modify `client/src/textBoxes/controller.mjs` | Treat `replace-paragraph` like `replace-source` for source bytes |
| Modify `client/src/App.jsx` | Paragraph selection, `commitParagraph()` on blur |
| Tests | `tests/test_paragraphs.py`, `tests/test_paragraph_edit.py`, `tests/test_worker.py` (add), `client/src/viewer/paragraphs.test.mjs` |

---

### Task 1: Paragraph grouping per page

**Files:**
- Create: `engine/paragraphs.py`
- Test: `tests/test_paragraphs.py`

**Interfaces:**
- Consumes: `engine.blocks._page(index: int, page: PageIndex) -> PageBlocks`; `Block.kind`, `Block.spans`; `Span.text`, `Span.source_runs`. A paragraph block joins lines with a `Span('\n')` that has no source runs.
- Produces:
  ```python
  @dataclass(frozen=True, slots=True)
  class Paragraph:
      paragraph_id: str
      lines: tuple[tuple[RunRecord, ...], ...]   # reading order, runs left→right
      kind: Literal['paragraph', 'heading', 'list']
      @property
      def run_ids(self) -> tuple[str, ...]: ...
  def paragraph_id(run_ids: Sequence[str]) -> str
  def page_paragraphs(page_index: int, page: PageIndex) -> tuple[Paragraph, ...]
  ```
  Table blocks are excluded: table cells stay single-run edits.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_paragraphs.py
from pathlib import Path

from engine.index import RunIndex
from engine.paragraphs import page_paragraphs, paragraph_id
from tools.build_export_fixtures import build_export_fixture


def line_texts(paragraph):
    return [''.join(r.display_text for r in line) for line in paragraph.lines]


def test_multiline_paragraph_keeps_lines_and_stable_id(tmp_path: Path) -> None:
    path = tmp_path / 'layout.pdf'
    build_export_fixture(path)
    with RunIndex(path) as index:
        paragraphs = page_paragraphs(0, index.page(0))
    left = next(p for p in paragraphs if line_texts(p) == ['Left first', 'Left second'])
    assert left.kind == 'paragraph'
    assert left.paragraph_id == paragraph_id(left.run_ids)
    assert left.paragraph_id.startswith('p_') and len(left.paragraph_id) == 18
    assert [line_texts(p) for p in paragraphs if p.kind == 'heading'] == [['Export heading']]


def test_tables_are_not_paragraphs(tmp_path: Path) -> None:
    path = tmp_path / 'layout.pdf'
    build_export_fixture(path)
    with RunIndex(path) as index:
        assert page_paragraphs(1, index.page(1)) == ()


def test_paragraph_id_depends_on_order() -> None:
    assert paragraph_id(['a', 'b']) != paragraph_id(['b', 'a'])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_paragraphs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.paragraphs'`

- [ ] **Step 3: Write minimal implementation**

```python
# engine/paragraphs.py
"""Editable paragraphs: the export block model, kept line by line."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal, Sequence

from engine.blocks import _page
from engine.index import PageIndex
from engine.records import RunRecord


def paragraph_id(run_ids: Sequence[str]) -> str:
    return 'p_' + hashlib.sha256('\0'.join(run_ids).encode()).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class Paragraph:
    paragraph_id: str
    lines: tuple[tuple[RunRecord, ...], ...]
    kind: Literal['paragraph', 'heading', 'list']

    @property
    def run_ids(self) -> tuple[str, ...]:
        return tuple(run.run_id for line in self.lines for run in line)


def page_paragraphs(page_index: int, page: PageIndex) -> tuple[Paragraph, ...]:
    out: list[Paragraph] = []
    for block in _page(page_index, page).blocks:
        if block.kind == 'table':
            continue
        lines: list[list[RunRecord]] = [[]]
        for span in block.spans:
            if span.text == '\n' and not span.source_runs:
                lines.append([])
            else:
                lines[-1].extend(span.source_runs)
        kept = tuple(tuple(line) for line in lines if line)
        ids = [run.run_id for line in kept for run in line]
        out.append(Paragraph(paragraph_id(ids), kept, block.kind))
    return tuple(out)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_paragraphs.py tests/test_blocks.py -v`
Expected: PASS (blocks tests unchanged)

- [ ] **Step 5: Commit**

```bash
git add engine/paragraphs.py tests/test_paragraphs.py
git commit -m "feat: group page runs into editable paragraphs"
```

---

### Task 2: Pure paragraph edit mapping

**Files:**
- Create: `engine/paragraph_edit.py`
- Test: `tests/test_paragraph_edit.py`

**Interfaces:**
- Produces:
  ```python
  Segment = tuple[str | None, str]   # (run_id, effective text); None = synthetic gap space
  def line_segments(runs: Sequence[RunRecord], effective: Mapping[str, str]) -> list[Segment]
  def line_ops(segments: Sequence[Segment], new_text: str) -> list[tuple[str, str]] | None
  def rebuild_text(old_line_count: int, new_lines: Sequence[str]) -> str
  ```
  - `line_ops` returns `(run_id, new_text)` pairs only for the runs it touched. It returns `[]` when nothing changed, and `None` when the line has no runs.
  - The changed span `[start, end)` comes from the common prefix and suffix. All runs overlapping it are touched. The first touched run takes `prefix_of_that_run + inserted + suffix_of_last_touched_run`, and the other touched runs become `''`.
  - A change that lies only inside a synthetic gap is attached to the run on its left. If there is none, it goes to the run on its right.
  - `rebuild_text`: if the line count is unchanged, the lines are joined with `' '`, because the soft wraps get re-wrapped. Otherwise they are joined with `'\n'`, because the user's breaks are explicit.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_paragraph_edit.py
import pytest

from engine.paragraph_edit import line_ops, rebuild_text

SEGS = [('r1', 'Hello'), (None, ' '), ('r2', 'bold'), (None, ' '), ('r3', 'world')]


@pytest.mark.parametrize('new,expected', [
    ('Hello bold world', []),
    ('Hallo bold world', [('r1', 'Hallo')]),
    ('Hello BOLD world', [('r2', 'BOLD')]),
    ('Hello bold world!', [('r3', 'world!')]),
    ('Hello there world', [('r2', 'there')]),
    ('Hi world', [('r1', 'Hi'), ('r2', '')]),          # r3 untouched keeps its style
    ('Hello  bold world', [('r2', ' bold')]),
    ('', [('r1', ''), ('r2', ''), ('r3', '')]),
])
def test_line_ops_touch_only_changed_runs(new, expected):
    assert line_ops(SEGS, new) == expected


def test_line_ops_without_runs_is_none():
    assert line_ops([(None, ' ')], 'x') is None


def test_line_ops_keeps_graphemes_whole():
    assert line_ops([('r1', 'café')], 'cafés') == [('r1', 'cafés')]


def test_rebuild_text_joins_soft_wraps_with_spaces_and_keeps_new_breaks():
    assert rebuild_text(2, ['Left first longer', 'Left second']) == 'Left first longer Left second'
    assert rebuild_text(2, ['Left', 'first', 'Left second']) == 'Left\nfirst\nLeft second'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_paragraph_edit.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.paragraph_edit'`

- [ ] **Step 3: Write minimal implementation**

```python
# engine/paragraph_edit.py
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
    if not touched:  # pure insertion, or a change inside a gap: the run at or before it
        touched = [next((r for r in reversed(runs) if r[1] <= start), runs[0])]
    first, last = touched[0], touched[-1]
    head = old[first[1]:start] if start > first[1] else ''
    tail = old[end_old:last[2]] if end_old < last[2] else ''
    return [(first[0], head + new_text[start:end_new] + tail)] + [(r[0], '') for r in touched[1:]]


def rebuild_text(old_line_count: int, new_lines: Sequence[str]) -> str:
    return (' ' if len(new_lines) == old_line_count else '\n').join(new_lines)
```

> This function was prototyped against every case in Step 1 before the plan was written; all pass.
> Known shortcut: deleting a whole middle run leaves its horizontal gap (neighbours never move in the line plan).
> `# shortcut: emptied runs keep their space, rebuild when users report holes.`

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_paragraph_edit.py -v`
Expected: PASS (11 cases)

- [ ] **Step 5: Commit**

```bash
git add engine/paragraph_edit.py tests/test_paragraph_edit.py
git commit -m "feat: map paragraph drafts onto source runs"
```

---

### Task 3: N-run source rebuild for a validated paragraph

**Files:**
- Modify: `engine/source_text_box.py:49-62` (`prepare_source_text_box` run-id validation)
- Test: `tests/test_source_text_box.py` (append)

**Interfaces:**
- Consumes: `engine.paragraphs.page_paragraphs`, `paragraph_id`.
- Produces: `prepare_source_text_box(path, source, payload, intermediate, *, password='')` now also accepts `payload['paragraph_id']` with `payload['source_run_ids']` of length ≥ 1.
  - It checks that the IDs equal exactly the `run_ids` of the paragraph with that ID on `page_index`, and raises `TextBoxError('PARAGRAPH_STALE')` if they don't.
  - It refuses with `TextBoxError('TEXT_BOX_SOURCE_UNSAFE')` if any run is `not_editable`, or if the runs span more than one `(part, xobj_path)`.
  - The existing 2-run initial-pair path (no `paragraph_id`) is unchanged.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_source_text_box.py
def paragraph_pdf(path: Path):
    with pikepdf.Pdf.new() as pdf:
        page=pdf.add_blank_page(page_size=(400,400))
        page.obj.Resources=pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=pdf.make_indirect(
            pikepdf.Dictionary(Type=pikepdf.Name.Font,Subtype=pikepdf.Name.Type1,BaseFont=pikepdf.Name.Helvetica))))
        page.obj.Contents=pdf.make_stream(b'BT /F1 12 Tf 1 0 0 1 30 340 Td (First line here) Tj ET\n'
            b'BT /F1 12 Tf 1 0 0 1 30 326 Td (Second line here) Tj ET\n'
            b'BT /F1 12 Tf 1 0 0 1 30 100 Td (Keep neighbor) Tj ET')
        pdf.save(path)
    from engine.index import RunIndex
    from engine.paragraphs import page_paragraphs
    with RunIndex(path) as index:
        paragraph=next(p for p in page_paragraphs(0,index.page(0)) if len(p.lines)==2)
    return path.read_bytes(),paragraph


def test_paragraph_rebuild_removes_every_line(tmp_path):
    from engine.source_text_box import prepare_source_text_box
    path=tmp_path/'p.pdf';source,paragraph=paragraph_pdf(path)
    payload={'operation':'replace-source','paragraph_id':paragraph.paragraph_id,
        'source_run_ids':list(paragraph.run_ids),'recipe':[],'page_index':0,
        'text':'First line here and much more text Second line here',
        'rect':{'left':30,'top':48,'width':200,'height':28},
        'style':{'font_family':'Sans','font_size':12},'auto_expand':True}
    result=prepare_source_text_box(path,source,payload,tmp_path/'base.pdf')
    text=extract(base64.b64decode(result['pdf']))
    assert 'much more text' in text and 'Keep neighbor' in text
    assert text.count('First line here')==1
    assert path.read_bytes()==source


def test_paragraph_rebuild_refuses_stale_ids(tmp_path):
    from engine.source_text_box import prepare_source_text_box
    from engine.text_boxes import TextBoxError
    path=tmp_path/'p.pdf';source,paragraph=paragraph_pdf(path)
    payload={'operation':'replace-source','paragraph_id':paragraph.paragraph_id,
        'source_run_ids':list(paragraph.run_ids)[:1],'recipe':[],'page_index':0,'text':'x',
        'rect':{'left':30,'top':48,'width':200,'height':28},'style':{'font_family':'Sans'}}
    with pytest.raises(TextBoxError,match='PARAGRAPH_STALE'):
        prepare_source_text_box(path,source,payload,tmp_path/'base.pdf')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_source_text_box.py -k paragraph -v`
Expected: FAIL with `INVALID_TEXT_BOX` (the `paragraph_id` key isn't allowed yet)

- [ ] **Step 3: Write minimal implementation**

In `engine/source_text_box.py`, add `'paragraph_id'` to `allowed` and validate before the existing `group` branch:

```python
def _validated_paragraph(path: Path, password: str, page: object,
                         identifier: object, identifiers: list[str]) -> None:
    from engine.index import RunIndex
    from engine.paragraphs import page_paragraphs
    from engine.run_id import decode_run_id
    if type(page) is not int or not isinstance(identifier, str) or not identifiers:
        raise TextBoxError('INVALID_TEXT_BOX')
    with RunIndex(path, password=password) as index:
        indexed = index.page(page)
        match = next((p for p in page_paragraphs(page, indexed) if p.paragraph_id == identifier), None)
        if match is None or list(match.run_ids) != identifiers:
            raise TextBoxError('PARAGRAPH_STALE')
        states = {run.run_id: verdict.state for run, verdict in indexed.runs}
    streams = {(a['part'], a['xobj_path']) for a in map(decode_run_id, identifiers)}
    if any(states.get(i) == 'not_editable' for i in identifiers) or len(streams) != 1:
        raise TextBoxError('TEXT_BOX_SOURCE_UNSAFE')
```

and replace the `group` handling:

```python
    group=payload.get('source_run_ids')
    if 'paragraph_id' in payload:
        if not isinstance(group,list) or not all(isinstance(item,str) for item in group):
            raise TextBoxError('INVALID_TEXT_BOX')
        identifiers=group
        _validated_paragraph(path,password,payload.get('page_index'),payload['paragraph_id'],identifiers)
    elif group is not None:
        ...existing two-run branch unchanged...
```

Also exclude `'paragraph_id'` from `insertion` (the comprehension on the `insertion=` line).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_source_text_box.py -v`
Expected: PASS (old and new tests)

- [ ] **Step 5: Commit**

```bash
git add engine/source_text_box.py tests/test_source_text_box.py
git commit -m "feat: rebuild a validated multi-line paragraph as a native text box"
```

---

### Task 4: `prepare_paragraph_edit` orchestrator (lines first, rebuild second)

**Files:**
- Modify: `engine/paragraph_edit.py` (append)
- Test: `tests/test_paragraph_edit.py` (append)

**Interfaces:**
- Consumes: `line_segments`, `line_ops`, `rebuild_text` (Task 2); `page_paragraphs` (Task 1); `prepare_source_text_box` with `paragraph_id` (Task 3); `engine.recipe.parse_recipe`, `apply_recipe`, `RecipeOp`.
- Produces:
  ```python
  def prepare_paragraph_edit(path: Path, source: bytes, payload: dict, scratch: Path, *,
                             password: str = '') -> dict[str, object]
  ```
  - Payload keys, exactly: `operation='replace-paragraph'`, `paragraph_id`, `source_run_ids`, `page_index`, `lines: list[str]`, `style: dict`, `recipe: list`, `rect`, `allow_rebuild: bool`.
  - Returns the line plan as `{'ok': True, 'plan': 'lines', 'pdf': b64, 'recipe': [ops...], 'source_hash': hex}`.
  - Returns the rebuild plan as the `prepare_source_text_box` result plus `'plan': 'rebuild'`.
  - If the line plan refuses and `allow_rebuild` is false, it raises `TextBoxError('PARAGRAPH_NEEDS_REBUILD')`. The client then shows the refusal with **Rebuild as text box**.
  - The paragraph check is the same one Task 3 uses, giving `PARAGRAPH_STALE`.
  - The style for the rebuild is the payload `style` merged over the first run's family. The line plan applies a recipe `style` to every touched run, and to every run when `style` is non-empty.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_paragraph_edit.py
import base64
from pathlib import Path

import pikepdf
import pypdfium2 as pdfium


def two_line_pdf(path: Path):
    with pikepdf.Pdf.new() as pdf:
        page = pdf.add_blank_page(page_size=(400, 400))
        page.obj.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=pdf.make_indirect(
            pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica))))
        page.obj.Contents = pdf.make_stream(b'BT /F1 12 Tf 30 340 Td (First line here) Tj ET\n'
                                            b'BT /F1 12 Tf 30 326 Td (Second line here) Tj ET')
        pdf.save(path)
    from engine.index import RunIndex
    from engine.paragraphs import page_paragraphs
    with RunIndex(path) as index:
        return path.read_bytes(), next(p for p in page_paragraphs(0, index.page(0)) if len(p.lines) == 2)


def text_of(b64: str) -> str:
    with pdfium.PdfDocument(base64.b64decode(b64)) as pdf:
        page = pdf[0].get_textpage()
        try:
            return page.get_text_range()
        finally:
            page.close()


def payload(paragraph, lines, **extra):
    return {'operation': 'replace-paragraph', 'paragraph_id': paragraph.paragraph_id,
            'source_run_ids': list(paragraph.run_ids), 'page_index': 0, 'lines': lines,
            'style': {}, 'recipe': [], 'allow_rebuild': False,
            'rect': {'left': 30, 'top': 48, 'width': 200, 'height': 28}, **extra}


def test_small_edit_uses_line_plan(tmp_path):
    from engine.paragraph_edit import prepare_paragraph_edit
    path = tmp_path / 's.pdf'; source, p = two_line_pdf(path)
    result = prepare_paragraph_edit(path, source, payload(p, ['First line here', 'Second line hers']), tmp_path)
    assert result['plan'] == 'lines'
    assert result['recipe'] == [{'run_id': p.lines[1][0].run_id, 'new_text': 'Second line hers'}]
    assert 'Second line hers' in text_of(result['pdf'])
    assert path.read_bytes() == source


def test_overflow_needs_consent_then_rebuilds(tmp_path):
    from engine.paragraph_edit import prepare_paragraph_edit
    from engine.text_boxes import TextBoxError
    path = tmp_path / 's.pdf'; source, p = two_line_pdf(path)
    long = ['First line here with a great deal of extra words added', 'Second line here']
    with pytest.raises(TextBoxError, match='PARAGRAPH_NEEDS_REBUILD'):
        prepare_paragraph_edit(path, source, payload(p, long), tmp_path)
    result = prepare_paragraph_edit(path, source, payload(p, long, allow_rebuild=True), tmp_path)
    assert result['plan'] == 'rebuild' and 'great deal' in text_of(result['pdf'])


def test_added_line_rebuilds_with_explicit_break(tmp_path):
    from engine.paragraph_edit import prepare_paragraph_edit
    path = tmp_path / 's.pdf'; source, p = two_line_pdf(path)
    result = prepare_paragraph_edit(path, source, payload(p, ['First', 'line here', 'Second line here'], allow_rebuild=True), tmp_path)
    assert result['plan'] == 'rebuild'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_paragraph_edit.py -k "plan or rebuild" -v`
Expected: FAIL with `ImportError: cannot import name 'prepare_paragraph_edit'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to engine/paragraph_edit.py
import base64
import hashlib
import json
from pathlib import Path
from typing import Any


def prepare_paragraph_edit(path: Path, source: bytes, payload: dict[str, Any], scratch: Path, *,
                           password: str = '') -> dict[str, object]:
    from engine.index import RunIndex
    from engine.paragraphs import page_paragraphs
    from engine.recipe import RecipeOp, RecipeTooLargeError, apply_recipe, parse_recipe
    from engine.source_text_box import prepare_source_text_box
    from engine.text_boxes import TextBoxError
    keys = {'operation', 'paragraph_id', 'source_run_ids', 'page_index', 'lines', 'style',
            'recipe', 'rect', 'allow_rebuild'}
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
        paragraph = next((p for p in page_paragraphs(page, index.page(page))
                          if p.paragraph_id == payload['paragraph_id']), None)
    if paragraph is None or list(paragraph.run_ids) != payload['source_run_ids']:
        raise TextBoxError('PARAGRAPH_STALE')
    effective = {op.run_id: op.new_text for op in prior}
    style = payload['style'] or None
    if len(lines) == len(paragraph.lines):
        changes: dict[str, str] = {}
        for runs, text in zip(paragraph.lines, lines):
            ops = line_ops(line_segments(runs, effective), text)
            if ops is None:
                raise TextBoxError('TEXT_BOX_SOURCE_UNSAFE')
            changes.update(ops)
        if style:
            for run_id in paragraph.run_ids:
                changes.setdefault(run_id, effective.get(run_id, next(
                    r.display_text for line in paragraph.lines for r in line if r.run_id == run_id)))
        new_ops = {run_id: RecipeOp(run_id, text, style) for run_id, text in changes.items()}  # type: ignore[arg-type]
        recipe = tuple(new_ops.pop(op.run_id, op) for op in prior) + tuple(new_ops.values())
        output = scratch / 'paragraph-lines.pdf'
        report = apply_recipe(path, recipe, output, password=password)
        if report.ok and output.exists():
            return {'ok': True, 'plan': 'lines', 'pdf': base64.b64encode(output.read_bytes()).decode(),
                    'recipe': [{'run_id': op.run_id, 'new_text': op.new_text, **({'style': op.style} if op.style else {})}
                               for op in recipe],
                    'source_hash': hashlib.sha256(source).hexdigest()}
    if not payload['allow_rebuild']:
        raise TextBoxError('PARAGRAPH_NEEDS_REBUILD')
    first = paragraph.lines[0][0]
    rebuild = {'operation': 'replace-source', 'paragraph_id': paragraph.paragraph_id,
               'source_run_ids': list(paragraph.run_ids), 'recipe': payload['recipe'],
               'page_index': page, 'text': rebuild_text(len(paragraph.lines), lines),
               'rect': payload['rect'], 'auto_expand': True,
               'style': {'font_family': 'Sans', 'font_size': first.effective_em or 12,
                         'bold': bool(first.bold), 'italic': bool(first.italic), **payload['style']}}
    result = prepare_source_text_box(path, source, rebuild, scratch / 'paragraph-base.pdf', password=password)
    return {**result, 'plan': 'rebuild'}
```

> Implementer note: `apply_recipe` raises for some invalid inputs rather than returning `ok=False`. Wrap the call in `try/except ValueError` and treat it as a refusal of the line plan. Check what `prepare_source_text_box` expects for `style.font_family` (it requires `Sans|Serif|Mono`). If the first run has `suggested_font_family` in the page data, the client sends it in `style`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_paragraph_edit.py tests/test_source_text_box.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add engine/paragraph_edit.py tests/test_paragraph_edit.py
git commit -m "feat: commit paragraph edits per line or rebuild with consent"
```

---

### Task 5: Worker and API wiring

**Files:**
- Modify: `server/worker.py` (page action ~line 286-327; `_text_box_payload` line 210; text-box action ~line 337)
- Modify: `server/errors.py:16-19`
- Test: `tests/test_text_box_api.py` (append), `tests/test_worker.py` (append)

**Interfaces:**
- Produces, page response: `"paragraphs": [{"paragraph_id": str, "kind": str, "lines": [[run_id, ...], ...], "box": [x0,y0,x1,y1], "single_style": bool, "state": "editable"|"not_editable", "reason": str|None}]`.
  - `box` is the union of member run `box` values. It's already computed in the same loop, in the same coordinate space as `runs[].box`.
  - `single_style` is true when all member runs share `font_identity`, `bold`, `italic` and `color` (from `formatting`).
  - `state` is `not_editable` when any member run's `state` is `not_editable` (with the first such run's `reason`), or when any run has `ownership` set.
- Produces, text-box action: `replace-paragraph` dispatches to `prepare_paragraph_edit(path, source, payload, Path(scratch), password=...)`. The existing signature-acknowledgement and notices handling applies unchanged.
- Error codes: add `'PARAGRAPH_STALE', 'PARAGRAPH_NEEDS_REBUILD'` to `TEXT_BOX_ERROR_CODES`.

- [ ] **Step 1: Write the failing tests**

Follow the existing client/fixture pattern at the top of `tests/test_text_box_api.py` (reuse its `client` fixture and upload helper).

```python
# append to tests/test_text_box_api.py
def test_page_runs_include_paragraphs_and_paragraph_commit(client, tmp_path):
    from tests.test_paragraph_edit import two_line_pdf
    source, paragraph = two_line_pdf(tmp_path / 'p.pdf')
    job = upload(client, source)            # existing helper in this file
    page = client.get(f'/api/jobs/{job}/pages/0/runs').json()
    entry = next(p for p in page['paragraphs'] if p['paragraph_id'] == paragraph.paragraph_id)
    assert entry['lines'] == [[r.run_id for r in line] for line in paragraph.lines]
    assert entry['state'] == 'editable' and entry['single_style'] is True
    body = {'operation': 'replace-paragraph', 'paragraph_id': paragraph.paragraph_id,
            'source_run_ids': list(paragraph.run_ids), 'page_index': 0,
            'lines': ['First line here', 'Second line hers'], 'style': {}, 'recipe': [],
            'allow_rebuild': False, 'rect': {'left': 30, 'top': 48, 'width': 200, 'height': 28}}
    result = client.post(f'/api/jobs/{job}/text-box', json=body).json()
    assert result['plan'] == 'lines' and result['location'] == 'server'
    stale = client.post(f'/api/jobs/{job}/text-box', json={**body, 'source_run_ids': body['source_run_ids'][:1]})
    assert stale.status_code == 422 and stale.json()['detail']['code'] == 'PARAGRAPH_STALE'
```

If the file names its helpers differently, adapt them to the names it already defines. Don't add new fixtures.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_text_box_api.py -k paragraph -v`
Expected: FAIL with `KeyError: 'paragraphs'`

- [ ] **Step 3: Write minimal implementation**

In `server/worker.py`, inside the `page` action after the `runs` loop and still inside `with RunIndex(...)`:

```python
                from engine.paragraphs import page_paragraphs
                by_id = {row['run_id']: row for row in runs}
                paragraphs = []
                for paragraph in page_paragraphs(number, indexed):
                    rows = [by_id[i] for i in paragraph.run_ids if i in by_id]
                    if len(rows) != len(paragraph.run_ids):
                        continue
                    blocked = next((r for r in rows if r['state'] == 'not_editable'), None)
                    style_keys = ('font_identity', 'bold', 'italic', 'color', 'source_font')
                    paragraphs.append({'paragraph_id': paragraph.paragraph_id, 'kind': paragraph.kind,
                        'lines': [[r.run_id for r in line] for line in paragraph.lines],
                        'box': [min(r['box'][0] for r in rows), min(r['box'][1] for r in rows),
                                max(r['box'][2] for r in rows), max(r['box'][3] for r in rows)],
                        'single_style': len({tuple(str(r.get(k)) for k in style_keys) for r in rows}) == 1,
                        'state': 'not_editable' if blocked else 'editable',
                        'reason': blocked['reason'] if blocked else None})
```

Add `"paragraphs": paragraphs` to the returned page dict. Check that `run_box` returns `[x0, y0, x1, y1]` in that order by reading `engine/boxes.py`. If it uses another order, take the union in that order.

In `_text_box_payload`, add `'replace-paragraph'` to the allowed operations tuple. In the text-box action:

```python
                if payload['operation']=='replace-paragraph':
                    from engine.paragraph_edit import prepare_paragraph_edit
                    result=prepare_paragraph_edit(path,source,payload,Path(scratch),
                                                  password=secret.get_secret_value())
                elif payload['operation']=='replace-source':
```

In `server/errors.py`, add both codes to `TEXT_BOX_ERROR_CODES`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_text_box_api.py tests/test_worker.py tests/test_source_text_box.py tests/test_paragraph_edit.py tests/test_paragraphs.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/worker.py server/errors.py tests/test_text_box_api.py
git commit -m "feat: expose page paragraphs and replace-paragraph over the text-box API"
```

---

### Task 6: Client pure paragraph model

**Files:**
- Create: `client/src/viewer/paragraphs.mjs`
- Test: `client/src/viewer/paragraphs.test.mjs`

**Interfaces:**
- Consumes: the page data `{runs:[{run_id,text,box,suggested_font_family,...}], paragraphs:[...]}` (Task 5); recipe ops `{run_id,new_text,style?}`.
- Produces:
  ```js
  export function effectiveLines(paragraph, runsById, recipe) // -> string[] (gap spaces as in engine.line_segments)
  export function paragraphAt(paragraphs, point)            // point {x,y} in PDF box space -> paragraph|null
  export function paragraphPayload({paragraph, lines, style, recipe, rect, allowRebuild, runsById}) // -> body for POST /text-box
  export function draftChanged(paragraph, lines, runsById, recipe) // -> boolean
  ```
  - `paragraphPayload` sets `style.font_family` from `style.font_family || first run suggested_font_family || 'Sans'`, but only when the server will need it. It always sends `style`; empty means "no style change".

- [ ] **Step 1: Write the failing test**

```js
// client/src/viewer/paragraphs.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import {effectiveLines,paragraphAt,paragraphPayload,draftChanged} from './paragraphs.mjs';

const runs=new Map([['a',{run_id:'a',text:'Hello'}],['b',{run_id:'b',text:'bold'}],['c',{run_id:'c',text:'Next line'}]]);
const paragraph={paragraph_id:'p_1',lines:[['a','b'],['c']],box:[10,10,100,40],state:'editable'};

test('effective lines join runs with gap spaces and apply recipe overrides',()=>{
  assert.deepEqual(effectiveLines(paragraph,runs,[]),['Hello bold','Next line']);
  assert.deepEqual(effectiveLines(paragraph,runs,[{run_id:'b',new_text:'BOLD'}]),['Hello BOLD','Next line']);
});

test('paragraphAt hit-tests the box',()=>{
  assert.equal(paragraphAt([paragraph],{x:50,y:20}),paragraph);
  assert.equal(paragraphAt([paragraph],{x:150,y:20}),null);
});

test('payload carries ids, lines and consent flag',()=>{
  const body=paragraphPayload({paragraph,lines:['Hi bold','Next line'],style:{},recipe:[],rect:{left:1,top:2,width:3,height:4},allowRebuild:false,runsById:runs});
  assert.equal(body.operation,'replace-paragraph');
  assert.deepEqual(body.source_run_ids,['a','b','c']);
  assert.equal(body.allow_rebuild,false);
  assert.deepEqual(body.lines,['Hi bold','Next line']);
});

test('draftChanged ignores unchanged drafts',()=>{
  assert.equal(draftChanged(paragraph,['Hello bold','Next line'],runs,[]),false);
  assert.equal(draftChanged(paragraph,['Hello bold!','Next line'],runs,[]),true);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (in `client/`): `node --test src/viewer/paragraphs.test.mjs`
Expected: FAIL with `Cannot find module './paragraphs.mjs'`

- [ ] **Step 3: Write minimal implementation**

```js
// client/src/viewer/paragraphs.mjs
/** Paragraph drafts: one string per original PDF line, matching engine.paragraph_edit. */
export function effectiveLines(paragraph,runsById,recipe){
  const overrides=new Map(recipe.map(op=>[op.run_id,op.new_text]));
  return paragraph.lines.map(ids=>ids.reduce((line,id)=>{
    const text=overrides.get(id)??runsById.get(id)?.text??'';
    return line&&!line.endsWith(' ')&&!text.startsWith(' ')?`${line} ${text}`:line+text;
  },''));
}
export function paragraphAt(paragraphs,{x,y}){
  return paragraphs.find(p=>x>=p.box[0]&&x<=p.box[2]&&y>=p.box[1]&&y<=p.box[3])||null;
}
export function draftChanged(paragraph,lines,runsById,recipe){
  const before=effectiveLines(paragraph,runsById,recipe);
  return before.length!==lines.length||before.some((line,i)=>line!==lines[i]);
}
export function paragraphPayload({paragraph,lines,style,recipe,rect,allowRebuild,runsById}){
  const first=runsById.get(paragraph.lines[0][0]);
  const family=style.font_family||first?.suggested_font_family;
  return {operation:'replace-paragraph',paragraph_id:paragraph.paragraph_id,source_run_ids:paragraph.lines.flat(),
    page_index:paragraph.page_index,lines:[...lines],style:{...style,...(allowRebuild&&family?{font_family:family}:{})},
    recipe:structuredClone(recipe),rect:{...rect},allow_rebuild:!!allowRebuild};
}
```

Then add `page_index` to the payload test's `paragraph` object (`page_index:0`) and assert `body.page_index===0`. The App sets `page_index` on each paragraph when it stores the page data.

- [ ] **Step 4: Run tests to verify they pass**

Run (in `client/`): `npm test`
Expected: PASS (all existing tests and the 4 new ones)

- [ ] **Step 5: Commit**

```bash
git add client/src/viewer/paragraphs.mjs client/src/viewer/paragraphs.test.mjs
git commit -m "feat: client paragraph draft model"
```

---

### Task 7: Paragraph editor, hover outlines and compact toolbar

**Files:**
- Create: `client/src/viewer/ParagraphEditor.jsx`
- Modify: `client/src/viewer/InlineEditor.jsx` (`TextToolbar`)
- Modify: `client/src/viewer/compactChrome.css` (append styles)

**Interfaces:**
- Consumes: `viewportBox(box, viewport)` from `../session.mjs`; `sourceTypography(run, style, scale)` and `viewportFontScale(viewport)` from `./model.mjs`; `effectiveLines` (Task 6).
- Produces:
  ```jsx
  export function ParagraphOutlines({paragraphs, viewport, activeId, onChoose})
  // renders a <button className="paragraph-outline" data-state=...> per paragraph; onChoose(paragraph, clickEvent)
  export default function ParagraphEditor({paragraph, lines, runsById, style, viewport, caret, busy, status, onLines, onCommit, onCancel})
  // contenteditable root with one <div data-line> per line; caret = {line, offset}
  // status: null | 'saving' | {refused: string, canRebuild: boolean}
  ```
  `TextToolbar` new props: `({run, style, busy, status, mixedStyle, needsRebuild, onStyle, onDelete, onRevert, onRebuild})`.
  - It renders one row: font select, size −/input/+, Bold, Italic, colour, Delete paragraph, and a `ToolbarDetails` "⋯" holding character spacing.
  - When `needsRebuild && mixedStyle` it renders a one-line warning: `Wrapping will make this paragraph one style.`
  - When `status.refused` it renders the reason plus **Revert** and **Rebuild as text box** (the latter only if `status.canRebuild`), and the `Server` location label.
  - The Preview fit / Apply edit / Expand buttons and long guidance paragraphs are removed.

- [ ] **Step 1: Write `ParagraphOutlines` and `ParagraphEditor`**

```jsx
// client/src/viewer/ParagraphEditor.jsx
import React,{useLayoutEffect,useRef} from 'react';
import {viewportBox} from '../session.mjs';
import {sourceTypography,viewportFontScale} from './model.mjs';
import {explainReason} from '../session.mjs';

export function ParagraphOutlines({paragraphs,viewport,activeId,onChoose}){
  return paragraphs.filter(p=>p.paragraph_id!==activeId).map(p=>{
    const box=viewportBox(p.box,viewport);
    return <button key={p.paragraph_id} type="button" className="paragraph-outline" data-state={p.state}
      style={{position:'absolute',...box}} title={p.state==='not_editable'?explainReason(p.reason):'Edit paragraph'}
      aria-label={p.state==='not_editable'?`Not editable: ${explainReason(p.reason)}`:'Edit paragraph'}
      disabled={p.state==='not_editable'} onClick={event=>onChoose(p,event)}/>;
  });
}

export default function ParagraphEditor({paragraph,lines,runsById,style,viewport,caret,busy,status,onLines,onCommit,onCancel}){
  const root=useRef(null);
  const first=runsById.get(paragraph.lines[0][0]);
  const typography=sourceTypography(first,style,viewportFontScale(viewport));
  useLayoutEffect(()=>{
    const node=root.current;if(!node)return;
    node.focus({preventScroll:true});
    const target=node.children[caret?.line??0]?.firstChild;
    if(target){const range=document.createRange();range.setStart(target,Math.min(caret?.offset??target.length,target.length));range.collapse(true);const sel=getSelection();sel.removeAllRanges();sel.addRange(range);}
  },[paragraph.paragraph_id]);
  const read=()=>[...root.current.children].map(div=>div.textContent.replace(/ /g,' '));
  return <div ref={root} className="paragraph-editor" data-status={status==='saving'?'saving':status?.refused?'refused':'editing'}
    contentEditable={!busy} suppressContentEditableWarning role="textbox" aria-multiline="true" aria-label="Edit paragraph on page" spellCheck={false}
    style={{position:'absolute',...viewportBox(paragraph.box,viewport),...typography}}
    onInput={()=>onLines(read())}
    onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();onCancel();}if(event.key==='Tab'){event.preventDefault();onCommit();}}}
    onBlur={event=>{if(!event.currentTarget.contains(event.relatedTarget)&&!event.relatedTarget?.closest?.('.floating-text-tools'))onCommit();}}>
    {lines.map((line,i)=><div key={i} data-line={i} style={{position:'absolute',left:viewportBox(lineBox(paragraph,i,runsById),viewport).left-viewportBox(paragraph.box,viewport).left,top:viewportBox(lineBox(paragraph,i,runsById),viewport).top-viewportBox(paragraph.box,viewport).top,whiteSpace:'pre'}}>{line}</div>)}
  </div>;
}

function lineBox(paragraph,index,runsById){
  const ids=paragraph.lines[index]||paragraph.lines.at(-1),boxes=ids.map(id=>runsById.get(id).box);
  return [Math.min(...boxes.map(b=>b[0])),Math.min(...boxes.map(b=>b[1])),Math.max(...boxes.map(b=>b[2])),Math.max(...boxes.map(b=>b[3]))];
}
```

> Implementer note: an Enter keypress in a contenteditable whose children are `data-line` divs creates a new div, which is what we want, since it becomes the line-count change. New divs have no `data-line` index of their own, so position them below the last line (`top` of the last line + line height). Compute `viewportBox(lineBox(...))` once per line, not three times.

- [ ] **Step 2: Shrink `TextToolbar` in `InlineEditor.jsx`**

Replace the body of `TextToolbar` (keep `InlineInput` untouched for text-box drafts) with:

```jsx
export default function TextToolbar({run,style,busy,status,mixedStyle,needsRebuild,onStyle,onDelete,onRevert,onRebuild}) {
  if(!run)return null;
  const size=style.font_size??run.font_size??12;
  return <section className="context-toolbar compact" aria-label="Text formatting">
    <fieldset disabled={!!busy}>
      <select aria-label="Font" value={style.font_family||''} onChange={event=>{const next={...style};if(event.target.value)next.font_family=event.target.value;else delete next.font_family;onStyle(next);}}><option value="">{run.source_font||'Source font'}</option><option value="Sans">Liberation Sans</option><option value="Serif">Liberation Serif</option><option value="Mono">Liberation Mono</option></select>
      <button aria-label="Decrease font size" onClick={()=>onStyle({...style,font_size:Math.max(1,Number(size)-1)})}>−</button>
      <input aria-label="Font size" type="number" min="1" max="512" step="0.5" value={size} onChange={event=>onStyle({...style,font_size:Number(event.target.value)})}/>
      <button aria-label="Increase font size" onClick={()=>onStyle({...style,font_size:Math.min(512,Number(size)+1)})}>+</button>
      <button aria-pressed={style.bold??!!run.bold} aria-label="Bold" onClick={()=>onStyle({...style,bold:!(style.bold??run.bold)})}><strong>B</strong></button>
      <button aria-pressed={style.italic??!!run.italic} aria-label="Italic" onClick={()=>onStyle({...style,italic:!(style.italic??run.italic)})}><em>I</em></button>
      <input type="color" aria-label="Text color" value={colorHex(style.color??run.color)} onChange={event=>onStyle({...style,color:event.target.value.slice(1).match(/../g).map(v=>parseInt(v,16)/255)})}/>
      <button aria-label="Delete paragraph" onClick={onDelete}>Delete</button>
      <ToolbarDetails label="⋯" closeKey={run.run_id}><label>Character spacing<input type="number" aria-label="Character spacing" min="0" max="10" step="0.1" value={style.character_spacing??run.character_spacing??0} onChange={event=>onStyle({...style,character_spacing:Number(event.target.value)})}/></label></ToolbarDetails>
      <span className="action-location">Server</span>
    </fieldset>
    {needsRebuild&&mixedStyle&&<p className="context-warning" role="status">Wrapping will make this paragraph one style.</p>}
    {status==='saving'&&<p role="status">Saving…</p>}
    {status?.refused&&<p className="context-warning" role="alert">{status.refused} <button onClick={onRevert}>Revert</button>{status.canRebuild&&<button onClick={onRebuild}>Rebuild as text box</button>}</p>}
  </section>;
}
```

Remove the now-unused imports (`draftProblem`, `needsFontChoice`, `inlineBox` if `InlineInput` no longer needs it). Keep anything `InlineInput` still uses.

- [ ] **Step 3: Styles**

```css
/* append to client/src/viewer/compactChrome.css */
.paragraph-outline{background:transparent;border:1px dashed transparent;border-radius:2px;cursor:text;padding:0}
.paragraph-outline:hover,.paragraph-outline:focus-visible{border-color:var(--accent,#2f6fed)}
.paragraph-outline[data-state="not_editable"]{cursor:not-allowed}
.paragraph-outline[data-state="not_editable"]:hover{border-color:#999}
.paragraph-editor{outline:1px solid var(--accent,#2f6fed);background:rgba(255,255,255,.96);color:inherit;white-space:pre;overflow:visible}
.paragraph-editor[data-status="saving"]{animation:paragraph-pulse 1s ease-in-out infinite}
.paragraph-editor[data-status="refused"]{outline-color:#c62828}
@keyframes paragraph-pulse{50%{outline-color:transparent}}
@media (prefers-reduced-motion:reduce){.paragraph-editor[data-status="saving"]{animation:none;outline-style:dotted}}
.context-toolbar.compact fieldset{display:flex;gap:4px;align-items:center;border:0;margin:0;padding:0}
```

> The editor's white background covers the source glyphs only while the draft is open, so the user isn't reading two copies at once. It is never written into the PDF. That's the same pattern as today's `inline-text-input`.

- [ ] **Step 4: Build check**

Run (in `client/`): `npm run build && npm test`
Expected: build succeeds; tests PASS. The App doesn't use the new props yet, which is fine because Task 8 wires them.

- [ ] **Step 5: Commit**

```bash
git add client/src/viewer/ParagraphEditor.jsx client/src/viewer/InlineEditor.jsx client/src/viewer/compactChrome.css
git commit -m "feat: paragraph editor overlay, hover outlines and compact toolbar"
```

---

### Task 8: App wiring, commit on blur

**Files:**
- Modify: `client/src/App.jsx` (`choose` ~line 234, `checkFit`/`apply` ~465-500, `renderOverlay` ~line 611, `applyTextBox` ~line 360)
- Modify: `client/src/textBoxes/controller.mjs:48`

**Interfaces:**
- Consumes: Tasks 5–7.
- Produces, App state: `paragraphSelection = {paragraph, lines, caret, style, status, allowRebuild}`.
  - `commitParagraph(allowRebuild=false)` returns nothing.
  - On success it publishes new bytes as one history entry.
  - For the `lines` plan it updates `recipeState.recipe` to `result.recipe` and keeps the source (same as `apply`).
  - For the `rebuild` plan it follows `applyTextBox`'s publish, then calls `analyze()` so the next click is editable without the "Analyze text" gate.

- [ ] **Step 1: Controller source bytes**

In `client/src/textBoxes/controller.mjs` line 48 change the condition to:

```js
      const sourceBytes=['replace-source','replace-paragraph'].includes(payload.operation)?capture.session.sourceBytes:capture.bytes;
```

Run (in `client/`): `npm test`. Expected: PASS.

- [ ] **Step 2: Selection on click**

In `renderOverlay`, in `mode==='edit'`, render:

```jsx
{mode==='edit'&&index[number]?.paragraphs&&<ParagraphOutlines paragraphs={index[number].paragraphs.map(p=>({...p,page_index:number-1}))} viewport={viewport} activeId={paragraphSelection?.paragraph.paragraph_id} onChoose={(p,event)=>chooseParagraph(p,number,event)}/>}
{paragraphSelection?.paragraph.page_index===number-1&&<>
  <FloatingTextTools box={viewportBox(paragraphSelection.paragraph.box,viewport)}><TextToolbar run={runsFor(number).get(paragraphSelection.paragraph.lines[0][0])} style={paragraphSelection.style} busy={busy} status={paragraphSelection.status} mixedStyle={!paragraphSelection.paragraph.single_style} needsRebuild={paragraphSelection.lines.length!==paragraphSelection.paragraph.lines.length} onStyle={style=>setParagraphSelection(s=>({...s,style,status:null}))} onDelete={()=>setParagraphSelection(s=>({...s,lines:s.lines.map(()=>''),status:null}))} onRevert={cancelParagraph} onRebuild={()=>commitParagraph(true)}/></FloatingTextTools>
  <ParagraphEditor paragraph={paragraphSelection.paragraph} lines={paragraphSelection.lines} runsById={runsFor(number)} style={paragraphSelection.style} viewport={viewport} caret={paragraphSelection.caret} busy={!!busy} status={paragraphSelection.status} onLines={lines=>setParagraphSelection(s=>({...s,lines,status:null}))} onCommit={()=>commitParagraph(false)} onCancel={cancelParagraph}/>
</>}
```

Remove the old `selection`-based `FloatingTextTools`/`TextToolbar` and `InlineInput` lines for source runs. Keep `InlineInput` only if text-box drafts still use it; otherwise delete it.

Add helpers next to `choose`:

```js
const runsFor=number=>new Map((index[number]?.runs||[]).map(run=>[run.run_id,run]));
const chooseParagraph=(paragraph,number,event)=>{
  if(busyOwnerRef.current||paragraph.state==='not_editable')return;
  cancelTextBox();setSideOpen(false);setManagedSelection(null);invalidateBatch();setPage(number);
  const lines=effectiveLines(paragraph,runsFor(number),recipeState.recipe);
  const caretPos=document.caretPositionFromPoint?.(event.clientX,event.clientY);
  // The outline button is under the pointer, so estimate line/offset from geometry instead.
  const rect=event.currentTarget.getBoundingClientRect(),line=Math.min(lines.length-1,Math.max(0,Math.floor((event.clientY-rect.top)/(rect.height/lines.length))));
  const offset=Math.round((event.clientX-rect.left)/rect.width*lines[line].length);
  setParagraphSelection({paragraph,lines,caret:{line,offset},style:{},status:null});
};
const cancelParagraph=()=>{editVersion.current++;setParagraphSelection(null);};
```

> Remove the `caretPositionFromPoint` line if it ends up unused. The geometry estimate is the shortcut: `// shortcut: caret offset assumes even glyph widths; upgrade to per-glyph boxes from the run map if users report misplaced carets.`

- [ ] **Step 3: `commitParagraph`**

```js
const commitParagraph=async(allowRebuild=false)=>{
  const sel=paragraphSelection,target=sessionRef.current;if(!sel||busyOwnerRef.current)return;
  const number=sel.paragraph.page_index+1,runs=runsFor(number);
  if(!allowRebuild&&!Object.keys(sel.style).length&&!draftChanged(sel.paragraph,sel.lines,runs,recipeState.recipe)){setParagraphSelection(null);return;}
  if(typeof localMetadata?.signed!=='boolean'||(localMetadata.signed&&!acknowledged)){setParagraphSelection(s=>({...s,status:{refused:'Acknowledge the signature notice before editing.',canRebuild:false}}));return;}
  const page=await pdfRef.current.getPage(number),viewport=page.getViewport({scale:1}),rect=viewportBox(sel.paragraph.box,viewport);
  const payload=paragraphPayload({paragraph:sel.paragraph,lines:sel.lines,style:sel.style,recipe:recipeState.recipe,rect,allowRebuild,runsById:runs});
  const owner=beginWork('paragraph','Saving paragraph on the server…');if(!owner)return;
  setParagraphSelection(s=>({...s,status:'saving'}));
  try{
    const result=await textBoxController.preview(payload,{acknowledged});
    if(!result?.prepared)return;
    if(result.plan==='lines'){
      // Same publish as apply(): source kept, recipe replaced, one history entry.
      const snapshot=takeSnapshot('paragraph edit');requireBudget({current:snapshot,candidateBytes:result.prepared.bytes});
      publishViewer(result.prepared,()=>current(target));retain(snapshot);target.bytes=result.prepared.bytes;
      setRecipeState({recipe:result.recipe,history:[]});setOutput(result.prepared.bytes);
      setParagraphSelection(null);editVersion.current++;setMessage('Paragraph saved. Undo restores the previous PDF.');
    }else{
      await applyTextBox();setParagraphSelection(null);await analyze();
    }
  }catch(error){
    setParagraphSelection(s=>s&&({...s,status:{refused:error.code==='PARAGRAPH_NEEDS_REBUILD'?'This text does not fit the original lines.':explainTextBoxError(error),canRebuild:error.code==='PARAGRAPH_NEEDS_REBUILD'}}));
  }finally{finishWork(owner);}
};
```

> Implementer note: check what `textBoxController.preview` returns and how it exposes server fields (`plan`, `recipe`). Read `client/src/textBoxes/controller.mjs` and pass those fields through the `prepared` result without changing its existing contract. `applyTextBox` reads `textBoxController.previewResult` and `textBoxPayloadRef.current`, so set `textBoxPayloadRef.current=payload` before calling it. Make `applyTextBox` take `'paragraph edit'` as its history action label when `payload.operation==='replace-paragraph'`. Delete the old `checkFit`, `apply` and `expandSourceText` only if nothing else references them (`grep -n "checkFit\|expandSourceText\|apply\b" client/src/App.jsx`). Find/Replace's `applyBatch` stays.

- [ ] **Step 4: Run all client checks**

Run (in `client/`): `npm test && npm run build`
Expected: PASS and build OK.

- [ ] **Step 5: Commit**

```bash
git add client/src/App.jsx client/src/textBoxes/controller.mjs
git commit -m "feat: commit paragraph edits on blur with one undo entry"
```

---

### Task 9: Browser verification and regression

**Files:**
- Create: `docs/verification/sejda-inline-editing-2026-10-31.md`

- [ ] **Step 1: Full suites**

Run: `uv run pytest -q` and, in `client/`, `npm test && npm run build`.
Expected: no new failures compared with the corpus audit baseline (`.planning/audits/corpus-compatibility-2026-10-30.md`: one known CPU-limit failure, `test_40page_batch_worker_apply`).

- [ ] **Step 2: Browser journey (built-in browser, local dev server)**

Start the app with the project's existing launch config (`.claude/launch.json`, or the README dev commands). Using `tools/build_export_fixtures.py`'s fixture saved to the scratchpad:
1. Open the PDF, switch to Edit text, run Analyze text.
2. Hover the "Left first / Left second" paragraph. A dashed outline appears.
3. Click inside "second". The caret lands in line 2. Type `!`.
4. Click empty page space. The status shows "Saving…", then the page re-renders with the edit and no editor.
5. Undo. The text returns. Redo. The edit returns.
6. Re-open the paragraph and type a long sentence on line 1, then click away. The refusal appears with **Rebuild as text box**. Click it. The paragraph is rebuilt and wrapped, and the next click works without the Analyze gate.
7. Download. Check with `qpdf --check` and confirm with pdfium text extraction that the old text is gone, the new text is present, and the neighbouring text is unchanged.

- [ ] **Step 3: Write evidence and commit**

Record the commands, results and any refusals in `docs/verification/sejda-inline-editing-2026-10-31.md`. Then:

```bash
git add docs/verification/sejda-inline-editing-2026-10-31.md
git commit -m "docs: verify Sejda-style inline paragraph editing"
```

---

## Self-review

- **Spec coverage:**
  - §1 UX: Tasks 7–8.
  - §2 paragraph data: Tasks 1 and 5.
  - §3 commit: Tasks 2–4, with line and rebuild plans.
  - §4 client: Tasks 6–8.
  - §5 errors: stale in Tasks 3–5, unsafe in Task 3, signature in Task 8, refusal keeps draft in Task 8.
  - §6 testing: each task plus Task 9.
- **Deviations** are listed at the top. Endpoint and line mapping are simpler than the spec but meet its rules.
- **Names checked across tasks:**
  - `page_paragraphs`, `paragraph_id`, `Paragraph.run_ids`
  - `line_segments`, `line_ops`, `rebuild_text`, `prepare_paragraph_edit`
  - `effectiveLines`, `paragraphAt`, `paragraphPayload`, `draftChanged`
  - `ParagraphOutlines`, `ParagraphEditor`
  - `commitParagraph`, `chooseParagraph`, `cancelParagraph`, `runsFor`
- **Known shortcut:** the caret offset comes from geometry with even glyph widths (comment in Task 8).
