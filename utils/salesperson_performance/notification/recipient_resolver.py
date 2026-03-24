# utils/salesperson_performance/notification/recipient_resolver.py
"""
Recipient Resolver for Salesperson Notifications.

Looks up salesperson and their direct manager's email addresses
from the employees table.  Returns structured recipient info
for the notification sender.

UPDATED v1.1.0:
- Added @st.cache_data on _resolve_recipients_cached() (ttl=300s)
- resolve_recipients_batch() now uses cached inner function
- Eliminates repeated SQL on every page rerun / dialog interaction

Usage:
    from utils.salesperson_performance.notification.recipient_resolver import (
        resolve_recipients,
        resolve_recipients_batch,
        RecipientInfo,
    )

VERSION: 1.1.0
"""

import logging
from dataclasses import dataclass
from email.utils import formataddr
from typing import Dict, List, Optional
import pandas as pd
import streamlit as st
from sqlalchemy import text

from utils.db import get_db_engine

logger = logging.getLogger(__name__)


@dataclass
class RecipientInfo:
    """Resolved email recipient for one salesperson."""
    employee_id: int
    sales_name: str
    sales_email: Optional[str]
    manager_id: Optional[int]
    manager_name: Optional[str]
    manager_email: Optional[str]

    @property
    def has_sales_email(self) -> bool:
        return bool(self.sales_email and "@" in self.sales_email)

    @property
    def has_manager_email(self) -> bool:
        return bool(self.manager_email and "@" in self.manager_email)

    @property
    def to_list(self) -> List[str]:
        """Primary recipients — plain email for SMTP envelope."""
        return [self.sales_email] if self.has_sales_email else []

    @property
    def cc_list(self) -> List[str]:
        """CC recipients — plain email for SMTP envelope."""
        return [self.manager_email] if self.has_manager_email else []

    @property
    def to_list_named(self) -> List[str]:
        """Primary recipients — 'Name <email>' for display headers."""
        if self.has_sales_email:
            return [formataddr((self.sales_name, self.sales_email))]
        return []

    @property
    def cc_list_named(self) -> List[str]:
        """CC recipients — 'Name <email>' for display headers."""
        if self.has_manager_email:
            return [formataddr((self.manager_name or '', self.manager_email))]
        return []


# =============================================================================
# CACHED SQL QUERY — avoids repeated DB hits on rerun/fragment rerun
# =============================================================================

@st.cache_data(ttl=300, show_spinner=False)
def _resolve_recipients_cached(
    employee_ids_tuple: tuple,
) -> Dict[int, dict]:
    """
    Cached SQL query for recipient resolution.
    
    Returns raw dict (not RecipientInfo) because dataclasses aren't
    hashable/serializable for st.cache_data by default.
    
    Cached for 5 minutes — employee emails rarely change.
    """
    if not employee_ids_tuple:
        return {}

    query = """
        SELECT
            e.id              AS employee_id,
            CONCAT(e.first_name, ' ', e.last_name) AS sales_name,
            e.email           AS sales_email,
            e.manager_id,
            CONCAT(m.first_name, ' ', m.last_name) AS manager_name,
            m.email           AS manager_email
        FROM employees e
        LEFT JOIN employees m 
            ON e.manager_id = m.id 
           AND m.delete_flag = 0
        WHERE e.id IN :employee_ids
          AND e.delete_flag = 0
    """

    try:
        engine = get_db_engine()
        df = pd.read_sql(text(query), engine, params={
            "employee_ids": employee_ids_tuple,
        })

        results: Dict[int, dict] = {}
        for _, row in df.iterrows():
            eid = int(row["employee_id"])
            results[eid] = {
                "employee_id": eid,
                "sales_name": row["sales_name"] or f"Employee #{eid}",
                "sales_email": row["sales_email"],
                "manager_id": int(row["manager_id"]) if pd.notna(row["manager_id"]) else None,
                "manager_name": row["manager_name"] if pd.notna(row["manager_name"]) else None,
                "manager_email": row["manager_email"] if pd.notna(row["manager_email"]) else None,
            }

        found = len(results)
        missing = set(employee_ids_tuple) - set(results.keys())
        if missing:
            logger.warning(f"Recipients: {found} found, {len(missing)} not found: {missing}")
        else:
            logger.info(f"Recipients resolved: {found} employees (cached)")

        return results

    except Exception as e:
        logger.error(f"Error resolving recipients: {e}")
        return {}


# =============================================================================
# PUBLIC API
# =============================================================================

def resolve_recipients(employee_id: int) -> Optional[RecipientInfo]:
    """
    Resolve recipient emails for a single salesperson.

    Args:
        employee_id: Employee ID of the salesperson

    Returns:
        RecipientInfo or None if employee not found
    """
    results = resolve_recipients_batch([employee_id])
    return results.get(employee_id)


def resolve_recipients_batch(
    employee_ids: List[int],
) -> Dict[int, RecipientInfo]:
    """
    Resolve recipient emails for multiple salespeople.
    
    Uses cached SQL query — no repeated DB hits on rerun.

    Args:
        employee_ids: List of employee IDs

    Returns:
        Dict mapping employee_id → RecipientInfo
    """
    if not employee_ids:
        return {}

    # Convert to tuple for cache key compatibility
    raw = _resolve_recipients_cached(tuple(sorted(employee_ids)))

    # Convert raw dicts to RecipientInfo dataclasses
    return {
        eid: RecipientInfo(**data)
        for eid, data in raw.items()
    }


# =============================================================================
# CC PICKER — all active employees with email
# =============================================================================

@st.cache_data(ttl=300, show_spinner=False)
def get_all_employees_with_email() -> List[Dict]:
    """
    Get all active employees with email for CC picker.

    Cached for 5 minutes. Returns list of {id, name, email, department}.
    Used by Send Now tab to populate additional CC multiselect.
    """
    query = """
        SELECT
            e.id,
            CONCAT(e.first_name, ' ', e.last_name) AS name,
            e.email,
            COALESCE(d.name, '') AS department
        FROM employees e
        LEFT JOIN departments d ON e.department_id = d.id AND d.delete_flag = 0
        WHERE e.delete_flag = 0
          AND e.email IS NOT NULL
          AND e.email != ''
        ORDER BY e.first_name, e.last_name
    """
    try:
        engine = get_db_engine()
        df = pd.read_sql(text(query), engine)
        return df.to_dict('records')
    except Exception as e:
        logger.error(f"Error loading employees for CC picker: {e}")
        return []


def resolve_all_selected_recipients(
    employee_ids: List[int],
) -> Dict:
    """
    Resolve recipients and return summary for UI display.

    Returns:
        Dict with:
        - recipients: Dict[int, RecipientInfo]
        - to_emails: deduplicated list of sales emails
        - cc_emails: deduplicated list of manager emails
        - missing_email: list of names with no email
        - summary: human-readable summary string
    """
    recipients = resolve_recipients_batch(employee_ids)

    to_emails = []
    cc_emails = []
    missing_email = []
    seen_to = set()
    seen_cc = set()

    for eid in employee_ids:
        info = recipients.get(eid)
        if not info:
            missing_email.append(f"Employee #{eid} (not found)")
            continue

        if info.has_sales_email and info.sales_email not in seen_to:
            to_emails.append(info.sales_email)
            seen_to.add(info.sales_email)
        elif not info.has_sales_email:
            missing_email.append(f"{info.sales_name} (no email)")

        if info.has_manager_email and info.manager_email not in seen_cc:
            cc_emails.append(info.manager_email)
            seen_cc.add(info.manager_email)

    # Summary
    parts = [f"To: {len(to_emails)} salesperson(s)"]
    if cc_emails:
        parts.append(f"CC: {len(cc_emails)} manager(s)")
    if missing_email:
        parts.append(f"⚠️ {len(missing_email)} missing email")
    summary = " | ".join(parts)

    return {
        "recipients": recipients,
        "to_emails": to_emails,
        "cc_emails": cc_emails,
        "missing_email": missing_email,
        "summary": summary,
    }