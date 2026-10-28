# Phase 8 pre-conversion validator baseline

Recorded 2026-10-28 before the PDF/A converter exists. No deployment or container
setup. Public corpus files remain unchanged.

## Validator

- Official CLI release: veraPDF Greenfield **1.30.3** (2026-10-07).
- Archive: <https://software.verapdf.org/rel/1.30/verapdf-greenfield-1.30.3-installer.zip>.
- SHA-256: `b512bf24945503a33fc10738ecffc1f2dccaaf8593a448e94ee9ac86a9559a59`.
- Detached archive signature verified with the signing fingerprint documented at
  <https://docs.verapdf.org/install/>:
  `13DD102B4DD69354D12DE5A83184863278B17FE7`. GPG reports a good signature;
  the public key was retrieved from Ubuntu's keyserver, not assigned local trust.
- CLI-only installation: `/private/tmp/pdf-tool-phase8-tools/verapdf`.
- Existing Java: `/Library/Java/JavaVirtualMachines/temurin-26.jdk/Contents/Home`;
  `--version` and actual validation work locally. No JRE installed.
- CLI and installer state dual GPLv3+/MPLv2+. Dev/CI subprocess only; no new
  runtime dependency and no parser, JVM or validator in request handling.

## Unmodified public sources

Command: `verapdf --flavour 2b --format json <13 original paths>` via a bounded
Python subprocess with the above JAVA_HOME. Result: **13 jobs, 1 compliant,
12 noncompliant, zero parsing/encryption/OOM/vera exceptions**, exit **1**, 4.93s.
The compliant source is `verapdf_type3_font_fixture.pdf`. This baseline does not
predict converter success; positive conversion floors must be fixed separately.

Selection: first three open, unencrypted files with at most 30 pages per manifest
risk category (annotation appearances, Type3, CID-keyed CFF, Identity-H, inline
images, subset fonts, OCR scans, outlined vectors), in manifest order, deduplicated.
No OCR-tagged file meets that page cap. Exact selected filenames, source hashes and
page counts are in `baseline-selection.json`; this is a stratified sample, not all
217 public documents.

Raw evidence: `/private/tmp/pdf-tool-phase8-g7a-20261028/` contains the selection,
`baseline-raw.json`, stderr, and the negative-control report. The source manifest's
hashes identify the immutable inputs. These temporary local artifacts are not a
claim of a hosted CI run.

## Report contract and corrected observation

JSON uses `report.jobs[].validationResult[].compliant`, not `isCompliant`.
Check every job, the explicit profile, `jobEndStatus`, rule summaries, and batch
failure/count fields. Missing reports or resource/parser failures must fail closed.
The known inline-image negative fails rule **6.1.10-1**, with `compliant: false`
and direct-process exit **1** (`negative-smoke-exit.json`). An earlier shell
observation of zero was the following `head` command's exit, not veraPDF's; it was
corrected before planning/implementation. No exit-zero-invalid behavior is claimed.

## What was NOT tested

No converted output, constructed-positive floor, Linux/hosted CI run or native
fidelity gate has been evaluated here. No PDF/A or DOCX product feature exists yet.
