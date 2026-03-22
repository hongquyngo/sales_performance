# utils/kpi_center_performance/payment/fragments.py
"""
Streamlit Fragments for KPI Center Performance — Payment & Collection Tab.

Adapted from salesperson_performance/payment/fragments.py.

Pattern:
- payment_tab_fragment: Tab-level @st.fragment with filters + sub-tabs
- Sub-tabs: Overview & Aging | Invoice Detail

VERSION: 1.0.0
"""

import logging
from datetime import date, datetime
from typing import Callable, Dict, List, Optional
from io import BytesIO
import pandas as pd
import numpy as np
import streamlit as st

from .payment_analysis import (
    analyze_payments,
    render_payment_section,
    _fmt_currency,
    _normalize_status,
    REV_COL,
    GP_COL,
    GP1_COL,
    PRECALC_OUTSTANDING_COL,
    PRECALC_COLLECTED_COL,
    LINE_OUTSTANDING_COL,
    LINE_COLLECTED_COL,
    ACTUAL_REVENUE_COL,
)
from .ar_drilldown import (
    ar_summary_section,
    _render_invoice_payments,
    _render_invoice_documents,
)

logger = logging.getLogger(__name__)


# =============================================================================
# HELPERS
# =============================================================================

def _format_product_display(row) -> str:
    parts = []
    if pd.notna(row.get('pt_code')) and row.get('pt_code'):
        parts.append(str(row['pt_code']))
    if pd.notna(row.get('product_pn')) and row.get('product_pn'):
        parts.append(str(row['product_pn']))
    return ' | '.join(parts) if parts else ''


def _format_oc_po(row) -> str:
    oc = str(row.get('oc_number', '')) if pd.notna(row.get('oc_number')) else ''
    po = str(row.get('customer_po_number', '')) if pd.notna(row.get('customer_po_number')) else ''
    if oc and po:
        return f"{oc}\n(PO: {po})"
    return oc or po or ''


def _group_by_invoice(df: pd.DataFrame) -> pd.DataFrame:
    """Merge multi-split rows into 1 row per invoice line."""
    if df.empty:
        return df

    if 'unified_line_id' in df.columns:
        group_key = 'unified_line_id'
    elif 'inv_number' in df.columns and 'product_pn' in df.columns:
        df = df.copy()
        df['_group_key'] = df['inv_number'].astype(str) + '||' + df['product_pn'].astype(str)
        group_key = '_group_key'
    else:
        return df

    def _build_kpc_display(group):
        parts = []
        for _, row in group.iterrows():
            name = row.get('kpi_center', 'Unknown')
            pct = row.get('split_rate_percent', 0)
            if pd.notna(name):
                parts.append(f"{name} {pct:.0f}%")
        return ' | '.join(parts) if parts else 'Unknown'

    try:
        kpc_display = df.groupby(group_key).apply(
            _build_kpc_display, include_groups=False
        ).reset_index()
    except TypeError:
        kpc_display = df.groupby(group_key).apply(_build_kpc_display).reset_index()
    kpc_display.columns = [group_key, '_kpi_center_display']

    first_rows = df.drop_duplicates(subset=group_key, keep='first').copy()
    first_rows = first_rows.merge(kpc_display, on=group_key, how='left')

    # LC display
    if 'line_invoiced_amount_lc' in first_rows.columns:
        first_rows['_invoiced_lc_display'] = first_rows['line_invoiced_amount_lc'].apply(
            lambda x: f"{x:,.2f}" if pd.notna(x) else "0.00"
        )
    if 'line_outstanding_lc' in first_rows.columns:
        first_rows['_outstanding_lc_display'] = first_rows['line_outstanding_lc'].apply(
            lambda x: f"{x:,.2f}" if pd.notna(x) else "0.00"
        )
    if 'line_collected_lc' in first_rows.columns:
        first_rows['_collected_lc_display'] = first_rows['line_collected_lc'].apply(
            lambda x: f"{x:,.2f}" if pd.notna(x) else "0.00"
        )

    line_out_col = 'line_outstanding_usd' if 'line_outstanding_usd' in first_rows.columns else 'outstanding_usd'
    first_rows['_outstanding_usd_grouped'] = pd.to_numeric(
        first_rows[line_out_col], errors='coerce'
    ).fillna(0)
    first_rows['_outstanding_usd_display'] = first_rows['_outstanding_usd_grouped'].apply(
        lambda x: f"${x:,.2f}" if pd.notna(x) else "$0.00"
    )

    if '_group_key' in first_rows.columns:
        first_rows.drop(columns=['_group_key'], inplace=True)

    return first_rows


# =============================================================================
# TAB-LEVEL FRAGMENT
# =============================================================================

@st.fragment
def payment_tab_fragment(
    sales_df: pd.DataFrame,
    filter_values: Dict = None,
    key_prefix: str = "kpc_payment_tab",
    ar_outstanding_df: pd.DataFrame = None,
    period_payment_df: pd.DataFrame = None,
    payment_txn_loader=None,
    doc_loader=None,
    s3_url_generator=None,
):
    """
    Fragment wrapper for Payment & Collection tab in KPI Center Performance.

    Dual-mode:
      - All Outstanding AR: ALL unpaid/partial invoices
      - Period Invoices: only invoices within selected period

    Args:
        sales_df: Filtered sales data (fallback)
        filter_values: Active filter values dict
        key_prefix: Unique key prefix
        ar_outstanding_df: All outstanding AR data
        period_payment_df: Period payment data
        payment_txn_loader: Callable(invoice_numbers) → DataFrame
        doc_loader: Callable(invoice_numbers) → DataFrame
        s3_url_generator: Callable(s3_key) → presigned URL
    """
    has_ar_data = ar_outstanding_df is not None and not ar_outstanding_df.empty

    period_source = period_payment_df if period_payment_df is not None else sales_df
    has_period_data = (
        not period_source.empty
        and 'payment_status' in period_source.columns
        and period_source['payment_status'].notna().any()
    )

    if not has_period_data and not has_ar_data:
        st.info(
            "📊 Payment data not available. "
            "Payment tracking requires the AR view to be configured."
        )
        return

    # =========================================================================
    # VIEW MODE TOGGLE
    # =========================================================================
    ar_mode = st.radio(
        "View mode",
        options=["📋 All Outstanding AR", "📅 Period Invoices"],
        horizontal=True,
        key=f"{key_prefix}_mode",
        help=(
            "**All Outstanding AR**: All unpaid/partially paid invoices regardless of period.  \n"
            "**Period Invoices**: Only invoices within the selected date range."
        ),
    )
    is_ar_mode = (ar_mode == "📋 All Outstanding AR")

    # =========================================================================
    # SELECT SOURCE DATA
    # =========================================================================
    if is_ar_mode:
        if not has_ar_data:
            st.warning("AR data not available. Showing period invoices instead.")
            is_ar_mode = False
            source_df = period_source
        else:
            source_df = ar_outstanding_df
    else:
        if not has_period_data:
            st.info("No payment data in the selected period.")
            return
        source_df = period_source

    if 'payment_status' not in source_df.columns:
        st.info("Payment data not available for this dataset.")
        return

    pay_df = source_df[source_df['payment_status'].notna()].copy()

    # Apply sidebar entity filter to AR mode
    if is_ar_mode and filter_values:
        entity_ids = filter_values.get('entity_ids', [])
        if entity_ids and 'legal_entity_id' in pay_df.columns:
            pay_df = pay_df[pay_df['legal_entity_id'].isin(entity_ids)]

    if pay_df.empty:
        st.info("No rows with payment data.")
        return

    # Ensure computed columns
    pay_df['payment_ratio'] = (
        pd.to_numeric(pay_df.get('payment_ratio', 0), errors='coerce').fillna(0).clip(0, 1)
    )

    if PRECALC_OUTSTANDING_COL in pay_df.columns:
        pay_df['collected_usd'] = pd.to_numeric(pay_df[PRECALC_COLLECTED_COL], errors='coerce').fillna(0)
        pay_df['outstanding_usd'] = pd.to_numeric(pay_df[PRECALC_OUTSTANDING_COL], errors='coerce').fillna(0)
    else:
        pay_df['collected_usd'] = pay_df[REV_COL] * pay_df['payment_ratio']
        pay_df['outstanding_usd'] = pay_df[REV_COL] * (1 - pay_df['payment_ratio'])

    if 'due_date' in pay_df.columns:
        pay_df['due_date'] = pd.to_datetime(pay_df['due_date'], errors='coerce')
    pay_df['inv_date'] = pd.to_datetime(pay_df['inv_date'], errors='coerce')

    total_count = len(pay_df)

    # =========================================================================
    # FILTERS
    # =========================================================================
    col_f1, col_f2, col_f3 = st.columns(3)

    with col_f1:
        st.markdown("**Payment Status**")
        status_options = sorted(pay_df['payment_status'].dropna().unique().tolist())
        selected_statuses = st.multiselect(
            "Status", status_options,
            key=f"{key_prefix}_status", placeholder="All statuses",
            label_visibility="collapsed"
        )

    with col_f2:
        _lbl2, _excl2 = st.columns([3, 1])
        with _lbl2:
            st.markdown("**Customer**")
        with _excl2:
            excl_customer = st.checkbox("Excl", key=f"{key_prefix}_excl_customer")
        customer_options = sorted(pay_df['customer'].dropna().unique().tolist())
        selected_customers = st.multiselect(
            "Customer", customer_options,
            key=f"{key_prefix}_customer", placeholder="Choose options",
            label_visibility="collapsed"
        )

    with col_f3:
        st.markdown("**Legal Entity**")
        entity_options = (
            sorted(pay_df['legal_entity'].dropna().unique().tolist())
            if 'legal_entity' in pay_df.columns else []
        )
        selected_entities = st.multiselect(
            "Entity", entity_options,
            key=f"{key_prefix}_entity", placeholder="All entities",
            label_visibility="collapsed"
        )

    # Row 2
    col_f4, col_f5, _ = st.columns(3)

    with col_f4:
        st.markdown("**Min Outstanding ($)**")
        min_outstanding = st.number_input(
            "Min Outstanding",
            min_value=0, value=0, step=1000,
            key=f"{key_prefix}_min_outstanding",
            label_visibility="collapsed"
        )

    with col_f5:
        _cb1, _cb2 = st.columns(2)
        with _cb1:
            overdue_only = st.checkbox("Overdue only", key=f"{key_prefix}_overdue_only")
        with _cb2:
            exclude_internal = st.checkbox("Exclude internal", key=f"{key_prefix}_excl_internal")

    # =========================================================================
    # APPLY FILTERS
    # =========================================================================
    filtered_df = pay_df.copy()

    if selected_statuses:
        filtered_df = filtered_df[filtered_df['payment_status'].isin(selected_statuses)]

    if selected_customers:
        if excl_customer:
            filtered_df = filtered_df[~filtered_df['customer'].isin(selected_customers)]
        else:
            filtered_df = filtered_df[filtered_df['customer'].isin(selected_customers)]

    if selected_entities and 'legal_entity' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['legal_entity'].isin(selected_entities)]

    if min_outstanding > 0:
        filtered_df = filtered_df[filtered_df['outstanding_usd'] >= min_outstanding]

    if overdue_only and 'due_date' in filtered_df.columns:
        today = pd.Timestamp(date.today())
        filtered_df = filtered_df[
            (filtered_df['due_date'].notna()) &
            (filtered_df['due_date'] < today) &
            (filtered_df['outstanding_usd'] > 0.01)
        ]

    if exclude_internal and 'customer_type' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['customer_type'].str.lower() != 'internal']

    # Filter summary
    active_filters = []
    if selected_statuses:
        active_filters.append(f"Status: {', '.join(selected_statuses)}")
    if selected_customers:
        mode = "excl" if excl_customer else "incl"
        active_filters.append(f"Customer: {len(selected_customers)} ({mode})")
    if selected_entities:
        active_filters.append(f"Entity: {', '.join(selected_entities)}")
    if min_outstanding > 0:
        active_filters.append(f"Outstanding ≥ ${min_outstanding:,.0f}")
    if overdue_only:
        active_filters.append("Overdue only")
    if exclude_internal:
        active_filters.append("Excl. internal")

    if active_filters:
        st.caption(f"🔍 Active filters: {' | '.join(active_filters)}")

    # =========================================================================
    # METRICS BANNER
    # =========================================================================
    _render_unified_metrics(filtered_df, is_ar_mode=is_ar_mode, filter_values=filter_values)

    st.divider()

    # =========================================================================
    # SUB-TABS
    # =========================================================================
    tab_overview, tab_detail = st.tabs([
        "📊 Overview & Aging",
        "📋 Invoice Detail",
    ])

    with tab_overview:
        payment_summary_fragment(
            pay_df=filtered_df,
            fragment_key=f"{key_prefix}_summary",
        )

    with tab_detail:
        ar_summary_section(
            pay_df=filtered_df,
            fragment_key=f"{key_prefix}_ar_summary",
        )
        st.divider()
        payment_list_fragment(
            pay_df=filtered_df,
            fragment_key=f"{key_prefix}_list",
            total_count=total_count,
            payment_txn_loader=payment_txn_loader,
            doc_loader=doc_loader,
            s3_url_generator=s3_url_generator,
        )


# =============================================================================
# METRICS BANNER
# =============================================================================

def _render_unified_metrics(
    pay_df: pd.DataFrame,
    is_ar_mode: bool = False,
    filter_values: dict = None,
):
    """Single metrics banner above sub-tabs."""
    if pay_df.empty:
        return

    today_ts = pd.Timestamp(date.today())
    inv_count = pay_df['inv_number'].nunique() if 'inv_number' in pay_df.columns else len(pay_df)
    status_counts = pay_df['payment_status'].value_counts()
    unpaid_count = int(status_counts.get('Unpaid', 0))
    partial_count = int(status_counts.get('Partially Paid', 0))
    fully_paid_count = int(status_counts.get('Fully Paid', 0))

    # Split-allocated amounts
    split_outstanding = pay_df['outstanding_usd'].sum()
    split_collected = pay_df.get('collected_usd', pd.Series(dtype=float)).sum()
    split_invoiced = pay_df[REV_COL].sum() if REV_COL in pay_df.columns else 0

    split_overdue = 0
    if 'due_date' in pay_df.columns:
        overdue_mask = (
            pay_df['due_date'].notna() &
            (pay_df['due_date'] < today_ts) &
            (pay_df['outstanding_usd'] > 0.01)
        )
        split_overdue = pay_df.loc[overdue_mask, 'outstanding_usd'].sum()
    split_nyd = split_outstanding - split_overdue
    split_rate = (split_collected / split_invoiced) if split_invoiced > 0 else 0

    # Actual invoice amounts (deduped)
    has_actual = LINE_OUTSTANDING_COL in pay_df.columns

    if has_actual:
        if 'unified_line_id' in pay_df.columns:
            dd = pay_df.drop_duplicates(subset='unified_line_id', keep='first')
        elif 'inv_number' in pay_df.columns and 'product_pn' in pay_df.columns:
            dd = pay_df.drop_duplicates(subset=['inv_number', 'product_pn'], keep='first')
        else:
            dd = pay_df

        act_outstanding = pd.to_numeric(dd[LINE_OUTSTANDING_COL], errors='coerce').fillna(0).sum()
        act_collected = pd.to_numeric(dd[LINE_COLLECTED_COL], errors='coerce').fillna(0).sum() if LINE_COLLECTED_COL in dd.columns else 0
        act_invoiced = pd.to_numeric(dd[ACTUAL_REVENUE_COL], errors='coerce').fillna(0).sum() if ACTUAL_REVENUE_COL in dd.columns else 0

        act_overdue = 0
        if 'due_date' in dd.columns:
            od_mask = (
                dd['due_date'].notna() &
                (dd['due_date'] < today_ts) &
                (pd.to_numeric(dd[LINE_OUTSTANDING_COL], errors='coerce').fillna(0) > 0.01)
            )
            act_overdue = pd.to_numeric(dd.loc[od_mask, LINE_OUTSTANDING_COL], errors='coerce').fillna(0).sum()
        act_nyd = act_outstanding - act_overdue
        act_rate = (act_collected / act_invoiced) if act_invoiced > 0 else 0
    else:
        act_outstanding = split_outstanding
        act_overdue = split_overdue
        act_nyd = split_nyd
        act_rate = split_rate
        act_invoiced = split_invoiced
        act_collected = split_collected

    # Row 1
    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        st.metric(
            "💰 Outstanding", f"${act_outstanding:,.2f}",
            delta=f"Split: ${split_outstanding:,.2f}" if has_actual else None,
            delta_color="off",
        )
    with c2:
        if act_overdue > 0:
            od_pct = (act_overdue / act_outstanding * 100) if act_outstanding > 0 else 0
            st.metric(
                "🔴 Overdue", f"${act_overdue:,.2f}",
                delta=f"{od_pct:.1f}%", delta_color="inverse",
            )
        else:
            st.metric("🟢 Overdue", "$0.00", delta="None", delta_color="off")
    with c3:
        st.metric(
            "🟢 Not Yet Due", f"${act_nyd:,.2f}",
            delta_color="off",
        )
    with c4:
        st.metric(
            "📊 Collection Rate", f"{act_rate:.1%}",
            delta=f"{unpaid_count:,} unpaid",
            delta_color="off",
        )
    with c5:
        st.metric(
            "📋 Invoices", f"{inv_count:,}",
            delta=f"{len(pay_df):,} split lines",
            delta_color="off",
        )

    # Row 2: Context
    if is_ar_mode and filter_values:
        _render_context_row_ar(pay_df, filter_values, act_outstanding)
    else:
        _render_context_row_period(
            act_invoiced, act_collected, split_invoiced, split_collected,
            fully_paid_count, inv_count, has_actual
        )


def _render_context_row_ar(pay_df, filter_values, total_outstanding):
    start_date = filter_values.get('start_date')
    end_date = filter_values.get('end_date')
    if not start_date or not end_date or total_outstanding <= 0:
        return

    period_mask = (
        (pay_df['inv_date'] >= pd.Timestamp(start_date)) &
        (pay_df['inv_date'] <= pd.Timestamp(end_date))
    )
    in_period = pay_df.loc[period_mask, 'outstanding_usd'].sum()
    carried = total_outstanding - in_period

    rc1, rc2 = st.columns(2)
    with rc1:
        pct = (in_period / total_outstanding * 100) if total_outstanding > 0 else 0
        st.metric("📅 Current Period", f"${in_period:,.2f}",
                  delta=f"{pct:.1f}% of AR", delta_color="off")
    with rc2:
        pct = (carried / total_outstanding * 100) if total_outstanding > 0 else 0
        st.metric("⏪ Carried Over", f"${carried:,.2f}",
                  delta=f"{pct:.1f}% of AR", delta_color="inverse" if carried > 0 else "off")


def _render_context_row_period(act_invoiced, act_collected, split_invoiced, split_collected,
                                fully_paid_count, inv_count, has_actual):
    rc1, rc2, rc3 = st.columns(3)
    with rc1:
        st.metric("📄 Total Invoiced", f"${act_invoiced:,.2f}",
                  delta=f"Split: ${split_invoiced:,.2f}" if has_actual else None,
                  delta_color="off")
    with rc2:
        st.metric("✅ Total Collected", f"${act_collected:,.2f}",
                  delta=f"Split: ${split_collected:,.2f}" if has_actual else None,
                  delta_color="off")
    with rc3:
        fp_pct = (fully_paid_count / inv_count * 100) if inv_count > 0 else 0
        st.metric("💯 Fully Paid", f"{fully_paid_count:,}",
                  delta=f"{fp_pct:.1f}% of invoices", delta_color="off")


# =============================================================================
# PAYMENT LIST FRAGMENT
# =============================================================================

def payment_list_fragment(
    pay_df: pd.DataFrame,
    fragment_key: str = "kpc_pay_list",
    total_count: int = None,
    payment_txn_loader=None,
    doc_loader: Callable = None,
    s3_url_generator: Callable = None,
):
    """Payment transaction list with click-to-select."""
    if pay_df.empty:
        st.info("No payment data for selected filters")
        return

    original_count = total_count if total_count is not None else len(pay_df)

    col_mode, col_sort = st.columns([1, 1])

    with col_mode:
        view_mode = st.radio(
            "Display mode",
            options=["📋 Show by Split", "📑 Group by Invoice"],
            horizontal=True,
            key=f"{fragment_key}_view_mode",
            help=(
                "**Show by Split**: 1 row per KPI Center per invoice line.  \n"
                "**Group by Invoice**: 1 row per invoice line."
            ),
        )
    is_grouped = (view_mode == "📑 Group by Invoice")

    with col_sort:
        sort_options = {
            'Outstanding (high→low)': ('outstanding_usd' if not is_grouped else '_outstanding_usd_grouped', False),
            'Invoice Date (newest)': ('inv_date', False),
            'Invoice Date (oldest)': ('inv_date', True),
            'Due Date (oldest)': ('due_date', True),
        }
        if not is_grouped:
            sort_options['Revenue (high→low)'] = (REV_COL, False)
        sort_label = st.selectbox("Sort by", list(sort_options.keys()), key=f"{fragment_key}_sort")

    sort_col, sort_asc = sort_options[sort_label]

    # Prepare display
    display_df = pay_df.copy()
    display_df['product_display'] = display_df.apply(_format_product_display, axis=1)
    if 'oc_number' in display_df.columns:
        display_df['oc_po_display'] = display_df.apply(_format_oc_po, axis=1)

    today = pd.Timestamp(date.today())
    if 'days_overdue' in display_df.columns and display_df['days_overdue'].notna().any():
        display_df['days_overdue'] = pd.to_numeric(display_df['days_overdue'], errors='coerce').fillna(0).astype(int)
    elif 'due_date' in display_df.columns:
        display_df['days_overdue'] = (today - display_df['due_date']).dt.days
    else:
        display_df['days_overdue'] = (today - display_df['inv_date']).dt.days

    if is_grouped:
        display_df = _group_by_invoice(display_df)

    # Sort
    actual_sort_col = sort_col
    if sort_col == '_outstanding_usd_grouped' and '_outstanding_usd_grouped' not in display_df.columns:
        actual_sort_col = 'outstanding_usd'
    if actual_sort_col in display_df.columns:
        display_df = display_df.sort_values(actual_sort_col, ascending=sort_asc, na_position='last')

    # Columns
    if is_grouped:
        display_columns = [
            'inv_date', 'inv_number', 'oc_po_display',
            '_kpi_center_display',
            'legal_entity', 'customer', 'customer_type',
            'product_display', 'brand',
            'payment_status', 'payment_ratio',
            'invoiced_currency',
            '_invoiced_lc_display', '_outstanding_lc_display', '_collected_lc_display',
            '_outstanding_usd_display',
            'due_date', 'days_overdue',
        ]
    else:
        display_columns = [
            'inv_date', 'inv_number', 'oc_po_display',
            'kpi_center',
            'legal_entity', 'customer', 'customer_type',
            'product_display', 'brand',
            REV_COL, GP_COL,
            'payment_status', 'payment_ratio',
            'collected_usd', 'outstanding_usd',
            'invoiced_currency', 'line_invoiced_amount_lc',
            'line_collected_lc', 'line_outstanding_lc',
            'due_date', 'days_overdue',
        ]

    available_cols = [c for c in display_columns if c in display_df.columns]

    if is_grouped:
        st.markdown(f"**{len(display_df):,} invoice lines** ({original_count:,} split rows)")
    else:
        st.markdown(f"**{len(display_df):,} lines** ({original_count:,} total)")

    detail = display_df[available_cols].copy()

    if not is_grouped:
        for col in [REV_COL, GP_COL, 'collected_usd', 'outstanding_usd']:
            if col in detail.columns:
                detail[col] = detail[col].apply(lambda x: f"${x:,.2f}" if pd.notna(x) else "$0.00")
        for col in ['line_invoiced_amount_lc', 'line_collected_lc', 'line_outstanding_lc']:
            if col in detail.columns:
                detail[col] = detail[col].apply(lambda x: f"{x:,.2f}" if pd.notna(x) else "0.00")

    if 'payment_ratio' in detail.columns:
        detail['payment_ratio'] = detail['payment_ratio'].apply(
            lambda x: f"{x:.1%}" if pd.notna(x) and isinstance(x, (int, float)) else str(x) if pd.notna(x) else "0.0%"
        )

    # Column config
    column_config = {
        'inv_date': st.column_config.DateColumn("Inv Date"),
        'inv_number': st.column_config.TextColumn("Invoice#"),
        'oc_po_display': st.column_config.TextColumn("OC / PO", width="medium"),
        'kpi_center': st.column_config.TextColumn("KPI Center"),
        '_kpi_center_display': st.column_config.TextColumn("KPI Center(s)", width="medium"),
        'legal_entity': st.column_config.TextColumn("Entity"),
        'customer': st.column_config.TextColumn("Customer", width="medium"),
        'customer_type': st.column_config.TextColumn("Type"),
        'product_display': st.column_config.TextColumn("Product", width="large"),
        'brand': st.column_config.TextColumn("Brand"),
        REV_COL: st.column_config.TextColumn("Revenue (USD)"),
        GP_COL: st.column_config.TextColumn("GP (USD)"),
        'payment_status': st.column_config.TextColumn("Status"),
        'payment_ratio': st.column_config.TextColumn("Paid%"),
        'collected_usd': st.column_config.TextColumn("Collected (USD)"),
        'outstanding_usd': st.column_config.TextColumn("Outstanding (USD)"),
        'invoiced_currency': st.column_config.TextColumn("Ccy"),
        '_invoiced_lc_display': st.column_config.TextColumn("Invoiced (LC)"),
        '_outstanding_lc_display': st.column_config.TextColumn("Outstanding (LC)"),
        '_collected_lc_display': st.column_config.TextColumn("Collected (LC)"),
        '_outstanding_usd_display': st.column_config.TextColumn("Outstanding (USD)"),
        'line_invoiced_amount_lc': st.column_config.TextColumn("Invoiced (LC)"),
        'line_collected_lc': st.column_config.TextColumn("Collected (LC)"),
        'line_outstanding_lc': st.column_config.TextColumn("Outstanding (LC)"),
        'due_date': st.column_config.DateColumn("Due Date"),
        'days_overdue': st.column_config.NumberColumn("Days O/D", format="%d"),
    }

    has_detail_loaders = payment_txn_loader is not None or doc_loader is not None
    if has_detail_loaders:
        st.caption("👆 Click a row to view payment history & documents")

    event = st.dataframe(
        detail,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        height=500,
        on_select="rerun" if has_detail_loaders else "ignore",
        selection_mode="single-row" if has_detail_loaders else None,
        key=f"{fragment_key}_table",
    )

    # Selected row → detail panel
    if has_detail_loaders and event and event.selection:
        selected_rows = event.selection.rows
        if selected_rows:
            row_idx = selected_rows[0]
            if row_idx < len(display_df):
                sel_row = display_df.iloc[row_idx]
                selected_inv = str(sel_row.get('inv_number', ''))
                if selected_inv and selected_inv != 'nan':
                    _render_selected_invoice_detail(
                        sel_row=sel_row,
                        inv_number=selected_inv,
                        payment_txn_loader=payment_txn_loader,
                        doc_loader=doc_loader,
                        s3_url_generator=s3_url_generator,
                        fragment_key=fragment_key,
                    )

    # Export
    _render_export_button(pay_df, fragment_key)


# =============================================================================
# SELECTED INVOICE DETAIL PANEL
# =============================================================================

def _render_selected_invoice_detail(
    sel_row: pd.Series,
    inv_number: str,
    payment_txn_loader=None,
    doc_loader: Callable = None,
    s3_url_generator: Callable = None,
    fragment_key: str = "inv_detail",
):
    with st.container(border=True):
        vat_num = sel_row.get('vat_number', '')
        vat_display = f" · VAT: {vat_num}" if pd.notna(vat_num) and vat_num else ""
        st.markdown(f"**{inv_number}**{vat_display}")

        ic1, ic2, ic3, ic4 = st.columns(4)
        with ic1:
            inv_date = sel_row.get('inv_date', '')
            due_date = sel_row.get('due_date', '')
            inv_str = pd.Timestamp(inv_date).strftime('%Y-%m-%d') if pd.notna(inv_date) else '—'
            due_str = pd.Timestamp(due_date).strftime('%Y-%m-%d') if pd.notna(due_date) else '—'
            st.caption(f"📅 Inv: {inv_str} · Due: {due_str}")
        with ic2:
            st.caption(f"🏢 {sel_row.get('customer', '—')}")
        with ic3:
            st.caption(f"📊 {sel_row.get('payment_status', '—')}")
        with ic4:
            aging = sel_row.get('aging_bucket', '')
            days = sel_row.get('days_overdue', 0)
            if aging:
                st.caption(f"⏰ {aging} ({days}d)")

        detail_tabs = []
        tab_keys = []
        if payment_txn_loader is not None:
            detail_tabs.append("💳 Payment History")
            tab_keys.append("txn")
        if doc_loader is not None:
            detail_tabs.append("📎 Documents")
            tab_keys.append("docs")

        if not detail_tabs:
            return

        tabs = st.tabs(detail_tabs)
        inv_key = inv_number[:12].replace('/', '_')

        for tab, tab_key in zip(tabs, tab_keys):
            with tab:
                if tab_key == "txn":
                    _render_invoice_payments(
                        inv_number=inv_number,
                        payment_txn_loader=payment_txn_loader,
                        fragment_key=f"{fragment_key}_txn_{inv_key}",
                    )
                elif tab_key == "docs":
                    _render_invoice_documents(
                        inv_number=inv_number,
                        doc_loader=doc_loader,
                        s3_url_generator=s3_url_generator,
                        fragment_key=f"{fragment_key}_doc_{inv_key}",
                    )


# =============================================================================
# PAYMENT SUMMARY FRAGMENT
# =============================================================================

def payment_summary_fragment(
    pay_df: pd.DataFrame,
    fragment_key: str = "kpc_pay_summary",
):
    if pay_df.empty:
        st.info("No payment data for selected filters")
        return

    payment_data = analyze_payments(pay_df)
    render_payment_section(payment_data)


# =============================================================================
# EXPORT
# =============================================================================

def _render_export_button(pay_df: pd.DataFrame, fragment_key: str):
    if st.button("📥 Export Payment Data", key=f"{fragment_key}_export"):
        export_columns = {
            'inv_date': 'Invoice Date',
            'inv_number': 'Invoice#',
            'kpi_center': 'KPI Center',
            'kpi_center_id': 'KPI Center ID',
            'split_rate_percent': 'Split %',
            'legal_entity': 'Legal Entity',
            'customer': 'Customer',
            'customer_type': 'Type',
            'product_pn': 'Product',
            'brand': 'Brand',
            'invoiced_currency': 'Currency',
            REV_COL: 'Revenue by Split (USD)',
            'outstanding_usd': 'O/S by Split (USD)',
            'collected_usd': 'Collected by Split (USD)',
            GP_COL: 'GP by Split (USD)',
            'payment_status': 'Payment Status',
            'payment_ratio': 'Payment Ratio',
            'due_date': 'Due Date',
            'days_overdue': 'Days Overdue',
            'aging_bucket': 'Aging Bucket',
        }

        export_df = pay_df.copy()
        available = {k: v for k, v in export_columns.items() if k in export_df.columns}
        export_df = export_df[list(available.keys())].rename(columns=available)

        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            export_df.to_excel(writer, sheet_name='Payment Collection', index=False)

        st.download_button(
            label="⬇️ Download Payment Data",
            data=buffer.getvalue(),
            file_name=f"kpc_payment_collection_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )