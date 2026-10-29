# Viewer upgrade stage 2 — native text boxes

The next authorized phase implements independent text insertion and reliable
multiline layout for explicitly owned text containers. It extends the existing
viewer and native engine, without pretending arbitrary source PDFs support reflow.

Insert text creates a transparent native PDF text block, not an annotation or a
white cover. Existing text editing continues through original server-issued run
IDs. New blocks use bundled Liberation Sans/Serif/Mono, subset Type0 fonts and
searchable Unicode from the existing font pipeline. The page's unrelated content,
forms, annotations and image resources remain intact. Preview and commit are
distinct: preview returns an actual candidate PDF; Apply publishes those exact
validated bytes as one mixed-history snapshot in the browser.

New blocks support explicit newlines, word/token wrapping, numeric font-size
growth/shrink, bold/italic, color, character spacing, line-height multiplier,
paragraph spacing and left/center/right alignment. Layout uses serialized glyph
widths and bounded coordinates. Overflow refuses with numeric required-height
feedback; Expand to fit increases this container only when it remains in-page.
It never moves other source content or silently clips/discards text.

Placement is in physical points from the visible page top-left. Native page
geometry honors effective CropBox/MediaBox, quarter rotation and UserUnit.
Default overlap protection checks the destination against actual rendered source
pixels plus annotation bounds, excluding the selected owned block during edit.
Nonwhite backgrounds/visible content may conservatively refuse. An explicit
Allow overlap control permits intentional transparent overprinting only; it never
erases underlying content. This is newly inserted content, not a fallback for
ordinary source text replacement.

Each block is an isolated content stream with bounded versioned metadata, its
specification, resource identity and content/font proof. Read/update/remove must
verify the complete owned drawing, including bounded Flate decoding. Untrusted,
unknown or modified ownership refuses rather than deleting source content. Shared
font resources are retained. Reopened blocks remain editable when verified.

API: bounded JSON POST `/jobs/{job_id}/text-box` reuses the existing transient
content-addressed source cache and isolated worker action `text-box`; the existing
recipe byte transport carries the finite text-box specification. No new storage,
header payload protocol, runtime library, larger limits or relaxed sandbox/CSP.
Client explicitly uploads CURRENT materialized PDF bytes for this operation using
a separate browser-held source/retry context; it must not accidentally send the
immutable pre-edit recipe source. Unicode passwords and cache-loss recovery reuse
the established transport. Signed changes require acknowledgement.

Operations are `list`, `upsert` and `remove`. Engine exports
`prepare_text_box(pdf, source, payload) -> dict[str, object]`, returning plain
JSON-safe transport data. Exact envelopes and finite errors are tested jointly.
Success upsert/remove returns `ok`, `source_hash`, `pdf` (base64), `page_index`,
`boxes`, `layout`, `notices`. List returns `ok`, `source_hash`, `boxes`.
Layout refusal returns `ok=false`, `source_hash`, `code`, `required_height`,
`available_height`; no candidate PDF. `source_hash` binds every response to the
uploaded bytes. `boxes` contain id/page_index/rect/text/style; never parser objects.

Upsert input: operation, page_index, optional id, text (1..10000 chars), rect
{left,top,width,height}, style {font_family,font_size,bold,italic,color,
character_spacing,line_spacing,paragraph_spacing,alignment}, allow_overlap=false.
Style defaults: Sans,12,false,false,[0,0,0],0,1.2,0,left. Bounds: size1..512,
character spacing0..10, line spacing1..3, paragraph spacing0..144. Unsafe glyph
coverage/shaping/RTL/control characters refuse explicitly. At most200 owned boxes,
2000 pages and48MiB output. No arbitrary source run reflow or automatic page flow.

UI uses the established contextual toolbar and continuous page overlays. A click
in Insert text mode positions a draft; click a verified loaded block to edit it.
Load text boxes and Preview each disclose server processing. Preview shows actual
candidate pages without replacing current bytes/history; current-PDF downloads
and exports must not accidentally download the uncommitted preview. Draft/options/
source/session changes, Undo, close and cancellation invalidate/dispose candidates.
Apply records one exact-byte history entry, invalidates source analysis and keeps
original bytes. Cancellation adds no history and issues no destructive writes.

No deployment. Earlier Linux/CDN/contract/HEIC/hosted-validator/Word/Acrobat gates
remain open. Outline/history panels and arbitrary existing image editing remain
future work; this phase does not claim the entire original objective is complete.
