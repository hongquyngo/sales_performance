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

VERSION: 2.0.0 — Added send_warning_to_selected()
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
        cc_list_named = []
        # Check CC preference (function param + per-employee preference)
        emp_cc_pref = True
        if prefs_cache and eid in prefs_cache:
            emp_cc_pref = prefs_cache[eid].get('all', {}).get('notify_manager', True)
        if cc_managers and emp_cc_pref and info.has_manager_email:
            cc_list = info.cc_list
            cc_list_named = info.cc_list_named
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
            to_display=info.to_list_named,
            cc_display=cc_list_named if cc_list else None,
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


# =============================================================================
# WARNING EMAIL SENDER (v3.0 — bilingual + Excel attachment)
# =============================================================================

def send_warning_to_selected(
    employee_ids: List[int],
    active_filters: Dict,
    sender_name: str = "Prostech BI",
    additional_cc: Optional[List[str]] = None,
    external_cc: Optional[List[str]] = None,
    override_preferences: bool = False,
    default_lang: str = 'en',
    # Data sources
    sales_df: Optional['pd.DataFrame'] = None,
    backlog_detail_df: Optional['pd.DataFrame'] = None,
    ar_outstanding_df: Optional['pd.DataFrame'] = None,
    targets_df: Optional['pd.DataFrame'] = None,
    # Warning config
    consequences: Optional[List[tuple]] = None,
    deadline_days: int = 7,
) -> NotificationResult:
    """
    Send formal warning email to selected salespeople.

    v3.0: Bilingual (en/vi), categorized alert sections, Excel attachment.

    Args:
        employee_ids:         Selected employee IDs
        active_filters:       Current filter state
        sender_name:          Trigger person name
        additional_cc:        Extra CC emails from employee picker
        external_cc:          External CC emails (typed by user)
        override_preferences: If True, send even to disabled employees
        default_lang:         Default language for email ('en' or 'vi')
        sales_df:             Filtered sales data
        backlog_detail_df:    Backlog detail
        ar_outstanding_df:    AR outstanding
        targets_df:           KPI targets
        consequences:         Custom consequences list
        deadline_days:        Days before consequences take effect

    Returns:
        NotificationResult with per-recipient details
    """
    import os
    import time
    import pandas as pd

    from .email_service import EmailService
    from .email_builder import build_warning_email, build_warning_plain_text
    from .recipient_resolver import resolve_recipients_batch
    from .alert_data_collector import collect_warning_data, generate_warning_excel

    start = time.perf_counter()

    # --- 1. Check email service ---
    svc = EmailService()
    if not svc.is_configured:
        return NotificationResult(
            success=False,
            message="Email not configured. Check EMAIL_SENDER / EMAIL_PASSWORD.",
        )

    if not employee_ids:
        return NotificationResult(success=False, message="No salespeople selected.")

    # --- 2. Resolve recipients ---
    recipients_map = resolve_recipients_batch(employee_ids)
    if not recipients_map:
        return NotificationResult(
            success=False, message="Could not resolve any recipient emails.",
        )

    # --- 3. Dashboard URL ---
    try:
        from utils.config import config
        dashboard_url = config.get_app_setting("APP_BASE_URL", "")
    except Exception:
        dashboard_url = ""

    # --- 4. Preferences (for enabled check + per-employee language) ---
    prefs_cache = {}
    try:
        from .preferences import get_preferences_for_employees
        prefs_cache = get_preferences_for_employees(employee_ids)
    except Exception as e:
        logger.debug(f"Preferences not available: {e}")

    # --- 5. Build combined CC list ---
    combined_extra_cc = list(set(
        (additional_cc or []) + (external_cc or [])
    ))

    # --- 6. Send per-salesperson ---
    details = []
    sent_count = 0
    failed_count = 0
    skipped_count = 0
    temp_files = []  # Track temp Excel files for cleanup

    for eid in employee_ids:
        info = recipients_map.get(eid)

        if not info:
            details.append({
                "employee_id": eid, "status": "skipped",
                "reason": "Employee not found in database",
            })
            skipped_count += 1
            continue

        if not info.has_sales_email:
            details.append({
                "employee_id": eid, "name": info.sales_name,
                "status": "skipped", "reason": "No email address",
            })
            skipped_count += 1
            continue

        # Check preferences (unless override)
        if not override_preferences and prefs_cache:
            master_pref = prefs_cache.get(eid, {}).get('all', {})
            if not master_pref.get('enabled', True):
                details.append({
                    "employee_id": eid, "name": info.sales_name,
                    "status": "skipped", "reason": "Notifications disabled",
                })
                skipped_count += 1
                continue

        # ─── Resolve language (preference > default) ───
        emp_lang = default_lang
        if prefs_cache and eid in prefs_cache:
            emp_lang = prefs_cache[eid].get('all', {}).get('language', default_lang) or default_lang

        # ─── Collect warning data ───
        warning_data = collect_warning_data(
            employee_id=eid,
            employee_name=info.sales_name,
            sales_df=sales_df if sales_df is not None else pd.DataFrame(),
            backlog_detail_df=backlog_detail_df if backlog_detail_df is not None else pd.DataFrame(),
            ar_outstanding_df=ar_outstanding_df if ar_outstanding_df is not None else pd.DataFrame(),
            targets_df=targets_df if targets_df is not None else pd.DataFrame(),
            active_filters=active_filters,
        )

        # ─── Generate Excel attachment ───
        excel_path = None
        try:
            excel_path = generate_warning_excel(
                warning_data=warning_data,
                active_filters=active_filters,
                lang=emp_lang,
            )
            if excel_path:
                temp_files.append(excel_path)
        except Exception as e:
            logger.warning(f"Excel generation failed for {info.sales_name}: {e}")

        # ─── CC list: manager (mandatory) + additional ───
        cc_list = []
        cc_display_list = []
        cc_note_parts = []

        # Manager CC (mandatory)
        if info.has_manager_email:
            cc_list.append(info.manager_email)
            cc_display_list.extend(info.cc_list_named)
            cc_note_parts.append(f"Manager: {info.manager_name}")

        # Additional CC (no display name available — use plain email)
        for cc_email in combined_extra_cc:
            if cc_email not in cc_list and cc_email != info.sales_email:
                cc_list.append(cc_email)
                cc_display_list.append(cc_email)

        cc_note = f"CC: {', '.join(cc_note_parts)}" if cc_note_parts else ""
        if combined_extra_cc:
            cc_note += f" + {len(combined_extra_cc)} additional"

        # ─── Build email (bilingual) ───
        subject, html_body = build_warning_email(
            warning_data=warning_data,
            active_filters=active_filters,
            sender_name=sender_name,
            dashboard_url=dashboard_url,
            cc_note=cc_note,
            consequences=consequences,
            deadline_days=deadline_days,
            lang=emp_lang,
            has_attachment=bool(excel_path),
        )
        plain_text = build_warning_plain_text(warning_data, deadline_days, lang=emp_lang)

        # ─── Send (with Excel attachment if available) ───
        attachments = [excel_path] if excel_path else None
        result = svc.send(
            to=info.to_list,
            subject=subject,
            html=html_body,
            plain_text=plain_text,
            cc=cc_list,
            attachments=attachments,
            to_display=info.to_list_named,
            cc_display=cc_display_list if cc_list else None,
        )

        alert_count = warning_data.get('bulletin', {}).get('alert_count', 0)
        overdue = warning_data.get('ar_summary', {}).get('total_overdue', 0)

        if result.success:
            sent_count += 1
            details.append({
                "employee_id": eid, "name": info.sales_name,
                "status": "sent", "to": info.sales_email,
                "cc": ", ".join(cc_list) if cc_list else None,
                "alerts": alert_count, "overdue": overdue,
                "subject": subject, "lang": emp_lang,
                "has_excel": bool(excel_path),
                "elapsed": result.elapsed_seconds,
            })
        else:
            failed_count += 1
            details.append({
                "employee_id": eid, "name": info.sales_name,
                "status": "failed", "to": info.sales_email,
                "error": result.message,
            })

        # Rate limit
        if len(employee_ids) > 1:
            time.sleep(0.5)

    elapsed = round(time.perf_counter() - start, 2)

    # --- 7. Cleanup temp Excel files ---
    for tmp_path in temp_files:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    # --- 8. Audit log ---
    try:
        from .send_log import log_send_batch
        triggered_by_id = None
        try:
            import streamlit as _st
            triggered_by_id = _st.session_state.get('employee_id')
        except Exception:
            pass
        # Mark as 'warning' type in log
        for d in details:
            d['alert_type'] = 'warning'
        log_send_batch(details, triggered_by=triggered_by_id)
    except Exception as e:
        logger.debug(f"Could not write send log: {e}")

    # --- 9. Summary ---
    if sent_count > 0 and failed_count == 0:
        msg = f"✅ Warning sent to {sent_count} salesperson(s)"
        if skipped_count:
            msg += f" ({skipped_count} skipped)"
        success = True
    elif sent_count > 0:
        msg = f"⚠️ Sent: {sent_count}, Failed: {failed_count}, Skipped: {skipped_count}"
        success = True
    else:
        msg = f"❌ All failed. Failed: {failed_count}, Skipped: {skipped_count}"
        success = False

    logger.info(f"Warning notification: {msg} ({elapsed}s)")

    return NotificationResult(
        success=success, message=msg,
        sent_count=sent_count, failed_count=failed_count,
        skipped_count=skipped_count, details=details,
        elapsed_seconds=elapsed,
    )