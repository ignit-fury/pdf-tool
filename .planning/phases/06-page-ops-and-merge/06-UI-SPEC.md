---
phase: 6
slug: page-ops-and-merge
status: approved
reviewed_at: 2026-10-25T08:36:45Z
shadcn_initialized: false
preset: none
created: 2026-10-24
---

# Phase 6 — UI Design Contract

> PAGE-01..PAGE-09, including the settled HEIC server-conversion exception. Reuse the existing document workstation. Work locally; deployment and prior release/specimen checks remain open.

## Design System

| Property | Value |
|---|---|
| Tool | none — existing manual CSS design system |
| Preset | not applicable |
| Component library | React and native HTML controls already in the client |
| Icon library | none; labeled text buttons, existing arrows with accessible names |
| Font | `Avenir Next, Avenir, Segoe UI, Arial, sans-serif` |

Evidence: current `client/src/{App.jsx,Viewer.jsx,session.mjs,style.css}`, approved `05-UI-SPEC.md`, PAGE requirements and `06-CONTEXT.md` including amendments. No `components.json` exists. The established manual system and current instruction to preserve it resolve the shadcn gate: do not initialize shadcn or add registry blocks, dependencies, fonts, or an aesthetic redesign.

Decisions D-6.1..D-6.7 and A-6.1..A-6.6 are upstream. Local-first opening, explicit text-analysis entry, current-page controls, numeric placement, white image compositing, last-page protection, and the defaults below are implementation choices made for this phase; they are not represented as user-confirmed preferences. Current Phase 4/5 code supersedes the old research's absent-SPA assumptions. New reusable page tools live under `client/src/pageOps/`.

## Spacing Scale

| Token | Value | Usage |
|---|---:|---|
| xs | 4px | Related inline metadata |
| sm | 8px | Labels, control gaps, wrapping button groups |
| md | 16px | Form groups, compact panel padding, review padding |
| lg | 24px | Panel sections and normal panel padding |
| xl | 32px | Reserved separation between major review sections |
| 2xl | 48px | Empty-state vertical space |
| 3xl | 64px | Reserved; no new large page-level gap |

Exceptions: 1px borders and 2px focus outlines are strokes. New controls have at least 44px touch height; checkbox labels have at least a 44×44px hit area. Keep existing workspace/rail/viewer dimensions. Do not globally retune legacy CSS.

## Typography

Exactly three sizes and two weights for new controls:

| Role | Size | Weight | Line height |
|---|---:|---:|---:|
| Body | 14px | 400 | 1.5 |
| Label | 12px | 600 | 1.5 |
| Heading | 16px | 600 | 1.2 |
| Display | 16px | 600 | 1.2 — same token as Heading |

Supporting copy and badges use 12px/400; buttons use 12px/600. Page dimensions/counts use tabular numerals. Long names and errors wrap; do not shrink them. PDF artwork keeps its own typography.

## Color

| Role | Value | Usage |
|---|---|---|
| Dominant (60%) | `#ffffff` | Panel, controls, review surfaces, document paper |
| Secondary (30%) | `#edf0f4` | Workstation background; retain existing `#e3e8ef` viewer and `#f5f7fa` rail/section fills |
| Accent (10%) | `#2458df` | Current panel selector, primary operation CTA, checked controls, keyboard focus and placement-preview outline |
| Destructive | `#994333` | Delete confirmation/action and failure text, always with explicit words |

Reuse `--navy: #182840`, body `#243248`, `--muted: #667489`, `--line: #d9e0e9`; supporting copy needing stronger contrast uses `#52647f`. Accent is reserved for the elements named above, not every action or entire cards. Use 1px whole borders and existing pale fills; no thick colored card side borders. Status is always stated in text.

## Layout and Component Inventory

1. Preserve rail → viewer → inspector. Add **Pages** to the existing inspector's native button group beside **Text inspector** and **Find and replace**, using `aria-pressed`. Pages is the initial panel. No fourth workspace column, modal page organizer, new navigation shell or draggable-only interaction.
   The current PDF page remains the primary visual anchor. Within Pages, only the
   currently actionable operation or commit CTA receives primary treatment.
2. Opening a PDF renders locally. Rail visibility, selecting pages, native browser find, zoom, page tools and download must not initiate document API requests. Before analysis, thumbnail supporting text is **Page tools available**, not a guessed text classification. Once text analysis is explicitly requested, reuse actual classification badges.
3. Pages panel order: heading/location; selected-page summary; blank insertion; move/rotate/delete; **Merge PDF**; **Add image**; active import/placement review; local/server disclosure. The current thumbnail remains the selection mechanism. Page controls do not depend on editable/scanned/outlined classifications.
4. Selected-page summary shows `Page {P} of {N}`, source page size `{W} × {H} pt`, and `Rotation {R}°`. Use the actual page rectangle, including nonzero origins, without silently resetting it. Product copy describes size/rotation; internal object names, hashes and run IDs do not enter the flow.
5. Blank insertion has **Insert before** and **Insert after**. Selecting any thumbnail makes every document position reachable. Show adjacent-page inheritance before the action. Move has **Move earlier**, **Move later**, a labeled native **Move to position** numeric field (1..N), and **Move page**. Edge actions are disabled at their limits. Rotation is **Rotate clockwise 90°**, with the current absolute rotation visible.
6. Merge review shows selected filename, imported-page count, insertion position (1..N+1), page-size policy, bookmark outcome and form-field outcome before **Add {N} pages**. Default insertion is after the current page. **Match imported pages to the current page size** is unchecked; enabling it updates the review with the target dimensions and explicitly states that imported pages will be resized. The unselected default preserves each imported page's size and rotation.
7. Image review shows filename, decoded size, destination choices **New page** (default) and **Current page**. New page matches the selected adjacent page's size/rotation and fits the image without cropping or distortion; show those exact dimensions before commit. Existing-page placement uses the numeric fields below and an actual draft preview. **Add image page** and **Place image** are separate destination-specific CTAs.
8. Existing-page placement exposes **Left (pt)**, **Top (pt)**, **Width (pt)** and **Height (pt)**. Coordinates are measured from the top-left of the visible, rotated/cropped page; display its visible dimensions. **Lock aspect ratio** is a visible native checkbox, checked by default. Editing width updates height and vice versa while locked; position remains independent. Reject nonfinite/zero/negative dimensions and rectangles outside the visible page with inline advice. The default rectangle contains the image centered on the visible page. No modifier key is required.
9. A draft placement rectangle/thumbnail preview is temporary interaction feedback. Committing writes the image as real PDF page content. It is not a white-box replacement path for text. Transparent input is composited on white, and the preview/copy must show that outcome before commit. Draft field changes never create history entries or modify download bytes.
10. For HEIC, choosing a file opens a disclosure/review first. **Convert HEIC** with a **Server** badge is an explicit separate action; only that image is uploaded. The PDF and its password are not sent with conversion. After successful conversion, use the same local add/place controls. No HEIC upload on selection, keystroke, or destination change.

## Copywriting Contract

| Element | Copy |
|---|---|
| Pages heading | `Page tools` with `Browser` badge |
| Welcome privacy | `Open and organize PDFs in your browser. Text analysis and text edits use the server. HEIC conversion uploads only the selected image when you choose Convert.` |
| Local session disclosure | `Page changes and PDF download stay in this browser. Text analysis uses the server; HEIC conversion is a separate server action.` |
| Unanalyzed text panel | `Analyze text to edit it` / `This uploads the current PDF for classification and text edits. Page tools work without uploading.` |
| Text-analysis CTA | `Analyze text` with `Server` badge |
| Local password prompt | `Unlock this PDF` / `Enter the document password to view and organize it in this browser.` |
| Password handling help | `Kept in memory while this document is open. Sent to the server only if you choose text analysis.` |
| Local encrypted-edit notice | `Local edits save an unlocked copy. Your untouched original retains its password protection.` |
| Blank inheritance | `Blank page will match page {P}: {W} × {H} pt, rotation {R}°.` |
| Blank success | `Blank page inserted at position {P}. Undo restores the previous document.` |
| Move success | `Page moved from {A} to {B}.` |
| Rotation success | `Page {P} rotated to {R}°.` |
| Delete first action | `Delete page` |
| Delete confirmation | `Delete page {P}?` / `This removes the selected page. You can restore it with one Undo.` / `Keep page` / `Delete page {P}` |
| Last-page protection | `Keep at least one page in this document.` |
| Merge choose CTA | `Merge PDF` with `Browser` badge |
| Default merge size | `Keep each imported page's size and rotation.` |
| Explicit normalization | `Imported pages will be resized to {W} × {H} pt. Check the preview before adding them.` |
| Bookmarks present | `Bookmarks will be nested under “{filename}”.` |
| Bookmarks absent | `No bookmarks to merge.` |
| No imported forms | `No form fields in the imported PDF.` |
| Imported forms, no collisions | `{N} form fields will be kept with the “{prefix}” name prefix. No duplicate names found.` |
| Imported forms, collisions | `{N} form fields will be kept with the “{prefix}” name prefix. {C} duplicate names will be renamed.` |
| Unsupported form merge | `This PDF's form fields cannot be merged safely. Choose another PDF; your current document is unchanged.` |
| Signed imported PDF | `Merging this PDF invalidates its signatures.` / `I understand that merging invalidates the imported PDF's signatures.` |
| Merge success | `Added {N} pages from {filename}. Undo restores the previous document.` Follow with the actual bookmark/form outcome, including the no-fields/no-bookmarks case. |
| Image transparency | `Transparent areas will be white in the PDF.` |
| New image page | `New page will match page {P}: {W} × {H} pt, rotation {R}°. The image will fit without cropping.` |
| Placement help | `Position is measured from the top-left of the visible page. 72 pt = 1 inch.` |
| Placement validation | `Enter a positive width and height and keep the image inside the visible page.` |
| HEIC disclosure | `Convert this HEIC image on the server? Only the selected image is uploaded. The converted image is returned to this browser for placement.` |
| HEIC progress | `Converting HEIC on the server…` |
| HEIC unavailable | `HEIC conversion is unavailable here. Choose PNG, JPEG or WebP, or retry when conversion is available.` |
| Local operation progress | `Preparing pages in this browser…` |
| Image decode error | `This image could not be opened. Choose a supported PNG, JPEG, WebP or HEIC image.` |
| General local failure | `The page change could not be completed. Your document is unchanged. Try again or choose a smaller file.` |
| Import/placement cancellation | `Discard import` / `Discard placement` — discards the named draft without changing the PDF. Pending HEIC uses `Dismiss conversion`; it dismisses the draft, without claiming to terminate server work. |
| Undo / success | `Undo {last action}` with `Browser` or actual existing text-replay `Server` badge / `Previous document restored.` |
| Empty document state | `Open a PDF to organize its pages.` / `Choose a PDF to insert, move, rotate, delete or merge pages.` |

Keep existing signed-document warning and acknowledgement visible. All local mutation CTAs are disabled until local signature detection completes and, for signed PDFs, acknowledgement is checked. Imported signed PDFs require their own disclosed acknowledgement before merge. Original-byte download remains available and keeps its signature/encryption bytes. Do not claim edited copies preserve digital signatures. Local encrypted rewrite disclosure must appear before the first rewrite; it applies to the page-operation output, not a guessed statement about all existing server edits.

## Interaction, History and Failure Contract

- Opening defaults to local viewing/Pages. Merely selecting Text inspector or Find and replace shows the analysis gate when the current document has not been analyzed; only **Analyze text** starts upload. After that action, retain the existing real indexing, classification, text editing and search behavior. Never present old text run addresses as current after a structural page change.
- Local page edits act on the currently visible materialized PDF, including prior successful text edits. After commit, invalidate stale text indexes/previews and show `Page changes updated this PDF. Analyze text again to edit its current pages.` A later text analysis uses the current bytes; this boundary must not discard prior visible edits or old undo snapshots.
- Each committed insert, move, rotate, delete, PDF merge or image add/place is one whole-document undo unit. One Undo/Ctrl/Cmd+Z restores the exact prior bytes and text/style/page state, including encryption where those prior bytes had it. Native input undo remains native. No-op move, draft changes, cancelled imports and failed conversions add no history entry.
- Prepare output and the replacement viewer before publishing page count, bytes, download and history. Keep the current viewer/download on failure. Use the existing single mutation owner across text and page work; duplicate submission cannot commit twice. Show real stage text and `aria-busy`, not fabricated percentages or elapsed-time promises.
- Navigation may show the existing document while work prepares, but every transaction captures its target document/page identity. Closing or opening a different document invalidates pending work. Late local/HEIC/text completions cannot modify the new document, expose an old password or clear a newer operation's busy state. Dismiss conversion invalidates the pending draft/generation; it does not claim that an already-running server converter was terminated.
- Selecting a different page with an image draft updates the destination summary and recalculates its visible-page rectangle; require the updated draft before placement. Never reuse an old page's coordinates on a new rotated/cropped destination.
- After move/rotate, select the same physical page at its new position. After deletion, select the next surviving page at that position, otherwise the previous page. Undo restores the prior selection. Successful mutations announce one concise result and restore focus to the relevant panel control/heading when its previous control disappeared.
- Delete confirmation is inline in the panel, not a second full-screen modal. Initial Delete opens it without mutating. Keep page restores focus to Delete; confirmed deletion is one undo unit. Disable final-page deletion and show the last-page explanation adjacent to it.
- PDF imports use Discard import, image placement drafts use Discard placement, and pending HEIC conversion uses Dismiss conversion. Keep validation beside the affected field, link it with `aria-describedby`, and use one alert for operation failures. Filenames are text, never HTML; wrap long names. Do not log decoded document text or display internal parser traces.
- Memory/file-limit refusals must leave current bytes, history and download intact and identify a retry path. If undo retention has a bounded history policy, explain the actual boundary before accepting a mutation that would discard retained entries; do not silently clear history to make an operation succeed.

## Responsive and Accessibility Contract

- Retain the existing 294px desktop, 265px compact and 330px wide inspector widths. At 760px and below keep the stacked rail → viewer → inspector order. At 320px, new forms fit the viewport with 16px panel padding; no form-level horizontal scrolling. The PDF canvas may retain its existing independent scroll region.
- Panel selectors and grouped actions wrap. Numeric geometry fields use a two-column grid only while each labeled input remains usable; stack to one column at narrow widths. Native file input buttons and destination/size choices remain reachable without pointer dragging. No nested buttons inside thumbnail buttons.
- Page actions, imports and placement work entirely with keyboard. Native checkbox Space, button Enter/Space and numeric inputs retain native behavior. Every new control has a visible label and a 2px cobalt focus outline with 2px offset. Do not override Ctrl/Cmd+F or input Ctrl/Cmd+Z.
- Tabs use the existing labeled button-group/`aria-pressed` pattern. Opening a panel focuses its heading/first relevant control; returning to a thumbnail retains the selected page. Use one polite result summary; do not announce every keystroke or rerender. Errors use one alert, without duplicated toast speech. Respect reduced-motion CSS; no animation or smooth-scroll requirement.

## Registry Safety

| Registry | Blocks used | Safety gate |
|---|---|---|
| none | none | Not applicable — existing native/manual design system and no new registry or UI dependency; source inspected 2026-10-24 |

## Required Verification Evidence

Planner assigns an owning task and dated `06-G5-RESULTS.md` evidence for: observed zero document API traffic from local open through page edits/download (HEIC explicitly excluded); explicit analysis transition; blank inheritance visible before insertion; keyboard reorder/delete/Undo on scanned pages; merge size/outline/form notices on both collision and no-collision paths; actual same-font/different-subset three-renderer outputs; visibly checked aspect lock and correct rotated/cropped placement; transparent-image result; explicit HEIC upload and safe failure; mixed text/page history; signatures/encrypted-copy disclosure; close/stale work; 320px/760px/focus checks. Unit/structural tests alone do not certify the observed-network or visible-affordance claims.

No G3 Linux/container/CDN or G4 literal-contract check is closed by this UI contract. No deployment is authorized.

## Checker Sign-Off

- [x] Dimension 1 Copywriting: PASS
- [x] Dimension 2 Visuals: PASS
- [x] Dimension 3 Color: PASS
- [x] Dimension 4 Typography: PASS
- [x] Dimension 5 Spacing: PASS
- [x] Dimension 6 Registry Safety: PASS

**Approval:** UI checker passed all six dimensions after the specific dismissal
labels and explicit visual-anchor/primary-action priorities were added. This is
the automated design-contract check, not a claim of user acceptance or deployment.
