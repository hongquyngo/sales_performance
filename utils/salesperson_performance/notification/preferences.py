# utils/salesperson_performance/notification/preferences.py
"""
Notification Preferences — CRUD operations.

Manages per-employee email notification settings:
- Which alert types are enabled
- Notification frequency (weekly/biweekly/monthly)
- Whether to CC manager

Uses notification_preferences table.

Usage:
    from utils.salesperson_performance.notification.preferences import (
        get_preferences_for_employees,
        save_preference,
        get_preference,
        is_notification_enabled,
        ALERT_TYPES,
    )

VERSION: 1.0.0
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
import pandas as pd
from sqlalchemy import text

from utils.db import get_db_engine

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

ALERT_TYPES = {
    'all': {
        'label': '📧 All Notifications',
        'description': 'Master switch — disable to stop all emails',
    },
    'backlog_past_etd': {
        'label': '📦 Backlog Past ETD',
        'description': 'Orders past expected delivery date',
    },
    'ar_overdue': {
        'label': '💰 AR Overdue',
        'description': 'Invoices past payment due date (30/60/90+ days)',
    },
    'payment_coming_due': {
        'label': '⏰ Payment Coming Due',
        'description': 'Invoices due within next 7 days',
    },
    'kpi_behind': {
        'label': '🎯 KPI Behind Target',
        'description': 'KPI achievement below expected pace',
    },
}

FREQUENCY_OPTIONS = {
    'weekly': 'Weekly (every Monday)',
    'biweekly': 'Bi-weekly (1st & 15th)',
    'monthly': 'Monthly (1st of month)',
}

DEFAULT_PREFS = {
    'enabled': True,
    'frequency': 'weekly',
    'notify_manager': True,
}


# =============================================================================
# READ
# =============================================================================

def get_preferences_for_employees(
    employee_ids: List[int],
) -> Dict[int, Dict[str, Any]]:
    """
    Get notification preferences for multiple employees.

    Returns:
        Dict mapping employee_id → {
            'all': {'enabled': True, 'frequency': 'weekly', 'notify_manager': True},
            'backlog_past_etd': {...},
            ...
        }
        Missing entries return defaults (all enabled).
    """
    if not employee_ids:
        return {}

    query = """
        SELECT employee_id, alert_type, enabled, frequency, notify_manager
        FROM notification_preferences
        WHERE employee_id IN :employee_ids
          AND delete_flag = 0
    """

    try:
        engine = get_db_engine()
        df = pd.read_sql(text(query), engine, params={
            'employee_ids': tuple(employee_ids),
        })
    except Exception as e:
        logger.warning(f"notification_preferences table may not exist: {e}")
        # Return defaults for all — table not created yet
        return {eid: _build_defaults() for eid in employee_ids}

    # Build result with defaults
    result: Dict[int, Dict[str, Any]] = {}
    for eid in employee_ids:
        result[eid] = _build_defaults()

    for _, row in df.iterrows():
        eid = int(row['employee_id'])
        atype = row['alert_type']
        if eid in result and atype in ALERT_TYPES:
            result[eid][atype] = {
                'enabled': bool(row['enabled']),
                'frequency': row['frequency'] or 'weekly',
                'notify_manager': bool(row['notify_manager']),
            }

    return result


def get_preference(
    employee_id: int,
    alert_type: str,
) -> Dict[str, Any]:
    """Get single preference. Returns defaults if not found."""
    prefs = get_preferences_for_employees([employee_id])
    emp_prefs = prefs.get(employee_id, _build_defaults())
    return emp_prefs.get(alert_type, DEFAULT_PREFS.copy())


def is_notification_enabled(
    employee_id: int,
    alert_type: str,
    prefs_cache: Optional[Dict] = None,
) -> bool:
    """
    Check if a specific notification is enabled for an employee.

    Checks both the master 'all' switch and the specific alert_type.
    """
    if prefs_cache and employee_id in prefs_cache:
        emp_prefs = prefs_cache[employee_id]
    else:
        emp_prefs = get_preferences_for_employees([employee_id]).get(
            employee_id, _build_defaults()
        )

    # Master switch
    master = emp_prefs.get('all', DEFAULT_PREFS)
    if not master.get('enabled', True):
        return False

    # Specific alert type
    specific = emp_prefs.get(alert_type, DEFAULT_PREFS)
    return specific.get('enabled', True)


# =============================================================================
# WRITE
# =============================================================================

def save_preference(
    employee_id: int,
    alert_type: str,
    enabled: bool,
    frequency: str = 'weekly',
    notify_manager: bool = True,
    modified_by: Optional[int] = None,
) -> bool:
    """
    Save (upsert) a notification preference.

    Returns True on success, False on error.
    """
    if alert_type not in ALERT_TYPES:
        logger.error(f"Invalid alert_type: {alert_type}")
        return False

    # Upsert: INSERT ... ON DUPLICATE KEY UPDATE
    query = """
        INSERT INTO notification_preferences 
            (employee_id, alert_type, enabled, frequency, notify_manager, modified_by)
        VALUES 
            (:employee_id, :alert_type, :enabled, :frequency, :notify_manager, :modified_by)
        ON DUPLICATE KEY UPDATE
            enabled = VALUES(enabled),
            frequency = VALUES(frequency),
            notify_manager = VALUES(notify_manager),
            modified_by = VALUES(modified_by),
            modified_date = CURRENT_TIMESTAMP
    """

    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            conn.execute(text(query), {
                'employee_id': employee_id,
                'alert_type': alert_type,
                'enabled': int(enabled),
                'frequency': frequency,
                'notify_manager': int(notify_manager),
                'modified_by': modified_by,
            })
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error saving notification preference: {e}")
        return False


def save_preferences_bulk(
    employee_id: int,
    prefs: Dict[str, Dict[str, Any]],
    modified_by: Optional[int] = None,
) -> int:
    """
    Save multiple preferences at once for one employee.

    Args:
        employee_id: Employee ID
        prefs: Dict of alert_type → {enabled, frequency, notify_manager}
        modified_by: User ID who made the change

    Returns:
        Number of successfully saved preferences
    """
    saved = 0
    for alert_type, settings in prefs.items():
        ok = save_preference(
            employee_id=employee_id,
            alert_type=alert_type,
            enabled=settings.get('enabled', True),
            frequency=settings.get('frequency', 'weekly'),
            notify_manager=settings.get('notify_manager', True),
            modified_by=modified_by,
        )
        if ok:
            saved += 1
    return saved


# =============================================================================
# HELPERS
# =============================================================================

def _build_defaults() -> Dict[str, Dict[str, Any]]:
    """Build default preferences for all alert types."""
    return {atype: DEFAULT_PREFS.copy() for atype in ALERT_TYPES}
