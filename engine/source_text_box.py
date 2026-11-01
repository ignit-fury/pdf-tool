"""Atomic candidate: guarded source-run removal followed by native multiline layout."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pikepdf

from engine.recipe import RecipeOp, RecipeTooLargeError, apply_recipe, parse_recipe
from engine.text_boxes import TextBoxError, _geometry, page_text_boxes, prepare_text_box


def _validated_initial_pair(path: Path, password: str, page: object,
                            identifiers: list[str]) -> None:
    """Only two consecutive, touching letters on one baseline may be one target."""
    from engine.index import RunIndex
    from engine.run_id import decode_run_id
    if type(page) is not int or len(identifiers)!=2 or identifiers[0]==identifiers[1]:
        raise TextBoxError('INVALID_TEXT_BOX')
    try:
        addresses=[decode_run_id(identifier) for identifier in identifiers]
        if any(address['page']!=page for address in addresses):
            raise ValueError('page')
        if any((address['part'],address['xobj_path']) !=
               (addresses[0]['part'],addresses[0]['xobj_path']) for address in addresses[1:]):
            raise ValueError('stream')
        with RunIndex(path,password=password) as index:
            runs=index.page(page).runs
            positions={run.run_id:i for i,(run,_) in enumerate(runs)}
            first_pos=positions[identifiers[0]]
            if positions[identifiers[1]]!=first_pos+1:
                raise ValueError('sequence')
            (first,first_verdict),(tail,tail_verdict)=runs[first_pos:first_pos+2]
        if first_verdict.state=='not_editable' or tail_verdict.state=='not_editable':
            raise ValueError('state')
        if not first.display_text.isalpha() or len(first.display_text)!=1 or not tail.display_text.isalpha() or len(tail.display_text)<2:
            raise ValueError('letters')
        a,b=first.glyphs[-1],tail.glyphs[0]
        if abs(a.y-b.y)>.5 or abs(a.x+a.advance[0]-b.x)>max(.5,.03*min(first.effective_em or 0,tail.effective_em or 0)):
            raise ValueError('geometry')
        if any(abs(g.advance[1])>.01 or g.advance[0]<=0 for run in (first,tail) for g in run.glyphs):
            raise ValueError('direction')
    except (KeyError,IndexError,ValueError,TypeError):
        raise TextBoxError('TEXT_BOX_SOURCE_UNSAFE') from None


def _validated_paragraph(path: Path, password: str, page: object,
                         identifier: object, identifiers: list[str]) -> None:
    from engine.index import RunIndex
    from engine.paragraphs import page_paragraphs
    from engine.run_id import decode_run_id
    if type(page) is not int or not isinstance(identifier, str) or not identifiers:
        raise TextBoxError('INVALID_TEXT_BOX')
    with RunIndex(path, password=password) as index:
        try:
            if page < 0:
                raise IndexError(page)
            indexed = index.page(page)
        except (IndexError, KeyError, ValueError):
            raise TextBoxError('INVALID_TEXT_BOX') from None
        match = next((p for p in page_paragraphs(page, indexed) if p.paragraph_id == identifier), None)
        if match is None or list(match.run_ids) != identifiers:
            raise TextBoxError('PARAGRAPH_STALE')
        if match.angled:
            raise TextBoxError('TEXT_BOX_SOURCE_UNSAFE')
        states = {run.run_id: verdict.state for run, verdict in indexed.runs}
    streams = {(a['part'], a['xobj_path']) for a in map(decode_run_id, identifiers)}
    if any(states.get(i) == 'not_editable' for i in identifiers) or len(streams) != 1:
        raise TextBoxError('TEXT_BOX_SOURCE_UNSAFE')


def prepare_source_text_box(path: Path, source: bytes, payload: dict[str, Any],
                            intermediate: Path, *, password: str = '',
                            push: bool = False) -> dict[str, object]:
    """`push`: when the box needs more room than `rect`, move the content below down."""
    allowed={'operation','source_run_id','source_run_ids','paragraph_id','recipe','page_index','text','rect','style','runs','allow_overlap','auto_expand'}
    if set(payload)-allowed or payload.get('operation')!='replace-source' or ('source_run_id' in payload)==('source_run_ids' in payload):
        raise TextBoxError('INVALID_TEXT_BOX')
    group=payload.get('source_run_ids')
    if 'paragraph_id' in payload:
        if not isinstance(group,list) or not all(isinstance(item,str) for item in group):
            raise TextBoxError('INVALID_TEXT_BOX')
        identifiers=group
        _validated_paragraph(path,password,payload.get('page_index'),payload['paragraph_id'],identifiers)
    elif group is not None:
        if not isinstance(group,list) or len(group)!=2 or not all(isinstance(item,str) for item in group):
            raise TextBoxError('INVALID_TEXT_BOX')
        identifiers=group
        _validated_initial_pair(path,password,payload.get('page_index'),identifiers)
    else:
        identifier=payload.get('source_run_id')
        if not isinstance(identifier,str):raise TextBoxError('INVALID_TEXT_BOX')
        identifiers=[identifier]
    if not isinstance(payload.get('recipe'),list):
        raise TextBoxError('INVALID_TEXT_BOX')
    try:
        encoded=json.dumps(payload['recipe'],allow_nan=False).encode()
        if len(encoded)>1024*1024:raise ValueError('limit')
        prior=parse_recipe(encoded)
    except (ValueError,TypeError,RecipeTooLargeError):
        raise TextBoxError('INVALID_TEXT_BOX') from None
    existing=next((op for op in prior if op.run_id==identifiers[0]),None)
    style=dict(existing.style or {}) if existing else {}
    family=payload.get('style',{}).get('font_family') if isinstance(payload.get('style',{}),dict) else None
    if family not in ('Sans','Serif','Mono'):raise TextBoxError('INVALID_TEXT_BOX')
    style['font_family']=family
    deletions={identifier:RecipeOp(identifier,'',style) for identifier in identifiers}  # type: ignore[arg-type]
    # Replace selected-run operations; keep all unrelated committed operations.
    recipe=tuple(deletions[op.run_id] if op.run_id in deletions else op for op in prior)
    recipe=(*recipe,*(deletion for identifier,deletion in deletions.items()
                      if not any(op.run_id==identifier for op in prior)))
    report=apply_recipe(path,recipe,intermediate,password=password)
    if not report.ok or not intermediate.exists():
        raise TextBoxError('TEXT_BOX_SOURCE_UNSAFE')
    materialized=intermediate.read_bytes()
    insertion={k:v for k,v in payload.items() if k not in ('source_run_id','source_run_ids','paragraph_id','recipe')}
    insertion['operation']='upsert'
    required=0.0
    if push:
        with pikepdf.open(intermediate) as pdf:  # layout only: no collision render
            probe=prepare_text_box(pdf,materialized,{**insertion,'auto_expand':False,'allow_overlap':True})
        layout: Any=probe['layout'] if probe['ok'] else probe
        required=float(layout['required_height'])
    if push and required>float(insertion['rect']['height'])+1e-6:
        # Push rather than grow into the free space below: the gap under the paragraph stays exact.
        if _columns(path,password,payload['page_index']):
            raise TextBoxError('PUSH_DOWN_UNSUPPORTED')  # push_down moves the full width: other columns would tear
        result,dy=_pushed_insert(intermediate,materialized,insertion,required)
    else:
        with pikepdf.open(intermediate) as pdf:
            result=prepare_text_box(pdf,materialized,insertion)
        dy=0.0
    # Public source binding remains the original immutable source/recipe pair.
    return {**result,'source_hash':hashlib.sha256(source).hexdigest(),'pushed':round(dy,6)}


def _columns(path: Path, password: str, page: int) -> bool:
    from engine.blocks import _page
    from engine.index import RunIndex
    with RunIndex(path, password=password) as index:
        return 'columns-inferred-unruled-tables-unsupported' in _page(page, index.page(page)).warnings


def _pushed_insert(intermediate: Path, materialized: bytes, insertion: dict[str, Any],
                   required: float) -> tuple[dict[str, object], float]:
    """Grow the box by exactly the height its text needs and move the content below
    down by the same amount; one more line if it still collides. Each attempt works on
    a fresh copy of the intermediate, so a refusal leaves nothing half-applied."""
    rect=insertion['rect']
    dy=math.ceil(required*100)/100-float(rect['height'])  # the height auto_expand grows to
    style=insertion['style']
    size=float(style.get('font_size',12))
    for extra in (0.0,size*float(style.get('line_spacing',1.2))):
        try:
            with pikepdf.open(intermediate) as pdf:
                _push(pdf,materialized,insertion['page_index'],rect,dy+extra,size*.1)
                result=prepare_text_box(pdf,materialized,insertion)
        except TextBoxError as error:
            if error.code!='TEXT_BOX_OVERLAP' or extra:
                raise
            continue
        if not result['ok']:
            raise TextBoxError('PUSH_DOWN_PAGE_FULL')  # the box itself would cross the page bottom
        return result,dy+extra
    raise AssertionError


def _push(pdf: pikepdf.Pdf, source: bytes, page_index: int, rect: dict[str, float],
          dy: float, margin: float) -> None:
    """Move everything below the paragraph's bottom (visible top-left coordinates)
    down by `dy`, including the native boxes there, which are re-upserted lower."""
    from engine.push_down import PushDownRefused, push_down
    geometry=_geometry(pdf.pages[page_index])
    a,b,c,d,e,f=geometry.matrix
    if b or c or d<=0:
        raise TextBoxError('PUSH_DOWN_UNSUPPORTED')  # rotated page: "down" is not -y
    bottom=rect['top']+rect['height']
    kept: list[str]=[]
    def keep(box_id: str) -> bool:
        kept.append(box_id)
        return True
    try:
        try:
            # Cut half a line gap below the bottom; ink above the next line's ascender is
            # outside push_down's extents. shortcut: 0.1em (half the 1.2 leading), not measured.
            push_down(pdf,page_index,f-d*(bottom+margin),dy*d,keep=keep)
        except PushDownRefused as refused:
            if refused.code!='PUSH_DOWN_STRADDLE':
                raise
            kept.clear()  # the margin reached into the next item: cut at the bottom itself
            push_down(pdf,page_index,f-d*bottom,dy*d,keep=keep)
    except PushDownRefused as refused:
        raise TextBoxError(refused.code) from None
    if not kept:
        return
    boxes={box['id']:box for box in page_text_boxes(pdf,source,page_index)}
    for box_id in kept:
        spec=boxes[box_id]
        moved={**spec['rect'],'top':spec['rect']['top']+dy}
        if moved['top']+moved['height']>geometry.height+1e-6:
            raise TextBoxError('PUSH_DOWN_PAGE_FULL')
        # Its neighbours moved by the same dy, so its overlap state is unchanged.
        prepare_text_box(pdf,source,{'operation':'upsert','id':box_id,'page_index':page_index,
                                     'text':spec['text'],'rect':moved,'style':spec['style'],
                                     **({'runs':spec['runs']} if 'runs' in spec else {}),
                                     'allow_overlap':True})
