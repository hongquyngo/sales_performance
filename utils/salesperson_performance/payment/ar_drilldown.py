# utils/salesperson_performance/payment/ar_drilldown.py
"""
AR Drill-Down UI for Salesperson Performance — Payment & Collection Tab.

3-level navigation:
  Level 1: Salesperson Summary (cards with KPI metrics)
  Level 2: Customer breakdown (per salesperson)
  Level 3: Invoice list (per customer) with expandable payment details

Payment transaction data comes from customer_payment_full_view.

VERSION: 1.0.0
"""

import logging
from datetime import date
from typing import Optional
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
# LEVEL 1: SALESPERSON AR SUMMARY
# =============================================================================

def ar_by_salesperson_fragment(
    pay_df: pd.DataFrame,
    payment_txn_loader=None,
    fragment_key: str = "ar_drill",
):
    """
    Salesperson-level AR drill-down.

    Args:
        pay_df: Filtered AR data (from payment_tab_fragment)
        payment_txn_loader: Callable(invoice_numbers) → DataFrame of payment transactions
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

    # Compute per-salesperson metrics
    sp_metrics = []
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
            overdue_mask = (
                sp_data['due_date'].notna() &
                (sp_data['due_date'] < today) &
                (sp_data[out_col if not is_unassigned else line_out_col] > 0.01)
            )
            overdue_amount = sp_data.loc[overdue_mask, out_col if not is_unassigned else line_out_col].sum()
        else:
            overdue_amount = 0

        collection_rate = collected / invoiced if invoiced > 0 else 0

        sp_metrics.append({
            'sales_name': sp_name,
            'outstanding': outstanding,
            'collected': collected,
            'invoiced': invoiced,
            'collection_rate': collection_rate,
            'overdue': overdue_amount,
            'customers': n_customers,
            'invoices': n_invoices,
            'is_unassigned': is_unassigned,
        })

    sp_summary = pd.DataFrame(sp_metrics).sort_values('outstanding', ascending=False)

    # =========================================================================
    # RENDER: Salesperson selector
    # =========================================================================
    st.markdown("##### 👤 AR by Salesperson")

    # Summary table first
    display_sp = sp_summary.copy()
    display_sp['#'] = range(1, len(display_sp) + 1)
    display_sp['Outstanding'] = display_sp['outstanding'].apply(_fmt_currency)
    display_sp['Overdue'] = display_sp['overdue'].apply(
        lambda x: _fmt_currency(x) if x > 0 else "—"
    )
    display_sp['Rate'] = display_sp['collection_rate'].apply(
        lambda x: f"{x:.0%}" if x > 0 else "—"
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
        fragment_key=f"{fragment_key}_{selected_sp[:8]}",
    )


# =============================================================================
# LEVEL 2: CUSTOMER BREAKDOWN (per salesperson)
# =============================================================================

def _render_customer_breakdown(
    sp_data: pd.DataFrame,
    sales_name: str,
    is_unassigned: bool,
    payment_txn_loader=None,
    fragment_key: str = "ar_cust",
):
    """Customer-level breakdown for a single salesperson."""

    out_col = LINE_OUTSTANDING_COL if is_unassigned and LINE_OUTSTANDING_COL in sp_data.columns else 'outstanding_usd'
    today = pd.Timestamp(date.today())

    # Aggregate by customer
    has_inv = 'inv_number' in sp_data.columns
    agg = {
        'outstanding': (out_col, 'sum'),
    }
    if has_inv:
        agg['invoices'] = ('inv_number', 'nunique')
    else:
        agg['invoices'] = (out_col, 'count')

    # LC outstanding for display
    if 'line_outstanding_lc' in sp_data.columns:
        agg['outstanding_lc'] = ('line_outstanding_lc', 'sum')
    if 'invoiced_currency' in sp_data.columns:
        agg['currency'] = ('invoiced_currency', 'first')

    cust_summary = sp_data.groupby('customer').agg(**agg).reset_index()
    cust_summary = cust_summary.sort_values('outstanding', ascending=False).reset_index(drop=True)

    # Header metrics
    total_outstanding = cust_summary['outstanding'].sum()
    total_customers = len(cust_summary)
    total_invoices = cust_summary['invoices'].sum()

    label = f"⚠️ {sales_name}" if is_unassigned else f"👤 {sales_name}"
    st.markdown(f"##### {label} — {total_customers} customers, {total_invoices} invoices")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Outstanding", _fmt_currency(total_outstanding))
    with c2:
        st.metric("Customers", f"{total_customers}")
    with c3:
        st.metric("Invoices", f"{total_invoices}")

    # =========================================================================
    # Customer table with expandable invoice details
    # =========================================================================
    st.markdown("---")

    for idx, cust_row in cust_summary.iterrows():
        cust_name = cust_row['customer']
        cust_out = cust_row['outstanding']
        cust_inv_count = int(cust_row['invoices'])

        # Currency info
        lc_text = ""
        if 'outstanding_lc' in cust_row and 'currency' in cust_row:
            lc_val = cust_row.get('outstanding_lc', 0)
            ccy = cust_row.get('currency', '')
            if pd.notna(lc_val) and lc_val > 0 and ccy:
                lc_text = f" · {lc_val:,.0f} {ccy}"

        expander_label = f"**{cust_name}** — {_fmt_currency(cust_out)}{lc_text} ({cust_inv_count} inv.)"

        with st.expander(expander_label, expanded=False):
            _render_invoice_list(
                inv_data=sp_data[sp_data['customer'] == cust_name],
                payment_txn_loader=payment_txn_loader,
                fragment_key=f"{fragment_key}_c{idx}",
            )


# =============================================================================
# LEVEL 3: INVOICE LIST (per customer)
# =============================================================================

def _render_invoice_list(
    inv_data: pd.DataFrame,
    payment_txn_loader=None,
    fragment_key: str = "ar_inv",
):
    """Invoice-level detail for a single customer."""
    if inv_data.empty:
        st.caption("No invoices")
        return

    # Deduplicate: if multi-split, same invoice appears multiple times
    # For invoice-level view, show each invoice once
    if 'inv_number' in inv_data.columns:
        display = inv_data.drop_duplicates(subset='inv_number', keep='first').copy()
    else:
        display = inv_data.copy()

    # Sort by outstanding DESC
    out_col = LINE_OUTSTANDING_COL if LINE_OUTSTANDING_COL in display.columns else 'outstanding_usd'
    display = display.sort_values(out_col, ascending=False)

    # Build display columns
    cols = []
    col_config = {}

    # Invoice number
    if 'inv_number' in display.columns:
        cols.append('inv_number')
        col_config['inv_number'] = st.column_config.TextColumn("Invoice#")

    # Dates
    for dc, label in [('inv_date', 'Inv Date'), ('due_date', 'Due Date')]:
        if dc in display.columns:
            cols.append(dc)
            col_config[dc] = st.column_config.DateColumn(label)

    # Product
    if 'product_pn' in display.columns:
        cols.append('product_pn')
        col_config['product_pn'] = st.column_config.TextColumn("Product", width="medium")

    # LC amounts
    if 'invoiced_currency' in display.columns:
        cols.append('invoiced_currency')
        col_config['invoiced_currency'] = st.column_config.TextColumn("Ccy")

    if 'line_invoiced_amount_lc' in display.columns:
        display['_inv_lc'] = display['line_invoiced_amount_lc'].apply(
            lambda x: f"{x:,.0f}" if pd.notna(x) else "0"
        )
        cols.append('_inv_lc')
        col_config['_inv_lc'] = st.column_config.TextColumn("Invoiced LC")

    if 'line_outstanding_lc' in display.columns:
        display['_os_lc'] = display['line_outstanding_lc'].apply(
            lambda x: f"{x:,.0f}" if pd.notna(x) else "0"
        )
        cols.append('_os_lc')
        col_config['_os_lc'] = st.column_config.TextColumn("O/S LC")

    # USD amounts
    if out_col in display.columns:
        display['_os_usd'] = display[out_col].apply(
            lambda x: f"${x:,.0f}" if pd.notna(x) else "$0"
        )
        cols.append('_os_usd')
        col_config['_os_usd'] = st.column_config.TextColumn("O/S USD")

    # Payment status
    if 'payment_status' in display.columns:
        cols.append('payment_status')
        col_config['payment_status'] = st.column_config.TextColumn("Status")

    if 'payment_ratio' in display.columns:
        display['_ratio'] = display['payment_ratio'].apply(
            lambda x: f"{x:.0%}" if pd.notna(x) else "0%"
        )
        cols.append('_ratio')
        col_config['_ratio'] = st.column_config.TextColumn("Paid%")

    # Aging
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
    # PAYMENT TRANSACTION DETAIL (expandable per invoice)
    # =========================================================================
    if payment_txn_loader is not None and 'inv_number' in display.columns:
        inv_numbers = display['inv_number'].dropna().unique().tolist()
        if inv_numbers:
            if st.button(
                "💳 Load Payment Transactions",
                key=f"{fragment_key}_load_txn",
                help="Load detailed payment transactions for these invoices"
            ):
                with st.spinner("Loading payment details..."):
                    txn_df = payment_txn_loader(inv_numbers)
                _render_payment_transactions(txn_df, fragment_key)


# =============================================================================
# LEVEL 4: PAYMENT TRANSACTIONS (from customer_payment_full_view)
# =============================================================================

def _render_payment_transactions(
    txn_df: pd.DataFrame,
    fragment_key: str = "ar_txn",
):
    """Render payment transaction details."""
    if txn_df is None or txn_df.empty:
        st.info("No payment transactions found for these invoices")
        return

    st.markdown("##### 💳 Payment Transactions")

    # Display columns
    display = txn_df.copy()

    cols_map = {
        'payment_number': 'Payment#',
        'sale_invoice_number': 'Invoice#',
        'payment_received_date': 'Payment Date',
        'amount_received': 'Amount Received',
        'currency_code': 'Ccy',
        'payment_status': 'Status',
        'payment_ratio': 'Paid%',
        'customer': 'Customer',
        'legal_entity': 'Entity',
        'receipt_bank': 'Bank',
        'days_outstanding': 'Days O/S',
        'aging_bucket': 'Aging',
        'created_by': 'Created By',
    }

    available = {k: v for k, v in cols_map.items() if k in display.columns}
    if not available:
        st.caption("No transaction columns available")
        return

    # Format payment_ratio
    if 'payment_ratio' in display.columns:
        display['payment_ratio'] = display['payment_ratio'].apply(
            lambda x: f"{x:.0%}" if pd.notna(x) else "—"
        )

    st.dataframe(
        display[list(available.keys())].rename(columns=available),
        hide_index=True,
        width="stretch",
        height=min(400, 35 * len(display) + 38),
    )

    # Summary
    if 'amount_received_raw' in txn_df.columns and 'currency_code' in txn_df.columns:
        by_ccy = txn_df.groupby('currency_code')['amount_received_raw'].sum()
        summary_parts = [f"{amt:,.0f} {ccy}" for ccy, amt in by_ccy.items()]
        st.caption(f"Total received: {' + '.join(summary_parts)} ({len(txn_df)} transactions)")
