"""Shared pytest fixtures for the corpus test suite."""

import json
from pathlib import Path

import pikepdf
import pytest


@pytest.fixture(scope="session")
def manifest():
    """Load and return the corpus manifest (list of document metadata dicts).

    Session-scoped: loaded once per test session.
    """
    manifest_path = Path(__file__).parent.parent / "corpus" / "manifest.json"
    with open(manifest_path) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def corpus_dir():
    """Return the path to the public corpus directory."""
    return Path(__file__).parent.parent / "corpus" / "public"


def docs_with_category(category: str, manifest_data=None):
    """Helper function: return list of manifest entries containing the given category.

    This is a plain helper function (not a fixture), importable directly from conftest.

    Args:
        category: The category string to filter by
        manifest_data: Optional manifest list; if not provided, you must load it yourself

    Returns:
        List of manifest entry dicts containing the category in their categories list
    """
    if manifest_data is None:
        raise ValueError("docs_with_category requires manifest_data parameter")

    return [entry for entry in manifest_data if category in entry.get("categories", [])]


def open_doc(filename: str, corpus_path=None):
    """Helper function: open a PDF document from the corpus.

    Returns a pikepdf.Pdf object. Caller is responsible for closing via .close().

    Args:
        filename: The document filename to open
        corpus_path: Optional corpus directory path; if not provided, defaults to corpus/public

    Returns:
        A pikepdf.Pdf object (caller must close it)
    """
    if corpus_path is None:
        corpus_path = Path(__file__).parent.parent / "corpus" / "public"
    else:
        corpus_path = Path(corpus_path)

    return pikepdf.open(corpus_path / filename)
