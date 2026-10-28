# G7 — Integrated local results

**2026-10-29: all six plans delivered and locally verified. Hosted G7a CI is pending.**
This is neither a deployment nor a public-release sign-off.

## PDF/A and the frozen gate

G7b ceiling commit `60dd243` and the frozen 31-input baseline predate product
implementation. The baseline remains one compliant, 29 noncompliant and one
deliberate malformed-parser failure; it was never reported as a converter pass.

Authenticated veraPDF 1.30.3 verifies all twelve required positives, one public
vector PDF and three supplementary cases at PDF/A-2b. Sixteen outputs/19 pages
pass **57 exact same-engine comparisons and 32 structural validations**. Of 57
cross-engine comparisons, 55 pass and two match existing source-baseline failures.
Sources, positive floor and tolerances are unchanged. All 18 unsupported frozen
inputs refuse safely. Detailed support policy: `08-G7A-RESULTS.md`.

The final integrated run repeats G7a and literal DOCX-removal proof:

```sh
PATH="$PWD/.venv/bin:$PATH" \
JAVA_HOME=/Library/Java/JavaVirtualMachines/temurin-26.jdk/Contents/Home \
VERAPDF_CMD=/private/tmp/pdf-tool-phase8-tools/verapdf/verapdf \
G7A_EVIDENCE_DIR=/private/tmp/pdf-tool-phase8-integrated-final \
.venv/bin/python -m pytest -q tests/test_gate_g7a.py tests/test_docx_cuttable.py
```

**7 passed in 39.37s**. Scratch removal additionally runs **134 Python tests**
(all other export units, G6 and G7a), **22 client export tests** and production
build. A deliberately unconditional import fails its negative control. Capability
becomes false, DOCX returns 503, text returns 200 and normal startup survives.
The original writer is never deleted. Nested native/validator reports and logs
are published under `docx-removed/` for CI artifact collection.

## Actual browser and downloaded artifacts

Local Chromium at `http://127.0.0.1:8767/`; existing Playwright connector used
because Prima/provider configuration is unavailable. No installation/deployment.
Earlier actual archival PDF downloads and native validation remain recorded in
`08-03-SUMMARY.md`.

- Selecting DOCX sends only a zero-body capability GET. Each explicit Review
  and Convert sends the same current PDF bytes in its own request. No eager
  upload/conversion occurs. The separate conversion header matches the reviewed
  source SHA-256, full snapshot SHA-256 and policy=1.
- Three-page layout source: 1,869 bytes, SHA-256
  `035839bcd7b055bf052948e7307e01f4cbd6b178079cc5b503c257a20dbd15ac`.
  Review identifies column-like page 1 and no text on page 3; one ruled table is
  kept. Actual download is 2,468 bytes, SHA-256
  `39a8f1d509890497faf341cb17af99dbd8ec345ebfeaf5ec14a65d28a9e29040`.
  ZIP CRC and all XML/relationships parse; table and inline image are present.
  Column fallback follows source page-position order rather than inferred columns.
- After browser-local blank insertion, the current four-page PDF is 2,052 bytes,
  SHA-256 `4d46a405dc1a92d3c4f1a8a7b6a935c5dc113a3cbf7630db9541f9d2912bf27f`.
  A new review identifies both no-text pages. Actual DOCX is 2,467 bytes, SHA-256
  `bd91613d7ec75578ebd30c6105fa9140409d17807d702ec3b1d25535732e634f`.
  Current PDF downloads before/after export are byte-identical. Original download
  is also byte-identical. Undo removes the stale review/download and requires a
  new Review action. Exports add no Undo entry.
- Held actual review and conversion responses are canceled separately. Neither
  publishes a link; Convert is absent and focus returns to Review. Unit checks
  additionally exercise changed session/bytes/revision/options and malformed facts.
- Unicode-password input unlocks locally; explicit review/conversion succeed and
  the unlocked-copy notice is visible. The DOCX has the same table/image/text
  projection as the unencrypted source. No password header/body is stored in logs.
- A structural signature canary shows the existing signed-source warning and
  explicit signature-not-carried notice. This is not cryptographic validation.
  A clean single-column source has no extra layout-loss facts; actual XML contains
  Heading1, bold and italic. macOS textutil reads the actual downloaded DOCX.
- Simulated capability=false disables Review while PNG remains enabled. At
  320px/760px, viewport and document scroll widths match. The 320px screenshot
  was visually inspected; review heading focus and native keyboard controls work.

Five actual DOCX downloads pass CRC, safe ZIP path and XML checks. Full sanitized
request observations, screenshots, files and `download-validation.json` are in
`/private/tmp/pdf-tool-phase8-docx-browser-20261029/`. Native gate outputs are in
`/private/tmp/pdf-tool-phase8-integrated-final/`. These are local temporary
artifacts; checked-in tests and this report preserve the reproducible procedure.

## Final regression and source checks

| Check | Observed result |
|---|---|
| Python, `python -m pytest -q -m 'not corpus and not linux_only and not cdn'` | 754 passed; six sandbox-denied OS checks; 39 deselected |
| Affected complete files outside sandbox: `tests/test_fetch_private_corpus.py tests/test_image_conversion.py` | 26 passed; all six failures resolved without code changes |
| Full client, `npm --prefix client test` | 147 passed |
| `python -m mypy engine/ server/` | 38 files, no issues |
| Production build | Passed; existing bundle-size advisory |
| Python/client runtime license gates | Both passed |
| Client license negative controls | 19 passed |
| Python license controls (included in broad run) | 3 passed |
| `python tools/build_search_unicode.py --check` | Unicode 15.1.0 data current |
| `git diff --check` | Passed |

The broad run did not have a zero-failure exit: four mock HTTP fixtures could not
bind loopback, one descendant check could not execute `/bin/ps`, and macOS sips
could not encode its test fixture under the sandbox. The 26-test OS rerun passes
outside it. Together they exercise all 760 selected tests successfully; raw
failure and rerun logs are retained separately. An earlier direct launcher used
an old Documents-path virtualenv; rerunning via this checkout's `python -m` fixes
that environment error without installing anything. No failures were waived.

Logs: `/private/tmp/08-full-python-final.log`, `08-os-tests-final.log`,
`08-full-client-final.log`, `08-g7-integrated-final.log`, `08-types-final.log`,
`08-build-final.log`, `08-license-final.log`, `08-client-license-final.log`,
`08-client-license-tests.log` and `08-unicode-final.log`.

## Outstanding checks

- Hosted mandatory G7a workflow has been authored, not executed/observed. EXPO-06
  retains this explicit CI acceptance item. Both complete gate files are assigned
  to that authenticated job, including negative/sensitivity controls.
- Word/Acrobat are unavailable; their visual observations are unperformed. ZIP/XML,
  native PDF validators and textutil do not substitute for those applications.
- G3 Linux/container/live CDN, G4 literal contract specimens and production HEIC
  confinement remain open. HEIC remains disabled in production until confined.
- No deployment, container-tool setup, runtime package or source-corpus change.
