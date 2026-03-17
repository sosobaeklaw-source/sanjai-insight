"""
Full-text Search Engine with FTS5 and advanced querying.

Features:
- SQLite FTS5 full-text search
- Advanced query syntax
- Relevance ranking
- Faceted search
- Search suggestions
"""

import sqlite3
import logging
import os
import re
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json

logger = logging.getLogger(__name__)


class SearchMode(Enum):
    """Search matching modes."""
    EXACT = "exact"
    PREFIX = "prefix"
    FUZZY = "fuzzy"
    BOOLEAN = "boolean"


@dataclass
class SearchQuery:
    """Search query specification."""
    query: str
    mode: SearchMode = SearchMode.FUZZY
    filters: Dict[str, any] = field(default_factory=dict)
    limit: int = 10
    offset: int = 0
    highlight: bool = True


@dataclass
class SearchResult:
    """Search result with metadata."""
    doc_id: str
    title: str
    content: str
    snippet: str
    score: float
    metadata: Dict = field(default_factory=dict)
    highlights: List[str] = field(default_factory=list)


@dataclass
class SearchStats:
    """Search statistics."""
    total_results: int
    query_time_ms: float
    facets: Dict[str, Dict[str, int]] = field(default_factory=dict)


class SearchEngine:
    """
    Full-text search engine using SQLite FTS5.

    Features:
    - FTS5 with porter stemming
    - BM25 relevance ranking
    - Query expansion
    - Faceted search
    - Search suggestions
    """

    def __init__(self, db_path: str = "data/search.db"):
        """
        Initialize search engine.

        Args:
            db_path: Database file path
        """
        self.db_path = db_path
        self._ensure_db()

    def _ensure_db(self):
        """Create search database with FTS5."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            # Create FTS5 virtual table with porter stemmer
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
                USING fts5(
                    doc_id UNINDEXED,
                    title,
                    content,
                    category,
                    tags,
                    tokenize = 'porter unicode61'
                )
            """)

            # Create metadata table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    doc_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    category TEXT,
                    tags TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}'
                )
            """)

            # Create indexes
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_category
                ON documents(category)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_created
                ON documents(created_at)
            """)

            # Create search suggestions table
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS search_suggestions
                USING fts5(
                    suggestion,
                    frequency UNINDEXED,
                    tokenize = 'porter unicode61'
                )
            """)

    def index_document(
        self,
        doc_id: str,
        title: str,
        content: str,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict] = None
    ):
        """
        Index a document for searching.

        Args:
            doc_id: Document identifier
            title: Document title
            content: Document content
            category: Optional category
            tags: Optional tags
            metadata: Optional metadata
        """
        now = datetime.utcnow().isoformat()
        tags_str = json.dumps(tags) if tags else "[]"
        metadata_str = json.dumps(metadata) if metadata else "{}"

        with sqlite3.connect(self.db_path) as conn:
            # Insert into metadata table
            conn.execute("""
                INSERT OR REPLACE INTO documents
                (doc_id, title, content, category, tags, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc_id,
                title,
                content,
                category,
                tags_str,
                now,
                now,
                metadata_str
            ))

            # Insert into FTS5 table
            conn.execute("""
                INSERT OR REPLACE INTO documents_fts
                (doc_id, title, content, category, tags)
                VALUES (?, ?, ?, ?, ?)
            """, (
                doc_id,
                title,
                content,
                category or "",
                " ".join(tags) if tags else ""
            ))

        logger.info(f"Indexed document: {doc_id}")

    def search(
        self,
        query: SearchQuery
    ) -> Tuple[List[SearchResult], SearchStats]:
        """
        Search for documents.

        Args:
            query: Search query specification

        Returns:
            Tuple of (results, statistics)
        """
        start_time = datetime.utcnow()

        # Build FTS5 query
        fts_query = self._build_fts_query(query.query, query.mode)

        # Build filter conditions
        where_clauses = []
        params = []

        if query.filters:
            for field, value in query.filters.items():
                if field == "category":
                    where_clauses.append("d.category = ?")
                    params.append(value)
                elif field == "created_after":
                    where_clauses.append("d.created_at > ?")
                    params.append(value)
                elif field == "created_before":
                    where_clauses.append("d.created_at < ?")
                    params.append(value)

        where_sql = ""
        if where_clauses:
            where_sql = "AND " + " AND ".join(where_clauses)

        # Execute search
        with sqlite3.connect(self.db_path) as conn:
            sql = f"""
                SELECT
                    d.doc_id,
                    d.title,
                    d.content,
                    d.category,
                    d.metadata,
                    bm25(documents_fts) as score,
                    snippet(documents_fts, 2, '<mark>', '</mark>', '...', 32) as snippet
                FROM documents_fts
                JOIN documents d ON documents_fts.doc_id = d.doc_id
                WHERE documents_fts MATCH ?
                {where_sql}
                ORDER BY score
                LIMIT ? OFFSET ?
            """

            cursor = conn.execute(
                sql,
                [fts_query] + params + [query.limit, query.offset]
            )

            results = []
            for row in cursor.fetchall():
                highlights = []
                if query.highlight:
                    highlights = self._extract_highlights(row[6])

                results.append(SearchResult(
                    doc_id=row[0],
                    title=row[1],
                    content=row[2],
                    snippet=row[6],
                    score=abs(row[5]),  # BM25 returns negative scores
                    metadata=json.loads(row[4]) if row[4] else {},
                    highlights=highlights
                ))

            # Get total count
            count_sql = f"""
                SELECT COUNT(*)
                FROM documents_fts
                JOIN documents d ON documents_fts.doc_id = d.doc_id
                WHERE documents_fts MATCH ?
                {where_sql}
            """
            cursor = conn.execute(count_sql, [fts_query] + params)
            total_results = cursor.fetchone()[0]

            # Get facets if filters applied
            facets = {}
            if query.filters.get("category"):
                facets = self._get_facets(conn, fts_query, params)

        elapsed = (datetime.utcnow() - start_time).total_seconds() * 1000

        stats = SearchStats(
            total_results=total_results,
            query_time_ms=elapsed,
            facets=facets
        )

        # Update search suggestions
        self._update_suggestions(query.query)

        return results, stats

    def _build_fts_query(self, query: str, mode: SearchMode) -> str:
        """
        Build FTS5 query from search query.

        Args:
            query: User query
            mode: Search mode

        Returns:
            FTS5 query string
        """
        # Clean query
        query = query.strip()

        if mode == SearchMode.EXACT:
            return f'"{query}"'

        elif mode == SearchMode.PREFIX:
            terms = query.split()
            return " ".join(f"{term}*" for term in terms)

        elif mode == SearchMode.FUZZY:
            # Use prefix matching for fuzzy
            terms = query.split()
            return " ".join(f"{term}*" for term in terms)

        elif mode == SearchMode.BOOLEAN:
            # Pass through for boolean queries (AND, OR, NOT)
            return query

        return query

    def _extract_highlights(self, snippet: str) -> List[str]:
        """Extract highlighted terms from snippet."""
        pattern = r'<mark>(.*?)</mark>'
        matches = re.findall(pattern, snippet)
        return matches

    def _get_facets(
        self,
        conn: sqlite3.Connection,
        fts_query: str,
        params: List
    ) -> Dict[str, Dict[str, int]]:
        """Get faceted counts for search results."""
        facets = {}

        # Category facets
        sql = """
            SELECT d.category, COUNT(*) as count
            FROM documents_fts
            JOIN documents d ON documents_fts.doc_id = d.doc_id
            WHERE documents_fts MATCH ?
            GROUP BY d.category
            ORDER BY count DESC
            LIMIT 10
        """

        cursor = conn.execute(sql, [fts_query])
        category_facets = {}

        for row in cursor.fetchall():
            if row[0]:
                category_facets[row[0]] = row[1]

        facets["category"] = category_facets

        return facets

    def _update_suggestions(self, query: str):
        """Update search suggestions based on query."""
        query = query.strip().lower()

        if len(query) < 3:
            return

        with sqlite3.connect(self.db_path) as conn:
            # Check if suggestion exists
            cursor = conn.execute(
                "SELECT frequency FROM search_suggestions WHERE suggestion = ?",
                (query,)
            )

            row = cursor.fetchone()

            if row:
                # Increment frequency
                conn.execute(
                    "UPDATE search_suggestions SET frequency = frequency + 1 WHERE suggestion = ?",
                    (query,)
                )
            else:
                # Insert new suggestion
                conn.execute(
                    "INSERT INTO search_suggestions (suggestion, frequency) VALUES (?, 1)",
                    (query,)
                )

    def get_suggestions(self, prefix: str, limit: int = 5) -> List[str]:
        """
        Get search suggestions based on prefix.

        Args:
            prefix: Search prefix
            limit: Maximum suggestions

        Returns:
            List of suggested queries
        """
        if len(prefix) < 2:
            return []

        with sqlite3.connect(self.db_path) as conn:
            sql = """
                SELECT suggestion
                FROM search_suggestions
                WHERE suggestion MATCH ?
                ORDER BY frequency DESC
                LIMIT ?
            """

            cursor = conn.execute(sql, (f"{prefix}*", limit))
            suggestions = [row[0] for row in cursor.fetchall()]

            return suggestions

    def delete_document(self, doc_id: str):
        """
        Delete document from index.

        Args:
            doc_id: Document to delete
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
            conn.execute("DELETE FROM documents_fts WHERE doc_id = ?", (doc_id,))

        logger.info(f"Deleted document: {doc_id}")

    def bulk_index(self, documents: List[Dict]):
        """
        Bulk index multiple documents.

        Args:
            documents: List of document dicts with keys:
                      doc_id, title, content, category, tags, metadata
        """
        with sqlite3.connect(self.db_path) as conn:
            now = datetime.utcnow().isoformat()

            for doc in documents:
                tags_str = json.dumps(doc.get("tags", []))
                metadata_str = json.dumps(doc.get("metadata", {}))

                conn.execute("""
                    INSERT OR REPLACE INTO documents
                    (doc_id, title, content, category, tags, created_at, updated_at, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    doc["doc_id"],
                    doc["title"],
                    doc["content"],
                    doc.get("category"),
                    tags_str,
                    now,
                    now,
                    metadata_str
                ))

                conn.execute("""
                    INSERT OR REPLACE INTO documents_fts
                    (doc_id, title, content, category, tags)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    doc["doc_id"],
                    doc["title"],
                    doc["content"],
                    doc.get("category", ""),
                    " ".join(doc.get("tags", []))
                ))

        logger.info(f"Bulk indexed {len(documents)} documents")

    def optimize(self):
        """Optimize FTS5 index."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO documents_fts(documents_fts) VALUES('optimize')")

        logger.info("Optimized search index")

    def get_stats(self) -> Dict:
        """Get index statistics."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM documents")
            total_docs = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(DISTINCT category) FROM documents WHERE category IS NOT NULL")
            total_categories = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM search_suggestions")
            total_suggestions = cursor.fetchone()[0]

            return {
                "total_documents": total_docs,
                "total_categories": total_categories,
                "total_suggestions": total_suggestions
            }
