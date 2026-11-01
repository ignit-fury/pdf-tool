"""Translate every top-level drawing item below a cut line down by `dy` points.

The primitive behind "a grown paragraph pushes the content below it down". Items are
moved, never redrawn: each moving item is bracketed by `X cm ... X^-1 cm`, where
`X = CTM . T(0,-dy) . CTM^-1`, so the item lands `dy` lower in default user space and
the graphics state after it is exactly what it was. Text objects that mix moving and
staying lines are split at a line boundary (`ET X cm BT <tlm> Tm`), which is safe
because text state survives `ET`/`BT` and only the line matrix needs restoring.

Unlike `engine.identity_rewrite` this never coalesces `/Contents` (`engine/rewrite.py`
Pitfall 3): run IDs and the native text box / managed image ownership proofs are
addressed by part index, so each changed part is replaced in place and owned parts are
left byte-identical. Parts are still walked as one concatenated stream, because
graphics and text state flow across part boundaries.

Every decision is made before the first write: a refusal leaves the page untouched.
"""
from __future__ import annotations

import math
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any, cast

import pikepdf

Matrix = tuple[float, float, float, float, float, float]
Instruction = pikepdf.ContentStreamInstruction | pikepdf.ContentStreamInlineImage
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
BACKGROUND_SHARE = 0.8
# AFM descender/ascender of the standard fonts, which carry no /FontDescriptor.
BASE14_METRICS = {'/Helvetica': (-0.207, 0.718), '/Arial': (-0.207, 0.718),
                  '/Times': (-0.217, 0.683), '/Courier': (-0.157, 0.629)}
_TRUNCATED_PARSE_WARNING = 'unexpected end of stream'

PATH_OPS = frozenset({'m', 'l', 'c', 'v', 'y', 'h', 're'})
PAINT_OPS = frozenset({'S', 's', 'f', 'F', 'f*', 'B', 'B*', 'b', 'b*', 'n'})
STROKE_OPS = frozenset({'S', 's', 'B', 'B*', 'b', 'b*'})
SHOW_OPS = frozenset({'Tj', 'TJ', "'", '"'})
POSITION_OPS = frozenset({'Td', 'TD', 'Tm', 'T*', "'", '"'})
# Operators that are illegal inside BT...ET and would break the line split.
NOT_IN_TEXT = PATH_OPS | PAINT_OPS | frozenset({'q', 'Q', 'cm', 'Do', 'sh', 'INLINE IMAGE', 'BT', 'W', 'W*'})


class PushDownRefused(ValueError):
    """`code` is one of PUSH_DOWN_STRADDLE, PUSH_DOWN_PAGE_FULL,
    PUSH_DOWN_MANAGED_IMAGE or PUSH_DOWN_UNSUPPORTED. Raised before any mutation."""

    def __init__(self, code: str, detail: str = '') -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail  # a structural reason for logs/tests; never document content


def _refuse(code: str = 'PUSH_DOWN_UNSUPPORTED', detail: str = '') -> PushDownRefused:
    return PushDownRefused(code, detail)


def _mul(a: Matrix, b: Matrix) -> Matrix:
    return (a[0]*b[0]+a[1]*b[2], a[0]*b[1]+a[1]*b[3], a[2]*b[0]+a[3]*b[2], a[2]*b[1]+a[3]*b[3],
            a[4]*b[0]+a[5]*b[2]+b[4], a[4]*b[1]+a[5]*b[3]+b[5])


def _inv(m: Matrix) -> Matrix:
    a, b, c, d, e, f = m
    det = a*d-b*c
    if not math.isfinite(det) or abs(det) < 1e-12:
        raise _refuse(detail='singular_ctm')
    return (d/det, -b/det, -c/det, a/det, (c*f-d*e)/det, (b*e-a*f)/det)


def _ys(m: Matrix, points: list[tuple[float, float]]) -> list[float]:
    return [m[1]*x+m[3]*y+m[5] for x, y in points]


def _matrix(values: Any) -> Matrix:
    numbers = [float(v) for v in values]
    if len(numbers) != 6 or not all(math.isfinite(v) for v in numbers):
        raise _refuse(detail='bad_matrix')
    return (numbers[0], numbers[1], numbers[2], numbers[3], numbers[4], numbers[5])


def _number(value: float) -> Decimal:
    text = f'{value:.10f}'.rstrip('0').rstrip('.')
    return Decimal('0' if text in ('', '-0') else text)


def _cm(m: Matrix) -> pikepdf.ContentStreamInstruction:
    return pikepdf.ContentStreamInstruction([_number(v) for v in m], pikepdf.Operator('cm'))


def _op(name: str, operands: list[Any] | None = None) -> pikepdf.ContentStreamInstruction:
    return pikepdf.ContentStreamInstruction(operands or [], pikepdf.Operator(name))


@dataclass
class _State:
    """The graphics state this module needs; copied on `q`."""
    ctm: Matrix = IDENTITY
    clip_lo: float = -math.inf     # y-range of the current clip, in default user space
    clip_hi: float = math.inf
    line_width: float = 1.0
    fill_pattern: bool = False     # pattern colours: pattern space ignores the CTM,
    stroke_pattern: bool = False   # so a moved item would slide over its pattern
    smask: bool = False            # a soft mask is active (mask space ignores later CTM)
    font_size: float = 0.0
    descent: float = -0.25         # of the current font, in em
    vertical: bool = False         # the current font writes top to bottom
    ascent: float = 1.0
    char_spacing: float = 0.0
    word_spacing: float = 0.0
    scale: float = 1.0
    leading: float = 0.0
    rise: float = 0.0
    render: int = 0


Pos = tuple[int, int]  # (content part, instruction index inside the part)


@dataclass
class _Plan:
    """Everything decided by the walk; applied only if nothing refused."""
    before: dict[Pos, list[pikepdf.ContentStreamInstruction]] = field(default_factory=dict)
    after: dict[Pos, list[pikepdf.ContentStreamInstruction]] = field(default_factory=dict)
    moved: int = 0
    lowest: float = math.inf  # lowest new bottom of a moved item that was visible
    straddle: str = ''  # kind of the first item crossing the cut
    managed_image: bool = False
    boxes: dict[str, list[float]] = field(default_factory=dict)  # native box id -> [lo, hi]
    # A page-spanning path that stays (frame, column rule, margin clip) bounds the
    # content inside it: pushing below its bottom would leave the frame or the clip.
    background_floor: float = -math.inf

    def insert(self, table: dict[Pos, list[pikepdf.ContentStreamInstruction]], pos: Pos,
               ops: list[pikepdf.ContentStreamInstruction]) -> None:
        table.setdefault(pos, []).extend(ops)


@dataclass
class _Line:
    first: int      # index into the block's instruction list of its first show op
    origin: Matrix  # text line matrix x CTM when the line starts
    last: int = 0
    advance: float = 0.0
    lo: float = math.inf
    hi: float = -math.inf


class _Walker:
    def __init__(self, page: pikepdf.Page, y_cut: float, dy: float,
                 parts: list[list[Instruction]], tags: list[str | None],
                 box: tuple[float, float]) -> None:
        self.y_cut, self.dy = y_cut, dy
        self.parts, self.tags = parts, tags
        self.crop_lo, crop_hi = box
        self.page_height = crop_hi-self.crop_lo
        self.plan = _Plan()
        resources = page.obj.get('/Resources')
        self.resources: pikepdf.Dictionary = resources if isinstance(resources, pikepdf.Dictionary) else pikepdf.Dictionary()

    # -- classification ---------------------------------------------------------------
    def _classify(self, kind: str, lo: float, hi: float, tag: str | None, background: bool,
                  state: _State) -> bool:
        """Record the item's fate; True when it must move."""
        if not lo <= hi:
            return False  # draws nothing measurable (e.g. an empty text line)
        if tag is not None:
            if tag == 'image':
                self.plan.managed_image |= lo < self.y_cut
            else:
                span = self.plan.boxes.setdefault(tag, [math.inf, -math.inf])
                span[0], span[1] = min(span[0], lo), max(span[1], hi)
            return False
        if lo >= self.y_cut:
            return False
        if hi > self.y_cut:
            if background and hi-lo > BACKGROUND_SHARE*self.page_height:
                self.plan.background_floor = max(self.plan.background_floor, lo)
                return False
            self.plan.straddle = self.plan.straddle or kind
            return False
        if state.fill_pattern or state.stroke_pattern or state.smask:
            raise _refuse(detail='pattern_or_smask')
        if hi > self.crop_lo:  # content already wholly off the page may move further off
            self.plan.lowest = min(self.plan.lowest, lo-self.dy)
        self.plan.moved += 1
        return True

    def _move(self, ctm: Matrix, start: Pos, end: Pos) -> None:
        self.plan.insert(self.plan.before, start, [_cm(self._shift(ctm, -self.dy))])
        self.plan.insert(self.plan.after, end, [_cm(self._shift(ctm, self.dy))])

    @staticmethod
    def _shift(ctm: Matrix, dy: float) -> Matrix:
        x = _mul(_mul(ctm, (1.0, 0.0, 0.0, 1.0, 0.0, dy)), _inv(ctm))
        if abs(x[0]-1) < 1e-9 and abs(x[3]-1) < 1e-9 and abs(x[1]) < 1e-9 and abs(x[2]) < 1e-9:
            x = (1.0, 0.0, 0.0, 1.0, x[4], x[5])  # keep pure translations exact
        return x

    # -- resources --------------------------------------------------------------------
    def _resource(self, category: str, name: object) -> Any:
        group = self.resources.get(category)
        if not isinstance(group, pikepdf.Dictionary) or not isinstance(name, pikepdf.Name):
            return None
        return group.get(name)

    def _is_pattern_space(self, name: object) -> bool:
        if name == pikepdf.Name.Pattern:
            return True
        space = self._resource('/ColorSpace', name)
        if isinstance(space, pikepdf.Array) and len(space):
            space = space[0]
        return bool(space == pikepdf.Name.Pattern)

    def _vertical(self, name: object) -> bool:
        """A Type0 font in vertical writing mode (`-V` CMap or /WMode 1)."""
        font = self._resource('/Font', name)
        if not isinstance(font, pikepdf.Dictionary) or font.get('/Subtype') != pikepdf.Name.Type0:
            return False
        encoding = font.get('/Encoding')
        if isinstance(encoding, pikepdf.Name):
            return str(encoding).endswith('-V')
        return isinstance(encoding, pikepdf.Stream) and encoding.get('/WMode') == 1

    def _font_extent(self, name: object) -> tuple[float, float]:
        """Descent/ascent in em: the font's own claim, never beyond -0.25..1.0 em.

        At 1.2 leading a fixed -0.25..1.0 em box overlaps the next line, so nearly
        every cut between lines would straddle. Tightening cannot create overlap: an
        item moves or stays whole, and moving down only separates it from what stays.
        It does not cover ink beyond the font's claim (accents above the ascender, a
        deep descender): such ink may cross the cut without the line being refused.
        """
        font = self._resource('/Font', name)
        if not isinstance(font, pikepdf.Dictionary) or font.get('/Subtype') == pikepdf.Name.Type3:
            return -0.25, 1.0
        base = str(font.get('/BaseFont', ''))
        if font.get('/Subtype') == pikepdf.Name.Type0:
            descendants = font.get('/DescendantFonts')
            font = descendants[0] if isinstance(descendants, pikepdf.Array) and len(descendants) else font
        descriptor = font.get('/FontDescriptor') if isinstance(font, pikepdf.Dictionary) else None
        metrics: tuple[float, float] | None = None
        if isinstance(descriptor, pikepdf.Dictionary):
            try:
                metrics = (float(cast(Any, descriptor.get('/Descent')))/1000,
                           float(cast(Any, descriptor.get('/Ascent')))/1000)
            except (TypeError, ValueError):
                metrics = None
        else:
            metrics = next((m for prefix, m in BASE14_METRICS.items() if base.startswith(prefix)), None)
        if metrics is None or not (-1 <= metrics[0] <= 0 < metrics[1] <= 2):
            return -0.25, 1.0
        return max(metrics[0], -0.25), min(metrics[1], 1.0)

    def _xobject_ys(self, name: object, ctm: Matrix) -> list[float]:
        xobject = self._resource('/XObject', name)
        if not isinstance(xobject, pikepdf.Stream):
            raise _refuse(detail='bad_xobject')
        subtype = xobject.get('/Subtype')
        if subtype == pikepdf.Name.Image:
            return _ys(ctm, [(0, 0), (1, 0), (0, 1), (1, 1)])
        if subtype != pikepdf.Name.Form:
            raise _refuse(detail='bad_xobject')
        bbox = xobject.get('/BBox')
        if not isinstance(bbox, pikepdf.Array) or len(bbox) != 4:
            raise _refuse(detail='bad_xobject')
        x0, y0, x1, y1 = (float(v) for v in bbox)
        matrix = xobject.get('/Matrix')
        m = _mul(_matrix(matrix), ctm) if matrix is not None else ctm
        return _ys(m, [(x0, y0), (x1, y0), (x0, y1), (x1, y1)])

    # -- walk -------------------------------------------------------------------------
    def walk(self) -> _Plan:
        flat: list[Pos] = [(p, i) for p, ops in enumerate(self.parts) for i in range(len(ops))]
        state = _State()
        stack: list[_State] = []
        k = 0
        while k < len(flat):
            pos = flat[k]
            ins = self.parts[pos[0]][pos[1]]
            op, args = str(ins.operator), list(ins.operands)
            tag = self.tags[pos[0]]
            if op == 'q':
                stack.append(replace(state))
            elif op == 'Q':
                if not stack:
                    raise _refuse(detail='q_underflow')
                state = stack.pop()
            elif op == 'cm':
                state.ctm = _mul(_matrix(args), state.ctm)
            elif op == 'BT':
                k = self._text(flat, k, state, tag)
            elif op in PATH_OPS:
                k = self._path(flat, k, state, tag)
            elif op == 'Do':
                ys = self._xobject_ys(args[0] if args else None, state.ctm)
                if self._classify('xobject', min(ys), max(ys), tag, False, state):
                    self._move(state.ctm, pos, pos)
            elif op == 'INLINE IMAGE':
                ys = _ys(state.ctm, [(0, 0), (1, 0), (0, 1), (1, 1)])
                if self._classify('inline_image', min(ys), max(ys), tag, False, state):
                    self._move(state.ctm, pos, pos)
            elif op == 'sh':
                # A shading fills the clip; as an item it is as wide as the clip region.
                lo, hi = max(state.clip_lo, self.crop_lo), min(state.clip_hi, self.crop_lo+self.page_height)
                if self._classify('shading', lo, hi, tag, True, state):
                    self._move(state.ctm, pos, pos)
            elif op in ('ET', 'W', 'W*') or op in PAINT_OPS:
                raise _refuse(detail='stray_operator')  # outside its construct: the stream is not well formed
            else:
                self._state_op(op, args, state)
            k += 1
        return self.plan

    def _state_op(self, op: str, args: list[Any], state: _State) -> None:
        if op == 'w' and args:
            state.line_width = abs(float(args[0]))
        elif op == 'cs' and args:
            state.fill_pattern = self._is_pattern_space(args[0])
        elif op == 'CS' and args:
            state.stroke_pattern = self._is_pattern_space(args[0])
        elif op == 'gs' and args:
            ext = self._resource('/ExtGState', args[0])
            if isinstance(ext, pikepdf.Dictionary):
                smask = ext.get('/SMask')
                if smask is not None:
                    state.smask = smask != pikepdf.Name('/None')
                if '/Font' in ext:
                    raise _refuse(detail='gs_font')  # font size we cannot track cheaply
        elif op == 'Tf' and len(args) == 2:
            state.font_size = float(args[1])
            state.descent, state.ascent = self._font_extent(args[0])
            state.vertical = self._vertical(args[0])
        elif op == 'Tc' and args:
            state.char_spacing = float(args[0])
        elif op == 'Tw' and args:
            state.word_spacing = float(args[0])
        elif op == 'Tz' and args:
            state.scale = float(args[0])/100
        elif op == 'TL' and args:
            state.leading = float(args[0])
        elif op == 'Ts' and args:
            state.rise = float(args[0])
        elif op == 'Tr' and args:
            state.render = int(args[0])

    def _path(self, flat: list[Pos], k: int, state: _State, tag: str | None) -> int:
        start = flat[k]
        ys: list[float] = []
        clip = False
        while True:
            if k >= len(flat):
                raise _refuse(detail='open_path')
            pos = flat[k]
            if self.tags[pos[0]] != tag:
                raise _refuse(detail='item_crosses_owned_part')  # an item must not cross into or out of an owned part
            ins = self.parts[pos[0]][pos[1]]
            op = str(ins.operator)
            if op in PAINT_OPS:
                break
            if op in ('W', 'W*'):
                clip = True
            elif op in PATH_OPS:
                v = [float(x) for x in ins.operands]
                if op == 're' and len(v) == 4:
                    ys += _ys(state.ctm, [(v[0], v[1]), (v[0], v[1]+v[3])])
                else:
                    ys += _ys(state.ctm, [(v[i], v[i+1]) for i in range(0, len(v)-1, 2)])
            else:
                raise _refuse(detail='operator_in_path')
            k += 1
        end = flat[k]
        paint = str(self.parts[end[0]][end[1]].operator)
        if not ys or paint == 'n' and not clip:
            return k  # draws nothing
        lo, hi = min(ys), max(ys)
        # Only a page-spanning path with no interior vertex below the cut can stay
        # behind moving content: a table grid's row rules would be left behind.
        background = all(y >= self.y_cut for y in ys if lo+1 < y < hi-1)
        if paint in STROKE_OPS:
            a, b, c, d = state.ctm[:4]
            pad = state.line_width*math.sqrt(abs(a*d-b*c))/2 if state.line_width else 0.5
            lo, hi = lo-pad, hi+pad
        moving = self._classify('path', lo, hi, tag, background, state)
        if moving:
            self._move(state.ctm, start, end)
        if clip:  # original geometry, like every other extent; a moved clip moves its shading
            state.clip_lo, state.clip_hi = max(state.clip_lo, lo), min(state.clip_hi, hi)
        return k

    def _text(self, flat: list[Pos], k: int, state: _State, tag: str | None) -> int:
        """One BT...ET block: measure each line, then split around moving groups."""
        begin = k
        block: list[Pos] = []
        tlm_before: list[Matrix] = []
        depth_before: list[int] = []
        lines: list[_Line] = []
        tlm = IDENTITY
        depth = 0
        clipping = state.render >= 4
        new_line = True
        k += 1
        while True:
            if k >= len(flat):
                raise _refuse(detail='open_text')
            pos = flat[k]
            if self.tags[pos[0]] != tag:
                raise _refuse(detail='text_crosses_owned_part')
            ins = self.parts[pos[0]][pos[1]]
            op, args = str(ins.operator), list(ins.operands)
            if op == 'ET':
                break
            if op in NOT_IN_TEXT:
                raise _refuse(detail='operator_in_text')
            index = len(block)
            block.append(pos)
            tlm_before.append(tlm)
            depth_before.append(depth)
            if op in ('BDC', 'BMC'):
                depth += 1
            elif op == 'EMC':
                depth -= 1
            elif op == '"' and len(args) == 3:
                state.word_spacing, state.char_spacing = float(args[0]), float(args[1])
            if op in ('Td', 'TD') and len(args) == 2:
                tx, ty = float(args[0]), float(args[1])
                if op == 'TD':
                    state.leading = -ty
                tlm = _mul((1.0, 0.0, 0.0, 1.0, tx, ty), tlm)
            elif op == 'Tm':
                tlm = _matrix(args)
            elif op in ("T*", "'", '"'):
                tlm = _mul((1.0, 0.0, 0.0, 1.0, 0.0, -state.leading), tlm)
            new_line |= op in POSITION_OPS
            if op in SHOW_OPS:
                if new_line:
                    lines.append(_Line(index, _mul(tlm, state.ctm)))
                    new_line = False
                if state.vertical:
                    raise _refuse(detail='vertical_text')  # lines run down the page, not across
                line = lines[-1]
                line.last = index
                line.advance += self._advance(op, args, state)
                size = abs(state.font_size)
                # Every show on the line is bounded by [origin, origin + summed advance].
                ys = _ys(line.origin, [(x, y) for x in (0.0, line.advance)
                                       for y in (state.rise+state.descent*size, state.rise+state.ascent*size)])
                line.lo, line.hi = min(line.lo, *ys), max(line.hi, *ys)
            else:
                self._state_op(op, args, state)
            clipping |= state.render >= 4
            k += 1
        end = flat[k]
        if depth:
            raise _refuse(detail='marked_content_open')
        moving = [self._classify('text', line.lo, line.hi, tag, False, state) for line in lines]
        if not any(moving):
            return k
        if all(moving):
            self._move(state.ctm, flat[begin], end)
            return k
        if clipping:
            raise _refuse(detail='clip_text_split')
        down, up = self._shift(state.ctm, -self.dy), self._shift(state.ctm, self.dy)
        for i, move in enumerate(moving):
            starts = move and (i == 0 or not moving[i-1])
            ends = move and (i == len(lines)-1 or not moving[i+1])
            if starts:
                if i == 0:
                    self.plan.insert(self.plan.before, flat[begin], [_cm(down)])
                else:
                    self._split(block, tlm_before, depth_before, lines[i-1].last, lines[i].first, down)
            if ends:
                if i == len(lines)-1:
                    self.plan.insert(self.plan.after, end, [_cm(up)])
                else:
                    self._split(block, tlm_before, depth_before, lines[i].last, lines[i+1].first, up)
        return k

    def _split(self, block: list[Pos], tlm_before: list[Matrix], depth_before: list[int],
               last_show: int, next_show: int, shift: Matrix) -> None:
        """Close and reopen the text object between two lines, outside marked content."""
        for index in range(next_show, last_show, -1):
            if depth_before[index] == 0:
                tlm = tlm_before[index]
                self.plan.insert(self.plan.before, block[index], [
                    _op('ET'), _cm(shift), _op('BT'), _op('Tm', [_number(v) for v in tlm])])
                return
        raise _refuse(detail='split_in_marked_content')

    @staticmethod
    def _advance(op: str, args: list[Any], state: _State) -> float:
        """Upper bound of the text-space advance of one show operator.

        shortcut: assumes no glyph is wider than 1 em per code byte; only rotated text's
        y-extent depends on it. Measure real widths if rotated captions get refused.
        """
        size, scale = abs(state.font_size), abs(state.scale)
        per_byte = (size+abs(state.char_spacing)+abs(state.word_spacing))*scale
        operands = args[-1:] if op in ("'", '"', 'Tj') else (list(args[0]) if args else [])
        total = 0.0
        for item in operands:
            if isinstance(item, (pikepdf.String, bytes)):
                total += len(bytes(item))*per_byte
            else:
                total += abs(float(item))/1000*size*scale
        return total


def _box(page: pikepdf.Page) -> tuple[float, float]:
    """The visible y-range: the cropbox clipped to the mediabox."""
    crop = [float(v) for v in page.cropbox]
    media = [float(v) for v in page.mediabox]
    lo = max(min(crop[1], crop[3]), min(media[1], media[3]))
    hi = min(max(crop[1], crop[3]), max(media[1], media[3]))
    if not lo < hi:
        raise _refuse(detail='empty_page_box')
    return lo, hi


def _parse(data: bytes) -> tuple[list[Instruction], bool]:
    """Instructions of one content part, and whether its tail was cut off mid-instruction."""
    with pikepdf.Pdf.new() as scratch:
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always')
                parsed: list[Instruction] = list(pikepdf.parse_content_stream(pikepdf.Stream(scratch, data)))
        except pikepdf.PdfError:
            raise _refuse(detail='parse_failure') from None
    return parsed, any(_TRUNCATED_PARSE_WARNING in str(w.message).lower() for w in caught)


def _parse_parts(contents: list[pikepdf.Object], tags: list[str | None]) -> tuple[list[list[Instruction]], list[int]]:
    """Parse each part with its full operands, even when a producer split an instruction
    across two parts (`engine/rewrite.py`: legal, and 20% of corpus page 0s).

    The operator decides which part an instruction belongs to; a part parsed alone gives
    exactly those operators, the whole page parsed at once gives their operands. Returns
    the parts and each truncated part index: rewriting part p or p+1 then rewrites both.
    """
    raw = [stream.read_bytes() for stream in contents]
    alone = [_parse(data) for data in raw]
    truncated = [p for p, (_, cut) in enumerate(alone) if cut]
    if not truncated:
        return [ops for ops, _ in alone], []
    joined, cut = _parse(b'\n'.join(raw))
    if cut or len(joined) != sum(len(ops) for ops, _ in alone):
        raise _refuse(detail='part_boundary_split')
    parts: list[list[Instruction]] = []
    for ops, _ in alone:
        chunk, joined = joined[:len(ops)], joined[len(ops):]
        if [str(i.operator) for i in chunk] != [str(i.operator) for i in ops]:
            raise _refuse(detail='part_boundary_split')
        parts.append(chunk)
    if any(p+1 >= len(parts) or tags[p] is not None or tags[p+1] is not None for p in truncated):
        raise _refuse(detail='part_boundary_split')
    return parts, truncated


def _owned_ids(pdf: pikepdf.Pdf, page_index: int, contents: list[pikepdf.Object]) -> dict[tuple[int, int], str]:
    if not any('/NativeTextBox' in stream for stream in contents):
        return {}
    from engine.text_boxes import TextBoxError, _owned
    try:
        return {stream.objgen: str(spec['id']) for spec, stream in _owned(pdf, page_index)}
    except TextBoxError:
        raise _refuse(detail='native_box_unverified') from None


def _annotation_moves(pdf: pikepdf.Pdf, page: pikepdf.Page, y_cut: float, dy: float, crop_lo: float,
                      plan: _Plan) -> list[tuple[pikepdf.Dictionary, dict[str, pikepdf.Array]]]:
    """New geometry for every annotation wholly below the cut."""
    annots = page.obj.get('/Annots')
    if not isinstance(annots, pikepdf.Array):
        return []
    result: list[tuple[pikepdf.Dictionary, dict[str, pikepdf.Array]]] = []
    for annot in annots:
        if not isinstance(annot, pikepdf.Dictionary):
            continue
        rect = annot.get('/Rect')
        if not isinstance(rect, pikepdf.Array) or len(rect) != 4:
            continue
        lo, hi = sorted((float(rect[1]), float(rect[3])))
        if lo >= y_cut:
            continue
        if hi > y_cut:
            plan.straddle = plan.straddle or 'annotation'
            continue
        if hi > crop_lo:
            plan.lowest = min(plan.lowest, lo-dy)
        changes: dict[str, pikepdf.Array] = {}
        for key in ('/Rect', '/QuadPoints', '/Vertices', '/L', '/CL'):
            value = annot.get(key)
            if isinstance(value, pikepdf.Array):
                changes[key] = pikepdf.Array([_number(float(v)-dy) if i % 2 else v for i, v in enumerate(value)])
        ink = annot.get('/InkList')
        if isinstance(ink, pikepdf.Array):
            changes['/InkList'] = pikepdf.Array([
                pikepdf.Array([_number(float(v)-dy) if i % 2 else v for i, v in enumerate(stroke)])
                for stroke in ink if isinstance(stroke, pikepdf.Array)])
        result.append((annot, changes))
    if any(annot.is_indirect for annot, _ in result):
        here = page.obj.objgen
        elsewhere: set[tuple[int, int]] = set()
        for other in pdf.pages:
            others = other.obj.get('/Annots')
            if other.obj.objgen != here and isinstance(others, pikepdf.Array):
                elsewhere |= {annot.objgen for annot in others if annot.is_indirect}
        if any(annot.is_indirect and annot.objgen in elsewhere for annot, _ in result):
            raise _refuse(detail='shared_annotation')  # moving it would move another page's link
    return result


def push_down(pdf: pikepdf.Pdf, page_index: int, y_cut: float, dy: float, *,
              keep: Callable[[str], bool] = lambda _: False) -> int:
    """Translate every top-level drawing item whose top lies at or below `y_cut`
    (default user space, PDF y-up) down by `dy` points. Mutates the page in place and
    returns the number of moved items. Raises PushDownRefused without mutating anything.

    Native text boxes are never moved here: each one not wholly above the cut is passed
    to `keep(id)`, and the caller must return True to take responsibility for it (Task 2
    re-upserts it lower). A box that crosses the cut refuses with PUSH_DOWN_STRADDLE,
    and one the caller does not keep refuses with PUSH_DOWN_UNSUPPORTED. `keep` is
    called only after every other check has passed, and only for boxes wholly below.
    """
    if not (math.isfinite(y_cut) and math.isfinite(dy) and dy > 0):
        raise ValueError('y_cut must be finite and dy positive')
    page = pdf.pages[page_index]
    try:
        return _push_down(pdf, page_index, page, y_cut, dy, keep)
    except PushDownRefused:
        raise
    except (TypeError, ValueError, IndexError):
        # Malformed operands or dictionaries; raised before the first write.
        raise _refuse(detail='bad_operand') from None


def _push_down(pdf: pikepdf.Pdf, page_index: int, page: pikepdf.Page, y_cut: float, dy: float,
               keep: Callable[[str], bool]) -> int:
    if int(page.obj.get('/Rotate', 0)) % 360:
        raise _refuse(detail='rotated_page')  # "down" would not be -y on screen
    raw = page.obj.get('/Contents')
    contents: list[pikepdf.Object] = (list(raw) if isinstance(raw, pikepdf.Array)
                                      else [] if raw is None else [raw])
    if not all(isinstance(stream, pikepdf.Stream) for stream in contents):
        raise _refuse(detail='bad_contents')
    owned = _owned_ids(pdf, page_index, contents)
    tags: list[str | None] = []
    for stream in contents:
        if '/PdfToolImage' in stream:
            tags.append('image')
        elif '/NativeTextBox' in stream:
            tags.append('box:'+owned[stream.objgen])
        else:
            tags.append(None)
    parts, truncated = _parse_parts(contents, tags)
    crop = _box(page)
    plan = _Walker(page, y_cut, dy, parts, tags, crop).walk()
    annotations = _annotation_moves(pdf, page, y_cut, dy, crop[0], plan)
    below = [tag[4:] for tag, (lo, hi) in plan.boxes.items() if lo < y_cut]
    if any(hi > y_cut for lo, hi in plan.boxes.values() if lo < y_cut):
        plan.straddle = plan.straddle or 'native_text_box'
    if plan.managed_image:
        raise _refuse('PUSH_DOWN_MANAGED_IMAGE')
    if plan.straddle:
        raise _refuse('PUSH_DOWN_STRADDLE', plan.straddle)
    if plan.lowest < max(crop[0], plan.background_floor):
        raise _refuse('PUSH_DOWN_PAGE_FULL', 'page' if plan.lowest < crop[0] else 'background')
    if not all([keep(box) for box in below]):  # every id is reported, even after a False
        raise _refuse(detail='native_box_not_kept')

    # Apply: nothing below can refuse.
    replaced: dict[int, bytes] = {}
    touched = {pos[0] for pos in (*plan.before, *plan.after)}
    grown = True
    while grown:  # a split instruction ties both of its parts' bytes together
        grown = False
        for p in truncated:
            if (p in touched) != (p+1 in touched):
                touched |= {p, p+1}
                grown = True
    for p in sorted(touched):
        out: list[Instruction] = []
        for i, ins in enumerate(parts[p]):
            out += plan.before.get((p, i), [])
            out.append(ins)
            out += plan.after.get((p, i), [])
        replaced[p] = pikepdf.unparse_content_stream(out)
    if replaced:
        if isinstance(raw, pikepdf.Array):
            page.obj.Contents = pikepdf.Array([pdf.make_stream(replaced[p]) if p in replaced else s
                                               for p, s in enumerate(contents)])
        else:
            page.obj.Contents = pdf.make_stream(replaced[0])
    for annot, changes in annotations:
        for key, value in changes.items():
            annot[key] = value
    return plan.moved+len(annotations)
