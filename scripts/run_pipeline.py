from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.insight_engine import PipelineOptions, PipelineRunner, load_runtime_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Canonical insight-engine batch entrypoint")
    parser.add_argument("--days", type=int, default=7, help="lookback window for recent material")
    parser.add_argument("--execute", action="store_true", help="disable dry-run safeguards")
    parser.add_argument("--publish-wordpress", action="store_true", help="publish WordPress drafts")
    parser.add_argument("--notify-telegram", action="store_true", help="send Telegram notification")
    parser.add_argument("--check-env", action="store_true", help="print redacted environment summary and exit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_runtime_config(ROOT)

    if args.check_env:
        print(
            json.dumps(
                config.redacted_summary(),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    options = PipelineOptions(
        days=args.days,
        dry_run=not args.execute,
        publish_wordpress=args.publish_wordpress,
        notify_telegram=args.notify_telegram,
    )
    result = PipelineRunner(config, options).run()
    summary = {
        "run_id": result.run_id,
        "mode": result.mode,
        "env_source": result.env_source,
        "drafts": len(result.drafts),
        "artifacts": len(result.artifacts),
        "warnings": result.warnings,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
