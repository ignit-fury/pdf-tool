---
phase: 8
slug: pdf-a-then-docx
status: approved
reviewed_at: "2026-10-28T02:26:00Z"
shadcn_initialized: false
preset: none
created: 2026-10-28
---

# Phase 8 — UI Design Contract

Scope: EXPO-06/07/08. Inherit the Phase 7 Export panel; PDF/A-2b is delivered and gated before optional DOCX. No deployment is authorized by this contract.

## Design System

| Property | Value |
|---|---|
| Tool | none — established manual CSS system; preserve it, no shadcn initialization |
| Preset | not applicable |
| Component library | Existing React/native HTML controls in `client/src/exports/ExportPanel.jsx` |
| Icon library | none; labeled text controls |
| Font | Existing `Avenir Next, Avenir, Segoe UI, Arial, sans-serif` |

Sources: `08-CONTEXT.md` D-8.1–D-8.6, `08-RESEARCH.md`, EXPO requirements, `07-UI-SPEC.md`, current `ExportPanel.jsx`, `controller.mjs`, `style.css`, and approved `06-UI-SPEC.md`. Current CSS supersedes Phase 7's prose reference to teal. No `components.json` exists; the established manual system resolves the shadcn gate. Unspecified interaction choices below are agent defaults, not new user decisions.

## Spacing Scale

| Token | Value | Usage |
|---|---|---|
| xs / sm | 4px / 8px | Inline gaps / label-to-control and button gaps |
| md / lg | 16px / 24px | Form sections / result section separation |
| xl / 2xl / 3xl | 32px / 48px / 64px | Inherited scale; no new large gaps |

Keep existing inspector dimensions and padding. Controls retain 44px minimum touch height; checkbox labels provide a 44×44px target. Borders (1px) and focus strokes (2px) are not spacing tokens. Do not globally retune legacy CSS.

## Typography

| Role | Size | Weight | Line height |
|---|---|---|---|
| Body | 13px | 400 | 1.5 |
| Label | 12px | 600 | 1.5 |
| Heading | 16px | 600 | 1.3 |
| Display | 16px | 600 | 1.3 — reuse Heading |

Exactly three sizes and two weights for additions; supporting copy uses 12px/400 and buttons 12px/600. Inherit existing export location badges; do not introduce additional typography tokens. Counts use tabular numerals. Wrap long errors instead of shrinking text.

## Color

| Role | Value | Usage |
|---|---|---|
| Dominant (60%) | `#ffffff` | Inspector, forms, review and result surfaces |
| Secondary (30%) | `#edf0f4` | Existing workstation; retain `#f5f7fa` supporting surfaces |
| Accent (10%) | `#2458df` | Current panel selector, primary action, checked controls, keyboard focus |
| Destructive | `#994333` | Existing error/refusal text; no destructive action added |

Accent reserved for the named elements, never warning panels or all links. Reuse body `#243248`, support `#52647f`, and border `--line: #d9e0e9`. Percentages describe visual balance. Warning/error meaning always appears in words; retain existing neutral section treatment.

## Layout and Interaction Contract

1. Reuse Export's Format select, server badge, privacy paragraph, inline review, busy/cancel and download region. Append **PDF/A-2b** and then **DOCX (best effort)** only as their capabilities become available. Preserve all Phase 7 formats and default Compressed PDF. Removing DOCX must leave PDF/A and every existing export usable.
2. Local PDF/A development availability follows reproducible validation of the complete fixed G7a corpus, positive floor and negative controls. Until that local proof, keep its option omitted and do not integrate a reachable server route. Public release additionally requires the mandatory corpus gate passing in CI; writing the workflow is not proof that hosted CI ran. Record local and hosted evidence separately. veraPDF is dev/CI-only: no per-request validator, “validated this file” badge, or universal certification claim. Do not add a runtime certification registry or metadata-only conversion path.
3. Opening Export or selecting a format initiates no upload, analysis or conversion. Each server CTA discloses the upload before activation. Export uses the exact current PDF revision, including the established pending-edit materialization path where needed. It never replaces editor bytes or creates an Undo entry.
4. PDF/A uses **Prepare PDF/A-2b**, then **Download PDF/A-2b** only after a matching successful response. Show returned safe-remediation notices; unsupported content is refused with a bounded reason. Never silently substitute arbitrary fonts or offer a failed candidate under the archival label. No conformance-level picker.
5. DOCX requires G7b's written ceiling before implementation: single-column body text, headings by font-size clustering, bold/italic, inline images, ruled tables only; everything else becomes plain paragraphs. Exclude unruled-table reconstruction, multi-column reading order, reconstructed headers/footers and round-trip editing. Show the concise limitations below before inspection.
6. DOCX has two explicit actions. **Review DOCX warnings** uploads/analyzes current bytes and returns a document-specific review, without producing DOCX. It consumes the shared Phase 7 block analysis from the Phase 2 text model; no second parse or separate scan for warning generation. **Convert to DOCX** appears only after that review is visible and requires a separate click. Conversion consumes the same analyzed block output used for the warning, bound to the current revision. No automatic conversion after inspection or acknowledgement.
7. Review heading is **Review this document before conversion**. Render a plain-text list of actual detected limitations with counts and affected pages where available. Separate supported ruled tables from unsupported features; never imply every detected table degrades. Do not invent counts, infer absence from missing metadata, or show document text/snippets unnecessarily. Missing/invalid review data blocks conversion; a stale review requires another explicit review action. Bind the acknowledgement to source, full output projection and policy digests; no receipt secret, expiry service or document cache is needed for this warning flow.
8. Reuse signature acknowledgement for PDF/A rewrites and any pending PDF rewrite before DOCX; block until acknowledged when required. DOCX separately states that digital signatures are not carried into Word. Protected input uses the existing in-memory password mechanism and a visible unlocked-output notice. Password errors expose a labeled password retry or the existing unlock flow without discarding the open PDF; no automatic password retry loop, persistence or password echo.
9. Shared lifecycle: idle → working → ready/error; DOCX adds reviewing → review-ready → converting → ready. Disable conflicting mutations while export owns busy state and retain **Cancel export**. Cancel, close/unmount, format/options change, document replacement, byte/version change or Undo aborts the operation, invalidates review/results, revokes Blob URLs and ignores late responses. Reopening starts idle; an old review cannot authorize new bytes. Cancellation returns focus to the initiating CTA.
10. Worker busy, timeout, limits, unsupported content, malformed responses and network errors show bounded inline errors with an explicit retry action. No raw exception, paths, PDF text or passwords. Preserve current bytes, protection and all history on success, error and cancellation; export downloads are separate copies. Apply existing output/memory admission checks before allocation and download-link publication.

## Copywriting Contract

| Element | Exact copy |
|---|---|
| Server disclosure | This action uploads the current PDF to the server to prepare a download. Exports keep your current PDF and Undo history. |
| DOCX inspection disclosure | Reviewing DOCX warnings uploads the current PDF to the server. Conversion starts only when you choose Convert to DOCX. |
| PDF/A guidance | Prepare an archival PDF/A-2b copy. Content that cannot be converted safely will be refused. |
| DOCX guidance | DOCX is best effort. Single-column text, headings, bold/italic, inline images and ruled tables are supported. Other content becomes plain paragraphs. Columns, headers and footers are not reconstructed. |
| Empty heading / body | No PDF open / Choose a PDF to prepare an export. |
| Review example, only when detected | 1 two-column section detected on page 3. Column reading order will not be preserved. |
| Table warning, actual count/pages | {N} unruled tables detected on pages {pages}. Table structure will become plain paragraphs. |
| No detected limitation | No additional layout limitations were detected. DOCX remains best effort; review the downloaded document. |
| No text | No extractable text was found. Scanned pages need OCR, which is not included. |
| Signature / encryption | DOCX does not preserve PDF digital signatures. / This export is an unlocked copy. Your open document keeps its original protection. |
| PDF/A refusal | This PDF cannot be converted safely to PDF/A-2b. {Safe reason} Download the current PDF or try another document. |
| Review failure | DOCX warnings could not be prepared. Your PDF and Undo history are unchanged. Choose Review DOCX warnings to try again. |
| Timeout / busy | The export took too long. Try a smaller document. / The server is busy. Try the export again shortly. |
| Password errors | A password is required to export this PDF. Enter its password and try again. / The document password was not accepted. Check it and try again. |
| Generic failure | This export could not be completed. Your current PDF and Undo history are unchanged. Try again. |
| Working / ready | Reviewing DOCX warnings… / Preparing PDF/A-2b… / Converting to DOCX… / Export ready |
| Download / cancellation | Download PDF/A-2b / Download DOCX / Cancel export |
| Destructive confirmation | None; exports create separate copies. Reuse the existing signature acknowledgement when a PDF rewrite is required. |

## Accessibility and Responsive Behavior

Keep the native labeled select, buttons, checkbox and download anchors. Associate disclosures and review with their CTA via `aria-describedby`; warning headings and lists remain semantic HTML. Announce progress/review/results with `aria-live="polite"`, failures with `role="alert"`; no invented percentage progress. On review completion, focus its `tabIndex="-1"` heading before the Convert button; on success/error focus the existing result/error heading. If invalidation removes the focused content, restore focus to Format or its initiating CTA. Preserve 2px cobalt focus outlines with 2px offset and keyboard access. No new modal or focus trap. At 320px and 760px, fields/actions/warning lists wrap within the inspector without horizontal overflow; the viewer/rail keep their existing responsive layout.

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|---|---|---|
| none | none; existing native components only | Not applicable — no registry code introduced, confirmed 2026-10-28 |

## Checker Sign-Off

The primary export action is the idle-state visual anchor. For DOCX, the
document-specific warning review becomes the anchor before conversion.

- [x] Copywriting, visuals, color, typography, spacing and registry safety verified.
**Approval:** approved by `phase8_ui_check`; its non-blocking visual-anchor
recommendation is incorporated above. This contract does not assert G7a/G7b completion.
