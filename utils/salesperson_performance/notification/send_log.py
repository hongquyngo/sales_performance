# utils/salesperson_performance/notification/send_log.py
"""
Notification Send Log — Audit trail for all email notifications.

UPDATED v1.1.0:
- Added @st.cache_data on read operations (ttl=30s)
- Write operations invalidate the read cache
- Eliminates repeated SQL queries on page rerun

VERSION: 1.1.0
"""

import logging
from datetime import date, datetime
from typing import Dict, List, Optional
import pandas as pd
import streamlit as st
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
        
        # Invalidate read caches after write
        _invalidate_send_log_cache()
        return True
    except Exception as e:
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
        ok = _log_send_no_invalidate(
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
    
    # Invalidate cache once after all writes
    if logged > 0:
        _invalidate_send_log_cache()
    
    return logged


def _log_send_no_invalidate(**kwargs) -> bool:
    """Internal log_send without cache invalidation (for batch use)."""
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
                'employee_id': kwargs['employee_id'],
                'employee_name': kwargs['employee_name'],
                'manager_id': kwargs['manager_id'],
                'alert_type': kwargs['alert_type'],
                'subject': (kwargs['subject'] or '')[:500],
                'to_email': (kwargs['to_email'] or '')[:255],
                'cc_email': (kwargs['cc_email'] or '')[:255],
                'alert_count': kwargs['alert_count'],
                'status': kwargs['status'],
                'error_message': (kwargs['error_message'] or '')[:2000],
                'triggered_by': kwargs['triggered_by'],
                'trigger_type': kwargs['trigger_type'],
            })
            conn.commit()
        return True
    except Exception as e:
        logger.warning(f"Could not write notification_log: {e}")
        return False


def _invalidate_send_log_cache():
    """Clear read caches after writes."""
    _get_send_history_cached.clear()
    _get_send_stats_cached.clear()


# =============================================================================
# CACHED READS
# =============================================================================

@st.cache_data(ttl=30, show_spinner=False)
def _get_send_history_cached(
    employee_ids_tuple: Optional[tuple],
    days: int,
    limit: int,
) -> pd.DataFrame:
    """Cached send history query."""
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

    if employee_ids_tuple:
        query += " AND employee_id IN :employee_ids"
        params['employee_ids'] = employee_ids_tuple

    query += " ORDER BY sent_at DESC LIMIT :limit"
    params['limit'] = limit

    try:
        engine = get_db_engine()
        return pd.read_sql(text(query), engine, params=params)
    except Exception as e:
        logger.warning(f"Could not read notification_log: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=30, show_spinner=False)
def _get_send_stats_cached(days: int) -> Dict:
    """Cached send stats query."""
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


# =============================================================================
# PUBLIC READ API
# =============================================================================

def get_send_history(
    employee_ids: Optional[List[int]] = None,
    days: int = 30,
    limit: int = 200,
) -> pd.DataFrame:
    """
    Get notification send history (cached).

    Args:
        employee_ids: Filter by employee (None = all)
        days: Look back N days
        limit: Max rows

    Returns:
        DataFrame with send history, newest first
    """
    ids_tuple = tuple(sorted(employee_ids)) if employee_ids else None
    return _get_send_history_cached(ids_tuple, days, limit)


def get_send_stats(days: int = 30) -> Dict:
    """
    Get send statistics for dashboard display (cached).

    Returns:
        Dict with total_sent, total_failed, total_skipped,
        unique_recipients, last_sent_at
    """
    return _get_send_stats_cached(days)