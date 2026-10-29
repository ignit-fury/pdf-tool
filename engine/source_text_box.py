"""Atomic candidate: guarded source-run removal followed by native multiline layout."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pikepdf

from engine.recipe import RecipeOp, RecipeTooLargeError, apply_recipe, parse_recipe
from engine.text_boxes import TextBoxError, prepare_text_box


def prepare_source_text_box(path: Path, source: bytes, payload: dict[str, Any],
                            intermediate: Path, *, password: str = '') -> dict[str, object]:
    allowed={'operation','source_run_id','recipe','page_index','text','rect','style','allow_overlap','auto_expand'}
    if set(payload)-allowed or payload.get('operation')!='replace-source' or not isinstance(payload.get('source_run_id'),str):
        raise TextBoxError('INVALID_TEXT_BOX')
    if not isinstance(payload.get('recipe'),list):
        raise TextBoxError('INVALID_TEXT_BOX')
    try:
        encoded=json.dumps(payload['recipe'],allow_nan=False).encode()
        if len(encoded)>1024*1024:raise ValueError('limit')
        prior=parse_recipe(encoded)
    except (ValueError,TypeError,RecipeTooLargeError):
        raise TextBoxError('INVALID_TEXT_BOX') from None
    identifier=payload['source_run_id']
    existing=next((op for op in prior if op.run_id==identifier),None)
    style=dict(existing.style or {}) if existing else {}
    family=payload.get('style',{}).get('font_family') if isinstance(payload.get('style',{}),dict) else None
    if family not in ('Sans','Serif','Mono'):raise TextBoxError('INVALID_TEXT_BOX')
    style['font_family']=family
    deletion=RecipeOp(identifier,'',style)  # type: ignore[arg-type]
    # Replace an existing selected-run operation, preserving all other committed ops.
    recipe=tuple(deletion if op.run_id==identifier else op for op in prior)
    if existing is None:recipe=(*recipe,deletion)
    report=apply_recipe(path,recipe,intermediate,password=password)
    if not report.ok or not intermediate.exists():
        raise TextBoxError('TEXT_BOX_SOURCE_UNSAFE')
    materialized=intermediate.read_bytes()
    insertion={k:v for k,v in payload.items() if k not in ('source_run_id','recipe')}
    insertion['operation']='upsert'
    with pikepdf.open(intermediate) as pdf:
        result=prepare_text_box(pdf,materialized,insertion)
    # Public source binding remains the original immutable source/recipe pair.
    return {**result,'source_hash':hashlib.sha256(source).hexdigest()}
