# utils/salesperson_performance/notification/__init__.py
"""
Email Notification Module for Salesperson Performance.

Phase 1: Ad-hoc bulletin email — send warning bulletin from UI.
Phase 2 (future): Per-salesperson individualized alerts.
Phase 3 (future): Notification preferences + audit log UI.
Phase 4 (future): Scheduled weekly alerts via standalone script.

Components:
- email_service:       SMTP sender using shared config credentials
- email_builder:       HTML email template for bulletin
- recipient_resolver:  Lookup sales + manager emails from employees table
- notification_sender: Orchestrator (resolve → build → send)
- ui:                  Streamlit UI (button + preview dialog)

Usage (in main page):
    from utils.salesperson_performance.notification.ui import render_email_bulletin_button

    render_email_bulletin_button(
        bulletin=warning_bulletin,
        active_filters=active_filters,
        overview_metrics=overview_metrics,
        employee_ids=active_filters['employee_ids'],
    )

VERSION: 1.0.0
"""

from .email_service import EmailService, EmailResult
from .email_builder import build_bulletin_email, build_bulletin_plain_text
from .alert_data_collector import collect_per_employee_bulletin
from .recipient_resolver import (
    RecipientInfo,
    resolve_recipients,
    resolve_recipients_batch,
    resolve_all_selected_recipients,
)
from .notification_sender import send_bulletin_to_team, NotificationResult
from .ui import render_email_bulletin_button

__all__ = [
    # Email service
    "EmailService",
    "EmailResult",
    # Email builder
    "build_bulletin_email",
    "build_bulletin_plain_text",
    # Alert data collector
    "collect_per_employee_bulletin",
    # Recipient resolver
    "RecipientInfo",
    "resolve_recipients",
    "resolve_recipients_batch",
    "resolve_all_selected_recipients",
    # Notification sender
    "send_bulletin_to_team",
    "NotificationResult",
    # UI
    "render_email_bulletin_button",
]

__version__ = "1.0.0"