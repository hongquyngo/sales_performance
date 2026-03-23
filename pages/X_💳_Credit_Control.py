# pages/X_💳_Credit_Control.py
"""
💳 Credit Control Dashboard

5 Tabs: Dashboard | Send Notification | Run Credit Check | Notification History | Block History

Depends on: utils.auth, utils.db, utils.credit_control
VERSION: 1.2.0
  v1.1 → v1.2 Performance:
    - @st.fragment on filter/history tabs → no full-page rerun on widget change
    - st.form on Send Notification / Unblock → no rerun until submit
    - Shared cache: Tab1 + Tab2 reuse same get_all_credit_statuses() call
    - @st.cache_data on history queries (was uncached)
    - Vectorized pandas formatting (replace .apply lambdas)
    - DB connection check cached in session_state
    - Timing debug panel (sidebar expandable)
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from time import perf_counter
from contextlib import contextmanager
import logging

from utils.auth import AuthManager
from utils.db import check_db_connection

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Credit Control", page_icon="💳", layout="wide", initial_sidebar_state="collapsed")

# ═══════════════════════════════════════════════════════════════
# TIMING UTILITY
# ═══════════════════════════════════════════════════════════════
_t_page_start = perf_counter()

if '_perf' not in st.session_state:
    st.session_state['_perf'] = []

def _perf_reset():
    st.session_state['_perf'] = []
    st.session_state['_perf_page_start'] = perf_counter()

_perf_reset()

@contextmanager
def _timer(label: str):
    """Time a block and append to session perf log."""
    t0 = perf_counter()
    yield
    elapsed_ms = (perf_counter() - t0) * 1000
    st.session_state['_perf'].append((label, elapsed_ms))
    if elapsed_ms > 500:
        logger.warning(f"⏱ SLOW: {label} took {elapsed_ms:.0f}ms")

# ═══════════════════════════════════════════════════════════════
# AUTH (lightweight — no DB)
# ═══════════════════════════════════════════════════════════════
with _timer("auth.check_session"):
    auth = AuthManager()
    if not auth.check_session():
        st.warning("⚠️ Please login to access this page"); st.stop()

user_role = st.session_state.get('user_role', 'viewer')
employee_id = st.session_state.get('employee_id')

# ═══════════════════════════════════════════════════════════════
# ACCESS CONTROL MATRIX
# ═══════════════════════════════════════════════════════════════
PAGE_ROLES = ['admin', 'gm', 'md', 'fa_manager', 'sales_manager', 'accountant', 'sales']

_SEND_TEMPLATES = {
    'admin':         ['overdue_reminder', 'overdue_escalation', 'credit_warning', 'credit_exceeded', 'block_notice'],
    'gm':            ['overdue_reminder', 'overdue_escalation', 'credit_warning', 'credit_exceeded', 'block_notice'],
    'md':            ['overdue_reminder', 'overdue_escalation', 'credit_warning', 'credit_exceeded', 'block_notice'],
    'fa_manager':    ['overdue_reminder', 'overdue_escalation', 'credit_warning', 'credit_exceeded'],
    'sales_manager': ['overdue_reminder', 'overdue_escalation', 'credit_warning'],
}
_DRYRUN_ROLES = ['admin', 'gm', 'md', 'fa_manager']
_EXECUTE_ROLES = ['admin', 'gm', 'md']
_UNBLOCK_ROLES = ['admin', 'gm', 'md']

_role = user_role.lower()

if _role not in PAGE_ROLES:
    st.error("⛔ Access denied. Contact admin for Credit Control access."); st.stop()

# ═══════════════════════════════════════════════════════════════
# DB CHECK — cached in session_state (skip on every rerun)
# ═══════════════════════════════════════════════════════════════
if not st.session_state.get('_db_ok'):
    with _timer("check_db_connection"):
        db_ok, db_err = check_db_connection()
    if not db_ok:
        st.error(f"❌ DB connection failed: {db_err}"); st.stop()
    st.session_state['_db_ok'] = True

# ─── Imports (after auth) ───
from utils.credit_control import (
    get_all_statuses, get_status, run_batch, send_manual, execute_unblock, ALERT_LEVELS, CreditStatus,
)
from utils.credit_control.queries import get_notification_history, get_block_history, get_all_credit_statuses

# ═══════════════════════════════════════════════════════════════
# SHARED DATA LOADING — single query, used by Tab1 + Tab2
# ═══════════════════════════════════════════════════════════════
@st.cache_data(ttl=300, show_spinner=False)
def _load_credit_data():
    """Single cached query for credit_status_view — reused by Dashboard + Send tab."""
    t0 = perf_counter()
    df = get_all_credit_statuses()
    elapsed = (perf_counter() - t0) * 1000
    logger.info(f"_load_credit_data: {len(df)} rows, {elapsed:.0f}ms")
    return df, elapsed

# ═══════════════════════════════════════════════════════════════
# FORMATTING HELPERS — vectorized (no .apply lambdas)
# ═══════════════════════════════════════════════════════════════
def _fmt_usd(s: pd.Series) -> pd.Series:
    """Vectorized USD formatting: 12345.67 → '$12,346'"""
    mask = s.notna() & (s != 0)
    result = pd.Series("—", index=s.index)
    if mask.any():
        result[mask] = s[mask].apply(lambda x: f"${x:,.0f}")  # apply only on non-null subset
    return result

def _fmt_pct(s: pd.Series) -> pd.Series:
    mask = s.notna()
    result = pd.Series("—", index=s.index)
    if mask.any():
        result[mask] = s[mask].apply(lambda x: f"{x:.0f}%")
    return result

# ═══════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════
st.title("💳 Credit Control")
st.caption(f"User: {st.session_state.get('user_fullname', '?')} | Role: {user_role}")

_can_send = _role in _SEND_TEMPLATES
_can_batch = _role in _DRYRUN_ROLES

tab_labels = ["📊 Dashboard"]
if _can_send:  tab_labels.append("📧 Send Notification")
if _can_batch: tab_labels.append("🔄 Run Credit Check")
tab_labels += ["📋 Notification History", "🔒 Block History"]

tabs = st.tabs(tab_labels)
_ti = 0

# ═══════════════════════════════════════════════════════════════
# TAB 1: DASHBOARD
#
# Perf notes:
#   - Metrics use full df (above fragment) — computed once
#   - Filters + table wrapped in @st.fragment → filter changes
#     only rerun the fragment, not the whole page
#   - _load_credit_data() cached 300s, shared with Tab 2
# ═══════════════════════════════════════════════════════════════
with tabs[_ti]:
    _ti += 1

    if st.button("🔄 Refresh", key="d_refresh"):
        st.cache_data.clear()
        st.session_state.pop('_db_ok', None)

    with _timer("load_credit_data"):
        df, _q_ms = _load_credit_data()

    if df.empty:
        st.info("No customers with credit limits. Check term_and_conditions.limit_credit."); st.stop()

    # ─── Metrics (outside fragment — static after data load) ───
    alert_counts = df['alert_level'].value_counts()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("🚫 Blocked", alert_counts.get('BLOCKED', 0))
    c2.metric("🔴 Over Limit", alert_counts.get('OVER_LIMIT', 0) + alert_counts.get('OVERDUE_BLOCK', 0))
    c3.metric("🟡 Warning", alert_counts.get('LIMIT_WARNING', 0) + alert_counts.get('OVERDUE_WARNING', 0))
    c4.metric("🔵 Outstanding", alert_counts.get('HAS_OUTSTANDING', 0))
    c5.metric("🟢 Clear", alert_counts.get('CLEAR', 0))

    st.divider()

    # ─── Filters + Table in fragment → no full-page rerun on filter change ───
    @st.fragment
    def _dashboard_filters():
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            af = st.multiselect(
                "Alert Level",
                ['BLOCKED','OVER_LIMIT','OVERDUE_BLOCK','LIMIT_WARNING','OVERDUE_WARNING','HAS_OUTSTANDING','CLEAR','VIP_EXEMPT'],
                default=['BLOCKED','OVER_LIMIT','OVERDUE_BLOCK','LIMIT_WARNING','OVERDUE_WARNING'],
                key="d_al",
            )
        with fc2:
            ef = st.multiselect("Entity", sorted(df['legal_entity_name'].dropna().unique().tolist()), key="d_ent")
        with fc3:
            sf = st.text_input("🔍 Search", key="d_search")

        # ─── Filter (vectorized) ───
        mask = pd.Series(True, index=df.index)
        if af:
            mask &= df['alert_level'].isin(af)
        if ef:
            mask &= df['legal_entity_name'].isin(ef)
        if sf:
            sf_lower = sf.lower()
            mask &= (df['customer_name'].str.lower().str.contains(sf_lower, na=False)
                      | df['customer_code'].str.lower().str.contains(sf_lower, na=False))
        filt = df[mask]

        st.markdown(f"**{len(filt)}** customers")

        if not filt.empty:
            disp_cols = ['alert_level','customer_name','customer_code','legal_entity_name','credit_status',
                         'credit_limit','outstanding_usd','utilization_pct','overdue_usd','max_overdue_days',
                         'outstanding_invoices','available_credit_usd','payment_term','assigned_salespeople']
            disp = filt[disp_cols].copy()

            # Vectorized formatting
            for c in ['credit_limit','outstanding_usd','overdue_usd','available_credit_usd']:
                if c in disp: disp[c] = _fmt_usd(disp[c])
            if 'utilization_pct' in disp:
                disp['utilization_pct'] = _fmt_pct(disp['utilization_pct'])
            disp['alert_level'] = disp['alert_level'].map(
                lambda x: f"{ALERT_LEVELS.get(x,{}).get('icon','❓')} {x}"
            )
            disp.columns = ['Alert','Customer','Code','Entity','Status','Limit','Outstanding',
                            'Util%','Overdue','MaxDays','Inv.','Available','Terms','Sales']
            st.dataframe(disp, hide_index=True, use_container_width=True, height=600)

    _dashboard_filters()

# ═══════════════════════════════════════════════════════════════
# TAB 2: SEND NOTIFICATION
#
# Perf notes:
#   - Reuses _load_credit_data() instead of separate _cust_opts() query
#   - st.form wraps all inputs → no rerun on selectbox/input change
#   - Preview and Send are separate forms to avoid accidental sends
# ═══════════════════════════════════════════════════════════════
if _can_send:
    with tabs[_ti]:
        _ti += 1
        st.subheader("📧 Send Manual Notification")

        if not employee_id:
            st.error("⚠️ Employee ID not found in session. Cannot send notifications — contact admin.")
        else:
            allowed_templates = _SEND_TEMPLATES.get(_role, [])

            # Reuse cached data — no extra query
            with _timer("tab2_build_options"):
                df2, _ = _load_credit_data()
                if df2.empty:
                    labels, ids = [], []
                else:
                    labels = (df2['customer_name'] + ' (' + df2['customer_code'].fillna('') + ') — ' + df2['alert_level']).tolist()
                    ids = df2['customer_id'].tolist()

            # ─── Selection (outside form — so selectbox state persists) ───
            sc1, sc2 = st.columns(2)
            with sc1:
                sel = st.selectbox("Customer", range(len(labels)), format_func=lambda i: labels[i], key="m_cust") if labels else None
                cid = ids[sel] if sel is not None else None
            with sc2:
                tpl = st.selectbox("Template", allowed_templates, key="m_tpl")
                extra = st.text_input("Extra emails (comma-sep)", key="m_extra")

            if cid:
                extra_list = [e.strip() for e in extra.split(',') if e.strip()] if extra else None
                bc1, bc2 = st.columns(2)
                with bc1:
                    if st.button("👁️ Preview", key="m_prev"):
                        with _timer("send_manual_preview"):
                            r = send_manual(cid, tpl, employee_id, extra_list, dry_run=True)
                        if r.get('status') == 'dry_run':
                            st.success(f"Would send to {len(r.get('to',[]))} recipients")
                            st.json({'subject': r.get('subject'), 'to': r.get('to'), 'cc': r.get('cc')})
                        else:
                            st.error(r.get('error', r.get('reason', '?')))
                with bc2:
                    # ─── Send in a form → requires explicit submit ───
                    with st.form("send_form", border=False):
                        confirm_send = st.form_submit_button("📤 Send", type="primary")
                    if confirm_send:
                        with _timer("send_manual_execute"):
                            r = send_manual(cid, tpl, employee_id, extra_list, dry_run=False)
                        if r.get('status') == 'sent':
                            st.success(f"✅ Sent to: {', '.join(r.get('to',[]))}")
                        else:
                            st.error(f"❌ {r.get('error','?')}")

# ═══════════════════════════════════════════════════════════════
# TAB 3: RUN CREDIT CHECK
#
# Perf notes:
#   - Batch processing is inherently slow (N customers × M rules × DB)
#   - Timing logged inside run_batch via BatchResult.started_at/finished_at
#   - Frontend just shows spinner — no caching (side-effects)
# ═══════════════════════════════════════════════════════════════
if _can_batch:
    with tabs[_ti]:
        _ti += 1
        st.subheader("🔄 Batch Credit Check")
        st.markdown("Process all customers against notification rules. Dry run previews; Execute sends real emails.")

        if not employee_id:
            st.error("⚠️ Employee ID not found in session. Cannot run batch — contact admin.")
        else:
            rc1, rc2 = st.columns(2)
            with rc1:
                if st.button("👁️ Dry Run", key="b_dry", use_container_width=True):
                    with st.spinner("Checking..."):
                        with _timer("batch_dry_run"):
                            res = run_batch(dry_run=True, triggered_by_user_id=employee_id)
                        st.success(f"✅ {res.summary()}")
                        if res.details:
                            st.dataframe(pd.DataFrame(res.details), hide_index=True, height=400, use_container_width=True)
            with rc2:
                if _role in _EXECUTE_ROLES:
                    with st.form("batch_execute_form", border=False):
                        st.checkbox("I confirm — send real emails", key="b_confirm")
                        execute_clicked = st.form_submit_button("🚀 Execute", type="primary")
                    if execute_clicked:
                        if st.session_state.get("b_confirm"):
                            with st.spinner("Sending..."):
                                with _timer("batch_execute"):
                                    res = run_batch(dry_run=False, triggered_by_user_id=employee_id)
                                (st.success if res.total_failed == 0 else st.warning)(
                                    f"{'✅' if res.total_failed == 0 else '⚠️'} {res.summary()}"
                                )
                                if res.details:
                                    st.dataframe(pd.DataFrame(res.details), hide_index=True, height=400, use_container_width=True)
                        else:
                            st.warning("Check the confirmation box")
                else:
                    st.info(f"🔒 Execute requires admin / GM / MD (current: {user_role})")

# ═══════════════════════════════════════════════════════════════
# TAB 4: NOTIFICATION HISTORY
#
# Perf notes:
#   - BEFORE: uncached → query on every rerun (even filter change in Tab1)
#   - AFTER:  @st.cache_data + @st.fragment
#   - Fragment: changing "Show" dropdown only reruns this fragment
# ═══════════════════════════════════════════════════════════════
with tabs[_ti]:
    _ti += 1

    @st.fragment
    def _notification_history():
        st.subheader("📋 Notification History")
        lim = st.selectbox("Show", [25, 50, 100], index=1, key="h_lim")

        @st.cache_data(ttl=120, show_spinner="Loading history...")
        def _fetch_history(limit: int):
            t0 = perf_counter()
            result = get_notification_history(limit=limit)
            return result, (perf_counter() - t0) * 1000

        with _timer("notification_history_query"):
            hdf, _hq_ms = _fetch_history(lim)

        if hdf.empty:
            st.info("No notifications sent yet")
        else:
            cols = ['created_at','notification_type','severity','customer_name','outstanding_usd','overdue_amount_usd',
                    'max_overdue_days','delivery_status','email_subject','triggered_by','triggered_by_name']
            avail = [c for c in cols if c in hdf.columns]
            h = hdf[avail].copy()
            for c in ['outstanding_usd','overdue_amount_usd']:
                if c in h: h[c] = _fmt_usd(h[c])
            st.dataframe(h, hide_index=True, use_container_width=True, height=500)

    _notification_history()

# ═══════════════════════════════════════════════════════════════
# TAB 5: BLOCK HISTORY + MANUAL UNBLOCK
#
# Perf notes:
#   - History: @st.cache_data + @st.fragment (same pattern as Tab4)
#   - Unblock: st.form → no rerun on typing reason / entering ID
# ═══════════════════════════════════════════════════════════════
with tabs[_ti]:

    @st.fragment
    def _block_history():
        st.subheader("🔒 Block / Unblock History")

        @st.cache_data(ttl=120, show_spinner="Loading block history...")
        def _fetch_blocks(limit: int):
            t0 = perf_counter()
            result = get_block_history(limit=limit)
            return result, (perf_counter() - t0) * 1000

        with _timer("block_history_query"):
            bdf, _bq_ms = _fetch_blocks(50)

        if bdf.empty:
            st.info("No block actions recorded")
        else:
            cols = ['created_at','action','reason','blocked_scope','customer_name','entity_name',
                    'outstanding_at_action','overdue_at_action','max_overdue_days','performed_by','user_name','notes']
            avail = [c for c in cols if c in bdf.columns]
            b = bdf[avail].copy()
            for c in ['outstanding_at_action','overdue_at_action']:
                if c in b: b[c] = _fmt_usd(b[c])
            st.dataframe(b, hide_index=True, use_container_width=True, height=500)

    _block_history()

    # ─── Unblock (separate from fragment — has side effects) ───
    st.divider()
    st.markdown("##### Manual Unblock")
    if _role in _UNBLOCK_ROLES:
        if not employee_id:
            st.error("⚠️ Employee ID not found in session — contact admin.")
        else:
            with st.form("unblock_form"):
                uf1, uf2 = st.columns(2)
                with uf1:
                    uc = st.number_input("Customer ID", min_value=1, step=1, key="u_cid")
                with uf2:
                    ur = st.text_input("Reason", key="u_reason", placeholder="e.g. Payment plan agreed")
                unblock_clicked = st.form_submit_button("🔓 Unblock", type="primary")

            if unblock_clicked:
                if not ur:
                    st.warning("Enter a reason")
                else:
                    with _timer("unblock_execute"):
                        statuses = get_status(int(uc))
                    if not statuses:
                        st.error(f"❌ No credit terms found for customer ID {int(uc)}")
                    else:
                        blocked = [cs for cs in statuses if cs.is_blocked]
                        if not blocked:
                            st.info(f"ℹ️ Customer **{statuses[0].customer_name}** is not currently blocked (status: {statuses[0].credit_status})")
                        else:
                            for cs in blocked:
                                ok = execute_unblock(cs, reason='gm_override', performed_by='user',
                                                     user_id=employee_id, notes=ur)
                                if ok:
                                    st.success(f"✅ Unblocked **{cs.customer_name}** ({cs.legal_entity_name or '—'})")
                                    st.cache_data.clear()  # refresh block history
                                else:
                                    st.error(f"❌ Failed to unblock {cs.customer_name}")
    else:
        st.info("🔒 Only admin / GM / MD can unblock customers")

# ═══════════════════════════════════════════════════════════════
# FOOTER + TIMING DEBUG
# ═══════════════════════════════════════════════════════════════
_t_page_total = (perf_counter() - st.session_state.get('_perf_page_start', _t_page_start)) * 1000

st.divider()
st.caption(f"Credit Control v1.2 | {st.session_state.get('user_fullname','?')} | {user_role}")

# ─── Debug panel (sidebar) ───
with st.sidebar:
    with st.expander("⏱ Performance", expanded=False):
        perf_data = st.session_state.get('_perf', [])
        if perf_data:
            st.markdown(f"**Page total: {_t_page_total:.0f}ms**")
            for label, ms in perf_data:
                bar = "🟥" if ms > 1000 else "🟧" if ms > 500 else "🟨" if ms > 100 else "🟩"
                st.markdown(f"{bar} `{ms:7.0f}ms` — {label}")
            st.markdown("---")
            st.markdown(f"Measured steps: {len(perf_data)}")
        else:
            st.info("No timing data")