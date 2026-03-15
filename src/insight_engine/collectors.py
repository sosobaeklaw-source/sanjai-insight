from __future__ import annotations

from datetime import datetime

from .config import RuntimeConfig
from .models import SourceRecord
from .vault_reader import VaultReader


PUBLIC_SOURCE_LABELS = (
    ("data_go_kr", "공공데이터포털"),
    ("dart", "DART 공시"),
    ("kosis", "통계청 KOSIS"),
    ("ecos", "한국은행 ECOS"),
    ("law_api_key", "법제처"),
)

SEARCH_SOURCE_LABELS = (
    ("brave", "Brave Search"),
    ("naver_client_id", "Naver Search"),
    ("google_cse_api_key", "Google CSE"),
)


class CanonicalCollector:
    """Collect only verifiable, read-only inputs for the batch pipeline."""

    def __init__(self, config: RuntimeConfig):
        self.config = config
        self.vault_reader = VaultReader(config.vault_path)

    def collect(self, days: int = 7) -> list[SourceRecord]:
        records: list[SourceRecord] = []
        records.extend(self._collect_provider_inventory(PUBLIC_SOURCE_LABELS))
        records.extend(self._collect_provider_inventory(SEARCH_SOURCE_LABELS))
        records.extend(self._collect_optional_targets())
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
                source="vault_path",
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
