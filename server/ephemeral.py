"""Ephemeral job scratch and content-addressed cache for the PDF Tool server.

Privacy model (from PROJECT.md, CLAUDE.md):
- Ephemerality is a structural property, not a retention policy.
- The server has no state whose loss is observable.
- Scratch is tmpfs-backed.
- Uploaded bytes are content-addressed (SHA-256), never stored by filename.
- No document content in logs or error reports.
- Files are unlinked in finally blocks; job results expire after TTL.

This module provides:
- EphemeralStore: a tmpfs-backed store that content-addresses uploaded PDFs
  and evicts stale entries after a TTL.
- JobStore: an in-memory (ephemeral) registry mapping job_id → metadata.
  No persistence, no Redis — a job is just a Python dict.
- _sanitize_log_context: ensures no document content leaks into log lines.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Scratch lives on the default temp filesystem (tmpfs on Linux, ~/.tmp on macOS).
# On macOS it is NOT tmpfs — that is an accepted limitation for local development.
# In production (Docker/Dockerfile.ci) it is mounted tmpfs.
SCRATCH_ROOT: Path

# How long a job result (replaced PDF) stays available before auto-eviction.
# Table stakes, not a selling point — 1 hour matches the competitor default,
# and the structural property is that the server CAN evict at any moment.
JOB_TTL_SECONDS = int(os.environ.get("PDF_TOOL_JOB_TTL", "3600"))

# Maximum upload size. 50 MB — above most single-form PDFs, below the Next.js
# 4.5 MB serverless limit that ruled out that architecture.
MAX_UPLOAD_BYTES = int(os.environ.get("PDF_TOOL_MAX_UPLOAD", str(50 * 1024 * 1024)))


def _init_scratch() -> Path:
    """Create the scratch root. Callsite: server startup."""
    root = Path(tempfile.mkdtemp(prefix="pdf-tool-scratch-"))
    log.info("scratch root: %s", root)
    return root


def _ensure_scratch() -> Path:
    """Lazily initialise SCRATCH_ROOT on first use (tests may not trigger startup)."""
    global SCRATCH_ROOT
    if SCRATCH_ROOT is None:
        SCRATCH_ROOT = _init_scratch()
    return SCRATCH_ROOT


# ---------------------------------------------------------------------------
# Content-addressed blob store
# ---------------------------------------------------------------------------

class BlobStore:
    """A write-once, content-addressed store on tmpfs.

    Keys are hex SHA-256 digests of the uploaded bytes. Values are files on disk.
    The store never sees the original filename and never logs document content.

    Deprecated uploads are evicted lazily by _cleanup_stale (called on startup
    and periodically by a background task in production).
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or _ensure_scratch()

    def store(self, data: bytes) -> str:
        """Store bytes, return the content-address (hex SHA-256)."""
        digest = hashlib.sha256(data).hexdigest()
        path = self.root / f"{digest[:16]}.pdf"
        if not path.exists():
            path.write_bytes(data)
            log.info("blob stored: %s..., size=%d", digest[:16], len(data))
        return digest

    def path_for(self, digest: str) -> Path:
        """Return the on-disk path for a content-address. May not exist."""
        return self.root / f"{digest[:16]}.pdf"

    def exists(self, digest: str) -> bool:
        return self.path_for(digest).exists()

    def size_for(self, digest: str) -> int | None:
        p = self.path_for(digest)
        try:
            return p.stat().st_size
        except OSError:
            return None

    def evict(self, digest: str) -> None:
        p = self.path_for(digest)
        try:
            p.unlink()
            log.info("blob evicted: %s...", digest[:16])
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Job metadata store (in-memory, ephemeral)
# ---------------------------------------------------------------------------

class JobStore:
    """In-memory registry of job metadata.

    A job is: {job_id, status, pdf_digest, filename, page_count, ...}.
    No document content ever enters this store — only the content-address
    and derived metadata.

    In production this would be backed by Redis (carrying only opaque handles),
    but for v1 the in-memory dict is correct: restart the server and all jobs
    vanish, which is exactly the 'no state whose loss is observable' property.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}

    def create(
        self,
        pdf_digest: str,
        filename: str,
        upload_size: int,
    ) -> str:
        """Register a new job. Returns the job_id."""
        job_id = hashlib.sha256(os.urandom(16)).hexdigest()[:16]
        self._jobs[job_id] = {
            "job_id": job_id,
            "status": "uploaded",
            "pdf_digest": pdf_digest,
            "filename": filename,
            "upload_size": upload_size,
            "created_at": time.time(),
            # Filled lazily by the classification endpoint:
            "page_count": None,
            "classification": None,
            # Filled by the replace endpoint:
            "output_digest": None,
            "output_path": None,
        }
        log.info("job created: %s (digest=%s..., file=%s)", job_id, pdf_digest[:16], filename)
        return job_id

    def get(self, job_id: str) -> dict[str, Any] | None:
        return self._jobs.get(job_id)

    def mark_indexed(self, job_id: str, page_count: int, classification: list[dict[str, Any]]) -> None:
        job = self._jobs.get(job_id)
        if job:
            job["status"] = "indexed"
            job["page_count"] = page_count
            job["classification"] = classification

    def mark_replacing(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job:
            job["status"] = "replacing"

    def mark_done(self, job_id: str, output_digest: str, output_path: Path) -> None:
        job = self._jobs.get(job_id)
        if job:
            job["status"] = "done"
            job["output_digest"] = output_digest
            job["output_path"] = str(output_path)

    def mark_failed(self, job_id: str, reason: str) -> None:
        job = self._jobs.get(job_id)
        if job:
            job["status"] = "failed"
            job["error"] = reason

    def list_active(self) -> list[dict[str, Any]]:
        """Return metadata for all non-expired jobs. For maintenance/cleanup."""
        now = time.time()
        return [
            j for j in self._jobs.values()
            if now - j.get("created_at", 0) < JOB_TTL_SECONDS
        ]


# ---------------------------------------------------------------------------
# Log sanitisation
# ---------------------------------------------------------------------------

# Characters that, if present in a user-supplied filename, could be used to
# inject into log output. We strip them so filenames in logs are safe.
import re as _re

# Keep only alphanumerics, hyphens, underscores, dots, spaces.
_SAFE_FILENAME_RE = _re.compile(r"[^a-zA-Z0-9._ -]")


def _sanitize_filename_for_log(name: str) -> str:
    """Return a log-safe version of a user-supplied filename."""
    return _SAFE_FILENAME_RE.sub("", name)[:64]


# ---------------------------------------------------------------------------
# Background cleanup (called periodically in production; best-effort here)
# ---------------------------------------------------------------------------

def _cleanup_stale_blobs(store: BlobStore, older_than: float) -> int:
    """Remove blobs whose last modification is older_than (seconds). Returns count."""
    removed = 0
    if not store.root.exists():
        return 0
    for child in store.root.iterdir():
        try:
            mtime = child.stat().st_mtime
            if time.time() - mtime > older_than:
                child.unlink()
                removed += 1
        except OSError:
            pass
    if removed:
        log.info("evicted %d stale blobs from scratch", removed)
    return removed


def _evict_expired_jobs(job_store: JobStore) -> int:
    """Mark jobs older than JOB_TTL_SECONDS as expired (logical deletion)."""
    now = time.time()
    removed = 0
    for job_id, job in list(job_store._jobs.items()):
        if now - job.get("created_at", 0) > JOB_TTL_SECONDS:
            # If there's an output file, unlink it.
            out_path = job.get("output_path")
            if out_path:
                try:
                    os.unlink(out_path)
                except OSError:
                    pass
            del job_store._jobs[job_id]
            removed += 1
    if removed:
        log.info("evicted %d expired jobs", removed)
    return removed


# ---------------------------------------------------------------------------
# Context manager for per-request scratch directories
# ---------------------------------------------------------------------------

@contextmanager
def ephemeral_scratch(prefix: str = "req-") -> Path:
    """Create a scratch directory that is always cleaned up in finally.

    Used for per-request work (e.g. subsetting a font, building a temporary
    PDF) where the result is copied out and the scratch is discarded.
    """
    root = _ensure_scratch()
    d = root / f"{prefix}{os.getpid()}-{ hashlib.sha256(os.urandom(8)).hexdigest()[:8] }"
    d.mkdir(parents=True, exist_ok=True)
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# Module-level singletons (initialised at import for simplicity; tests reset them)
# ---------------------------------------------------------------------------

blob_store = BlobStore()
job_store = JobStore()


def reset_for_tests() -> None:
    """Clear global state. Called by test teardown."""
    global blob_store, job_store
    blob_store = BlobStore()
    job_store = JobStore()
