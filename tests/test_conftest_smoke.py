"""Smoke tests for conftest.py fixtures and helpers."""

from conftest import docs_with_category, open_doc


def test_manifest_has_correct_size(manifest):
    """Verify the manifest contains exactly 216 entries."""
    assert len(manifest) == 216


def test_corpus_dir_exists(corpus_dir):
    """Verify the corpus directory is accessible and is a directory."""
    assert corpus_dir.is_dir()


def test_docs_with_category_type3(manifest):
    """Verify the type3 category has the expected 12 documents.

    This matches the measured corpus distribution from the research phase.
    """
    type3_docs = docs_with_category("type3", manifest)
    assert len(type3_docs) >= 12, (
        f"Expected at least 12 documents with 'type3' category, got {len(type3_docs)}"
    )
