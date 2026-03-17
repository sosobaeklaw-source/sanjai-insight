from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import httpx

from .config import RuntimeConfig
from .models import DraftDocument, PublishArtifact

logger = logging.getLogger(__name__)

_PERSONA_CATEGORY_MAP: dict[str, str] = {
    "nomu": "노무 인사이트",
    "lawyer": "법률 인사이트",
}


def _ensure_wp_url(url: str) -> str:
    """Normalize a WordPress URL so it ends with ``/wp/v2/posts``."""
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    url = url.rstrip("/")
    if not url.endswith("/wp/v2/posts"):
        if "/wp-json" in url or "/wp/v2" in url:
            # Already has WP API path, ensure it ends with /posts
            if not url.endswith("/posts"):
                url = url.rstrip("/") + "/posts" if url.endswith("/v2") else url
        else:
            url = f"{url}/wp-json/wp/v2/posts"
    return url


def _get_or_create_category(
    client: httpx.Client,
    base_url: str,
    auth: tuple[str, str],
    name: str,
) -> int | None:
    """Return the WP category ID for *name*, creating it if necessary.

    *base_url* should be the site root **without** ``/wp-json/...`` — the
    helper builds the categories endpoint itself.  Returns ``None`` when the
    remote call fails so the caller can proceed without a category.
    """
    # Derive categories endpoint from the posts URL or base
    cats_url = base_url.rstrip("/")
    if cats_url.endswith("/wp/v2/posts"):
        cats_url = cats_url.rsplit("/posts", 1)[0] + "/categories"
    elif cats_url.endswith("/wp/v2"):
        cats_url += "/categories"
    else:
        cats_url += "/wp-json/wp/v2/categories"

    try:
        resp = client.post(
            cats_url,
            auth=auth,
            json={"name": name},
        )
        if resp.status_code in (200, 201):
            return resp.json().get("id")
        if resp.status_code == 409:
            # Category already exists — extract id from error response
            err_data = resp.json()
            term_id = (err_data.get("data") or {}).get("term_id")
            if term_id is not None:
                return int(term_id)
        # Fallback: search existing categories by name
        search_resp = client.get(
            cats_url,
            auth=auth,
            params={"search": name, "per_page": 1},
        )
        if search_resp.status_code == 200:
            results = search_resp.json()
            if results:
                return results[0].get("id")
    except Exception:
        logger.warning("Failed to get/create WP category %r", name, exc_info=True)

    return None


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
    *,
    output_root: Path | None = None,
    run_id: str = "",
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

    wp_url = _ensure_wp_url(config.word_press_url)
    auth = (config.word_press_user, config.word_press_app_password)

    try:
        with httpx.Client(timeout=30) as client:
            # Pre-resolve category IDs for known personas
            category_cache: dict[str, int | None] = {}

            for draft in drafts:
                # Resolve category for this persona
                cat_name = _PERSONA_CATEGORY_MAP.get(draft.persona)
                category_id: int | None = None
                if cat_name:
                    if cat_name not in category_cache:
                        category_cache[cat_name] = _get_or_create_category(
                            client, wp_url, auth, cat_name
                        )
                    category_id = category_cache[cat_name]

                post_payload: dict = {
                    "title": draft.title,
                    "content": draft.body,
                    "status": "draft",
                }
                if category_id is not None:
                    post_payload["categories"] = [category_id]

                response = client.post(
                    wp_url,
                    auth=auth,
                    json=post_payload,
                )
                response.raise_for_status()
                payload = response.json()
                artifacts.append(
                    PublishArtifact(
                        target="wordpress",
                        mode="draft",
                        location=str(
                            payload.get("link") or payload.get("id") or ""
                        ),
                        status="published",
                        metadata={
                            "id": payload.get("id"),
                            "category_id": category_id,
                        },
                    )
                )
    except Exception:
        logger.error(
            "WordPress publishing failed, falling back to local",
            exc_info=True,
        )
        # Fallback: write drafts locally so nothing is lost
        fallback_root = output_root or Path("published")
        fallback_artifacts = publish_local(
            drafts, fallback_root, run_id or "wp-fallback"
        )
        # Tag every fallback artifact with a warning
        for art in fallback_artifacts:
            art.metadata["wp_fallback"] = True
            art.metadata["wp_error"] = "wordpress_publish_failed"
        artifacts.extend(fallback_artifacts)
        artifacts.append(
            PublishArtifact(
                target="wordpress",
                mode="draft",
                location="",
                status="error_fallback_local",
                metadata={"warning": "WordPress publish failed; saved locally"},
            )
        )

    return artifacts
