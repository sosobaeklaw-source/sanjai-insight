#!/usr/bin/env bash
# Setup cron job for daily insight pipeline at 23:00 KST
set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PYTHON="${PROJECT_ROOT}/.venv/bin/python"
PIPELINE_CMD="${PYTHON} -m src.insight_engine"
LOG_FILE="${PROJECT_ROOT}/logs/insight_cron.log"

mkdir -p "$(dirname "$LOG_FILE")"

CRON_ENTRY="0 23 * * * cd ${PROJECT_ROOT} && ${PIPELINE_CMD} >> ${LOG_FILE} 2>&1"

# Check if already installed
if crontab -l 2>/dev/null | grep -qF "src.insight_engine"; then
    echo "Cron job already exists. Updating..."
    crontab -l 2>/dev/null | grep -vF "src.insight_engine" | { cat; echo "$CRON_ENTRY"; } | crontab -
else
    echo "Installing new cron job..."
    (crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -
fi

echo "Cron job installed:"
crontab -l | grep "insight_engine"
echo "Logs will be written to: ${LOG_FILE}"
