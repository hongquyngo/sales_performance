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
    # Per-employee data sources (for individualized emails)
    sales_df: Optional[pd.DataFrame] = None,
    backlog_detail_df: Optional[pd.DataFrame] = None,
    ar_outstanding_df: Optional[pd.DataFrame] = None,
    targets_df: Optional[pd.DataFrame] = None,
):
    """
    Render the "📧 Email Bulletin" button below the warning bulletin.

    When clicked, opens a preview dialog with recipient list and send button.
    Each salesperson receives individualized email with their own data.

    Args:
        bulletin:           Output of generate_warning_bulletin() (team-level fallback)
        active_filters:     Current filter state
        overview_metrics:   Team-level overview metrics (fallback)
        employee_ids:       Salesperson IDs to notify
        key_prefix:         Unique key prefix for Streamlit widgets
        sales_df:           Filtered sales data (all employees)
        backlog_detail_df:  Backlog detail (all employees)
        ar_outstanding_df:  AR outstanding (all employees)
        targets_df:         KPI targets (all employees)
    """
    from .email_service import EmailService

    # Check if email is configured
    svc = EmailService()
    if not svc.is_configured:
        return

    # Store data in session_state for the dialog
    def _open_dialog():
        st.session_state[f"{key_prefix}_bulletin"] = bulletin
        st.session_state[f"{key_prefix}_filters"] = active_filters
        st.session_state[f"{key_prefix}_metrics"] = overview_metrics
        st.session_state[f"{key_prefix}_employee_ids"] = employee_ids or []
        st.session_state[f"{key_prefix}_sales_df"] = sales_df
        st.session_state[f"{key_prefix}_backlog_df"] = backlog_detail_df
        st.session_state[f"{key_prefix}_ar_df"] = ar_outstanding_df
        st.session_state[f"{key_prefix}_targets_df"] = targets_df
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
    sales_df = st.session_state.get(f"{key_prefix}_sales_df")
    backlog_detail_df = st.session_state.get(f"{key_prefix}_backlog_df")
    ar_outstanding_df = st.session_state.get(f"{key_prefix}_ar_df")
    targets_df = st.session_state.get(f"{key_prefix}_targets_df")

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

        # Build preview — show sample for first employee (individualized)
        sender_name = st.session_state.get("user_fullname", "Prostech BI")
        has_per_employee = sales_df is not None and not sales_df.empty

        if has_per_employee and employee_ids:
            from .alert_data_collector import collect_per_employee_bulletin
            # Preview for first employee
            first_eid = employee_ids[0]
            first_info = resolved["recipients"].get(first_eid)
            first_name = first_info.sales_name if first_info else f"Employee #{first_eid}"

            preview_bulletin, preview_metrics = collect_per_employee_bulletin(
                employee_id=first_eid,
                employee_name=first_name,
                sales_df=sales_df,
                backlog_detail_df=backlog_detail_df if backlog_detail_df is not None else pd.DataFrame(),
                ar_outstanding_df=ar_outstanding_df if ar_outstanding_df is not None else pd.DataFrame(),
                targets_df=targets_df if targets_df is not None else pd.DataFrame(),
                active_filters=active_filters,
            )
            st.info(
                f"📧 **Individualized emails** — each salesperson receives their own data. "
                f"Preview below shows sample for **{first_name}**."
            )
        else:
            preview_bulletin = bulletin
            preview_metrics = overview_metrics
            st.caption("Preview shows team-level bulletin (no per-employee data available)")

        subject, html_preview = build_bulletin_email(
            bulletin=preview_bulletin,
            active_filters=active_filters,
            overview_metrics=preview_metrics,
            sender_name=sender_name,
        )

        st.markdown(f"**Subject:** `{subject}`")

        with st.container(height=400, border=True):
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
            with st.spinner(f"Sending individualized emails to {len(to_emails)} recipient(s)..."):
                result = send_bulletin_to_team(
                    bulletin=bulletin,
                    employee_ids=employee_ids,
                    active_filters=active_filters,
                    overview_metrics=overview_metrics,
                    sender_name=sender_name,
                    cc_managers=cc_managers,
                    # Per-employee data
                    sales_df=sales_df,
                    backlog_detail_df=backlog_detail_df,
                    ar_outstanding_df=ar_outstanding_df,
                    targets_df=targets_df,
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