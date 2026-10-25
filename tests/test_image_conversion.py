"""Native image boundary: real codec smoke plus controlled hostile children."""
from __future__ import annotations

import importlib.util
import io
import os
from pathlib import Path
import struct
import subprocess
import sys

import pytest
from PIL import Image


def box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack('>I4s', 8 + len(payload), kind) + payload


def heic(width: int = 2, height: int = 3, *, count: int = 1) -> bytes:
    entries = b''.join(box(b'infe', b'\x02\0\0\0' + struct.pack('>HH', n + 1, 0) + b'hvc1image\0') for n in range(count))
    meta = box(b'pitm', b'\0' * 4 + b'\0\x01')
    meta += box(b'iinf', b'\0' * 4 + struct.pack('>H', count) + entries)
    meta += box(b'iprp', box(b'ipco', box(b'ispe', b'\0' * 4 + struct.pack('>II', width, height))))
    return box(b'ftyp', b'heic\0\0\0\0heicmif1') + box(b'meta', b'\0' * 4 + meta) + box(b'mdat', b'fake')


def png() -> bytes:
    stream = io.BytesIO()
    Image.new('RGB', (2, 3), 'red').save(stream, format='PNG')
    return stream.getvalue()


def test_converter_boundary_exists() -> None:
    assert importlib.util.find_spec('server.image_conversion') is not None


@pytest.fixture
def conversion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from server import image_conversion as module
    monkeypatch.setenv('PDF_TOOL_SCRATCH_ROOT', str(tmp_path))
    monkeypatch.delenv('PDF_TOOL_ENV', raising=False)
    return module


@pytest.mark.parametrize('data,code', [(b'not heic', 'INVALID_HEIC'),
    (heic(16385, 1), 'IMAGE_LIMIT_EXCEEDED'), (heic(5000, 5000), 'IMAGE_LIMIT_EXCEEDED'),
    (heic(count=2), 'INVALID_HEIC'), (b'x' * (20 * 1024 * 1024 + 1), 'IMAGE_LIMIT_EXCEEDED')])
def test_preflight_rejects_before_launch(conversion, monkeypatch, tmp_path, data, code):
    monkeypatch.setattr(conversion, '_worker_command', lambda *_: pytest.fail('launched'))
    with pytest.raises(conversion.ImageConversionError) as caught:
        conversion.convert_heic(data)
    assert caught.value.code == code
    assert str(caught.value) == code
    assert list(tmp_path.iterdir()) == []


def test_production_fails_closed_even_with_codec(conversion, monkeypatch, tmp_path):
    monkeypatch.setenv('PDF_TOOL_ENV', 'production')
    with pytest.raises(conversion.ImageConversionError) as caught:
        conversion.convert_heic(heic())
    assert caught.value.code == 'HEIC_UNAVAILABLE'
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('script,code', [
    ('import time; time.sleep(10)', 'IMAGE_CONVERSION_TIMEOUT'),
    ('import sys; print("private-content",file=sys.stderr); sys.exit(42)', 'IMAGE_CONVERSION_FAILED'),
    ('from pathlib import Path; Path("output.png").symlink_to("input.heic")', 'IMAGE_CONVERSION_FAILED'),
    ('from pathlib import Path; Path("output.png").write_bytes(b"\\x89PNG\\r\\n\\x1a\\n")', 'IMAGE_CONVERSION_FAILED'),
    ('from pathlib import Path; Path("output.png").write_bytes(b"x"*2048)', 'IMAGE_LIMIT_EXCEEDED'),
    ('from pathlib import Path; Path("extra.png").write_bytes(b"private")', 'IMAGE_CONVERSION_FAILED'),
])
def test_hostile_child_cleanup(conversion, monkeypatch, tmp_path, script, code):
    monkeypatch.setattr(conversion, '_codec', lambda: '/usr/bin/sips')
    monkeypatch.setattr(conversion, '_worker_command', lambda *_: [sys.executable, '-c', script])
    monkeypatch.setattr(conversion, 'MAX_OUTPUT_BYTES', 1024)
    with pytest.raises(conversion.ImageConversionError) as caught:
        conversion.convert_heic(heic(), timeout=0.15)
    assert caught.value.code == code
    assert 'private' not in str(caught.value)
    assert list(tmp_path.iterdir()) == []


def test_missing_decoder_is_unavailable(conversion, monkeypatch):
    monkeypatch.setattr(conversion, '_codec', lambda: None)
    with pytest.raises(conversion.ImageConversionError, match='^HEIC_UNAVAILABLE$'):
        conversion.convert_heic(heic())


def test_png_requires_complete_decode(conversion, tmp_path):
    target = tmp_path / 'output.png'
    target.write_bytes(png()[:-14])
    with pytest.raises(conversion.ImageConversionError):
        conversion._validate_png(target)
    target.write_bytes(png())
    conversion._validate_png(target)


@pytest.mark.skipif(sys.platform != 'darwin' or not Path('/usr/bin/sips').exists(), reason='installed macOS codec')
def test_real_native_heic_roundtrip(conversion, tmp_path):
    # No downloaded fixture or decoder library: use the installed OS encoder.
    fixture = tmp_path.parent / (tmp_path.name + '.heic')
    original = tmp_path.parent / (tmp_path.name + '.png')
    try:
        original.write_bytes(png())
        result = subprocess.run(['/usr/bin/sips', '-s', 'format', 'heic', str(original), '--out', str(fixture)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        assert result.returncode == 0 and fixture.is_file(), 'installed codec failed its real capability probe'
        output = conversion.convert_heic(fixture.read_bytes())
        with Image.open(io.BytesIO(output)) as image:
            image.load()
            assert image.size == (2, 3)
        assert list(tmp_path.iterdir()) == []
    finally:
        original.unlink(missing_ok=True)
        fixture.unlink(missing_ok=True)
