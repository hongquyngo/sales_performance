# utils/salesperson_performance/notification/__init__.py
"""
Email Notification Module for Salesperson Performance.

Phase 1: Ad-hoc bulletin email — send warning bulletin from UI.
Phase 2: Per-salesperson individualized alerts.
Phase 3: Notification preferences + send log + setup UI.
Phase 4 (future): Scheduled weekly alerts via standalone script.

Components:
- email_service:         SMTP sender using shared config credentials
- email_builder:         HTML email template for bulletin
- alert_data_collector:  Per-employee data filtering (zero SQL)
- recipient_resolver:    Lookup sales + manager emails from employees table
- notification_sender:   Orchestrator (resolve → check prefs → build → send → log)
- preferences:           CRUD for notification_preferences table
- send_log:              Write/read notification_log for audit trail
- ui:                    Streamlit UI (button + preview dialog)
- setup_ui:              Setup tab sub-section (preferences + history + test send)

VERSION: 2.0.0
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

# Phase 3: Setup UI, Preferences, Send Log
from .preferences import (
    get_preferences_for_employees,
    save_preference,
    save_preferences_bulk,
    is_notification_enabled,
    ALERT_TYPES,
    FREQUENCY_OPTIONS,
)
from .send_log import log_send, get_send_history, get_send_stats
from .setup_ui import render_notification_setup

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
    # Phase 3: Setup UI, Preferences, Send Log
    "render_notification_setup",
    "get_preferences_for_employees",
    "save_preference",
    "save_preferences_bulk",
    "is_notification_enabled",
    "ALERT_TYPES",
    "FREQUENCY_OPTIONS",
    "log_send",
    "get_send_history",
    "get_send_stats",
]

__version__ = "2.0.0"