"""
Automatic Backup Manager
Schedules and manages database backups.
"""

import logging
import os
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event, Thread
from typing import Optional

logger = logging.getLogger(__name__)


class BackupManager:
    """Manages automatic database backups"""

    def __init__(
        self,
        db_path: str,
        backup_dir: str = "./backups",
        s3_bucket: Optional[str] = None,
        s3_prefix: str = "sanjai-insight-backups",
        backup_interval_hours: int = 24,
        retention_days: int = 30
    ):
        self.db_path = db_path
        self.backup_dir = backup_dir
        self.s3_bucket = s3_bucket
        self.s3_prefix = s3_prefix
        self.backup_interval_hours = backup_interval_hours
        self.retention_days = retention_days

        self._stop_event = Event()
        self._thread: Optional[Thread] = None
        self._last_backup_time: Optional[datetime] = None

        # Ensure backup directory exists
        Path(backup_dir).mkdir(parents=True, exist_ok=True)

    def start(self):
        """Start automatic backup scheduler"""
        if self._thread and self._thread.is_alive():
            logger.warning("Backup manager already running")
            return

        self._stop_event.clear()
        self._thread = Thread(target=self._backup_loop, daemon=True, name="BackupManager")
        self._thread.start()
        logger.info("Backup manager started (interval: %dh)", self.backup_interval_hours)

    def stop(self):
        """Stop automatic backup scheduler"""
        if not self._thread or not self._thread.is_alive():
            logger.warning("Backup manager not running")
            return

        logger.info("Stopping backup manager...")
        self._stop_event.set()
        self._thread.join(timeout=10)

        if self._thread.is_alive():
            logger.warning("Backup manager thread did not stop gracefully")
        else:
            logger.info("Backup manager stopped")

    def _backup_loop(self):
        """Main backup loop"""
        while not self._stop_event.is_set():
            try:
                # Check if backup is needed
                if self._should_backup():
                    self.create_backup()

                # Sleep in small intervals to respond to stop events quickly
                for _ in range(60):  # Check every minute
                    if self._stop_event.is_set():
                        break
                    time.sleep(60)

            except Exception as e:
                logger.error("Error in backup loop: %s", e, exc_info=True)
                time.sleep(300)  # Wait 5 minutes on error

    def _should_backup(self) -> bool:
        """Check if backup is needed"""
        if self._last_backup_time is None:
            return True

        elapsed = datetime.utcnow() - self._last_backup_time
        return elapsed >= timedelta(hours=self.backup_interval_hours)

    def create_backup(self) -> bool:
        """Create a database backup"""
        try:
            logger.info("Starting backup: %s", self.db_path)

            # Check if database exists
            if not os.path.exists(self.db_path):
                logger.error("Database not found: %s", self.db_path)
                return False

            # Prepare environment variables
            env = os.environ.copy()
            env.update({
                "DB_PATH": self.db_path,
                "BACKUP_DIR": self.backup_dir,
                "RETENTION_DAYS": str(self.retention_days)
            })

            if self.s3_bucket:
                env.update({
                    "S3_BUCKET": self.s3_bucket,
                    "S3_PREFIX": self.s3_prefix
                })

            # Find backup script
            script_path = self._find_backup_script()
            if not script_path:
                logger.error("Backup script not found")
                return False

            # Run backup script
            result = subprocess.run(
                ["bash", script_path],
                env=env,
                capture_output=True,
                text=True,
                timeout=600  # 10 minutes timeout
            )

            if result.returncode == 0:
                logger.info("Backup completed successfully")
                self._last_backup_time = datetime.utcnow()
                return True
            else:
                logger.error("Backup failed: %s", result.stderr)
                return False

        except subprocess.TimeoutExpired:
            logger.error("Backup timed out")
            return False
        except Exception as e:
            logger.error("Error creating backup: %s", e, exc_info=True)
            return False

    def _find_backup_script(self) -> Optional[str]:
        """Find the backup.sh script"""
        # Try multiple locations
        candidates = [
            "./scripts/backup.sh",
            "../scripts/backup.sh",
            "/app/scripts/backup.sh",
            os.path.join(os.path.dirname(__file__), "../../scripts/backup.sh")
        ]

        for path in candidates:
            if os.path.exists(path):
                return os.path.abspath(path)

        return None

    def restore_from_latest(self, source: str = "local") -> bool:
        """Restore from latest backup"""
        try:
            logger.warning("Restoring from latest %s backup", source)

            # Stop backup scheduler during restore
            was_running = self._thread and self._thread.is_alive()
            if was_running:
                self.stop()

            # Prepare environment variables
            env = os.environ.copy()
            env.update({
                "DB_PATH": self.db_path,
                "BACKUP_DIR": self.backup_dir,
            })

            if self.s3_bucket:
                env.update({
                    "S3_BUCKET": self.s3_bucket,
                    "S3_PREFIX": self.s3_prefix
                })

            # Find restore script
            script_path = self._find_restore_script()
            if not script_path:
                logger.error("Restore script not found")
                return False

            # Determine restore option
            option = "--latest" if source == "local" else "--s3-latest"

            # Run restore script
            result = subprocess.run(
                ["bash", script_path, option, "--yes"],
                env=env,
                capture_output=True,
                text=True,
                timeout=600
            )

            if result.returncode == 0:
                logger.info("Restore completed successfully")

                # Restart backup scheduler if it was running
                if was_running:
                    self.start()

                return True
            else:
                logger.error("Restore failed: %s", result.stderr)
                return False

        except subprocess.TimeoutExpired:
            logger.error("Restore timed out")
            return False
        except Exception as e:
            logger.error("Error restoring backup: %s", e, exc_info=True)
            return False

    def _find_restore_script(self) -> Optional[str]:
        """Find the restore.sh script"""
        candidates = [
            "./scripts/restore.sh",
            "../scripts/restore.sh",
            "/app/scripts/restore.sh",
            os.path.join(os.path.dirname(__file__), "../../scripts/restore.sh")
        ]

        for path in candidates:
            if os.path.exists(path):
                return os.path.abspath(path)

        return None

    def list_backups(self, source: str = "local") -> list:
        """List available backups"""
        try:
            if source == "local":
                backup_files = list(Path(self.backup_dir).glob("sanjai_backup_*.db.gz"))
                backups = []

                for f in sorted(backup_files, reverse=True):
                    stat = f.stat()
                    backups.append({
                        "filename": f.name,
                        "path": str(f),
                        "size": stat.st_size,
                        "created": datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })

                return backups

            elif source == "s3":
                if not self.s3_bucket:
                    logger.error("S3 bucket not configured")
                    return []

                # Use AWS CLI to list S3 backups
                result = subprocess.run(
                    [
                        "aws", "s3", "ls",
                        f"s3://{self.s3_bucket}/{self.s3_prefix}/"
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.returncode != 0:
                    logger.error("Failed to list S3 backups: %s", result.stderr)
                    return []

                # Parse AWS CLI output
                backups = []
                for line in result.stdout.strip().split("\n"):
                    if "sanjai_backup_" in line:
                        parts = line.split()
                        if len(parts) >= 4:
                            backups.append({
                                "filename": parts[3],
                                "size": int(parts[2]),
                                "created": f"{parts[0]} {parts[1]}"
                            })

                return sorted(backups, key=lambda x: x["created"], reverse=True)

        except Exception as e:
            logger.error("Error listing backups: %s", e, exc_info=True)
            return []

    def get_status(self) -> dict:
        """Get backup manager status"""
        return {
            "running": self._thread and self._thread.is_alive(),
            "last_backup_time": self._last_backup_time.isoformat() if self._last_backup_time else None,
            "backup_interval_hours": self.backup_interval_hours,
            "retention_days": self.retention_days,
            "db_path": self.db_path,
            "backup_dir": self.backup_dir,
            "s3_enabled": bool(self.s3_bucket),
            "s3_bucket": self.s3_bucket,
            "local_backups_count": len(self.list_backups("local")),
            "s3_backups_count": len(self.list_backups("s3")) if self.s3_bucket else 0
        }
