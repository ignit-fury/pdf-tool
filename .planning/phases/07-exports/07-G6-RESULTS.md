# Phase 7 — Local G6 results

Date: 2026-10-27. Final application source: `2bbebe2`; no deployment, package installation,
container setup or corpus mutation. All EXPO-01..05 are implemented; the consolidated checks below pass. Final independent goal verification passes 12/12 merged must-haves in
07-VERIFICATION.md, with all five EXPO requirements satisfied locally.

## Automated checks

| Check | Actual result |
|---|---|
| Consolidated Python local suite | 634 passed, 36 deselected, two existing warnings, 120.71s |
| `npm --prefix client test` | 140 passed, zero failed/skipped; exports tests included in standard glob |
| `npm --prefix client run build` |Passed in 1.91s; existing chunk-size advisory |
| `.venv/bin/python -m mypy engine server` | 35 source files clean |
| `.venv/bin/python -m pytest -q tests/test_gate_g4.py` | 7 passed, one existing deprecation warning, 95.02s; technical proxy only |
| Focused native/API/isolation/header/ephemerality | 45 passed before review; final native 14 and review 33 green after relevant fixes |
| Client license gate negatives | 19 passed; resolved runtime closure/bundled notices passed |
| Python runtime license closure |Passed |
| Unicode artifact check | 15.1.0 data current |

Logs:`/private/tmp/07-python-regression-final.log`,07-client-tests-final.log,
07-client-build-final.log,07-review-types-final.log,07-g4-regression-final.log.
Focused RED/GREEN and intermediate failure logs also remain in/private/tmp.
The consolidated selection is `-m 'not corpus and not linux_only and not cdn'`;
G4 is run explicitly because that selection excludes its corpus-marked proof.
No whole-corpus sweep or Linux/CDN execution is implied.

## Independent native gate

See 07-04-GATE-SUMMARY.md for full command, source provenance, tools, oracles
and negative controls. Actual production client split/ZIP plus isolated worker PDF
exports generated 7 PDFs / 13 mapped pages and one archive. All 14 qpdf/pdfcpu calls pass.
The 5-test gate passed in 5.96s and is included again in consolidated final regression.

- 39 same-engine checks:27 exact source/output, 9 exact independently painted flatten
 reference/output, 3 confined downsample comparisons. No tolerance for exact checks.
- 12 confined comparisons show zero changes outside independent annotation/image support;
 18 appearance-region comparisons prove actual filled text, state and transformed AP.
- 78 native rasters across PDFium/Poppler/MuPDF; unchanged siblings remain unmasked.
- ZIP names/count/order/CRC/headers/extracted bytes checked independently with Python zipfile.
- Corruption controls catch omitted/wrong-order pages, missing appearances, detached
 graph objects, changed siblings, unrelated pixels between regions and broken archives.
- All 8 constructed source/reference digests and original IRS Form 1040 digest preserved.
- Real IRS Form 1040 lossless compression: 220,237 → 200,250 bytes; both pages exact per engine.

Cross-engine results remain explicit: **27 pass/12 fail** at unchanged 8% threshold.
All 12 failures match unmodified source or independent-reference baselines. 29 pairs
also retain source-baseline raster-size disagreements, including UserUnit and pixel
rounding. These are not represented as 39 cross-engine passes or newly fixed renderers.

Artifacts:`/private/tmp/pdf-tool-phase7-g6-20261027/`, including gate-evidence.json.
Reference refinements use independent Form/image coverage rendered by each engine,
without mask padding, enclosing-box substitution or tolerance widening.

## Actual browser and network proof

Used the existing connected Playwright plugin, Chrome 156 on macOS, local app
http://127.0.0.1:8767/. No browser CLI/package/provider setup was added.
Before Open, the observer watches same-origin HTTP requests of every resource type,
excluding served/static /assets/ and favicon. Negative controls counted both a new
unknown fetch path and a navigation-type document request. Data/blob downloads do
not generate document API requests.

Raw sanitized observer records are preserved in
`/private/tmp/pdf-tool-phase7-browser-20261027/phase7-network-observations.json`:
13 journey records, actual method/path/type/body-byte counts, selected request hashes,
preview geometry/hashes and lifecycle outcomes. No PDF bodies or password headers
are in this JSON. Screenshots, input fixtures and 23 artifact digests remain alongside.

| Journey | Actual observation |
|---|---|
| Open, insert blank, PNG/JPEG/split/download |Zero API requests; analysis never chosen |
| Print PNG |1250×834 pixels for 300 × 200 pt page at 300 DPI |
| All-page JPEG ZIP |Two correctly named 625 × 417 JPEGs at 150 DPI; Python CRC/decode/count pass |
| Every-page split |Two 1-page PDFs and ZIP; current 2-page working PDF remains byte-exact; Undo stays available |
| Styled current source |Edit Hello world→Hi export, bold/color, then insert another blank page; all five server formats use current 3-page PDF |
| Text/Markdown/HTML |Exactly one /exports POST each, 7496 bytes; request SHA matches current download; new text present, old text absent, Markdown/HTML bold retained |
| Server PDF formats |Compress/flatten return 3-page PDFs, preserve working PDF byte-exact; one subsequent Undo returns 2 pages and clears prepared results |
| Downsample preview |Lossless checkbox default false; explicit selection changes one image; 6,292,232 → 735,448 bytes; exact Before/After canvases visible and download SHA equals prepared response |
| Responsive/focus |320/320 and 760/760 viewport/scroll widths; previews stack, controls visible; Tab focuses Prepare with solid outline |
| Late response/cancel/close |Actual server response held, Cancel produces zero links, Close/reopen cannot publish stale result; next document export succeeds |
| Layout HTML |Actual download rendered separately: heading, left column before right, bold/italic spans, one list item and 2 × 2 table read correctly |
| Filled forms flatten |Actual 3-page browser download has burnt saved appearances and no interactive form; native preview visibly retains FILLED/state/transforms |
| Unicode password |Local unlock makes zero API calls; explicit flatten receives correct password and returns a readable unlocked copy with visible notice |
| Signed rewrite |Prepare disabled until signature acknowledgement; then succeeds. Structural canary only, not cryptographic attestation |
| Unsafe appearance |Named UI refusal; zero prepared download links, current document preserved |
| Styled/rotated local export |PNG 417 × 625; split groups 1;2-3 yield 1+2 pages, retain Hi export/bold/rotation; zero API calls |
| Invalid groups |Overlapping 1-2;2 is rejected before dispatch |

Current3-page source and all text POST body hashes:
`fec4f75fff544d59a076d8acb1623ae2aa9c9e39b108228761fcde8dedea5078`.
Working2-page source before/after local exports:
`9cff9f3c8f5d62341e31fcccd7589152c86889ed1e0925ff3456c47ba8a44344`.
Downsample response and downloaded bytes:
`e9e4c2aab09d9b232b6950530a44257f6b318bafe5e39143f45a73401859e0d7`.

Nine actual browser PDF outputs pass 18 additional qpdf/pdfcpu validations; see
native-validation.json. Independent ZIP readback verifies actual downloaded archives.
Final mobile and rendered HTML screenshots were inspected; native-preview/pdfium_p0.png
was inspected for the actual filled flatten download. Observers/routes removed and
all documents closed. Local server remains available; it is not a deployment.

Two connector locator assumptions needed correction: Undo's accessible name was more
specific than its visible text, and Rotation90 appeared in both summary/inheritance
copy. Those harness errors did not undo/repeat completed mutations; subsequent precise
locators continued from observed state. Expected console HTTP errors were favicon404,
intentional unsafe-flatten422 and observer-control404; no app JavaScript exception seen.

## Review and limits

Independent source review: 35 files, no open findings; one blocker and six warnings
resolved. Main fix protects mask/alternate image roles globally, including direct
ExtGState containers and ordinary aliases. Other fixes cover list-prefix spans, actual
empty-text metadata, nonvacuous client extraction guards, typed limits and server error
messages. Original RED/intermediate logs remain; no assertion/limit was weakened.

Reading-order inference is conservative for horizontal layouts and complete axis-aligned
ruled grids; ambiguous layouts retain text/warnings. No OCR or pixel-faithful HTML claim.
Large-document/timeout/retention guards have automated coverage rather than every limit
being forced in the browser. This is Chromium proof, not fresh Safari/Firefox certification.

G3 Linux/container/live-CDN checks, G4 literal legal-contract specimen and production
HEIC confinement remain open. PDF/A and DOCX remain Phase 8. No deployment is authorized.
