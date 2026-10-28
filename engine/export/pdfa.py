"""Conservative native PDF/A-2b remediation inside the disposable PDF worker.

This is a support allowlist, not a general PDF/A validator. The independent
dev/CI corpus oracle validates emitted files; no validator runs in requests.
"""
from __future__ import annotations

from collections.abc import Buffer
from dataclasses import dataclass
import hashlib
import io
import math
from pathlib import Path
import re
import time
from typing import Any
import zlib

import pikepdf
from fontTools.ttLib import TTFont

from engine.fonts import build_tounicode_cmap_bytes

MAX_OUTPUT_BYTES = 48 * 1024 * 1024
MAX_DECODED_BYTES = 48 * 1024 * 1024
MAX_STREAM_BYTES = 16 * 1024 * 1024
MAX_OBJECTS = 50_000
MAX_OPERATORS = 100_000
MAX_PAGES = 1000
MAX_CPU_SECONDS = 18
REASONS = frozenset({'font-missing', 'font-unsupported', 'font-invalid',
    'color-unsupported', 'content-unsupported', 'structure-unsupported',
    'metadata-unsupported', 'pdf-version', 'limit'})
ICC_SHA256 = '384b832de3412066743b52a75ee906b6fb9fb8d9e09e936fc2c43223815c6e0a'
# Read before the caller installs its filesystem sandbox, like bundled fonts.
ICC_DATA = (Path(__file__).resolve().parents[1] / 'data/sRGB2014.icc').read_bytes()
if hashlib.sha256(ICC_DATA).hexdigest() != ICC_SHA256:
    raise RuntimeError('Archival profile integrity failure')


class PdfaRefusal(Exception):
    """Finite safe public reasons; never carry source values or candidate bytes."""
    code = 'PDFA_UNSUPPORTED'

    def __init__(self, reason_id: str = 'content-unsupported') -> None:
        self.reason_id = reason_id if reason_id in REASONS else 'content-unsupported'
        super().__init__(self.reason_id)


@dataclass(frozen=True, slots=True)
class PdfaResult:
    data: bytes
    notices: tuple[str, ...] = ()


class _Output(io.BytesIO):
    def write(self, buffer: Buffer, /) -> int:
        if self.tell() + memoryview(buffer).nbytes > MAX_OUTPUT_BYTES:
            raise PdfaRefusal('limit')
        return super().write(buffer)


def _keys(obj: Any, allowed: str, reason: str = 'structure-unsupported') -> None:
    if not isinstance(obj, (pikepdf.Dictionary, pikepdf.Stream)):
        raise PdfaRefusal(reason)
    if set(obj.keys()) - {'/' + key for key in allowed.split()}:
        raise PdfaRefusal(reason)


def _number(value: Any, reason: str = 'content-unsupported') -> float:
    if isinstance(value, bool) or isinstance(value, (pikepdf.Object, str)):
        raise PdfaRefusal(reason)
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        raise PdfaRefusal(reason) from None
    if not math.isfinite(result) or abs(result) > 10_000_000:
        raise PdfaRefusal(reason)
    return result


def _integer(value: Any, reason: str) -> int:
    numeric = _number(value, reason)
    if numeric != int(numeric):
        raise PdfaRefusal(reason)
    return int(numeric)


class _Audit:
    def __init__(self) -> None:
        self.started = time.process_time()
        self.decoded = 0
        self.operators = 0
        self.streams: dict[tuple[int, int], bytes] = {}

    def tick(self) -> None:
        if time.process_time() - self.started > MAX_CPU_SECONDS:
            raise PdfaRefusal('limit')

    def stream(self, obj: Any) -> bytes:
        self.tick()
        if not isinstance(obj, pikepdf.Stream):
            raise PdfaRefusal('structure-unsupported')
        identity = obj.objgen
        if identity in self.streams:
            return self.streams[identity]
        filters = obj.get('/Filter')
        if isinstance(filters, pikepdf.Array):
            if len(filters) != 1:
                raise PdfaRefusal('content-unsupported')
            filters = filters[0]
        if obj.get('/DecodeParms') is not None:
            raise PdfaRefusal('content-unsupported')
        raw = obj.read_raw_bytes()
        if len(raw) > MAX_STREAM_BYTES:
            raise PdfaRefusal('limit')
        if filters is None:
            data = raw
        elif filters == pikepdf.Name.FlateDecode:
            decoder = zlib.decompressobj()
            data = decoder.decompress(raw, MAX_STREAM_BYTES + 1)
            if len(data) > MAX_STREAM_BYTES or decoder.unconsumed_tail:
                raise PdfaRefusal('limit')
            if not decoder.eof or decoder.unused_data:
                raise PdfaRefusal('content-unsupported')
        else:
            raise PdfaRefusal('content-unsupported')
        self.decoded += len(data)
        if self.decoded > MAX_DECODED_BYTES:
            raise PdfaRefusal('limit')
        self.streams[identity] = data
        return data

    def graph(self, pdf: pikepdf.Pdf) -> None:
        """Bound direct/indirect closure, including otherwise unused objects."""
        seen: set[tuple[int, int]] = set()
        pending = [(obj, 0) for obj in pdf.objects]
        work = 0
        while pending:
            obj, depth = pending.pop()
            work += 1
            if work + len(pending) > MAX_OBJECTS or depth > 64:
                raise PdfaRefusal('limit')
            self.tick()
            if not isinstance(obj, (pikepdf.Dictionary, pikepdf.Array, pikepdf.Stream)):
                continue
            if obj.objgen != (0, 0):
                if obj.objgen in seen:
                    continue
                seen.add(obj.objgen)
            if isinstance(obj, pikepdf.Array):
                pending.extend((value, depth + 1) for value in obj)
                continue
            forbidden = {'/AA', '/OpenAction', '/A', '/JS', '/JavaScript', '/Launch',
                '/EmbeddedFiles', '/AF', '/XFA', '/AcroForm', '/Annots', '/OC', '/OCProperties',
                '/RichMedia', '/F', '/FFilter', '/FDecodeParms', '/Ref', '/OPI',
                '/Alternates', '/PresSteps', '/Perms', '/Collection'}
            if forbidden.intersection(obj.keys()):
                raise PdfaRefusal('structure-unsupported')
            if any(key in obj for key in ('/SMask', '/Mask', '/Group')):
                raise PdfaRefusal('color-unsupported')
            if isinstance(obj, pikepdf.Stream):
                self.stream(obj)
            pending.extend((value, depth + 1) for key, value in obj.items()
                           if key not in ('/Parent', '/P', '/Pg'))

    def font(self, font: Any) -> tuple[list[str], dict[int, float], Any]:
        reason = 'font-invalid'
        subtype = font.get('/Subtype')
        if subtype not in (pikepdf.Name.Type0, pikepdf.Name.TrueType):
            descriptor = font.get('/FontDescriptor')
            if descriptor is None and subtype == pikepdf.Name.Type1:
                raise PdfaRefusal('font-missing')
            raise PdfaRefusal('font-unsupported')
        _keys(font, 'Type Subtype BaseFont Encoding DescendantFonts ToUnicode FirstChar LastChar Widths FontDescriptor', reason)
        if font.get('/Type') != pikepdf.Name.Font:
            raise PdfaRefusal(reason)
        composite = subtype == pikepdf.Name.Type0
        if composite:
            if font.get('/Encoding') != pikepdf.Name('/Identity-H'):
                raise PdfaRefusal('font-unsupported')
            descendants = font.get('/DescendantFonts')
            if not isinstance(descendants, pikepdf.Array) or len(descendants) != 1:
                raise PdfaRefusal(reason)
            child = descendants[0]
            _keys(child, 'Type Subtype BaseFont CIDSystemInfo CIDToGIDMap W DW FontDescriptor', reason)
            if child.get('/Subtype') != pikepdf.Name.CIDFontType2:
                raise PdfaRefusal('font-unsupported')
            info: Any = child.get('/CIDSystemInfo')
            _keys(info, 'Registry Ordering Supplement', reason)
            if (str(info.get('/Registry')) != 'Adobe' or str(info.get('/Ordering')) != 'Identity'
                    or info.get('/Supplement') != 0 or child.get('/CIDToGIDMap') != pikepdf.Name.Identity):
                raise PdfaRefusal(reason)
            if child.get('/BaseFont') != font.get('/BaseFont'):
                raise PdfaRefusal(reason)
        else:
            child = font
            if font.get('/Encoding') != pikepdf.Name.WinAnsiEncoding:
                raise PdfaRefusal('font-unsupported')
        descriptor = child.get('/FontDescriptor')
        if descriptor is None or '/FontFile2' not in descriptor:
            raise PdfaRefusal('font-missing')
        _keys(descriptor, 'Type FontName Flags FontBBox ItalicAngle Ascent Descent CapHeight StemV FontFile2 MissingWidth', reason)
        if descriptor.get('/Type') != pikepdf.Name.FontDescriptor or child.get('/Type') != pikepdf.Name.Font:
            raise PdfaRefusal(reason)
        flags = _integer(descriptor.get('/Flags'), reason)
        if flags < 0 or flags & ~0x7007F or (bool(flags & 4) == bool(flags & 32)):
            raise PdfaRefusal(reason)
        for field in ('/Ascent', '/Descent', '/CapHeight', '/StemV', '/ItalicAngle'):
            _number(descriptor.get(field), reason)
        bbox = descriptor.get('/FontBBox')
        if not isinstance(bbox, pikepdf.Array) or len(bbox) != 4:
            raise PdfaRefusal(reason)
        for coordinate in bbox:
            _number(coordinate, reason)
        name = str(font.get('/BaseFont', ''))
        if (not re.fullmatch(r'/([A-Z]{6}\+)?[A-Za-z0-9_.-]+', name)
                or str(descriptor.get('/FontName')) != name):
            raise PdfaRefusal(reason)
        _keys(descriptor.FontFile2, 'Length Length1 Filter DecodeParms', reason)
        program = self.stream(descriptor.FontFile2)
        try:
            tt = TTFont(io.BytesIO(program), lazy=False, recalcTimestamp=False)
            if (tt.sfntVersion not in ('\x00\x01\x00\x00', 'true')
                    or not {'head', 'hhea', 'maxp', 'hmtx', 'loca', 'glyf', 'OS/2', 'name', 'cmap'} <= set(tt.keys())
                    or any(key in tt for key in ('CFF ', 'CFF2', 'fvar', 'COLR', 'SVG '))):
                raise PdfaRefusal('font-unsupported')
            permission = tt['OS/2'].fsType
            if permission & ~0xC or permission & 0x2:
                raise PdfaRefusal(reason)
            order: list[str] = tt.getGlyphOrder()
            if not order or len(order) > 4096 or order[0] != '.notdef':
                raise PdfaRefusal(reason)
            ps_name = tt['name'].getDebugName(6)
            # Existing engine dictionaries name the family for every variant;
            # the actual embedded program retains its PostScript style suffix.
            if not ps_name or name[1:].split('+')[-1] not in (ps_name.split('+')[-1], ps_name.split('+')[-1].split('-')[0]):
                raise PdfaRefusal(reason)
            upem = tt['head'].unitsPerEm
            if not 16 <= upem <= 16384 or tt['maxp'].numGlyphs != len(order):
                raise PdfaRefusal(reason)
            for glyph in order:
                self.tick()
                # Force lazy glyf/loca/composite and metric tables to be read.
                tt['glyf'][glyph].getCoordinates(tt['glyf'])
                if glyph not in tt['hmtx'].metrics:
                    raise PdfaRefusal(reason)
            program_widths = {gid: tt['hmtx'].metrics[glyph][0] * 1000 / upem
                              for gid, glyph in enumerate(order)}
            cmap = tt.getBestCmap() or {}
            if composite:
                widths = self.widths(child.get('/W'))
                mapping = {gid: gid for gid in range(len(order))}
            else:
                first = _integer(font.get('/FirstChar'), reason)
                last = _integer(font.get('/LastChar'), reason)
                values = font.get('/Widths')
                if (not 0 <= first <= last <= 255 or not isinstance(values, pikepdf.Array)
                        or len(values) != last - first + 1):
                    raise PdfaRefusal(reason)
                widths = {first + i: _number(value, reason) for i, value in enumerate(values)}
                mapping = {}
                for code in range(first, last + 1):
                    try:
                        char = bytes([code]).decode('cp1252')
                    except UnicodeDecodeError:
                        continue
                    mapped_glyph = cmap.get(ord(char))
                    if mapped_glyph in order:
                        mapping[code] = order.index(mapped_glyph)
            for code, width in widths.items():
                gid = mapping.get(code)
                if gid is None or abs(program_widths[gid] - width) > 1.0:
                    raise PdfaRefusal(reason)
            if '/ToUnicode' in font:
                _keys(font.ToUnicode, 'Length Filter DecodeParms', reason)
                unicode_data = self.stream(font.ToUnicode)
                # Only the engine's finite bfchar CMap form is supported.
                if (b'beginbfchar' not in unicode_data or b'begincmap' not in unicode_data
                        or b'beginbfrange' in unicode_data or b'usecmap' in unicode_data):
                    raise PdfaRefusal('font-unsupported')
                pairs: dict[int, str] = {}
                for block in re.findall(rb'\d+ beginbfchar\s+(.*?)\s+endbfchar', unicode_data, re.S):
                    for code, value in re.findall(rb'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', block):
                        cid = int(code, 16)
                        text = bytes.fromhex(value.decode('ascii')).decode('utf-16-be')
                        if cid in pairs or not text:
                            raise PdfaRefusal(reason)
                        pairs[cid] = text
                if not pairs or any(cid not in mapping or not mapping[cid] for cid in pairs):
                    raise PdfaRefusal(reason)
                if unicode_data != build_tounicode_cmap_bytes(pairs):
                    raise PdfaRefusal('font-unsupported')
            else:
                # Identity text without a finite Unicode map is outside this policy.
                if composite:
                    raise PdfaRefusal('font-unsupported')
                pairs = {code: '' for code in mapping}
            tt.close()
            return order, widths, (mapping, pairs, composite)
        except PdfaRefusal:
            raise
        except Exception:
            raise PdfaRefusal(reason) from None

    def widths(self, values: Any) -> dict[int, float]:
        if not isinstance(values, pikepdf.Array):
            raise PdfaRefusal('font-invalid')
        widths: dict[int, float] = {}
        index = 0
        while index < len(values):
            start = _integer(values[index], 'font-invalid')
            index += 1
            if index >= len(values) or not 0 <= start <= 65535:
                raise PdfaRefusal('font-invalid')
            next_value = values[index]
            index += 1
            if isinstance(next_value, pikepdf.Array):
                run = list(next_value)
            else:
                end = _integer(next_value, 'font-invalid')
                if index >= len(values) or not start <= end <= 65535:
                    raise PdfaRefusal('font-invalid')
                run = [values[index]] * (end - start + 1)
                index += 1
            if len(run) + len(widths) > 4096:
                raise PdfaRefusal('limit')
            for offset, width in enumerate(run):
                code = start + offset
                if code in widths or code > 65535:
                    raise PdfaRefusal('font-invalid')
                widths[code] = _number(width, 'font-invalid')
        return widths

    def resources(self, resources: Any) -> dict[str, Any]:
        _keys(resources, 'Font XObject ProcSet ColorSpace')
        if '/ColorSpace' in resources and len(resources.ColorSpace):
            raise PdfaRefusal('color-unsupported')
        if '/ProcSet' in resources:
            if (not isinstance(resources.ProcSet, pikepdf.Array)
                    or any(str(value) not in {'/PDF', '/Text', '/ImageB', '/ImageC'} for value in resources.ProcSet)):
                raise PdfaRefusal('structure-unsupported')
        fonts = {}
        if '/Font' in resources:
            if not isinstance(resources.Font, pikepdf.Dictionary):
                raise PdfaRefusal('font-invalid')
            for key, value in resources.Font.items():
                self.tick()
                fonts[key] = self.font(value)
        if '/XObject' in resources:
            if not isinstance(resources.XObject, pikepdf.Dictionary):
                raise PdfaRefusal('structure-unsupported')
            for _key, image in resources.XObject.items():
                _keys(image, 'Type Subtype Width Height BitsPerComponent ColorSpace Length Filter DecodeParms Interpolate Intent')
                if image.get('/Subtype') != pikepdf.Name.Image or image.get('/Type') != pikepdf.Name.XObject:
                    raise PdfaRefusal('content-unsupported')
                color = image.get('/ColorSpace')
                if color not in (pikepdf.Name.DeviceRGB, pikepdf.Name.DeviceGray):
                    raise PdfaRefusal('color-unsupported')
                width = _integer(image.get('/Width'), 'content-unsupported')
                height = _integer(image.get('/Height'), 'content-unsupported')
                if width <= 0 or height <= 0 or width * height > 16_000_000 or max(width, height) > 16384:
                    raise PdfaRefusal('limit')
                if image.get('/BitsPerComponent') != 8 or image.get('/Intent') not in (None, pikepdf.Name.RelativeColorimetric):
                    raise PdfaRefusal('content-unsupported')
                channels = 3 if color == pikepdf.Name.DeviceRGB else 1
                if len(self.stream(image)) != width * height * channels:
                    raise PdfaRefusal('content-unsupported')
        return fonts

    def content(self, page: Any, fonts: dict[str, Any], resources: Any) -> None:
        contents = page.obj.get('/Contents')
        streams = list(contents) if isinstance(contents, pikepdf.Array) else [contents]
        for stream in streams:
            _keys(stream, 'Length Filter DecodeParms')
            self.stream(stream)
        # Parsing is bounded above by the decoded byte cap and worker CPU/RSS.
        instructions = pikepdf.parse_content_stream(page)
        numeric_counts = {'q': 0, 'Q': 0, 'cm': 6, 'w': 1, 'J': 1, 'j': 1, 'M': 1,
            'm': 2, 'l': 2, 'c': 6, 'v': 4, 'y': 4, 'h': 0, 're': 4,
            'S': 0, 's': 0, 'f': 0, 'F': 0, 'f*': 0, 'B': 0, 'B*': 0,
            'b': 0, 'b*': 0, 'n': 0, 'W': 0, 'W*': 0, 'BT': 0, 'ET': 0,
            'Tc': 1, 'Tw': 1, 'Tz': 1, 'TL': 1, 'Tr': 1, 'Ts': 1,
            'Td': 2, 'TD': 2, 'Tm': 6, 'T*': 0, 'rg': 3, 'RG': 3, 'g': 1, 'G': 1}
        selected = None
        in_text = False
        stack: list[Any] = []

        def showing(value: Any) -> None:
            if not in_text or selected is None or not isinstance(value, pikepdf.String):
                raise PdfaRefusal('content-unsupported')
            order, widths, (mapping, unicode_map, composite) = selected
            raw = bytes(value)
            if composite and len(raw) % 2:
                raise PdfaRefusal('font-invalid')
            codes = [int.from_bytes(raw[i:i + 2], 'big') for i in range(0, len(raw), 2)] if composite else list(raw)
            for code in codes:
                gid = mapping.get(code)
                if (gid is None or gid <= 0 or gid >= len(order)
                        or code not in widths or code not in unicode_map):
                    raise PdfaRefusal('font-invalid')

        for instruction in instructions:
            self.operators += 1
            self.tick()
            if self.operators > MAX_OPERATORS:
                raise PdfaRefusal('limit')
            if isinstance(instruction, pikepdf.ContentStreamInlineImage):
                raise PdfaRefusal('content-unsupported')
            operands = instruction.operands
            op = str(instruction.operator)
            if op in {'Tf', 'Tc', 'Tw', 'Tz', 'TL', 'Tr', 'Ts', 'Td', 'TD', 'Tm', 'T*'} and not in_text:
                raise PdfaRefusal('content-unsupported')
            if op in ('k', 'K', 'cs', 'CS', 'sc', 'SC', 'scn', 'SCN', 'sh'):
                raise PdfaRefusal('color-unsupported')
            if op in numeric_counts:
                if len(operands) != numeric_counts[op]:
                    raise PdfaRefusal('content-unsupported')
                numbers = [_number(value) for value in operands]
                if op in ('rg', 'RG', 'g', 'G') and any(not 0 <= value <= 1 for value in numbers):
                    raise PdfaRefusal('color-unsupported')
                if op == 'BT':
                    if in_text:
                        raise PdfaRefusal('content-unsupported')
                    in_text = True
                elif op == 'ET':
                    if not in_text:
                        raise PdfaRefusal('content-unsupported')
                    in_text = False
                elif op == 'q':
                    if in_text or len(stack) >= 64:
                        raise PdfaRefusal('content-unsupported')
                    stack.append(selected)
                elif op == 'Q':
                    if in_text or not stack:
                        raise PdfaRefusal('content-unsupported')
                    selected = stack.pop()
                elif op in ('J', 'j') and numbers[0] not in (0, 1, 2):
                    raise PdfaRefusal('content-unsupported')
                elif op == 'w' and numbers[0] < 0:
                    raise PdfaRefusal('content-unsupported')
                elif op == 'M' and numbers[0] < 1:
                    raise PdfaRefusal('content-unsupported')
                elif op == 'Tr' and numbers[0] not in range(8):
                    raise PdfaRefusal('content-unsupported')
            elif op == 'Tf':
                if len(operands) != 2 or not isinstance(operands[0], pikepdf.Name):
                    raise PdfaRefusal('content-unsupported')
                _number(operands[1])
                selected = fonts.get(str(operands[0]))
                if selected is None:
                    raise PdfaRefusal('font-missing')
            elif op in ('Tj', "'", '"'):
                if len(operands) != (3 if op == '"' else 1):
                    raise PdfaRefusal('content-unsupported')
                for value in operands[:-1]:
                    _number(value)
                showing(operands[-1])
            elif op == 'TJ':
                if len(operands) != 1 or not isinstance(operands[0], pikepdf.Array):
                    raise PdfaRefusal('content-unsupported')
                for value in operands[0]:
                    if isinstance(value, pikepdf.String):
                        showing(value)
                    else:
                        _number(value)
            elif op == 'Do':
                if (in_text or len(operands) != 1 or not isinstance(operands[0], pikepdf.Name)
                        or str(operands[0]) not in resources.get('/XObject', pikepdf.Dictionary())):
                    raise PdfaRefusal('content-unsupported')
            elif op == 'd':
                if len(operands) != 2 or not isinstance(operands[0], pikepdf.Array):
                    raise PdfaRefusal('content-unsupported')
                dash = [_number(value) for value in operands[0]]
                if any(value < 0 for value in dash) or (dash and not any(dash)) or _number(operands[1]) < 0:
                    raise PdfaRefusal('content-unsupported')
            else:
                raise PdfaRefusal('content-unsupported')
        if in_text or stack:
            raise PdfaRefusal('content-unsupported')


def _geometry(pdf: pikepdf.Pdf) -> list[tuple[Any, ...]]:
    result = []
    for page in pdf.pages:
        record: list[Any] = []
        for key in ('/MediaBox', '/CropBox', '/BleedBox', '/TrimBox', '/ArtBox'):
            value = page.obj.get(key, page.obj.get('/MediaBox'))
            if not isinstance(value, pikepdf.Array) or len(value) != 4:
                raise PdfaRefusal('structure-unsupported')
            coords = tuple(_number(number, 'structure-unsupported') for number in value)
            if coords[0] >= coords[2] or coords[1] >= coords[3]:
                raise PdfaRefusal('structure-unsupported')
            record.append(coords)
        rotate = _integer(page.obj.get('/Rotate', 0), 'structure-unsupported')
        unit = _number(page.obj.get('/UserUnit', 1), 'structure-unsupported')
        if rotate % 90 or not 0 < unit <= 75000:
            raise PdfaRefusal('structure-unsupported')
        record.extend((rotate, unit))
        result.append(tuple(record))
    return result


def export_pdfa(pdf: pikepdf.Pdf, source: bytes) -> PdfaResult:
    """Return an audited copy or a fixed refusal; never mutate the source bytes."""
    try:
        return _export(pdf, source)
    except PdfaRefusal:
        raise
    except (MemoryError, RecursionError):
        raise PdfaRefusal('limit') from None
    except Exception:
        raise PdfaRefusal('content-unsupported') from None


def _export(pdf: pikepdf.Pdf, source: bytes) -> PdfaResult:
    if len(source) > 50 * 1024 * 1024:
        raise PdfaRefusal('limit')
    if (not re.fullmatch(r'1\.[0-7]', pdf.pdf_version)
            or str(pdf.Root.get('/Version', '/1.7')) not in {'/1.' + str(n) for n in range(8)}):
        raise PdfaRefusal('pdf-version')
    audit = _Audit()
    if pdf.get_warnings():
        raise PdfaRefusal('structure-unsupported')
    audit.graph(pdf)
    _keys(pdf.Root, 'Type Pages Metadata OutputIntents Version')
    if pdf.Root.get('/Type') != pikepdf.Name.Catalog:
        raise PdfaRefusal('structure-unsupported')
    if not 0 < len(pdf.pages) <= MAX_PAGES:
        raise PdfaRefusal('limit')
    # Do not copy arbitrary metadata claims. Initially only absent XMP is supported.
    if '/Metadata' in pdf.Root:
        raise PdfaRefusal('metadata-unsupported')
    _keys(pdf.docinfo, 'Title Author Subject Keywords Creator Producer CreationDate ModDate Trapped', 'metadata-unsupported')
    for key, value in pdf.docinfo.items():
        if key == '/Trapped':
            if value != pikepdf.Name('/False'):
                raise PdfaRefusal('metadata-unsupported')
        elif not isinstance(value, pikepdf.String):
            raise PdfaRefusal('metadata-unsupported')
    notices = ['PDFA_METADATA_ADDED']
    if '/OutputIntents' in pdf.Root:
        intents = pdf.Root.OutputIntents
        if not isinstance(intents, pikepdf.Array) or len(intents) != 1:
            raise PdfaRefusal('color-unsupported')
        intent = intents[0]
        _keys(intent, 'Type S OutputConditionIdentifier Info RegistryName DestOutputProfile', 'color-unsupported')
        profile: Any = intent.get('/DestOutputProfile')
        _keys(profile, 'Length N Filter DecodeParms', 'color-unsupported')
        if (intent.get('/S') != pikepdf.Name.GTS_PDFA1 or profile.get('/N') != 3
                or audit.stream(profile) != ICC_DATA):
            raise PdfaRefusal('color-unsupported')
    else:
        notices.append('PDFA_OUTPUT_INTENT_ADDED')
    normalized = False
    for page in pdf.pages:
        _keys(page.obj, 'Type Parent Resources Contents MediaBox CropBox BleedBox TrimBox ArtBox Rotate UserUnit')
        # pikepdf resolves inherited resources on lookup, but serialize them explicitly.
        owner: Any = page.obj
        lineage: set[tuple[int, int]] = set()
        while '/Resources' not in owner:
            if owner.objgen in lineage or '/Parent' not in owner:
                raise PdfaRefusal('structure-unsupported')
            lineage.add(owner.objgen)
            owner = owner.Parent
            if len(lineage) > 64:
                raise PdfaRefusal('limit')
        resources = owner.Resources
        fonts = audit.resources(resources)
        audit.content(page, fonts, resources)
        if owner.objgen != page.obj.objgen:
            page.obj.Resources = resources
            normalized = True
    # Page tree dictionaries have a separate finite role, including shared resources.
    for obj in pdf.objects:
        if isinstance(obj, pikepdf.Dictionary) and obj.get('/Type') == pikepdf.Name.Pages:
            _keys(obj, 'Type Parent Kids Count Resources MediaBox CropBox Rotate')
    geometry = _geometry(pdf)
    if pdf.get_warnings():
        raise PdfaRefusal('content-unsupported')
    if normalized:
        notices.append('PDFA_RESOURCES_NORMALIZED')
    if '/OutputIntents' not in pdf.Root:
        profile = pdf.make_stream(ICC_DATA)
        profile.N = 3
        pdf.Root.OutputIntents = [pdf.make_indirect(pikepdf.Dictionary(
            Type=pikepdf.Name.OutputIntent, S=pikepdf.Name.GTS_PDFA1,
            OutputConditionIdentifier='sRGB2014', Info='sRGB2014',
            RegistryName='http://www.color.org', DestOutputProfile=profile))]
    with pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False, strict=True) as metadata:
        metadata.load_from_docinfo(pdf.docinfo)
        metadata['pdfaid:part'] = '2'
        metadata['pdfaid:conformance'] = 'B'
    output = _Output()
    pdf.save(output, force_version='1.7', object_stream_mode=pikepdf.ObjectStreamMode.generate,
             recompress_flate=True)
    data = output.getvalue()
    audit.tick()
    with pikepdf.open(io.BytesIO(data), attempt_recovery=False) as final:
        if (final.is_encrypted or final.pdf_version != '1.7' or _geometry(final) != geometry
                or '/ID' not in final.trailer or final.check_pdf_syntax()):
            raise PdfaRefusal('structure-unsupported')
    return PdfaResult(data, tuple(notices))
