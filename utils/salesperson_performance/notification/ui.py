# utils/salesperson_performance/notification/ui.py
"""
Notification UI — Streamlit components for sending bulletin emails.

Provides:
- render_email_bulletin_button(): Button below the warning bulletin
- _email_bulletin_dialog(): Preview + send dialog (st.dialog)

Integration in 1___Salesperson_Performance.py:
    from utils.salesperson_performance.notification.ui import render_email_bulletin_button

    # Inside tab1 (Overview), after render_warning_bulletin():
    render_email_bulletin_button(
        bulletin=warning_bulletin,
        active_filters=active_filters,
        overview_metrics=overview_metrics,
        employee_ids=active_filters['employee_ids'],
    )

VERSION: 1.0.0
"""

import logging
from typing import Dict, List, Optional
import streamlit as st
import pandas as pd

logger = logging.getLogger(__name__)


# =============================================================================
# PUBLIC API
# =============================================================================

def render_email_bulletin_button(
    bulletin: Dict,
    active_filters: Dict,
    overview_metrics: Optional[Dict] = None,
    employee_ids: Optional[List[int]] = None,
    key_prefix: str = "bulletin_email",
):
    """
    Render the "📧 Email Bulletin" button below the warning bulletin.

    When clicked, opens a preview dialog with recipient list and send button.

    Args:
        bulletin:         Output of generate_warning_bulletin()
        active_filters:   Current filter state
        overview_metrics: Overview metrics for KPI snapshot in email
        employee_ids:     Salesperson IDs to notify (from current filter selection)
        key_prefix:       Unique key prefix for Streamlit widgets
    """
    from .email_service import EmailService

    # Check if email is configured
    svc = EmailService()
    if not svc.is_configured:
        # Don't show button if email not configured
        return

    # Store data in session_state for the dialog (st.dialog can't receive args)
    def _open_dialog():
        st.session_state[f"{key_prefix}_bulletin"] = bulletin
        st.session_state[f"{key_prefix}_filters"] = active_filters
        st.session_state[f"{key_prefix}_metrics"] = overview_metrics
        st.session_state[f"{key_prefix}_employee_ids"] = employee_ids or []
        st.session_state[f"{key_prefix}_open"] = True

    # Render button row
    col_btn, col_info = st.columns([1, 4])
    with col_btn:
        if st.button(
            "📧 Email Bulletin",
            key=f"{key_prefix}_btn",
            help="Send this bulletin via email to selected salespeople and their managers",
            use_container_width=True,
        ):
            _open_dialog()

    with col_info:
        alert_count = bulletin.get("alert_count", 0)
        if alert_count > 0:
            st.caption(
                f"Send {alert_count} alert(s) to "
                f"{len(employee_ids or [])} salesperson(s) via email"
            )
        else:
            st.caption("Send bulletin summary via email")

    # Render dialog if open
    if st.session_state.get(f"{key_prefix}_open", False):
        _render_email_dialog(key_prefix)


def _render_email_dialog(key_prefix: str):
    """
    Render the email preview + send dialog.

    Uses st.dialog decorator pattern via a contained expander
    (st.dialog requires @st.dialog decorator which doesn't support
    dynamic data well, so we use an expander-based approach instead).
    """
    from .recipient_resolver import resolve_all_selected_recipients
    from .email_builder import build_bulletin_email, build_bulletin_plain_text
    from .notification_sender import send_bulletin_to_team

    # Retrieve data from session_state
    bulletin = st.session_state.get(f"{key_prefix}_bulletin", {})
    active_filters = st.session_state.get(f"{key_prefix}_filters", {})
    overview_metrics = st.session_state.get(f"{key_prefix}_metrics")
    employee_ids = st.session_state.get(f"{key_prefix}_employee_ids", [])

    with st.expander("📧 **Email Bulletin — Preview & Send**", expanded=True):
        # Close button
        col_spacer, col_close = st.columns([8, 1])
        with col_close:
            if st.button("✕", key=f"{key_prefix}_close", help="Close"):
                st.session_state[f"{key_prefix}_open"] = False
                st.rerun()

        if not employee_ids:
            st.warning("No salespeople selected. Adjust sidebar filters to select recipients.")
            return

        # --- Resolve recipients ---
        with st.spinner("Resolving recipients..."):
            resolved = resolve_all_selected_recipients(employee_ids)

        to_emails = resolved["to_emails"]
        cc_emails = resolved["cc_emails"]
        missing = resolved["missing_email"]

        # --- Recipients section ---
        st.markdown("##### 📬 Recipients")

        col_to, col_cc = st.columns(2)
        with col_to:
            st.markdown(f"**To** ({len(to_emails)} salesperson{'s' if len(to_emails) != 1 else ''})")
            if to_emails:
                for email in to_emails:
                    st.markdown(f"- `{email}`")
            else:
                st.warning("No valid email addresses found")

        with col_cc:
            cc_managers = st.checkbox(
                f"CC Managers ({len(cc_emails)})",
                value=True,
                key=f"{key_prefix}_cc_managers",
            )
            if cc_managers and cc_emails:
                for email in cc_emails:
                    st.markdown(f"- `{email}`")
            elif not cc_emails:
                st.caption("No manager emails found")

        if missing:
            st.warning(f"⚠️ Missing email for: {', '.join(missing)}")

        st.divider()

        # --- Preview section ---
        st.markdown("##### 👁️ Email Preview")

        # Build preview
        sender_name = st.session_state.get("user_fullname", "Prostech BI")
        subject, html_preview = build_bulletin_email(
            bulletin=bulletin,
            active_filters=active_filters,
            overview_metrics=overview_metrics,
            sender_name=sender_name,
        )

        st.markdown(f"**Subject:** `{subject}`")

        with st.container(height=350, border=True):
            st.html(html_preview)

        st.divider()

        # --- Send section ---
        col_send, col_status = st.columns([1, 3])

        with col_send:
            can_send = len(to_emails) > 0
            send_clicked = st.button(
                "📤 Send Now",
                key=f"{key_prefix}_send",
                type="primary",
                disabled=not can_send,
                use_container_width=True,
            )

        with col_status:
            if not can_send:
                st.caption("No valid recipients to send to.")

        # --- Handle send ---
        if send_clicked and can_send:
            with st.spinner(f"Sending to {len(to_emails)} recipient(s)..."):
                result = send_bulletin_to_team(
                    bulletin=bulletin,
                    employee_ids=employee_ids,
                    active_filters=active_filters,
                    overview_metrics=overview_metrics,
                    sender_name=sender_name,
                    cc_managers=cc_managers,
                )

            # Show result
            if result.success:
                st.success(result.message)
            else:
                st.error(result.message)

            # Show details
            if result.details:
                with st.expander(
                    f"📋 Send Details ({result.sent_count} sent, "
                    f"{result.failed_count} failed, "
                    f"{result.skipped_count} skipped)",
                    expanded=result.failed_count > 0,
                ):
                    for d in result.details:
                        status = d.get("status", "unknown")
                        name = d.get("name", f"ID #{d.get('employee_id', '?')}")
                        if status == "sent":
                            st.markdown(
                                f"✅ **{name}** → `{d.get('to', '')}` "
                                f"{'(CC: ' + d['cc'] + ')' if d.get('cc') else ''}"
                            )
                        elif status == "failed":
                            st.markdown(f"❌ **{name}** → {d.get('error', 'Unknown error')}")
                        elif status == "skipped":
                            st.markdown(f"⏭️ **{name}** — {d.get('reason', 'Skipped')}")

                    st.caption(f"Total time: {result.elapsed_seconds}s")

            # Close dialog after successful send
            if result.success and result.failed_count == 0:
                st.session_state[f"{key_prefix}_open"] = False
