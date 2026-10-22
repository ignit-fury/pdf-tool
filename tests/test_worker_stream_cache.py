"""Page response construction must not decompress a stream again for every run."""
import io
import sys

import pikepdf

from server import isolation
from tools.build_security_fixtures import text_pdf


def test_page_metadata_reads_each_stream_once(monkeypatch) -> None:
    with pikepdf.open(io.BytesIO(text_pdf())) as pdf:
        pdf.pages[0].Contents = pdf.make_stream(
            b'BT /F1 12 Tf 20 150 Td (First) Tj 0 -30 Td (Second) Tj 0 -30 Td (Third) Tj ET')
        output = io.BytesIO()
        pdf.save(output)
    runner = (
        'import inspect\n'
        'import engine.classify_run as module\n'
        'original=module.stream_bytes_and_resources\n'
        'reads=[]\n'
        'def counted(*args,**kwargs):\n'
        ' if inspect.currentframe().f_back.f_code.co_name == "_execute":\n'
        '  reads.append((args[1],args[2],args[3]))\n'
        '  if len(reads)>1: raise AssertionError("repeated_response_stream_decode")\n'
        ' return original(*args,**kwargs)\n'
        'module.stream_bytes_and_resources=counted\n'
        'from server.worker import main\n'
        'main()\n'
    )
    monkeypatch.setattr(isolation, '_worker_command', lambda: [sys.executable, '-c', runner])
    result = isolation.run_worker('page', output.getvalue(), page=0)
    assert result.get('error') is None, result
    assert len(result['runs']) == 3
