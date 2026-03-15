from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import httpx

from .config import RuntimeConfig
from .models import DraftDocument, PublishArtifact


def publish_local(
    drafts: list[DraftDocument],
    output_root: Path,
    run_id: str,
) -> list[PublishArtifact]:
    date_dir = output_root / datetime.now().strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "run_id": run_id,
        "generated_at": datetime.now().isoformat(),
        "drafts": [],
    }
    artifacts: list[PublishArtifact] = []

    for draft in drafts:
        path = date_dir / f"{draft.slug}.md"
        path.write_text(f"# {draft.title}\n\n{draft.body}\n", encoding="utf-8")
        manifest["drafts"].append(
            {
                "persona": draft.persona,
                "title": draft.title,
                "path": str(path),
                "quality_checks": list(draft.quality_checks),
            }
        )
        artifacts.append(
            PublishArtifact(
                target="local_markdown",
                mode="write",
                location=str(path),
                status="published",
            )
        )

    manifest_path = date_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    artifacts.append(
        PublishArtifact(
            target="local_manifest",
            mode="write",
            location=str(manifest_path),
            status="published",
            metadata={"draft_count": len(drafts)},
        )
    )
    return artifacts


def publish_wordpress(
    config: RuntimeConfig,
    drafts: list[DraftDocument],
    dry_run: bool,
) -> list[PublishArtifact]:
    if not (
        config.word_press_url
        and config.word_press_user
        and config.word_press_app_password
    ):
        return [
            PublishArtifact(
                target="wordpress",
                mode="draft",
                location="",
                status="missing_config",
            )
        ]

    artifacts: list[PublishArtifact] = []
    if dry_run:
        for draft in drafts:
            artifacts.append(
                PublishArtifact(
                    target="wordpress",
                    mode="draft",
                    location=config.word_press_url,
                    status="skipped_dry_run",
                    metadata={"title": draft.title},
                )
            )
        return artifacts

    with httpx.Client(timeout=30) as client:
        for draft in drafts:
            response = client.post(
                config.word_press_url,
                auth=(config.word_press_user, config.word_press_app_password),
                json={
                    "title": draft.title,
                    "content": draft.body,
                    "status": "draft",
                },
            )
            response.raise_for_status()
            payload = response.json()
            artifacts.append(
                PublishArtifact(
                    target="wordpress",
                    mode="draft",
                    location=str(payload.get("link") or payload.get("id") or ""),
                    status="published",
                    metadata={"id": payload.get("id")},
                )
            )
    return artifacts
