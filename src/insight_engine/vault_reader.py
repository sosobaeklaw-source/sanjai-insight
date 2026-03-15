from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from .models import SourceRecord


class VaultReader:
    """Read-only reader for recent vault material."""

    def __init__(self, vault_path: Path | None):
        self.vault_path = vault_path

    @property
    def enabled(self) -> bool:
        return bool(self.vault_path and self.vault_path.exists())

    def get_recent_files(self, days: int = 7, limit: int = 20) -> list[Path]:
        if not self.enabled or not self.vault_path:
            return []

        cutoff = datetime.now().timestamp() - timedelta(days=days).total_seconds()
        items = [
            path
            for path in self.vault_path.rglob("*.md")
            if path.is_file() and path.stat().st_mtime >= cutoff
        ]
        items.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return items[:limit]

    def _excerpt(self, path: Path, max_chars: int = 800) -> str:
        content = path.read_text(encoding="utf-8", errors="ignore")
        return " ".join(content.split())[:max_chars]

    def snapshot(self, days: int = 7, limit: int = 20) -> list[SourceRecord]:
        if not self.enabled or not self.vault_path:
            return []

        records: list[SourceRecord] = []
        for path in self.get_recent_files(days=days, limit=limit):
            relative_path = str(path.relative_to(self.vault_path))
            records.append(
                SourceRecord(
                    source="vault",
                    status="collected",
                    title=path.stem,
                    excerpt=self._excerpt(path),
                    published_at=datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                    evidence=[relative_path],
                    metadata={"relative_path": relative_path},
                )
            )
        return records
