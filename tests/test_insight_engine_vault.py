from __future__ import annotations

from pathlib import Path

from src.insight_engine.vault_reader import VaultReader


def test_vault_reader_snapshot(tmp_path):
    vault = tmp_path / "vault"
    folder = vault / "판례"
    folder.mkdir(parents=True)
    file_path = folder / "recent_case.md"
    file_path.write_text("# 제목\n\n산재와 임금체불 관련 최근 판례 요약", encoding="utf-8")

    reader = VaultReader(vault)
    snapshot = reader.snapshot(days=30, limit=5)

    assert len(snapshot) == 1
    assert snapshot[0].source == "vault"
    assert snapshot[0].status == "collected"
    assert "recent_case.md" in snapshot[0].evidence[0]
