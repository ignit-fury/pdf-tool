"""Shared pytest fixtures for the corpus test suite."""

import json
from pathlib import Path

import pikepdf
import pytest


def _load_manifest():
    """Internal: load the corpus manifest from disk."""
    manifest_path = Path(__file__).parent.parent / "corpus" / "manifest.json"
    with open(manifest_path) as f:
        return json.load(f)


def _corpus_dir():
    """Internal: return the path to the public corpus directory."""
    return Path(__file__).parent.parent / "corpus" / "public"


@pytest.fixture(scope="session")
def manifest():
    """Load and return the corpus manifest (list of document metadata dicts).

    Session-scoped: loaded once per test session.
    """
    return _load_manifest()


@pytest.fixture(scope="session")
def corpus_dir():
    """Return the path to the public corpus directory."""
    return _corpus_dir()


def docs_with_category(category: str):
    """Helper function: return list of manifest entries containing the given category.

    This is a plain helper function (not a fixture), importable directly from conftest.

    Args:
        category: The category string to filter by

    Returns:
        List of manifest entry dicts containing the category in their categories list
    """
    manifest_data = _load_manifest()
    return [entry for entry in manifest_data if category in entry.get("categories", [])]


def open_doc(filename: str):
    """Helper function: open a PDF document from the corpus.

    Returns a pikepdf.Pdf object. Caller is responsible for closing via .close().

    Args:
        filename: The document filename to open

    Returns:
        A pikepdf.Pdf object (caller must close it)
    """
    return pikepdf.open(_corpus_dir() / filename)
