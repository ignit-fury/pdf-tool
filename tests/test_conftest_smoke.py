"""Smoke tests for conftest.py fixtures and helpers."""

from conftest import docs_with_category, open_doc


def test_manifest_has_correct_size(manifest):
    """Verify the manifest contains exactly 217 entries.

    216 wild/disclosed-substitution documents plus vector_outlined_text_sample.pdf, added by
    Plan 02-02 Task 1 to close the vector_outlined_text zero-count gap (see corpus/sources.md
    "Disclosed Substitutions").
    """
    assert len(manifest) == 217


def test_corpus_dir_exists(corpus_dir):
    """Verify the corpus directory is accessible and is a directory."""
    assert corpus_dir.is_dir()


def test_docs_with_category_type3():
    """Verify the type3 category has the expected 12 documents.

    This matches the measured corpus distribution from the research phase.
    """
    type3_docs = docs_with_category("type3")
    assert len(type3_docs) >= 12, (
        f"Expected at least 12 documents with 'type3' category, got {len(type3_docs)}"
    )
