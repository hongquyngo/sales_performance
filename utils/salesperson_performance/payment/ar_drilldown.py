# utils/salesperson_performance/payment/ar_drilldown.py
"""
AR Drill-Down UI for Salesperson Performance — Payment & Collection Tab.

4-level navigation:
  Level 1: Salesperson Summary + Top Customers Overview (with stacked chart)
  Level 2: Customer breakdown (per salesperson) — absorbs old Customer Analysis tab
  Level 3: Invoice list (per customer) with VAT#, documents, payment details
  Level 4: Payment transactions with document links

v2.1 CHANGES:
- Added VAT invoice number (vat_number) in invoice list
- Added payment details inline for Partially Paid invoices (auto-load)
- Added S3 document links for sale invoices and payment receipts
- New callbacks: doc_loader, s3_url_generator
- Absorbed Customer Analysis tab into Level 1 (top customers chart) + Level 2
- Fixed double-count bug: dedup by invoice line before summing actual amounts
- Unassigned: collection rate shows "N/A" instead of misleading "0%"
- Unassigned section visually separated in Level 1

VERSION: 2.1.0
"""

import logging
from datetime import date
from typing import Optional, Callable
import pandas as pd
import numpy as np
import streamlit as st
import altair as alt

from .payment_analysis import (
    REV_COL,
    GP_COL,
    LINE_OUTSTANDING_COL,
    LINE_COLLECTED_COL,
    ACTUAL_REVENUE_COL,
    _fmt_currency,
)

logger = logging.getLogger(__name__)


# =============================================================================
# HELPERS
# =============================================================================

def _dedup_for_actual_amounts(df: pd.DataFrame) -> pd.DataFrame:
    """
    Deduplicate multi-split rows before summing actual line amounts.

    When using line_outstanding_usd (actual, not split-allocated), multi-split
    invoices have duplicate rows (1 per split) with the same actual amount.
    Summing without dedup would double-count.
    """
    if 'si_line_id' in df.columns:
        return df.drop_duplicates(subset='si_line_id', keep='first')
    elif 'unified_line_id' in df.columns:
        return df.drop_duplicates(subset='unified_line_id', keep='first')
    elif 'inv_number' in df.columns and 'product_pn' in df.columns:
        return df.drop_duplicates(subset=['inv_number', 'product_pn'], keep='first')
    return df


def _fmt_days(d) -> str:
    """Format days overdue for display."""
    d = int(d)
    if d > 0:
        return f"⚠️ {d}d overdue"
    elif d < 0:
        return f"due in {abs(d)}d"
    return "due today"


def _get_file_icon(filename: str) -> str:
    """Get emoji icon based on file type."""
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    return {'pdf': '📄', 'png': '🖼️', 'jpg': '🖼️', 'jpeg': '🖼️'}.get(ext, '📎')


# =============================================================================
# LEVEL 1: SALESPERSON AR SUMMARY + TOP CUSTOMERS
# =============================================================================

def ar_by_salesperson_fragment(
    pay_df: pd.DataFrame,
    payment_txn_loader=None,
    doc_loader: Callable = None,
    s3_url_generator: Callable = None,
    fragment_key: str = "ar_drill",
):
    """
    Salesperson-level AR drill-down with integrated customer overview.

    Args:
        pay_df: Filtered AR data (from payment_tab_fragment)
        payment_txn_loader: Callable(invoice_numbers) → DataFrame of payment transactions
        doc_loader: Callable(invoice_numbers) → DataFrame of document metadata (s3_key, etc.)
        s3_url_generator: Callable(s3_key) → presigned URL string
        fragment_key: Widget key prefix
    """
    if pay_df.empty:
        st.info("No AR data for selected filters")
        return

    # =========================================================================
    # BUILD SALESPERSON SUMMARY
    # =========================================================================
    has_line_outstanding = LINE_OUTSTANDING_COL in pay_df.columns
    out_col = 'outstanding_usd'  # split-allocated
    line_out_col = LINE_OUTSTANDING_COL if has_line_outstanding else out_col

    today = pd.Timestamp(date.today())

    # Build summary per salesperson
    sp_list = sorted(pay_df['sales_name'].unique().tolist())

    assigned_metrics = []
    unassigned_metrics = []

    for sp_name in sp_list:
        sp_data = pay_df[pay_df['sales_name'] == sp_name]
        is_unassigned = sp_name == 'Unassigned'

        outstanding = sp_data[line_out_col].sum() if is_unassigned else sp_data[out_col].sum()
        collected = sp_data['collected_usd'].sum() if not is_unassigned else 0
        invoiced = sp_data[REV_COL].sum() if not is_unassigned else sp_data[line_out_col].sum()

        n_customers = sp_data['customer'].nunique()
        n_invoices = sp_data['inv_number'].nunique() if 'inv_number' in sp_data.columns else len(sp_data)

        # Overdue
        if 'due_date' in sp_data.columns:
            use_col = out_col if not is_unassigned else line_out_col
            overdue_mask = (
                sp_data['due_date'].notna() &
                (sp_data['due_date'] < today) &
                (sp_data[use_col] > 0.01)
            )
            overdue_amount = sp_data.loc[overdue_mask, use_col].sum()
        else:
            overdue_amount = 0

        if is_unassigned:
            collection_rate = None
        else:
            collection_rate = collected / invoiced if invoiced > 0 else 0

        row = {
            'sales_name': sp_name,
            'outstanding': outstanding,
            'collected': collected,
            'invoiced': invoiced,
            'collection_rate': collection_rate,
            'overdue': overdue_amount,
            'customers': n_customers,
            'invoices': n_invoices,
            'is_unassigned': is_unassigned,
        }

        if is_unassigned:
            unassigned_metrics.append(row)
        else:
            assigned_metrics.append(row)

    sp_summary = pd.DataFrame(assigned_metrics + unassigned_metrics)
    if sp_summary.empty:
        st.info("No salesperson data available")
        return

    sp_summary = sp_summary.sort_values('outstanding', ascending=False).reset_index(drop=True)

    # =========================================================================
    # RENDER: Assigned Salesperson Table
    # =========================================================================
    st.markdown("##### 👤 AR by Salesperson")

    assigned_df = sp_summary[~sp_summary['is_unassigned']]
    if not assigned_df.empty:
        display_sp = assigned_df.copy()
        display_sp['#'] = range(1, len(display_sp) + 1)
        display_sp['Outstanding'] = display_sp['outstanding'].apply(_fmt_currency)
        display_sp['Overdue'] = display_sp['overdue'].apply(
            lambda x: _fmt_currency(x) if x > 0 else "—"
        )
        display_sp['Rate'] = display_sp['collection_rate'].apply(
            lambda x: f"{x:.0%}" if x is not None and x > 0 else "—"
        )
        display_sp['Cust.'] = display_sp['customers'].astype(int)
        display_sp['Inv.'] = display_sp['invoices'].astype(int)

        st.dataframe(
            display_sp[['#', 'sales_name', 'Outstanding', 'Overdue', 'Rate', 'Cust.', 'Inv.']].rename(
                columns={'sales_name': 'Salesperson'}
            ),
            hide_index=True,
            width="stretch",
            height=min(400, 35 * len(display_sp) + 38),
        )

    # =========================================================================
    # RENDER: Unassigned Section (visually separated)
    # =========================================================================
    unassigned_df = sp_summary[sp_summary['is_unassigned']]
    if not unassigned_df.empty:
        ua = unassigned_df.iloc[0]
        st.warning(
            f"⚠️ **Unassigned AR**: {_fmt_currency(ua['outstanding'])} outstanding "
            f"— {int(ua['customers'])} customers, {int(ua['invoices'])} invoices"
            + (f" · {_fmt_currency(ua['overdue'])} overdue" if ua['overdue'] > 0 else ""),
            icon="⚠️",
        )

    # =========================================================================
    # TOP CUSTOMERS CHART (absorbed from old Customer Analysis tab)
    # =========================================================================
    if has_line_outstanding and len(pay_df['customer'].unique()) > 1:
        _render_top_customers_chart(pay_df, fragment_key)

    # =========================================================================
    # LEVEL 2: Salesperson drill-down selector
    # =========================================================================
    st.divider()

    selected_sp = st.selectbox(
        "🔍 Drill down into salesperson",
        options=['— Select —'] + sp_summary['sales_name'].tolist(),
        key=f"{fragment_key}_sp_select",
    )

    if selected_sp == '— Select —':
        st.caption("Select a salesperson above to see customer and invoice breakdown")
        return

    sp_data = pay_df[pay_df['sales_name'] == selected_sp].copy()
    is_unassigned = selected_sp == 'Unassigned'

    _render_customer_breakdown(
        sp_data=sp_data,
        sales_name=selected_sp,
        is_unassigned=is_unassigned,
        payment_txn_loader=payment_txn_loader,
        doc_loader=doc_loader,
        s3_url_generator=s3_url_generator,
        fragment_key=f"{fragment_key}_{selected_sp[:8]}",
    )


# =============================================================================
# TOP CUSTOMERS STACKED BAR CHART
# =============================================================================

def _render_top_customers_chart(pay_df: pd.DataFrame, fragment_key: str):
    """
    Stacked bar chart: top 10 customers by outstanding (Collected vs Outstanding).
    Uses deduped actual line amounts to avoid double-counting.
    """
    deduped = _dedup_for_actual_amounts(pay_df)

    use_actual = LINE_OUTSTANDING_COL in deduped.columns
    rev_col = ACTUAL_REVENUE_COL if use_actual and ACTUAL_REVENUE_COL in deduped.columns else REV_COL
    out_col = LINE_OUTSTANDING_COL if use_actual else 'outstanding_usd'
    coll_col = LINE_COLLECTED_COL if use_actual and LINE_COLLECTED_COL in deduped.columns else 'collected_usd'

    cust_agg = deduped.groupby('customer').agg(
        invoiced=(rev_col, 'sum'),
        collected=(coll_col, 'sum'),
        outstanding=(out_col, 'sum'),
    ).reset_index()

    top10 = cust_agg.nlargest(10, 'invoiced').copy()
    if len(top10) < 2:
        return

    st.markdown("##### 📊 Top Customers — Collected vs Outstanding")
    if use_actual:
        st.caption("Actual invoice amounts (not split-allocated)")

    melted = top10.melt(
        id_vars=['customer'],
        value_vars=['collected', 'outstanding'],
        var_name='type', value_name='amount'
    )
    melted['type'] = melted['type'].map({
        'collected': 'Collected', 'outstanding': 'Outstanding'
    })

    chart = alt.Chart(melted).mark_bar().encode(
        y=alt.Y('customer:N', sort='-x', title=None,
                axis=alt.Axis(labelLimit=200)),
        x=alt.X('amount:Q', title='Amount (USD)',
                axis=alt.Axis(format='~s')),
        color=alt.Color('type:N', scale=alt.Scale(
            domain=['Collected', 'Outstanding'],
            range=['#28a745', '#dc3545']
        ), legend=alt.Legend(orient='top', title=None)),
        order=alt.Order('type:N', sort='ascending'),
        tooltip=[
            alt.Tooltip('customer:N', title='Customer'),
            alt.Tooltip('type:N', title='Type'),
            alt.Tooltip('amount:Q', title='Amount', format='$,.0f'),
        ]
    ).properties(height=350)

    st.altair_chart(chart, width="stretch")


# =============================================================================
# LEVEL 2: CUSTOMER BREAKDOWN (per salesperson)
# =============================================================================

def _render_customer_breakdown(
    sp_data: pd.DataFrame,
    sales_name: str,
    is_unassigned: bool,
    payment_txn_loader=None,
    doc_loader: Callable = None,
    s3_url_generator: Callable = None,
    fragment_key: str = "ar_cust",
):
    """
    Customer-level breakdown for a single salesperson.
    v2.1: Passes doc_loader and s3_url_generator through to Level 3.
    """
    use_actual = is_unassigned and LINE_OUTSTANDING_COL in sp_data.columns
    out_col = LINE_OUTSTANDING_COL if use_actual else 'outstanding_usd'
    today = pd.Timestamp(date.today())

    # DEDUP: When using actual line amounts, dedup to avoid double-counting
    agg_source = _dedup_for_actual_amounts(sp_data) if use_actual else sp_data

    # Aggregate by customer
    has_inv = 'inv_number' in agg_source.columns
    agg = {
        'outstanding': (out_col, 'sum'),
    }
    if has_inv:
        agg['invoices'] = ('inv_number', 'nunique')
    else:
        agg['invoices'] = (out_col, 'count')

    # LC outstanding for display
    if 'line_outstanding_lc' in agg_source.columns:
        agg['outstanding_lc'] = ('line_outstanding_lc', 'sum')
    if 'invoiced_currency' in agg_source.columns:
        agg['currency'] = ('invoiced_currency', 'first')

    # Overdue amount per customer
    if 'due_date' in agg_source.columns:
        overdue_source = agg_source[
            (agg_source['due_date'].notna()) &
            (agg_source['due_date'] < today) &
            (agg_source[out_col] > 0.01)
        ]
        if not overdue_source.empty:
            overdue_by_cust = overdue_source.groupby('customer').agg(
                overdue=(out_col, 'sum'),
            ).reset_index()
        else:
            overdue_by_cust = pd.DataFrame(columns=['customer', 'overdue'])
    else:
        overdue_by_cust = pd.DataFrame(columns=['customer', 'overdue'])

    cust_summary = agg_source.groupby('customer').agg(**agg).reset_index()

    # Merge overdue
    if not overdue_by_cust.empty:
        cust_summary = cust_summary.merge(overdue_by_cust, on='customer', how='left')
        cust_summary['overdue'] = cust_summary['overdue'].fillna(0)
    else:
        cust_summary['overdue'] = 0

    # Sort options
    sort_col_map = {
        'Outstanding (high→low)': ('outstanding', False),
        'Overdue (high→low)': ('overdue', False),
        'Invoices (high→low)': ('invoices', False),
    }
    sort_label = st.selectbox(
        "Sort customers by",
        list(sort_col_map.keys()),
        key=f"{fragment_key}_cust_sort",
    )
    s_col, s_asc = sort_col_map[sort_label]
    cust_summary = cust_summary.sort_values(s_col, ascending=s_asc).reset_index(drop=True)

    # Header metrics
    total_outstanding = cust_summary['outstanding'].sum()
    total_customers = len(cust_summary)
    total_invoices = int(cust_summary['invoices'].sum())
    total_overdue = cust_summary['overdue'].sum()

    label = f"⚠️ {sales_name}" if is_unassigned else f"👤 {sales_name}"
    st.markdown(f"##### {label}")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Outstanding", _fmt_currency(total_outstanding))
    with c2:
        if total_overdue > 0:
            st.metric("Overdue", _fmt_currency(total_overdue))
        else:
            st.metric("Overdue", "—")
    with c3:
        st.metric("Customers", f"{total_customers}")
    with c4:
        st.metric("Invoices", f"{total_invoices}")

    # =========================================================================
    # Customer table with expandable invoice details
    # =========================================================================
    st.markdown("---")

    for idx, cust_row in cust_summary.iterrows():
        cust_name = cust_row['customer']
        cust_out = cust_row['outstanding']
        cust_inv_count = int(cust_row['invoices'])
        cust_overdue = cust_row.get('overdue', 0)

        # Currency info
        lc_text = ""
        if 'outstanding_lc' in cust_row and 'currency' in cust_row:
            lc_val = cust_row.get('outstanding_lc', 0)
            ccy = cust_row.get('currency', '')
            if pd.notna(lc_val) and lc_val > 0 and ccy:
                lc_text = f" · {lc_val:,.0f} {ccy}"

        # Overdue indicator in label
        overdue_text = ""
        if cust_overdue > 0:
            overdue_text = f" · 🔴 {_fmt_currency(cust_overdue)} overdue"

        expander_label = (
            f"**{cust_name}** — {_fmt_currency(cust_out)}{lc_text} "
            f"({cust_inv_count} inv.){overdue_text}"
        )

        with st.expander(expander_label, expanded=False):
            _render_invoice_list(
                inv_data=sp_data[sp_data['customer'] == cust_name],
                payment_txn_loader=payment_txn_loader,
                doc_loader=doc_loader,
                s3_url_generator=s3_url_generator,
                fragment_key=f"{fragment_key}_c{idx}",
            )


# =============================================================================
# LEVEL 3: INVOICE LIST (per customer) — select row for detail + documents
# =============================================================================

def _render_invoice_list(
    inv_data: pd.DataFrame,
    payment_txn_loader=None,
    doc_loader: Callable = None,
    s3_url_generator: Callable = None,
    fragment_key: str = "ar_inv",
):
    """
    Invoice-level detail for a single customer.

    v2.2: Per-invoice selection UX.
    - Invoice table at top
    - Selectbox to pick specific invoice
    - Detail panel: payment transactions + document links for selected invoice only
    """
    if inv_data.empty:
        st.caption("No invoices")
        return

    # Deduplicate: if multi-split, same invoice appears multiple times
    if 'inv_number' in inv_data.columns:
        display = inv_data.drop_duplicates(subset='inv_number', keep='first').copy()
    else:
        display = inv_data.copy()

    # Sort by outstanding DESC
    out_col = LINE_OUTSTANDING_COL if LINE_OUTSTANDING_COL in display.columns else 'outstanding_usd'
    display = display.sort_values(out_col, ascending=False).reset_index(drop=True)

    # Build display columns
    cols = []
    col_config = {}

    if 'inv_number' in display.columns:
        cols.append('inv_number')
        col_config['inv_number'] = st.column_config.TextColumn("Invoice#")

    if 'vat_number' in display.columns:
        cols.append('vat_number')
        col_config['vat_number'] = st.column_config.TextColumn("VAT Inv#",
            help="VAT invoice number from sale_invoices")

    for dc, label in [('inv_date', 'Inv Date'), ('due_date', 'Due Date')]:
        if dc in display.columns:
            cols.append(dc)
            col_config[dc] = st.column_config.DateColumn(label)

    if 'product_pn' in display.columns:
        cols.append('product_pn')
        col_config['product_pn'] = st.column_config.TextColumn("Product", width="medium")

    if 'invoiced_currency' in display.columns:
        cols.append('invoiced_currency')
        col_config['invoiced_currency'] = st.column_config.TextColumn("Ccy")

    if 'line_invoiced_amount_lc' in display.columns:
        display['_inv_lc'] = display['line_invoiced_amount_lc'].apply(
            lambda x: f"{x:,.0f}" if pd.notna(x) else "0"
        )
        cols.append('_inv_lc')
        col_config['_inv_lc'] = st.column_config.TextColumn("Invoiced (LC)")

    if 'line_outstanding_lc' in display.columns:
        display['_os_lc'] = display['line_outstanding_lc'].apply(
            lambda x: f"{x:,.0f}" if pd.notna(x) else "0"
        )
        cols.append('_os_lc')
        col_config['_os_lc'] = st.column_config.TextColumn("Outstanding (LC)")

    if out_col in display.columns:
        display['_os_usd'] = display[out_col].apply(
            lambda x: f"${x:,.0f}" if pd.notna(x) else "$0"
        )
        cols.append('_os_usd')
        col_config['_os_usd'] = st.column_config.TextColumn("Outstanding (USD)")

    if 'payment_status' in display.columns:
        cols.append('payment_status')
        col_config['payment_status'] = st.column_config.TextColumn("Status")

    if 'payment_ratio' in display.columns:
        display['_ratio'] = display['payment_ratio'].apply(
            lambda x: f"{x:.0%}" if pd.notna(x) else "0%"
        )
        cols.append('_ratio')
        col_config['_ratio'] = st.column_config.TextColumn("Paid%")

    if 'aging_bucket' in display.columns:
        cols.append('aging_bucket')
        col_config['aging_bucket'] = st.column_config.TextColumn("Aging")

    if 'days_overdue' in display.columns:
        display['_days'] = pd.to_numeric(display['days_overdue'], errors='coerce').fillna(0).astype(int)
        cols.append('_days')
        col_config['_days'] = st.column_config.NumberColumn("Days O/D", format="%d")

    available = [c for c in cols if c in display.columns]
    if not available:
        st.caption("No display columns available")
        return

    st.dataframe(
        display[available],
        column_config=col_config,
        hide_index=True,
        width="stretch",
        height=min(300, 35 * len(display) + 38),
    )

    # =========================================================================
    # PER-INVOICE DETAIL SELECTOR
    # =========================================================================
    if 'inv_number' not in display.columns:
        return

    inv_list = display['inv_number'].dropna().tolist()
    if not inv_list:
        return

    # Build display labels: "INV123 | Unpaid | $5,000 | 90+ days"
    inv_labels = {}
    for _, row in display.iterrows():
        inv_num = row.get('inv_number', '')
        if pd.isna(inv_num):
            continue
        status = row.get('payment_status', '')
        os_usd = row.get('_os_usd', '')
        aging = row.get('aging_bucket', '')
        label_parts = [str(inv_num)]
        if status:
            label_parts.append(str(status))
        if os_usd:
            label_parts.append(str(os_usd))
        if aging:
            label_parts.append(str(aging))
        inv_labels[str(inv_num)] = ' · '.join(label_parts)

    selected_inv = st.selectbox(
        "🔍 Select invoice for details",
        options=['— Select invoice —'] + list(inv_labels.keys()),
        format_func=lambda x: inv_labels.get(x, x) if x != '— Select invoice —' else x,
        key=f"{fragment_key}_inv_select",
    )

    if selected_inv == '— Select invoice —':
        st.caption("Select an invoice above to view payment details and documents")
        return

    # =========================================================================
    # SELECTED INVOICE DETAIL PANEL
    # =========================================================================
    sel_row = display[display['inv_number'] == selected_inv].iloc[0] if not display[display['inv_number'] == selected_inv].empty else None
    if sel_row is None:
        return

    with st.container(border=True):
        # Header
        vat_num = sel_row.get('vat_number', '')
        vat_display = f" · VAT: {vat_num}" if pd.notna(vat_num) and vat_num else ""
        st.markdown(f"**{selected_inv}**{vat_display}")

        # Key info row
        ic1, ic2, ic3, ic4 = st.columns(4)
        with ic1:
            inv_date = sel_row.get('inv_date', '')
            due_date = sel_row.get('due_date', '')
            inv_str = pd.Timestamp(inv_date).strftime('%Y-%m-%d') if pd.notna(inv_date) else '—'
            due_str = pd.Timestamp(due_date).strftime('%Y-%m-%d') if pd.notna(due_date) else '—'
            st.caption(f"📅 Inv: {inv_str} · Due: {due_str}")
        with ic2:
            st.caption(f"💰 O/S: {sel_row.get('_os_usd', '—')}")
        with ic3:
            status = sel_row.get('payment_status', '—')
            ratio = sel_row.get('_ratio', '0%')
            st.caption(f"📊 {status} · {ratio}")
        with ic4:
            aging = sel_row.get('aging_bucket', '')
            days = sel_row.get('_days', 0)
            if aging:
                st.caption(f"⏰ {aging} ({days}d)")

        # -----------------------------------------------------------------
        # Tab layout: Payment History | Documents
        # -----------------------------------------------------------------
        has_txn_loader = payment_txn_loader is not None
        has_doc_loader = doc_loader is not None

        if has_txn_loader or has_doc_loader:
            detail_tabs = []
            tab_keys = []
            if has_txn_loader:
                detail_tabs.append("💳 Payment History")
                tab_keys.append("txn")
            if has_doc_loader:
                detail_tabs.append("📎 Documents")
                tab_keys.append("docs")

            tabs = st.tabs(detail_tabs)

            for tab, tab_key in zip(tabs, tab_keys):
                with tab:
                    if tab_key == "txn":
                        _render_invoice_payments(
                            inv_number=selected_inv,
                            payment_txn_loader=payment_txn_loader,
                            fragment_key=f"{fragment_key}_txn_{selected_inv[:12]}",
                        )
                    elif tab_key == "docs":
                        _render_invoice_documents(
                            inv_number=selected_inv,
                            doc_loader=doc_loader,
                            s3_url_generator=s3_url_generator,
                            fragment_key=f"{fragment_key}_doc_{selected_inv[:12]}",
                        )


# =============================================================================
# PER-INVOICE: PAYMENT HISTORY
# =============================================================================

def _render_invoice_payments(
    inv_number: str,
    payment_txn_loader: Callable,
    fragment_key: str = "ar_inv_txn",
):
    """Load and display payment transactions for a single invoice."""
    try:
        txn_df = payment_txn_loader([inv_number])
    except Exception as e:
        logger.error(f"Error loading payment transactions for {inv_number}: {e}")
        st.caption(f"⚠️ Could not load payment details")
        return

    if txn_df is None or txn_df.empty:
        st.caption("No payment transactions recorded for this invoice")
        return

    # Display columns
    display = txn_df.copy()

    cols_map = {
        'payment_number': 'Payment#',
        'payment_received_date': 'Payment Date',
        'amount_received': 'Amount',
        'currency_code': 'Ccy',
        'payment_status': 'Status',
        'payment_ratio': 'Paid%',
        'receipt_bank': 'Bank',
        'aging_bucket': 'Aging',
    }

    available = {k: v for k, v in cols_map.items() if k in display.columns}
    if not available:
        st.caption("No payment data columns available")
        return

    if 'payment_ratio' in display.columns:
        display['payment_ratio'] = display['payment_ratio'].apply(
            lambda x: f"{x:.0%}" if pd.notna(x) else "—"
        )

    st.dataframe(
        display[list(available.keys())].rename(columns=available),
        hide_index=True,
        width="stretch",
        height=min(250, 35 * len(display) + 38),
    )

    # Summary
    if 'amount_received_raw' in txn_df.columns and 'currency_code' in txn_df.columns:
        by_ccy = txn_df.groupby('currency_code')['amount_received_raw'].sum()
        summary_parts = [f"{amt:,.0f} {ccy}" for ccy, amt in by_ccy.items()]
        st.caption(f"Total received: {' + '.join(summary_parts)} ({len(txn_df)} transactions)")


# =============================================================================
# PER-INVOICE: DOCUMENTS (S3 links)
# =============================================================================

def _render_invoice_documents(
    inv_number: str,
    doc_loader: Callable,
    s3_url_generator: Callable = None,
    fragment_key: str = "ar_inv_doc",
):
    """Load and display documents for a single invoice."""
    try:
        docs_df = doc_loader([inv_number])
    except Exception as e:
        logger.error(f"Error loading documents for {inv_number}: {e}")
        st.caption(f"⚠️ Could not load documents")
        return

    if docs_df is None or docs_df.empty:
        st.caption("No documents attached to this invoice")
        return

    # Group by doc_type
    inv_docs = docs_df[docs_df['doc_type'] == 'invoice'] if 'doc_type' in docs_df.columns else pd.DataFrame()
    pmt_docs = docs_df[docs_df['doc_type'] == 'payment'] if 'doc_type' in docs_df.columns else pd.DataFrame()

    # Render invoice documents
    if not inv_docs.empty:
        st.markdown(f"**📄 Invoice Documents** ({len(inv_docs)})")
        for _, doc in inv_docs.iterrows():
            _render_doc_link(doc, s3_url_generator)

    # Render payment receipt documents
    if not pmt_docs.empty:
        st.markdown(f"**💳 Payment Receipts** ({len(pmt_docs)})")
        for _, doc in pmt_docs.iterrows():
            pmt_label = f" ({doc['payment_number']})" if pd.notna(doc.get('payment_number')) else ""
            _render_doc_link(doc, s3_url_generator, extra_label=pmt_label)

    if inv_docs.empty and pmt_docs.empty:
        st.markdown("**📎 Documents**")
        for _, doc in docs_df.iterrows():
            _render_doc_link(doc, s3_url_generator)


def _render_doc_link(doc: pd.Series, s3_url_generator: Callable = None, extra_label: str = ""):
    """Render a single document link with icon and presigned URL."""
    filename = doc.get('filename', 'Unknown')
    s3_key = doc.get('s3_key', '')
    icon = _get_file_icon(filename)
    inv_num = doc.get('invoice_number', '')

    if s3_url_generator and s3_key:
        try:
            url = s3_url_generator(s3_key)
            if url:
                st.markdown(
                    f"{icon} [{filename}]({url}){extra_label} "
                    f"— {inv_num}",
                    unsafe_allow_html=False,
                )
                return
        except Exception as e:
            logger.warning(f"Failed to generate URL for {s3_key}: {e}")

    # Fallback: show filename without link
    st.caption(f"{icon} {filename}{extra_label} — {inv_num} (S3: {s3_key})")