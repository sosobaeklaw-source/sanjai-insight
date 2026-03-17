"""CLI entry point: python -m src.insight_engine"""
from __future__ import annotations

from .config import load_runtime_config
from .pipeline import PipelineOptions, PipelineRunner


def main() -> None:
    config = load_runtime_config()
    options = PipelineOptions(dry_run=False, notify_telegram=True)
    result = PipelineRunner(config, options).run()
    print(f"[insight-engine] {result.run_id} completed — {len(result.drafts)} drafts, {len(result.warnings)} warnings")


if __name__ == "__main__":
    main()
