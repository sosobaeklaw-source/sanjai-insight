"""
Competitor Crawler - 경쟁사 블로그 모니터링
PRD §6.6
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import yaml

from ..models import CrawledData, DataType, SourceType
from .base import BaseCrawler

logger = logging.getLogger(__name__)


class CompetitorCrawler(BaseCrawler):
    """경쟁사 블로그 크롤러"""

    def __init__(self):
        super().__init__(SourceType.COMPETITOR)
        self.competitors = self._load_competitors()

    def _load_competitors(self) -> list[dict]:
        """경쟁사 목록 로드"""
        try:
            with open("config/competitors.yaml", "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            return [
                c for c in config.get("competitors", []) if c.get("enabled", False)
            ]
        except Exception as e:
            logger.warning(f"Failed to load competitors: {e}")
            return []

    async def _crawl(self) -> list[CrawledData]:
        """
        경쟁사 블로그 크롤링

        수집 항목:
        - 제목
        - 내용
        - 발행일
        - 태그
        - URL
        """
        items = []

        if not self.competitors:
            logger.info("No competitors configured. Skipping.")
            return items

        for competitor in self.competitors:
            try:
                name = competitor.get("name")
                blog_url = competitor.get("blog_url")
                rss_url = competitor.get("rss_url")
                tags = competitor.get("tags", [])

                logger.info(f"Crawling competitor: {name}")

                # RSS 우선, 없으면 웹 크롤링
                if rss_url:
                    posts = await self._crawl_rss(name, rss_url, tags)
                else:
                    posts = await self._crawl_blog(name, blog_url, tags)

                items.extend(posts)
                logger.info(f"Collected {len(posts)} posts from {name}")

            except Exception as e:
                logger.error(f"Failed to crawl competitor {name}: {e}")
                continue

        # DB 저장
        await self.save_crawled_data(items)

        return items

    async def _crawl_rss(
        self, name: str, rss_url: str, tags: list[str]
    ) -> list[CrawledData]:
        """RSS 피드로 크롤링"""
        items = []

        try:
            import feedparser
            import asyncio

            loop = asyncio.get_event_loop()
            feed = await loop.run_in_executor(None, feedparser.parse, rss_url)

            # 최근 30일 게시물만 수집
            cutoff_date = datetime.now() - timedelta(days=30)

            for entry in feed.entries[:10]:  # 최대 10개
                try:
                    # 발행일 파싱
                    published = entry.get("published_parsed")
                    if published:
                        pub_date = datetime(*published[:6])
                        if pub_date < cutoff_date:
                            continue

                    # 태그 필터링
                    entry_tags = [t.get("term", "") for t in entry.get("tags", [])]
                    if tags and not any(tag in entry_tags for tag in tags):
                        continue

                    # CrawledData 생성
                    item = CrawledData(
                        source=self.source,
                        crawled_at=datetime.now(),
                        data_type=DataType.COMPETITOR_POST,
                        raw_content=entry.get("summary", ""),
                        metadata={
                            "competitor_name": name,
                            "title": entry.get("title"),
                            "link": entry.get("link"),
                            "published": str(pub_date) if published else None,
                            "author": entry.get("author"),
                            "tags": entry_tags,
                        },
                    )
                    items.append(item)

                except Exception as e:
                    logger.error(f"Failed to parse RSS entry: {e}")
                    continue

        except Exception as e:
            logger.error(f"Failed to crawl RSS {rss_url}: {e}")

        return items

    async def _crawl_blog(
        self, name: str, blog_url: str, tags: list[str]
    ) -> list[CrawledData]:
        """웹 크롤링 (RSS 없는 경우)"""
        items = []

        try:
            soup = await self.fetch_html(blog_url)
            if not soup:
                return items

            # TODO: 사이트별 HTML 구조에 맞춰 파싱 로직 구현
            # 예시: WordPress 기반 블로그
            # articles = soup.find_all("article", class_="post")
            # for article in articles:
            #     title = article.find("h2", class_="entry-title").text
            #     link = article.find("a")["href"]
            #     date = article.find("time")["datetime"]
            #     content = article.find("div", class_="entry-content").text
            #     ...

            logger.warning(
                f"[MOCK] Web crawling for {blog_url} not yet implemented. "
                "Each site requires custom parsing logic."
            )

        except Exception as e:
            logger.error(f"Failed to crawl blog {blog_url}: {e}")

        return items

    def analyze_competitor_post(self, post: CrawledData) -> dict:
        """
        경쟁사 게시물 분석 (선택적)

        분석 항목:
        - 주제
        - 키워드
        - 콘텐츠 길이
        - SEO 품질
        """
        analysis = {
            "competitor": post.metadata.get("competitor_name"),
            "title": post.metadata.get("title"),
            "word_count": len(post.raw_content.split()),
            "has_images": False,  # TODO: 실제 분석
            "seo_score": 0.0,  # TODO: 실제 분석
        }

        return analysis
