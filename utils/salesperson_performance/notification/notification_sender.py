# utils/salesperson_performance/notification/notification_sender.py
"""
Notification Sender — Orchestrator for Salesperson Performance Alerts.

Coordinates:
1. Recipient resolution (recipient_resolver)
2. HTML email building (email_builder)
3. Email sending (email_service)
4. Audit logging (notification_log table — future)

Phase 1: Send team-level bulletin to selected salespeople + managers.
Phase 2 (future): Per-salesperson individualized alerts.

Usage:
    from utils.salesperson_performance.notification.notification_sender import (
        send_bulletin_to_team,
        NotificationResult,
    )

    result = send_bulletin_to_team(
        bulletin=warning_bulletin,
        employee_ids=[42, 55, 60],
        active_filters=active_filters,
        overview_metrics=overview_metrics,
        sender_name="Quy Ngo",
        cc_managers=True,
    )

    if result.success:
        st.success(f"Sent to {result.sent_count} recipients")
    else:
        st.error(result.message)

VERSION: 1.0.0
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class NotificationResult:
    """Result of a notification send operation."""
    success: bool
    message: str
    sent_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    details: List[Dict] = field(default_factory=list)
    elapsed_seconds: float = 0.0


# =============================================================================
# PUBLIC API
# =============================================================================

def send_bulletin_to_team(
    bulletin: Dict,
    employee_ids: List[int],
    active_filters: Dict,
    overview_metrics: Optional[Dict] = None,
    sender_name: str = "Prostech BI",
    cc_managers: bool = True,
    # Per-employee data sources (NEW — individualized emails)
    sales_df: Optional['pd.DataFrame'] = None,
    backlog_detail_df: Optional['pd.DataFrame'] = None,
    ar_outstanding_df: Optional['pd.DataFrame'] = None,
    targets_df: Optional['pd.DataFrame'] = None,
) -> NotificationResult:
    """
    Send individualized bulletin email to each salesperson (+ their manager CC).

    Each salesperson receives email with THEIR OWN data:
    - Their revenue, GP, GP1, invoices
    - Their backlog past ETD
    - Their AR overdue
    - Their KPI achievement vs target

    If per-employee data sources are not provided, falls back to
    team-level bulletin (same content for everyone).

    Args:
        bulletin:           Team-level bulletin (fallback if no per-employee data)
        employee_ids:       List of salesperson employee IDs to notify
        active_filters:     Current filter state
        overview_metrics:   Team-level metrics (fallback)
        sender_name:        Name of the person triggering the send
        cc_managers:        Whether to CC direct managers
        sales_df:           Filtered sales data (all employees) for per-person split
        backlog_detail_df:  Backlog detail (all employees) for per-person split
        ar_outstanding_df:  AR outstanding (all employees) for per-person split
        targets_df:         KPI targets (all employees) for per-person split

    Returns:
        NotificationResult with per-recipient details
    """
    import time
    import pandas as pd

    # Lazy imports
    from .email_service import EmailService
    from .email_builder import build_bulletin_email, build_bulletin_plain_text
    from .recipient_resolver import resolve_recipients_batch

    start = time.perf_counter()

    # --- 1. Check email service ---
    svc = EmailService()
    if not svc.is_configured:
        return NotificationResult(
            success=False,
            message="Email not configured. Check EMAIL_SENDER / EMAIL_PASSWORD.",
        )

    if not employee_ids:
        return NotificationResult(
            success=False,
            message="No salespeople selected.",
        )

    # --- 2. Resolve recipients ---
    recipients_map = resolve_recipients_batch(employee_ids)

    if not recipients_map:
        return NotificationResult(
            success=False,
            message="Could not resolve any recipient emails.",
        )

    # --- 3. Get dashboard URL ---
    try:
        from utils.config import config
        dashboard_url = config.get_app_setting("APP_BASE_URL", "")
    except Exception:
        dashboard_url = ""

    # --- 3b. Load preferences (skip disabled employees) ---
    prefs_cache = {}
    try:
        from .preferences import get_preferences_for_employees, is_notification_enabled
        prefs_cache = get_preferences_for_employees(employee_ids)
    except Exception as e:
        logger.debug(f"Preferences not available (table may not exist): {e}")
        # Continue without preferences — all enabled by default

    # --- 4. Check if per-employee data is available ---
    has_per_employee_data = (
        sales_df is not None and not sales_df.empty
    )

    if has_per_employee_data:
        from .alert_data_collector import collect_per_employee_bulletin

    # --- 5. Send per-salesperson ---
    details = []
    sent_count = 0
    failed_count = 0
    skipped_count = 0

    for eid in employee_ids:
        info = recipients_map.get(eid)

        if not info:
            details.append({
                "employee_id": eid,
                "status": "skipped",
                "reason": "Employee not found in database",
            })
            skipped_count += 1
            continue

        if not info.has_sales_email:
            details.append({
                "employee_id": eid,
                "name": info.sales_name,
                "status": "skipped",
                "reason": "No email address",
            })
            skipped_count += 1
            continue

        # Check notification preferences (skip if disabled)
        if prefs_cache:
            master_pref = prefs_cache.get(eid, {}).get('all', {})
            if not master_pref.get('enabled', True):
                details.append({
                    "employee_id": eid,
                    "name": info.sales_name,
                    "status": "skipped",
                    "reason": "Notifications disabled",
                })
                skipped_count += 1
                continue

        # ─── Build per-employee content ───
        if has_per_employee_data:
            # INDIVIDUALIZED: filter data for this employee
            emp_bulletin, emp_metrics = collect_per_employee_bulletin(
                employee_id=eid,
                employee_name=info.sales_name,
                sales_df=sales_df,
                backlog_detail_df=backlog_detail_df if backlog_detail_df is not None else pd.DataFrame(),
                ar_outstanding_df=ar_outstanding_df if ar_outstanding_df is not None else pd.DataFrame(),
                targets_df=targets_df if targets_df is not None else pd.DataFrame(),
                active_filters=active_filters,
            )
        else:
            # FALLBACK: team-level bulletin
            emp_bulletin = bulletin
            emp_metrics = overview_metrics

        # ─── CC note for manager ───
        cc_note = ""
        cc_list = []
        # Check CC preference (function param + per-employee preference)
        emp_cc_pref = True
        if prefs_cache and eid in prefs_cache:
            emp_cc_pref = prefs_cache[eid].get('all', {}).get('notify_manager', True)
        if cc_managers and emp_cc_pref and info.has_manager_email:
            cc_list = info.cc_list
            cc_note = f"This alert was also sent to {info.sales_name} (your direct report)."

        # ─── Build HTML email ───
        subject, html_body = build_bulletin_email(
            bulletin=emp_bulletin,
            active_filters=active_filters,
            overview_metrics=emp_metrics,
            sender_name=sender_name,
            dashboard_url=dashboard_url,
            cc_note=cc_note,
        )
        plain_text = build_bulletin_plain_text(emp_bulletin)

        # Append employee name to subject
        personal_subject = f"{subject} — {info.sales_name}"

        # ─── Send ───
        result = svc.send(
            to=info.to_list,
            subject=personal_subject,
            html=html_body,
            plain_text=plain_text,
            cc=cc_list,
        )

        if result.success:
            sent_count += 1
            alert_count = emp_bulletin.get('alert_count', 0)
            details.append({
                "employee_id": eid,
                "name": info.sales_name,
                "status": "sent",
                "to": info.sales_email,
                "cc": info.manager_email if cc_list else None,
                "alerts": alert_count,
                "elapsed": result.elapsed_seconds,
            })
        else:
            failed_count += 1
            details.append({
                "employee_id": eid,
                "name": info.sales_name,
                "status": "failed",
                "to": info.sales_email,
                "error": result.message,
            })

        # Brief delay between emails to avoid rate limiting
        if len(employee_ids) > 1:
            time.sleep(0.5)

    elapsed = round(time.perf_counter() - start, 2)

    # --- 5b. Write to notification_log (non-blocking) ---
    try:
        from .send_log import log_send_batch
        triggered_by_id = None
        try:
            import streamlit as _st
            triggered_by_id = _st.session_state.get('employee_id')
        except Exception:
            pass
        log_send_batch(details, triggered_by=triggered_by_id)
    except Exception as e:
        logger.debug(f"Could not write send log: {e}")

    # --- 6. Build summary ---
    mode = "individualized" if has_per_employee_data else "team bulletin"
    if sent_count > 0 and failed_count == 0:
        success = True
        msg = f"✅ Sent {mode} to {sent_count} salesperson(s)"
        if skipped_count:
            msg += f" ({skipped_count} skipped — no email)"
    elif sent_count > 0 and failed_count > 0:
        success = True
        msg = f"⚠️ Sent: {sent_count}, Failed: {failed_count}, Skipped: {skipped_count} ({mode})"
    else:
        success = False
        msg = f"❌ All emails failed. Sent: 0, Failed: {failed_count}, Skipped: {skipped_count}"

    logger.info(f"Bulletin notification: {msg} ({elapsed}s)")

    return NotificationResult(
        success=success,
        message=msg,
        sent_count=sent_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
        details=details,
        elapsed_seconds=elapsed,
    )