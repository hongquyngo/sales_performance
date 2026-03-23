# pages/X_💳_Credit_Control.py
"""
💳 Credit Control Dashboard

5 Tabs: Dashboard | Send Notification | Run Credit Check | Notification History | Block History

Depends on: utils.auth, utils.db, utils.credit_control
VERSION: 1.0.0
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import logging

from utils.auth import AuthManager
from utils.db import check_db_connection

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Credit Control", page_icon="💳", layout="wide", initial_sidebar_state="collapsed")

# ─── Auth ───
auth = AuthManager()
if not auth.check_session():
    st.warning("⚠️ Please login to access this page"); st.stop()

user_role = st.session_state.get('user_role', 'viewer')
if user_role.lower() not in ['admin', 'gm', 'md', 'sales_manager']:
    st.error("⛔ Access denied. Requires admin / GM / MD / sales_manager."); st.stop()

db_ok, db_err = check_db_connection()
if not db_ok:
    st.error(f"❌ DB connection failed: {db_err}"); st.stop()

# ─── Imports (after auth) ───
from utils.credit_control import (
    get_all_statuses, get_status, run_batch, send_manual, execute_unblock, ALERT_LEVELS, CreditStatus,
)
from utils.credit_control.queries import get_notification_history, get_block_history, get_all_credit_statuses

# ─── Header ───
st.title("💳 Credit Control")
st.caption(f"User: {st.session_state.get('user_fullname', '?')} | Role: {user_role}")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Dashboard", "📧 Send Notification", "🔄 Run Credit Check", "📋 Notification History", "🔒 Block History"])

# ═══════════════════════════════════════════════════════════════
# TAB 1: DASHBOARD
# ═══════════════════════════════════════════════════════════════
with tab1:
    if st.button("🔄 Refresh", key="d_refresh"):
        st.cache_data.clear()

    @st.cache_data(ttl=300)
    def _load():
        return get_all_credit_statuses()

    df = _load()
    if df.empty:
        st.info("No customers with credit limits. Check term_and_conditions.limit_credit."); st.stop()

    # Metrics row
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("🚫 Blocked", len(df[df['alert_level'] == 'BLOCKED']))
    c2.metric("🔴 Over Limit", len(df[df['alert_level'].isin(['OVER_LIMIT', 'OVERDUE_BLOCK'])]))
    c3.metric("🟡 Warning", len(df[df['alert_level'].isin(['LIMIT_WARNING', 'OVERDUE_WARNING'])]))
    c4.metric("🔵 Outstanding", len(df[df['alert_level'] == 'HAS_OUTSTANDING']))
    c5.metric("🟢 Clear", len(df[df['alert_level'] == 'CLEAR']))

    st.divider()

    # Filters
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        af = st.multiselect("Alert Level", ['BLOCKED','OVER_LIMIT','OVERDUE_BLOCK','LIMIT_WARNING','OVERDUE_WARNING','HAS_OUTSTANDING','CLEAR','VIP_EXEMPT'],
                            default=['BLOCKED','OVER_LIMIT','OVERDUE_BLOCK','LIMIT_WARNING','OVERDUE_WARNING'], key="d_al")
    with fc2:
        ef = st.multiselect("Entity", sorted(df['legal_entity_name'].dropna().unique().tolist()), key="d_ent")
    with fc3:
        sf = st.text_input("🔍 Search", key="d_search")

    filt = df.copy()
    if af: filt = filt[filt['alert_level'].isin(af)]
    if ef: filt = filt[filt['legal_entity_name'].isin(ef)]
    if sf: filt = filt[filt['customer_name'].str.contains(sf, case=False, na=False) | filt['customer_code'].str.contains(sf, case=False, na=False)]

    st.markdown(f"**{len(filt)}** customers")

    if not filt.empty:
        disp = filt[['alert_level','customer_name','customer_code','legal_entity_name','credit_status',
                      'credit_limit','outstanding_usd','utilization_pct','overdue_usd','max_overdue_days',
                      'outstanding_invoices','available_credit_usd','payment_term','assigned_salespeople']].copy()
        for c in ['credit_limit','outstanding_usd','overdue_usd','available_credit_usd']:
            if c in disp: disp[c] = disp[c].apply(lambda x: f"${x:,.0f}" if pd.notna(x) and x else "—")
        if 'utilization_pct' in disp: disp['utilization_pct'] = disp['utilization_pct'].apply(lambda x: f"{x:.0f}%" if pd.notna(x) else "—")
        disp['alert_level'] = disp['alert_level'].apply(lambda x: f"{ALERT_LEVELS.get(x,{}).get('icon','❓')} {x}")
        disp.columns = ['Alert','Customer','Code','Entity','Status','Limit','Outstanding','Util%','Overdue','MaxDays','Inv.','Available','Terms','Sales']
        st.dataframe(disp, hide_index=True, width="stretch", height=600)

# ═══════════════════════════════════════════════════════════════
# TAB 2: SEND NOTIFICATION
# ═══════════════════════════════════════════════════════════════
with tab2:
    st.subheader("📧 Send Manual Notification")

    @st.cache_data(ttl=300)
    def _cust_opts():
        d = get_all_credit_statuses()
        if d.empty: return [], []
        labels = [f"{r['customer_name']} ({r['customer_code']}) — {r['alert_level']}" for _, r in d.iterrows()]
        return labels, d['customer_id'].tolist()

    labels, ids = _cust_opts()
    sc1, sc2 = st.columns(2)
    with sc1:
        sel = st.selectbox("Customer", range(len(labels)), format_func=lambda i: labels[i], key="m_cust") if labels else None
        cid = ids[sel] if sel is not None else None
    with sc2:
        tpl = st.selectbox("Template", ['overdue_reminder','overdue_escalation','credit_warning','credit_exceeded','block_notice'], key="m_tpl")
        extra = st.text_input("Extra emails (comma-sep)", key="m_extra")

    if cid:
        bc1, bc2 = st.columns(2)
        with bc1:
            if st.button("👁️ Preview", key="m_prev"):
                r = send_manual(cid, tpl, st.session_state.get('employee_id'), [e.strip() for e in extra.split(',') if e.strip()] if extra else None, dry_run=True)
                if r.get('status') == 'dry_run':
                    st.success(f"Would send to {len(r.get('to',[]))} recipients")
                    st.json({'subject': r.get('subject'), 'to': r.get('to'), 'cc': r.get('cc')})
                else:
                    st.error(r.get('error', r.get('reason', '?')))
        with bc2:
            if st.button("📤 Send", type="primary", key="m_send"):
                r = send_manual(cid, tpl, st.session_state.get('employee_id'), [e.strip() for e in extra.split(',') if e.strip()] if extra else None, dry_run=False)
                if r.get('status') == 'sent':
                    st.success(f"✅ Sent to: {', '.join(r.get('to',[]))}")
                else:
                    st.error(f"❌ {r.get('error','?')}")

# ═══════════════════════════════════════════════════════════════
# TAB 3: RUN CREDIT CHECK
# ═══════════════════════════════════════════════════════════════
with tab3:
    st.subheader("🔄 Batch Credit Check")
    st.markdown("Process all customers against notification rules. Dry run previews; Execute sends real emails.")

    rc1, rc2 = st.columns(2)
    with rc1:
        if st.button("👁️ Dry Run", key="b_dry", use_container_width=True):
            with st.spinner("Checking..."):
                res = run_batch(dry_run=True, triggered_by_user_id=st.session_state.get('employee_id'))
                st.success(f"✅ {res.summary()}")
                if res.details:
                    st.dataframe(pd.DataFrame(res.details), hide_index=True, height=400, width="stretch")
    with rc2:
        if st.button("🚀 Execute", type="primary", key="b_exec", use_container_width=True):
            if st.checkbox("I confirm — send real emails", key="b_confirm"):
                with st.spinner("Sending..."):
                    res = run_batch(dry_run=False, triggered_by_user_id=st.session_state.get('employee_id'))
                    (st.success if res.total_failed == 0 else st.warning)(f"{'✅' if res.total_failed == 0 else '⚠️'} {res.summary()}")
                    if res.details:
                        st.dataframe(pd.DataFrame(res.details), hide_index=True, height=400, width="stretch")
            else:
                st.warning("Check the confirmation box")

# ═══════════════════════════════════════════════════════════════
# TAB 4: NOTIFICATION HISTORY
# ═══════════════════════════════════════════════════════════════
with tab4:
    st.subheader("📋 Notification History")
    lim = st.selectbox("Show", [25, 50, 100], index=1, key="h_lim")
    hdf = get_notification_history(limit=lim)
    if hdf.empty:
        st.info("No notifications sent yet")
    else:
        cols = ['created_at','notification_type','severity','customer_name','outstanding_usd','overdue_amount_usd',
                'max_overdue_days','delivery_status','email_subject','triggered_by','triggered_by_name']
        avail = [c for c in cols if c in hdf.columns]
        h = hdf[avail].copy()
        for c in ['outstanding_usd','overdue_amount_usd']:
            if c in h: h[c] = h[c].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "—")
        st.dataframe(h, hide_index=True, width="stretch", height=500)

# ═══════════════════════════════════════════════════════════════
# TAB 5: BLOCK HISTORY + MANUAL UNBLOCK
# ═══════════════════════════════════════════════════════════════
with tab5:
    st.subheader("🔒 Block / Unblock History")
    bdf = get_block_history(limit=50)
    if bdf.empty:
        st.info("No block actions recorded")
    else:
        cols = ['created_at','action','reason','blocked_scope','customer_name','entity_name',
                'outstanding_at_action','overdue_at_action','max_overdue_days','performed_by','user_name','notes']
        avail = [c for c in cols if c in bdf.columns]
        b = bdf[avail].copy()
        for c in ['outstanding_at_action','overdue_at_action']:
            if c in b: b[c] = b[c].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "—")
        st.dataframe(b, hide_index=True, width="stretch", height=500)

    st.divider()
    st.markdown("##### Manual Unblock")
    if user_role.lower() in ['admin', 'gm', 'md']:
        uc = st.number_input("Customer ID", min_value=1, step=1, key="u_cid")
        ur = st.text_input("Reason", key="u_reason", placeholder="e.g. Payment plan agreed")
        if st.button("🔓 Unblock", key="u_btn"):
            if ur:
                for cs in get_status(int(uc)):
                    if cs.is_blocked:
                        ok = execute_unblock(cs, reason='gm_override', performed_by='user',
                                             user_id=st.session_state.get('employee_id'), notes=ur)
                        st.success(f"✅ Unblocked {cs.customer_name}") if ok else st.error("Failed")
            else:
                st.warning("Enter a reason")
    else:
        st.info("Only admin/GM/MD can unblock")

st.divider()
st.caption(f"Credit Control v1.0 | {st.session_state.get('user_fullname','?')} | {user_role}")
