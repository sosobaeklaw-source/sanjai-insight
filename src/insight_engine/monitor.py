"""Insight engine health monitoring."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import httpx

from .config import SECRET_KEYS, RuntimeConfig


def check_collectors() -> dict[str, str]:
    """Check which collector API keys are configured."""
    collector_keys = {
        "kosha": "DATA_GO_KR_API_KEY",
        "moel": "DATA_GO_KR_API_KEY",
        "dart": "DART_API",
        "kosis": "KOSIS_API",
        "ecos": "ECOS_API",
        "law": "LAW_API_OC",
        "data_go_kr": "DATA_GO_KR_API_KEY",
        "brave": "BRAVE_API_KEY",
        "naver": "NAVER_CLIENT_ID",
        "google_cse": "GOOGLE_CSE_API_KEY",
    }
    return {name: "ok" if os.getenv(env_key) else "missing" for name, env_key in collector_keys.items()}


def check_vault(config: RuntimeConfig) -> dict[str, object]:
    """Check vault accessibility."""
    if not config.vault_path:
        return {"status": "not_configured", "path": None}
    path = config.vault_path
    if not path.exists():
        return {"status": "path_missing", "path": str(path)}
    md_count = len(list(path.rglob("*.md")))
    return {"status": "ok", "path": str(path), "markdown_files": md_count}


def check_wp(config: RuntimeConfig) -> dict[str, str]:
    """Check WordPress connectivity."""
    if not (config.word_press_url and config.word_press_user and config.word_press_app_password):
        return {"status": "not_configured"}
    url = config.word_press_url
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    try:
        resp = httpx.get(url.split("/wp-json")[0] + "/wp-json", timeout=10)
        return {"status": "ok" if resp.status_code == 200 else f"http_{resp.status_code}"}
    except Exception as exc:
        return {"status": f"error: {exc}"}


def check_telegram(config: RuntimeConfig) -> dict[str, str]:
    """Check Telegram bot connectivity."""
    if not config.telegram_bot_token:
        return {"status": "not_configured"}
    try:
        resp = httpx.get(
            f"https://api.telegram.org/bot{config.telegram_bot_token}/getMe",
            timeout=10,
        )
        if resp.status_code == 200:
            bot_info = resp.json().get("result", {})
            return {"status": "ok", "bot_username": bot_info.get("username", "")}
        return {"status": f"http_{resp.status_code}"}
    except Exception as exc:
        return {"status": f"error: {exc}"}


def check_api_keys() -> dict[str, str]:
    """Check all known API key presence."""
    return {label: "present" if os.getenv(env_key) else "missing" for label, env_key in SECRET_KEYS.items()}


def daily_report(config: RuntimeConfig) -> dict[str, object]:
    """Generate a daily health report."""
    report = {
        "timestamp": datetime.now().isoformat(),
        "collectors": check_collectors(),
        "vault": check_vault(config),
        "wordpress": check_wp(config),
        "telegram": check_telegram(config),
        "api_keys": check_api_keys(),
    }

    # Check latest pipeline report
    pipeline_report = config.reports_root / "health" / "pipeline_latest.json"
    if pipeline_report.exists():
        try:
            data = json.loads(pipeline_report.read_text(encoding="utf-8"))
            report["last_pipeline"] = {
                "run_id": data.get("run_id"),
                "mode": data.get("mode"),
                "source_count": len(data.get("source_records", [])),
                "draft_count": len(data.get("drafts", [])),
                "warnings": data.get("warnings", []),
            }
        except Exception:
            report["last_pipeline"] = {"status": "parse_error"}
    else:
        report["last_pipeline"] = {"status": "no_report_found"}

    # Summary
    collector_status = report["collectors"]
    ok_count = sum(1 for v in collector_status.values() if v == "ok")
    total = len(collector_status)
    report["summary"] = {
        "collectors_ready": f"{ok_count}/{total}",
        "vault_status": report["vault"]["status"],
        "wordpress_status": report["wordpress"]["status"],
        "telegram_status": report["telegram"]["status"],
    }
    return report
