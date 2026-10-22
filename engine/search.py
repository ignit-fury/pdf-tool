"""Canonical search projection, preserving original UTF-16 source provenance.

The sparse generated table is shared with the browser. Runtime Unicode versions
therefore cannot change search addresses. Display text and run IDs stay intact.
"""
import json
from pathlib import Path
from typing import TypedDict


class Projection(TypedDict):
    text: str
    spans: list[list[int]]


class SearchProjection(TypedDict):
    version: str
    sensitive: Projection
    folded: Projection


class _Data(TypedDict):
    version: str
    unicode_version: str
    nfkd: dict[str, str]
    casefold: dict[str, str]
    combining: dict[str, int]


_DATA: _Data = json.loads((Path(__file__).parent / 'data/search-unicode-15.1.json').read_text())
VERSION = _DATA['version']
_Tagged = tuple[str, int, int]


def _decompose(items: list[_Tagged]) -> list[_Tagged]:
    expanded = [(part, start, end) for char, start, end in items
                for part in _DATA['nfkd'].get(str(ord(char)), char)]
    # Stable insertion ordering, bounded by the previous starter. CCC=0 is a
    # boundary, including consecutive starters produced by ligature expansion.
    ordered: list[_Tagged] = []
    for item in expanded:
        ccc = _DATA['combining'].get(str(ord(item[0])), 0)
        position = len(ordered)
        if ccc:
            while position and _DATA['combining'].get(str(ord(ordered[position - 1][0])), 0) > ccc:
                position -= 1
        ordered.insert(position, item)
    return ordered


def project_text(text: str, *, match_case: bool = False) -> Projection:
    source: list[_Tagged] = []
    offset = 0
    for char in text:
        end = offset + (2 if ord(char) > 0xFFFF else 1)
        source.append((char, offset, end))
        offset = end
    items = _decompose(source)
    if not match_case:
        items = _decompose([(part, start, end) for char, start, end in items
                            for part in _DATA['casefold'].get(str(ord(char)), char)])
    spans = [[start, end] for char, start, end in items for _ in range(2 if ord(char) > 0xFFFF else 1)]
    return {'text': ''.join(char for char, _, _ in items), 'spans': spans}


def project_search_text(text: str) -> SearchProjection:
    return {'version': VERSION, 'sensitive': project_text(text, match_case=True), 'folded': project_text(text)}
