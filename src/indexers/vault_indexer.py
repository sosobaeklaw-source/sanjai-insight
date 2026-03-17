"""
Vault Indexer - Obsidian 볼트 인덱싱
PRD §6.6

NOTE: Obsidian 볼트 경로는 환경변수로 설정
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from ..models import DocumentCategory, DocumentSourceType, IndexedDocument

logger = logging.getLogger(__name__)


class VaultIndexer:
    """Obsidian 볼트 인덱서"""

    def __init__(self, vault_path: Optional[str] = None):
        self.vault_path = vault_path or os.getenv("OBSIDIAN_VAULT_PATH")

        if not self.vault_path:
            logger.warning("OBSIDIAN_VAULT_PATH not configured. VaultIndexer disabled.")
            self.enabled = False
        else:
            self.vault_path = Path(self.vault_path)
            self.enabled = self.vault_path.exists()

            if not self.enabled:
                logger.warning(f"Vault path does not exist: {self.vault_path}")

    async def index_vault(self) -> list[IndexedDocument]:
        """
        Obsidian 볼트 전체 인덱싱

        파일 유형:
        - *.md: Markdown 문서
        - 카테고리는 폴더 구조로 추론

        Returns:
            IndexedDocument 리스트
        """
        if not self.enabled:
            logger.warning("VaultIndexer is disabled. Skipping.")
            return []

        documents = []

        try:
            # .md 파일 모두 찾기
            md_files = list(self.vault_path.rglob("*.md"))
            logger.info(f"Found {len(md_files)} markdown files in vault")

            for md_file in md_files:
                try:
                    doc = await self._index_file(md_file)
                    if doc:
                        documents.append(doc)
                except Exception as e:
                    logger.error(f"Failed to index {md_file}: {e}")
                    continue

            logger.info(f"Indexed {len(documents)} documents from vault")

        except Exception as e:
            logger.error(f"Failed to index vault: {e}")

        return documents

    async def _index_file(self, file_path: Path) -> Optional[IndexedDocument]:
        """
        단일 Markdown 파일 인덱싱

        Args:
            file_path: 파일 경로

        Returns:
            IndexedDocument 또는 None
        """
        try:
            # 파일 읽기
            content = file_path.read_text(encoding="utf-8")

            # 메타데이터 파싱 (YAML frontmatter)
            metadata = self._parse_frontmatter(content)

            # 카테고리 추론 (폴더명 기반)
            category = self._infer_category(file_path)

            # 키워드 추출 (간단 구현)
            keywords = metadata.get("tags", [])
            if isinstance(keywords, str):
                keywords = [k.strip() for k in keywords.split(",")]

            # 요약 생성 (첫 500자)
            summary = self._extract_summary(content)

            doc = IndexedDocument(
                crawled_data_id=None,
                source_type=DocumentSourceType.VAULT,
                category=category,
                subcategory=file_path.parent.name,
                title=metadata.get("title", file_path.stem),
                date=None,  # TODO: 파일 수정 시간 또는 메타데이터에서 추출
                keywords=keywords,
                entities={},
                summary=summary,
                embedding_id=None,
            )

            return doc

        except Exception as e:
            logger.error(f"Failed to index file {file_path}: {e}")
            return None

    def _parse_frontmatter(self, content: str) -> dict:
        """
        YAML frontmatter 파싱

        예시:
        ---
        title: 문서 제목
        tags: [산재, 판례]
        ---
        """
        metadata = {}

        try:
            if content.startswith("---"):
                # frontmatter 추출
                end_index = content.find("---", 3)
                if end_index != -1:
                    frontmatter = content[3:end_index].strip()

                    # YAML 파싱
                    import yaml

                    metadata = yaml.safe_load(frontmatter) or {}

        except Exception as e:
            logger.warning(f"Failed to parse frontmatter: {e}")

        return metadata

    def _infer_category(self, file_path: Path) -> DocumentCategory:
        """
        파일 경로에서 카테고리 추론

        폴더 구조 예시:
        - 판례/
        - 법령/
        - 사건문서/
        - 서면/
        - 연구/
        - 마케팅/
        - 운영/
        """
        folder_name = file_path.parent.name.lower()

        category_map = {
            "판례": DocumentCategory.PRECEDENT,
            "precedent": DocumentCategory.PRECEDENT,
            "법령": DocumentCategory.LAW,
            "law": DocumentCategory.LAW,
            "사건문서": DocumentCategory.CASE_DOC,
            "cases": DocumentCategory.CASE_DOC,
            "서면": DocumentCategory.BRIEF,
            "briefs": DocumentCategory.BRIEF,
            "연구": DocumentCategory.RESEARCH,
            "research": DocumentCategory.RESEARCH,
            "마케팅": DocumentCategory.MARKETING,
            "marketing": DocumentCategory.MARKETING,
            "운영": DocumentCategory.OPS,
            "ops": DocumentCategory.OPS,
        }

        return category_map.get(folder_name, DocumentCategory.RESEARCH)

    def _extract_summary(self, content: str) -> str:
        """
        요약 추출

        - frontmatter 제거
        - 첫 500자
        """
        # frontmatter 제거
        if content.startswith("---"):
            end_index = content.find("---", 3)
            if end_index != -1:
                content = content[end_index + 3 :].strip()

        # 첫 500자
        summary = content[:500]

        return summary
