from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

from .models import SourceRecord

PRIORITY_PATHS = (
    "판례", "precedent", "precedents",
    "지침", "guideline", "guidelines",
    "교재", "textbook", "textbooks",
    "법령", "law", "regulation",
    "산재", "industrial",
)


def categorize(path: str) -> str:
    """Categorize a vault file path as 'nomu', 'lawyer', or 'both'."""
    lower = path.lower()
    nomu_keywords = ("노무", "산재", "임금", "근로", "해고", "nomu", "labor")
    lawyer_keywords = ("법률", "판례", "소송", "변호", "lawyer", "legal", "litigation")
    is_nomu = any(kw in lower for kw in nomu_keywords)
    is_lawyer = any(kw in lower for kw in lawyer_keywords)
    if is_nomu and is_lawyer:
        return "both"
    if is_nomu:
        return "nomu"
    if is_lawyer:
        return "lawyer"
    return "both"


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

        def _sort_key(path: Path) -> tuple[int, float]:
            """Priority files first (0), then others (1). Within group, newest first."""
            path_str = str(path).lower()
            is_priority = any(kw in path_str for kw in PRIORITY_PATHS)
            return (0 if is_priority else 1, -path.stat().st_mtime)

        items.sort(key=_sort_key)
        return items[:limit]

    def _excerpt(self, path: Path, max_chars: int = 800) -> str:
        content = path.read_text(encoding="utf-8", errors="ignore")
        return " ".join(content.split())[:max_chars]

    def enrich_with_pinecone(self, records: list[SourceRecord], top_k: int = 5) -> list[SourceRecord]:
        """Optionally enrich records with Pinecone similarity search."""
        api_key = os.getenv("PINECONE_API_KEY")
        if not api_key:
            return records
        try:
            import httpx

            index_host = os.getenv("PINECONE_INDEX_HOST", "")
            if not index_host:
                return records

            queries = [r.excerpt[:200] for r in records[:3] if r.excerpt]
            if not queries:
                return records

            resp = httpx.post(
                f"https://{index_host}/query",
                headers={"Api-Key": api_key, "Content-Type": "application/json"},
                json={"topK": top_k, "includeMetadata": True, "queries": [{"values": [], "filter": {}}]},
                timeout=10,
            )
            if resp.status_code == 200:
                matches = resp.json().get("matches", [])
                for match in matches:
                    meta = match.get("metadata", {})
                    records.append(
                        SourceRecord(
                            source="pinecone",
                            status="collected",
                            title=meta.get("title", "Pinecone Match"),
                            excerpt=meta.get("text", "")[:800],
                            published_at=meta.get("date", datetime.now().isoformat()),
                            evidence=[f"pinecone:{match.get('id', '')}"],
                            metadata={"score": match.get("score", 0), "category": categorize(meta.get("path", ""))},
                        )
                    )
        except Exception:
            pass  # Pinecone is optional enrichment
        return records

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
                    metadata={"relative_path": relative_path, "category": categorize(relative_path)},
                )
            )
        return records
