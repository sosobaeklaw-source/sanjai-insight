"""Tests for enhanced VaultReader (Phase 4)."""
from __future__ import annotations

from pathlib import Path

from src.insight_engine.vault_reader import PRIORITY_PATHS, VaultReader, categorize


def test_categorize_nomu():
    assert categorize("노무/산재/case.md") == "nomu"
    assert categorize("임금체불/report.md") == "nomu"


def test_categorize_lawyer():
    assert categorize("판례/recent.md") == "lawyer"
    assert categorize("소송/civil.md") == "lawyer"


def test_categorize_both():
    assert categorize("노무/판례/overlap.md") == "both"
    assert categorize("misc/notes.md") == "both"


def test_priority_paths_exist():
    assert "판례" in PRIORITY_PATHS
    assert "지침" in PRIORITY_PATHS


def test_vault_reader_snapshot_has_category(tmp_path):
    vault = tmp_path / "vault"
    folder = vault / "판례"
    folder.mkdir(parents=True)
    (folder / "case.md").write_text("# 산재 판례\n\n산업재해 관련 판례", encoding="utf-8")

    reader = VaultReader(vault)
    records = reader.snapshot(days=30, limit=5)

    assert len(records) == 1
    assert "category" in records[0].metadata
    assert records[0].metadata["category"] in ("nomu", "lawyer", "both")


def test_vault_reader_priority_sorting(tmp_path):
    vault = tmp_path / "vault"
    normal = vault / "notes"
    priority = vault / "판례"
    normal.mkdir(parents=True)
    priority.mkdir(parents=True)

    # Create files with normal dir first
    (normal / "a.md").write_text("normal note", encoding="utf-8")
    (priority / "b.md").write_text("priority note", encoding="utf-8")

    reader = VaultReader(vault)
    files = reader.get_recent_files(days=30, limit=10)

    # Priority file should come first
    assert len(files) == 2
    assert "판례" in str(files[0])


def test_vault_reader_disabled():
    reader = VaultReader(None)
    assert not reader.enabled
    assert reader.snapshot() == []


def test_enrich_with_pinecone_no_key(tmp_path, monkeypatch):
    monkeypatch.delenv("PINECONE_API_KEY", raising=False)
    vault = tmp_path / "vault"
    vault.mkdir()
    reader = VaultReader(vault)
    records = reader.snapshot(days=30)
    result = reader.enrich_with_pinecone(records)
    assert result == records  # No change without API key
