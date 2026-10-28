"""Literal optional-module removal in an isolated copy; checkout is untouched."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
IGNORE = shutil.ignore_patterns('__pycache__', '.pytest_cache', '.mypy_cache', 'node_modules', 'dist', '.DS_Store')


@pytest.fixture(scope='module')
def removed(tmp_path_factory):
    directory = tmp_path_factory.mktemp('docx-removed')
    for name in ('engine','server','harness','tools','tests','fonts','.planning','.github','client'):
        shutil.copytree(ROOT / name, directory / name, ignore=IGNORE)
    for path in ROOT.iterdir():
        if path.is_file() and not path.name.startswith('.'):
            shutil.copy2(path, directory / path.name)
    shutil.copytree(ROOT / 'corpus', directory / 'corpus', ignore=shutil.ignore_patterns('public','private'))
    (directory / 'corpus/public').symlink_to(ROOT / 'corpus/public', target_is_directory=True)
    (directory / 'corpus/private').mkdir(exist_ok=True)
    (directory / 'client/node_modules').symlink_to(ROOT / 'client/node_modules', target_is_directory=True)
    (directory / 'engine/export/docx.py').unlink()
    assert (ROOT / 'engine/export/docx.py').is_file()
    return directory


def _run(directory: Path, command: list[str], *, timeout: int = 60, name: str = 'probe'):
    artifacts = Path(os.environ.get('G7A_EVIDENCE_DIR', str(directory / 'evidence'))) / 'docx-removed'
    env = {**os.environ, 'PYTHONPATH':str(directory),
        'PATH':str(Path(sys.executable).parent)+os.pathsep+os.environ.get('PATH',''),
        'G7A_EVIDENCE_DIR':str(artifacts / 'g7a'),
        'PDF_TOOL_G6_ARTIFACTS':str(artifacts / 'g6')}
    result = subprocess.run(command, cwd=directory, env=env, capture_output=True, text=True, timeout=timeout)
    (directory / (name+'.log')).write_text(result.stdout+result.stderr)
    return result


PROBE = '''
from pathlib import Path
import json
from fastapi.testclient import TestClient
import engine.index
from server.app import create_app
from tools.build_security_fixtures import text_pdf
assert Path(engine.index.__file__).resolve().is_relative_to(Path.cwd())
with TestClient(create_app()) as c:
    capability=c.get('/exports/capabilities').json()
    missing=c.post('/exports?operation=docx-review',content=text_pdf(),headers={'content-type':'application/pdf'})
    text=c.post('/exports?operation=text',content=text_pdf(),headers={'content-type':'application/pdf'})
    assert capability=={'docx':False} and missing.status_code==503 and text.status_code==200
print(json.dumps({'capability':capability,'docx':missing.status_code,'text':text.status_code}))
'''


def test_startup_and_other_exports_survive_literal_writer_removal(removed):
    result = _run(removed, [sys.executable,'-c',PROBE])
    assert result.returncode == 0, result.stdout+result.stderr


def test_removal_proof_detects_unconditional_import(removed):
    path = removed / 'server/app.py'
    original = path.read_bytes()
    try:
        path.write_bytes(original + b'\nimport engine.export.docx\n')
        result = _run(removed, [sys.executable,'-c',PROBE], name='negative-import')
        assert result.returncode != 0 and 'ModuleNotFoundError' in result.stderr
    finally:
        path.write_bytes(original)


@pytest.mark.corpus
def test_every_other_export_gate_without_docx(removed):
    assert os.environ.get('VERAPDF_CMD'), 'Removal proof needs the real G7a validator'
    files = ['tests/test_export_api.py','tests/test_export_pdf.py','tests/test_export_text.py',
             'tests/test_export_metadata.py','tests/test_export_single_path.py','tests/test_blocks.py',
             'tests/test_pdfa.py','tests/test_gate_g6.py','tests/test_gate_g7a.py']
    result = _run(removed, [sys.executable,'-m','pytest','-q',*files], timeout=240, name='all-other-export-gates')
    assert result.returncode == 0, result.stdout[-4000:]+result.stderr[-1000:]
    modules = [str(p.relative_to(removed)) for p in sorted((removed/'client/src/exports').glob('*.test.mjs'))]
    result = _run(removed, ['node','--test',*modules], timeout=60, name='client-export-tests')
    assert result.returncode == 0, result.stdout[-2000:]+result.stderr[-1000:]
    result = _run(removed, ['npm','--prefix','client','run','build'], timeout=90, name='client-build')
    assert result.returncode == 0, result.stdout[-2000:]+result.stderr[-1000:]
    evidence = {'passed':True,'removed':'engine/export/docx.py','checkout_untouched':(ROOT/'engine/export/docx.py').is_file(),
                'python_files':files,'client_modules':modules,'copy':str(removed)}
    (removed/'removal-results.json').write_text(json.dumps(evidence,indent=2)+'\n')
    published = Path(os.environ.get('G7A_EVIDENCE_DIR', str(removed/'evidence'))) / 'docx-removed'
    published.mkdir(parents=True, exist_ok=True)
    (published/'removal-results.json').write_text(json.dumps(evidence,indent=2)+'\n')
    for log in removed.glob('*.log'):
        shutil.copy2(log, published/log.name)
