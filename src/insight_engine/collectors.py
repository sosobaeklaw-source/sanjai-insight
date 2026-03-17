from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

from .config import RuntimeConfig
from .models import SourceRecord
from .vault_reader import VaultReader


PUBLIC_SOURCE_LABELS = (
    ("data_go_kr", "공공데이터포털"),
    ("dart", "DART 공시"),
    ("kosis", "통계청 KOSIS"),
    ("ecos", "한국은행 ECOS"),
    ("law_api_key", "법제처"),
    ("kosha", "안전보건공단 KOSHA"),
    ("moel", "고용노동부"),
)

SEARCH_SOURCE_LABELS = (
    ("brave", "Brave Search"),
    ("naver_client_id", "Naver Search"),
    ("google_cse_api_key", "Google CSE"),
)


# ---------------------------------------------------------------------------
# Shared HTTP helper
# ---------------------------------------------------------------------------

def _fetch(
    url: str,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    retries: int = 3,
) -> httpx.Response | None:
    """GET *url* with exponential back-off.  Returns None on any failure."""
    for attempt in range(retries):
        try:
            resp = httpx.get(url, params=params, headers=headers, timeout=10.0)
            resp.raise_for_status()
            return resp
        except Exception as exc:  # noqa: BLE001
            wait = 2**attempt  # 1 s, 2 s, 4 s
            print(f"[collectors] _fetch attempt {attempt + 1}/{retries} failed "
                  f"for {url}: {exc}", file=sys.stderr)
            if attempt < retries - 1:
                time.sleep(wait)
    return None


# ---------------------------------------------------------------------------
# Raw-data persistence
# ---------------------------------------------------------------------------

def _save_raw(data: object, source: str, data_root: Path) -> None:
    """Persist fetched payload to data/raw/{source}/YYYY-MM-DD/."""
    today = datetime.now().strftime("%Y-%m-%d")
    dest = data_root / "raw" / source / today
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {
        "source": source,
        "fetched_at": datetime.now().isoformat(),
        "date": today,
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Public-API collectors  (each returns list[SourceRecord])
# ---------------------------------------------------------------------------

def collect_kosha(data_root: Path | None = None) -> list[SourceRecord]:
    """KOSHA (안전보건공단) 산업재해 통계."""
    api_key = os.getenv("DATA_GO_KR_API_KEY")
    if not api_key:
        return []
    resp = _fetch(
        "https://apis.data.go.kr/B552468/kosha_indacc_stat/getAccidentStatList",
        params={"serviceKey": api_key, "numOfRows": "20", "type": "json"},
    )
    if not resp:
        return []
    try:
        payload = resp.json()
        if data_root:
            _save_raw(payload, "kosha", data_root)
        items = (
            payload.get("response", {}).get("body", {}).get("items", {}).get("item", [])
        )
        if not isinstance(items, list):
            items = [items] if items else []
        now = datetime.now().isoformat()
        records: list[SourceRecord] = []
        for item in items[:20]:
            title = item.get("kindNm") or item.get("occurYear") or "산업재해 통계"
            excerpt = json.dumps(item, ensure_ascii=False)[:300]
            records.append(
                SourceRecord(
                    source="kosha",
                    status="collected",
                    title=str(title),
                    excerpt=excerpt,
                    published_at=now,
                    evidence=[resp.url.host if resp.url else "apis.data.go.kr"],
                    metadata=item,
                )
            )
        return records
    except Exception as exc:  # noqa: BLE001
        print(f"[collectors] collect_kosha parse error: {exc}", file=sys.stderr)
        return []


def collect_moel(data_root: Path | None = None) -> list[SourceRecord]:
    """고용노동부 고용동향."""
    api_key = os.getenv("DATA_GO_KR_API_KEY")
    if not api_key:
        return []
    resp = _fetch(
        "https://apis.data.go.kr/B490007/openApiService/getEmpTrend",
        params={"serviceKey": api_key, "numOfRows": "20", "type": "json"},
    )
    if not resp:
        return []
    try:
        payload = resp.json()
        if data_root:
            _save_raw(payload, "moel", data_root)
        items = (
            payload.get("response", {}).get("body", {}).get("items", {}).get("item", [])
        )
        if not isinstance(items, list):
            items = [items] if items else []
        now = datetime.now().isoformat()
        records: list[SourceRecord] = []
        for item in items[:20]:
            title = item.get("empNm") or item.get("baseDt") or "고용동향"
            excerpt = json.dumps(item, ensure_ascii=False)[:300]
            records.append(
                SourceRecord(
                    source="moel",
                    status="collected",
                    title=str(title),
                    excerpt=excerpt,
                    published_at=now,
                    evidence=["apis.data.go.kr"],
                    metadata=item,
                )
            )
        return records
    except Exception as exc:  # noqa: BLE001
        print(f"[collectors] collect_moel parse error: {exc}", file=sys.stderr)
        return []


def collect_dart(data_root: Path | None = None) -> list[SourceRecord]:
    """DART 주요사항보고."""
    api_key = os.getenv("DART_API")
    if not api_key:
        return []
    resp = _fetch(
        "https://opendart.fss.or.kr/api/list.json",
        params={"crtfc_key": api_key, "page_count": "10", "type_nm": "주요사항보고서"},
    )
    if not resp:
        return []
    try:
        payload = resp.json()
        if data_root:
            _save_raw(payload, "dart", data_root)
        items = payload.get("list", [])
        if not isinstance(items, list):
            items = []
        now = datetime.now().isoformat()
        records: list[SourceRecord] = []
        for item in items[:10]:
            title = item.get("report_nm", "DART 공시")
            corp = item.get("corp_name", "")
            excerpt = f"{corp}: {title}" if corp else str(title)
            url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={item.get('rcept_no', '')}" if item.get("rcept_no") else None
            records.append(
                SourceRecord(
                    source="dart",
                    status="collected",
                    title=str(title),
                    excerpt=excerpt[:300],
                    url=url,
                    published_at=item.get("rcept_dt", now),
                    evidence=["opendart.fss.or.kr"],
                    metadata=item,
                )
            )
        return records
    except Exception as exc:  # noqa: BLE001
        print(f"[collectors] collect_dart parse error: {exc}", file=sys.stderr)
        return []


def collect_kosis(data_root: Path | None = None) -> list[SourceRecord]:
    """통계청 KOSIS."""
    api_key = os.getenv("KOSIS_API")
    if not api_key:
        return []
    resp = _fetch(
        "https://kosis.kr/openapi/Param/statisticsParameterData.do",
        params={"method": "getList", "apiKey": api_key, "format": "json", "jsonVD": "Y"},
    )
    if not resp:
        return []
    try:
        payload = resp.json()
        if data_root:
            _save_raw(payload, "kosis", data_root)
        items = payload if isinstance(payload, list) else payload.get("data", [])
        if not isinstance(items, list):
            items = []
        now = datetime.now().isoformat()
        records: list[SourceRecord] = []
        for item in items[:10]:
            title = item.get("TBL_NM") or item.get("ORG_NM") or "KOSIS 통계"
            excerpt = json.dumps(item, ensure_ascii=False)[:300]
            records.append(
                SourceRecord(
                    source="kosis",
                    status="collected",
                    title=str(title),
                    excerpt=excerpt,
                    published_at=now,
                    evidence=["kosis.kr"],
                    metadata=item,
                )
            )
        return records
    except Exception as exc:  # noqa: BLE001
        print(f"[collectors] collect_kosis parse error: {exc}", file=sys.stderr)
        return []


def collect_ecos(data_root: Path | None = None) -> list[SourceRecord]:
    """한국은행 ECOS 경제통계."""
    api_key = os.getenv("ECOS_API")
    if not api_key:
        return []
    resp = _fetch(
        f"https://ecos.bok.or.kr/api/StatisticSearch/{api_key}/json/kr/1/10/010Y002/MM",
    )
    if not resp:
        return []
    try:
        payload = resp.json()
        if data_root:
            _save_raw(payload, "ecos", data_root)
        rows = (
            payload.get("StatisticSearch", {}).get("row", [])
        )
        if not isinstance(rows, list):
            rows = []
        now = datetime.now().isoformat()
        records: list[SourceRecord] = []
        for row in rows[:10]:
            title = row.get("STAT_NAME") or row.get("ITEM_NAME1") or "ECOS 통계"
            value = row.get("DATA_VALUE", "")
            period = row.get("TIME", "")
            excerpt = f"{title} ({period}): {value}"
            records.append(
                SourceRecord(
                    source="ecos",
                    status="collected",
                    title=str(title),
                    excerpt=excerpt[:300],
                    published_at=now,
                    evidence=["ecos.bok.or.kr"],
                    metadata=row,
                )
            )
        return records
    except Exception as exc:  # noqa: BLE001
        print(f"[collectors] collect_ecos parse error: {exc}", file=sys.stderr)
        return []


def collect_law(data_root: Path | None = None) -> list[SourceRecord]:
    """법제처 최근 법령."""
    api_key = os.getenv("LAW_API_OC")
    if not api_key:
        return []
    resp = _fetch(
        "https://www.law.go.kr/DRF/lawSearch.do",
        params={"OC": api_key, "target": "law", "type": "JSON", "display": "10", "sort": "date"},
    )
    if not resp:
        return []
    try:
        payload = resp.json()
        if data_root:
            _save_raw(payload, "law", data_root)
        items = payload.get("LawSearch", {}).get("law", [])
        if not isinstance(items, list):
            items = [items] if items else []
        now = datetime.now().isoformat()
        records: list[SourceRecord] = []
        for item in items[:10]:
            title = item.get("법령명한글") or item.get("lawNameKor") or "법령"
            law_id = item.get("법령일련번호") or item.get("lawId") or ""
            url = f"https://www.law.go.kr/법령/{title}" if title else None
            excerpt = f"{title} (ID: {law_id})" if law_id else str(title)
            records.append(
                SourceRecord(
                    source="law",
                    status="collected",
                    title=str(title),
                    excerpt=excerpt[:300],
                    url=url,
                    published_at=item.get("시행일자") or now,
                    evidence=["www.law.go.kr"],
                    metadata=item,
                )
            )
        return records
    except Exception as exc:  # noqa: BLE001
        print(f"[collectors] collect_law parse error: {exc}", file=sys.stderr)
        return []


def collect_data_go_kr(data_root: Path | None = None) -> list[SourceRecord]:
    """공공데이터포털 산재/노동 관련."""
    api_key = os.getenv("DATA_GO_KR_API_KEY")
    if not api_key:
        return []
    resp = _fetch(
        "https://apis.data.go.kr/B490007/openApiService/getJobTrend",
        params={"serviceKey": api_key, "numOfRows": "10", "type": "json"},
    )
    if not resp:
        return []
    try:
        payload = resp.json()
        if data_root:
            _save_raw(payload, "data_go_kr", data_root)
        items = (
            payload.get("response", {}).get("body", {}).get("items", {}).get("item", [])
        )
        if not isinstance(items, list):
            items = [items] if items else []
        now = datetime.now().isoformat()
        records: list[SourceRecord] = []
        for item in items[:10]:
            title = item.get("jobNm") or item.get("baseDt") or "노동 동향"
            excerpt = json.dumps(item, ensure_ascii=False)[:300]
            records.append(
                SourceRecord(
                    source="data_go_kr",
                    status="collected",
                    title=str(title),
                    excerpt=excerpt,
                    published_at=now,
                    evidence=["apis.data.go.kr"],
                    metadata=item,
                )
            )
        return records
    except Exception as exc:  # noqa: BLE001
        print(f"[collectors] collect_data_go_kr parse error: {exc}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Search collectors
# ---------------------------------------------------------------------------

def collect_brave(data_root: Path | None = None) -> list[SourceRecord]:
    """Brave Search 산업재해/노동법 최신 뉴스."""
    api_key = os.getenv("BRAVE_API_KEY")
    if not api_key:
        return []
    resp = _fetch(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": "산업재해 노동법 최신", "count": "10"},
        headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
    )
    if not resp:
        return []
    try:
        payload = resp.json()
        if data_root:
            _save_raw(payload, "brave", data_root)
        results = payload.get("web", {}).get("results", [])
        if not isinstance(results, list):
            results = []
        now = datetime.now().isoformat()
        records: list[SourceRecord] = []
        for item in results[:10]:
            title = item.get("title", "Brave Search result")
            excerpt = item.get("description", "")[:300]
            url = item.get("url")
            records.append(
                SourceRecord(
                    source="brave",
                    status="collected",
                    title=str(title),
                    excerpt=excerpt,
                    url=url,
                    published_at=item.get("age") or now,
                    evidence=[url] if url else ["api.search.brave.com"],
                    metadata=item,
                )
            )
        return records
    except Exception as exc:  # noqa: BLE001
        print(f"[collectors] collect_brave parse error: {exc}", file=sys.stderr)
        return []


def collect_naver(data_root: Path | None = None) -> list[SourceRecord]:
    """Naver 뉴스 검색 산업재해/중대재해."""
    client_id = os.getenv("NAVER_CLIENT_ID")
    client_secret = os.getenv("NAVER_CLIENT_SECRET")
    if not (client_id and client_secret):
        return []
    resp = _fetch(
        "https://openapi.naver.com/v1/search/news.json",
        params={"query": "산업재해 중대재해", "display": "10", "sort": "date"},
        headers={"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret},
    )
    if not resp:
        return []
    try:
        payload = resp.json()
        if data_root:
            _save_raw(payload, "naver", data_root)
        items = payload.get("items", [])
        if not isinstance(items, list):
            items = []
        now = datetime.now().isoformat()
        records: list[SourceRecord] = []
        for item in items[:10]:
            title = item.get("title", "Naver 뉴스").replace("<b>", "").replace("</b>", "")
            excerpt = item.get("description", "").replace("<b>", "").replace("</b>", "")[:300]
            url = item.get("originallink") or item.get("link")
            records.append(
                SourceRecord(
                    source="naver",
                    status="collected",
                    title=str(title),
                    excerpt=excerpt,
                    url=url,
                    published_at=item.get("pubDate") or now,
                    evidence=[url] if url else ["openapi.naver.com"],
                    metadata=item,
                )
            )
        return records
    except Exception as exc:  # noqa: BLE001
        print(f"[collectors] collect_naver parse error: {exc}", file=sys.stderr)
        return []


def collect_google_cse(data_root: Path | None = None) -> list[SourceRecord]:
    """Google Custom Search 산재보험/노동법/판례."""
    api_key = os.getenv("GOOGLE_CSE_API_KEY") or os.getenv("GOOGLE_API_KEY")
    cse_id = os.getenv("GOOGLE_CSE_ID")
    if not (api_key and cse_id):
        return []
    resp = _fetch(
        "https://www.googleapis.com/customsearch/v1",
        params={"key": api_key, "cx": cse_id, "q": "산재보험 노동법 판례 최신", "num": "10"},
    )
    if not resp:
        return []
    try:
        payload = resp.json()
        if data_root:
            _save_raw(payload, "google_cse", data_root)
        items = payload.get("items", [])
        if not isinstance(items, list):
            items = []
        now = datetime.now().isoformat()
        records: list[SourceRecord] = []
        for item in items[:10]:
            title = item.get("title", "Google CSE result")
            excerpt = item.get("snippet", "")[:300]
            url = item.get("link")
            records.append(
                SourceRecord(
                    source="google_cse",
                    status="collected",
                    title=str(title),
                    excerpt=excerpt,
                    url=url,
                    published_at=now,
                    evidence=[url] if url else ["googleapis.com"],
                    metadata=item,
                )
            )
        return records
    except Exception as exc:  # noqa: BLE001
        print(f"[collectors] collect_google_cse parse error: {exc}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Canonical orchestrator
# ---------------------------------------------------------------------------

class CanonicalCollector:
    """Collect only verifiable, read-only inputs for the batch pipeline."""

    def __init__(self, config: RuntimeConfig):
        self.config = config
        self.vault_reader = VaultReader(config.vault_path)

    def collect(self, days: int = 7) -> list[SourceRecord]:
        records: list[SourceRecord] = []
        data_root = self.config.data_root

        # Real public-API collectors
        for collector_fn in (
            collect_kosha,
            collect_moel,
            collect_dart,
            collect_kosis,
            collect_ecos,
            collect_law,
            collect_data_go_kr,
        ):
            records.extend(collector_fn(data_root))

        # Search collectors
        for collector_fn in (collect_brave, collect_naver, collect_google_cse):
            records.extend(collector_fn(data_root))

        # Provider inventory (status tracking)
        records.extend(self._collect_provider_inventory(PUBLIC_SOURCE_LABELS))
        records.extend(self._collect_provider_inventory(SEARCH_SOURCE_LABELS))
        records.extend(self._collect_optional_targets())

        # Vault
        records.extend(self.vault_reader.snapshot(days=days, limit=12))
        return records

    def _collect_provider_inventory(
        self, labels: tuple[tuple[str, str], ...]
    ) -> list[SourceRecord]:
        timestamp = datetime.now().isoformat()
        items: list[SourceRecord] = []
        for key, label in labels:
            present = self.config.secret_presence.get(key, False)
            items.append(
                SourceRecord(
                    source=key,
                    status="configured" if present else "missing",
                    title=label,
                    excerpt=(
                        f"{label} credential is present in {self.config.env_source}."
                        if present
                        else f"{label} credential is missing from {self.config.env_source}."
                    ),
                    published_at=timestamp,
                    evidence=[key],
                )
            )
        return items

    def _collect_optional_targets(self) -> list[SourceRecord]:
        records: list[SourceRecord] = []
        vault_status = "collected" if self.vault_reader.enabled else "missing"
        records.append(
            SourceRecord(
                source="vault",
                status=vault_status,
                title="Obsidian Vault",
                excerpt=(
                    f"Vault path is accessible: {self.config.vault_path}"
                    if self.vault_reader.enabled
                    else "Vault path is not accessible from the current workspace."
                ),
                published_at=datetime.now().isoformat(),
                evidence=[str(self.config.vault_path)] if self.config.vault_path else [],
            )
        )

        wordpress_ready = bool(
            self.config.word_press_url
            and self.config.word_press_user
            and self.config.word_press_app_password
        )
        records.append(
            SourceRecord(
                source="wordpress",
                status="configured" if wordpress_ready else "missing",
                title="WordPress Draft Target",
                excerpt=(
                    "WordPress draft publishing can be enabled."
                    if wordpress_ready
                    else "WordPress draft publishing is not fully configured."
                ),
                published_at=datetime.now().isoformat(),
                evidence=["WORDPRESS_URL", "WORDPRESS_USER", "WORDPRESS_APP_PASSWORD"],
            )
        )

        telegram_ready = bool(
            self.config.telegram_bot_token and self.config.notify_chat_id
        )
        records.append(
            SourceRecord(
                source="telegram",
                status="configured" if telegram_ready else "missing",
                title="Telegram Notification Target",
                excerpt=(
                    "Telegram notification target can be enabled."
                    if telegram_ready
                    else "Telegram notification target is not fully configured."
                ),
                published_at=datetime.now().isoformat(),
                evidence=["TELEGRAM_BOT_TOKEN", "BOSS_CHAT_ID|TELEGRAM_CHAT_ID"],
            )
        )
        return records
