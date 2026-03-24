# utils/salesperson_performance/notification/setup_ui.py
"""
Notification Setup UI — Standalone tab for email notifications.

Renders:
1. ⚙️ Preferences: Per-salesperson toggle grid (enabled/frequency/CC manager)
2. 📋 Send History: Recent notification log with stats
3. 🧪 Test Send: Send test email to verify configuration

Integration: Rendered in tab7 (📧 Notifications) of main page.

Usage:
    from utils.salesperson_performance.notification.setup_ui import (
        render_notification_setup,
    )

    with tab7:
        render_notification_setup(
            employee_ids=active_filters.get('employee_ids') or [],
            access_level=access.get_access_level(),
        )

VERSION: 1.0.0
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional
import streamlit as st
import pandas as pd

logger = logging.getLogger(__name__)


# =============================================================================
# PUBLIC API
# =============================================================================

def render_notification_setup(
    employee_ids: List[int],
    access_level: str = "self",
    key_prefix: str = "notif_setup",
):
    """
    Render notification setup section.

    Args:
        employee_ids: Accessible employee IDs (from filter/access control)
        access_level: 'full', 'team', or 'self'
        key_prefix:   Unique key prefix for widgets
    """
    from .email_service import EmailService

    st.subheader("📧 Email Notifications")
    st.caption("Manage notification preferences, view send history, and test email configuration.")

    # --- Check email configuration ---
    svc = EmailService()
    if not svc.is_configured:
        st.warning(
            "⚠️ **Email not configured.** "
            "Set `EMAIL_SENDER` and `EMAIL_PASSWORD` in `.env` or Streamlit secrets."
        )
        return

    st.caption(f"Sender: `{svc.sender_address}`")
    st.divider()

    # Sub-tabs
    pref_tab, log_tab, test_tab = st.tabs([
        "⚙️ Preferences",
        "📋 Send History",
        "🧪 Test Send",
    ])

    with pref_tab:
        _render_preferences_tab(employee_ids, access_level, key_prefix)

    with log_tab:
        _render_send_history_tab(employee_ids, key_prefix)

    with test_tab:
        _render_test_send_tab(key_prefix)


# =============================================================================
# TAB 1: PREFERENCES
# =============================================================================

def _render_preferences_tab(
    employee_ids: List[int],
    access_level: str,
    key_prefix: str,
):
    """Render notification preferences editor."""
    from .preferences import (
        get_preferences_for_employees,
        save_preferences_bulk,
        ALERT_TYPES,
        FREQUENCY_OPTIONS,
    )
    from .recipient_resolver import resolve_recipients_batch

    if not employee_ids:
        st.info("No salespeople selected. Adjust sidebar filters to manage preferences.")
        return

    # Resolve names
    recipients = resolve_recipients_batch(employee_ids)

    # Load current preferences
    all_prefs = get_preferences_for_employees(employee_ids)

    can_edit = access_level in ('full', 'team')

    st.markdown(f"**{len(employee_ids)} salesperson(s)** — "
                f"{'Edit' if can_edit else 'View'} notification preferences")

    if not can_edit:
        st.info("🔒 Read-only — contact your manager to change notification settings.")

    # --- Per-salesperson editor ---
    for eid in employee_ids:
        info = recipients.get(eid)
        name = info.sales_name if info else f"Employee #{eid}"
        email = info.sales_email if info and info.has_sales_email else "⚠️ no email"
        mgr = info.manager_name if info and info.manager_name else "—"

        prefs = all_prefs.get(eid, {})

        with st.expander(f"👤 {name} ({email})", expanded=(len(employee_ids) == 1)):
            st.caption(f"Manager: {mgr}")

            # Master switch
            master_pref = prefs.get('all', {'enabled': True, 'frequency': 'weekly', 'notify_manager': True})

            col_master, col_freq, col_cc = st.columns([2, 2, 1])

            with col_master:
                master_enabled = st.toggle(
                    "📧 Notifications Enabled",
                    value=master_pref['enabled'],
                    key=f"{key_prefix}_{eid}_master",
                    disabled=not can_edit,
                )

            with col_freq:
                freq_options = list(FREQUENCY_OPTIONS.keys())
                freq_labels = list(FREQUENCY_OPTIONS.values())
                current_freq = master_pref.get('frequency', 'weekly')
                freq_idx = freq_options.index(current_freq) if current_freq in freq_options else 0
                selected_freq = st.selectbox(
                    "Frequency",
                    options=freq_options,
                    format_func=lambda x: FREQUENCY_OPTIONS[x],
                    index=freq_idx,
                    key=f"{key_prefix}_{eid}_freq",
                    disabled=not can_edit or not master_enabled,
                )

            with col_cc:
                cc_mgr = st.checkbox(
                    "CC Manager",
                    value=master_pref.get('notify_manager', True),
                    key=f"{key_prefix}_{eid}_cc",
                    disabled=not can_edit or not master_enabled,
                )

            # Per-alert-type toggles (skip 'all')
            if master_enabled:
                st.markdown("**Alert types:**")
                alert_cols = st.columns(2)
                alert_types_list = [(k, v) for k, v in ALERT_TYPES.items() if k != 'all']

                for idx, (atype, ainfo) in enumerate(alert_types_list):
                    type_pref = prefs.get(atype, {'enabled': True})
                    with alert_cols[idx % 2]:
                        st.checkbox(
                            f"{ainfo['label']}",
                            value=type_pref.get('enabled', True),
                            key=f"{key_prefix}_{eid}_{atype}",
                            help=ainfo['description'],
                            disabled=not can_edit,
                        )

            # Save button
            if can_edit:
                if st.button(
                    "💾 Save",
                    key=f"{key_prefix}_{eid}_save",
                    use_container_width=True,
                ):
                    # Collect current widget state
                    new_prefs = {
                        'all': {
                            'enabled': master_enabled,
                            'frequency': selected_freq,
                            'notify_manager': cc_mgr,
                        },
                    }
                    for atype, _ in [(k, v) for k, v in ALERT_TYPES.items() if k != 'all']:
                        widget_val = st.session_state.get(f"{key_prefix}_{eid}_{atype}", True)
                        new_prefs[atype] = {
                            'enabled': widget_val if master_enabled else False,
                            'frequency': selected_freq,
                            'notify_manager': cc_mgr,
                        }

                    modifier_id = st.session_state.get('employee_id')
                    saved = save_preferences_bulk(eid, new_prefs, modified_by=modifier_id)
                    st.success(f"✅ Saved {saved} preference(s) for {name}")


# =============================================================================
# TAB 2: SEND HISTORY
# =============================================================================

def _render_send_history_tab(employee_ids: List[int], key_prefix: str):
    """Render notification send history."""
    from .send_log import get_send_history, get_send_stats

    # Stats cards
    stats = get_send_stats(days=30)

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("📧 Total Sent", stats['sent'])
    with col2:
        st.metric("❌ Failed", stats['failed'])
    with col3:
        st.metric("⏭️ Skipped", stats['skipped'])
    with col4:
        st.metric("👥 Recipients", stats['unique_recipients'])
    with col5:
        last = stats.get('last_sent_at')
        if last:
            st.metric("🕐 Last Sent", pd.Timestamp(last).strftime('%d %b %H:%M'))
        else:
            st.metric("🕐 Last Sent", "Never")

    st.caption("Last 30 days")

    st.divider()

    # History table
    col_filter, col_days = st.columns([3, 1])
    with col_days:
        days = st.selectbox(
            "Period",
            options=[7, 14, 30, 90],
            index=2,
            format_func=lambda x: f"Last {x} days",
            key=f"{key_prefix}_log_days",
        )

    history_df = get_send_history(
        employee_ids=employee_ids if employee_ids else None,
        days=days,
    )

    if history_df.empty:
        st.info("No notification history found.")
        return

    # Format for display
    display_df = history_df[[
        'sent_at', 'employee_name', 'to_email', 'cc_email',
        'alert_count', 'status', 'trigger_type',
    ]].copy()

    display_df['sent_at'] = pd.to_datetime(display_df['sent_at']).dt.strftime('%Y-%m-%d %H:%M')

    display_df.columns = [
        'Sent At', 'Salesperson', 'To', 'CC',
        'Alerts', 'Status', 'Trigger',
    ]

    # Color status
    def _color_status(val):
        colors = {'sent': '#28a745', 'failed': '#dc3545', 'skipped': '#6c757d'}
        color = colors.get(val, '#333')
        return f'color: {color}; font-weight: 600'

    st.dataframe(
        display_df.style.map(_color_status, subset=['Status']),
        width="stretch",
        hide_index=True,
        height=min(400, 40 + len(display_df) * 35),
    )


# =============================================================================
# TAB 3: TEST SEND
# =============================================================================

def _render_test_send_tab(key_prefix: str):
    """Render test send section."""
    from .email_service import EmailService
    from .email_builder import build_bulletin_email

    st.markdown("#### 🧪 Test Email Configuration")
    st.caption("Send a test email to verify SMTP settings are working.")

    svc = EmailService()

    # Determine default test recipient
    user_email = st.session_state.get('user_email', '')

    col_email, col_btn = st.columns([3, 1])
    with col_email:
        test_email = st.text_input(
            "Send test to",
            value=user_email,
            placeholder="your.email@company.com",
            key=f"{key_prefix}_test_email",
        )
    with col_btn:
        st.markdown("")  # spacer
        test_clicked = st.button(
            "📤 Send Test",
            key=f"{key_prefix}_test_btn",
            type="primary",
            disabled=not test_email or '@' not in test_email,
            use_container_width=True,
        )

    if test_clicked and test_email:
        # Build a sample bulletin
        sample_bulletin = {
            'headline': 'This is a test email from Prostech BI Dashboard',
            'alerts': [
                {'severity': 'high', 'icon': '🔴', 'message': 'Sample critical alert — backlog past ETD'},
                {'severity': 'medium', 'icon': '🟡', 'message': 'Sample warning — KPI behind target'},
                {'severity': 'low', 'icon': '🔵', 'message': 'Sample info — 2 invoices coming due this week'},
            ],
            'alert_count': 3,
            'has_critical': True,
            'period_label': '🧪 Test Email',
        }
        sample_metrics = {
            'total_revenue': 123456,
            'total_gp': 34567,
            'total_gp1': 31000,
            'gp_percent': 28.0,
            'total_invoices': 42,
            'total_customers': 15,
        }

        try:
            from utils.config import config
            dashboard_url = config.get_app_setting("APP_BASE_URL", "")
        except Exception:
            dashboard_url = ""

        subject, html = build_bulletin_email(
            bulletin=sample_bulletin,
            active_filters={'period_type': 'YTD', 'year': 2026},
            overview_metrics=sample_metrics,
            sender_name=st.session_state.get('user_fullname', 'Test'),
            dashboard_url=dashboard_url,
        )

        with st.spinner(f"Sending test to {test_email}..."):
            result = svc.send(
                to=[test_email],
                subject=f"🧪 TEST — {subject}",
                html=html,
            )

        if result.success:
            st.success(f"✅ Test email sent to `{test_email}` ({result.elapsed_seconds}s)")
        else:
            st.error(f"❌ Failed: {result.message}")

    # Show current config
    with st.expander("🔧 SMTP Configuration", expanded=False):
        st.markdown(f"""
        | Setting | Value |
        |---------|-------|
        | Sender | `{svc.sender_address}` |
        | SMTP Host | `{svc._smtp_host}` |
        | SMTP Port | `{svc._smtp_port}` |
        | Configured | {'✅ Yes' if svc.is_configured else '❌ No'} |
        """)

        if st.session_state.get('user_role') == 'admin':
            try:
                from utils.config import config
                url = config.get_app_setting("APP_BASE_URL", "")
                st.markdown(f"| APP_BASE_URL | `{url or '(not set)'}` |")
            except Exception:
                pass
