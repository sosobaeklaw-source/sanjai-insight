from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run repeated dry-run backfill windows")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--step", type=int, default=7)
    args = parser.parse_args()

    python = ROOT / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        python = Path(sys.executable)

    for _ in range(max(1, args.days // max(1, args.step))):
        result = subprocess.run(
            [str(python), str(ROOT / "scripts" / "run_pipeline.py"), "--days", str(args.step)],
            cwd=ROOT,
            check=False,
        )
        if result.returncode != 0:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
