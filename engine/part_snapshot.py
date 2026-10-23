"""Request-owned structural snapshots for ordinary page content.

Every splice is followed by the complete existing two-pass interpreter zip. Untouched
instructions retain an internal token and must have identical operands and rendering
state. This proves their glyph semantics unchanged without reconstructing millions of
GlyphRecords or running the spatial clusterer again. Targets, replacements and the
following-glyph witness are decoded freshly. Unsupported provenance uses the full
classified-page path before any mutation; an invalid active context always refuses.
"""
from __future__ import annotations

from copy import copy
from dataclasses import replace
from pathlib import Path
import tempfile
from typing import Any

import pikepdf

from engine.classify_run import (
    RunVerdict, _find_active_font_name, _resolve_font_for_glyph, classify_run, stream_bytes_and_resources,
)
from engine.clusterer import cluster_page
from engine.encoding_table import glyph_verdict
from engine.index import MAX_DOCUMENT_GLYPHS
from engine.playa_boundary import open_document, walk_page
from engine.records import GlyphRecord, RunRecord
from engine.run_id import decode_run_id, encode_run_id
from engine.walker import StreamPath, _FontIds, _op_records


def _has_text(instruction: Any) -> bool:
    op, args = str(instruction.operator), instruction.operands
    if op not in ("Tj", "TJ", "'", '"') or not args:
        return False
    if op == "TJ":
        return any(isinstance(item, pikepdf.String) and bytes(item) for item in args[0])
    return isinstance(args[-1], pikepdf.String) and bool(bytes(args[-1]))


def _signature(instruction: Any) -> bytes:
    return pikepdf.unparse_content_stream([instruction])


def _state(op: Any) -> tuple[Any, ...]:
    text = op[3]
    gs = text.gstate
    # Font resource objects are immutable during this optimization: recipe embedding
    # adds a fresh resource name, never overwrites an existing font. Each actual target
    # is still passed through current PDF font/encoding and glyph validation below.
    return (
        tuple(text.ctm), tuple(text.line_matrix), tuple(text._glyph_offset),
        text.fontbase, text.fontname,
        gs.fontsize, gs.charspace, gs.wordspace, gs.scaling, gs.leading,
        gs.render_mode, gs.rise, tuple(gs.ncolor.values), gs.ncolor.pattern,
        tuple(gs.scolor.values), gs.scolor.pattern, gs.linewidth,
        gs.linecap, gs.linejoin, gs.miterlimit, tuple(gs.dash.dash), gs.dash.phase,
        gs.salpha, gs.nalpha, gs.alpha_source, repr(gs.blend_mode),
    )


def _equal_state(before: Any, after: Any) -> bool:
    if before == after:
        return True
    if isinstance(before, tuple) and isinstance(after, tuple):
        return len(before) == len(after) and all(_equal_state(a, b) for a, b in zip(before, after))
    if isinstance(before, (float, int)) and isinstance(after, (float, int)):
        return abs(before - after) <= 1e-6
    return bool(before == after)


def _eligible(pdf: pikepdf.Pdf, page: int, runs: Any) -> bool:
    obj = pdf.pages[page]
    if any(annot.get("/AP") is not None for annot in obj.obj.get("/Annots", [])):
        return False
    resources = obj.Resources
    if resources.get("/Pattern"):
        return False
    if any(str(x.get("/Subtype")) != "/Image" for _, x in resources.get("/XObject", pikepdf.Dictionary()).items()):
        return False
    if any(str(f.get("/Subtype")) == "/Type3" for _, f in resources.get("/Font", pikepdf.Dictionary()).items()):
        return False
    for run, _ in runs:
        address = decode_run_id(run.run_id)
        if run.page != page or address["xobj_path"] or any(address[k] is not None for k in ("annot", "pattern", "charproc")):
            return False
    return True


class PartSnapshot:
    """Private context owned and closed by one atomic recipe application."""

    def __init__(self, pdf: pikepdf.Pdf, page: int, runs: tuple[tuple[RunRecord, RunVerdict], ...]) -> None:
        self.page = page
        self.runs = runs
        self._pdf = pdf
        self._scratch: Any = None
        self._doc: Any = None
        self._pending: Any = None
        self._next_token = 0
        self._instructions: dict[int, list[Any]] = {}
        self._signatures: dict[int, list[bytes]] = {}
        self._part_bytes: dict[int, bytes] = {}
        self._tokens: dict[int, list[int]] = {}
        self._states: dict[int, Any] = {}
        self._bindings: dict[int, Any] = {}
        self._ops: dict[int, Any] = {}
        self._membership: dict[str, list[tuple[int, int | None, int]]] = {}
        self._original: dict[str, RunRecord] = {}
        self._current: dict[str, tuple[RunRecord, RunVerdict]] = {}
        self._source_keys: dict[str, list[str]] = {}
        self._witness: tuple[int, int | None, int] | None = None
        self._witness_before: tuple[float, float] | None = None
        self._glyph_count = sum(len(run.glyphs) for run, _ in runs)

    @classmethod
    def create(cls, pdf: pikepdf.Pdf, page: int, runs: tuple[tuple[RunRecord, RunVerdict], ...]) -> PartSnapshot | None:
        context = cls(pdf, page, runs)
        try:
            if not _eligible(pdf, page, runs):
                return None
            for run, verdict in runs:
                # Spatially separate fragments of one shared TJ can have the same
                # source run ID. Keep every fragment in the full guard domain;
                # duplicate source addresses must never select an arbitrary target.
                keys = context._source_keys.setdefault(run.run_id, [])
                key = run.run_id if not keys else f"{run.run_id}:fragment:{len(keys)}"
                keys.append(key)
                context._original[key] = run
                context._current[key] = (run, verdict)
            contents = pdf.pages[page].obj.get("/Contents")
            parts = list(contents) if isinstance(contents, pikepdf.Array) else [contents]
            for number, part in enumerate(parts):
                if part is None:
                    return None
                instructions = list(pikepdf.parse_content_stream(pdf.make_stream(part.read_bytes())))
                context._instructions[number] = instructions
                context._signatures[number] = [_signature(i) for i in instructions]
                context._part_bytes[number] = bytes(part.read_bytes())
                context._tokens[number] = [context._token() for _ in instructions]
            context._capture(pdf)
            by_offset = {(op[1], op[0]): token for token, op in context._ops.items()}
            # The full source classification must cover precisely the operator domain
            # that the ordinary correlator accepts, including uneditable text.
            covered = {(g.stream_id, g.operator_byte_offset) for r, _ in runs for g in r.glyphs}
            if covered != set(by_offset):
                context.close()
                return None
            for key, (run, _) in context._current.items():
                context._membership[key] = [
                    (by_offset[(g.stream_id, g.operator_byte_offset)], g.item_index_within_tj, g.byte_offset_within_string)
                    for g in run.glyphs]
            context._states = context._state_view()
            return context
        except Exception:
            context.close()
            return None

    def _token(self) -> int:
        token = self._next_token
        self._next_token += 1
        return token

    def close(self) -> None:
        if self._doc is not None:
            self._doc.close()
            self._doc = None
        if self._scratch is not None:
            self._scratch.cleanup()
            self._scratch = None

    def _capture(self, pdf: pikepdf.Pdf) -> None:
        """Open one disposable page; consume the full zip and its trailing assertion."""
        self.close()
        self._scratch = tempfile.TemporaryDirectory()
        path = Path(self._scratch.name) / "page.pdf"
        with pikepdf.Pdf.new() as single:
            single.pages.append(pdf.pages[self.page])
            if "/Annots" in single.pages[0].obj:
                del single.pages[0].obj["/Annots"]
            single.save(path, compress_streams=False, object_stream_mode=pikepdf.ObjectStreamMode.disable)
        self._doc = open_document(path)
        expected = [
            (part, token, instruction)
            for part in sorted(self._instructions)
            for token, instruction in zip(self._tokens[part], self._instructions[part])
            if _has_text(instruction)]
        ops = []
        for offset, part_number, operands, text in walk_page(self._doc.pages[0], self._doc):
            # Playa's interpreter mutates the shared GraphicState at later Tf/Tz/
            # color operators. Freeze each yielded object's state before advancing;
            # deferring this copy would decode earlier text using the final font.
            frozen = copy(text)
            frozen.gstate = copy(text.gstate)
            ops.append((offset, part_number, operands, frozen))
        if len(ops) != len(expected):
            raise ValueError("operator domain changed")
        self._ops = {}
        # Boundary operands and pikepdf instructions describe the same serialized
        # bytes. Exact instruction identities come from the writer notification;
        # full current-part signatures below rule out unannounced byte mutation.
        for (part, token, _instruction), op in zip(expected, ops):
            if op[1] != part:
                raise ValueError("part changed")
            self._ops[token] = op
        page = pdf.pages[self.page]
        contents = page.obj.get("/Contents")
        parts = list(contents) if isinstance(contents, pikepdf.Array) else [contents]
        if len(parts) != len(self._instructions):
            raise ValueError("part count changed")
        for number, content_part in enumerate(parts):
            if content_part is None:
                raise ValueError("missing part")
            if bytes(content_part.read_bytes()) != self._part_bytes[number]:
                raise ValueError("instructions changed")
        # Pin the actual owning PDF resource alias/object, not only BaseFont: two
        # aliases can share a display name while selecting different glyph programs.
        # Unlike scratch IDs, these object identities stay stable during this apply.
        contexts = {number: stream_bytes_and_resources(pdf, self.page, number, ())
                    for number in self._instructions}
        self._bindings = {}
        bindings = {}
        for token, op in self._ops.items():
            data, resources = contexts[op[1]]
            alias = _find_active_font_name(data, op[0])
            key = op[1], alias
            if key not in bindings:
                fonts = resources.get("/Font") if resources is not None else None
                font = fonts.get("/" + alias.decode("latin-1")) if alias is not None and fonts is not None else None
                bindings[key] = (alias, font.objgen if font is not None else None,
                                 font.unparse() if font is not None else None)
            self._bindings[token] = bindings[key]

    def _state_view(self) -> dict[int, Any]:
        return {token: (_state(op), self._bindings[token]) for token, op in self._ops.items()}

    def _records(self, tokens: set[int]) -> dict[tuple[int, int | None, int], Any]:
        fonts = _FontIds()
        result = {}
        for token in tokens:
            for glyph, attrs in _op_records(self._ops[token], fonts):
                result[(token, glyph.item_index_within_tj, glyph.byte_offset_within_string)] = (glyph, attrs)
        return result

    def _classify(self, run: RunRecord) -> RunVerdict:
        cache: dict[Any, Any] = {}
        contexts: dict[int, Any] = {}
        operators: dict[tuple[int, int], Any] = {}
        fonts = []
        for glyph in run.glyphs:
            if glyph.stream_id not in contexts:
                contexts[glyph.stream_id] = stream_bytes_and_resources(self._pdf, self.page, glyph.stream_id, ())
            key = glyph.stream_id, glyph.operator_byte_offset
            if key not in operators:
                operators[key] = _resolve_font_for_glyph(
                    self._pdf, self.page, StreamPath(self.page), glyph, cache, contexts[glyph.stream_id])
            fonts.append(operators[key])
        if not fonts:
            return RunVerdict("not_editable", "font resolution lost across clustering")
        for font, glyph in zip(fonts, run.glyphs):
            result = glyph_verdict(font, glyph)
            if not result.editable:
                return RunVerdict("not_editable", result.reason)
        return classify_run(run, fonts[0], {})

    def resolve(self, original: RunRecord) -> tuple[RunRecord, RunVerdict] | None:
        keys = self._source_keys.get(original.run_id, [])
        if len(keys) != 1:
            return None
        source_id = keys[0]
        pair = self._current.get(source_id)
        if pair is None or self._pending is not None:
            return None
        run, _ = pair
        try:
            membership = self._membership[source_id]
            records = self._records({token for token, _, _ in membership})
            glyphs = [records[key][0] for key in membership]
            # Identity is an exact untouched instruction and glyph byte position,
            # never a fuzzy text match. Confirm the source anchor and sequence too.
            if len(glyphs) != len(run.glyphs) or any(
                a.code != b.code or a.unicode != b.unicode or
                abs(a.x - b.x) > 1e-6 or abs(a.y - b.y) > 1e-6
                for a, b in zip(run.glyphs, glyphs)):
                return None
            run = replace(run, glyphs=glyphs)
            verdict = self._classify(run)
            self._current[source_id] = (run, verdict)
            self._refresh_runs()
            return run, verdict
        except Exception:
            return None

    def _refresh_runs(self) -> None:
        self.runs = tuple(self._current.values())

    def before_witness(self, run: RunRecord) -> tuple[float, float] | None:
        part = decode_run_id(run.run_id)["part"]
        last = max((g.operator_byte_offset, -1 if g.item_index_within_tj is None else g.item_index_within_tj,
                    g.byte_offset_within_string) for g in run.glyphs)
        following = []
        for source_id, (other, _) in self._current.items():
            for key, glyph in zip(self._membership[source_id], other.glyphs):
                position = (glyph.operator_byte_offset, -1 if glyph.item_index_within_tj is None else glyph.item_index_within_tj,
                            glyph.byte_offset_within_string)
                if glyph.stream_id == part and position > last:
                    following.append((position, key))
        self._witness = None
        self._witness_before = None
        if following:
            key = min(following)[1]
            glyph = self._records({key[0]})[key][0]
            self._witness = key
            self._witness_before = (glyph.x, glyph.y)
        return self._witness_before

    def splice(self, run: RunRecord, instructions: Any, touched: list[int], new_instructions: Any) -> None:
        if self._pending is not None or not touched:
            raise ValueError("invalid splice state")
        part = decode_run_id(run.run_id)["part"]
        if [_signature(i) for i in instructions] != self._signatures[part]:
            raise ValueError("stale splice")
        matching = [key for key, (current, _) in self._current.items() if current is run]
        if len(matching) != 1:
            raise ValueError("ambiguous target")
        source_id = matching[0]
        target_tokens = {token for token, _, _ in self._membership[source_id]}
        if any(target_tokens.intersection(token for token, _, _ in membership)
               for other, membership in self._membership.items() if other != source_id):
            raise ValueError("shared text operator")
        old_tokens = self._tokens[part]
        if {old_tokens[i] for i in touched} != target_tokens:
            raise ValueError("incorrect splice span")
        first = touched[0]
        inserted_tokens = [self._token() for _ in new_instructions]
        new_tokens = old_tokens[:first] + inserted_tokens + old_tokens[first + 1:]
        surviving = list(instructions[:first]) + list(new_instructions) + list(instructions[first + 1:])
        signatures = self._signatures[part][:first] + [_signature(i) for i in new_instructions] + self._signatures[part][first + 1:]
        shift = len(new_instructions) - 1
        for index in sorted(touched[1:], reverse=True):
            del surviving[index + shift]
            del new_tokens[index + shift]
            del signatures[index + shift]
        self._instructions[part] = surviving
        self._signatures[part] = signatures
        self._part_bytes[part] = b"\n".join(signatures)
        self._tokens[part] = new_tokens
        self._pending = (source_id, set(inserted_tokens), target_tokens)

    def check_after(self, pdf: pikepdf.Pdf) -> str | None:
        if self._pending is None:
            return "correlation_failed"
        source_id, inserted, removed = self._pending
        try:
            self._capture(pdf)
            current_states = self._state_view()
            for token, before in self._states.items():
                if token not in removed and (token not in current_states or not _equal_state(before, current_states[token])):
                    return "text_matrix_shifted_after_edit"
            if self._witness is not None:
                witness_key = self._witness
                glyph = self._records({witness_key[0]})[witness_key][0]
                before = self._witness_before
                if before is None or abs(glyph.x - before[0]) > 1e-6 or abs(glyph.y - before[1]) > 1e-6:
                    return "text_matrix_shifted_after_edit"
            removed_glyphs = len(self._current[source_id][0].glyphs)
            del self._current[source_id]
            del self._membership[source_id]
            for key, (run, verdict) in list(self._current.items()):
                membership = self._membership[key]
                glyphs = []
                changed = False
                for glyph, (token, _, _) in zip(run.glyphs, membership):
                    offset = self._ops[token][0]
                    if offset == glyph.operator_byte_offset:
                        glyphs.append(glyph)
                    else:
                        changed = True
                        glyphs.append(GlyphRecord(
                            glyph.code, glyph.glyph, glyph.unicode, glyph.x, glyph.y,
                            glyph.advance, glyph.font_id, glyph.render_mode, glyph.visible,
                            glyph.stream_id, offset, glyph.item_index_within_tj,
                            glyph.byte_offset_within_string))
                if not changed:
                    continue
                address = decode_run_id(run.run_id)
                run_id = encode_run_id(address["source_hash"], self.page, address["part"],
                                       byte_offset=min(g.operator_byte_offset for g in glyphs), subrange=address["subrange"])
                self._current[key] = (replace(run, run_id=run_id, glyphs=glyphs), verdict)
            records = self._records(inserted.intersection(self._ops))
            self._glyph_count += len(records) - removed_glyphs
            if self._glyph_count > MAX_DOCUMENT_GLYPHS:
                return "correlation_failed"
            located = [(StreamPath(self.page), glyph, attrs) for glyph, attrs in records.values()]
            if located:
                address = decode_run_id(self._original[source_id].run_id)
                font_cache: dict[Any, Any] = {}
                contexts = {g.stream_id: stream_bytes_and_resources(pdf, self.page, g.stream_id, ())
                            for _, g, _ in located}
                operator_fonts = {}
                for path, glyph, _ in located:
                    op_key = glyph.stream_id, glyph.operator_byte_offset
                    if op_key not in operator_fonts:
                        operator_fonts[op_key] = _resolve_font_for_glyph(
                            pdf, self.page, path, glyph, font_cache, contexts[glyph.stream_id])
                by_glyph = {id(g): operator_fonts[(g.stream_id, g.operator_byte_offset)] for _, g, _ in located}
                emitted = cluster_page(self.page, located, address["source_hash"],
                                       lambda glyph: glyph_verdict(by_glyph[id(glyph)], glyph))
                by_address = {(op[1], op[0]): token for token, op in self._ops.items() if token in inserted}
                # No source operation addresses these newly written runs, but their
                # actual glyphs remain in the full correlation/shared-operator domain.
                for number, run in enumerate(emitted):
                    key = f"{source_id}:written:{number}"
                    run.page_ctm = self._doc.pages[0].ctm
                    run.effective_em = located[0][2].effective_em
                    run.direction = located[0][2].direction
                    self._current[key] = (run, self._classify(run))
                    self._membership[key] = [(by_address[(g.stream_id, g.operator_byte_offset)],
                                              g.item_index_within_tj, g.byte_offset_within_string) for g in run.glyphs]
            self._states = current_states
            self._refresh_runs()
            self._pending = None
            return None
        except Exception:
            return "correlation_failed"
