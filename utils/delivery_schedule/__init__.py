# utils/delivery_schedule/__init__.py
"""Delivery Schedule modules — all page logic lives here"""

# Data & services
from .data_loader import DeliveryDataLoader
from .email_sender import EmailSender
from .calendar_utils import CalendarEventGenerator
from .client_filters import needs_completed_data, apply_client_filters
from .fulfillment import calculate_fulfillment

# UI fragments
from .filters import create_filter_section
from .metrics import display_metrics
from .pivot import display_pivot_table
from .detailed_list import display_detailed_list
from .alerts import display_overdue_alert
from .email_notifications import display_email_notifications
from .user_guide import render_user_guide

__all__ = [
    # Data & services
    'DeliveryDataLoader',
    'EmailSender',
    'CalendarEventGenerator',
    'needs_completed_data',
    'apply_client_filters',
    'calculate_fulfillment',
    # UI
    'create_filter_section',
    'display_metrics',
    'display_pivot_table',
    'display_detailed_list',
    'display_overdue_alert',
    'display_email_notifications',
    'render_user_guide',
]