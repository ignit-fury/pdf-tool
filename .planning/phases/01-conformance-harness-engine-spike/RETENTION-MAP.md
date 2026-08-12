# Retention Map — Document Byte Data Flow

**Date:** 2026-08-12
**Status:** Written before any infrastructure (venv, lockfile, CI, storage) is selected, per
ENG-06. Task 2 of this plan (project scaffold, AGPL gate) and all later phases must honor the
two decisions at the bottom of this document.

## Purpose

Enumerate every hop document bytes could traverse in the eventual hybrid client/server
architecture (per `ARCHITECTURE.md` and `PITFALLS.md` Pitfall 12), so that infrastructure choices
that are expensive to reverse — queue payload shape, scratch storage type — are made with the
full picture in view, not discovered after the fact.

## Hop Table

| Hop | Retains bytes? | For how long | Deletion mechanism | How to verify deletion |
|---|---|---|---|---|
| Browser (client) | Yes — authoritative copy | Session lifetime (tab open) | Tab close / navigation; no IndexedDB persistence | Manual: confirm no IndexedDB/localStorage entry after edit session; automated: assert no `indexedDB.databases()` entries containing document bytes in an e2e test |
| CDN (edge) | No, by policy | N/A — must never cache document routes | `Cache-Control: no-store, private` on every document response; explicit Cache Rule bypass for document paths; no `.pdf`/`.docx` extension in URL paths | CI/integration test asserting response headers on every document-bearing route; periodic check of CDN cache-rule config against route list |
| Load balancer / app ingress | No — passthrough only | 0 (in-flight only) | Nothing to delete; LB does not buffer to disk | Not independently testable; covered by "no object storage" and "no logs with content" controls below |
| App (FastAPI request handler) | Transient — in-process memory only, per request | Duration of the request | Buffers freed on request completion/exception (`finally`); no disk write in this hop | Unit test: exception mid-handler still frees buffers; process memory does not grow across repeated requests (leak test) |
| Queue (if/when a job queue exists — ARQ, per STACK.md, added only if a request exceeds timeout) | No — **opaque short-TTL handle only, never bytes** | Handle TTL only (minutes) | Handle expires; queue never holds an object-store key with long-lived credentials, only a content-hash reference resolvable via the same cache described below | CI canary test: enqueue a job, inspect queue payload (Redis `LRANGE`/`XRANGE` or ARQ job args), assert no document bytes and no long-lived credential present, only a bounded-TTL hash reference |
| Worker (background job processor) | Transient — same as app hop | Duration of job | Same buffer-free discipline as app hop | Same leak/exception test as app hop |
| Subprocess (veraPDF, poppler, LibreOffice — file-in/file-out sidecars) | Yes — reads/writes files by design | Duration of subprocess call | Explicit `unlink()` in a `finally` around every subprocess invocation; subprocess given a per-job scratch dir, not a shared one | Canary test: run a real subprocess conversion, assert the per-job scratch dir does not exist after the call returns (success or exception) |
| Scratch space | Yes, transiently — **tmpfs, not persistent volume** | Duration of the job that created it | tmpfs mount is memory-backed; per-job subdirectory removed in `finally`; container itself is ephemeral | Integration test: kill the container mid-job, confirm no bytes survive (tmpfs is wiped with the container); `mount` inspection in CI confirms scratch path is tmpfs, not a bind-mounted persistent volume |
| Object store | **No — not used for document bytes at all** | N/A | N/A — the architecture (ARCHITECTURE.md §3, Option C) uses a content-addressed, evictable in-RAM/tmpfs-backed cache instead of an object store for document bytes | Code review / dependency audit: no S3/R2/GCS client call ever receives document bytes; only the content-addressed cache does |
| Server cache (`sha256(bytes) → bytes`) | Yes, deliberately — this is the one designed retention point | Short TTL (e.g. `EX 900`) or LRU eviction, whichever comes first; evictable at any moment | TTL expiry or `maxmemory`+`allkeys-lru` eviction; backing store is tmpfs if it spills, never a persistent volume | Retention test (Pitfall 12): kill/evict the cache mid-session in CI and confirm the client session survives via the `409 {missing: [...]}` re-upload path |
| Response (server → client) | No | 0 — streamed, not buffered to disk | Bytes streamed directly to the response; no server-side copy retained beyond the cache entry above | Test: response streaming does not write to disk (strace/tmp dir check in CI) |
| CDN (response leg) | No, by policy | Same as ingress leg | Same `no-store` header applies to responses | Same header-assertion test as ingress leg |
| Browser (receiving edited/exported file) | Yes — user's own download | User's choice (their device) | Not our system's responsibility once downloaded | N/A — outside the trust boundary |
| Logs (cross-cutting) | No document content, ever | N/A | Log statements never include filenames, extracted text, or document bytes; only job IDs and content hashes (which are one-way and do not reveal content) | CI grep/static check: no `logger.*` call in engine modules interpolates a variable holding text/bytes; canary test greps actual log output for a unique marker string after a job runs |
| Error reporter (cross-cutting) | No document content, ever | N/A | `before_send` hook strips frame locals for engine modules; no attachments; no request bodies | Canary test: trigger a real exception in the engine with a marker string in the input, assert the captured event does not contain the marker |

## Decisions This Map Forces

These two conclusions are binding on Task 2 of this plan and on every later plan that touches
the queue or scratch storage. Both follow directly from the hop table above and from
`ARCHITECTURE.md` §3's resolution of Conflict #3, and from `PROJECT.md`'s Privacy constraint.

1. **Job queues carry an opaque short-TTL handle, never document bytes.** If/when a job queue
   (ARQ, per `research/STACK.md`) is introduced for conversions that exceed the request timeout,
   the payload placed on the queue MUST be a content-hash reference with a bounded TTL — never
   the document bytes themselves, and never an object-store key backed by a long-lived
   credential. A queue is durable state by construction; durable state holding document content
   is a retention window this product has explicitly promised not to have. Dead-letter queues,
   if used at all, must have zero retention or be omitted entirely, because they preferentially
   retain exactly the documents that caused errors.

2. **Scratch space is tmpfs, not a persistent object store, and the server cache is
   content-addressed and evictable at any moment.** No hop in this data flow writes document
   bytes to a persistent volume, a database, or an object store with a lifecycle-policy backstop.
   The only server-side retention point is the `sha256(bytes) → bytes` cache described in
   `ARCHITECTURE.md` §3 Option C, and it is designed to be lost at any time without breaking the
   session — the client holds the authoritative copy. This converts "the server has no state
   whose loss is observable" from a policy into a structural, testable property: killing the
   cache mid-session must not lose the user's work, only cost a re-upload.
