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
