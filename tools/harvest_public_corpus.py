#!/usr/bin/env python3
"""Harvest real, wild-harvested PDFs from public corpora into the public tier (ENG-01).

Gate G0 requires a combined corpus of >=100 documents. Plan 01-02 sourced the first 17, but 10 of
those came from just two producers (7 IRS, 3 veraPDF fixtures). Document *count* is a proxy; the
thing that actually matters for Phase 2 is **producer diversity** — the forward-encoding decision
table has >=5 branches selected by the /Symbolic flag, /Encoding presence, and which cmap subtables
the embedded font carries, and those branches are exercised by variety of generator, not by volume.
A hundred files from one producer exercise one code path.

Primary source is govdocs1 (digitalcorpora.org): ~1M real files scraped from US government web
servers, released for forensics research, public domain. It is the right source precisely because
nobody curated it for prettiness — it is what real producers actually emit.

govdocs1 ships as 1000 zip "threads" of ~486MB each and does not expose individual files over HTTP.
Downloading a whole thread to keep ~20 PDFs is wasteful, so this module reads the ZIP central
directory via HTTP range requests and fetches only the member entries it actually wants. That turns
a 486MB download into tens of MB.

Category labels are NEVER taken from a source description — every entry's categories come from
tools/probe_corpus.probe_file(), D-04's independent structural verifier. If the prober disagrees
with an expectation, the prober is right.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import probe_corpus  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
CORPUS_DIR = REPO_ROOT / "corpus" / "public"
MANIFEST_PATH = REPO_ROOT / "corpus" / "manifest.json"

# A decompression bomb or a 200MB scan is not worth committing to git-lfs forever.
MAX_PDF_BYTES = 12 * 1024 * 1024
MIN_PDF_BYTES = 512

GOVDOCS1_THREAD_URL = (
    "https://digitalcorpora.s3.amazonaws.com/corpora/files/govdocs1/zipfiles/{thread:03d}.zip"
)
GOVDOCS1_LICENSE = "Public domain - US government documents, digitalcorpora.org govdocs1 research corpus"

USER_AGENT = "pdf-tool-corpus-harvester/1.0 (+https://github.com/; research corpus assembly)"


class HttpRangeFile(io.RawIOBase):
    """A seekable read-only file over HTTP range requests.

    Enough of the file protocol for `zipfile.ZipFile` to read a central directory and then extract
    individual members without downloading the whole archive.

    Uses `curl` rather than `urllib`: this interpreter ships no CA bundle (``load_default_certs()``
    finds zero certificates on this platform), so ``urllib`` fails every HTTPS request with
    CERTIFICATE_VERIFY_FAILED. curl uses the system trust store and verifies correctly. Shelling out
    keeps certificate verification ON — the alternative fix, an unverified SSL context, would
    silently accept a MITM, and this code writes what it downloads straight into the repository.
    """

    def __init__(self, url: str, timeout: int = 60) -> None:
        self.url = url
        self.timeout = timeout
        self._pos = 0
        self._size = self._head_size()

    def _curl(self, *extra: str) -> bytes:
        cmd = [
            "curl", "-sL", "--fail", "--max-time", str(self.timeout),
            "-A", USER_AGENT, *extra, self.url,
        ]
        proc = subprocess.run(cmd, capture_output=True)
        if proc.returncode != 0:
            raise OSError(f"curl failed ({proc.returncode}) for {self.url}")
        return proc.stdout

    def _head_size(self) -> int:
        cmd = [
            "curl", "-sIL", "--fail", "--max-time", str(self.timeout),
            "-A", USER_AGENT, self.url,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise OSError(f"curl HEAD failed ({proc.returncode}) for {self.url}")
        sizes = re.findall(r"(?im)^content-length:\s*(\d+)", proc.stdout)
        if not sizes:
            raise OSError(f"no Content-Length for {self.url}; cannot range-read")
        return int(sizes[-1])

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            self._pos = offset
        elif whence == io.SEEK_CUR:
            self._pos += offset
        elif whence == io.SEEK_END:
            self._pos = self._size + offset
        self._pos = max(0, min(self._pos, self._size))
        return self._pos

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = self._size - self._pos
        if size == 0 or self._pos >= self._size:
            return b""
        end = min(self._pos + size, self._size) - 1
        data = self._curl("-r", f"{self._pos}-{end}")
        self._pos += len(data)
        return data

    def readinto(self, b) -> int:  # type: ignore[override]
        data = self.read(len(b))
        b[: len(data)] = data
        return len(data)


def is_real_pdf(data: bytes) -> bool:
    """Magic-byte check. A redirect page or an HTML error saved as .pdf is not a PDF."""
    return data.startswith(b"%PDF-")


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def producer_of(pdf_path: Path) -> str:
    """Read /Producer (falling back to /Creator) — the diversity axis this harvest selects on."""
    try:
        import pikepdf

        with pikepdf.open(str(pdf_path)) as pdf:
            info = pdf.docinfo if hasattr(pdf, "docinfo") else {}
            for key in ("/Producer", "/Creator"):
                val = info.get(key)
                if val:
                    return _normalize_producer(str(val))
    except Exception:
        pass
    return "unknown"


def _normalize_producer(raw: str) -> str:
    """Collapse version noise so 'Distiller 9.0' and 'Distiller 10.1' count as one producer."""
    s = re.sub(r"[\d.]+", "", raw).strip(" -_/()")
    s = re.sub(r"\s+", " ", s)
    return (s or "unknown").lower()[:60]


@dataclass
class HarvestState:
    entries: list[dict] = field(default_factory=list)
    producers: dict[str, int] = field(default_factory=dict)
    seen_hashes: set[str] = field(default_factory=set)
    seen_names: set[str] = field(default_factory=set)

    @classmethod
    def load(cls) -> HarvestState:
        entries = json.loads(MANIFEST_PATH.read_text())
        st = cls(entries=entries)
        for e in entries:
            st.seen_hashes.add(e["sha256"])
            st.seen_names.add(e["filename"])
        for p in CORPUS_DIR.glob("*.pdf"):
            st.producers[producer_of(p)] = st.producers.get(producer_of(p), 0) + 1
        return st

    def producer_cap(self, target_total: int, max_share: float = 0.15) -> int:
        return max(2, int(target_total * max_share))

    def save(self) -> None:
        MANIFEST_PATH.write_text(json.dumps(self.entries, indent=2) + "\n")


def harvest_from_thread(
    state: HarvestState,
    thread: int,
    want: int,
    target_total: int,
    verbose: bool = True,
) -> int:
    """Pull up to `want` diverse PDFs out of one govdocs1 thread. Returns how many were added."""
    url = GOVDOCS1_THREAD_URL.format(thread=thread)
    added = 0
    cap = state.producer_cap(target_total)
    try:
        zf = zipfile.ZipFile(HttpRangeFile(url))
    except Exception as exc:  # noqa: BLE001
        print(f"  thread {thread:03d}: unreachable ({exc})", file=sys.stderr)
        return 0

    names = [n for n in zf.namelist() if n.lower().endswith(".pdf")]
    for name in names:
        if added >= want:
            break
        try:
            info = zf.getinfo(name)
            if not (MIN_PDF_BYTES <= info.file_size <= MAX_PDF_BYTES):
                continue
            data = zf.read(name)
        except Exception:
            continue

        if not is_real_pdf(data):
            continue
        digest = sha256_of(data)
        if digest in state.seen_hashes:
            continue

        stem = Path(name).stem
        filename = f"govdocs1_{thread:03d}_{stem}.pdf"
        if filename in state.seen_names:
            continue

        dest = CORPUS_DIR / filename
        dest.write_bytes(data)

        prod = producer_of(dest)
        if state.producers.get(prod, 0) >= cap:
            dest.unlink()
            continue

        try:
            categories = sorted(probe_corpus.probe_file(str(dest)))
        except Exception:
            dest.unlink()
            continue
        if not categories:
            dest.unlink()
            continue

        state.entries.append(
            {
                "filename": filename,
                "sha256": digest,
                "tier": "public",
                "categories": categories,
                "source_url": url + f"#{name}",
                "license": GOVDOCS1_LICENSE,
                "weight_class": "other",
                "notes": f"govdocs1 thread {thread:03d}, member {name}. Producer: {prod}. "
                "Categories assigned by tools/probe_corpus.probe_file(), not by source description.",
            }
        )
        state.seen_hashes.add(digest)
        state.seen_names.add(filename)
        state.producers[prod] = state.producers.get(prod, 0) + 1
        added += 1
        if verbose:
            print(f"  + {filename}  [{prod}]  {','.join(categories)}")
    return added


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--threads", default="0", help="comma-separated govdocs1 thread numbers")
    ap.add_argument("--want", type=int, default=20, help="max documents to add from each thread")
    ap.add_argument("--target-total", type=int, default=100, help="Gate G0 floor, for producer cap")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    state = HarvestState.load()
    start = len(state.entries)
    for t in [int(x) for x in args.threads.split(",") if x.strip()]:
        got = harvest_from_thread(
            state, t, args.want, args.target_total, verbose=not args.quiet
        )
        print(f"thread {t:03d}: added {got}")
    state.save()
    print(f"manifest: {start} -> {len(state.entries)} documents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
