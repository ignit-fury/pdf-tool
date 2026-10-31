"""Bounded transparent native text containers with independently verified ownership.

Only this module's exact deterministic drawing and bundled font graph are editable.
Metadata alone never grants permission to remove a content stream.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, replace
from decimal import Decimal
import hashlib
import io
import json
import math
import re
import secrets
import unicodedata
import zlib
from typing import Any, NoReturn, cast

import pikepdf
import pypdfium2 as pdfium  # type: ignore[import-untyped]
from fontTools.ttLib import TTFont

from engine.fonts import (
    BundledFamily, BundledVariant, embed_type0_font, has_unmapped_glyph,
    shape_cids, shape_glyph_names, subset_cid_widths, subset_font_for_family,
    substitution_unicode_reason,
)

ERROR_CODES = frozenset({'INVALID_TEXT_BOX', 'TEXT_BOX_UNSUPPORTED_TEXT',
    'TEXT_BOX_UNSAFE', 'TEXT_BOX_NOT_FOUND', 'TEXT_BOX_OVERLAP',
    'TEXT_BOX_LIMIT', 'TEXT_BOX_OUTPUT_LIMIT', 'TEXT_BOX_SOURCE_UNSAFE',
    'PARAGRAPH_STALE'})
MAX_DECODED = 1024 * 1024
MAX_METADATA = 128 * 1024
MAX_OUTPUT = 48 * 1024 * 1024
MAX_TEXT_BOX_PAGES = 2048
DEFAULT_STYLE: dict[str, object] = dict(font_family='Sans', font_size=12, bold=False,
    italic=False, color=[0,0,0], character_spacing=0, line_spacing=1.2,
    paragraph_spacing=0, alignment='left')
RUN_STYLE_KEYS = ('font_family','bold','italic','font_size','color')


class TextBoxError(ValueError):
    def __init__(self, code: str) -> None:
        if code not in ERROR_CODES:
            raise ValueError('unknown text-box error')
        self.code = code
        super().__init__(code)


def _fail(code: str = 'INVALID_TEXT_BOX') -> NoReturn:
    raise TextBoxError(code)


def _number(value: object, low: float, high: float) -> float:
    if type(value) not in (float, int):
        _fail()
    result = float(cast(float, value))
    if not math.isfinite(result) or not low <= result <= high:
        _fail()
    return result


def _dict(value: object, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or any(type(k) is not str or k not in keys for k in value):
        _fail()
    return cast(dict[str, Any], value)


def _identifier(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r'[a-f0-9]{32}', value) is None:
        _fail()
    return value


def _spec(payload: dict[str, Any], count: int) -> dict[str, Any]:
    page = payload.get('page_index')
    if type(page) is not int or not 0 <= page < count:
        _fail()
    text = payload.get('text')
    if not isinstance(text, str) or not 1 <= len(text) <= 10000:
        _fail()
    rect = _dict(payload.get('rect'), {'left','top','width','height'})
    if set(rect) != {'left','top','width','height'}:
        _fail()
    normalized_rect = {k: _number(v, 0 if k in ('left','top') else .01, 144000)
                       for k,v in rect.items()}
    style = dict(DEFAULT_STYLE)
    supplied = _dict(payload.get('style', {}), set(style) | {'initial_font_size'})
    style.update(supplied)
    if style['font_family'] not in ('Sans','Serif','Mono') or style['alignment'] not in ('left','center','right'):
        _fail()
    for key in ('bold','italic'):
        if type(style[key]) is not bool:
            _fail()
    for key,lo,hi in [('font_size',1,512),('character_spacing',0,10),
                      ('line_spacing',1,3),('paragraph_spacing',0,144)]:
        style[key] = _number(style[key],lo,hi)
    if 'initial_font_size' in supplied:
        style['initial_font_size'] = _number(supplied['initial_font_size'],1,512)
    color = style['color']
    if not isinstance(color,list) or len(color) != 3:
        _fail()
    style['color'] = [_number(c,0,1) for c in color]
    result = dict(id=_identifier(payload['id']) if 'id' in payload else secrets.token_hex(16),
                  page_index=page, rect=normalized_rect, text=text, style=style)
    if 'runs' in payload:
        runs = payload['runs']
        if 'initial_font_size' in supplied or not isinstance(runs, list) or not 1 <= len(runs) <= 512:
            _fail()
        merged: list[dict[str, Any]] = []
        for run in runs:
            if set(_dict(run, {'text','style'})) != {'text','style'} or not isinstance(run['text'], str) or not run['text']:
                _fail()
            run_style = {k: style[k] for k in RUN_STYLE_KEYS}
            run_style.update(_dict(run['style'], set(RUN_STYLE_KEYS)))
            if run_style['font_family'] not in ('Sans','Serif','Mono') or type(run_style['bold']) is not bool or type(run_style['italic']) is not bool:
                _fail()
            run_style['font_size'] = _number(run_style['font_size'],1,512)
            run_color = run_style['color']
            if not isinstance(run_color,list) or len(run_color) != 3:
                _fail()
            run_style['color'] = [_number(c,0,1) for c in run_color]
            merged.append(dict(text=run['text'], style=run_style))
        if ''.join(r['text'] for r in merged) != text:
            _fail()
        result['runs'] = merged
    return result


@dataclass(frozen=True)
class Geometry:
    matrix: tuple[float,float,float,float,float,float]
    width: float
    height: float
    unit: float

    def visible(self, x: float, y: float) -> tuple[float,float]:
        a,b,c,d,e,f = self.matrix
        det=a*d-b*c
        return ((d*(x-e)-c*(y-f))/det, -(-b*(x-e)+a*(y-f))/det)


def _geometry(page: pikepdf.Page) -> Geometry:
    try:
        media = [float(v) for v in page.mediabox]
        crop = [float(v) for v in page.cropbox]
        x0,y0=max(media[0],crop[0]),max(media[1],crop[1])
        x1,y1=min(media[2],crop[2]),min(media[3],crop[3])
        unit=float(page.obj.get('/UserUnit',1))
        rotation=float(page.obj.get('/Rotate',0))
        if not all(math.isfinite(v) for v in (*media,*crop,unit,rotation)) or not .01 <= unit <= 75000 or rotation % 90 or x1<=x0 or y1<=y0:
            _fail('TEXT_BOX_UNSAFE')
        r=int(rotation)%360
        s=1/unit
        matrix={0:(s,0.,0.,s,x0,y1),90:(0.,s,-s,0.,x0,y0),
                180:(-s,0.,0.,-s,x1,y0),270:(0.,-s,s,0.,x1,y1)}[r]
        w,h=(x1-x0)*unit,(y1-y0)*unit
        if r in (90,270):
            w,h=h,w
        if max(w,h)>144000:
            _fail('TEXT_BOX_LIMIT')
        return Geometry(matrix,w,h,unit)
    except (TypeError,ValueError,IndexError,OverflowError,pikepdf.PdfError):
        _fail('TEXT_BOX_UNSAFE')
    raise AssertionError


def _decoded(stream: pikepdf.Object, limit: int = MAX_DECODED) -> bytes:
    if not isinstance(stream,pikepdf.Stream):
        _fail('TEXT_BOX_UNSAFE')
    raw=stream.read_raw_bytes()
    if len(raw)>limit:
        _fail('TEXT_BOX_LIMIT')
    filt=stream.get('/Filter')
    if filt is None:
        return raw
    if isinstance(filt,pikepdf.Array) and len(filt)==1:
        filt=filt[0]
    if filt != pikepdf.Name.FlateDecode or stream.get('/DecodeParms') is not None:
        _fail('TEXT_BOX_UNSAFE')
    try:
        decoder=zlib.decompressobj()
        result=decoder.decompress(raw,limit+1)
        if len(result)>limit or decoder.unconsumed_tail or not decoder.eof or decoder.unused_data:
            _fail('TEXT_BOX_UNSAFE')
        return result
    except zlib.error:
        _fail('TEXT_BOX_UNSAFE')
    raise AssertionError


def _contents(page: pikepdf.Page) -> list[pikepdf.Object]:
    contents=page.obj.get('/Contents')
    if contents is None:
        return []
    result=list(contents) if isinstance(contents,pikepdf.Array) else [contents]
    if len(result)>4096 or any(not isinstance(s,pikepdf.Stream) for s in result):
        _fail('TEXT_BOX_UNSAFE')
    return result


def _canonical(obj: object, depth: int = 0, budget: list[int] | None = None) -> object:
    """Hash font meaning, including bounded decoded programs, independent of objgens."""
    if budget is None:
        budget=[10000]
    budget[0]-=1
    if depth>12 or budget[0]<0:
        _fail('TEXT_BOX_UNSAFE')
    if isinstance(obj,pikepdf.Stream):
        return ['stream',_decoded(obj).hex(),{str(k):_canonical(v,depth+1,budget)
                for k,v in sorted(obj.items()) if str(k) not in ('/Length','/Filter','/DecodeParms')}]
    if isinstance(obj,pikepdf.Dictionary):
        return ['dictionary',{str(k):_canonical(v,depth+1,budget) for k,v in sorted(obj.items())}]
    if isinstance(obj,pikepdf.Array):
        return ['array',[_canonical(v,depth+1,budget) for v in obj]]
    if isinstance(obj,pikepdf.Name):
        return ['name',str(obj)]
    if isinstance(obj,pikepdf.String):
        return ['string',bytes(obj).hex()]
    if isinstance(obj,(int,float,Decimal)) and not isinstance(obj,bool):
        return ['number',round(float(obj),6)]
    if obj is None:
        return ['null']
    if isinstance(obj,bool):
        return ['boolean',obj]
    _fail('TEXT_BOX_UNSAFE')


def _json(value: object) -> bytes:
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()


@dataclass
class Drawing:
    stream: bytes
    fonts: dict[str,pikepdf.Object]
    layout: dict[str,object]


@dataclass
class _Face:
    subset: Any
    widths: dict[int,float]
    chars: dict[str,int]
    font: Any
    bounds: dict[str,tuple[float,float,float,float]]


def _drawing(pdf: pikepdf.Pdf, spec: dict[str,Any], geometry: Geometry) -> Drawing:
    text=cast(str,spec['text'])
    style=spec['style']; rect=spec['rect']
    styled='runs' in spec
    # The single-style box is the one-run case; its arithmetic is kept exactly.
    runs=cast(list[dict[str,Any]],spec['runs']) if styled else [dict(text=text,style=style)]
    if any(ch!='\n' and (unicodedata.category(ch)[0]=='C' or unicodedata.combining(ch) or unicodedata.bidirectional(ch) in ('R','AL','AN')) for ch in text):
        _fail('TEXT_BOX_UNSUPPORTED_TEXT')
    keys: dict[tuple[BundledFamily,BundledVariant],list[str]]={}
    # Per character: (face, glyph size, colour, is-initial-letter).
    cells: list[tuple[int,float,list[float],bool]]=[]
    for run in runs:
        run_text=cast(str,run['text']); run_style=run['style']
        family=cast(BundledFamily,run_style['font_family'])
        variant=cast(BundledVariant,('Bold' if run_style['bold'] else '')+('Italic' if run_style['italic'] else '') or 'Regular')
        if has_unmapped_glyph(family,variant,run_text.replace('\n','')) or substitution_unicode_reason(family,variant,tuple(run_text.split('\n'))) is not None:
            _fail('TEXT_BOX_UNSUPPORTED_TEXT')
        if (family,variant) not in keys:
            keys[(family,variant)]=[]
        keys[(family,variant)].extend(run_text.split('\n'))
        face=list(keys).index((family,variant))
        cells.extend((face,run_style['font_size'],run_style['color'],False) for _ in run_text)
    size=style['font_size']; spacing=style['character_spacing']
    initial_size=style.get('initial_font_size')
    first=next((i for i,ch in enumerate(text) if ch!='\n'),None)
    if initial_size is not None and first is not None:
        cells[first]=(0,initial_size,style['color'],True)
    faces: list[_Face]=[]
    for (family,variant),paragraphs in keys.items():
        names=frozenset(name for paragraph in paragraphs for name in shape_glyph_names(family,variant,paragraph))
        if not names:
            names=frozenset(shape_glyph_names(family,variant,' '))
        subset=subset_font_for_family(family,variant,names)
        # FontTools defaults to a wall-clock modified timestamp. Normalize it before
        # embedding so the proof remains reproducible after reopening in a new worker.
        stable_font=TTFont(io.BytesIO(subset.data),recalcTimestamp=False)
        stable_font['head'].modified=stable_font['head'].created
        stable_bytes=io.BytesIO()
        stable_font.save(stable_bytes)
        subset=replace(subset,data=stable_bytes.getvalue())
        widths=subset_cid_widths(subset)
        try:
            chars=dict((ch,cid) for paragraph in paragraphs for cid,ch in shape_cids(subset,paragraph))
        except ValueError:
            _fail('TEXT_BOX_UNSUPPORTED_TEXT')
        font=TTFont(io.BytesIO(subset.data))
        scale=size/font['head'].unitsPerEm
        order=font.getGlyphOrder()
        bounds: dict[str,tuple[float,float,float,float]]={}
        for ch,cid in chars.items():
            glyph=font['glyf'][order[cid]]
            if glyph.numberOfContours:
                glyph.recalcBounds(font['glyf'])
                bounds[ch]=(glyph.xMin*scale,glyph.yMin*scale,glyph.xMax*scale,glyph.yMax*scale)
            else:
                bounds[ch]=(0,0,0,0)
        faces.append(_Face(subset,widths,chars,font,bounds))
    def bound(i: int) -> tuple[float,...]:
        face,glyph_size,_,_=cells[i]
        return tuple(v*glyph_size/size for v in faces[face].bounds[text[i]])
    def advance(i: int) -> float:
        face,glyph_size,_,_=cells[i]
        return round(faces[face].widths[faces[face].chars[text[i]]])*glyph_size/1000
    if styled:
        visible=[i for i,ch in enumerate(text) if ch!='\n'] or list(range(len(text)))
        used={cells[i][:2] for i in visible}
        asc=max(max(faces[f].font['hhea'].ascent*s/faces[f].font['head'].unitsPerEm for f,s in used),
                max(bound(i)[3] for i in visible))
        desc=max(max(-faces[f].font['hhea'].descent*s/faces[f].font['head'].unitsPerEm for f,s in used),
                 max(-bound(i)[1] for i in visible))
    else:
        main=faces[0]; scale=size/main.font['head'].unitsPerEm
        initial_bounds=tuple(v*initial_size/size for v in main.bounds[text[first]]) if initial_size is not None and first is not None else (0.,0.,0.,0.)
        asc=max(main.font['hhea'].ascent*scale,max((b[3] for b in main.bounds.values()),default=0),initial_bounds[3])
        desc=max(-main.font['hhea'].descent*scale,max((-b[1] for b in main.bounds.values()),default=0),-initial_bounds[1])
    def measure(start: int, end: int) -> tuple[float,float]:
        pen=0.; lo=0.; hi=0.
        for i in range(start,end):
            b=bound(i)
            lo=min(lo,pen+b[0]); hi=max(hi,pen+b[2])
            pen+=advance(i)
            if i<end-1:
                pen+=spacing
        return lo,max(hi,pen)
    lines: list[tuple[int,int,bool]]=[]
    start=0
    for paragraph in text.split('\n'):
        stop=start+len(paragraph)
        if not paragraph:
            lines.append((start,start,True))
        position=start
        while position<stop:
            # A bounded character scan preserves every space and breaks long tokens.
            end=position; last_break=position
            pen=0.;lo=0.;hi=0.
            for i in range(position,stop):
                b=bound(i)
                lo=min(lo,pen+b[0]);hi=max(hi,pen+b[2])
                glyph_advance=advance(i)
                if max(hi,pen+glyph_advance)-lo>rect['width']+1e-7:
                    break
                pen+=glyph_advance+spacing
                end=i+1
                if text[i]==' ':
                    last_break=end
            if end==position:
                _fail('TEXT_BOX_UNSUPPORTED_TEXT')
            if end<stop and last_break>position:
                end=last_break
            lines.append((position,end,end==stop))
            position=end
        start=stop+1
    # A line's advance from the previous baseline is its own largest glyph size.
    heights=[max((cells[i][1] for i in range(a,b)),default=cells[min(a,len(text)-1)][1]) if styled else size
             for a,b,_ in lines]
    if styled:
        required=asc+desc+sum(h*style['line_spacing'] for h in heights[1:])+sum(style['paragraph_spacing'] for _,_,last in lines[:-1] if last)
    else:
        required=asc+desc+max(0,len(lines)-1)*size*style['line_spacing']+sum(style['paragraph_spacing'] for _,_,last in lines[:-1] if last)
    resource=_resource(spec)
    resources=[resource+f'F{n}' for n in range(len(faces))] if styled else [resource]
    fonts={name:embed_type0_font(pdf,face.subset,face.widths,{cid:ch for ch,cid in face.chars.items()})
           for name,face in zip(resources,faces)}
    head=cells[first] if styled and first is not None else (0,size,style['color'],False)
    state=(head[0],head[1],head[3]); color=head[2]
    commands=['q',' '.join(_fmt(v) for v in geometry.matrix)+' cm','BT',
              f'{resources[state[0]]} {_fmt(state[1])} Tf',' '.join(_fmt(c) for c in color)+' rg', '0 Tr']
    y=rect['top']+asc
    for k,(line_start,line_end,_) in enumerate(lines):
        if k:
            y+=heights[k]*style['line_spacing']+(style['paragraph_spacing'] if lines[k-1][2] else 0)
        lo,hi=measure(line_start,line_end)
        x=rect['left']-lo
        extra=rect['width']-(hi-lo)
        if style['alignment']=='center':x+=extra/2
        elif style['alignment']=='right':x+=extra
        for i in range(line_start,line_end):
            face,glyph_size,glyph_color,initial=cells[i]
            if (face,glyph_size,initial)!=state:
                state=(face,glyph_size,initial)
                commands.append(f'{resources[face]} {_fmt(glyph_size)} Tf')
            if glyph_color!=color:
                color=glyph_color
                commands.append(' '.join(_fmt(c) for c in color)+' rg')
            commands.append(f'1 0 0 1 {_fmt(x)} {_fmt(-y)} Tm <{faces[face].chars[text[i]]:04X}> Tj')
            x+=advance(i)+spacing
    if state[2]:
        # A lone initial letter restores the body size before ET, as it always has.
        commands.append(f'{resources[0]} {_fmt(size)} Tf')
    commands.extend(['ET','Q'])
    return Drawing(('\n'.join(commands)+'\n').encode(),fonts,
                   dict(required_height=round(required,6),available_height=rect['height'],line_count=len(lines)))


def _resource(spec: dict[str,Any]) -> str:
    return '/NTB'+cast(str,spec['id'])+hashlib.sha256(_json(spec)).hexdigest()[:16]


def _fmt(number: float) -> str:
    return f'{number:.8f}'.rstrip('0').rstrip('.') or '0'


def _owned(pdf: pikepdf.Pdf) -> list[tuple[dict[str,Any],pikepdf.Object]]:
    result: list[tuple[dict[str,Any],pikepdf.Object]]=[]
    seen: set[str]=set()
    for index,page in enumerate(pdf.pages):
        for stream in _contents(page):
            metadata=stream.get('/NativeTextBox')
            if metadata is None:
                continue
            try:
                raw=bytes(metadata)
                if len(raw)>MAX_METADATA:
                    _fail('TEXT_BOX_UNSAFE')
                meta=json.loads(raw)
                if not isinstance(meta,dict) or set(meta)!={'version','spec'} or type(meta['version']) is not int or meta['version']!=1 or raw!=_json(meta):
                    _fail('TEXT_BOX_UNSAFE')
                spec=meta['spec']
                if not isinstance(spec,dict) or set(spec)-{'runs'}!={'id','page_index','rect','text','style'}:
                    _fail('TEXT_BOX_UNSAFE')
                normalized=_spec(spec,MAX_TEXT_BOX_PAGES)
                if normalized!=spec or spec['id'] in seen:
                    _fail('TEXT_BOX_UNSAFE')
                seen.add(spec['id'])
                if len(seen)>200:
                    _fail('TEXT_BOX_LIMIT')
                current_geometry=_geometry(page)
                drawing_bytes=_decoded(stream)
                geometry=_historical_geometry(drawing_bytes)
                # Rebuild in a scratch document: never trust a caller-provided proof.
                with pikepdf.Pdf.new() as expected_pdf:
                    expected=_drawing(expected_pdf,spec,geometry)
                    page_resources: Any=page.obj.get('/Resources',{})
                    resources: Any=page_resources.get('/Font',{})
                    if drawing_bytes!=expected.stream:
                        _fail('TEXT_BOX_UNSAFE')
                    for name,font in expected.fonts.items():
                        actual=resources.get(name)
                        if actual is None or _canonical(actual)!=_canonical(font):
                            _fail('TEXT_BOX_UNSAFE')
                if set(str(k) for k in stream.keys())-{'/Length','/Filter','/DecodeParms','/NativeTextBox'}:
                    _fail('TEXT_BOX_UNSAFE')
                result.append((_project(spec,index,geometry,current_geometry),stream))
            except TextBoxError as exc:
                if exc.code=='TEXT_BOX_LIMIT':raise
                _fail('TEXT_BOX_UNSAFE')
            except (ValueError,TypeError,KeyError,AttributeError,pikepdf.PdfError):
                _fail('TEXT_BOX_UNSAFE')
    if result:
        _exclusive(pdf,{stream.objgen for _,stream in result})
    return result


def _exclusive(pdf: pikepdf.Pdf, targets: set[tuple[int,int]]) -> None:
    references=dict.fromkeys(targets,0)
    budget=200000
    def scan(obj: object, root: bool = False, depth: int = 0) -> None:
        nonlocal budget
        budget-=1
        if budget<0 or depth>64:
            _fail('TEXT_BOX_LIMIT')
        if isinstance(obj,pikepdf.Object) and obj.is_indirect and not root:
            if obj.objgen in references:references[obj.objgen]+=1
            return
        if isinstance(obj,(pikepdf.Dictionary,pikepdf.Stream)):
            for _,value in obj.items():scan(value,depth=depth+1)
        elif isinstance(obj,pikepdf.Array):
            for value in obj:scan(value,depth=depth+1)
    for obj in pdf.objects:scan(obj,root=True)
    if any(v!=1 for v in references.values()):
        _fail('TEXT_BOX_UNSAFE')


def _historical_geometry(drawing: bytes) -> Geometry:
    """Read only a finite quarter-turn transform; full drawing is proven afterwards.

    Page tree indices and /Rotate can change independently of a content stream.
    The drawing's exact canonical matrix is therefore the placement authority.
    """
    lines=drawing.split(b'\n',2)
    if len(lines)!=3 or lines[0]!=b'q' or len(lines[1])>256:
        _fail('TEXT_BOX_UNSAFE')
    parts=lines[1].split(b' ')
    if len(parts)!=7 or parts[-1]!=b'cm':
        _fail('TEXT_BOX_UNSAFE')
    try:
        values=tuple(float(v) for v in parts[:6])
    except ValueError:
        _fail('TEXT_BOX_UNSAFE')
    if len(values)!=6 or not all(math.isfinite(v) and abs(v)<=1e12 for v in values):
        _fail('TEXT_BOX_UNSAFE')
    a,b,c,d,e,f=values
    scale=max(abs(a),abs(b),abs(c),abs(d))
    if scale<1/75000-1e-8 or scale>100 or a*d-b*c<=0:
        _fail('TEXT_BOX_UNSAFE')
    if not ((b==c==0 and a==d and a!=0) or (a==d==0 and b==-c and b!=0)):
        _fail('TEXT_BOX_UNSAFE')
    matrix=values
    return Geometry(matrix,144000,144000,1/scale)


def _project(spec: dict[str,Any], index: int, historical: Geometry,
             current: Geometry) -> dict[str,Any]:
    if historical.matrix==tuple(float(_fmt(v)) for v in current.matrix):
        return {**spec,'page_index':index}
    a,b,c,d,e,f=historical.matrix
    rect=spec['rect']
    points=[current.visible(e+a*x-c*y,f+b*x-d*y)
            for x in (rect['left'],rect['left']+rect['width'])
            for y in (rect['top'],rect['top']+rect['height'])]
    x0=min(x for x,_ in points);x1=max(x for x,_ in points)
    y0=min(y for _,y in points);y1=max(y for _,y in points)
    origin=current.visible(e,f);right=current.visible(e+a,f+b)
    rotation=round(math.degrees(math.atan2(right[1]-origin[1],right[0]-origin[0]))/90)*90%360
    result={**spec,'page_index':index,'rect':dict(left=round(x0,6),top=round(y0,6),
                                                width=round(x1-x0,6),height=round(y1-y0,6))}
    if rotation:result['rotation']=rotation
    return result


def _in_page(spec: dict[str,Any], geometry: Geometry) -> None:
    rect=spec['rect']
    if rect['left']+rect['width']>geometry.width+1e-6 or rect['top']+rect['height']>geometry.height+1e-6:
        _fail()


def _serialize(pdf: pikepdf.Pdf) -> bytes:
    buffer=io.BytesIO()
    # Page tools may preserve/add UserUnit even at its default value. Its PDF
    # dictionary entry requires 1.6 regardless of the older source header.
    pdf.save(buffer, min_version='1.6' if any('/UserUnit' in page.obj for page in pdf.pages) else '1.3')
    result=buffer.getvalue()
    if len(result)>MAX_OUTPUT:
        _fail('TEXT_BOX_OUTPUT_LIMIT')
    return result


def _collision(pdf: pikepdf.Pdf, spec: dict[str,Any], geometry: Geometry) -> None:
    rect=spec['rect']; page=pdf.pages[spec['page_index']]
    def intersects(x0:float,y0:float,x1:float,y1:float) -> bool:
        return bool(min(x0,x1)<rect['left']+rect['width'] and max(x0,x1)>rect['left'] and min(y0,y1)<rect['top']+rect['height'] and max(y0,y1)>rect['top'])
    annots=page.obj.get('/Annots',[])
    if len(annots)>10000:_fail('TEXT_BOX_LIMIT')
    for annotation in annots:
        try:
            raw=annotation.get('/Rect')
            if raw is None or len(raw)!=4:_fail('TEXT_BOX_UNSAFE')
            x0,y0=geometry.visible(float(raw[0]),float(raw[1]))
            x1,y1=geometry.visible(float(raw[2]),float(raw[3]))
            if not all(math.isfinite(v) for v in (x0,y0,x1,y1)):_fail('TEXT_BOX_UNSAFE')
            if intersects(x0,y0,x1,y1):_fail('TEXT_BOX_OVERLAP')
        except TextBoxError:raise
        except (ValueError,TypeError,AttributeError):_fail('TEXT_BOX_UNSAFE')
    data=_serialize(pdf)
    with pdfium.PdfDocument(data) as document:
        document.init_forms()
        rendered_page=document[spec['page_index']]
        try:
            w,h=rendered_page.get_size()
            # PDFium ignores UserUnit; derive its exact physical-to-canvas ratio.
            sx,sy=w/geometry.width,h/geometry.height
            if abs(sx-sy)>max(sx,sy)*.001:_fail('TEXT_BOX_UNSAFE')
            scale=2/sx
            if rect['width']*rect['height']*4>4_000_000:_fail('TEXT_BOX_LIMIT')
            # Round outward so no fractional edge escapes the occupancy check.
            left=max(0,math.floor(rect['left']*2)/2)
            top=max(0,math.floor(rect['top']*2)/2)
            right=min(geometry.width,math.ceil((rect['left']+rect['width'])*2)/2)
            bottom=min(geometry.height,math.ceil((rect['top']+rect['height'])*2)/2)
            bitmap=rendered_page.render(scale=scale,crop=(left*sx,(geometry.height-bottom)*sy,(geometry.width-right)*sx,top*sy),draw_annots=True)
            try:
                extrema=bitmap.to_pil().convert('RGB').getextrema()
                if any(low<255 for low,_ in extrema):_fail('TEXT_BOX_OVERLAP')
            finally:bitmap.close()
        finally:rendered_page.close()


def _isolation_marker(stream: pikepdf.Object, side: str) -> bool:
    marker=stream.get('/NativeTextBoxIsolation')
    if marker is None:return False
    if not isinstance(marker,pikepdf.String) or bytes(marker)!=('v1:'+side).encode():
        return False
    if set(str(k) for k in stream.keys())-{'/Length','/Filter','/DecodeParms','/NativeTextBoxIsolation'}:
        _fail('TEXT_BOX_UNSAFE')
    if _decoded(stream)!=(b'q\n' if side=='start' else b'Q\n'):
        _fail('TEXT_BOX_UNSAFE')
    return True


def _isolate(pdf: pikepdf.Pdf, page: pikepdf.Page) -> None:
    """Reuse only an exact exclusive paired source-state envelope.

    The pair encloses source content; individually verified native drawings follow
    its restoring Q. It adds no graphics-state nesting on repeated edits.
    """
    contents=_contents(page)
    reusable=False
    end=-1
    marked=[i for i,stream in enumerate(contents) if stream.get('/NativeTextBoxIsolation') is not None]
    if marked:
        stack: list[int]=[]
        pairs: dict[int,int]={}
        for i in marked:
            if _isolation_marker(contents[i],'start'):
                stack.append(i)
            elif _isolation_marker(contents[i],'end'):
                if not stack:_fail('TEXT_BOX_UNSAFE')
                pairs[stack.pop()]=i
            else:
                _fail('TEXT_BOX_UNSAFE')
        if stack:
            _fail('TEXT_BOX_UNSAFE')
        _exclusive(pdf,{contents[i].objgen for i in marked})
        # Browser page/image operations can add an unmarked q/Q around the
        # existing contents. Verify the inner pairs, then retain that complete
        # source state under a new outer envelope instead of discarding it.
        if 0 in pairs:
            end=pairs[0]
            reusable=all(stream.get('/NativeTextBox') is not None for stream in contents[end+1:])
        # When another producer appends source after the restoring Q, retain the
        # prior envelope in place: removing it would change inherited graphics
        # state for existing owned drawings. One new outer envelope is reusable
        # on all subsequent edits until source is appended again.
    depth=0;text=False
    body=contents[1:end] if reusable else contents
    envelope_allowance=max(0,len(marked)//2-(1 if reusable else 0))
    operator_count=0
    try:
        for stream in body:
            for i,instruction in enumerate(pikepdf.parse_content_stream(stream)):
                operator_count+=1
                if operator_count>100000:_fail('TEXT_BOX_LIMIT')
                op=str(instruction.operator)
                if op=='q':
                    depth+=1
                    if depth>128+envelope_allowance:_fail('TEXT_BOX_UNSAFE')
                elif op=='Q':
                    depth-=1
                    if depth<0:_fail('TEXT_BOX_UNSAFE')
                elif op=='BT':
                    if text:_fail('TEXT_BOX_UNSAFE')
                    text=True
                elif op=='ET':
                    if not text:_fail('TEXT_BOX_UNSAFE')
                    text=False
        if depth or text:_fail('TEXT_BOX_UNSAFE')
    except pikepdf.PdfError:_fail('TEXT_BOX_UNSAFE')
    if reusable:return
    start_stream=pikepdf.Stream(pdf,b'q\n')
    end_stream=pikepdf.Stream(pdf,b'Q\n')
    start_stream.NativeTextBoxIsolation=pikepdf.String('v1:start')
    end_stream.NativeTextBoxIsolation=pikepdf.String('v1:end')
    page.obj.Contents=pikepdf.Array([start_stream,*contents,end_stream])


def prepare_text_box(pdf: pikepdf.Pdf, source: bytes, payload: object) -> dict[str,object]:
    """Return a source-bound list, exact candidate PDF, or finite layout refusal."""
    request=_dict(payload,{'operation','page_index','id','text','rect','style','runs','allow_overlap','auto_expand'})
    operation=cast(str,request.get('operation'))
    if operation not in ('list','upsert','remove'):_fail()
    keys={'list':{'operation'},'remove':{'operation','id'},'upsert':{'operation','page_index','id','text','rect','style','runs','allow_overlap','auto_expand'}}[operation]
    if set(request)-keys:_fail()
    if len(source)>50*1024*1024 or len(pdf.pages)>MAX_TEXT_BOX_PAGES:_fail('TEXT_BOX_LIMIT')
    source_hash=hashlib.sha256(source).hexdigest()
    owned=_owned(pdf)
    boxes=[s for s,_ in owned]
    if operation=='list':return dict(ok=True,source_hash=source_hash,boxes=boxes)
    selected=None
    if 'id' in request:
        identifier=_identifier(request['id'])
        selected=next(((s,stream) for s,stream in owned if s['id']==identifier),None)
        if selected is None:_fail('TEXT_BOX_NOT_FOUND')
    if operation=='remove' and selected is None:_fail()
    if selected and operation=='upsert' and selected[0].get('rotation',0):
        _fail('TEXT_BOX_UNSAFE')
    if selected:
        selected_spec,selected_stream=selected
        page=pdf.pages[selected_spec['page_index']]
        page.obj.Contents=pikepdf.Array([s for s in _contents(page) if s.objgen!=selected_stream.objgen])
        boxes=[s for s in boxes if s['id']!=selected_spec['id']]
    layout: dict[str,object] | None=None
    if operation=='upsert':
        if type(request.get('allow_overlap',False)) is not bool:_fail()
        if type(request.get('auto_expand',False)) is not bool:_fail()
        if selected is None and len(boxes)>=200:_fail('TEXT_BOX_LIMIT')
        spec=_spec(request,len(pdf.pages))
        page=pdf.pages[spec['page_index']]
        geometry=_geometry(page)
        _in_page(spec,geometry)
        drawing=_drawing(pdf,spec,geometry)
        layout=drawing.layout
        required=cast(float,layout['required_height'])
        if required>spec['rect']['height']+1e-6 and request.get('auto_expand',False):
            grown=math.ceil(required*100)/100
            if spec['rect']['top']+grown<=geometry.height+1e-6:
                spec['rect']['height']=grown
                drawing=_drawing(pdf,spec,geometry)
                layout=drawing.layout
        if cast(float,layout['required_height'])>spec['rect']['height']+1e-6:
            return dict(ok=False,source_hash=source_hash,code='TEXT_BOX_OVERFLOW',required_height=layout['required_height'],available_height=layout['available_height'])
        metadata=_json(dict(version=1,spec=spec))
        if len(metadata)>MAX_METADATA:_fail('TEXT_BOX_LIMIT')  # would not reopen
        if not request.get('allow_overlap',False):_collision(pdf,spec,geometry)
        _isolate(pdf,page)
        # Copy dictionaries to avoid modifying inherited/shared resource dictionaries.
        resources=pikepdf.Dictionary(page.obj.get('/Resources',{}))
        fonts=pikepdf.Dictionary(cast(Any,resources.get('/Font',{})))
        for name,font in drawing.fonts.items():
            if fonts.get(name) is not None and _canonical(fonts[name])!=_canonical(font):
                _fail('TEXT_BOX_UNSAFE')
            fonts[name]=font
        resources.Font=fonts
        page.obj.Resources=resources
        stream=pikepdf.Stream(pdf,drawing.stream)
        stream.NativeTextBox=pikepdf.String(metadata)
        page.obj.Contents=pikepdf.Array([*_contents(page),stream])
        boxes.append(spec)
        page_index=spec['page_index']
    else:
        assert selected is not None
        page_index=selected[0]['page_index']
    candidate=_serialize(pdf)
    return dict(ok=True,source_hash=source_hash,pdf=base64.b64encode(candidate).decode('ascii'),
                page_index=page_index,boxes=boxes,layout=layout,notices=[])
