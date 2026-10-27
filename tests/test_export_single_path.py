"""Non-vacuous source and runtime proof of EXPO-05's single text path."""
import ast
import re
from collections import Counter
from pathlib import Path

import pytest

from engine.index import RunIndex
from tools.build_export_fixtures import build_export_fixture

FORBIDDEN = {'extract_text', 'extractText', 'getTextContent', 'pdftotext', 'PDFParser',
             'PdfReader', 'open_document', 'parse_document', 'walk_page', 'located_cluster_records',
             'classify_document', 'get_textpage', 'get_text_range', 'get_text_bounded'}


def violations(path: Path, *, exporter: bool) -> list[str]:
    tree = ast.parse(path.read_text())
    problems: list[str] = []
    aliases: dict[str,str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [a.name for a in node.names] if isinstance(node,ast.Import) else [node.module or '']
            if any(m.split('.')[0] in {'playa','pdfminer'} for m in modules) and path.name != 'playa_boundary.py':
                problems.append('parser-import')
            for alias in node.names:
                aliases[alias.asname or alias.name] = alias.name.split('.')[-1]
                if exporter and alias.name.split('.')[-1] in FORBIDDEN:
                    problems.append('alternate-extractor-import')
    if exporter:
        for node in ast.walk(tree):
            if isinstance(node,ast.Call):
                name = node.func.attr if isinstance(node.func,ast.Attribute) else node.func.id if isinstance(node.func,ast.Name) else ''
                if aliases.get(name,name) in FORBIDDEN:
                    problems.append('alternate-extractor-call')
    return problems


def test_production_has_one_parser_boundary_and_no_export_extractors(tmp_path: Path) -> None:
    for directory in (Path('engine'), Path('server')):
        for path in directory.rglob('*.py'):
            exporter = 'export' in path.parts or path.name == 'exports.py'
            assert not violations(path,exporter=exporter), str(path)
    # Viewer selection uses getTextContent deliberately; only export modules are gated.
    for path in Path('client/src').rglob('*'):
        if path.suffix in {'.ts','.tsx'} and ('exports' in path.parts or path.stem.lower().startswith('export')):
            assert not re.search(r'\b(?:getTextContent|extractText|extract_text)\s*\(',path.read_text()), str(path)
    bad = tmp_path / 'bad.py'
    bad.write_text('from pdfminer.high_level import extract_text as hidden\nhidden("x")\n')
    assert set(violations(bad,exporter=True)) == {'parser-import','alternate-extractor-import','alternate-extractor-call'}
    bad.write_text('page.get_textpage().get_text_range()\n')
    assert violations(bad,exporter=True) == ['alternate-extractor-call','alternate-extractor-call']


def test_repeated_exports_open_one_index_and_parse_each_page_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.index as module
    from engine.export.text import export_document
    path = tmp_path / 'in.pdf'
    build_export_fixture(path)
    opens: list[int] = []
    parses: Counter[int] = Counter()
    original_open, original_parse = module.open_document, RunIndex._parse_page
    def opening(*args: object, **kwargs: object) -> object:
        opens.append(1)
        return original_open(*args,**kwargs)
    def parsing(self: RunIndex, number: int) -> object:
        parses[number] += 1
        return original_parse(self,number)
    monkeypatch.setattr(module,'open_document',opening)
    monkeypatch.setattr(RunIndex,'_parse_page',parsing)
    with RunIndex(path) as index:
        for _ in range(2):
            for format in ('text','markdown','html'):
                assert 'Export heading' in export_document(index,format)
        assert parses == Counter({0:1,1:1,2:1})
        assert len(opens) == 1


def test_export_builds_document_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.export.text as module
    path = tmp_path / 'in.pdf'
    build_export_fixture(path)
    build = module.build_document
    calls: list[int] = []
    def building(index: RunIndex) -> object:
        calls.append(1)
        return build(index)
    monkeypatch.setattr(module,'build_document',building)
    with RunIndex(path) as index:
        module.export_document(index,'html')
    assert len(calls) == 1
