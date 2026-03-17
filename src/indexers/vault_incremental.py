"""
Incremental Vault Indexer with FTS5
Indexes only changed files (sha256/mtime comparison)
"""

import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from uuid import uuid4

import aiosqlite

from ..models import VaultChunk, VaultFile

logger = logging.getLogger(__name__)


class IncrementalVaultIndexer:
    """Incremental vault indexer with FTS5"""

    def __init__(self, db_path: str, vault_path: Optional[str] = None):
        self.db_path = db_path
        self.vault_path = vault_path or os.getenv("VAULT_PATH", "/data/vault")

        if not self.vault_path or not Path(self.vault_path).exists():
            logger.warning(f"Vault path not accessible: {self.vault_path}")
            self.enabled = False
        else:
            self.enabled = True

    async def index_vault(
        self,
        correlation_id: str,
        force_full: bool = False,
    ) -> Tuple[int, int, int]:
        """
        Incremental vault indexing
        Returns: (new_files, changed_files, deleted_files)
        """
        if not self.enabled:
            logger.warning("Vault indexer disabled")
            return (0, 0, 0)

        new_count = 0
        changed_count = 0
        deleted_count = 0

        # Step 1: Collect file metadata
        current_files = self._collect_file_metadata()
        logger.info(f"Found {len(current_files)} files in vault")

        # Step 2: Get existing files from DB
        existing_files = await self._get_existing_files()
        existing_paths = {f["path"]: f for f in existing_files}

        # Step 3: Detect changes
        for file_meta in current_files:
            path = file_meta["path"]
            existing = existing_paths.get(path)

            if not existing:
                # New file
                await self._index_file(file_meta, correlation_id)
                new_count += 1
            elif force_full or self._is_changed(file_meta, existing):
                # Changed file
                await self._reindex_file(file_meta, existing["file_id"], correlation_id)
                changed_count += 1

        # Step 4: Detect deletions
        current_paths = {f["path"] for f in current_files}
        for existing_path in existing_paths:
            if existing_path not in current_paths:
                # Deleted file
                await self._delete_file(existing_paths[existing_path]["file_id"])
                deleted_count += 1

        logger.info(
            f"Indexing complete: {new_count} new, {changed_count} changed, {deleted_count} deleted"
        )

        return (new_count, changed_count, deleted_count)

    def _collect_file_metadata(self) -> List[dict]:
        """Collect file metadata (path, mtime, size)"""
        vault_path = Path(self.vault_path)
        files = []

        for md_file in vault_path.rglob("*.md"):
            try:
                stat = md_file.stat()
                rel_path = str(md_file.relative_to(vault_path))

                files.append(
                    {
                        "path": rel_path,
                        "abs_path": str(md_file),
                        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "size": stat.st_size,
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to stat {md_file}: {e}")

        return files

    async def _get_existing_files(self) -> List[dict]:
        """Get existing files from DB"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT file_id, path, sha256, mtime, size FROM vault_files"
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    def _is_changed(self, file_meta: dict, existing: dict) -> bool:
        """Check if file changed (mtime or size)"""
        return (
            file_meta["mtime"] != existing["mtime"]
            or file_meta["size"] != existing["size"]
        )

    async def _index_file(self, file_meta: dict, correlation_id: str) -> None:
        """Index new file"""
        file_id = str(uuid4())

        # Read file content
        try:
            content = Path(file_meta["abs_path"]).read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to read {file_meta['path']}: {e}")
            return

        # Calculate SHA256
        sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()

        # Parse metadata
        title, category, metadata = self._parse_file_metadata(content, file_meta["path"])

        # Insert vault_file
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO vault_files (file_id, path, sha256, mtime, size, title, category, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_id,
                    file_meta["path"],
                    sha256,
                    file_meta["mtime"],
                    file_meta["size"],
                    title,
                    category,
                    json.dumps(metadata, ensure_ascii=False),
                ),
            )
            await db.commit()

        # Chunk and insert
        chunks = self._chunk_text(content, file_id)
        await self._insert_chunks(chunks)

        logger.debug(f"Indexed new file: {file_meta['path']} ({len(chunks)} chunks)")

    async def _reindex_file(
        self, file_meta: dict, file_id: str, correlation_id: str
    ) -> None:
        """Reindex changed file"""
        # Read file content
        try:
            content = Path(file_meta["abs_path"]).read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to read {file_meta['path']}: {e}")
            return

        # Calculate SHA256
        sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()

        # Parse metadata
        title, category, metadata = self._parse_file_metadata(content, file_meta["path"])

        # Update vault_file
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE vault_files
                SET sha256 = ?, mtime = ?, size = ?, title = ?, category = ?, metadata_json = ?, indexed_at = ?
                WHERE file_id = ?
                """,
                (
                    sha256,
                    file_meta["mtime"],
                    file_meta["size"],
                    title,
                    category,
                    json.dumps(metadata, ensure_ascii=False),
                    datetime.now().isoformat(),
                    file_id,
                ),
            )

            # Delete old chunks (FTS5 trigger handles deletion)
            await db.execute(
                "DELETE FROM vault_chunks WHERE file_id = ?",
                (file_id,),
            )

            await db.commit()

        # Insert new chunks
        chunks = self._chunk_text(content, file_id)
        await self._insert_chunks(chunks)

        logger.debug(f"Reindexed file: {file_meta['path']} ({len(chunks)} chunks)")

    async def _delete_file(self, file_id: str) -> None:
        """Delete file (soft delete or hard delete)"""
        async with aiosqlite.connect(self.db_path) as db:
            # Hard delete (FTS5 trigger handles cleanup)
            await db.execute("DELETE FROM vault_chunks WHERE file_id = ?", (file_id,))
            await db.execute("DELETE FROM vault_files WHERE file_id = ?", (file_id,))
            await db.commit()

    def _chunk_text(self, text: str, file_id: str) -> List[VaultChunk]:
        """
        Chunk text into 120~200 line segments
        """
        lines = text.split("\n")
        chunks = []

        chunk_size = 150  # Target lines per chunk
        start = 0

        while start < len(lines):
            end = min(start + chunk_size, len(lines))
            chunk_text = "\n".join(lines[start:end])

            # Skip empty chunks
            if chunk_text.strip():
                chunk_sha256 = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()

                chunks.append(
                    VaultChunk(
                        chunk_id=str(uuid4()),
                        file_id=file_id,
                        start_line=start + 1,  # 1-indexed
                        end_line=end,
                        text=chunk_text,
                        sha256=chunk_sha256,
                    )
                )

            start = end

        return chunks

    async def _insert_chunks(self, chunks: List[VaultChunk]) -> None:
        """Insert chunks (FTS5 trigger auto-indexes)"""
        if not chunks:
            return

        async with aiosqlite.connect(self.db_path) as db:
            for chunk in chunks:
                await db.execute(
                    """
                    INSERT INTO vault_chunks (chunk_id, file_id, start_line, end_line, text, sha256)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.chunk_id,
                        chunk.file_id,
                        chunk.start_line,
                        chunk.end_line,
                        chunk.text,
                        chunk.sha256,
                    ),
                )
            await db.commit()

    def _parse_file_metadata(self, content: str, path: str) -> Tuple[str, str, dict]:
        """
        Parse file metadata (title, category, frontmatter)
        Returns: (title, category, metadata_dict)
        """
        title = Path(path).stem
        category = self._infer_category(path)
        metadata = {}

        # Parse YAML frontmatter
        if content.startswith("---"):
            try:
                end_index = content.find("---", 3)
                if end_index != -1:
                    frontmatter = content[3:end_index].strip()
                    import yaml

                    metadata = yaml.safe_load(frontmatter) or {}
                    title = metadata.get("title", title)
            except Exception as e:
                logger.warning(f"Failed to parse frontmatter in {path}: {e}")

        return title, category, metadata

    def _infer_category(self, path: str) -> str:
        """Infer category from path"""
        parts = path.split(os.sep)

        category_map = {
            "판례": "PRECEDENT",
            "precedent": "PRECEDENT",
            "법령": "LAW",
            "law": "LAW",
            "사건문서": "CASE_DOC",
            "cases": "CASE_DOC",
            "서면": "BRIEF",
            "briefs": "BRIEF",
            "연구": "RESEARCH",
            "research": "RESEARCH",
            "마케팅": "MARKETING",
            "marketing": "MARKETING",
            "운영": "OPS",
            "ops": "OPS",
        }

        for part in parts:
            if part.lower() in category_map:
                return category_map[part.lower()]

        return "RESEARCH"

    async def search_vault(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> List[dict]:
        """
        Search vault using FTS5
        Returns: List of {chunk_id, file_path, title, category, snippet, rank}
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            if category:
                cursor = await db.execute(
                    """
                    SELECT
                        chunk_id,
                        path,
                        title,
                        category,
                        snippet(vault_fts, 1, '[', ']', '...', 64) as snippet,
                        rank
                    FROM vault_fts
                    WHERE vault_fts MATCH ? AND category = ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (query, category, limit),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT
                        chunk_id,
                        path,
                        title,
                        category,
                        snippet(vault_fts, 1, '[', ']', '...', 64) as snippet,
                        rank
                    FROM vault_fts
                    WHERE vault_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (query, limit),
                )

            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
