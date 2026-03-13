# utils/salesperson_performance/payment/fragments.py
"""
Streamlit Fragments for Salesperson Performance — Payment & Collection Tab.

Adapted from legal_entity_performance/payment/fragments.py.

Pattern:
- payment_tab_fragment: Tab-level @st.fragment with filters + sub-tabs
- Sub-tabs: Overview & Aging | Invoice Detail | Drill-Down

v3.0 CHANGES (from v2.0):
- Unified metrics banner above tabs (no duplicate metrics per tab)
- Merged 4 tabs → 3: Overview & Aging | Invoice Detail | Drill-Down
- Customer Analysis absorbed into Drill-Down tab (Level 2)
- Removed "By Salesperson" from Summary (now only in Drill-Down)
- Removed Column Legend expander (help= tooltips sufficient)
- Fixed _group_by_invoice for pandas 2.x compatibility

v3.2.0 FIX:
- Fixed double-count bug for INACTIVE co-split employees
- Root cause: v3.1.0 override replaced split-allocated amounts with 100% line amounts
  for ALL is_unassigned=1 rows. But v2.3.1 SQL view now returns INACTIVE employees
  with is_unassigned=1 AND split_percentage>0 (valid split allocations).
  Override was 30% → 100%, causing 170% total when ACTIVE co-split also exists.
- Fix: only override amounts when split_percentage=0 (truly no split), not for
  INACTIVE employees whose split-allocated amounts are already correct from SQL.
- Affects: AR Context Banner, Unified Metrics, all sub-tabs

v3.1.0 FIX:
- Unassigned AR now shows actual outstanding amount ($430K+ was hidden as $0)
- Root cause: unassigned rows have split_percentage=0, so split-allocated amounts
  (outstanding_by_split_usd, collected_by_split_usd, sales_by_split_usd) were all $0
- Fix: after computing split-allocated amounts, override unassigned rows with actual
  line amounts (line_outstanding_usd, line_collected_usd, calculated_invoiced_amount_usd)
- Affects: AR Context Banner, Unified Metrics, all sub-tabs, and filter by Assignment

VERSION: 3.2.0
"""

import logging
from datetime import date, datetime
from typing import Dict, List, Optional
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
from .ar_drilldown import ar_by_salesperson_fragment

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
    """
    Merge multi-split rows into 1 row per invoice line.

    For each si_line_id (or inv_number + product_pn combo):
      - Salesperson: "Brian Phạm 70% | Trang Phạm 30%"
      - Amounts: actual invoice amounts (from first row, not summed)
      - Keep first row's metadata (dates, customer, product, etc.)
    """
    if df.empty:
        return df

    # Determine grouping key
    if 'si_line_id' in df.columns:
        group_key = 'si_line_id'
    elif 'unified_line_id' in df.columns:
        group_key = 'unified_line_id'
    elif 'inv_number' in df.columns and 'product_pn' in df.columns:
        df = df.copy()
        df['_group_key'] = df['inv_number'].astype(str) + '||' + df['product_pn'].astype(str)
        group_key = '_group_key'
    else:
        return df  # can't group

    # Build salesperson display: "Brian Phạm 70% | Trang Phạm 30%"
    def _build_sp_display(group):
        parts = []
        for _, row in group.iterrows():
            name = row.get('sales_name', 'Unknown')
            pct = row.get('split_rate_percent', 0)
            if pd.notna(name) and name != 'Unassigned':
                parts.append(f"{name} {pct:.0f}%")
            elif name == 'Unassigned':
                parts.append("Unassigned")
        return ' | '.join(parts) if parts else 'Unassigned'

    # pandas 2.x compatible: use include_groups=False
    try:
        sp_display = df.groupby(group_key).apply(
            _build_sp_display, include_groups=False
        ).reset_index()
    except TypeError:
        # pandas < 2.0 fallback
        sp_display = df.groupby(group_key).apply(_build_sp_display).reset_index()
    sp_display.columns = [group_key, '_salesperson_display']

    # Deduplicate: keep first row per group (actual invoice amounts)
    first_rows = df.drop_duplicates(subset=group_key, keep='first').copy()

    # Merge salesperson display
    first_rows = first_rows.merge(sp_display, on=group_key, how='left')

    # Use actual line amounts (not split-allocated) for grouped view
    # LC
    if 'line_invoiced_amount_lc' in first_rows.columns:
        first_rows['_invoiced_lc_display'] = first_rows['line_invoiced_amount_lc'].apply(
            lambda x: f"{x:,.0f}" if pd.notna(x) else "0"
        )
    if 'line_outstanding_lc' in first_rows.columns:
        first_rows['_outstanding_lc_display'] = first_rows['line_outstanding_lc'].apply(
            lambda x: f"{x:,.0f}" if pd.notna(x) else "0"
        )
    if 'line_collected_lc' in first_rows.columns:
        first_rows['_collected_lc_display'] = first_rows['line_collected_lc'].apply(
            lambda x: f"{x:,.0f}" if pd.notna(x) else "0"
        )

    # USD (actual line outstanding, not split)
    line_out_col = 'line_outstanding_usd' if 'line_outstanding_usd' in first_rows.columns else 'outstanding_usd'
    first_rows['_outstanding_usd_grouped'] = pd.to_numeric(
        first_rows[line_out_col], errors='coerce'
    ).fillna(0)
    first_rows['_outstanding_usd_display'] = first_rows['_outstanding_usd_grouped'].apply(
        lambda x: f"${x:,.0f}" if pd.notna(x) else "$0"
    )

    # Clean up temp column
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
    key_prefix: str = "sp_payment_tab",
    ar_outstanding_df: pd.DataFrame = None,
    period_payment_df: pd.DataFrame = None,
    payment_txn_loader=None,
    doc_loader=None,
    s3_url_generator=None,
):
    """
    Fragment wrapper for Payment & Collection tab in Salesperson Performance.

    Dual-mode:
      - All Outstanding AR: shows ALL unpaid/partial invoices regardless of date
      - Period Invoices: shows only invoices within the selected period

    v3.0: Unified metrics above tabs. 3 sub-tabs instead of 4.
    Customer Analysis merged into Drill-Down tab.

    Args:
        sales_df: Filtered sales data (fallback only if period_payment_df is None)
        filter_values: Active filter values dict
        key_prefix: Unique key prefix for widgets
        ar_outstanding_df: All outstanding AR data (from get_ar_outstanding_data)
        period_payment_df: Period payment data (from get_payment_period_data, NEW v2.0)
        payment_txn_loader: Callable(invoice_numbers) → DataFrame of payment transactions
        doc_loader: Callable(invoice_numbers) → DataFrame of document metadata
        s3_url_generator: Callable(s3_key) → presigned URL string
    """
    # Determine data availability
    has_ar_data = ar_outstanding_df is not None and not ar_outstanding_df.empty

    # v2.0: Prefer period_payment_df (accurate, from AR view) over sales_df (unified view)
    period_source = period_payment_df if period_payment_df is not None else sales_df
    has_period_data = (
        not period_source.empty
        and 'payment_status' in period_source.columns
        and period_source['payment_status'].notna().any()
    )

    if not has_period_data and not has_ar_data:
        st.info(
            "📊 Payment data not available. "
            "Payment tracking is available for 2025+ invoices only."
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
            "**All Outstanding AR**: All unpaid/partially paid invoices regardless of period — "
            "gives complete AR picture.  \n"
            "**Period Invoices**: Only invoices within the selected date range — "
            "shows collection performance for the period."
        ),
    )
    is_ar_mode = (ar_mode == "📋 All Outstanding AR")

    # =========================================================================
    # SELECT SOURCE DATA BASED ON MODE
    # =========================================================================
    if is_ar_mode:
        if not has_ar_data:
            st.warning("AR outstanding data not available. Showing period invoices instead.")
            is_ar_mode = False
            source_df = period_source
        else:
            source_df = ar_outstanding_df
    else:
        if not has_period_data:
            st.info(
                "No payment data in the selected period. "
                "Switch to 'All Outstanding AR' to see full AR picture."
            )
            return
        source_df = period_source

    # Filter rows with payment data
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
        st.info(
            "No rows with payment data. "
            "HISTORY data (2014-2024) does not include payment tracking."
        )
        return

    # Ensure computed columns
    pay_df['payment_ratio'] = (
        pd.to_numeric(pay_df.get('payment_ratio', 0), errors='coerce')
        .fillna(0).clip(0, 1)
    )

    # v2.0: Use pre-calculated outstanding/collected from customer_ar_by_salesperson_view
    if PRECALC_OUTSTANDING_COL in pay_df.columns:
        pay_df['collected_usd'] = pd.to_numeric(
            pay_df[PRECALC_COLLECTED_COL], errors='coerce'
        ).fillna(0)
        pay_df['outstanding_usd'] = pd.to_numeric(
            pay_df[PRECALC_OUTSTANDING_COL], errors='coerce'
        ).fillna(0)
    else:
        # Fallback for legacy callers
        logger.warning("Pre-calculated columns not found, using proxy")
        pay_df['collected_usd'] = pay_df[REV_COL] * pay_df['payment_ratio']
        pay_df['outstanding_usd'] = pay_df[REV_COL] * (1 - pay_df['payment_ratio'])

    # =========================================================================
    # FIX v3.1.0 → v3.2.0: Unassigned AR visibility
    #
    # Problem: rows with split_percentage=0 have all split-allocated amounts = $0,
    #   hiding real AR from the UI.
    # Fix: override with actual line amounts for those rows.
    #
    # v3.2.0 IMPORTANT: Only override when split_percentage=0 (truly no split).
    #   INACTIVE employees (is_unassigned=1 but split_percentage>0) have correct
    #   split-allocated amounts from SQL — overriding those would double-count
    #   when an ACTIVE co-split partner also exists.
    #
    # Scenarios:
    #   is_unassigned=1, split=0%   → no split exists, override to line amounts ✅
    #   is_unassigned=1, split=30%  → INACTIVE employee, SQL amounts correct, keep ✅
    #   is_unassigned=0, split=70%  → ACTIVE employee, SQL amounts correct, keep ✅
    # =========================================================================
    _no_split_mask = None
    if 'is_unassigned' in pay_df.columns and 'split_rate_percent' in pay_df.columns:
        _no_split_mask = (
            (pay_df['is_unassigned'] == 1) &
            (pay_df['split_rate_percent'].fillna(0) == 0)
        )
    elif 'is_unassigned' in pay_df.columns:
        # Fallback: no split_rate_percent column (legacy data)
        _no_split_mask = pay_df['is_unassigned'] == 1
    elif 'sales_name' in pay_df.columns:
        _no_split_mask = pay_df['sales_name'] == 'Unassigned'

    if _no_split_mask is not None and _no_split_mask.any():
        n_no_split = int(_no_split_mask.sum())
        # Outstanding: use actual line outstanding (not split-allocated)
        if LINE_OUTSTANDING_COL in pay_df.columns:
            pay_df.loc[_no_split_mask, 'outstanding_usd'] = pd.to_numeric(
                pay_df.loc[_no_split_mask, LINE_OUTSTANDING_COL], errors='coerce'
            ).fillna(0)
            # Also override the pre-calculated column so that downstream
            # functions (analyze_payments, etc.) read correct values
            if PRECALC_OUTSTANDING_COL in pay_df.columns:
                pay_df.loc[_no_split_mask, PRECALC_OUTSTANDING_COL] = (
                    pay_df.loc[_no_split_mask, 'outstanding_usd']
                )
        # Collected: use actual line collected
        if LINE_COLLECTED_COL in pay_df.columns:
            pay_df.loc[_no_split_mask, 'collected_usd'] = pd.to_numeric(
                pay_df.loc[_no_split_mask, LINE_COLLECTED_COL], errors='coerce'
            ).fillna(0)
            if PRECALC_COLLECTED_COL in pay_df.columns:
                pay_df.loc[_no_split_mask, PRECALC_COLLECTED_COL] = (
                    pay_df.loc[_no_split_mask, 'collected_usd']
                )
        # Revenue (invoiced): use actual line invoiced amount for display
        if ACTUAL_REVENUE_COL in pay_df.columns:
            pay_df.loc[_no_split_mask, REV_COL] = pd.to_numeric(
                pay_df.loc[_no_split_mask, ACTUAL_REVENUE_COL], errors='coerce'
            ).fillna(0)
        logger.info(
            f"No-split AR fix: {n_no_split} rows overridden with actual line amounts "
            f"(outstanding=${pay_df.loc[_no_split_mask, 'outstanding_usd'].sum():,.0f})"
        )

    if 'due_date' in pay_df.columns:
        pay_df['due_date'] = pd.to_datetime(pay_df['due_date'], errors='coerce')
    pay_df['inv_date'] = pd.to_datetime(pay_df['inv_date'], errors='coerce')

    total_count = len(pay_df)

    # =========================================================================
    # FILTERS ROW 1
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
        st.markdown("**Salesperson**")
        # Exclude unassigned names from dropdown — controlled by Assignment filter
        if 'is_unassigned' in pay_df.columns:
            _assigned_df = pay_df[pay_df['is_unassigned'] == 0]
        else:
            _assigned_df = pay_df[pay_df['sales_name'] != 'Unassigned']
        sp_options = sorted(_assigned_df['sales_name'].dropna().unique().tolist())
        selected_salespeople = st.multiselect(
            "Salesperson", sp_options,
            key=f"{key_prefix}_salesperson", placeholder="All salespeople",
            label_visibility="collapsed"
        )

    # =========================================================================
    # FILTERS ROW 2
    # =========================================================================
    col_f4, col_f5, col_f6 = st.columns(3)

    with col_f4:
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

    with col_f5:
        st.markdown("**Min Outstanding ($)**")
        min_outstanding = st.number_input(
            "Min Outstanding",
            min_value=0, value=0, step=1000,
            key=f"{key_prefix}_min_outstanding",
            label_visibility="collapsed"
        )

    with col_f6:
        st.markdown("**Assignment**")
        assignment_filter = st.radio(
            "Assignment",
            options=["All", "Assigned", "Unassigned"],
            horizontal=True,
            key=f"{key_prefix}_assignment",
            label_visibility="collapsed",
        )

    # Overdue checkbox
    overdue_only = st.checkbox(
        "Overdue only", key=f"{key_prefix}_overdue_only"
    )

    # =========================================================================
    # APPLY FILTERS
    #
    # Filter interaction rules (v3.2.0):
    #   - Salesperson filter: only filters assigned salespeople
    #     (unassigned controlled exclusively by Assignment filter)
    #   - Assignment filter: applied AFTER salesperson filter
    #     → "All": show selected salespeople + unassigned
    #     → "Assigned": show selected salespeople only (no unassigned)
    #     → "Unassigned": show unassigned only (ignore salesperson selection)
    #   - When salesperson selected + Assignment="All": 
    #     show ONLY the selected salespeople (not all unassigned too)
    # =========================================================================
    filtered_df = pay_df.copy()

    if selected_statuses:
        filtered_df = filtered_df[filtered_df['payment_status'].isin(selected_statuses)]

    if selected_customers:
        if excl_customer:
            filtered_df = filtered_df[~filtered_df['customer'].isin(selected_customers)]
        else:
            filtered_df = filtered_df[filtered_df['customer'].isin(selected_customers)]

    # Salesperson filter: straightforward — only keep selected names
    if selected_salespeople:
        filtered_df = filtered_df[filtered_df['sales_name'].isin(selected_salespeople)]

    if selected_entities and 'legal_entity' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['legal_entity'].isin(selected_entities)]

    if min_outstanding > 0:
        filtered_df = filtered_df[filtered_df['outstanding_usd'] >= min_outstanding]

    # Assignment filter (applied after salesperson filter)
    if assignment_filter == 'Assigned':
        if 'is_unassigned' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['is_unassigned'] == 0]
        else:
            filtered_df = filtered_df[filtered_df['sales_name'] != 'Unassigned']
    elif assignment_filter == 'Unassigned':
        if 'is_unassigned' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['is_unassigned'] == 1]
        else:
            filtered_df = filtered_df[filtered_df['sales_name'] == 'Unassigned']

    if overdue_only and 'due_date' in filtered_df.columns:
        today = pd.Timestamp(date.today())
        filtered_df = filtered_df[
            (filtered_df['due_date'].notna()) &
            (filtered_df['due_date'] < today) &
            (filtered_df['outstanding_usd'] > 0.01)
        ]

    # Filter summary
    active_filters = []
    if selected_statuses:
        active_filters.append(f"Status: {', '.join(selected_statuses)}")
    if selected_customers:
        mode = "excl" if excl_customer else "incl"
        active_filters.append(f"Customer: {len(selected_customers)} ({mode})")
    if selected_salespeople:
        active_filters.append(f"Salesperson: {', '.join(selected_salespeople)}")
    if selected_entities:
        active_filters.append(f"Entity: {', '.join(selected_entities)}")
    if min_outstanding > 0:
        active_filters.append(f"Outstanding ≥ ${min_outstanding:,.0f}")
    if assignment_filter != 'All':
        active_filters.append(f"Assignment: {assignment_filter}")
    if overdue_only:
        active_filters.append("Overdue only")

    if active_filters:
        st.caption(f"🔍 Active filters: {' | '.join(active_filters)}")

    # =========================================================================
    # METRICS BANNER (single banner, adaptive by mode)
    # =========================================================================
    _render_unified_metrics(filtered_df, is_ar_mode=is_ar_mode, filter_values=filter_values)

    st.divider()

    # =========================================================================
    # SUB-TABS (3 tabs — no duplicated data between them)
    # =========================================================================
    tab_overview, tab_list, tab_drilldown = st.tabs([
        "📊 Overview & Aging",
        "📋 Invoice Detail",
        "🔍 Drill-Down",
    ])

    with tab_overview:
        payment_summary_fragment(
            pay_df=filtered_df,
            fragment_key=f"{key_prefix}_summary",
        )

    with tab_list:
        payment_list_fragment(
            pay_df=filtered_df,
            fragment_key=f"{key_prefix}_list",
            total_count=total_count,
        )

    with tab_drilldown:
        ar_by_salesperson_fragment(
            pay_df=filtered_df,
            payment_txn_loader=payment_txn_loader,
            doc_loader=doc_loader,
            s3_url_generator=s3_url_generator,
            fragment_key=f"{key_prefix}_ar_drill",
        )


# =============================================================================
# METRICS BANNER — Single adaptive banner (v3.3.0)
#
# Row 1 (both modes): Outstanding | Overdue | Not Yet Due | Collection Rate | Invoices
# Row 2 (adaptive):
#   AR mode:     Current Period | Carried Over | Unassigned AR
#   Period mode: Total Invoiced | Total Collected | Fully Paid
#
# All amounts: actual invoice (deduped) as main value, split-allocated in delta.
# =============================================================================

def _render_unified_metrics(
    pay_df: pd.DataFrame,
    is_ar_mode: bool = False,
    filter_values: dict = None,
):
    """Single metrics banner above sub-tabs. Adaptive row 2 based on mode."""
    if pay_df.empty:
        return

    today_ts = pd.Timestamp(date.today())
    inv_count = pay_df['inv_number'].nunique() if 'inv_number' in pay_df.columns else len(pay_df)
    status_counts = pay_df['payment_status'].value_counts()
    unpaid_count = int(status_counts.get('Unpaid', 0))
    partial_count = int(status_counts.get('Partially Paid', 0))
    fully_paid_count = int(status_counts.get('Fully Paid', 0))

    # -----------------------------------------------------------------
    # Split-allocated amounts (per-salesperson share)
    # -----------------------------------------------------------------
    split_outstanding = pay_df['outstanding_usd'].sum()
    split_collected = pay_df.get('collected_usd', pd.Series(dtype=float)).sum()
    split_invoiced = pay_df[REV_COL].sum() if REV_COL in pay_df.columns else 0

    split_overdue = 0
    split_overdue_lines = 0
    if 'due_date' in pay_df.columns:
        overdue_mask = (
            pay_df['due_date'].notna() &
            (pay_df['due_date'] < today_ts) &
            (pay_df['outstanding_usd'] > 0.01)
        )
        split_overdue = pay_df.loc[overdue_mask, 'outstanding_usd'].sum()
        split_overdue_lines = int(overdue_mask.sum())
    split_nyd = split_outstanding - split_overdue
    split_rate = (split_collected / split_invoiced) if split_invoiced > 0 else 0

    # -----------------------------------------------------------------
    # Actual invoice amounts (deduped — no double-count)
    # -----------------------------------------------------------------
    has_actual = LINE_OUTSTANDING_COL in pay_df.columns

    if has_actual:
        if 'unified_line_id' in pay_df.columns:
            dd = pay_df.drop_duplicates(subset='unified_line_id', keep='first')
        elif 'inv_number' in pay_df.columns and 'product_pn' in pay_df.columns:
            dd = pay_df.drop_duplicates(subset=['inv_number', 'product_pn'], keep='first')
        else:
            dd = pay_df

        act_outstanding = pd.to_numeric(dd[LINE_OUTSTANDING_COL], errors='coerce').fillna(0).sum()
        act_collected = (
            pd.to_numeric(dd[LINE_COLLECTED_COL], errors='coerce').fillna(0).sum()
            if LINE_COLLECTED_COL in dd.columns else 0
        )
        act_invoiced = (
            pd.to_numeric(dd[ACTUAL_REVENUE_COL], errors='coerce').fillna(0).sum()
            if ACTUAL_REVENUE_COL in dd.columns else 0
        )

        act_overdue = 0
        act_overdue_inv = 0
        if 'due_date' in dd.columns:
            od_mask = (
                dd['due_date'].notna() &
                (dd['due_date'] < today_ts) &
                (pd.to_numeric(dd[LINE_OUTSTANDING_COL], errors='coerce').fillna(0) > 0.01)
            )
            act_overdue = pd.to_numeric(dd.loc[od_mask, LINE_OUTSTANDING_COL], errors='coerce').fillna(0).sum()
            act_overdue_inv = dd.loc[od_mask, 'inv_number'].nunique() if 'inv_number' in dd.columns else int(od_mask.sum())
        act_nyd = act_outstanding - act_overdue
        act_rate = (act_collected / act_invoiced) if act_invoiced > 0 else 0
    else:
        # Fallback: use split amounts as primary
        act_outstanding = split_outstanding
        act_collected = split_collected
        act_invoiced = split_invoiced
        act_overdue = split_overdue
        act_overdue_inv = 0
        act_nyd = split_nyd
        act_rate = split_rate

    # =====================================================================
    # ROW 1: Primary metrics (both modes)
    # =====================================================================
    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        st.metric(
            "💰 Outstanding",
            f"${act_outstanding:,.0f}",
            delta=f"Split: ${split_outstanding:,.0f}" if has_actual else f"{inv_count:,} invoices",
            delta_color="off",
            help=(
                "**Main**: Actual invoice outstanding (deduped). True AR amount.\n\n"
                "**Split**: Each salesperson's share by split %."
            ) if has_actual else "Split-allocated outstanding by salesperson %.",
        )

    with c2:
        if act_overdue > 0:
            od_pct = (act_overdue / act_outstanding * 100) if act_outstanding > 0 else 0
            st.metric(
                "🔴 Overdue",
                f"${act_overdue:,.0f}",
                delta=(
                    f"Split: ${split_overdue:,.0f} · {od_pct:.0f}%"
                    if has_actual else f"{split_overdue_lines:,} lines · {od_pct:.0f}%"
                ),
                delta_color="inverse",
                help=(
                    f"**Main**: Actual past-due amount (deduped). {act_overdue_inv:,} invoices.\n\n"
                    f"**Split**: ${split_overdue:,.0f} ({split_overdue_lines:,} lines)."
                ) if has_actual else "Split-allocated overdue (due_date < today).",
            )
        else:
            st.metric("🟢 Overdue", "$0", delta="None", delta_color="off")

    with c3:
        nyd_pct = (act_nyd / act_outstanding * 100) if act_outstanding > 0 else 0
        st.metric(
            "🟢 Not Yet Due",
            f"${act_nyd:,.0f}",
            delta=(
                f"Split: ${split_nyd:,.0f} · {nyd_pct:.0f}%"
                if has_actual else f"{nyd_pct:.0f}% of total"
            ),
            delta_color="off",
            help="Within payment terms. = Outstanding − Overdue.",
        )

    with c4:
        st.metric(
            "📊 Collection Rate",
            f"{act_rate:.0%}",
            delta=(
                f"Split: {split_rate:.0%} · {unpaid_count:,} unpaid"
                if has_actual else f"{unpaid_count:,} unpaid · {partial_count:,} partial"
            ),
            delta_color="off",
            help=(
                f"**Main**: Invoice-level (deduped). **Split**: {split_rate:.0%}.\n\n"
                f"{unpaid_count:,} unpaid + {partial_count:,} partial invoices."
            ),
        )

    with c5:
        st.metric(
            "📋 Invoices",
            f"{inv_count:,}",
            delta=f"{len(pay_df):,} split lines",
            delta_color="off",
            help=(
                f"{inv_count:,} unique invoices. "
                f"{len(pay_df):,} split lines (1 inv × N salespeople)."
            ),
        )

    # =====================================================================
    # ROW 2: Context metrics (adaptive by mode)
    # =====================================================================
    if is_ar_mode and filter_values:
        _render_context_row_ar(pay_df, filter_values, has_actual,
                               act_outstanding if has_actual else split_outstanding)
    else:
        _render_context_row_period(pay_df, has_actual,
                                   act_invoiced, act_collected, split_invoiced, split_collected,
                                   fully_paid_count, inv_count)


def _render_context_row_ar(pay_df, filter_values, has_actual, total_outstanding):
    """Row 2 for AR mode: Current Period | Carried Over | Unassigned."""
    start_date = filter_values.get('start_date')
    end_date = filter_values.get('end_date')
    if not start_date or not end_date or total_outstanding <= 0:
        return

    period_mask = (
        (pay_df['inv_date'] >= pd.Timestamp(start_date)) &
        (pay_df['inv_date'] <= pd.Timestamp(end_date))
    )

    if has_actual and LINE_OUTSTANDING_COL in pay_df.columns:
        # Dedup for actual amounts
        if 'unified_line_id' in pay_df.columns:
            dd = pay_df.drop_duplicates(subset='unified_line_id', keep='first')
        elif 'inv_number' in pay_df.columns and 'product_pn' in pay_df.columns:
            dd = pay_df.drop_duplicates(subset=['inv_number', 'product_pn'], keep='first')
        else:
            dd = pay_df
        dd_period = (
            (dd['inv_date'] >= pd.Timestamp(start_date)) &
            (dd['inv_date'] <= pd.Timestamp(end_date))
        )
        in_period = pd.to_numeric(dd.loc[dd_period, LINE_OUTSTANDING_COL], errors='coerce').fillna(0).sum()
        carried = total_outstanding - in_period
    else:
        in_period = pay_df.loc[period_mask, 'outstanding_usd'].sum()
        carried = total_outstanding - in_period

    # Split amounts for delta
    split_in_period = pay_df.loc[period_mask, 'outstanding_usd'].sum()
    split_carried = pay_df['outstanding_usd'].sum() - split_in_period

    # Unassigned
    if 'is_unassigned' in pay_df.columns:
        ua_mask = pay_df['is_unassigned'] == 1
    else:
        ua_mask = pay_df['sales_name'] == 'Unassigned'
    ua_outstanding = pay_df.loc[ua_mask, 'outstanding_usd'].sum()
    ua_lines = int(ua_mask.sum())

    rc1, rc2, rc3 = st.columns(3)
    with rc1:
        pct = (in_period / total_outstanding * 100) if total_outstanding > 0 else 0
        st.metric(
            "📅 Current Period",
            f"${in_period:,.0f}",
            delta=f"Split: ${split_in_period:,.0f} · {pct:.0f}% of AR",
            delta_color="off",
            help=f"Outstanding from invoices within {start_date} – {end_date}.",
        )
    with rc2:
        pct = (carried / total_outstanding * 100) if total_outstanding > 0 else 0
        st.metric(
            "⏪ Carried Over",
            f"${carried:,.0f}",
            delta=f"Split: ${split_carried:,.0f} · {pct:.0f}% of AR",
            delta_color="inverse" if carried > 0 else "off",
            help="Outstanding from invoices BEFORE selected period. Older receivables.",
        )
    with rc3:
        if ua_outstanding > 0:
            pct = (ua_outstanding / total_outstanding * 100) if total_outstanding > 0 else 0
            st.metric(
                "⚠️ Unassigned AR",
                f"${ua_outstanding:,.0f}",
                delta=f"{ua_lines:,} lines · {pct:.0f}%",
                delta_color="inverse",
                help="No sales split assignment. Uses actual invoice amount. Setup → Sales Split to assign.",
            )
        else:
            st.metric(
                "✅ Unassigned",
                "$0",
                delta="All assigned",
                delta_color="off",
            )


def _render_context_row_period(pay_df, has_actual,
                                act_invoiced, act_collected,
                                split_invoiced, split_collected,
                                fully_paid_count, inv_count):
    """Row 2 for Period mode: Invoiced | Collected | Fully Paid."""
    rc1, rc2, rc3 = st.columns(3)
    with rc1:
        st.metric(
            "📄 Total Invoiced",
            f"${act_invoiced:,.0f}",
            delta=f"Split: ${split_invoiced:,.0f}" if has_actual else None,
            delta_color="off",
            help="Total invoiced amount (actual, deduped)." if has_actual else "Split-allocated invoiced.",
        )
    with rc2:
        st.metric(
            "✅ Total Collected",
            f"${act_collected:,.0f}",
            delta=f"Split: ${split_collected:,.0f}" if has_actual else None,
            delta_color="off",
            help="Total collected from payment records (actual, deduped)." if has_actual else "Split-allocated collected.",
        )
    with rc3:
        fp_pct = (fully_paid_count / inv_count * 100) if inv_count > 0 else 0
        st.metric(
            "💯 Fully Paid",
            f"{fully_paid_count:,}",
            delta=f"{fp_pct:.0f}% of {inv_count:,} invoices",
            delta_color="off",
            help="Number of invoices with payment_status = 'Fully Paid'.",
        )


# =============================================================================
# PAYMENT LIST FRAGMENT (no metrics — shown above)
# =============================================================================

def payment_list_fragment(
    pay_df: pd.DataFrame,
    fragment_key: str = "sp_pay_list",
    total_count: int = None,
):
    """Payment transaction list with payment-focused columns."""
    if pay_df.empty:
        st.info("No payment data for selected filters")
        return

    original_count = total_count if total_count is not None else len(pay_df)

    # =========================================================================
    # VIEW MODE + SORT (no duplicate metrics — unified banner above)
    # =========================================================================
    col_mode, col_sort = st.columns([1, 1])

    with col_mode:
        view_mode = st.radio(
            "Display mode",
            options=["📋 Show by Split", "📑 Group by Invoice"],
            horizontal=True,
            key=f"{fragment_key}_view_mode",
            help=(
                "**Show by Split**: 1 row per salesperson per invoice line — "
                "amounts are split-allocated.  \n"
                "**Group by Invoice**: 1 row per invoice — "
                "shows all salespersons in one column, amounts are actual invoice amounts."
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
        sort_label = st.selectbox(
            "Sort by", list(sort_options.keys()),
            key=f"{fragment_key}_sort",
        )

    sort_col, sort_asc = sort_options[sort_label]

    # =========================================================================
    # PREPARE DISPLAY DATA
    # =========================================================================
    display_df = pay_df.copy()

    display_df['product_display'] = display_df.apply(_format_product_display, axis=1)
    if 'oc_number' in display_df.columns:
        display_df['oc_po_display'] = display_df.apply(_format_oc_po, axis=1)

    # Overdue days — use pre-calculated if available (AR view)
    today = pd.Timestamp(date.today())
    if 'days_overdue' in display_df.columns and display_df['days_overdue'].notna().any():
        display_df['days_overdue'] = pd.to_numeric(
            display_df['days_overdue'], errors='coerce'
        ).fillna(0).astype(int)
    elif 'due_date' in display_df.columns:
        display_df['days_overdue'] = (today - display_df['due_date']).dt.days
    else:
        display_df['days_overdue'] = (today - display_df['inv_date']).dt.days

    if is_grouped:
        display_df = _group_by_invoice(display_df)

    # Sort
    actual_sort_col = sort_col
    if sort_col == '_outstanding_usd_grouped' and '_outstanding_usd_grouped' in display_df.columns:
        actual_sort_col = '_outstanding_usd_grouped'
    elif sort_col == '_outstanding_usd_grouped':
        actual_sort_col = 'outstanding_usd'

    if actual_sort_col in display_df.columns:
        display_df = display_df.sort_values(actual_sort_col, ascending=sort_asc, na_position='last')

    # =========================================================================
    # DISPLAY COLUMNS
    # =========================================================================
    if is_grouped:
        display_columns = [
            'inv_date', 'inv_number', 'oc_po_display',
            '_salesperson_display',
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
            'sales_name',
            'legal_entity', 'customer', 'customer_type',
            'product_display', 'brand',
            REV_COL,
            GP_COL,
            'payment_status', 'payment_ratio',
            'collected_usd', 'outstanding_usd',
            'invoiced_currency', 'line_invoiced_amount_lc',
            'line_collected_lc', 'line_outstanding_lc',
            'due_date', 'days_overdue',
        ]

    available_cols = [c for c in display_columns if c in display_df.columns]

    # Row count label
    if is_grouped:
        st.markdown(f"**{len(display_df):,} invoice lines** ({original_count:,} split rows before grouping)")
    else:
        st.markdown(
            f"**{len(display_df):,} lines** "
            f"({original_count:,} total before filters)"
        )

    detail = display_df[available_cols].copy()

    # Pre-format for SPLIT mode (amounts are numeric)
    if not is_grouped:
        for col in [REV_COL, GP_COL, 'collected_usd', 'outstanding_usd']:
            if col in detail.columns:
                detail[col] = detail[col].apply(
                    lambda x: f"${x:,.0f}" if pd.notna(x) else "$0"
                )
        for col in ['line_invoiced_amount_lc', 'line_collected_lc', 'line_outstanding_lc']:
            if col in detail.columns:
                detail[col] = detail.apply(
                    lambda r: f"{r[col]:,.0f}" if pd.notna(r.get(col)) else "0",
                    axis=1,
                )

    if 'payment_ratio' in detail.columns:
        detail['payment_ratio'] = detail['payment_ratio'].apply(
            lambda x: f"{x:.0%}" if pd.notna(x) and isinstance(x, (int, float)) else str(x) if pd.notna(x) else "0%"
        )

    # Column configs — help= tooltips replace the old Column Legend expander
    if is_grouped:
        column_config = {
            'inv_date': st.column_config.DateColumn("Inv Date"),
            'inv_number': st.column_config.TextColumn("Invoice#"),
            'oc_po_display': st.column_config.TextColumn("OC / PO", width="medium"),
            '_salesperson_display': st.column_config.TextColumn("Salesperson(s)", width="medium",
                help="All salespersons with split %. Format: Name Split%"),
            'legal_entity': st.column_config.TextColumn("Entity"),
            'customer': st.column_config.TextColumn("Customer", width="medium"),
            'customer_type': st.column_config.TextColumn("Type"),
            'product_display': st.column_config.TextColumn("Product", width="large"),
            'brand': st.column_config.TextColumn("Brand"),
            'payment_status': st.column_config.TextColumn("Status"),
            'payment_ratio': st.column_config.TextColumn("Paid%",
                help="Payment ratio from actual payment records"),
            'invoiced_currency': st.column_config.TextColumn("Ccy"),
            '_invoiced_lc_display': st.column_config.TextColumn("Invoiced (LC)",
                help="Invoice line amount in original currency (includes VAT)"),
            '_outstanding_lc_display': st.column_config.TextColumn("Outstanding (LC)",
                help="Outstanding in original currency"),
            '_collected_lc_display': st.column_config.TextColumn("Collected (LC)"),
            '_outstanding_usd_display': st.column_config.TextColumn("Outstanding (USD)",
                help="Outstanding converted to USD"),
            'due_date': st.column_config.DateColumn("Due Date"),
            'days_overdue': st.column_config.NumberColumn("Days O/D", format="%d",
                help="Days overdue (positive = past due, negative = not yet due)"),
        }
    else:
        column_config = {
            'inv_date': st.column_config.DateColumn("Inv Date"),
            'inv_number': st.column_config.TextColumn("Invoice#"),
            'oc_po_display': st.column_config.TextColumn("OC / PO", width="medium"),
            'sales_name': st.column_config.TextColumn("Salesperson"),
            'legal_entity': st.column_config.TextColumn("Entity"),
            'customer': st.column_config.TextColumn("Customer", width="medium"),
            'customer_type': st.column_config.TextColumn("Type"),
            'product_display': st.column_config.TextColumn("Product", width="large"),
            'brand': st.column_config.TextColumn("Brand"),
            REV_COL: st.column_config.TextColumn("Revenue (USD)",
                help="Split-allocated invoiced amount (USD)"),
            GP_COL: st.column_config.TextColumn("GP (USD)",
                help="Split-allocated gross profit (USD)"),
            'payment_status': st.column_config.TextColumn("Status"),
            'payment_ratio': st.column_config.TextColumn("Paid%",
                help="Payment ratio from actual payment records"),
            'collected_usd': st.column_config.TextColumn("Collected (USD)",
                help="Split-allocated collected (USD)"),
            'outstanding_usd': st.column_config.TextColumn("Outstanding (USD)",
                help="Split-allocated outstanding (USD)"),
            'invoiced_currency': st.column_config.TextColumn("Ccy"),
            'line_invoiced_amount_lc': st.column_config.TextColumn("Invoiced (LC)",
                help="Invoice line amount in original currency"),
            'line_collected_lc': st.column_config.TextColumn("Collected (LC)"),
            'line_outstanding_lc': st.column_config.TextColumn("Outstanding (LC)"),
            'due_date': st.column_config.DateColumn("Due Date"),
            'days_overdue': st.column_config.NumberColumn("Days O/D", format="%d",
                help="Days overdue (positive = past due, negative = not yet due)"),
        }

    st.dataframe(
        detail,
        column_config=column_config,
        width="stretch",
        hide_index=True,
        height=500,
    )

    # Export
    _render_export_button(pay_df, fragment_key)


# =============================================================================
# PAYMENT SUMMARY FRAGMENT
# =============================================================================

def payment_summary_fragment(
    pay_df: pd.DataFrame,
    fragment_key: str = "sp_pay_summary",
):
    """Overview & Aging — delegates to payment_analysis.render_payment_section."""
    if pay_df.empty:
        st.info("No payment data for selected filters")
        return

    payment_data = analyze_payments(pay_df)
    render_payment_section(payment_data)


# =============================================================================
# SHARED EXPORT
# =============================================================================

def _render_export_button(pay_df: pd.DataFrame, fragment_key: str):
    """Export payment data to Excel."""
    if st.button("📥 Export Payment Data", key=f"{fragment_key}_export"):
        export_columns = {
            'inv_date': 'Invoice Date',
            'inv_number': 'Invoice#',
            'oc_number': 'OC#',
            'customer_po_number': 'Customer PO',
            'sales_name': 'Salesperson',
            'sales_email': 'Email',
            'split_rate_percent': 'Split %',
            'is_unassigned': 'Unassigned',
            'legal_entity': 'Legal Entity',
            'customer': 'Customer',
            'customer_type': 'Type',
            'product_pn': 'Product',
            'brand': 'Brand',
            'invoiced_currency': 'Currency',
            # LC amounts (what's on the invoice, including VAT)
            'line_invoiced_amount_lc': 'Invoiced (LC)',
            'line_collected_lc': 'Collected (LC)',
            'line_outstanding_lc': 'Outstanding (LC)',
            'outstanding_by_split_lc': 'O/S by Split (LC)',
            'total_invoiced_amount': 'Invoice Total (LC)',
            'total_payment_received': 'Total Received (LC)',
            'invoice_outstanding_lc': 'Invoice O/S (LC)',
            'line_vat_amount_lc': 'VAT Amount (LC)',
            # USD amounts (GROSS, including VAT)
            REV_COL: 'Revenue by Split (USD)',
            'outstanding_usd': 'O/S by Split (USD)',
            'collected_usd': 'Collected by Split (USD)',
            GP_COL: 'GP by Split (USD)',
            GP1_COL: 'GP1 by Split (USD)',
            # Payment info
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
            file_name=f"sp_payment_collection_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )