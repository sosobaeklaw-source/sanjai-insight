#!/usr/bin/env python3
"""CLI health check for the insight engine."""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.insight_engine.config import load_runtime_config
from src.insight_engine.monitor import daily_report


def main() -> None:
    try:
        config = load_runtime_config()
    except RuntimeError as exc:
        print(f"Config load failed: {exc}", file=sys.stderr)
        sys.exit(1)

    report = daily_report(config)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # Exit code based on health
    summary = report.get("summary", {})
    if summary.get("vault_status") != "ok":
        sys.exit(2)


if __name__ == "__main__":
    main()
