"""Ephemeral native HEIC boundary, deliberately separate from the PDF sandbox.

Only development codec execution is enabled. Production fails closed until a
separate native filesystem/network confinement boundary is reviewed and tested.
The parent imports neither Pillow nor a HEIF decoder.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from collections.abc import Iterator

MAX_INPUT_BYTES = 20 * 1024 * 1024
MAX_OUTPUT_BYTES = 64 * 1024 * 1024
MAX_PIXELS = 16_000_000
MAX_DIMENSION = 16_384
WALL_SECONDS = 20.0
CPU_SECONDS = 20
ADDRESS_BYTES = 1024 * 1024 * 1024
_CODES = ('IMAGE_CONVERSION_FAILED', 'INVALID_HEIC', 'IMAGE_LIMIT_EXCEEDED',
          'IMAGE_CONVERSION_TIMEOUT', 'HEIC_UNAVAILABLE')


class ImageConversionError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code if code in _CODES else 'IMAGE_CONVERSION_FAILED'
        super().__init__(self.code)


def _dimensions(width: int, height: int) -> None:
    if min(width, height) <= 0 or max(width, height) > MAX_DIMENSION or width * height > MAX_PIXELS:
        raise ImageConversionError('IMAGE_LIMIT_EXCEEDED')


def _boxes(data: bytes) -> Iterator[tuple[bytes, bytes]]:
    offset = count = 0
    while offset < len(data):
        if len(data) - offset < 8 or count >= 4096:
            raise ImageConversionError('INVALID_HEIC')
        size, kind = struct.unpack_from('>I4s', data, offset)
        header = 8
        if size == 1:
            if len(data) - offset < 16:
                raise ImageConversionError('INVALID_HEIC')
            size = struct.unpack_from('>Q', data, offset + 8)[0]
            header = 16
        elif size == 0:
            size = len(data) - offset
        if size < header or offset + size > len(data):
            raise ImageConversionError('INVALID_HEIC')
        yield kind, data[offset + header:offset + size]
        offset += size
        count += 1


def validate_heic(source: bytes) -> None:
    """Strict single-image subset; sequences, grids and ambiguous items refuse."""
    if len(source) > MAX_INPUT_BYTES:
        raise ImageConversionError('IMAGE_LIMIT_EXCEEDED')
    try:
        top = list(_boxes(source))
        if not top or top[0][0] != b'ftyp':
            raise ValueError
        brands = top[0][1]
        if len(brands) < 12 or len(brands) % 4 or brands[:4] not in (b'heic', b'heix', b'mif1'):
            raise ValueError
        compatible = {brands[n:n + 4] for n in range(8, len(brands), 4)} | {brands[:4]}
        if not compatible.intersection({b'heic', b'heix'}) or compatible.intersection({b'msf1', b'hevc', b'hevx', b'avif', b'avis'}):
            raise ValueError
        if any(kind not in (b'ftyp', b'meta', b'mdat', b'free', b'skip') for kind, _ in top):
            raise ValueError
        metas = [body for kind, body in top if kind == b'meta']
        if len(metas) != 1 or metas[0][:4] != b'\0' * 4:
            raise ValueError
        meta = list(_boxes(metas[0][4:]))
        primary: list[int] = []
        items: list[int] = []
        dimensions = 0
        for kind, body in meta:
            if kind == b'pitm':
                if body[:4] != b'\0' * 4 or len(body) != 6:
                    raise ValueError
                primary.append(int.from_bytes(body[4:], 'big'))
            elif kind == b'iinf':
                if body[:4] != b'\0' * 4:
                    raise ValueError
                entries = list(_boxes(body[6:]))
                if len(entries) != int.from_bytes(body[4:6], 'big'):
                    raise ValueError
                for entry_kind, entry in entries:
                    if entry_kind != b'infe' or len(entry) < 13 or entry[:4] != b'\x02\0\0\0' or entry[6:8] != b'\0\0':
                        raise ValueError
                    item_type = entry[8:12]
                    if item_type == b'hvc1':
                        items.append(int.from_bytes(entry[4:6], 'big'))
                    elif item_type not in (b'Exif', b'mime'):
                        raise ValueError
            elif kind == b'iprp':
                for prop_kind, prop in _boxes(body):
                    if prop_kind == b'ipco':
                        for property_kind, value in _boxes(prop):
                            if property_kind == b'ispe':
                                if len(value) != 12 or value[:4] != b'\0' * 4:
                                    raise ValueError
                                _dimensions(*struct.unpack('>II', value[4:]))
                                dimensions += 1
            elif kind in (b'ipro', b'iref'):
                # Auxiliary images, thumbnails, external/protected references:
                # refuse rather than silently selecting one frame.
                raise ValueError
            elif kind == b'dinf':
                for reference_kind, reference in _boxes(body):
                    if reference_kind != b'dref' or reference[:4] != b'\0' * 4:
                        raise ValueError
                    locations = list(_boxes(reference[8:]))
                    if len(locations) != int.from_bytes(reference[4:8], 'big') or any(
                        name != b'url ' or location != b'\0\0\0\x01' for name, location in locations):
                        raise ValueError
            elif kind == b'iloc':
                # The supported v0 layout has no construction methods or
                # external data references. More complex layouts refuse.
                if body[:4] != b'\0' * 4 or len(body) < 8:
                    raise ValueError
                offset_size, length_size = body[4] >> 4, body[4] & 15
                base_size = body[5] >> 4
                if any(size not in (0, 4, 8) for size in (offset_size, length_size, base_size)) or body[5] & 15:
                    raise ValueError
                cursor = 8
                count = int.from_bytes(body[6:8], 'big')
                if count > 256:
                    raise ValueError
                for _ in range(count):
                    if cursor + 6 + base_size > len(body) or body[cursor + 2:cursor + 4] != b'\0\0':
                        raise ValueError
                    cursor += 4 + base_size
                    extents = int.from_bytes(body[cursor:cursor + 2], 'big')
                    cursor += 2 + extents * (offset_size + length_size)
                    if extents > 256 or cursor > len(body):
                        raise ValueError
                if cursor != len(body):
                    raise ValueError
        if len(primary) != 1 or items != primary or dimensions != 1:
            raise ValueError
    except (ValueError, IndexError, struct.error):
        raise ImageConversionError('INVALID_HEIC') from None


def _codec() -> str | None:
    configured = os.environ.get('PDF_TOOL_HEIC_DECODER')
    candidates = ['/usr/bin/sips'] if sys.platform == 'darwin' else ['/usr/bin/heif-dec', '/usr/bin/heif-convert']
    if configured is not None:
        candidates = [configured] if configured in candidates else []
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file() and not path.is_symlink() and os.access(path, os.X_OK):
            return candidate
    return None


def _worker_command(codec: str, timeout: float) -> list[str]:
    return [sys.executable, '-I', str(Path(__file__).resolve()), '--worker', codec, str(timeout)]


def _png_header(path: Path) -> bytes:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ImageConversionError('IMAGE_CONVERSION_FAILED')
    if info.st_size > MAX_OUTPUT_BYTES:
        raise ImageConversionError('IMAGE_LIMIT_EXCEEDED')
    data = path.read_bytes()
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ImageConversionError('IMAGE_CONVERSION_FAILED')
    offset = 8
    seen_header = seen_data = False
    while offset + 12 <= len(data):
        length, kind = struct.unpack_from('>I4s', data, offset)
        end = offset + 12 + length
        if end > len(data):
            break
        value = data[offset + 8:end - 4]
        checksum = struct.unpack_from('>I', data, end - 4)[0]
        if zlib.crc32(kind + value) & 0xffffffff != checksum:
            break
        if not seen_header:
            if kind != b'IHDR' or length != 13:
                break
            _dimensions(*struct.unpack('>II', value[:8]))
            seen_header = True
        elif kind in (b'IHDR', b'acTL', b'fcTL', b'fdAT'):
            break
        if kind == b'IDAT':
            seen_data = True
        if kind == b'IEND':
            if length == 0 and end == len(data) and seen_data:
                return data
            break
        offset = end
    raise ImageConversionError('IMAGE_CONVERSION_FAILED')


def _validate_png(path: Path) -> None:
    """Run only in the resource-bounded child; decode every pixel, not just IHDR."""
    _png_header(path)
    from PIL import Image
    with Image.open(path) as image:
        if image.format != 'PNG' or getattr(image, 'n_frames', 1) != 1:
            raise ImageConversionError('IMAGE_CONVERSION_FAILED')
        _dimensions(*image.size)
        image.verify()
    with Image.open(path) as decoded:
        decoded.load()
        _dimensions(*decoded.size)


def _kill_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except PermissionError:
        # macOS can report EPERM for an already-reaped, empty group. A live
        # child must never be treated as terminated on this path.
        if process.poll() is None:
            raise
    process.wait()


def convert_heic(source: bytes, *, timeout: float = WALL_SECONDS) -> bytes:
    deadline = time.monotonic() + min(timeout, WALL_SECONDS)
    validate_heic(source)
    # No environment variable may assert unverified confinement into existence.
    if os.environ.get('PDF_TOOL_ENV') == 'production':
        raise ImageConversionError('HEIC_UNAVAILABLE')
    codec = _codec()
    if codec is None:
        raise ImageConversionError('HEIC_UNAVAILABLE')
    from server.isolation import _scratch_root
    try:
        with tempfile.TemporaryDirectory(prefix='heic-worker-', dir=_scratch_root()) as directory:
            scratch = Path(directory)
            (scratch / 'input.heic').write_bytes(source)
            environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
                           'TMPDIR': directory, 'TEMP': directory, 'TMP': directory, 'HOME': directory}
            process = subprocess.Popen(_worker_command(codec, max(0.001, deadline - time.monotonic())),
                cwd=scratch, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
            try:
                while True:
                    entries = list(scratch.iterdir())
                    for entry in entries:
                        info = entry.lstat()
                        if entry.name not in ('input.heic', 'output.png', 'probe.txt') or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                            raise ImageConversionError('IMAGE_CONVERSION_FAILED')
                        limit = MAX_INPUT_BYTES if entry.name == 'input.heic' else 65536 if entry.name == 'probe.txt' else MAX_OUTPUT_BYTES
                        if info.st_size > limit:
                            raise ImageConversionError('IMAGE_LIMIT_EXCEEDED')
                    if time.monotonic() >= deadline:
                        raise ImageConversionError('IMAGE_CONVERSION_TIMEOUT')
                    if process.poll() is not None:
                        break
                    time.sleep(0.01)
                if process.returncode:
                    code = _CODES[process.returncode - 10] if 10 <= process.returncode < 10 + len(_CODES) else 'IMAGE_CONVERSION_FAILED'
                    raise ImageConversionError(code)
                _kill_group(process)
                if any(entry.name not in ('input.heic', 'output.png', 'probe.txt') for entry in scratch.iterdir()):
                    raise ImageConversionError('IMAGE_CONVERSION_FAILED')
                return _png_header(scratch / 'output.png')
            finally:
                _kill_group(process)
    except ImageConversionError:
        raise
    except Exception:
        raise ImageConversionError('IMAGE_CONVERSION_FAILED') from None


def _worker(codec: str, timeout: float) -> None:
    import resource
    started = time.monotonic()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_OUTPUT_BYTES, MAX_OUTPUT_BYTES))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    if sys.platform == 'linux':
        resource.setrlimit(resource.RLIMIT_AS, (ADDRESS_BYTES, ADDRESS_BYTES))

    def run(argv: list[str], *, probe: bool = False) -> None:
        # All stages share one deadline. Native grandchildren inherit limits and
        # the parent's process group; never preexec_fn in the threaded server.
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            raise ImageConversionError('IMAGE_CONVERSION_TIMEOUT')
        with Path('probe.txt').open('wb') as output:
            result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=output if probe else subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, close_fds=True, timeout=remaining)
        if result.returncode:
            raise ImageConversionError('IMAGE_CONVERSION_FAILED')
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        own = resource.getrusage(resource.RUSAGE_SELF)
        remaining_cpu = CPU_SECONDS - usage.ru_utime - usage.ru_stime - own.ru_utime - own.ru_stime
        if remaining_cpu <= 0:
            raise ImageConversionError('IMAGE_LIMIT_EXCEEDED')
        soft, hard = resource.getrlimit(resource.RLIMIT_CPU)
        resource.setrlimit(resource.RLIMIT_CPU, (min(soft, max(1, math.ceil(remaining_cpu))), hard))

    if codec == '/usr/bin/sips':
        run([codec, '-g', 'pixelWidth', '-g', 'pixelHeight', 'input.heic'], probe=True)
        probe = Path('probe.txt').read_text()
        values = {line.split(':')[0].strip(): line.split(':')[1].strip() for line in probe.splitlines() if ':' in line}
        try:
            _dimensions(int(values['pixelWidth']), int(values['pixelHeight']))
        except (KeyError, ValueError):
            raise ImageConversionError('INVALID_HEIC') from None
        run([codec, '-s', 'format', 'png', 'input.heic', '--out', 'output.png'])
    elif codec in ('/usr/bin/heif-dec', '/usr/bin/heif-convert') and sys.platform == 'linux':
        # Legacy executable is accepted only after a bounded real invocation;
        # output validation is the capability probe, never file existence.
        run([codec, 'input.heic', 'output.png'])
    else:
        raise ImageConversionError('HEIC_UNAVAILABLE')
    _validate_png(Path('output.png'))


if __name__ == '__main__':
    try:
        if len(sys.argv) != 4 or sys.argv[1] != '--worker':
            raise ImageConversionError('HEIC_UNAVAILABLE')
        _worker(sys.argv[2], float(sys.argv[3]))
    except subprocess.TimeoutExpired:
        sys.exit(13)
    except ImageConversionError as error:
        sys.exit(10 + _CODES.index(error.code))
    except BaseException:
        sys.exit(10)
