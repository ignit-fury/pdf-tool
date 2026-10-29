"""Atomic candidate: guarded source-run removal followed by native multiline layout."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pikepdf

from engine.recipe import RecipeOp, RecipeTooLargeError, apply_recipe, parse_recipe
from engine.text_boxes import TextBoxError, prepare_text_box


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


def prepare_source_text_box(path: Path, source: bytes, payload: dict[str, Any],
                            intermediate: Path, *, password: str = '') -> dict[str, object]:
    allowed={'operation','source_run_id','source_run_ids','recipe','page_index','text','rect','style','allow_overlap','auto_expand'}
    if set(payload)-allowed or payload.get('operation')!='replace-source' or ('source_run_id' in payload)==('source_run_ids' in payload):
        raise TextBoxError('INVALID_TEXT_BOX')
    group=payload.get('source_run_ids')
    if group is not None:
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
    insertion={k:v for k,v in payload.items() if k not in ('source_run_id','source_run_ids','recipe')}
    insertion['operation']='upsert'
    with pikepdf.open(intermediate) as pdf:
        result=prepare_text_box(pdf,materialized,insertion)
    # Public source binding remains the original immutable source/recipe pair.
    return {**result,'source_hash':hashlib.sha256(source).hexdigest()}
