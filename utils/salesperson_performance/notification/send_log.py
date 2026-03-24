# utils/salesperson_performance/notification/send_log.py
"""
Notification Send Log — Audit trail for all email notifications.

Write after each send, read for history display in Setup UI.
Uses notification_log table.

Usage:
    from utils.salesperson_performance.notification.send_log import (
        log_send,
        get_send_history,
    )

VERSION: 1.0.0
"""

import logging
from datetime import date, datetime
from typing import Dict, List, Optional
import pandas as pd
from sqlalchemy import text

from utils.db import get_db_engine

logger = logging.getLogger(__name__)


# =============================================================================
# WRITE
# =============================================================================

def log_send(
    employee_id: int,
    employee_name: str = "",
    manager_id: Optional[int] = None,
    alert_type: str = "bulletin",
    subject: str = "",
    to_email: str = "",
    cc_email: str = "",
    alert_count: int = 0,
    status: str = "sent",
    error_message: str = "",
    triggered_by: Optional[int] = None,
    trigger_type: str = "manual",
) -> bool:
    """
    Log a single notification send event.

    Returns True on success, False on error (non-blocking).
    """
    query = """
        INSERT INTO notification_log
            (employee_id, employee_name, manager_id, alert_type, subject,
             to_email, cc_email, alert_count, status, error_message,
             triggered_by, trigger_type)
        VALUES
            (:employee_id, :employee_name, :manager_id, :alert_type, :subject,
             :to_email, :cc_email, :alert_count, :status, :error_message,
             :triggered_by, :trigger_type)
    """

    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            conn.execute(text(query), {
                'employee_id': employee_id,
                'employee_name': employee_name,
                'manager_id': manager_id,
                'alert_type': alert_type,
                'subject': subject[:500] if subject else '',
                'to_email': to_email[:255] if to_email else '',
                'cc_email': cc_email[:255] if cc_email else '',
                'alert_count': alert_count,
                'status': status,
                'error_message': error_message[:2000] if error_message else '',
                'triggered_by': triggered_by,
                'trigger_type': trigger_type,
            })
            conn.commit()
        return True
    except Exception as e:
        # Non-blocking — don't crash the send flow
        logger.warning(f"Could not write notification_log: {e}")
        return False


def log_send_batch(details: List[Dict], triggered_by: Optional[int] = None) -> int:
    """
    Log multiple send events from notification_sender details list.

    Args:
        details: List of dicts from NotificationResult.details
        triggered_by: User ID who triggered the send

    Returns:
        Number of successfully logged entries
    """
    logged = 0
    for d in details:
        ok = log_send(
            employee_id=d.get('employee_id', 0),
            employee_name=d.get('name', ''),
            manager_id=None,
            alert_type='bulletin',
            subject=d.get('subject', ''),
            to_email=d.get('to', ''),
            cc_email=d.get('cc', ''),
            alert_count=d.get('alerts', 0),
            status=d.get('status', 'sent'),
            error_message=d.get('error', ''),
            triggered_by=triggered_by,
            trigger_type='manual',
        )
        if ok:
            logged += 1
    return logged


# =============================================================================
# READ
# =============================================================================

def get_send_history(
    employee_ids: Optional[List[int]] = None,
    days: int = 30,
    limit: int = 200,
) -> pd.DataFrame:
    """
    Get notification send history.

    Args:
        employee_ids: Filter by employee (None = all)
        days: Look back N days
        limit: Max rows

    Returns:
        DataFrame with send history, newest first
    """
    query = """
        SELECT
            id,
            employee_id,
            employee_name,
            alert_type,
            subject,
            to_email,
            cc_email,
            alert_count,
            sent_at,
            status,
            error_message,
            triggered_by,
            trigger_type
        FROM notification_log
        WHERE sent_at >= DATE_SUB(NOW(), INTERVAL :days DAY)
    """
    params: Dict = {'days': days}

    if employee_ids:
        query += " AND employee_id IN :employee_ids"
        params['employee_ids'] = tuple(employee_ids)

    query += " ORDER BY sent_at DESC LIMIT :limit"
    params['limit'] = limit

    try:
        engine = get_db_engine()
        return pd.read_sql(text(query), engine, params=params)
    except Exception as e:
        logger.warning(f"Could not read notification_log: {e}")
        return pd.DataFrame()


def get_send_stats(days: int = 30) -> Dict:
    """
    Get send statistics for dashboard display.

    Returns:
        Dict with total_sent, total_failed, total_skipped,
        unique_recipients, last_sent_at
    """
    query = """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) AS sent,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
            SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END) AS skipped,
            COUNT(DISTINCT employee_id) AS unique_recipients,
            MAX(sent_at) AS last_sent_at
        FROM notification_log
        WHERE sent_at >= DATE_SUB(NOW(), INTERVAL :days DAY)
    """

    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            row = conn.execute(text(query), {'days': days}).fetchone()
            if row:
                return {
                    'total': row[0] or 0,
                    'sent': row[1] or 0,
                    'failed': row[2] or 0,
                    'skipped': row[3] or 0,
                    'unique_recipients': row[4] or 0,
                    'last_sent_at': row[5],
                }
    except Exception as e:
        logger.warning(f"Could not read notification stats: {e}")

    return {
        'total': 0, 'sent': 0, 'failed': 0, 'skipped': 0,
        'unique_recipients': 0, 'last_sent_at': None,
    }
