"""
Tests for Normalizer
"""

from datetime import datetime

import pytest

from src.indexers.normalizer import Normalizer
from src.models import CrawledData, DataType, DocumentCategory, SourceType


@pytest.mark.asyncio
async def test_normalize_precedent(test_db):
    """Test precedent normalization"""
    normalizer = Normalizer()

    crawled = CrawledData(
        source=SourceType.SUPREME_COURT,
        data_type=DataType.PRECEDENT,
        raw_content="판례 내용",
        metadata={
            "case_number": "2023다12345",
            "case_name": "산재보험 급여 부지급처분 취소",
            "court": "대법원",
            "decision_date": "2023-12-01",
            "case_type": "민사",
            "summary": "업무상 재해 인정 기준에 관한 판시",
            "keyword": "산재보험",
        },
    )

    doc = await normalizer.normalize(crawled)

    assert doc is not None
    assert doc.category == DocumentCategory.PRECEDENT
    assert doc.title == "산재보험 급여 부지급처분 취소"
    assert "산재보험" in doc.keywords
    assert doc.entities["case_number"] == "2023다12345"


@pytest.mark.asyncio
async def test_normalize_trend(test_db):
    """Test trend data normalization"""
    normalizer = Normalizer()

    crawled = CrawledData(
        source=SourceType.NAVER_TREND,
        data_type=DataType.TREND,
        raw_content="트렌드 데이터",
        metadata={
            "keywords": ["산재 신청", "산재 승인"],
            "period": "2024-01 ~ 2024-02",
        },
    )

    doc = await normalizer.normalize(crawled)

    assert doc is not None
    assert doc.category == DocumentCategory.RESEARCH
    assert doc.subcategory == "트렌드"
    assert len(doc.keywords) == 2


@pytest.mark.asyncio
async def test_date_parsing():
    """Test date parsing"""
    normalizer = Normalizer()

    # Test various formats
    assert normalizer._parse_date("2023-12-01") is not None
    assert normalizer._parse_date("20231201") is not None
    assert normalizer._parse_date("2023/12/01") is not None
    assert normalizer._parse_date("invalid") is None
    assert normalizer._parse_date(None) is None
