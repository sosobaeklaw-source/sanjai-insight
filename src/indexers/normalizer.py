"""
Normalizer - 크롤링 데이터를 IndexedDocument로 정규화
PRD §6.6
"""

import json
import logging
from datetime import datetime
from typing import Optional

from ..db import db
from ..models import (
    CrawledData,
    DataType,
    DocumentCategory,
    DocumentSourceType,
    IndexedDocument,
)

logger = logging.getLogger(__name__)


class Normalizer:
    """크롤링 데이터 정규화"""

    async def normalize(self, crawled: CrawledData) -> Optional[IndexedDocument]:
        """
        CrawledData → IndexedDocument 변환

        Args:
            crawled: 크롤링된 원본 데이터

        Returns:
            정규화된 IndexedDocument 또는 None
        """
        try:
            # 데이터 타입별 정규화
            if crawled.data_type == DataType.PRECEDENT:
                return await self._normalize_precedent(crawled)
            elif crawled.data_type == DataType.POLICY:
                return await self._normalize_policy(crawled)
            elif crawled.data_type == DataType.TREND:
                return await self._normalize_trend(crawled)
            elif crawled.data_type == DataType.COMPETITOR_POST:
                return await self._normalize_competitor(crawled)
            else:
                logger.warning(f"Unknown data type: {crawled.data_type}")
                return None

        except Exception as e:
            logger.error(f"Failed to normalize {crawled.id}: {e}")
            return None

    async def _normalize_precedent(
        self, crawled: CrawledData
    ) -> Optional[IndexedDocument]:
        """판례 정규화"""
        metadata = crawled.metadata

        # 키워드 추출 (간단 구현)
        keywords = []
        if metadata.get("keyword"):
            keywords.append(metadata["keyword"])

        # 엔티티 추출 (간단 구현)
        entities = {
            "case_number": metadata.get("case_number"),
            "court": metadata.get("court"),
            "decision_date": metadata.get("decision_date"),
        }

        # 요약 (판시사항 사용)
        summary = metadata.get("summary", "")[:500]

        doc = IndexedDocument(
            crawled_data_id=crawled.id,
            source_type=DocumentSourceType.CRAWLED,
            category=DocumentCategory.PRECEDENT,
            subcategory=metadata.get("case_type"),
            title=metadata.get("case_name", "제목 없음"),
            date=self._parse_date(metadata.get("decision_date")),
            keywords=keywords,
            entities=entities,
            summary=summary,
            embedding_id=None,  # TODO: 벡터 임베딩 생성
        )

        return doc

    async def _normalize_policy(
        self, crawled: CrawledData
    ) -> Optional[IndexedDocument]:
        """정책 정규화"""
        metadata = crawled.metadata

        doc = IndexedDocument(
            crawled_data_id=crawled.id,
            source_type=DocumentSourceType.CRAWLED,
            category=DocumentCategory.LAW,
            subcategory="정책",
            title=metadata.get("title", "제목 없음"),
            date=self._parse_date(metadata.get("published_date")),
            keywords=metadata.get("keywords", []),
            entities={},
            summary=crawled.raw_content[:500],
            embedding_id=None,
        )

        return doc

    async def _normalize_trend(
        self, crawled: CrawledData
    ) -> Optional[IndexedDocument]:
        """트렌드 데이터 정규화"""
        metadata = crawled.metadata

        doc = IndexedDocument(
            crawled_data_id=crawled.id,
            source_type=DocumentSourceType.CRAWLED,
            category=DocumentCategory.RESEARCH,
            subcategory="트렌드",
            title=f"검색량 트렌드: {', '.join(metadata.get('keywords', []))}",
            date=datetime.now(),
            keywords=metadata.get("keywords", []),
            entities={"period": metadata.get("period")},
            summary=f"네이버 검색량 트렌드 데이터 ({metadata.get('period')})",
            embedding_id=None,
        )

        return doc

    async def _normalize_competitor(
        self, crawled: CrawledData
    ) -> Optional[IndexedDocument]:
        """경쟁사 게시물 정규화"""
        metadata = crawled.metadata

        doc = IndexedDocument(
            crawled_data_id=crawled.id,
            source_type=DocumentSourceType.CRAWLED,
            category=DocumentCategory.MARKETING,
            subcategory="경쟁사",
            title=metadata.get("title", "제목 없음"),
            date=self._parse_date(metadata.get("published")),
            keywords=metadata.get("tags", []),
            entities={
                "competitor": metadata.get("competitor_name"),
                "author": metadata.get("author"),
            },
            summary=crawled.raw_content[:500],
            embedding_id=None,
        )

        return doc

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """날짜 문자열 파싱"""
        if not date_str:
            return None

        try:
            # 다양한 날짜 형식 시도
            formats = [
                "%Y-%m-%d",
                "%Y%m%d",
                "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d",
            ]

            for fmt in formats:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue

            # ISO 형식 시도
            return datetime.fromisoformat(date_str)

        except Exception as e:
            logger.warning(f"Failed to parse date '{date_str}': {e}")
            return None

    async def save_indexed_document(self, doc: IndexedDocument) -> str:
        """IndexedDocument를 DB에 저장"""
        async with db.connect() as conn:
            await conn.execute(
                """
                INSERT INTO indexed_documents
                (id, crawled_data_id, source_type, category, subcategory,
                 title, date, keywords, entities, summary, embedding_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc.id,
                    doc.crawled_data_id,
                    doc.source_type.value,
                    doc.category.value,
                    doc.subcategory,
                    doc.title,
                    doc.date.isoformat() if doc.date else None,
                    json.dumps(doc.keywords, ensure_ascii=False),
                    json.dumps(doc.entities, ensure_ascii=False),
                    doc.summary,
                    doc.embedding_id,
                ),
            )
            await conn.commit()

        logger.info(f"Saved indexed document: {doc.id}")
        return doc.id

    async def process_crawled_data(self, limit: int = 100) -> int:
        """
        미처리 크롤링 데이터를 일괄 정규화

        Args:
            limit: 처리할 최대 개수

        Returns:
            처리된 개수
        """
        crawled_items = await db.list_crawled_data(status="NEW", limit=limit)

        processed = 0
        for item in crawled_items:
            try:
                # 정규화
                doc = await self.normalize(item)
                if doc:
                    # 저장
                    await self.save_indexed_document(doc)

                    # 원본 상태 업데이트
                    await db.update_crawled_data_status(item.id, "INDEXED")
                    processed += 1

            except Exception as e:
                logger.error(f"Failed to process {item.id}: {e}")
                continue

        logger.info(f"Processed {processed}/{len(crawled_items)} crawled items")
        return processed
