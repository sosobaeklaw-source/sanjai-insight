from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .collectors import CanonicalCollector
from .config import RuntimeConfig
from .content import build_draft
from .insight import extract_insights
from .models import PipelineResult, PublishArtifact
from .notify import notify_telegram
from .publishers import publish_local, publish_wordpress


@dataclass(slots=True)
class PipelineOptions:
    days: int = 7
    dry_run: bool = True
    publish_wordpress: bool = False
    notify_telegram: bool = False


class PipelineRunner:
    def __init__(self, config: RuntimeConfig, options: PipelineOptions):
        self.config = config
        self.options = options

    def run(self) -> PipelineResult:
        run_id = f"insight-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
        collector = CanonicalCollector(self.config)
        records = collector.collect(days=self.options.days)
        insights = extract_insights(records)

        drafts = [
            build_draft("nomu", insights[0]),
            build_draft("lawyer", insights[1] if len(insights) > 1 else insights[0]),
        ]

        artifacts = publish_local(drafts, self.config.published_root, run_id)
        warnings = []

        if not any(record.source == "vault_path" and record.status == "collected" for record in records):
            warnings.append("vault_unavailable")
        if not any(record.source == "wordpress" and record.status == "configured" for record in records):
            warnings.append("wordpress_draft_fallback_only")
        if not any(record.source == "telegram" and record.status == "configured" for record in records):
            warnings.append("telegram_preview_only")

        if self.options.publish_wordpress:
            artifacts.extend(
                publish_wordpress(self.config, drafts, dry_run=self.options.dry_run)
            )

        if self.options.notify_telegram:
            artifacts.append(
                notify_telegram(self.config, drafts, run_id, dry_run=self.options.dry_run)
            )

        result = PipelineResult(
            run_id=run_id,
            mode="dry-run" if self.options.dry_run else "live",
            env_source=self.config.env_source,
            source_records=records,
            insights=insights,
            drafts=drafts,
            artifacts=artifacts,
            warnings=warnings,
        )
        self._write_reports(result)
        return result

    def _write_reports(self, result: PipelineResult) -> None:
        health_root = self.config.reports_root / "health"
        publish_root = self.config.reports_root / "publish_log"
        health_root.mkdir(parents=True, exist_ok=True)
        publish_root.mkdir(parents=True, exist_ok=True)

        payload = result.to_dict()
        payload["config"] = self.config.redacted_summary()
        payload["options"] = asdict(self.options)

        json_path = health_root / "pipeline_latest.json"
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        md_lines = [
            f"# Insight Engine Batch Report ({result.run_id})",
            "",
            f"- mode: `{result.mode}`",
            f"- env_source: `{result.env_source}`",
            f"- source_records: `{len(result.source_records)}`",
            f"- insights: `{len(result.insights)}`",
            f"- drafts: `{len(result.drafts)}`",
            "",
            "## Drafts",
        ]
        for draft in result.drafts:
            md_lines.append(f"- {draft.title} ({draft.word_count} words)")
        if result.warnings:
            md_lines.extend(["", "## Warnings"])
            for warning in result.warnings:
                md_lines.append(f"- {warning}")
        md_path = health_root / "pipeline_latest.md"
        md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

        publish_summary = publish_root / "latest_manifest.json"
        publish_summary.write_text(
            json.dumps(
                [artifact.to_dict() for artifact in result.artifacts],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
