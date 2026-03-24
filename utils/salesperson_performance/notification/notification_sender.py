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
) -> NotificationResult:
    """
    Send the warning bulletin email to selected salespeople (+ their managers).

    Phase 1 approach: One email per salesperson, same bulletin content,
    CC to their direct manager.

    Args:
        bulletin:         Output of generate_warning_bulletin()
        employee_ids:     List of salesperson employee IDs to notify
        active_filters:   Current filter state
        overview_metrics: Overview metrics dict for KPI snapshot
        sender_name:      Name of the person triggering the send
        cc_managers:       Whether to CC direct managers

    Returns:
        NotificationResult with per-recipient details
    """
    import time

    # Lazy imports to avoid circular imports at module load
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

    # --- 4. Build email content (shared for all recipients in Phase 1) ---
    subject, html_body = build_bulletin_email(
        bulletin=bulletin,
        active_filters=active_filters,
        overview_metrics=overview_metrics,
        sender_name=sender_name,
        dashboard_url=dashboard_url,
    )
    plain_text = build_bulletin_plain_text(bulletin)

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

        # Build CC note for manager
        cc_note = ""
        cc_list = []
        if cc_managers and info.has_manager_email:
            cc_list = info.cc_list
            cc_note = f"This alert was also sent to {info.sales_name} (your direct report)."

        # Personalize subject with name if sending individually
        personal_subject = f"{subject} — {info.sales_name}"

        # Build personalized HTML (add CC note for manager copy)
        if cc_note:
            personal_html = html_body  # manager CC note added via builder
            # Re-build with cc_note for the manager's benefit
            personal_subject_text, personal_html = build_bulletin_email(
                bulletin=bulletin,
                active_filters=active_filters,
                overview_metrics=overview_metrics,
                sender_name=sender_name,
                dashboard_url=dashboard_url,
                cc_note=cc_note if cc_managers else "",
            )
            personal_subject = f"{personal_subject_text} — {info.sales_name}"
        else:
            personal_html = html_body

        # Send
        result = svc.send(
            to=info.to_list,
            subject=personal_subject,
            html=personal_html,
            plain_text=plain_text,
            cc=cc_list,
        )

        if result.success:
            sent_count += 1
            details.append({
                "employee_id": eid,
                "name": info.sales_name,
                "status": "sent",
                "to": info.sales_email,
                "cc": info.manager_email if cc_list else None,
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

    # --- 6. Build summary ---
    if sent_count > 0 and failed_count == 0:
        success = True
        msg = f"✅ Bulletin sent to {sent_count} salesperson(s)"
        if skipped_count:
            msg += f" ({skipped_count} skipped — no email)"
    elif sent_count > 0 and failed_count > 0:
        success = True  # partial success
        msg = f"⚠️ Sent: {sent_count}, Failed: {failed_count}, Skipped: {skipped_count}"
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
