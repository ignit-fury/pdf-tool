"""Inert serializers over renderer-independent blocks, with bounded output.

The caller supplies its one RunIndex over the current materialized PDF. This
module opens no files, creates no parsers and imports no server code.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass

from engine.blocks import Block, DocumentBlocks, Span, build_document
from engine.index import RunIndex

# At most 32 MiB UTF-8, below the worker's 48 MiB artifact cap even for astral text.
MAX_OUTPUT_CHARS = 8 * 1024 * 1024
_MARKDOWN = re.compile(r'([\\`*_{}\[\]()#+.!|>~\-])')


@dataclass(frozen=True, slots=True)
class ExportResult:
    text: str
    has_text: bool


class _Output:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.size = 0

    def add(self, text: str) -> None:
        self.size += len(text)
        if self.size > MAX_OUTPUT_CHARS:
            raise ValueError('export-output-limit')
        self.parts.append(text)

    def finish(self) -> str:
        return ''.join(self.parts)


def _plain(spans: tuple[Span, ...]) -> str:
    return ''.join(span.text for span in spans)


def serialize_text(document: DocumentBlocks) -> str:
    out = _Output()
    for number,page in enumerate(document.pages):
        if number:
            out.add('\f\n')
        for block in page.blocks:
            if block.kind == 'table':
                for row in block.rows:
                    out.add('\t'.join(_plain(cell) for cell in row)+'\n')
            else:
                out.add(_plain(block.spans)+'\n')
    return out.finish()


def _markdown(spans: tuple[Span, ...], *, cell: bool = False) -> str:
    out: list[str] = []
    for span in spans:
        escaped = _MARKDOWN.sub(r'\\\1',html.escape(span.text,quote=False))
        # Tables cannot contain literal row breaks. Only this trusted tag is emitted.
        if cell:
            escaped = escaped.replace('\n','<br>').replace('\r','')
        if span.bold is True:
            escaped = '**'+escaped+'**'
        if span.italic is True:
            escaped = '*'+escaped+'*'
        out.append(escaped)
    return ''.join(out)


def _list_body(block: Block) -> tuple[Span, ...]:
    # Only the explicit source marker is stripped. Keep style and provenance.
    spans = list(block.spans)
    if spans:
        first = spans[0]
        text = re.sub(r'^(?:[-*•]|\d+[.)])\s+','',first.text,count=1)
        spans[0] = Span(text,first.bold,first.italic,first.source_runs)
    return tuple(spans)


def serialize_markdown(document: DocumentBlocks) -> str:
    out = _Output()
    for number,page in enumerate(document.pages):
        if number:
            out.add('\n---\n\n')
        for block in page.blocks:
            if block.kind == 'table':
                for row_number,row in enumerate(block.rows):
                    out.add('| '+' | '.join(_markdown(cell,cell=True) for cell in row)+' |\n')
                    if row_number == 0:
                        out.add('| '+' | '.join('---' for _ in row)+' |\n')
                out.add('\n')
            else:
                prefix = '#'*(block.heading_level or 1)+' ' if block.kind == 'heading' else '- ' if block.kind == 'list' else ''
                spans = _list_body(block) if block.kind == 'list' else block.spans
                out.add(prefix+_markdown(spans)+'\n\n')
    return out.finish()


def _html(spans: tuple[Span, ...]) -> str:
    out: list[str] = []
    for span in spans:
        text = html.escape(span.text,quote=True).replace('\n','<br>')
        if span.bold is True:
            text = '<strong>'+text+'</strong>'
        if span.italic is True:
            text = '<em>'+text+'</em>'
        out.append(text)
    return ''.join(out)


def serialize_html(document: DocumentBlocks) -> str:
    out = _Output()
    out.add('<!doctype html>\n<html><head><meta charset="utf-8"><title>Document export</title></head><body>\n')
    for page in document.pages:
        out.add('<section>\n')
        in_list = False
        for block in page.blocks:
            if in_list and block.kind != 'list':
                out.add('</ul>\n')
                in_list = False
            if block.kind == 'table':
                out.add('<table><tbody>\n')
                for row in block.rows:
                    out.add('<tr>'+''.join('<td>'+_html(cell)+'</td>' for cell in row)+'</tr>\n')
                out.add('</tbody></table>\n')
            elif block.kind == 'list':
                if not in_list:
                    out.add('<ul>\n')
                    in_list = True
                out.add('<li>'+_html(_list_body(block))+'</li>\n')
            else:
                tag = 'h'+str(min(6,max(1,block.heading_level or 1))) if block.kind == 'heading' else 'p'
                out.add('<'+tag+'>'+_html(block.spans)+'</'+tag+'>\n')
        if in_list:
            out.add('</ul>\n')
        out.add('</section>\n')
    out.add('</body></html>\n')
    return out.finish()


def export_document_result(index: RunIndex, format: str) -> ExportResult:
    """Serialize once and report real block content independently of format markup."""
    serializers = {'text': serialize_text, 'markdown': serialize_markdown, 'html': serialize_html}
    serializer = serializers.get(format)
    if serializer is None:
        raise ValueError('unsupported-export-format')
    document = build_document(index)
    has_text = any(
        span.text.strip()
        for page in document.pages
        for block in page.blocks
        for spans in (block.spans, *(cell for row in block.rows for cell in row))
        for span in spans
    )
    return ExportResult(serializer(document),has_text)


def export_document(index: RunIndex, format: str) -> str:
    return export_document_result(index,format).text
