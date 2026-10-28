"""Optional, bounded OOXML from shared blocks. No PDF reader or registration.

Deleting this module disables DOCX alone. Review and serialization consume the
same immutable projection, including explicit unsupported-layout facts.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable
import hashlib
import io
import json
import math
import re
import zipfile
import xml.etree.ElementTree as ET

from engine.blocks import DocumentBlocks, ExportLimitError, LayoutFact, Span
from engine.image_index import ImagePlacement
from engine.records import RunRecord

MAX_BYTES = 48 * 1024 * 1024
MAX_TEXT = 8 * 1024 * 1024
POLICY_VERSION = 1
NAMESPACES = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture',
}
for prefix, uri in NAMESPACES.items():
    ET.register_namespace(prefix, uri)
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
CONTENT = 'http://schemas.openxmlformats.org/package/2006/content-types'
OFFICE_REL = NAMESPACES['r'] + '/'


class DocxRefusal(ValueError):
    def __init__(self) -> None:
        super().__init__('DOCX_UNSUPPORTED')


@dataclass(frozen=True, slots=True)
class DocxSpan:
    text: str
    bold: bool
    italic: bool


@dataclass(frozen=True, slots=True)
class DocxBlock:
    kind: str
    spans: tuple[DocxSpan, ...]
    heading_level: int | None = None
    rows: tuple[tuple[tuple[DocxSpan, ...], ...], ...] = ()
    y: float = 0


@dataclass(frozen=True, slots=True)
class DocxPage:
    blocks: tuple[DocxBlock, ...]
    images: tuple[ImagePlacement, ...]


@dataclass(frozen=True, slots=True)
class DocxSnapshot:
    pages: tuple[DocxPage, ...]
    facts: tuple[LayoutFact, ...]
    images_complete: bool

    @property
    def review(self) -> dict[str, object]:
        return {'schema_version': 1, 'page_count': len(self.pages),
            'has_text': any(span.text.strip() for page in self.pages for block in page.blocks
                            for span in (*block.spans, *(s for row in block.rows for cell in row for s in cell))),
            'facts': [{'code': f.code, 'pages': list(f.pages), 'count': f.count} for f in self.facts],
            'supported_ruled_tables': sum(b.kind == 'table' for p in self.pages for b in p.blocks),
            'images_complete': self.images_complete}


def _text(value: str) -> str:
    if any(not (c in '\t\r\n' or 0x20 <= ord(c) <= 0xD7FF
                or 0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF) for c in value):
        raise DocxRefusal()
    return value.replace('\r\n', '\n').replace('\r', '\n')


def prepare_docx(document: DocumentBlocks) -> DocxSnapshot:
    if not 0 < len(document.pages) <= 2000:
        raise ExportLimitError('docx-page-limit')
    pages: list[DocxPage] = []
    all_facts: list[LayoutFact] = []
    text_count = image_count = image_bytes = 0
    complete = True

    def spans(source: Iterable[Span]) -> tuple[DocxSpan, ...]:
        nonlocal text_count
        result = []
        for span in source:
            value = _text(span.text)
            text_count += len(value)
            if text_count > MAX_TEXT:
                raise ExportLimitError('docx-text-limit')
            result.append(DocxSpan(value, span.bold is True, span.italic is True))
        return tuple(result)

    for page in document.pages:
        facts = list(page.facts)
        if not page.image_analysis_complete and not any(f.code == 'IMAGE_UNSUPPORTED' for f in facts):
            facts.append(LayoutFact('IMAGE_UNSUPPORTED', (page.page_index,)))
        complete = complete and page.image_analysis_complete
        fallback = any(f.code in {'COLUMN_LAYOUT', 'AMBIGUOUS_TABLE', 'UNSUPPORTED_DIRECTION'} for f in facts)
        blocks = []
        if fallback:
            runs = {r.run_id: r for block in page.blocks for r in block.source_runs}
            ordered = sorted(runs.values(), key=lambda r: (
                min((g.y for g in r.glyphs), default=0),
                min((g.x for g in r.glyphs), default=0), r.run_id))
            for run in ordered:
                blocks.append(DocxBlock('paragraph', spans((run_as_span(run),)),
                                         y=min((g.y for g in run.glyphs), default=0)))
            # Synthetic blocks without provenance retain their text, never vanish.
            for block in page.blocks:
                if not block.source_runs:
                    blocks.append(DocxBlock('paragraph', spans(block.spans)))
            table_count = sum(b.kind == 'table' for b in page.blocks)
            if table_count:
                facts.append(LayoutFact('TABLES_FLATTENED', (page.page_index,), table_count))
        else:
            for block in page.blocks:
                rows = tuple(tuple(spans(cell) for cell in row) for row in block.rows)
                y = min((g.y for r in block.source_runs for g in r.glyphs), default=0)
                blocks.append(DocxBlock(block.kind, spans(block.spans), block.heading_level, rows, y))
        images = []
        for image in page.images:
            image_count += 1
            image_bytes += len(image.data)
            if image_count > 200 or image_bytes > 32 * 1024 * 1024:
                raise ExportLimitError('docx-image-limit')
            if (image.media_type != 'image/png' or not image.data.startswith(b'\x89PNG\r\n\x1a\n')
                    or len(image.bbox) != 4 or not all(math.isfinite(v) for v in image.bbox)
                    or image.bbox[2] <= image.bbox[0] or image.bbox[3] <= image.bbox[1]):
                raise DocxRefusal()
            images.append(image)
        if not any(s.text.strip() for b in blocks for s in (*b.spans, *(s for row in b.rows for cell in row for s in cell))):
            if not any(f.code == 'NO_EXTRACTABLE_TEXT' for f in facts):
                facts.append(LayoutFact('NO_EXTRACTABLE_TEXT', (page.page_index,), 1))
        all_facts.extend(facts)
        pages.append(DocxPage(tuple(blocks), tuple(images)))
    grouped: dict[str, list[LayoutFact]] = {}
    for fact in all_facts:
        grouped.setdefault(fact.code, []).append(fact)
    merged = tuple(LayoutFact(code, tuple(sorted({p for f in facts for p in f.pages})),
        sum(f.count for f in facts if f.count is not None) if all(f.count is not None for f in facts) else None)
        for code, facts in sorted(grouped.items()))
    return DocxSnapshot(tuple(pages), merged, complete)


def run_as_span(run: RunRecord) -> Span:
    # Local adapter keeps the optional writer's projection independent of parser objects.
    return Span(run.display_text, run.bold, run.italic)


def snapshot_digest(snapshot: DocxSnapshot) -> str:
    def span(s: DocxSpan) -> list[object]:
        return [s.text, s.bold, s.italic]
    canonical = {'policy_version': POLICY_VERSION, 'review': snapshot.review,
        'pages': [{'blocks': [[b.kind, b.heading_level, b.y, [span(s) for s in b.spans],
            [[[span(s) for s in cell] for cell in row] for row in b.rows]] for b in p.blocks],
            'images': [[i.image_id, i.bbox, i.pixel_width, i.pixel_height, i.media_type,
                        hashlib.sha256(i.data).hexdigest()] for i in p.images]} for p in snapshot.pages]}
    encoded = json.dumps(canonical, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _tag(name: str) -> str:
    prefix, local = name.split(':')
    return '{' + NAMESPACES[prefix] + '}' + local


def _child(parent: ET.Element, tag_name: str, **attributes: object) -> ET.Element:
    return ET.SubElement(parent, _tag(tag_name), {_tag(k) if ':' in k else k: str(v) for k,v in attributes.items()})


def _paragraph(parent: ET.Element, content: tuple[DocxSpan, ...], heading: int | None = None) -> ET.Element:
    paragraph = _child(parent, 'w:p')
    if heading is not None:
        _child(_child(paragraph, 'w:pPr'), 'w:pStyle', **{'w:val': 'Heading' + str(max(1,min(6,heading)))})
    for span in content:
        run = _child(paragraph, 'w:r')
        if span.bold or span.italic:
            props = _child(run, 'w:rPr')
            if span.bold:
                _child(props, 'w:b')
            if span.italic:
                _child(props, 'w:i')
        for part in re.split(r'([\t\n])', span.text):
            if part in ('\t','\n'):
                _child(run, 'w:tab' if part == '\t' else 'w:br')
            elif part:
                text = _child(run, 'w:t')
                text.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
                text.text = part
    return paragraph


def _picture(body: ET.Element, image: ImagePlacement, identifier: int) -> None:
    width, height = image.bbox[2]-image.bbox[0], image.bbox[3]-image.bbox[1]
    scale = min(1.0, 468 / width, 648 / height)
    cx, cy = max(1,round(width*scale*12700)), max(1,round(height*scale*12700))
    inline = _child(_child(_child(_child(body, 'w:p'), 'w:r'), 'w:drawing'), 'wp:inline')
    _child(inline, 'wp:extent', cx=cx, cy=cy)
    _child(inline, 'wp:docPr', id=identifier, name=f'Image {identifier}')
    graphic = _child(_child(inline, 'a:graphic'), 'a:graphicData', uri=NAMESPACES['pic'])
    picture = _child(graphic, 'pic:pic')
    props = _child(picture, 'pic:nvPicPr')
    _child(props, 'pic:cNvPr', id=identifier, name=f'image{identifier}.png')
    _child(props, 'pic:cNvPicPr')
    fill = _child(picture, 'pic:blipFill')
    _child(fill, 'a:blip', **{'r:embed': f'rIdImage{identifier}'})
    _child(_child(fill, 'a:stretch'), 'a:fillRect')
    shape = _child(picture, 'pic:spPr')
    transform = _child(shape, 'a:xfrm')
    _child(transform, 'a:off', x=0, y=0)
    _child(transform, 'a:ext', cx=cx, cy=cy)
    _child(_child(shape, 'a:prstGeom', prst='rect'), 'a:avLst')


def serialize_docx(snapshot: DocxSnapshot) -> bytes:
    document = ET.Element(_tag('w:document'))
    body = _child(document, 'w:body')
    styles = ET.Element(_tag('w:styles'))
    normal = _child(styles, 'w:style', **{'w:type':'paragraph', 'w:default':'1', 'w:styleId':'Normal'})
    _child(normal, 'w:name', **{'w:val':'Normal'})
    props = _child(normal, 'w:rPr')
    _child(props, 'w:rFonts', **{'w:ascii':'Arial','w:hAnsi':'Arial'})
    _child(props, 'w:sz', **{'w:val':'24'})
    for level, size in enumerate((40,32,28,26,24,24), 1):
        style = _child(styles, 'w:style', **{'w:type':'paragraph','w:styleId':f'Heading{level}'})
        _child(style, 'w:name', **{'w:val':f'heading {level}'})
        _child(style, 'w:basedOn', **{'w:val':'Normal'})
        paragraph = _child(style, 'w:pPr')
        _child(paragraph, 'w:keepNext')
        _child(paragraph, 'w:outlineLvl', **{'w:val':level-1})
        run = _child(style, 'w:rPr')
        _child(run, 'w:b')
        _child(run, 'w:sz', **{'w:val':size})
    relationships = ET.Element('{' + REL + '}Relationships')
    ET.SubElement(relationships, '{'+REL+'}Relationship', Id='rIdStyles', Type=OFFICE_REL+'styles', Target='styles.xml')
    parts: dict[str, bytes] = {}
    image_id = 0
    for page_number, page in enumerate(snapshot.pages):
        if page_number:
            paragraph = _child(body, 'w:p')
            _child(_child(paragraph, 'w:r'), 'w:br', **{'w:type':'page'})
        ordered = [(b.y,0,n,b) for n,b in enumerate(page.blocks)] + [(i.bbox[1],1,n,i) for n,i in enumerate(page.images)]
        for _, _, _, item in sorted(ordered, key=lambda value:value[:3]):
            if isinstance(item, ImagePlacement):
                image_id += 1
                parts[f'word/media/image{image_id}.png'] = item.data
                ET.SubElement(relationships, '{'+REL+'}Relationship', Id=f'rIdImage{image_id}',
                    Type=OFFICE_REL+'image', Target=f'media/image{image_id}.png')
                _picture(body, item, image_id)
            elif item.kind == 'table':
                table = _child(body, 'w:tbl')
                properties = _child(table, 'w:tblPr')
                borders = _child(properties, 'w:tblBorders')
                for edge in ('top','left','bottom','right','insideH','insideV'):
                    _child(borders, 'w:'+edge, **{'w:val':'single','w:sz':'4','w:color':'auto'})
                columns = max((len(row) for row in item.rows), default=1)
                grid = _child(table, 'w:tblGrid')
                for _ in range(columns):
                    _child(grid, 'w:gridCol', **{'w:w':9360//columns})
                for row in item.rows:
                    tr = _child(table, 'w:tr')
                    for cell in row:
                        tc = _child(tr, 'w:tc')
                        _paragraph(tc, cell)
            else:
                _paragraph(body, item.spans, item.heading_level if item.kind == 'heading' else None)
    section = _child(body, 'w:sectPr')
    _child(section, 'w:pgSz', **{'w:w':12240,'w:h':15840})
    _child(section, 'w:pgMar', **{'w:top':1440,'w:right':1440,'w:bottom':1440,'w:left':1440,'w:header':720,'w:footer':720,'w:gutter':0})
    def xml(root: ET.Element) -> bytes:
        return bytes(ET.tostring(root, encoding='utf-8', xml_declaration=True))
    parts.update({'word/document.xml':xml(document), 'word/styles.xml':xml(styles),
                  'word/_rels/document.xml.rels':xml(relationships)})
    types = ET.Element('{'+CONTENT+'}Types')
    for extension, media in [('rels','application/vnd.openxmlformats-package.relationships+xml'),('xml','application/xml'),('png','image/png')]:
        ET.SubElement(types, '{'+CONTENT+'}Default', Extension=extension, ContentType=media)
    for path, media in [('document','application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'),
                        ('styles','application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml')]:
        ET.SubElement(types, '{'+CONTENT+'}Override', PartName='/word/'+path+'.xml', ContentType=media)
    roots = ET.Element('{'+REL+'}Relationships')
    ET.SubElement(roots, '{'+REL+'}Relationship', Id='rIdDocument', Type=OFFICE_REL+'officeDocument', Target='word/document.xml')
    parts.update({'[Content_Types].xml':xml(types), '_rels/.rels':xml(roots)})
    if len(parts) > 256 or sum(map(len,parts.values())) > MAX_BYTES:
        raise ExportLimitError('docx-package-limit')
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path, data in parts.items():
            info = zipfile.ZipInfo(path, date_time=(1980,1,1,0,0,0))
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)
            if output.tell() > MAX_BYTES:
                raise ExportLimitError('docx-package-limit')
    result = output.getvalue()
    if len(result) > MAX_BYTES:
        raise ExportLimitError('docx-package-limit')
    return result
