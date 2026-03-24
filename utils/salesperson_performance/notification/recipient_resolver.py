# utils/salesperson_performance/notification/recipient_resolver.py
"""
Recipient Resolver for Salesperson Notifications.

Looks up salesperson and their direct manager's email addresses
from the employees table.  Returns structured recipient info
for the notification sender.

Usage:
    from utils.salesperson_performance.notification.recipient_resolver import (
        resolve_recipients,
        resolve_recipients_batch,
        RecipientInfo,
    )

    # Single person
    info = resolve_recipients(employee_id=42)
    # info.sales_email = "nguyen@company.com"
    # info.manager_email = "boss@company.com"

    # Multiple people (batch — single SQL query)
    infos = resolve_recipients_batch([42, 55, 60])

VERSION: 1.0.0
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
import pandas as pd
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
        """Primary recipients (sales person)."""
        return [self.sales_email] if self.has_sales_email else []

    @property
    def cc_list(self) -> List[str]:
        """CC recipients (manager)."""
        return [self.manager_email] if self.has_manager_email else []


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
    Resolve recipient emails for multiple salespeople in one query.

    Joins employees table with itself (self-join on manager_id)
    to get both salesperson and manager info.

    Args:
        employee_ids: List of employee IDs

    Returns:
        Dict mapping employee_id → RecipientInfo
    """
    if not employee_ids:
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
            "employee_ids": tuple(employee_ids),
        })

        results: Dict[int, RecipientInfo] = {}
        for _, row in df.iterrows():
            eid = int(row["employee_id"])
            results[eid] = RecipientInfo(
                employee_id=eid,
                sales_name=row["sales_name"] or f"Employee #{eid}",
                sales_email=row["sales_email"],
                manager_id=int(row["manager_id"]) if pd.notna(row["manager_id"]) else None,
                manager_name=row["manager_name"] if pd.notna(row["manager_name"]) else None,
                manager_email=row["manager_email"] if pd.notna(row["manager_email"]) else None,
            )

        found = len(results)
        missing = set(employee_ids) - set(results.keys())
        if missing:
            logger.warning(f"Recipients: {found} found, {len(missing)} not found: {missing}")
        else:
            logger.info(f"Recipients resolved: {found} employees")

        return results

    except Exception as e:
        logger.error(f"Error resolving recipients: {e}")
        return {}


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
