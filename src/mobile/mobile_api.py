"""
Mobile App Backend API.

Features:
- Mobile-optimized endpoints
- Push notification support
- Offline sync capabilities
- Device management
- Mobile analytics
"""

import logging
import sqlite3
import os
import json
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class DevicePlatform(Enum):
    """Mobile device platforms."""
    IOS = "ios"
    ANDROID = "android"
    WEB = "web"


class NotificationType(Enum):
    """Push notification types."""
    INSIGHT = "insight"
    ALERT = "alert"
    MESSAGE = "message"
    REMINDER = "reminder"


@dataclass
class Device:
    """Mobile device registration."""
    device_id: str
    user_id: str
    platform: DevicePlatform
    push_token: str
    app_version: str
    os_version: str
    created_at: datetime
    last_active: datetime
    is_active: bool = True
    metadata: Dict = field(default_factory=dict)


@dataclass
class PushNotification:
    """Push notification definition."""
    notification_id: str
    device_id: str
    notification_type: NotificationType
    title: str
    body: str
    data: Dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None


@dataclass
class SyncState:
    """Offline sync state."""
    user_id: str
    last_sync: datetime
    pending_changes: List[Dict] = field(default_factory=list)
    conflict_resolution: str = "server_wins"


class DeviceManager:
    """
    Manage mobile device registrations and lifecycle.

    Features:
    - Device registration and authentication
    - Session management
    - Device metadata tracking
    """

    def __init__(self, db_path: str = "data/mobile.db"):
        """Initialize device manager."""
        self.db_path = db_path
        self._ensure_db()

    def _ensure_db(self):
        """Create mobile database."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    push_token TEXT,
                    app_version TEXT NOT NULL,
                    os_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_active TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    metadata TEXT DEFAULT '{}'
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_devices
                ON devices(user_id)
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    duration_seconds INTEGER DEFAULT 0,
                    FOREIGN KEY (device_id) REFERENCES devices(device_id)
                )
            """)

    def register_device(
        self,
        device_id: str,
        user_id: str,
        platform: DevicePlatform,
        app_version: str,
        os_version: str,
        push_token: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Device:
        """
        Register or update mobile device.

        Args:
            device_id: Device identifier
            user_id: User identifier
            platform: Device platform
            app_version: App version
            os_version: OS version
            push_token: Optional push notification token
            metadata: Optional device metadata

        Returns:
            Device object
        """
        now = datetime.utcnow()

        device = Device(
            device_id=device_id,
            user_id=user_id,
            platform=platform,
            push_token=push_token or "",
            app_version=app_version,
            os_version=os_version,
            created_at=now,
            last_active=now,
            metadata=metadata or {}
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO devices
                (device_id, user_id, platform, push_token, app_version,
                 os_version, created_at, last_active, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                device.device_id,
                device.user_id,
                device.platform.value,
                device.push_token,
                device.app_version,
                device.os_version,
                device.created_at.isoformat(),
                device.last_active.isoformat(),
                json.dumps(device.metadata)
            ))

        logger.info(f"Registered device {device_id} for user {user_id}")
        return device

    def update_last_active(self, device_id: str):
        """Update device last active timestamp."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE devices
                SET last_active = ?
                WHERE device_id = ?
            """, (datetime.utcnow().isoformat(), device_id))

    def get_user_devices(self, user_id: str) -> List[Device]:
        """Get all devices for user."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT device_id, user_id, platform, push_token,
                       app_version, os_version, created_at, last_active,
                       is_active, metadata
                FROM devices
                WHERE user_id = ? AND is_active = 1
                ORDER BY last_active DESC
            """, (user_id,))

            devices = []
            for row in cursor.fetchall():
                devices.append(Device(
                    device_id=row[0],
                    user_id=row[1],
                    platform=DevicePlatform(row[2]),
                    push_token=row[3],
                    app_version=row[4],
                    os_version=row[5],
                    created_at=datetime.fromisoformat(row[6]),
                    last_active=datetime.fromisoformat(row[7]),
                    is_active=bool(row[8]),
                    metadata=json.loads(row[9])
                ))

            return devices

    def deactivate_device(self, device_id: str):
        """Deactivate device."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE devices
                SET is_active = 0
                WHERE device_id = ?
            """, (device_id,))

        logger.info(f"Deactivated device {device_id}")


class PushNotificationService:
    """
    Push notification service for mobile apps.

    Features:
    - FCM (Firebase Cloud Messaging) for Android
    - APNs (Apple Push Notification service) for iOS
    - Notification scheduling
    - Delivery tracking
    """

    def __init__(
        self,
        db_path: str = "data/mobile.db",
        fcm_key: Optional[str] = None,
        apns_key: Optional[str] = None
    ):
        """Initialize push notification service."""
        self.db_path = db_path
        self.fcm_key = fcm_key or os.getenv("FCM_SERVER_KEY")
        self.apns_key = apns_key or os.getenv("APNS_KEY")
        self._ensure_db()

    def _ensure_db(self):
        """Create notification database."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    notification_id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    notification_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    data TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    sent_at TEXT,
                    delivered_at TEXT,
                    clicked_at TEXT
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_device_notifications
                ON notifications(device_id, created_at)
            """)

    def send_notification(
        self,
        device: Device,
        notification_type: NotificationType,
        title: str,
        body: str,
        data: Optional[Dict] = None
    ) -> PushNotification:
        """
        Send push notification to device.

        Args:
            device: Target device
            notification_type: Notification type
            title: Notification title
            body: Notification body
            data: Optional data payload

        Returns:
            Push notification object
        """
        notification_id = f"notif_{int(time.time())}_{device.device_id}"

        notification = PushNotification(
            notification_id=notification_id,
            device_id=device.device_id,
            notification_type=notification_type,
            title=title,
            body=body,
            data=data or {}
        )

        # Save notification
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO notifications
                (notification_id, device_id, notification_type,
                 title, body, data, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                notification.notification_id,
                notification.device_id,
                notification.notification_type.value,
                notification.title,
                notification.body,
                json.dumps(notification.data),
                notification.created_at.isoformat()
            ))

        # Send via platform-specific service
        if device.platform == DevicePlatform.ANDROID:
            self._send_fcm(device, notification)
        elif device.platform == DevicePlatform.IOS:
            self._send_apns(device, notification)

        logger.info(
            f"Sent notification {notification_id} to device {device.device_id}"
        )

        return notification

    def _send_fcm(self, device: Device, notification: PushNotification):
        """Send notification via Firebase Cloud Messaging."""
        if not self.fcm_key or not device.push_token:
            logger.warning("FCM key or push token not available")
            return

        # Simulate FCM send (replace with actual FCM client)
        logger.info(f"FCM: Sending to {device.push_token}")

        # Update sent timestamp
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE notifications
                SET sent_at = ?
                WHERE notification_id = ?
            """, (datetime.utcnow().isoformat(), notification.notification_id))

    def _send_apns(self, device: Device, notification: PushNotification):
        """Send notification via Apple Push Notification service."""
        if not self.apns_key or not device.push_token:
            logger.warning("APNs key or push token not available")
            return

        # Simulate APNs send (replace with actual APNs client)
        logger.info(f"APNs: Sending to {device.push_token}")

        # Update sent timestamp
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE notifications
                SET sent_at = ?
                WHERE notification_id = ?
            """, (datetime.utcnow().isoformat(), notification.notification_id))

    def mark_delivered(self, notification_id: str):
        """Mark notification as delivered."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE notifications
                SET delivered_at = ?
                WHERE notification_id = ?
            """, (datetime.utcnow().isoformat(), notification_id))

    def mark_clicked(self, notification_id: str):
        """Mark notification as clicked."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE notifications
                SET clicked_at = ?
                WHERE notification_id = ?
            """, (datetime.utcnow().isoformat(), notification_id))

    def get_notification_stats(self, device_id: str) -> Dict:
        """Get notification statistics for device."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN sent_at IS NOT NULL THEN 1 ELSE 0 END) as sent,
                    SUM(CASE WHEN delivered_at IS NOT NULL THEN 1 ELSE 0 END) as delivered,
                    SUM(CASE WHEN clicked_at IS NOT NULL THEN 1 ELSE 0 END) as clicked
                FROM notifications
                WHERE device_id = ?
            """, (device_id,))

            row = cursor.fetchone()

            return {
                "total": row[0],
                "sent": row[1],
                "delivered": row[2],
                "clicked": row[3],
                "delivery_rate": row[2] / max(row[1], 1),
                "click_rate": row[3] / max(row[2], 1)
            }


class OfflineSyncManager:
    """
    Manage offline data synchronization for mobile apps.

    Features:
    - Incremental sync
    - Conflict resolution
    - Change tracking
    - Sync queue management
    """

    def __init__(self, db_path: str = "data/mobile.db"):
        """Initialize sync manager."""
        self.db_path = db_path
        self._ensure_db()

    def _ensure_db(self):
        """Create sync database."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_states (
                    user_id TEXT PRIMARY KEY,
                    last_sync TEXT NOT NULL,
                    pending_changes TEXT DEFAULT '[]',
                    conflict_resolution TEXT DEFAULT 'server_wins'
                )
            """)

    def get_sync_state(self, user_id: str) -> SyncState:
        """Get sync state for user."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT user_id, last_sync, pending_changes, conflict_resolution
                FROM sync_states
                WHERE user_id = ?
            """, (user_id,))

            row = cursor.fetchone()

            if not row:
                # Initialize sync state
                now = datetime.utcnow()
                state = SyncState(
                    user_id=user_id,
                    last_sync=now
                )

                conn.execute("""
                    INSERT INTO sync_states (user_id, last_sync)
                    VALUES (?, ?)
                """, (user_id, now.isoformat()))

                return state

            return SyncState(
                user_id=row[0],
                last_sync=datetime.fromisoformat(row[1]),
                pending_changes=json.loads(row[2]),
                conflict_resolution=row[3]
            )

    def update_sync_state(self, state: SyncState):
        """Update sync state."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE sync_states
                SET last_sync = ?, pending_changes = ?, conflict_resolution = ?
                WHERE user_id = ?
            """, (
                state.last_sync.isoformat(),
                json.dumps(state.pending_changes),
                state.conflict_resolution,
                state.user_id
            ))

    def get_changes_since(
        self,
        user_id: str,
        since: datetime
    ) -> List[Dict]:
        """
        Get changes since timestamp.

        Args:
            user_id: User identifier
            since: Timestamp to get changes after

        Returns:
            List of change objects
        """
        # Simulate fetching changes (replace with actual data source)
        changes = [
            {
                "type": "insight",
                "id": "insight_123",
                "action": "created",
                "timestamp": datetime.utcnow().isoformat(),
                "data": {"title": "New Insight", "content": "..."}
            }
        ]

        return changes

    def apply_changes(
        self,
        user_id: str,
        changes: List[Dict]
    ) -> Dict[str, int]:
        """
        Apply changes from mobile device.

        Args:
            user_id: User identifier
            changes: List of changes to apply

        Returns:
            Summary of applied changes
        """
        applied = 0
        conflicts = 0

        for change in changes:
            try:
                # Simulate applying change
                logger.info(f"Applying change: {change['type']} {change['id']}")
                applied += 1

            except Exception as e:
                logger.error(f"Failed to apply change: {e}")
                conflicts += 1

        return {
            "applied": applied,
            "conflicts": conflicts,
            "total": len(changes)
        }
