---
phase: quick-261021-ply
plan: "01"
type: execute
wave: 1
depends_on: []
autonomous: true
requirements: [FONT-DETECT, FONT-CHOOSE, FONT-SAFE]
files_modified:
  - engine/fonts.py
  - engine/recipe.py
  - server/worker.py
  - client/src/App.jsx
  - client/src/session.mjs
  - client/src/session.test.mjs
  - client/src/style.css
  - tests/test_fonts.py
  - tests/test_engine_styles.py
  - tests/test_web_contract.py
must_haves:
  truths:
    - "Times New Roman is recognized without a mapping-table failure."
    - "A user sees the source font name and can choose Automatic, Serif, Sans-serif, or Monospace."
    - "An otherwise safe unknown source font can be edited with an explicitly chosen bundled family."
    - "Chosen families survive recipe replay and undo; fit, glyph coverage, and unsafe geometry still gate every edit."
  artifacts:
    - path: engine/recipe.py
      provides: "Validated explicit bundled-family replacement"
    - path: server/worker.py
      provides: "Source font identity and known-family suggestion on page runs"
    - path: client/src/App.jsx
      provides: "Reachable font selection in the selected-text inspector"
  key_links:
    - from: client/src/App.jsx
      to: engine/recipe.py
      via: "style.font_family on the existing edit recipe"
    - from: server/worker.py
      to: client/src/App.jsx
      via: "source_font and suggested_font_family in page-run responses"
---

<objective>
Allow readable PDF text to use an explicitly selected bundled replacement family when its source font has no automatic mapping. Fix exact known Microsoft font aliases and expose source font identity. Preserve actual content-stream replacement, immutable originals, atomic recipes, searchable Unicode, and all existing safety checks.
</objective>

<context>
@CLAUDE.md
@.planning/STATE.md
@engine/fonts.py
@engine/recipe.py
@engine/rewrite.py
@server/worker.py
@client/src/App.jsx
@client/src/session.mjs

User intent and implementation choices for this quick task:
- D-01: Detect and display the source font; recognize Times New Roman.
- D-02: Let the user specify the font kind or replace with a selected typeface when automatic detection/mapping cannot choose it.
- D-03 (controller choice): Use the existing bundled Liberation Serif/Sans/Mono choices. No arbitrary font uploads or external font loading in this task.
- D-04: Preserve genuine unreadable-text, unsafe-geometry, missing-glyph and width-fit refusals; choosing a family only overrides a missing source-family mapping.

Interfaces already present: BundledFamily = Literal["Sans", "Serif", "Mono"]; BundledVariant = Regular/Bold/Italic/BoldItalic; lookup_bundled_font returns MappingVerdict. RecipeStyle is a validated optional TypedDict; _resolve_op determines substitution_key; apply_recipe passes force_substitution to rewrite_run. Page runs are created in server.worker inside the isolated parser process. Client candidate() includes style; choose() restores recipe style; draft/style changes invalidate preview. Existing snapshot history includes the complete recipe.

Discovery: Level 0. Reuse bundled fonts, font mapping, active-font resource resolution, existing recipe validation and client state. No new dependencies or installation tasks.
</context>

<tasks>
<task type="auto" tdd="true">
  <name>Task 1: Recognize exact aliases and implement explicit family substitution</name>
  <files>engine/fonts.py, engine/recipe.py, tests/test_fonts.py, tests/test_engine_styles.py</files>
  <behavior>
    - Exact spaced Times New Roman and Courier New regular/bold/italic/bold-italic names map to the correct bundled family and variant; existing subset-prefix handling remains intact; unrelated substring names remain unmapped.
    - style.font_family accepts only Sans, Serif, Mono. Reject null, unknown strings, lists and booleans; absent field preserves old recipes.
    - A readable unknown source name refuses under Automatic and succeeds with an explicit family if replacement text fits and has glyph coverage.
    - Explicit family forces replacement even for editable_original with a usable embedded font. Bold and italic overrides still select the correct variant.
    - Unsupported text geometry, stateful operators, glyph coverage and ambiguous shaping remain refused. Unchanged runs and source embedded font objects remain intact.
  </behavior>
  <action>Per D-01, add explicit exact aliases to BASE_FONT_MAPPING with table-driven tests; do not use substring or fuzzy family guessing. Per D-02/D-03, extend RecipeStyle validation with optional font_family: BundledFamily. In _resolve_op select the explicit family before requiring a mapped family, force the substitution branch whenever it is present, and retain mapped variant defaults where known; for unmapped source names use Regular unless bold/italic is explicitly requested. Pass the same force-substitution condition in apply_recipe to rewrite_run, so planning and emission agree. Reuse existing glyph validation, shaping, width fit, per-family/variant subset deduplication, current-byte re-resolution and atomic refusal behavior per D-04. Do not change the classifier's structural safety verdicts or treat font-family choice as permission to bypass them. Update comments that imply no explicit substitution escape exists.</action>
  <verify><automated>.venv/bin/python -m pytest tests/test_fonts.py tests/test_engine_styles.py tests/test_recipe.py -q -m "not corpus"</automated></verify>
  <done>Known spaced aliases work automatically; unknown readable source fonts succeed only with explicit choice; embedded originals can be replaced intentionally; original recipes and safety refusals retain their behavior.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Expose source font identity and prove the HTTP replacement path</name>
  <files>server/worker.py, tests/test_web_contract.py</files>
  <behavior>
    - Page runs include source_font string|null and suggested_font_family Sans|Serif|Mono|null without changing run IDs, states, reasons or geometry.
    - A synthetic readable unknown-font PDF can be uploaded, inspected, previewed and edited through HTTP using explicit font_family; returned PDF extracts the replacement text and contains the selected Liberation family.
    - Unknown-family input is rejected; automatic unmapped resolution remains a named failure; worker isolation and existing privacy headers remain intact.
  </behavior>
  <action>Per D-01, resolve each run's active Tf and font resource from the already available stream bytes/resources inside the worker; use the same BaseFont normalization/subset-tag handling as engine mapping rather than introducing an inconsistent name detector. Return the source name for display and mapping.family as suggestion when available, with null for unavailable metadata. Keep metadata extraction from turning a structurally refused run into an editable one. Per D-02/D-04 add a positive real-worker HTTP regression that uploads a synthetic unknown-name document, fetches its server-issued run ID, demonstrates Automatic refusal, then previews/applies explicit Serif successfully and inspects searchable output/font resources. Add rejection cases to ensure the client cannot provide arbitrary font paths or URLs. Avoid importing parsers into the request process, persisting font names, or logging document metadata.</action>
  <verify><automated>.venv/bin/python -m pytest tests/test_web_contract.py tests/test_engine_styles.py -q</automated></verify>
  <done>API consumers can display the actual source name and a reliable known-family suggestion; the existing HTTP edit flow proves manual replacement works without weakening isolation or validation.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Make font selection reachable and preserve it through preview and undo</name>
  <files>client/src/App.jsx, client/src/session.mjs, client/src/session.test.mjs, client/src/style.css</files>
  <behavior>
    - Inspector shows the detected source font and Automatic, Serif (Liberation Serif), Sans-serif (Liberation Sans), Monospace (Liberation Mono) choices.
    - Automatic omits font_family; each explicit choice adds the exact enum value while retaining color/bold/italic.
    - Selecting an existing edit restores its family; recipe snapshots and undo retain it; changing family invalidates a ready preview before apply.
    - An unresolved mapping produces a single useful prompt to choose a replacement family, preserving the detected name without duplicated raw mapping errors.
  </behavior>
  <action>Per D-01/D-02/D-03 put an accessible labeled selector beside the existing text style controls, disabled during active work. Display source_font using React text escaping, with a clear unavailable label when absent. Automatic remains the default and does not silently copy suggested_font_family into the recipe; known suggestions can be described as the automatic substitute. Use the existing style state and immutable candidate/history operations to carry explicit font_family; selecting Automatic removes the field. Extract a small pure helper only where it makes family-change and recipe-preservation cases directly testable in session.test.mjs. Reuse draft/style preview invalidation and editVersion request guards so a stale family preview cannot enable Apply. Per D-04 retain structural refusal UI; for mapping-only preview failures show a concise request to choose Serif, Sans-serif, or Monospace instead of repeating raw mapping details. Make substitution disclosure include an explicit family even if the original was editable_original. Match current understated inspector styling.</action>
  <verify><automated>node --test client/src/session.test.mjs; npm --prefix client run build</automated><human-check>Open a Times New Roman fixture and an unmapped-font fixture. Inspect source names, select each family, preview and apply a fitting text replacement, download and inspect searchable text, undo, and switch runs to confirm restored selections. Change family after a successful preview and confirm Apply becomes unavailable until a new successful preview.</human-check></verify>
  <done>Users can recover an otherwise safe unknown-font edit through an explicit, accurately labeled replacement choice; the final recipe and undo preserve the choice and stale previews never authorize a different family.</done>
</task>
</tasks>

<threat_model>
| Boundary / threat | Disposition | Mitigation |
|---|---|---|
| Client recipe → worker: arbitrary font path/URL or invalid enum | mitigate | Strict font_family enum validation; existing bundled paths only. |
| Hostile PDF metadata → browser: markup injection | mitigate | Display source name as React text, never HTML. |
| Explicit family → rewrite: safety-check bypass | mitigate | Override family mapping only; preserve all structural, Unicode, fit and atomicity gates. |
| Document font metadata → logs/storage | mitigate | Existing worker-only parsing; no font metadata logging or persistent storage. |
| Dependency supply chain | accept | No package changes or installs. |
</threat_model>

<verification>
Run the task-specific tests, strict typing with .venv/bin/python -m mypy engine/ server/, and git diff --check. Run existing renderer/font gates if substitution emission changed. Perform the browser journey after automated tests pass. Record actual commands/results and any remaining browser limitations in SUMMARY.md; do not promise all scripts or corrupted PDFs become editable.
</verification>

<source_audit>
| Source | Item | Coverage |
|---|---|---|
| GOAL / user | Detect source font and recover unknown-family edits | Tasks 1–3 |
| REQ FONT-DETECT | Exact aliases and source identity | Tasks 1–2 |
| REQ FONT-CHOOSE | Explicit replacement including embedded originals, UI and undo | Tasks 1–3 |
| REQ FONT-SAFE | Preserve geometry/glyph/fit/atomicity gates | Tasks 1–2 |
| RESEARCH | Existing bundled families, strict validation, isolated worker, immutable recipe patterns | Tasks 1–3 |
| CONTEXT D-01 / D-02 / D-03 / D-04 | Detection / selection / existing bundled fonts / preserved safety | Tasks 1–3 |
No roadmap phase is changed by this quick task; later export/page/find-replace work and external font loading are excluded.
</source_audit>

<success_criteria>
Times New Roman no longer triggers the reported mapping failure. An otherwise safe unknown font can be edited through the UI with an explicit bundled family and downloaded as searchable text. Selecting a family deliberately replaces embedded originals, retains intended style, survives undo/replay, and preserves surrounding document content. Unsupported glyphs or unsafe text geometry still produce actionable refusals.
</success_criteria>

<output>Create .planning/quick/261021-ply-detect-font-names-and-allow-explicit-rep/SUMMARY.md after implementation.</output>
