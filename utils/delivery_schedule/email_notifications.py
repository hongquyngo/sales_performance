# utils/delivery_schedule/email_notifications.py
"""Email notification tab — send delivery schedules, overdue alerts, customs clearance emails"""

import streamlit as st
import pandas as pd
from datetime import datetime
from sqlalchemy import text
import re
import logging

logger = logging.getLogger(__name__)


@st.fragment
def display_email_notifications(data_loader, email_sender):
    """Full email notification UI — runs as a fragment (interactions don't rerun the whole page)"""

    # Role check
    user_role = st.session_state.get('user_role', '')
    if user_role not in ['supply_chain_manager', 'outbound_manager', 'supply_chain']:
        st.warning("🔒 You need admin/manager/logistics role to send emails.")
        return

    st.subheader("📧 Email Notifications")
    st.caption("Send delivery schedules, urgent alerts, or customs clearance emails")

    # ── Layout: Settings (right) + Recipients (left) ─────────────
    col_left, col_right = st.columns([2, 1])

    with col_right:
        notification_type = st.radio(
            "📧 Notification Type",
            ["📅 Delivery Schedule", "🚨 Overdue Alerts", "🛃 Custom Clearance"],
            key="email_notif_type"
        )

        weeks_ahead = 4
        if notification_type in ["📅 Delivery Schedule", "🛃 Custom Clearance"]:
            weeks_ahead = st.selectbox(
                "📅 Time Period", options=[1, 2, 3, 4, 5, 6, 7, 8], index=3,
                format_func=lambda x: f"{x} week{'s' if x > 1 else ''}",
                key="email_weeks_ahead"
            )

        schedule_type = st.radio("Schedule Type", ["Preview Only", "Send Now"], index=0,
                                  key="email_schedule_type")

    # ── Recipients ────────────────────────────────────────────────
    with col_left:
        selected_recipients = []
        selected_customer_contacts = []
        custom_recipients = []
        sales_df = pd.DataFrame()

        if notification_type == "🛃 Custom Clearance":
            recipient_type = "customs"
            st.info(f"📌 Customs clearance schedule → customs team · Next {weeks_ahead} weeks")
            _show_customs_summary(data_loader, weeks_ahead)
        else:
            recipient_type = st.selectbox(
                "Send to:", ["creators", "customers", "custom"],
                format_func=lambda x: {"creators": "👤 Sales/Creators",
                                        "customers": "🏢 Customers",
                                        "custom": "✉️ Custom Recipients"}[x],
                key="email_recipient_type"
            )

            if recipient_type == "creators":
                sales_df, selected_recipients = _render_creator_selection(
                    data_loader, notification_type, weeks_ahead)

            elif recipient_type == "customers":
                selected_customer_contacts = _render_customer_selection(
                    data_loader, weeks_ahead)

            else:
                custom_recipients = _render_custom_selection()

    # ── CC settings (in right column) ─────────────────────────────
    with col_right:
        cc_emails = _render_cc_settings(
            notification_type, recipient_type, selected_recipients,
            sales_df if not sales_df.empty else None
        )

    st.markdown("---")

    # ── Preview ───────────────────────────────────────────────────
    can_preview = _can_proceed(notification_type, recipient_type,
                               selected_recipients, selected_customer_contacts, custom_recipients)

    if can_preview and st.button("👁️ Preview Email Content", key="email_preview_btn"):
        _render_preview(data_loader, notification_type, recipient_type,
                        selected_recipients, selected_customer_contacts,
                        custom_recipients, sales_df, weeks_ahead)

    # ── Send ──────────────────────────────────────────────────────
    if can_preview and schedule_type == "Send Now":
        st.markdown("---")
        _render_send_section(
            data_loader, email_sender, notification_type, recipient_type,
            selected_recipients, selected_customer_contacts, custom_recipients,
            sales_df, cc_emails, weeks_ahead
        )

    # ── Help ──────────────────────────────────────────────────────
    with st.expander("ℹ️ Help & Information"):
        st.markdown("""
        **📅 Delivery Schedule** — upcoming deliveries grouped by week, with Excel + calendar attachment  
        **🚨 Overdue Alerts** — urgent notifications for overdue/due-today items  
        **🛃 Custom Clearance** — EPE & Foreign customer deliveries for customs team  

        **Recipient types:** Sales/Creators · Customers (2-step: company → contact) · Custom emails  
        """)


# ═════════════════════════════════════════════════════════════════
# PRIVATE HELPERS — Data queries
# ═════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300)
def _get_sales_list(_engine, weeks_ahead=4):
    """Sales people with active deliveries"""
    query = text("""
    SELECT DISTINCT
        e.id, CONCAT(e.first_name, ' ', e.last_name) as name, e.email,
        COUNT(DISTINCT d.delivery_id) as active_deliveries,
        SUM(d.remaining_quantity_to_deliver) as total_quantity,
        COUNT(DISTINCT CASE WHEN d.delivery_timeline_status = 'Overdue' THEN d.delivery_id END) as overdue_deliveries,
        m.email as manager_email
    FROM employees e
    LEFT JOIN employees m ON e.manager_id = m.id
    INNER JOIN delivery_full_view d ON d.created_by_email = e.email
    WHERE d.etd >= CURDATE() AND d.etd <= DATE_ADD(CURDATE(), INTERVAL :weeks WEEK)
        AND d.remaining_quantity_to_deliver > 0
        AND d.shipment_status NOT IN ('DELIVERED', 'COMPLETED')
    GROUP BY e.id, e.first_name, e.last_name, e.email, m.email
    ORDER BY name
    """)
    with _engine.connect() as conn:
        return pd.read_sql(query, conn, params={'weeks': weeks_ahead})


@st.cache_data(ttl=300)
def _get_sales_list_overdue(_engine):
    """Sales with overdue/due-today deliveries"""
    query = text("""
    SELECT DISTINCT
        e.id, CONCAT(e.first_name, ' ', e.last_name) as name, e.email,
        COUNT(DISTINCT CASE WHEN d.delivery_timeline_status = 'Overdue' THEN d.delivery_id END) as overdue_deliveries,
        COUNT(DISTINCT CASE WHEN d.delivery_timeline_status = 'Due Today' THEN d.delivery_id END) as due_today_deliveries,
        MAX(d.days_overdue) as max_days_overdue,
        m.email as manager_email
    FROM employees e
    LEFT JOIN employees m ON e.manager_id = m.id
    INNER JOIN delivery_full_view d ON d.created_by_email = e.email
    WHERE d.delivery_timeline_status IN ('Overdue', 'Due Today')
        AND d.remaining_quantity_to_deliver > 0
        AND d.shipment_status NOT IN ('DELIVERED', 'COMPLETED')
    GROUP BY e.id, e.first_name, e.last_name, e.email, m.email
    HAVING (overdue_deliveries > 0 OR due_today_deliveries > 0)
    ORDER BY overdue_deliveries DESC, name
    """)
    with _engine.connect() as conn:
        return pd.read_sql(query, conn)


@st.cache_data(ttl=300)
def _get_customers_with_deliveries(_engine, weeks_ahead=4):
    """Customers with active deliveries"""
    query = text("""
    SELECT DISTINCT
        d.customer, d.customer_code,
        COUNT(DISTINCT d.delivery_id) as active_deliveries,
        SUM(d.remaining_quantity_to_deliver) as total_quantity,
        COUNT(DISTINCT d.recipient_state_province) as provinces_count
    FROM delivery_full_view d
    WHERE d.etd >= CURDATE() AND d.etd <= DATE_ADD(CURDATE(), INTERVAL :weeks WEEK)
        AND d.remaining_quantity_to_deliver > 0
        AND d.shipment_status NOT IN ('DELIVERED', 'COMPLETED')
    GROUP BY d.customer, d.customer_code
    ORDER BY d.customer
    """)
    with _engine.connect() as conn:
        return pd.read_sql(query, conn, params={'weeks': weeks_ahead})


@st.cache_data(ttl=300)
def _get_customer_contacts(_engine, customer_names):
    """Contacts for selected customers"""
    if not customer_names:
        return pd.DataFrame()
    query = text("""
    SELECT DISTINCT
        CONCAT(d.customer, '_', COALESCE(d.customer_contact_email, 'no_email'), '_',
               COALESCE(d.customer_contact, 'Unknown')) as contact_id,
        d.customer, COALESCE(d.customer_contact, 'Unknown Contact') as contact_name,
        d.customer_contact_email as email,
        COUNT(DISTINCT d.delivery_id) as delivery_count
    FROM delivery_full_view d
    WHERE d.customer IN :customers
        AND d.etd >= CURDATE() AND d.etd <= DATE_ADD(CURDATE(), INTERVAL 4 WEEK)
        AND d.remaining_quantity_to_deliver > 0 AND d.shipment_status NOT IN ('DELIVERED', 'COMPLETED')
        AND d.customer_contact_email IS NOT NULL AND d.customer_contact_email != ''
    GROUP BY d.customer, d.customer_contact, d.customer_contact_email
    ORDER BY d.customer, d.customer_contact
    """)
    with _engine.connect() as conn:
        return pd.read_sql(query, conn, params={'customers': tuple(customer_names)})


# ═════════════════════════════════════════════════════════════════
# PRIVATE HELPERS — UI Sections
# ═════════════════════════════════════════════════════════════════

def _validate_email(email):
    return re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email) is not None


def _can_proceed(notif_type, recip_type, selected, contacts, custom):
    if notif_type == "🛃 Custom Clearance":
        return True
    if recip_type == "creators" and selected:
        return True
    if recip_type == "customers" and contacts:
        return True
    if recip_type == "custom" and custom:
        return True
    return False


def _show_customs_summary(data_loader, weeks_ahead):
    customs = data_loader.get_customs_clearance_summary(weeks_ahead)
    if not customs.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("EPE Deliveries", customs['epe_deliveries'].sum())
        c2.metric("Foreign Deliveries", customs['foreign_deliveries'].sum())
        c3.metric("Total Countries", customs['countries'].sum())
    else:
        st.warning(f"No customs deliveries found for the next {weeks_ahead} weeks")


def _render_creator_selection(data_loader, notification_type, weeks_ahead):
    """Render sales/creator selection; return (sales_df, selected_names)"""
    if notification_type == "🚨 Overdue Alerts":
        sales_df = _get_sales_list_overdue(data_loader.engine)
    else:
        sales_df = _get_sales_list(data_loader.engine, weeks_ahead)

    if sales_df.empty:
        st.warning("No sales with active deliveries found")
        return pd.DataFrame(), []

    if notification_type == "🚨 Overdue Alerts":
        fmt = lambda x: f"{x} (OD:{sales_df[sales_df['name']==x].iloc[0]['overdue_deliveries']}, DT:{sales_df[sales_df['name']==x].iloc[0]['due_today_deliveries']})"
    else:
        fmt = lambda x: f"{x} ({sales_df[sales_df['name']==x].iloc[0]['active_deliveries']} del, {sales_df[sales_df['name']==x].iloc[0]['total_quantity']:.0f} units)"

    selected = st.multiselect("Select sales people:", options=sales_df['name'].tolist(),
                               format_func=fmt, key="email_select_creators")

    if selected:
        sel_df = sales_df[sales_df['name'].isin(selected)]
        if notification_type == "🚨 Overdue Alerts":
            disp = sel_df[['name', 'email', 'overdue_deliveries', 'due_today_deliveries']].copy()
            disp.columns = ['Name', 'Email', 'Overdue', 'Due Today']
        else:
            disp = sel_df[['name', 'email', 'active_deliveries', 'total_quantity']].copy()
            disp['total_quantity'] = disp['total_quantity'].apply(lambda x: f"{x:,.0f}")
            disp.columns = ['Name', 'Email', 'Deliveries', 'Pending Qty']
        st.dataframe(disp, width="stretch", hide_index=True)

    return sales_df, selected


def _render_customer_selection(data_loader, weeks_ahead):
    """Two-step customer → contact selection; return list of contact dicts"""
    cust_df = _get_customers_with_deliveries(data_loader.engine, weeks_ahead)
    if cust_df.empty:
        st.warning("No customers with active deliveries found")
        return []

    fmt_cust = lambda x: f"{x} ({cust_df[cust_df['customer']==x].iloc[0]['active_deliveries']} del)"
    selected_names = st.multiselect("Step 1 — Select customers:",
                                     options=cust_df['customer'].tolist(),
                                     format_func=fmt_cust, key="email_select_customers")
    if not selected_names:
        st.info("Select customers to see contacts")
        return []

    contacts_df = _get_customer_contacts(data_loader.engine, selected_names)
    if contacts_df.empty:
        st.warning("No contacts found for selected customers")
        return []

    fmt_ct = lambda cid: (lambda c: f"{c['contact_name']} — {c['customer']} ({c['email']})")(
        contacts_df[contacts_df['contact_id'] == cid].iloc[0])

    selected_ids = st.multiselect("Step 2 — Select contacts:",
                                   options=contacts_df['contact_id'].tolist(),
                                   format_func=fmt_ct, key="email_select_contacts")

    contacts = contacts_df[contacts_df['contact_id'].isin(selected_ids)].to_dict('records')
    if contacts:
        st.dataframe(pd.DataFrame(contacts)[['customer', 'contact_name', 'email']].rename(
            columns={'customer': 'Customer', 'contact_name': 'Contact', 'email': 'Email'}),
            width="stretch", hide_index=True)
    return contacts


def _render_custom_selection():
    """Custom email entry; return list of valid emails"""
    txt = st.text_area("Email addresses (one per line)",
                        placeholder="john@company.com\njane@company.com",
                        height=120, key="email_custom_text")
    if not txt:
        return []
    emails = [e.strip() for e in txt.split('\n') if e.strip()]
    valid = [e for e in emails if _validate_email(e)]
    invalid = [e for e in emails if not _validate_email(e)]
    if invalid:
        st.error(f"Invalid: {', '.join(invalid)}")
    if valid:
        st.success(f"✅ {len(valid)} valid")
    return valid


def _render_cc_settings(notification_type, recipient_type, selected_recipients, sales_df):
    """Render CC email settings; return list of CC emails"""
    cc_emails = []

    if notification_type == "🛃 Custom Clearance":
        st.text_input("Primary Recipient", value="custom.clearance@prostech.vn",
                       disabled=True, key="email_customs_to")
        cc_emails = ["custom.clearance@prostech.vn"]
    else:
        if recipient_type == "creators" and sales_df is not None and selected_recipients:
            if st.checkbox("CC to managers", value=True, key="email_cc_managers"):
                sel_df = sales_df[sales_df['name'].isin(selected_recipients)]
                mgr = sel_df[sel_df['manager_email'].notna()]['manager_email'].unique().tolist()
                if mgr:
                    st.caption(f"Managers CC'd: {', '.join(mgr)}")
                    cc_emails.extend(mgr)

    additional = st.text_area("Additional CC (one per line)", height=80,
                               key="email_additional_cc",
                               placeholder="outbound@prostech.vn")
    if additional:
        for e in additional.split('\n'):
            e = e.strip()
            if e and _validate_email(e):
                cc_emails.append(e)

    cc_emails = list(dict.fromkeys(cc_emails))  # dedupe
    if cc_emails:
        st.caption(f"Total CC: {len(cc_emails)}")
    return cc_emails


# ═════════════════════════════════════════════════════════════════
# Preview
# ═════════════════════════════════════════════════════════════════

def _render_preview(data_loader, notif_type, recip_type,
                    selected, contacts, custom, sales_df, weeks):
    with st.spinner("Generating preview..."):
        try:
            if notif_type == "🛃 Custom Clearance":
                df = data_loader.get_customs_clearance_schedule(weeks)
                if df.empty:
                    st.warning("No customs deliveries"); return
                c1, c2, c3 = st.columns(3)
                c1.metric("EPE", df[df.get('customs_type', pd.Series()) == 'EPE']['delivery_id'].nunique()
                          if 'customs_type' in df.columns else "–")
                c2.metric("Foreign", df[df.get('customs_type', pd.Series()) == 'Foreign']['delivery_id'].nunique()
                          if 'customs_type' in df.columns else "–")
                c3.metric("Pending Qty", f"{df['remaining_quantity_to_deliver'].sum():,.0f}")

            elif recip_type == "customers" and contacts:
                ct = contacts[0]
                st.markdown(f"**Preview for {ct['customer']} — {ct['contact_name']}**")
                df = data_loader.get_customer_deliveries(ct['customer'], weeks)
                if df.empty:
                    st.info("No deliveries"); return
                c1, c2, c3 = st.columns(3)
                c1.metric("Deliveries", df['delivery_id'].nunique())
                c2.metric("Products", df['product_pn'].nunique())
                c3.metric("Pending Qty", f"{df['remaining_quantity_to_deliver'].sum():,.0f}")

            elif recip_type == "creators" and selected:
                name = selected[0]
                st.markdown(f"**Preview for {name}**")
                df = (data_loader.get_sales_delivery_summary(name, weeks)
                      if notif_type == "📅 Delivery Schedule"
                      else data_loader.get_sales_urgent_deliveries(name))
                if df.empty:
                    st.info("No deliveries"); return
                c1, c2, c3 = st.columns(3)
                c1.metric("Deliveries", df['delivery_id'].nunique())
                c2.metric("Customers", df['customer'].nunique())
                c3.metric("Pending Qty", f"{df['remaining_quantity_to_deliver'].sum():,.0f}")

            elif recip_type == "custom" and custom:
                df = data_loader.get_all_deliveries_summary(weeks)
                if df.empty:
                    st.warning("No delivery data"); return
                c1, c2, c3 = st.columns(3)
                c1.metric("Deliveries", df['delivery_id'].nunique())
                c2.metric("Customers", df['customer'].nunique())
                c3.metric("Pending Qty", f"{df['remaining_quantity_to_deliver'].sum():,.0f}")

        except Exception as e:
            st.error(f"Preview error: {e}")
            logger.error(f"Preview error: {e}", exc_info=True)


# ═════════════════════════════════════════════════════════════════
# Send
# ═════════════════════════════════════════════════════════════════

def _render_send_section(data_loader, email_sender, notif_type, recip_type,
                         selected, contacts, custom, sales_df, cc_emails, weeks):
    st.subheader("📤 Send Emails")

    # Count
    if notif_type == "🛃 Custom Clearance":
        count_str = f"customs team ({', '.join(cc_emails)})"
    elif recip_type == "creators":
        count_str = f"{len(selected)} sales people"
    elif recip_type == "customers":
        count_str = f"{len(contacts)} customer contacts"
    else:
        count_str = f"{len(custom)} custom recipients"

    st.warning(f"⚠️ About to send **{notif_type}** emails to {count_str}")
    confirm = st.checkbox("I confirm to send these emails", key="email_confirm_send")

    if confirm and st.button("🚀 Send Emails Now", type="primary", key="email_send_btn"):
        results, errors = _execute_send(
            data_loader, email_sender, notif_type, recip_type,
            selected, contacts, custom, sales_df, cc_emails, weeks
        )
        _show_results(results, errors)


def _execute_send(data_loader, email_sender, notif_type, recip_type,
                  selected, contacts, custom, sales_df, cc_emails, weeks):
    """Execute email sending with progress bar"""
    progress = st.progress(0)
    status = st.empty()
    results = []
    errors = []

    try:
        if notif_type == "🛃 Custom Clearance":
            status.text("Sending customs clearance schedule...")
            df = data_loader.get_customs_clearance_schedule(weeks)
            if not df.empty:
                ok, msg = email_sender.send_customs_clearance_email(
                    cc_emails[0], df, cc_emails=cc_emails[1:] if len(cc_emails) > 1 else None)
                results.append({'Recipient': 'Customs Team', 'Email': cc_emails[0],
                                'Status': '✅' if ok else '❌', 'Message': msg})
            progress.progress(1.0)

        elif recip_type == "customers":
            for i, ct in enumerate(contacts):
                progress.progress((i + 1) / len(contacts))
                status.text(f"Sending to {ct['contact_name']}... ({i+1}/{len(contacts)})")
                try:
                    df = data_loader.get_customer_deliveries(ct['customer'], weeks)
                    if not df.empty:
                        ok, msg = email_sender.send_delivery_schedule_email(
                            ct['email'], ct['customer'], df,
                            cc_emails=cc_emails or None,
                            notification_type=notif_type, weeks_ahead=weeks,
                            contact_name=ct['contact_name'])
                        results.append({'Recipient': f"{ct['contact_name']} ({ct['customer']})",
                                        'Email': ct['email'],
                                        'Status': '✅' if ok else '❌', 'Message': msg})
                    else:
                        results.append({'Recipient': ct['contact_name'], 'Email': ct['email'],
                                        'Status': '⚠️ Skip', 'Message': 'No deliveries'})
                except Exception as e:
                    errors.append(str(e))
                    results.append({'Recipient': ct['contact_name'], 'Email': ct['email'],
                                    'Status': '❌', 'Message': str(e)})

        elif recip_type == "custom":
            for i, email in enumerate(custom):
                progress.progress((i + 1) / len(custom))
                status.text(f"Sending to {email}... ({i+1}/{len(custom)})")
                try:
                    name = email.split('@')[0].title()
                    df = (data_loader.get_all_deliveries_summary(weeks) if notif_type == "📅 Delivery Schedule"
                          else data_loader.get_all_urgent_deliveries())
                    if not df.empty:
                        ok, msg = email_sender.send_delivery_schedule_email(
                            email, name, df, cc_emails=cc_emails or None,
                            notification_type=notif_type, weeks_ahead=weeks)
                        results.append({'Recipient': name, 'Email': email,
                                        'Status': '✅' if ok else '❌', 'Message': msg})
                    else:
                        results.append({'Recipient': name, 'Email': email,
                                        'Status': '⚠️ Skip', 'Message': 'No deliveries'})
                except Exception as e:
                    errors.append(str(e))
                    results.append({'Recipient': email, 'Email': email,
                                    'Status': '❌', 'Message': str(e)})

        else:  # creators
            for i, name in enumerate(selected):
                progress.progress((i + 1) / len(selected))
                status.text(f"Sending to {name}... ({i+1}/{len(selected)})")
                try:
                    info = sales_df[sales_df['name'] == name].iloc[0]
                    df = (data_loader.get_sales_delivery_summary(name, weeks)
                          if notif_type == "📅 Delivery Schedule"
                          else data_loader.get_sales_urgent_deliveries(name))
                    if not df.empty:
                        ok, msg = email_sender.send_delivery_schedule_email(
                            info['email'], name, df, cc_emails=cc_emails or None,
                            notification_type=notif_type, weeks_ahead=weeks)
                        results.append({'Recipient': name, 'Email': info['email'],
                                        'Status': '✅' if ok else '❌', 'Message': msg})
                    else:
                        results.append({'Recipient': name, 'Email': info['email'],
                                        'Status': '⚠️ Skip', 'Message': 'No deliveries'})
                except Exception as e:
                    errors.append(str(e))
                    results.append({'Recipient': name, 'Email': 'N/A',
                                    'Status': '❌', 'Message': str(e)})

    except Exception as e:
        st.error(f"Critical error: {e}")
        logger.error(f"Send error: {e}", exc_info=True)

    progress.empty()
    status.empty()
    return results, errors


def _show_results(results, errors):
    if not results:
        return
    st.success("✅ Email process completed!")
    df = pd.DataFrame(results)
    c1, c2, c3 = st.columns(3)
    c1.metric("Success", len(df[df['Status'] == '✅']))
    c2.metric("Failed", len(df[df['Status'] == '❌']))
    c3.metric("Skipped", len(df[df['Status'].str.contains('Skip', na=False)]))
    st.dataframe(df, width="stretch", hide_index=True)
    if errors:
        with st.expander("❌ Error Details"):
            for e in errors:
                st.error(e)