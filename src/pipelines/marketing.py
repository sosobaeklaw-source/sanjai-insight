"""
MarketingPipeline - Insight to Marketing Content Automation
인사이트 → 마케팅 콘텐츠 자동 생성 파이프라인

Features:
1. Content Transformation (Blog, SNS, Ads)
2. SEO Optimization (Keywords, Meta Tags, Schema.org)
3. Content Scheduling (Time-based Recommendations)
4. A/B Testing (Title Variants, CTR Prediction)
5. Compliance Checking (Legal Risk, False Advertising)
"""

import hashlib
import json
import re
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import uuid4

from ..db import Database
from ..models import ContentStatus, ContentType, Insight, MarketingContent


class MarketingPipeline:
    """Marketing Content Generation Pipeline"""

    def __init__(self, db: Database):
        self.db = db

        # Compliance risk keywords
        self.risk_keywords = {
            "법적 리스크": [
                "100% 승소",
                "무조건",
                "반드시",
                "확실한",
                "보장합니다",
                "단 1건도 패소한 적 없습니다",
            ],
            "과장 광고": [
                "최고",
                "최저가",
                "1위",
                "독보적",
                "타의 추종을 불허",
                "비교불가",
            ],
            "의료법 위반": ["치료", "완치", "효과", "의료"],
            "금융법 위반": ["수익 보장", "원금 보장", "무위험"],
        }

        # SEO keyword templates by insight type
        self.seo_templates = {
            "CASE_IMPACT": [
                "산재 판례",
                "산재 승소",
                "산재 보상",
                "산재 신청",
                "근로복지공단",
            ],
            "MARKET_OPPORTUNITY": [
                "산재 노무사",
                "산재 상담",
                "산재 전문",
                "산재 법률",
                "산재 처리",
            ],
            "STRATEGY_SHIFT": [
                "산재 전략",
                "산재 대응",
                "산재 절차",
                "산재 팁",
                "산재 가이드",
            ],
        }

        # Content scheduling rules (hour of day, day of week)
        self.scheduling_rules = {
            "BLOG": {
                "best_hours": [9, 10, 14, 15],  # 오전 10시, 오후 3시
                "best_days": [1, 2, 3, 4],  # 화-금
            },
            "SNS": {
                "best_hours": [12, 18, 20],  # 점심, 저녁
                "best_days": [0, 1, 2, 3, 4, 5, 6],  # 매일
            },
            "NEWSLETTER": {
                "best_hours": [8, 9],  # 출근 시간
                "best_days": [1, 3],  # 화, 목
            },
        }

    async def generate_content(
        self, insight_id: str, content_types: list[str]
    ) -> list[str]:
        """
        Generate marketing content from insight

        Args:
            insight_id: Insight ID
            content_types: List of content types to generate (BLOG, SNS, NEWSLETTER)

        Returns:
            List of created content IDs
        """
        # Load insight
        insight = await self.db.get_insight(insight_id)
        if not insight:
            raise ValueError(f"Insight not found: {insight_id}")

        content_ids = []

        for content_type in content_types:
            if content_type == "BLOG":
                content_id = await self._generate_blog(insight)
            elif content_type == "SNS":
                content_id = await self._generate_sns(insight)
            elif content_type == "NEWSLETTER":
                content_id = await self._generate_newsletter(insight)
            else:
                raise ValueError(f"Unknown content type: {content_type}")

            content_ids.append(content_id)

        return content_ids

    async def _generate_blog(self, insight: Insight) -> str:
        """Generate blog post from insight"""
        # Extract key information
        title_variants = self._generate_title_variants(insight, "BLOG")
        body_sections = self._transform_insight_to_blog(insight)

        # SEO optimization
        keywords = self._extract_keywords(insight)
        seo_meta = self._generate_seo_meta(title_variants[0], body_sections, keywords)

        # Compliance check
        legal_review = self._check_compliance(title_variants[0], body_sections)

        # Create draft
        draft = self._format_blog_post(title_variants[0], body_sections)

        # Create content record
        content = MarketingContent(
            insight_id=insight.id,
            content_type=ContentType.BLOG,
            title=title_variants[0],
            target_keyword=keywords[0] if keywords else None,
            seo_meta={
                "title_variants": title_variants,
                "meta_description": seo_meta["meta_description"],
                "keywords": keywords,
                "schema_org": seo_meta["schema_org"],
            },
            draft=draft,
            legal_review=legal_review,
            status=ContentStatus.DRAFT,
        )

        # Save to DB
        content_id = await self._save_content(content)

        return content_id

    async def _generate_sns(self, insight: Insight) -> str:
        """Generate SNS post from insight"""
        # Generate variants for different platforms
        variants = {
            "twitter": self._generate_twitter_post(insight),
            "instagram": self._generate_instagram_post(insight),
            "linkedin": self._generate_linkedin_post(insight),
        }

        # Select best variant
        best_variant = self._select_best_variant(variants)

        # Compliance check
        legal_review = self._check_compliance(
            best_variant["title"], best_variant["body"]
        )

        # Create content record
        content = MarketingContent(
            insight_id=insight.id,
            content_type=ContentType.SNS,
            title=best_variant["title"],
            seo_meta={"variants": variants, "selected": best_variant["platform"]},
            draft=best_variant["body"],
            legal_review=legal_review,
            status=ContentStatus.DRAFT,
        )

        content_id = await self._save_content(content)
        return content_id

    async def _generate_newsletter(self, insight: Insight) -> str:
        """Generate newsletter content from insight"""
        # Generate newsletter sections
        sections = self._transform_insight_to_newsletter(insight)

        # Generate subject line variants
        subject_variants = self._generate_title_variants(insight, "NEWSLETTER")

        # Compliance check
        legal_review = self._check_compliance(subject_variants[0], sections)

        # Format newsletter
        draft = self._format_newsletter(subject_variants[0], sections)

        # Create content record
        content = MarketingContent(
            insight_id=insight.id,
            content_type=ContentType.NEWSLETTER,
            title=subject_variants[0],
            seo_meta={"subject_variants": subject_variants},
            draft=draft,
            legal_review=legal_review,
            status=ContentStatus.DRAFT,
        )

        content_id = await self._save_content(content)
        return content_id

    def _generate_title_variants(self, insight: Insight, content_type: str) -> list[str]:
        """Generate 3 title variants for A/B testing"""
        base_title = insight.title

        if content_type == "BLOG":
            variants = [
                base_title,
                f"[실무 가이드] {base_title}",
                f"{base_title} - 전문가가 알려드립니다",
            ]
        elif content_type == "NEWSLETTER":
            variants = [
                f"📩 {base_title}",
                f"[산재뉴스] {base_title}",
                f"알아두면 유용한 {base_title}",
            ]
        else:
            variants = [base_title]

        return variants

    def _transform_insight_to_blog(self, insight: Insight) -> str:
        """Transform insight body to blog post content"""
        body = insight.body
        sections = []

        # Introduction
        intro = f"최근 {insight.type.value} 관련하여 중요한 변화가 있었습니다."
        sections.append(intro)

        # Main content
        if "summary" in body:
            sections.append(f"\n## 요약\n{body['summary']}")

        if "impact" in body:
            sections.append(f"\n## 영향\n{body['impact']}")

        if "details" in body:
            sections.append(f"\n## 상세 내용\n{body['details']}")

        # Suggested actions
        if insight.suggested_actions:
            actions_text = "\n".join(
                [f"- {action}" for action in insight.suggested_actions]
            )
            sections.append(f"\n## 권장 조치\n{actions_text}")

        # Conclusion
        conclusion = "산재 관련 궁금한 점이 있으시면 소백노무법인으로 문의해주세요."
        sections.append(f"\n## 문의\n{conclusion}")

        return "\n".join(sections)

    def _transform_insight_to_newsletter(self, insight: Insight) -> str:
        """Transform insight to newsletter format"""
        sections = []

        # Header
        sections.append("안녕하세요, 소백노무법인입니다.\n")

        # Key insight
        sections.append(f"## {insight.title}\n")
        sections.append(f"{insight.body.get('summary', '')}\n")

        # CTA
        sections.append("더 자세한 내용은 블로그에서 확인하세요.")
        sections.append("[블로그 바로가기](https://sobaeklaw.com/blog)\n")

        # Footer
        sections.append("---")
        sections.append("소백노무법인")
        sections.append("수신거부: [링크]")

        return "\n".join(sections)

    def _generate_twitter_post(self, insight: Insight) -> dict[str, str]:
        """Generate Twitter post (280 characters)"""
        summary = insight.body.get("summary", insight.title)
        short_text = summary[:250]

        return {
            "platform": "twitter",
            "title": insight.title[:100],
            "body": f"{short_text}\n\n#산재 #노무사 #소백노무법인",
        }

    def _generate_instagram_post(self, insight: Insight) -> dict[str, str]:
        """Generate Instagram post"""
        return {
            "platform": "instagram",
            "title": insight.title,
            "body": f"{insight.title}\n\n{insight.body.get('summary', '')}\n\n"
            f"#산재 #노무사 #산재보상 #근로복지공단 #소백노무법인",
        }

    def _generate_linkedin_post(self, insight: Insight) -> dict[str, str]:
        """Generate LinkedIn post"""
        return {
            "platform": "linkedin",
            "title": insight.title,
            "body": f"[산재 인사이트] {insight.title}\n\n"
            f"{insight.body.get('summary', '')}\n\n"
            f"전문가 상담이 필요하시면 소백노무법인으로 연락주세요.",
        }

    def _select_best_variant(self, variants: dict[str, dict]) -> dict[str, str]:
        """Select best variant based on predicted CTR"""
        # Simple heuristic: prefer longer content for engagement
        scores = {}
        for platform, content in variants.items():
            scores[platform] = len(content["body"])

        best_platform = max(scores, key=scores.get)
        return variants[best_platform]

    def _format_blog_post(self, title: str, body: str) -> str:
        """Format blog post with markdown"""
        return f"# {title}\n\n{body}"

    def _format_newsletter(self, subject: str, body: str) -> str:
        """Format newsletter HTML"""
        return f"<h1>{subject}</h1>\n\n{body}"

    def _extract_keywords(self, insight: Insight) -> list[str]:
        """Extract SEO keywords from insight"""
        keywords = []

        # Get template keywords
        template_keywords = self.seo_templates.get(insight.type.value, [])
        keywords.extend(template_keywords[:3])

        # Extract from title
        title_words = insight.title.split()
        keywords.extend([word for word in title_words if len(word) >= 2][:2])

        # Extract from body
        body_text = json.dumps(insight.body, ensure_ascii=False)
        body_words = re.findall(r"\w+", body_text)
        important_words = [word for word in body_words if len(word) >= 3]
        keywords.extend(important_words[:2])

        # Deduplicate
        unique_keywords = list(dict.fromkeys(keywords))

        return unique_keywords[:8]

    def _generate_seo_meta(
        self, title: str, body: str, keywords: list[str]
    ) -> dict[str, Any]:
        """Generate SEO meta tags"""
        # Meta description (150-160 chars)
        description = body[:150].strip()
        if len(body) > 150:
            description += "..."

        # Schema.org structured data
        schema_org = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": title,
            "description": description,
            "keywords": ", ".join(keywords),
            "author": {"@type": "Organization", "name": "소백노무법인"},
            "publisher": {
                "@type": "Organization",
                "name": "소백노무법인",
                "logo": {
                    "@type": "ImageObject",
                    "url": "https://sobaeklaw.com/logo.png",
                },
            },
        }

        return {
            "meta_description": description,
            "keywords": keywords,
            "schema_org": schema_org,
        }

    def _check_compliance(self, title: str, body: str) -> dict[str, Any]:
        """Check legal compliance and false advertising"""
        issues = []
        risk_level = "LOW"

        full_text = f"{title} {body}"

        # Check risk keywords
        for category, keywords in self.risk_keywords.items():
            for keyword in keywords:
                if keyword in full_text:
                    issues.append(
                        {
                            "category": category,
                            "keyword": keyword,
                            "severity": "HIGH",
                            "suggestion": f"'{keyword}' 표현을 완화하거나 제거하세요.",
                        }
                    )
                    risk_level = "HIGH"

        # Check exaggeration patterns
        exaggeration_patterns = [
            r"\d+%\s*승소",
            r"무조건\s+\w+",
            r"반드시\s+\w+",
            r"최고[의]?\s+\w+",
        ]

        for pattern in exaggeration_patterns:
            matches = re.findall(pattern, full_text)
            for match in matches:
                issues.append(
                    {
                        "category": "과장 광고",
                        "keyword": match,
                        "severity": "MEDIUM",
                        "suggestion": f"'{match}' 표현이 과장되었을 수 있습니다.",
                    }
                )
                if risk_level == "LOW":
                    risk_level = "MEDIUM"

        # Auto-fix suggestions
        auto_fixes = []
        if risk_level == "HIGH":
            auto_fixes.append("법적 리스크가 있는 표현을 제거하거나 완화하세요.")
        if risk_level == "MEDIUM":
            auto_fixes.append("과장된 표현을 객관적 표현으로 변경하세요.")

        return {
            "risk_level": risk_level,
            "issues": issues,
            "auto_fixes": auto_fixes,
            "checked_at": datetime.now().isoformat(),
        }

    async def schedule_content(
        self, content_id: str, preferred_time: Optional[datetime] = None
    ) -> datetime:
        """
        Schedule content publication

        Args:
            content_id: Content ID
            preferred_time: Preferred publication time (optional)

        Returns:
            Scheduled publication time
        """
        # Load content
        content = await self._get_content(content_id)
        if not content:
            raise ValueError(f"Content not found: {content_id}")

        # If preferred time provided, use it
        if preferred_time:
            scheduled_time = preferred_time
        else:
            # Calculate optimal time based on content type
            scheduled_time = self._calculate_optimal_time(content.content_type.value)

        # Update content with scheduled time
        await self._update_content_schedule(content_id, scheduled_time)

        return scheduled_time

    def _calculate_optimal_time(self, content_type: str) -> datetime:
        """Calculate optimal publication time"""
        now = datetime.now()
        rules = self.scheduling_rules.get(content_type, self.scheduling_rules["BLOG"])

        # Find next best day
        best_days = rules["best_days"]
        best_hours = rules["best_hours"]

        # Start from tomorrow
        candidate = now + timedelta(days=1)

        # Find next best day
        while candidate.weekday() not in best_days:
            candidate += timedelta(days=1)

        # Set best hour
        optimal_hour = best_hours[0]
        scheduled_time = candidate.replace(hour=optimal_hour, minute=0, second=0)

        return scheduled_time

    async def analyze_performance(self, content_id: str) -> dict[str, Any]:
        """
        Analyze content performance (placeholder for future integration)

        Args:
            content_id: Content ID

        Returns:
            Performance metrics
        """
        content = await self._get_content(content_id)
        if not content:
            raise ValueError(f"Content not found: {content_id}")

        # Placeholder metrics
        performance = {
            "views": 0,
            "clicks": 0,
            "ctr": 0.0,
            "engagement_rate": 0.0,
            "conversions": 0,
            "last_updated": datetime.now().isoformat(),
        }

        # Update content performance
        await self._update_content_performance(content_id, performance)

        return performance

    def calculate_seo_score(self, content: MarketingContent) -> float:
        """
        Calculate SEO score (0-100)

        Factors:
        - Title length (50-60 chars optimal)
        - Meta description (150-160 chars optimal)
        - Keyword density (1-3% optimal)
        - Content length (>1000 chars for blog)
        - Header structure
        """
        score = 0.0

        # Title score (0-25)
        title_len = len(content.title)
        if 50 <= title_len <= 60:
            score += 25
        elif 40 <= title_len <= 70:
            score += 15
        else:
            score += 5

        # Meta description score (0-25)
        if content.seo_meta and "meta_description" in content.seo_meta:
            desc_len = len(content.seo_meta["meta_description"])
            if 150 <= desc_len <= 160:
                score += 25
            elif 140 <= desc_len <= 170:
                score += 15
            else:
                score += 5

        # Content length score (0-25)
        content_len = len(content.draft)
        if content.content_type == ContentType.BLOG:
            if content_len >= 1500:
                score += 25
            elif content_len >= 1000:
                score += 15
            else:
                score += 5
        else:
            if content_len >= 200:
                score += 20
            else:
                score += 10

        # Keyword score (0-25)
        if content.seo_meta and "keywords" in content.seo_meta:
            keywords = content.seo_meta["keywords"]
            if len(keywords) >= 5:
                score += 25
            elif len(keywords) >= 3:
                score += 15
            else:
                score += 5

        return min(score, 100.0)

    async def _save_content(self, content: MarketingContent) -> str:
        """Save content to database"""
        async with self.db.connect() as db:
            await db.execute(
                """
                INSERT INTO marketing_content
                (id, insight_id, content_type, title, target_keyword, seo_meta,
                draft, legal_review, status, total_cost, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    content.id,
                    content.insight_id,
                    content.content_type.value,
                    content.title,
                    content.target_keyword,
                    json.dumps(content.seo_meta, ensure_ascii=False),
                    content.draft,
                    json.dumps(content.legal_review, ensure_ascii=False),
                    content.status.value,
                    content.total_cost,
                    content.created_at.isoformat(),
                ),
            )
            await db.commit()

        return content.id

    async def _get_content(self, content_id: str) -> Optional[MarketingContent]:
        """Get content by ID"""
        async with self.db.connect() as db:
            cursor = await db.execute(
                "SELECT * FROM marketing_content WHERE id = ?", (content_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None

            return MarketingContent(
                id=row["id"],
                insight_id=row["insight_id"],
                content_type=ContentType(row["content_type"]),
                title=row["title"],
                target_keyword=row["target_keyword"],
                seo_meta=json.loads(row["seo_meta"]) if row["seo_meta"] else {},
                draft=row["draft"],
                legal_review=json.loads(row["legal_review"])
                if row["legal_review"]
                else {},
                status=ContentStatus(row["status"]),
                published_url=row["published_url"],
                performance=json.loads(row["performance"]) if row["performance"] else {},
                total_cost=row["total_cost"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )

    async def _update_content_schedule(self, content_id: str, scheduled_at: datetime):
        """Update content scheduled time"""
        async with self.db.connect() as db:
            # Add scheduled_at column if not exists (via seo_meta)
            cursor = await db.execute(
                "SELECT seo_meta FROM marketing_content WHERE id = ?", (content_id,)
            )
            row = await cursor.fetchone()
            if row:
                seo_meta = json.loads(row["seo_meta"]) if row["seo_meta"] else {}
                seo_meta["scheduled_at"] = scheduled_at.isoformat()

                await db.execute(
                    "UPDATE marketing_content SET seo_meta = ? WHERE id = ?",
                    (json.dumps(seo_meta, ensure_ascii=False), content_id),
                )
                await db.commit()

    async def _update_content_performance(
        self, content_id: str, performance: dict[str, Any]
    ):
        """Update content performance metrics"""
        async with self.db.connect() as db:
            await db.execute(
                "UPDATE marketing_content SET performance = ? WHERE id = ?",
                (json.dumps(performance, ensure_ascii=False), content_id),
            )
            await db.commit()

    async def batch_generate(
        self, insight_ids: list[str], content_type: str
    ) -> list[str]:
        """
        Batch generate content for multiple insights

        Args:
            insight_ids: List of insight IDs
            content_type: Content type to generate

        Returns:
            List of created content IDs
        """
        content_ids = []

        for insight_id in insight_ids:
            try:
                ids = await self.generate_content(insight_id, [content_type])
                content_ids.extend(ids)
            except Exception as e:
                print(f"Error generating content for insight {insight_id}: {e}")
                continue

        return content_ids

    async def get_pending_content(self, limit: int = 10) -> list[MarketingContent]:
        """Get pending content for review"""
        async with self.db.connect() as db:
            cursor = await db.execute(
                """
                SELECT * FROM marketing_content
                WHERE status = 'DRAFT'
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()

            contents = []
            for row in rows:
                content = MarketingContent(
                    id=row["id"],
                    insight_id=row["insight_id"],
                    content_type=ContentType(row["content_type"]),
                    title=row["title"],
                    target_keyword=row["target_keyword"],
                    seo_meta=json.loads(row["seo_meta"]) if row["seo_meta"] else {},
                    draft=row["draft"],
                    legal_review=json.loads(row["legal_review"])
                    if row["legal_review"]
                    else {},
                    status=ContentStatus(row["status"]),
                    published_url=row["published_url"],
                    performance=json.loads(row["performance"])
                    if row["performance"]
                    else {},
                    total_cost=row["total_cost"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                contents.append(content)

            return contents

    async def approve_content(self, content_id: str) -> bool:
        """Approve content for publication"""
        async with self.db.connect() as db:
            await db.execute(
                "UPDATE marketing_content SET status = 'APPROVED' WHERE id = ?",
                (content_id,),
            )
            await db.commit()

        return True

    async def publish_content(self, content_id: str, published_url: str) -> bool:
        """Mark content as published"""
        async with self.db.connect() as db:
            await db.execute(
                """
                UPDATE marketing_content
                SET status = 'PUBLISHED', published_url = ?
                WHERE id = ?
                """,
                (published_url, content_id),
            )
            await db.commit()

        return True

    async def get_analytics(
        self, start_date: datetime, end_date: datetime
    ) -> dict[str, Any]:
        """
        Get marketing analytics for date range

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            Analytics data
        """
        async with self.db.connect() as db:
            # Total content count
            cursor = await db.execute(
                """
                SELECT content_type, COUNT(*) as count
                FROM marketing_content
                WHERE created_at BETWEEN ? AND ?
                GROUP BY content_type
                """,
                (start_date.isoformat(), end_date.isoformat()),
            )
            type_counts = {row["content_type"]: row["count"] for row in await cursor.fetchall()}

            # Status breakdown
            cursor = await db.execute(
                """
                SELECT status, COUNT(*) as count
                FROM marketing_content
                WHERE created_at BETWEEN ? AND ?
                GROUP BY status
                """,
                (start_date.isoformat(), end_date.isoformat()),
            )
            status_counts = {row["status"]: row["count"] for row in await cursor.fetchall()}

            # Total cost
            cursor = await db.execute(
                """
                SELECT SUM(total_cost) as total
                FROM marketing_content
                WHERE created_at BETWEEN ? AND ?
                """,
                (start_date.isoformat(), end_date.isoformat()),
            )
            row = await cursor.fetchone()
            total_cost = row["total"] if row["total"] else 0.0

            return {
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                },
                "content_by_type": type_counts,
                "content_by_status": status_counts,
                "total_cost": total_cost,
                "total_content": sum(type_counts.values()),
            }
