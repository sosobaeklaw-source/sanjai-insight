"""
GDPR Compliance Tools
Data anonymization, deletion, and export utilities.
"""

import hashlib
import json
import logging
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


def anonymize_chat_id(chat_id: int) -> str:
    """Anonymize chat ID using one-way hash"""
    salt = "sanjai-insight-2026"  # Application-specific salt
    return hashlib.sha256(f"{chat_id}:{salt}".encode()).hexdigest()[:16]


def log_audit_event(
    conn: sqlite3.Connection,
    event_type: str,
    actor: str,
    actor_id: Optional[str],
    resource_type: str,
    resource_id: str,
    action: str,
    result: str,
    metadata: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
):
    """Log audit event to audit_log table"""
    audit_id = str(uuid4())
    timestamp = datetime.utcnow().isoformat()

    conn.execute("""
        INSERT INTO audit_log (
            id, timestamp, event_type, actor, actor_id,
            resource_type, resource_id, action, metadata_json,
            ip_address, user_agent, result
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        audit_id, timestamp, event_type, actor, actor_id,
        resource_type, resource_id, action,
        json.dumps(metadata) if metadata else None,
        ip_address, user_agent, result
    ))
    conn.commit()

    logger.info(
        "Audit log: %s %s on %s:%s - %s",
        actor, action, resource_type, resource_id, result
    )


def export_user_data(db_path: str, chat_id: int) -> Dict[str, Any]:
    """
    Export all data related to a user (GDPR Article 15).

    Args:
        db_path: Path to database
        chat_id: Telegram chat ID

    Returns:
        Dict with user data
    """
    with sqlite3.connect(db_path) as conn:
        # Log audit event
        log_audit_event(
            conn,
            event_type="DATA_EXPORT",
            actor="USER",
            actor_id=str(chat_id),
            resource_type="USER_DATA",
            resource_id=str(chat_id),
            action="READ",
            result="SUCCESS"
        )

        # Get proposals
        proposals_cursor = conn.execute("""
            SELECT id, title, summary, response, created_at, updated_at
            FROM proposals
            WHERE chat_id = ?
            ORDER BY created_at DESC
        """, (chat_id,))

        proposals = [
            {
                "id": row[0],
                "title": row[1],
                "summary": row[2],
                "response": row[3],
                "created_at": row[4],
                "updated_at": row[5]
            }
            for row in proposals_cursor.fetchall()
        ]

        # Get approvals
        approvals_cursor = conn.execute("""
            SELECT approval_id, proposal_id, decision, decided_at, actor, note
            FROM approvals
            WHERE chat_id = ?
            ORDER BY decided_at DESC
        """, (chat_id,))

        approvals = [
            {
                "approval_id": row[0],
                "proposal_id": row[1],
                "decision": row[2],
                "decided_at": row[3],
                "actor": row[4],
                "note": row[5]
            }
            for row in approvals_cursor.fetchall()
        ]

        # Get telegram updates
        updates_cursor = conn.execute("""
            SELECT update_id, processed_at
            FROM telegram_updates
            WHERE chat_id = ?
            ORDER BY processed_at DESC
            LIMIT 100
        """, (chat_id,))

        updates = [
            {
                "update_id": row[0],
                "processed_at": row[1]
            }
            for row in updates_cursor.fetchall()
        ]

        return {
            "chat_id": chat_id,
            "export_date": datetime.utcnow().isoformat(),
            "proposals": proposals,
            "approvals": approvals,
            "telegram_updates": updates,
            "total_proposals": len(proposals),
            "total_approvals": len(approvals),
            "total_updates": len(updates)
        }


def delete_user_data(db_path: str, chat_id: int, anonymize_audit: bool = True) -> Dict[str, int]:
    """
    Delete all data related to a user (GDPR Article 17).

    Args:
        db_path: Path to database
        chat_id: Telegram chat ID
        anonymize_audit: If True, anonymize audit logs instead of deleting

    Returns:
        Dict with deletion counts
    """
    with sqlite3.connect(db_path) as conn:
        # Log audit event BEFORE deletion
        log_audit_event(
            conn,
            event_type="DATA_DELETION",
            actor="USER",
            actor_id=str(chat_id),
            resource_type="USER_DATA",
            resource_id=str(chat_id),
            action="DELETE",
            result="STARTED"
        )

        counts = {}

        # Delete telegram updates
        cursor = conn.execute("DELETE FROM telegram_updates WHERE chat_id = ?", (chat_id,))
        counts["telegram_updates"] = cursor.rowcount

        # Delete approvals
        cursor = conn.execute("DELETE FROM approvals WHERE chat_id = ?", (chat_id,))
        counts["approvals"] = cursor.rowcount

        # Delete proposals (cascade will handle proposal_actions)
        cursor = conn.execute("DELETE FROM proposals WHERE chat_id = ?", (chat_id,))
        counts["proposals"] = cursor.rowcount

        # Anonymize audit logs (legal requirement to keep audit trail)
        if anonymize_audit:
            anonymized_id = anonymize_chat_id(chat_id)
            cursor = conn.execute("""
                UPDATE audit_log
                SET actor_id = ?
                WHERE actor_id = ?
            """, (anonymized_id, str(chat_id)))
            counts["audit_logs_anonymized"] = cursor.rowcount
        else:
            cursor = conn.execute("DELETE FROM audit_log WHERE actor_id = ?", (str(chat_id),))
            counts["audit_logs_deleted"] = cursor.rowcount

        conn.commit()

        # Log completion
        log_audit_event(
            conn,
            event_type="DATA_DELETION",
            actor="USER",
            actor_id=str(chat_id),
            resource_type="USER_DATA",
            resource_id=str(chat_id),
            action="DELETE",
            result="SUCCESS",
            metadata=counts
        )

        logger.info("User data deleted: chat_id=%s, counts=%s", chat_id, counts)

        return counts


def anonymize_old_data(db_path: str, days: int = 90) -> Dict[str, int]:
    """
    Anonymize data older than specified days.

    Args:
        db_path: Path to database
        days: Age threshold in days

    Returns:
        Dict with anonymization counts
    """
    cutoff = datetime.utcnow().isoformat().replace("T", " ")

    with sqlite3.connect(db_path) as conn:
        counts = {}

        # Anonymize old telegram updates (replace payload_json with placeholder)
        cursor = conn.execute("""
            UPDATE telegram_updates
            SET payload_json = '{}'
            WHERE processed_at < datetime('now', '-{} days')
              AND payload_json != '{{}}'
        """.format(days))
        counts["telegram_updates_anonymized"] = cursor.rowcount

        # Anonymize old LLM call metadata
        cursor = conn.execute("""
            UPDATE llm_calls
            SET meta_json = NULL
            WHERE created_at < datetime('now', '-{} days')
              AND meta_json IS NOT NULL
        """.format(days))
        counts["llm_calls_anonymized"] = cursor.rowcount

        conn.commit()

        logger.info("Anonymized old data (>%d days): %s", days, counts)

        return counts


def cleanup_retention_policy(db_path: str) -> Dict[str, int]:
    """
    Execute retention policy cleanup.

    Returns:
        Dict with deletion counts
    """
    with sqlite3.connect(db_path) as conn:
        counts = {}

        # 30-day retention
        cursor = conn.execute("DELETE FROM telegram_updates WHERE processed_at < datetime('now', '-30 days')")
        counts["telegram_updates"] = cursor.rowcount

        cursor = conn.execute("DELETE FROM source_items WHERE fetched_at < datetime('now', '-30 days')")
        counts["source_items"] = cursor.rowcount

        cursor = conn.execute("DELETE FROM jobs WHERE status IN ('COMPLETED', 'FAILED') AND completed_at < datetime('now', '-30 days')")
        counts["jobs"] = cursor.rowcount

        # 90-day retention
        cursor = conn.execute("DELETE FROM runlogs WHERE ended_at < datetime('now', '-90 days')")
        counts["runlogs"] = cursor.rowcount

        cursor = conn.execute("DELETE FROM llm_calls WHERE created_at < datetime('now', '-90 days')")
        counts["llm_calls"] = cursor.rowcount

        cursor = conn.execute("DELETE FROM events WHERE created_at < datetime('now', '-90 days')")
        counts["events"] = cursor.rowcount

        # 365-day retention
        cursor = conn.execute("DELETE FROM approvals WHERE decided_at < datetime('now', '-365 days')")
        counts["approvals"] = cursor.rowcount

        # Archive and delete audit logs older than 365 days
        # (Archive implementation would go here)
        cursor = conn.execute("DELETE FROM audit_log WHERE created_at < datetime('now', '-365 days')")
        counts["audit_log"] = cursor.rowcount

        conn.commit()

        # Log cleanup event
        log_audit_event(
            conn,
            event_type="RETENTION_CLEANUP",
            actor="SYSTEM",
            actor_id="cleanup_job",
            resource_type="DATABASE",
            resource_id="all_tables",
            action="DELETE",
            result="SUCCESS",
            metadata=counts
        )

        logger.info("Retention policy cleanup completed: %s", counts)

        return counts


def get_data_inventory(db_path: str) -> Dict[str, Any]:
    """
    Get data inventory for compliance reporting.

    Returns:
        Dict with table sizes and retention info
    """
    with sqlite3.connect(db_path) as conn:
        tables = [
            "telegram_updates",
            "jobs",
            "runlogs",
            "llm_calls",
            "events",
            "insights",
            "proposals",
            "approvals",
            "source_items",
            "vault_files",
            "audit_log"
        ]

        inventory = {}

        for table in tables:
            try:
                # Row count
                cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
                row_count = cursor.fetchone()[0]

                # Date range (if has created_at/timestamp column)
                date_columns = ["created_at", "processed_at", "fetched_at", "decided_at", "timestamp", "started_at"]
                date_range = None

                for col in date_columns:
                    try:
                        cursor = conn.execute(f"SELECT MIN({col}), MAX({col}) FROM {table}")
                        result = cursor.fetchone()
                        if result[0] and result[1]:
                            date_range = {"min": result[0], "max": result[1]}
                            break
                    except sqlite3.OperationalError:
                        continue

                inventory[table] = {
                    "row_count": row_count,
                    "date_range": date_range
                }

            except sqlite3.OperationalError as e:
                inventory[table] = {"error": str(e)}

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "tables": inventory
        }


def restrict_user_processing(db_path: str, chat_id: int) -> bool:
    """
    Restrict processing for a user (GDPR Article 18).

    Adds user to exclusion list.

    Args:
        db_path: Path to database
        chat_id: Telegram chat ID

    Returns:
        True if successful
    """
    # In a real implementation, this would add to an exclusion table
    # For now, we'll use audit log
    with sqlite3.connect(db_path) as conn:
        log_audit_event(
            conn,
            event_type="PROCESSING_RESTRICTED",
            actor="USER",
            actor_id=str(chat_id),
            resource_type="USER_DATA",
            resource_id=str(chat_id),
            action="RESTRICT",
            result="SUCCESS"
        )

        logger.info("Processing restricted for chat_id=%s", chat_id)
        return True


def check_if_restricted(db_path: str, chat_id: int) -> bool:
    """
    Check if user processing is restricted.

    Args:
        db_path: Path to database
        chat_id: Telegram chat ID

    Returns:
        True if restricted
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("""
            SELECT COUNT(*) FROM audit_log
            WHERE event_type = 'PROCESSING_RESTRICTED'
              AND actor_id = ?
              AND result = 'SUCCESS'
            ORDER BY created_at DESC
            LIMIT 1
        """, (str(chat_id),))

        return cursor.fetchone()[0] > 0
