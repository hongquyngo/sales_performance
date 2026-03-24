# utils/salesperson_performance/notification/preferences.py
"""
Notification Preferences — CRUD operations.

UPDATED v1.1.0:
- Added @st.cache_data on _get_preferences_cached() (ttl=60s)
- Read operations use cached query — no repeated SQL on rerun
- Write operations clear the cache via st.cache_data.clear()
- save_preference/save_preferences_bulk now invalidate cache after write

VERSION: 1.1.0
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
import pandas as pd
import streamlit as st
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

LANGUAGE_OPTIONS = {
    'en': '🇺🇸 English',
    'vi': '🇻🇳 Tiếng Việt',
}

DEFAULT_PREFS = {
    'enabled': True,
    'frequency': 'weekly',
    'notify_manager': True,
    'language': 'en',
}


# =============================================================================
# CACHED SQL READ — avoids repeated DB hits on rerun
# =============================================================================

@st.cache_data(ttl=60, show_spinner=False)
def _get_preferences_cached(
    employee_ids_tuple: tuple,
) -> Dict[int, Dict[str, Any]]:
    """
    Cached SQL query for notification preferences.
    
    Cached for 60s — preferences change infrequently, and writes
    invalidate this cache explicitly.
    
    Returns dict of employee_id → {alert_type → {enabled, frequency, notify_manager}}
    """
    if not employee_ids_tuple:
        return {}

    query = """
        SELECT employee_id, alert_type, enabled, frequency, notify_manager,
               COALESCE(language, 'en') AS language
        FROM notification_preferences
        WHERE employee_id IN :employee_ids
          AND delete_flag = 0
    """

    try:
        engine = get_db_engine()
        df = pd.read_sql(text(query), engine, params={
            'employee_ids': employee_ids_tuple,
        })
    except Exception as e:
        logger.warning(f"notification_preferences table may not exist: {e}")
        return {eid: _build_defaults() for eid in employee_ids_tuple}

    # Build result with defaults
    result: Dict[int, Dict[str, Any]] = {}
    for eid in employee_ids_tuple:
        result[eid] = _build_defaults()

    for _, row in df.iterrows():
        eid = int(row['employee_id'])
        atype = row['alert_type']
        if eid in result and atype in ALERT_TYPES:
            result[eid]['_from_db'] = True
            result[eid][atype] = {
                'enabled': bool(row['enabled']),
                'frequency': row['frequency'] or 'weekly',
                'notify_manager': bool(row['notify_manager']),
                'language': row.get('language', 'en') or 'en',
            }

    return result


def _invalidate_preferences_cache():
    """Clear preferences cache after writes."""
    _get_preferences_cached.clear()


# =============================================================================
# READ
# =============================================================================

def get_preferences_for_employees(
    employee_ids: List[int],
) -> Dict[int, Dict[str, Any]]:
    """
    Get notification preferences for multiple employees.
    
    Uses cached SQL query — no repeated DB hits on rerun.

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
    return _get_preferences_cached(tuple(sorted(employee_ids)))


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
    language: str = 'en',
    modified_by: Optional[int] = None,
) -> bool:
    """
    Save (upsert) a notification preference.
    
    Invalidates preferences cache on success.

    Returns True on success, False on error.
    """
    if alert_type not in ALERT_TYPES:
        logger.error(f"Invalid alert_type: {alert_type}")
        return False

    query = """
        INSERT INTO notification_preferences 
            (employee_id, alert_type, enabled, frequency, notify_manager, language, modified_by)
        VALUES 
            (:employee_id, :alert_type, :enabled, :frequency, :notify_manager, :language, :modified_by)
        ON DUPLICATE KEY UPDATE
            enabled = VALUES(enabled),
            frequency = VALUES(frequency),
            notify_manager = VALUES(notify_manager),
            language = VALUES(language),
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
                'language': language,
                'modified_by': modified_by,
            })
            conn.commit()
        
        # Invalidate cache after successful write
        _invalidate_preferences_cache()
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
    
    Invalidates preferences cache once after all writes.

    Args:
        employee_id: Employee ID
        prefs: Dict of alert_type → {enabled, frequency, notify_manager}
        modified_by: User ID who made the change

    Returns:
        Number of successfully saved preferences
    """
    saved = 0
    for alert_type, settings in prefs.items():
        if alert_type not in ALERT_TYPES:
            continue
        # Use internal save without per-item cache invalidation
        ok = _save_preference_no_invalidate(
            employee_id=employee_id,
            alert_type=alert_type,
            enabled=settings.get('enabled', True),
            frequency=settings.get('frequency', 'weekly'),
            notify_manager=settings.get('notify_manager', True),
            language=settings.get('language', 'en'),
            modified_by=modified_by,
        )
        if ok:
            saved += 1
    
    # Invalidate cache once after all writes
    if saved > 0:
        _invalidate_preferences_cache()
    
    return saved


def _save_preference_no_invalidate(
    employee_id: int,
    alert_type: str,
    enabled: bool,
    frequency: str,
    notify_manager: bool,
    language: str = 'en',
    modified_by: Optional[int] = None,
) -> bool:
    """Internal save without cache invalidation (for bulk use)."""
    query = """
        INSERT INTO notification_preferences 
            (employee_id, alert_type, enabled, frequency, notify_manager, language, modified_by)
        VALUES 
            (:employee_id, :alert_type, :enabled, :frequency, :notify_manager, :language, :modified_by)
        ON DUPLICATE KEY UPDATE
            enabled = VALUES(enabled),
            frequency = VALUES(frequency),
            notify_manager = VALUES(notify_manager),
            language = VALUES(language),
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
                'language': language,
                'modified_by': modified_by,
            })
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error saving notification preference: {e}")
        return False


# =============================================================================
# HELPERS
# =============================================================================

def _build_defaults() -> Dict[str, Dict[str, Any]]:
    """Build default preferences for all alert types."""
    return {
        '_from_db': False,
        **{atype: DEFAULT_PREFS.copy() for atype in ALERT_TYPES},
    }