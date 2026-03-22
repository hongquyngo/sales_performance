# utils/kpi_center_performance/payment/ar_drilldown.py
"""
AR Drill-Down UI for KPI Center Performance — Payment & Collection Tab.

Adapted from salesperson_performance/payment/ar_drilldown.py.

Levels:
  Level 1: KPI Center Summary + Top Customers Overview
  (Invoice detail with click-to-select handled by fragments.py)

VERSION: 1.0.0
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
    """Deduplicate multi-split rows before summing actual line amounts."""
    if 'unified_line_id' in df.columns:
        return df.drop_duplicates(subset='unified_line_id', keep='first')
    elif 'inv_number' in df.columns and 'product_pn' in df.columns:
        return df.drop_duplicates(subset=['inv_number', 'product_pn'], keep='first')
    return df


def _fmt_days(d) -> str:
    d = int(d)
    if d > 0:
        return f"⚠️ {d}d overdue"
    elif d < 0:
        return f"due in {abs(d)}d"
    return "due today"


def _get_file_icon(filename: str) -> str:
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    return {'pdf': '📄', 'png': '🖼️', 'jpg': '🖼️', 'jpeg': '🖼️'}.get(ext, '📎')


# =============================================================================
# AR SUMMARY SECTION (for combined Invoice Detail tab)
# =============================================================================

def ar_summary_section(
    pay_df: pd.DataFrame,
    fragment_key: str = "kpc_ar_summary",
):
    """
    Render AR by KPI Center summary table + Top Customers chart.

    Args:
        pay_df: Filtered AR data
        fragment_key: Widget key prefix
    """
    if pay_df.empty:
        st.info("No AR data for selected filters")
        return

    has_line_outstanding = LINE_OUTSTANDING_COL in pay_df.columns
    out_col = 'outstanding_usd'
    today = pd.Timestamp(date.today())

    # =========================================================================
    # AR by KPI Center table
    # =========================================================================
    if 'kpi_center' in pay_df.columns:
        kpc_list = sorted(pay_df['kpi_center'].dropna().unique().tolist())
        kpc_metrics = []

        for kpc_name in kpc_list:
            kpc_data = pay_df[pay_df['kpi_center'] == kpc_name]

            outstanding = kpc_data[out_col].sum()
            collected = kpc_data['collected_usd'].sum()
            invoiced = kpc_data[REV_COL].sum() if REV_COL in kpc_data.columns else 0

            n_customers = kpc_data['customer'].nunique() if 'customer' in kpc_data.columns else 0
            n_invoices = kpc_data['inv_number'].nunique() if 'inv_number' in kpc_data.columns else len(kpc_data)

            overdue_amount = 0
            if 'due_date' in kpc_data.columns:
                overdue_mask = (
                    kpc_data['due_date'].notna() &
                    (kpc_data['due_date'] < today) &
                    (kpc_data[out_col] > 0.01)
                )
                overdue_amount = kpc_data.loc[overdue_mask, out_col].sum()

            collection_rate = (collected / invoiced) if invoiced > 0 else 0

            kpc_metrics.append({
                'kpi_center': kpc_name,
                'outstanding': outstanding,
                'collected': collected,
                'invoiced': invoiced,
                'collection_rate': collection_rate,
                'overdue': overdue_amount,
                'customers': n_customers,
                'invoices': n_invoices,
            })

        kpc_summary = pd.DataFrame(kpc_metrics)
        if not kpc_summary.empty:
            kpc_summary = kpc_summary.sort_values('outstanding', ascending=False).reset_index(drop=True)

            st.markdown("##### 🎯 AR by KPI Center")
            display_kpc = kpc_summary.copy()
            display_kpc['#'] = range(1, len(display_kpc) + 1)
            display_kpc['Outstanding'] = display_kpc['outstanding'].apply(lambda x: f"${x:,.2f}")
            display_kpc['Overdue'] = display_kpc['overdue'].apply(
                lambda x: f"${x:,.2f}" if x > 0 else "—"
            )
            display_kpc['Rate'] = display_kpc['collection_rate'].apply(
                lambda x: f"{x:.1%}" if x > 0 else "—"
            )
            display_kpc['Cust.'] = display_kpc['customers'].astype(int)
            display_kpc['Inv.'] = display_kpc['invoices'].astype(int)

            st.dataframe(
                display_kpc[['#', 'kpi_center', 'Outstanding', 'Overdue', 'Rate', 'Cust.', 'Inv.']].rename(
                    columns={'kpi_center': 'KPI Center'}
                ),
                hide_index=True,
                width="stretch",
                height=min(400, 35 * len(display_kpc) + 38),
            )

    # =========================================================================
    # Top Customers chart
    # =========================================================================
    _render_top_customers_chart(pay_df, out_col, fragment_key)


def _render_top_customers_chart(
    pay_df: pd.DataFrame,
    out_col: str,
    fragment_key: str,
):
    """Render stacked bar chart of top customers by outstanding."""
    if pay_df.empty or 'customer' not in pay_df.columns:
        return

    has_line = LINE_OUTSTANDING_COL in pay_df.columns
    if has_line:
        dd = _dedup_for_actual_amounts(pay_df)
        chart_col = LINE_OUTSTANDING_COL
    else:
        dd = pay_df
        chart_col = out_col

    cust_totals = dd.groupby('customer')[chart_col].sum().sort_values(ascending=False).head(10)
    if cust_totals.empty or cust_totals.sum() < 1:
        return

    st.markdown("##### 🏆 Top Customers by Outstanding")

    chart_data = cust_totals.reset_index()
    chart_data.columns = ['customer', 'outstanding']

    chart = alt.Chart(chart_data).mark_bar().encode(
        y=alt.Y('customer:N', sort='-x', title=None, axis=alt.Axis(labelLimit=200)),
        x=alt.X('outstanding:Q', title='Outstanding (USD)', axis=alt.Axis(format='~s')),
        color=alt.Color('customer:N', legend=None),
        tooltip=[
            alt.Tooltip('customer:N', title='Customer'),
            alt.Tooltip('outstanding:Q', title='Outstanding', format='$,.2f'),
        ]
    ).properties(height=35 * min(len(chart_data), 10) + 40)

    st.altair_chart(chart, width="stretch")


# =============================================================================
# FULL DRILL-DOWN (legacy — all levels)
# =============================================================================

def ar_by_kpi_center_fragment(
    pay_df: pd.DataFrame,
    fragment_key: str = "kpc_ar_drill",
    payment_txn_loader=None,
    doc_loader=None,
    s3_url_generator=None,
):
    """Full AR drill-down by KPI Center (legacy — for standalone use)."""
    ar_summary_section(pay_df=pay_df, fragment_key=fragment_key)


# =============================================================================
# PER-INVOICE: PAYMENT HISTORY
# =============================================================================

def _render_invoice_payments(
    inv_number: str,
    payment_txn_loader: Callable,
    fragment_key: str = "kpc_inv_txn",
):
    """Load and display payment transactions for a single invoice."""
    try:
        txn_df = payment_txn_loader([inv_number])
    except Exception as e:
        logger.error(f"Error loading payment transactions for {inv_number}: {e}")
        st.caption("⚠️ Could not load payment details")
        return

    if txn_df is None or txn_df.empty:
        st.caption("No payment transactions recorded for this invoice")
        return

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
            lambda x: f"{x:.1%}" if pd.notna(x) else "—"
        )

    st.dataframe(
        display[list(available.keys())].rename(columns=available),
        hide_index=True, width="stretch",
        height=min(250, 35 * len(display) + 38),
    )


# =============================================================================
# PER-INVOICE: DOCUMENTS (S3 links)
# =============================================================================

def _render_invoice_documents(
    inv_number: str,
    doc_loader: Callable,
    s3_url_generator: Callable = None,
    fragment_key: str = "kpc_inv_doc",
):
    """Load and display documents for a single invoice."""
    try:
        docs_df = doc_loader([inv_number])
    except Exception as e:
        logger.error(f"Error loading documents for {inv_number}: {e}")
        st.caption("⚠️ Could not load documents")
        return

    if docs_df is None or docs_df.empty:
        st.caption("No documents attached to this invoice")
        return

    inv_docs = docs_df[docs_df['doc_type'] == 'invoice'] if 'doc_type' in docs_df.columns else pd.DataFrame()
    pmt_docs = docs_df[docs_df['doc_type'] == 'payment'] if 'doc_type' in docs_df.columns else pd.DataFrame()

    if not inv_docs.empty:
        st.markdown(f"**📄 Invoice Documents** ({len(inv_docs)})")
        for _, doc in inv_docs.iterrows():
            _render_doc_link(doc, s3_url_generator)

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
    filename = doc.get('filename', 'Unknown')
    s3_key = doc.get('s3_key', '')
    icon = _get_file_icon(filename)
    inv_num = doc.get('invoice_number', '')

    if s3_url_generator and s3_key:
        try:
            url = s3_url_generator(s3_key)
            if url:
                st.markdown(f"{icon} [{filename}]({url}){extra_label} — {inv_num}")
                return
        except Exception as e:
            logger.warning(f"Failed to generate URL for {s3_key}: {e}")

    st.caption(f"{icon} {filename}{extra_label} — {inv_num} (S3: {s3_key})")