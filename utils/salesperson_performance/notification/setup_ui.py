# utils/salesperson_performance/notification/setup_ui.py
"""
Notification Setup UI — Full-featured tab for email notifications.

3 sub-tabs:
1. 📨 Send Warning — select recipients, configure CC, preview & send
2. ⚙️ Preferences — per-salesperson notification settings
3. 📋 Send History — audit trail with stats

VERSION: 3.0.0

CHANGELOG:
- v3.0.0: Complete rewrite
          - NEW "📨 Send Warning" tab (primary action)
            - Recipient table with real-time AR/alert data
            - Mandatory manager CC + additional CC picker + external CC
            - Warning email template with AR aging, customer risk, consequences
          - Removed 🧪 Test Send tab (email stable)
          - @st.fragment isolation (no full page rerun)
          - All SQL reads cached
- v2.0.0: Added @st.fragment, cached reads, is_email_configured()
- v1.0.0: Initial — preferences + history + test send
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
    # Data for Send Warning (NEW v3.0)
    active_filters: Optional[Dict] = None,
    sales_df: Optional[pd.DataFrame] = None,
    backlog_detail_df: Optional[pd.DataFrame] = None,
    ar_outstanding_df: Optional[pd.DataFrame] = None,
    targets_df: Optional[pd.DataFrame] = None,
):
    """
    Render notification setup section.

    Public API — delegates to @st.fragment for isolation.
    """
    _render_notification_setup_fragment(
        employee_ids, access_level, key_prefix,
        active_filters, sales_df, backlog_detail_df,
        ar_outstanding_df, targets_df,
    )


@st.fragment
def _render_notification_setup_fragment(
    employee_ids: List[int],
    access_level: str,
    key_prefix: str,
    active_filters: Optional[Dict],
    sales_df: Optional[pd.DataFrame],
    backlog_detail_df: Optional[pd.DataFrame],
    ar_outstanding_df: Optional[pd.DataFrame],
    targets_df: Optional[pd.DataFrame],
):
    """Internal fragment — isolated from full page rerun."""
    from .email_service import is_email_configured

    st.subheader("📧 Email Notifications")
    st.caption("Send warnings, manage preferences, and view notification history.")

    if not is_email_configured():
        st.warning(
            "⚠️ **Email not configured.** "
            "Set `EMAIL_SENDER` and `EMAIL_PASSWORD` in `.env` or Streamlit secrets."
        )
        return

    # Show sender
    try:
        from utils.config import config
        email_cfg = config.get_email_config("outbound")
        sender_addr = email_cfg.get("sender", "")
        if sender_addr:
            st.caption(f"Sender: `{sender_addr}`")
    except Exception:
        pass

    st.divider()

    # 3 sub-tabs
    warning_tab, pref_tab, log_tab = st.tabs([
        "📨 Send Warning",
        "⚙️ Preferences",
        "📋 Send History",
    ])

    with warning_tab:
        _render_send_warning_tab(
            employee_ids, active_filters or {},
            sales_df, backlog_detail_df, ar_outstanding_df, targets_df,
            key_prefix,
        )

    with pref_tab:
        _render_preferences_tab(employee_ids, access_level, key_prefix)

    with log_tab:
        _render_send_history_tab(employee_ids, key_prefix)


# =============================================================================
# TAB 1: 📨 SEND WARNING
# =============================================================================

def _render_send_warning_tab(
    employee_ids: List[int],
    active_filters: Dict,
    sales_df: Optional[pd.DataFrame],
    backlog_detail_df: Optional[pd.DataFrame],
    ar_outstanding_df: Optional[pd.DataFrame],
    targets_df: Optional[pd.DataFrame],
    key_prefix: str,
):
    """Render Send Warning tab with recipient selection, CC config, and send."""
    from .alert_data_collector import collect_recipients_warning_summary, collect_warning_data
    from .email_builder import build_warning_email
    from .notification_sender import send_warning_to_selected
    from .preferences import get_preferences_for_employees
    from .recipient_resolver import resolve_recipients_batch, get_all_employees_with_email

    if not employee_ids:
        st.info("No salespeople in current filter. Adjust sidebar filters.")
        return

    has_data = (
        sales_df is not None and not sales_df.empty
        and ar_outstanding_df is not None
    )

    if not has_data:
        st.warning("Data not available. Navigate to other tabs first to load data.")
        return

    # ─────────────────────────────────────────────────────────────
    # PANEL A: RECIPIENT SELECTION
    # ─────────────────────────────────────────────────────────────
    st.markdown("##### 👥 Select Recipients")

    # Load preferences for enabled/disabled status
    prefs_cache = {}
    try:
        prefs_cache = get_preferences_for_employees(employee_ids)
    except Exception:
        pass

    # Build summary table (cached via inner functions)
    with st.spinner("Analyzing alerts..."):
        summary_df = collect_recipients_warning_summary(
            employee_ids=employee_ids,
            ar_outstanding_df=ar_outstanding_df if ar_outstanding_df is not None else pd.DataFrame(),
            sales_df=sales_df if sales_df is not None else pd.DataFrame(),
            backlog_detail_df=backlog_detail_df if backlog_detail_df is not None else pd.DataFrame(),
            targets_df=targets_df if targets_df is not None else pd.DataFrame(),
            active_filters=active_filters,
            prefs_cache=prefs_cache,
        )

    if summary_df.empty:
        st.info("No recipient data available.")
        return

    # ─── Quick filter buttons ───
    # Pattern: delete checkbox widget keys → rerun → checkbox re-creates
    # fresh using value= from _sel_target list
    all_eids = summary_df['employee_id'].tolist()
    _sel_key = f"{key_prefix}_sel_target"

    # Default target (first render): those with issues
    _default_ids = summary_df[
        (summary_df['overdue_amount'] > 0) | (summary_df['alert_count'] > 0)
    ]['employee_id'].tolist()

    def _apply_selection(target_ids: list):
        """Delete all checkbox keys → set target → rerun."""
        st.session_state[_sel_key] = target_ids
        for eid in all_eids:
            st.session_state.pop(f"{key_prefix}_chk_{eid}", None)
        st.rerun(scope="fragment")

    col_btn1, col_btn2, col_btn3, col_spacer = st.columns([1, 1, 1, 3])
    with col_btn1:
        if st.button("⚠️ With issues", key=f"{key_prefix}_sel_issues", use_container_width=True,
                      help="Select only salespersons who have overdue AR or active alerts"):
            issue_ids = summary_df[
                (summary_df['overdue_amount'] > 0) | (summary_df['alert_count'] > 0)
            ]['employee_id'].tolist()
            _apply_selection(issue_ids)
    with col_btn2:
        if st.button("✅ All enabled", key=f"{key_prefix}_sel_enabled", use_container_width=True,
                      help="Select all salespersons whose notifications are enabled in Preferences"):
            enabled_ids = summary_df[summary_df['enabled']]['employee_id'].tolist()
            _apply_selection(enabled_ids)
    with col_btn3:
        if st.button("🗑️ Clear", key=f"{key_prefix}_sel_clear", use_container_width=True,
                      help="Deselect all — no one will receive the warning email"):
            _apply_selection([])

    # Target selection list (buttons write, checkboxes read)
    target_selection = st.session_state.get(_sel_key, _default_ids)

    # ─── Render recipient checkboxes ───
    selected_eids = []

    for _, row in summary_df.iterrows():
        eid = int(row['employee_id'])
        name = row['name']
        overdue = row['overdue_amount']
        cust_count = int(row['customer_count'])
        worst = row['worst_aging']
        worst_icon = row['worst_icon']
        alerts = int(row['alert_count'])
        enabled = row['enabled']

        # Build label
        overdue_label = f"${overdue:,.0f} overdue" if overdue > 0 else "$0"
        cust_label = f"{cust_count} customer{'s' if cust_count != 1 else ''}" if cust_count > 0 else "—"
        alert_label = f"{alerts} alert{'s' if alerts != 1 else ''}" if alerts > 0 else "0"

        col_check, col_name, col_overdue, col_cust, col_aging, col_alerts = st.columns([0.4, 2, 1.5, 1, 1, 0.8])

        with col_check:
            is_checked = st.checkbox(
                "sel", value=(eid in target_selection),
                key=f"{key_prefix}_chk_{eid}",
                label_visibility="collapsed",
                disabled=not enabled and not st.session_state.get(f"{key_prefix}_override", False),
            )
        with col_name:
            if not enabled:
                st.markdown(f"~~{name}~~ <span style='color:gray;font-size:12px;'>🚫 disabled</span>",
                            unsafe_allow_html=True)
            else:
                st.markdown(f"**{name}**")
        with col_overdue:
            color = "#dc2626" if overdue > 0 else "#6b7280"
            st.markdown(f"<span style='color:{color};font-size:13px;'>{overdue_label}</span>",
                        unsafe_allow_html=True)
        with col_cust:
            st.caption(cust_label)
        with col_aging:
            st.caption(f"{worst_icon} {worst.replace(' overdue', '')}" if worst != 'OK' else "✅ OK")
        with col_alerts:
            if alerts > 0:
                st.markdown(f"<span style='color:#ea580c;font-weight:600;font-size:13px;'>{alert_label}</span>",
                            unsafe_allow_html=True)
            else:
                st.caption("0")

        if is_checked:
            selected_eids.append(eid)

    st.caption(f"**{len(selected_eids)}** of {len(employee_ids)} selected")

    st.divider()

    # ─────────────────────────────────────────────────────────────
    # PANEL B: CC CONFIGURATION
    # ─────────────────────────────────────────────────────────────
    st.markdown("##### 📋 CC Recipients")

    # Auto CC managers (mandatory)
    recipients_map = resolve_recipients_batch(selected_eids) if selected_eids else {}
    manager_cc_emails = set()
    manager_info = {}  # manager_email → [managed names]

    for eid in selected_eids:
        info = recipients_map.get(eid)
        if info and info.has_manager_email:
            email = info.manager_email
            manager_cc_emails.add(email)
            if email not in manager_info:
                manager_info[email] = {"name": info.manager_name, "manages": []}
            manager_info[email]["manages"].append(info.sales_name)

    if manager_cc_emails:
        st.markdown("**Auto CC (mandatory):**")
        for email, minfo in manager_info.items():
            manages_str = ", ".join(minfo["manages"][:5])
            if len(minfo["manages"]) > 5:
                manages_str += f" +{len(minfo['manages'])-5} more"
            st.caption(f"✅ {minfo['name']} ({email}) — manages {manages_str}")
    elif selected_eids:
        st.caption("No manager emails found for selected recipients")

    # Additional CC from employees
    all_employees = get_all_employees_with_email()
    cc_options = [
        f"{e['name']} ({e['email']})"
        for e in all_employees
        if e['email'] not in manager_cc_emails
    ]
    cc_email_map = {
        f"{e['name']} ({e['email']})": e['email']
        for e in all_employees
    }

    additional_cc_selected = st.multiselect(
        "Additional CC (from employees)",
        options=cc_options,
        key=f"{key_prefix}_additional_cc",
        placeholder="Search employee name...",
    )
    additional_cc_emails = [cc_email_map[s] for s in additional_cc_selected if s in cc_email_map]

    # External CC
    col_ext, col_add = st.columns([3, 1])
    with col_ext:
        ext_email_input = st.text_input(
            "External CC email",
            placeholder="partner@client.com",
            key=f"{key_prefix}_ext_cc_input",
            label_visibility="collapsed",
        )
    with col_add:
        add_ext = st.button("+ Add", key=f"{key_prefix}_ext_cc_add", use_container_width=True)

    # Manage external CC list in session state
    ext_cc_key = f"{key_prefix}_external_cc_list"
    if ext_cc_key not in st.session_state:
        st.session_state[ext_cc_key] = []

    if add_ext and ext_email_input and '@' in ext_email_input:
        if ext_email_input not in st.session_state[ext_cc_key]:
            st.session_state[ext_cc_key].append(ext_email_input)

    external_cc_list = st.session_state[ext_cc_key]
    if external_cc_list:
        for idx, ext_email in enumerate(external_cc_list):
            col_e, col_x = st.columns([5, 1])
            with col_e:
                st.caption(f"• {ext_email}")
            with col_x:
                if st.button("✕", key=f"{key_prefix}_rm_ext_{idx}"):
                    st.session_state[ext_cc_key].remove(ext_email)
                    st.rerun(scope="fragment")

    total_cc = len(manager_cc_emails) + len(additional_cc_emails) + len(external_cc_list)
    st.caption(f"Total CC: {total_cc} ({len(manager_cc_emails)} manager{'s' if len(manager_cc_emails)!=1 else ''}"
               f" + {len(additional_cc_emails)} additional + {len(external_cc_list)} external)")

    st.divider()

    # ─────────────────────────────────────────────────────────────
    # PANEL C: PREVIEW & SEND
    # ─────────────────────────────────────────────────────────────
    st.markdown("##### 📤 Preview & Send")

    col_summary, col_lang, col_options = st.columns([3, 1.5, 1.5])

    with col_summary:
        to_count = len(selected_eids)
        st.markdown(f"**To:** {to_count} salesperson{'s' if to_count!=1 else ''} "
                    f"&nbsp;|&nbsp; **CC:** {total_cc} recipient{'s' if total_cc!=1 else ''}")

    with col_lang:
        from .preferences import LANGUAGE_OPTIONS as _LANG_OPTS
        send_lang = st.selectbox(
            "Email Language",
            options=list(_LANG_OPTS.keys()),
            format_func=lambda x: _LANG_OPTS[x],
            key=f"{key_prefix}_send_lang",
            help="Language for email content. Per-employee language from preferences is used when 'Use preferences' is checked.",
        )

    with col_options:
        override_prefs = st.checkbox(
            "Override disabled preferences",
            key=f"{key_prefix}_override",
            help="Send even to employees with notifications disabled",
        )

    # Preview (first selected employee)
    if selected_eids:
        with st.expander("👁️ Preview sample email", expanded=False):
            first_eid = selected_eids[0]
            first_info = recipients_map.get(first_eid)
            first_name = first_info.sales_name if first_info else f"Employee #{first_eid}"

            preview_data = collect_warning_data(
                employee_id=first_eid,
                employee_name=first_name,
                sales_df=sales_df if sales_df is not None else pd.DataFrame(),
                backlog_detail_df=backlog_detail_df if backlog_detail_df is not None else pd.DataFrame(),
                ar_outstanding_df=ar_outstanding_df if ar_outstanding_df is not None else pd.DataFrame(),
                targets_df=targets_df if targets_df is not None else pd.DataFrame(),
                active_filters=active_filters,
            )

            sender_name = st.session_state.get("user_fullname", "Prostech BI")
            subject, html_preview = build_warning_email(
                warning_data=preview_data,
                active_filters=active_filters,
                sender_name=sender_name,
                lang=send_lang,
            )

            st.info(f"Preview for **{first_name}** — each person receives their own data.")
            st.markdown(f"**Subject:** `{subject}`")
            with st.container(height=500, border=True):
                st.html(html_preview)

    # Send button
    can_send = len(selected_eids) > 0

    if st.button(
        f"📨 Send Warning to {len(selected_eids)} salesperson{'s' if len(selected_eids)!=1 else ''}",
        key=f"{key_prefix}_send_warning",
        type="primary",
        disabled=not can_send,
        use_container_width=True,
    ):
        sender_name = st.session_state.get("user_fullname", "Prostech BI")

        with st.spinner(f"Sending warnings to {len(selected_eids)} recipient(s)..."):
            result = send_warning_to_selected(
                employee_ids=selected_eids,
                active_filters=active_filters,
                sender_name=sender_name,
                additional_cc=additional_cc_emails,
                external_cc=external_cc_list,
                override_preferences=override_prefs,
                default_lang=send_lang,
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

        # Details
        if result.details:
            with st.expander(
                f"📋 Details ({result.sent_count} sent, "
                f"{result.failed_count} failed, "
                f"{result.skipped_count} skipped)",
                expanded=result.failed_count > 0,
            ):
                for d in result.details:
                    status = d.get("status", "unknown")
                    name = d.get("name", f"ID #{d.get('employee_id', '?')}")
                    if status == "sent":
                        overdue = d.get('overdue', 0)
                        cc_info = f" (CC: {d['cc']})" if d.get('cc') else ""
                        lang_info = f" [{d.get('lang', 'en').upper()}]"
                        excel_info = " 📎" if d.get('has_excel') else ""
                        st.markdown(
                            f"✅ **{name}** → `{d.get('to', '')}` "
                            f"| O/S: ${overdue:,.0f}{cc_info}{lang_info}{excel_info}"
                        )
                    elif status == "failed":
                        st.markdown(f"❌ **{name}** → {d.get('error', 'Unknown error')}")
                    elif status == "skipped":
                        st.markdown(f"⏭️ **{name}** — {d.get('reason', 'Skipped')}")

                st.caption(f"Total time: {result.elapsed_seconds}s")


# =============================================================================
# TAB 2: ⚙️ PREFERENCES (preserved from v2.0)
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
        LANGUAGE_OPTIONS,
    )
    from .recipient_resolver import resolve_recipients_batch

    if not employee_ids:
        st.info("No salespeople selected. Adjust sidebar filters to manage preferences.")
        return

    recipients = resolve_recipients_batch(employee_ids)
    all_prefs = get_preferences_for_employees(employee_ids)
    can_edit = access_level in ('full', 'team')

    st.markdown(f"**{len(employee_ids)} salesperson(s)** — "
                f"{'Edit' if can_edit else 'View'} notification preferences")

    if not can_edit:
        st.info("🔒 Read-only — contact your manager to change notification settings.")

    # Bulk actions
    if can_edit and len(employee_ids) > 1:
        col_b1, col_b2, col_b3, col_b_spacer = st.columns([1, 1, 1, 3])
        with col_b1:
            if st.button("✅ Enable All", key=f"{key_prefix}_bulk_enable", use_container_width=True):
                _bulk_toggle_all(employee_ids, True, key_prefix)
        with col_b2:
            if st.button("🚫 Disable All", key=f"{key_prefix}_bulk_disable", use_container_width=True):
                _bulk_toggle_all(employee_ids, False, key_prefix)
        with col_b3:
            if st.button("🔄 Set All Weekly", key=f"{key_prefix}_bulk_weekly", use_container_width=True):
                _bulk_set_frequency(employee_ids, 'weekly', key_prefix)

    for eid in employee_ids:
        info = recipients.get(eid)
        name = info.sales_name if info else f"Employee #{eid}"
        email = info.sales_email if info and info.has_sales_email else "⚠️ no email"
        mgr = info.manager_name if info and info.manager_name else "—"
        prefs = all_prefs.get(eid, {})

        with st.expander(f"👤 {name} ({email})", expanded=(len(employee_ids) == 1)):
            # Show whether prefs are from DB or hardcoded defaults
            is_from_db = prefs.get('_from_db', False)
            if is_from_db:
                st.caption(f"Manager: {mgr} &nbsp;·&nbsp; ✅ Saved in DB")
            else:
                st.caption(f"Manager: {mgr} &nbsp;·&nbsp; ⚙️ Defaults (not yet saved)")

            master_pref = prefs.get('all', {'enabled': True, 'frequency': 'weekly', 'notify_manager': True, 'language': 'en'})

            col_master, col_freq, col_lang, col_cc = st.columns([2, 2, 1.5, 1])
            with col_master:
                master_enabled = st.toggle(
                    "📧 Notifications Enabled",
                    value=master_pref['enabled'],
                    key=f"{key_prefix}_{eid}_master",
                    disabled=not can_edit,
                )
            with col_freq:
                freq_options = list(FREQUENCY_OPTIONS.keys())
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
            with col_lang:
                lang_options = list(LANGUAGE_OPTIONS.keys())
                current_lang = master_pref.get('language', 'en')
                lang_idx = lang_options.index(current_lang) if current_lang in lang_options else 0
                selected_lang = st.selectbox(
                    "Language",
                    options=lang_options,
                    format_func=lambda x: LANGUAGE_OPTIONS[x],
                    index=lang_idx,
                    key=f"{key_prefix}_{eid}_lang",
                    disabled=not can_edit or not master_enabled,
                )
            with col_cc:
                cc_mgr = st.checkbox(
                    "CC Manager",
                    value=master_pref.get('notify_manager', True),
                    key=f"{key_prefix}_{eid}_cc",
                    disabled=not can_edit or not master_enabled,
                )

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

            if can_edit:
                if st.button("💾 Save", key=f"{key_prefix}_{eid}_save", use_container_width=True):
                    new_prefs = {
                        'all': {
                            'enabled': master_enabled,
                            'frequency': selected_freq,
                            'notify_manager': cc_mgr,
                            'language': selected_lang,
                        },
                    }
                    for atype, _ in [(k, v) for k, v in ALERT_TYPES.items() if k != 'all']:
                        widget_val = st.session_state.get(f"{key_prefix}_{eid}_{atype}", True)
                        new_prefs[atype] = {
                            'enabled': widget_val if master_enabled else False,
                            'frequency': selected_freq,
                            'notify_manager': cc_mgr,
                            'language': selected_lang,
                        }
                    modifier_id = st.session_state.get('employee_id')
                    saved = save_preferences_bulk(eid, new_prefs, modified_by=modifier_id)
                    st.success(f"✅ Saved {saved} preference(s) for {name}")


def _bulk_toggle_all(employee_ids: List[int], enabled: bool, key_prefix: str):
    """Bulk enable/disable all employees."""
    from .preferences import save_preference
    count = 0
    for eid in employee_ids:
        if save_preference(eid, 'all', enabled=enabled):
            count += 1
    st.success(f"{'Enabled' if enabled else 'Disabled'} notifications for {count} employee(s)")


def _bulk_set_frequency(employee_ids: List[int], frequency: str, key_prefix: str):
    """Bulk set frequency for all employees."""
    from .preferences import save_preference
    count = 0
    for eid in employee_ids:
        if save_preference(eid, 'all', enabled=True, frequency=frequency):
            count += 1
    st.success(f"Set frequency to {frequency} for {count} employee(s)")


# =============================================================================
# TAB 3: 📋 SEND HISTORY
# =============================================================================

def _render_send_history_tab(employee_ids: List[int], key_prefix: str):
    """Render notification send history."""
    from .send_log import get_send_history, get_send_stats

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

    # Filter
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

    display_df = history_df[[
        'sent_at', 'employee_name', 'to_email', 'cc_email',
        'alert_count', 'status', 'trigger_type',
    ]].copy()

    display_df['sent_at'] = pd.to_datetime(display_df['sent_at']).dt.strftime('%Y-%m-%d %H:%M')
    display_df.columns = [
        'Sent At', 'Salesperson', 'To', 'CC',
        'Alerts', 'Status', 'Trigger',
    ]

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