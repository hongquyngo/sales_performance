# utils/salesperson_performance/payment/payment_analysis.py
"""
Payment & Collection Analysis for Salesperson Performance.

Adapted from legal_entity_performance/payment_analysis.py for salesperson view.

DATA SOURCE (v2.0):
  Both AR mode and Period mode use customer_ar_by_salesperson_view:
    - Pre-calculated columns: outstanding_by_split_usd, collected_by_split_usd,
      days_overdue, aging_bucket, gp_outstanding_by_split_usd
    - Sales split joined by CURDATE() → shows CURRENT salesperson
    - All amounts derived from actual payment records (customer_payment_details)
    - No proxy/estimated calculations

  AR mode filter:     payment_status IN ('Unpaid', 'Partially Paid')
  Period mode filter:  inv_date BETWEEN start AND end

  Fallback proxy (revenue × ratio) is only triggered if pre-calculated columns
  are missing — this should only happen with legacy callers.

VERSION: 2.0.0
"""

import logging
from datetime import date
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import streamlit as st
import altair as alt

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Revenue and GP columns in salesperson view
REV_COL = 'sales_by_split_usd'
GP_COL = 'gross_profit_by_split_usd'
GP1_COL = 'gp1_by_split_usd'

# Pre-calculated columns from customer_ar_by_salesperson_view (NEW v2.0)
# When these columns exist, use them DIRECTLY instead of proxy calculation
PRECALC_OUTSTANDING_COL = 'outstanding_by_split_usd'
PRECALC_COLLECTED_COL = 'collected_by_split_usd'
PRECALC_GP_OUTSTANDING_COL = 'gp_outstanding_by_split_usd'
PRECALC_DAYS_OVERDUE_COL = 'days_overdue'
PRECALC_AGING_BUCKET_COL = 'aging_bucket'
# Actual line-level amounts (not split-allocated, for customer-level analysis)
LINE_OUTSTANDING_COL = 'line_outstanding_usd'
LINE_COLLECTED_COL = 'line_collected_usd'
ACTUAL_REVENUE_COL = 'calculated_invoiced_amount_usd'

# Aging buckets based on days PAST DUE (due_date), not invoice date
# Negative = not yet due, 0+ = overdue
AGING_BUCKETS_OVERDUE = [
    ('Not Yet Due', -999999, -1),
    ('0-30 days overdue', 0, 30),
    ('31-60 days overdue', 31, 60),
    ('61-90 days overdue', 61, 90),
    ('90+ days overdue', 91, 999999),
]

# Fallback: aging by invoice age (when due_date not available)
AGING_BUCKETS_BY_INV_DATE = [
    ('Current (0-30)', 0, 30),
    ('31-60 days', 31, 60),
    ('61-90 days', 61, 90),
    ('90+ days', 91, 999999),
]

# Alert thresholds
OVERDUE_90_THRESHOLD_USD = 10000     # Alert if 90+ overdue > $10K
COLLECTION_RATE_LOW = 0.70           # Alert if collection rate < 70%
LARGE_UNPAID_THRESHOLD_USD = 50000   # Alert for single customer > $50K outstanding
OVERDUE_SHARE_THRESHOLD = 0.15       # Alert if overdue share > 15%

# Colors for charts
COLORS = {
    'collected': '#28a745',
    'outstanding': '#dc3545',
    'partial': '#ffc107',
    'not_yet_due': '#28a745',
    '0-30': '#ffc107',
    '31-60': '#ff8c00',
    '61-90': '#dc3545',
    '90+': '#8b0000',
}


# =============================================================================
# HELPERS
# =============================================================================

def _fmt_currency(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:,.1f}M"
    elif abs(value) >= 10_000:
        return f"${value / 1_000:,.0f}K"
    else:
        return f"${value:,.0f}"


def _normalize_status(val) -> str:
    """Normalize payment_status to standard category."""
    if pd.isna(val):
        return 'unknown'
    s = str(val).strip().lower()
    if 'fully' in s or s == 'paid':
        return 'fully_paid'
    elif 'partial' in s:
        return 'partially_paid'
    elif 'unpaid' in s or 'open' in s or 'pending' in s:
        return 'unpaid'
    return 'unknown'


# =============================================================================
# MAIN ANALYSIS
# =============================================================================

def analyze_payments(
    sales_df: pd.DataFrame,
    as_of_date: date = None,
) -> Optional[Dict]:
    """
    Analyze payment & collection from salesperson sales data.

    Args:
        sales_df: Filtered sales DataFrame from unified_sales_by_salesperson_view
        as_of_date: Reference date for aging (default: today)

    Returns:
        Dict with payment metrics, or None if no payment data available.
    """
    if sales_df.empty:
        return None

    # Check required columns
    required = ['payment_status', 'payment_ratio', REV_COL]
    missing = [c for c in required if c not in sales_df.columns]
    if missing:
        logger.info(f"Payment analysis skipped — missing columns: {missing}")
        return None

    today = as_of_date or date.today()

    # Only analyze rows WITH payment data (REALTIME, not HISTORY)
    df = sales_df[sales_df['payment_status'].notna()].copy()
    if df.empty:
        logger.info("Payment analysis skipped — no rows with payment_status")
        return None

    # Ensure types
    df['payment_ratio'] = pd.to_numeric(df['payment_ratio'], errors='coerce').fillna(0).clip(0, 1)
    df['inv_date'] = pd.to_datetime(df['inv_date'], errors='coerce')
    if 'due_date' in df.columns:
        df['due_date'] = pd.to_datetime(df['due_date'], errors='coerce')

    # Normalize status
    df['_status'] = df['payment_status'].apply(_normalize_status)

    # =========================================================================
    # LINE-LEVEL USD CALCULATION
    # v2.0: Always use pre-calculated columns from customer_ar_by_salesperson_view
    # Both AR mode and Period mode now query the same view — no proxy needed
    # =========================================================================
    has_precalc = PRECALC_OUTSTANDING_COL in df.columns

    if has_precalc:
        # Use pre-calculated values from customer_ar_by_salesperson_view
        # These are accurate: derived from actual payment records in SQL
        df['_collected_usd'] = pd.to_numeric(
            df[PRECALC_COLLECTED_COL], errors='coerce'
        ).fillna(0)
        df['_outstanding_usd'] = pd.to_numeric(
            df[PRECALC_OUTSTANDING_COL], errors='coerce'
        ).fillna(0)
        if PRECALC_GP_OUTSTANDING_COL in df.columns:
            df['_outstanding_gp'] = pd.to_numeric(
                df[PRECALC_GP_OUTSTANDING_COL], errors='coerce'
            ).fillna(0)
        elif GP_COL in df.columns:
            df['_outstanding_gp'] = df[GP_COL] * (1 - df['payment_ratio'])
        logger.info("Using pre-calculated amounts from AR view (accurate)")
    else:
        # Fallback: only triggered if data does NOT come from AR view
        # (e.g. legacy callers passing unified_sales data directly)
        logger.warning(
            "Pre-calculated columns not found — falling back to proxy. "
            "Ensure data comes from customer_ar_by_salesperson_view."
        )
        df['_collected_usd'] = df[REV_COL] * df['payment_ratio']
        df['_outstanding_usd'] = df[REV_COL] * (1 - df['payment_ratio'])
        if GP_COL in df.columns:
            df['_outstanding_gp'] = df[GP_COL] * (1 - df['payment_ratio'])

    # Raw status values
    raw_statuses = df['payment_status'].dropna().unique().tolist()

    # =========================================================================
    # 1. SUMMARY
    # =========================================================================
    total_invoiced = df[REV_COL].sum()
    total_collected = df['_collected_usd'].sum()
    total_outstanding = df['_outstanding_usd'].sum()
    collection_rate = (total_collected / total_invoiced) if total_invoiced > 0 else 0

    # Count by status (invoice-level dedup for counts)
    has_inv_number = 'inv_number' in df.columns
    if has_inv_number:
        inv_status = df.groupby('inv_number')['_status'].first()
        fully_paid_invoices = (inv_status == 'fully_paid').sum()
        partial_invoices = (inv_status == 'partially_paid').sum()
        unpaid_invoices = (inv_status == 'unpaid').sum()
        total_invoices = len(inv_status)
    else:
        fully_paid_invoices = (df['_status'] == 'fully_paid').sum()
        partial_invoices = (df['_status'] == 'partially_paid').sum()
        unpaid_invoices = (df['_status'] == 'unpaid').sum()
        total_invoices = len(df)

    # Revenue breakdown by status category
    status_rev = df.groupby('_status').agg(
        invoiced=(REV_COL, 'sum'),
        collected=('_collected_usd', 'sum'),
        outstanding=('_outstanding_usd', 'sum'),
    ).reset_index()

    summary = {
        'total_invoiced': total_invoiced,
        'total_collected': total_collected,
        'total_outstanding': total_outstanding,
        'collection_rate': collection_rate,
        'fully_paid_invoices': int(fully_paid_invoices),
        'partial_invoices': int(partial_invoices),
        'unpaid_invoices': int(unpaid_invoices),
        'total_invoices': int(total_invoices),
        'invoice_paid_rate': (fully_paid_invoices / total_invoices) if total_invoices > 0 else 0,
        'status_breakdown': status_rev,
        'has_outstanding': total_outstanding > 0,
    }

    # =========================================================================
    # 2. AGING ANALYSIS (outstanding only)
    # =========================================================================
    outstanding_df = df[df['_outstanding_usd'] > 0.01].copy()
    aging_data = _calculate_aging(outstanding_df, today)

    # =========================================================================
    # 3. BY CUSTOMER (outstanding)
    # =========================================================================
    by_customer = _analyze_by_customer(outstanding_df, today)

    # =========================================================================
    # 4. BY SALESPERSON
    # =========================================================================
    by_salesperson = _analyze_by_salesperson(df)

    # =========================================================================
    # 5. BY ENTITY
    # =========================================================================
    by_entity = _analyze_by_entity(df)

    # =========================================================================
    # 6. BY MONTH (collection trend)
    # =========================================================================
    by_month = _analyze_by_month(df)

    return {
        'summary': summary,
        'aging_buckets': aging_data,
        'by_customer': by_customer,
        'by_salesperson': by_salesperson,
        'by_entity': by_entity,
        'by_month': by_month,
        'raw_statuses': raw_statuses,
        'collection_rate': collection_rate,
        'as_of_date': today,
    }


# =============================================================================
# AGING CALCULATION
# =============================================================================

def _calculate_aging(
    outstanding_df: pd.DataFrame,
    today: date,
) -> pd.DataFrame:
    """
    Calculate aging buckets for outstanding amounts.

    v2.0: If pre-calculated aging_bucket column exists (from AR view),
    use it directly. Otherwise fall back to computing from dates.
    Uses due_date (overdue days) if available, else inv_date (invoice age).
    """
    if outstanding_df.empty:
        return pd.DataFrame(columns=['bucket', 'amount', 'gp', 'count', 'share'])

    df = outstanding_df.copy()
    today_ts = pd.Timestamp(today)
    total_outstanding = df['_outstanding_usd'].sum()

    # -----------------------------------------------------------------
    # FAST PATH: Use pre-calculated aging_bucket from AR view
    # -----------------------------------------------------------------
    if PRECALC_AGING_BUCKET_COL in df.columns and df[PRECALC_AGING_BUCKET_COL].notna().any():
        # Use SQL-calculated aging buckets directly
        agg_dict = {
            'amount': ('_outstanding_usd', 'sum'),
            'count': ('_outstanding_usd', 'count'),
        }
        if '_outstanding_gp' in df.columns:
            agg_dict['gp'] = ('_outstanding_gp', 'sum')

        result = df.groupby(PRECALC_AGING_BUCKET_COL).agg(**agg_dict).reset_index()
        result.rename(columns={PRECALC_AGING_BUCKET_COL: 'bucket'}, inplace=True)

        if 'gp' not in result.columns:
            result['gp'] = 0

        result['share'] = np.where(
            total_outstanding > 0,
            result['amount'] / total_outstanding,
            0
        )

        # Define display order and min_days for downstream compatibility
        bucket_order = {
            'Not Yet Due': (-999999, -1),
            'No Due Date': (-999998, -1),
            '1-30 days overdue': (1, 30),
            '31-60 days overdue': (31, 60),
            '61-90 days overdue': (61, 90),
            '90+ days overdue': (91, 999999),
        }
        result['_order'] = result['bucket'].map(
            {k: i for i, k in enumerate(bucket_order.keys())}
        ).fillna(99)
        result['min_days'] = result['bucket'].map(
            lambda b: bucket_order.get(b, (0, 0))[0]
        )
        result['max_days'] = result['bucket'].map(
            lambda b: bucket_order.get(b, (0, 0))[1]
        )

        result = result.sort_values('_order').drop(columns=['_order'])
        result = result[result['amount'] > 0.01].reset_index(drop=True)
        result.attrs['aging_mode'] = 'overdue'
        return result

    # -----------------------------------------------------------------
    # FALLBACK: Calculate aging from date columns (period mode)
    # -----------------------------------------------------------------
    has_due_date = 'due_date' in df.columns and df['due_date'].notna().any()

    if has_due_date:
        df['_aging_days'] = (today_ts - df['due_date']).dt.days
        buckets = AGING_BUCKETS_OVERDUE
        aging_mode = 'overdue'
    else:
        df['_aging_days'] = (today_ts - df['inv_date']).dt.days.clip(lower=0)
        buckets = AGING_BUCKETS_BY_INV_DATE
        aging_mode = 'invoice_age'

    rows = []

    for bucket_name, min_d, max_d in buckets:
        mask = (df['_aging_days'] >= min_d) & (df['_aging_days'] <= max_d)
        bucket_df = df[mask]
        amount = bucket_df['_outstanding_usd'].sum()
        gp = bucket_df['_outstanding_gp'].sum() if '_outstanding_gp' in bucket_df.columns else 0
        count = len(bucket_df)
        share = (amount / total_outstanding) if total_outstanding > 0 else 0

        rows.append({
            'bucket': bucket_name,
            'min_days': min_d,
            'max_days': max_d,
            'amount': amount,
            'gp': gp,
            'count': count,
            'share': share,
        })

    result = pd.DataFrame(rows)
    result = result[result['amount'] > 0.01].reset_index(drop=True)
    result.attrs['aging_mode'] = aging_mode
    return result


# =============================================================================
# BY CUSTOMER
# =============================================================================

def _analyze_by_customer(
    outstanding_df: pd.DataFrame,
    today: date,
) -> pd.DataFrame:
    """
    Top customers by outstanding USD amount.

    v2.0: When line_outstanding_usd is available (AR view), uses actual
    invoice amounts for customer-level aggregation. Customer AR is a
    company-level metric — split allocation would undercount if multiple
    salespersons share the same customer.
    """
    if outstanding_df.empty or 'customer' not in outstanding_df.columns:
        return pd.DataFrame()

    today_ts = pd.Timestamp(today)
    df = outstanding_df.copy()

    # Use pre-calculated days_overdue if available, else compute
    if PRECALC_DAYS_OVERDUE_COL in df.columns and df[PRECALC_DAYS_OVERDUE_COL].notna().any():
        df['_days'] = pd.to_numeric(df[PRECALC_DAYS_OVERDUE_COL], errors='coerce').fillna(0)
    elif 'due_date' in df.columns and df['due_date'].notna().any():
        df['_days'] = (today_ts - df['due_date']).dt.days
    else:
        df['_days'] = (today_ts - df['inv_date']).dt.days.clip(lower=0)

    # Use actual line outstanding (not split-allocated) for customer-level view
    # This prevents undercounting when multiple salespeople share a customer
    use_actual = LINE_OUTSTANDING_COL in df.columns
    outstanding_col = LINE_OUTSTANDING_COL if use_actual else '_outstanding_usd'

    # DEDUP: When using actual line amounts, multi-split invoices have duplicate
    # rows (1 per split) with the same line_outstanding_usd → sum would double-count.
    # Deduplicate by invoice line before aggregating.
    if use_actual:
        dedup_key = None
        if 'si_line_id' in df.columns:
            dedup_key = 'si_line_id'
        elif 'unified_line_id' in df.columns:
            dedup_key = 'unified_line_id'
        elif 'inv_number' in df.columns and 'product_pn' in df.columns:
            dedup_key = ['inv_number', 'product_pn']
        if dedup_key is not None:
            df = df.drop_duplicates(subset=dedup_key, keep='first')

    has_inv = 'inv_number' in df.columns
    agg_dict = {
        'outstanding': (outstanding_col, 'sum'),
        'max_days': ('_days', 'max'),
        'avg_days': ('_days', 'mean'),
    }
    if has_inv:
        agg_dict['invoices'] = ('inv_number', 'nunique')
    else:
        agg_dict['invoices'] = (outstanding_col, 'count')

    result = df.groupby('customer').agg(**agg_dict).reset_index()
    return result.sort_values('outstanding', ascending=False).head(15).reset_index(drop=True)


# =============================================================================
# BY SALESPERSON (new — specific to salesperson performance)
# =============================================================================

def _analyze_by_salesperson(df: pd.DataFrame) -> pd.DataFrame:
    """
    Collection rate by salesperson.
    
    v2.0: Handles 'Unassigned' (is_unassigned=1 or sales_name='Unassigned').
    Unassigned lines are grouped together with outstanding only (collected/invoiced = 0
    since split_percentage = 0 for unassigned).
    """
    if df.empty or 'sales_name' not in df.columns:
        return pd.DataFrame()

    # Group by sales_name only (sales_id can be NULL for Unassigned)
    result = df.groupby('sales_name').agg(
        total_invoiced=(REV_COL, 'sum'),
        collected=('_collected_usd', 'sum'),
        outstanding=('_outstanding_usd', 'sum'),
    ).reset_index()

    result['collection_rate'] = np.where(
        result['total_invoiced'] > 0,
        result['collected'] / result['total_invoiced'],
        0
    )

    # For Unassigned: show actual line outstanding even though split amounts are 0
    if LINE_OUTSTANDING_COL in df.columns:
        has_unassigned = 'is_unassigned' in df.columns
        if has_unassigned:
            unassigned_df = df[df['is_unassigned'] == 1]
        else:
            unassigned_df = df[df['sales_name'] == 'Unassigned']

        if not unassigned_df.empty:
            actual_outstanding = unassigned_df[LINE_OUTSTANDING_COL].sum()
            # Update the Unassigned row with actual line outstanding
            unassigned_mask = result['sales_name'] == 'Unassigned'
            if unassigned_mask.any():
                result.loc[unassigned_mask, 'outstanding'] = actual_outstanding
                result.loc[unassigned_mask, 'total_invoiced'] = unassigned_df[LINE_OUTSTANDING_COL].sum()

    return result.sort_values('outstanding', ascending=False).reset_index(drop=True)


# =============================================================================
# BY ENTITY
# =============================================================================

def _analyze_by_entity(df: pd.DataFrame) -> pd.DataFrame:
    """Collection rate by legal entity."""
    if df.empty or 'legal_entity' not in df.columns:
        return pd.DataFrame()

    result = df.groupby('legal_entity').agg(
        total_invoiced=(REV_COL, 'sum'),
        collected=('_collected_usd', 'sum'),
        outstanding=('_outstanding_usd', 'sum'),
    ).reset_index()

    result['collection_rate'] = np.where(
        result['total_invoiced'] > 0,
        result['collected'] / result['total_invoiced'],
        0
    )
    return result.sort_values('total_invoiced', ascending=False).reset_index(drop=True)


# =============================================================================
# BY MONTH (collection trend)
# =============================================================================

def _analyze_by_month(df: pd.DataFrame) -> pd.DataFrame:
    """Monthly collection rate trend."""
    if df.empty or 'inv_date' not in df.columns:
        return pd.DataFrame()

    df = df.copy()
    df['_inv_month'] = df['inv_date'].dt.to_period('M').astype(str)

    result = df.groupby('_inv_month').agg(
        invoiced=(REV_COL, 'sum'),
        collected=('_collected_usd', 'sum'),
        outstanding=('_outstanding_usd', 'sum'),
    ).reset_index()
    result.rename(columns={'_inv_month': 'inv_month'}, inplace=True)

    result['collection_rate'] = np.where(
        result['invoiced'] > 0,
        result['collected'] / result['invoiced'],
        0
    )
    return result.sort_values('inv_month').reset_index(drop=True)


# =============================================================================
# EXECUTIVE SUMMARY ALERTS
# =============================================================================

def check_payment_alerts(payment_data: Optional[Dict]) -> List[Dict]:
    """Generate payment alerts for dashboard."""
    if not payment_data:
        return []

    summary = payment_data['summary']
    aging = payment_data.get('aging_buckets', pd.DataFrame())
    by_customer = payment_data.get('by_customer', pd.DataFrame())
    alerts = []

    total_outstanding = summary.get('total_outstanding', 0)

    if total_outstanding < 100:
        return []

    # 1. High overdue share
    if not aging.empty:
        overdue_mask = aging['min_days'] >= 0
        total_overdue = aging.loc[overdue_mask, 'amount'].sum()
        overdue_share = total_overdue / total_outstanding if total_outstanding > 0 else 0

        if overdue_share >= OVERDUE_SHARE_THRESHOLD and total_overdue > OVERDUE_90_THRESHOLD_USD:
            unpaid_count = summary.get('unpaid_invoices', 0)
            partial_count = summary.get('partial_invoices', 0)
            alerts.append({
                'severity': 'medium',
                'icon': '💰',
                'message': (
                    f"Overdue: {overdue_share:.0%} of outstanding — "
                    f"{_fmt_currency(total_overdue)} / {_fmt_currency(total_outstanding)} "
                    f"({unpaid_count} unpaid + {partial_count} partial)"
                ),
            })

    # 2. Heavy overdue 90+ days
    if not aging.empty:
        bucket_90 = aging[aging['min_days'] >= 91]
        if not bucket_90.empty:
            amount_90 = bucket_90['amount'].sum()
            count_90 = int(bucket_90['count'].sum())
            if amount_90 > OVERDUE_90_THRESHOLD_USD:
                share = amount_90 / total_outstanding if total_outstanding > 0 else 0
                alerts.append({
                    'severity': 'high',
                    'icon': '🔴',
                    'message': (
                        f"90+ days overdue: {_fmt_currency(amount_90)} "
                        f"({share:.0%} of outstanding, {count_90} line items)"
                    ),
                })

    # 3. Large single-customer outstanding
    if not by_customer.empty:
        large = by_customer[by_customer['outstanding'] >= LARGE_UNPAID_THRESHOLD_USD]
        for _, row in large.head(2).iterrows():
            max_days = int(row['max_days'])
            day_label = (
                f"overdue {max_days}d" if max_days > 0
                else f"due in {abs(max_days)}d" if max_days < 0
                else "due today"
            )
            alerts.append({
                'severity': 'medium',
                'icon': '💰',
                'message': (
                    f"Customer {row['customer']} — outstanding {_fmt_currency(row['outstanding'])} "
                    f"({int(row['invoices'])} invoices, {day_label})"
                ),
            })

    return alerts


# =============================================================================
# STREAMLIT RENDERER
# =============================================================================

def render_payment_section(payment_data: Optional[Dict]):
    """
    Render payment/collection analysis section.

    Layout:
      Row 1: 4 summary metrics (Outstanding, Overdue, Not Yet Due, Avg Days)
      Row 2: Aging chart + detail table  (if outstanding > 0)
      Row 3: Collection trend + top unpaid customers
      Row 4: Collection by entity (if multi-entity)
      Row 5: Collection by salesperson (if multiple salespeople)
    """
    if not payment_data:
        st.info("📊 Payment data not available for this period. "
                "Payment tracking is available for 2025+ invoices only.")
        return

    summary = payment_data['summary']
    aging = payment_data.get('aging_buckets', pd.DataFrame())
    by_customer = payment_data.get('by_customer', pd.DataFrame())
    by_salesperson = payment_data.get('by_salesperson', pd.DataFrame())
    by_entity = payment_data.get('by_entity', pd.DataFrame())
    by_month = payment_data.get('by_month', pd.DataFrame())
    has_outstanding = summary.get('has_outstanding', False)

    # Show raw statuses detected
    raw_statuses = payment_data.get('raw_statuses', [])
    if raw_statuses:
        st.caption(f"Payment statuses in data: {', '.join(raw_statuses)}")

    # -----------------------------------------------------------------
    # ROW 1: Summary Metrics
    # -----------------------------------------------------------------
    total_outstanding = summary['total_outstanding']
    unpaid_count = summary['unpaid_invoices'] + summary['partial_invoices']

    # Parse aging for overdue / not-yet-due split
    not_yet_due_amount = 0
    total_overdue_amount = 0
    overdue_line_count = 0
    nyd_line_count = 0
    weighted_days_sum = 0
    total_outstanding_for_avg = 0

    if not aging.empty and 'min_days' in aging.columns:
        nyd_mask = aging['min_days'] < 0
        not_yet_due_amount = aging.loc[nyd_mask, 'amount'].sum()
        nyd_line_count = int(aging.loc[nyd_mask, 'count'].sum())

        overdue_mask = aging['min_days'] >= 0
        total_overdue_amount = aging.loc[overdue_mask, 'amount'].sum()
        overdue_line_count = int(aging.loc[overdue_mask, 'count'].sum())

        for _, row in aging.iterrows():
            mid = (row['min_days'] + min(row['max_days'], 365)) / 2
            if mid > 0:
                weighted_days_sum += mid * row['amount']
                total_outstanding_for_avg += row['amount']

    avg_days = int(weighted_days_sum / total_outstanding_for_avg) if total_outstanding_for_avg > 0 else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(
            "💰 Outstanding",
            _fmt_currency(total_outstanding),
            f"{unpaid_count:,} invoices ({summary['unpaid_invoices']} unpaid · {summary['partial_invoices']} partial)",
            delta_color="off",
        )
    with c2:
        if total_overdue_amount > 0:
            overdue_pct = (total_overdue_amount / total_outstanding * 100) if total_outstanding > 0 else 0
            st.metric(
                "🔴 Overdue",
                _fmt_currency(total_overdue_amount),
                f"{overdue_line_count:,} lines · {overdue_pct:.0f}% of total",
                delta_color="inverse",
            )
        else:
            st.metric("🟢 Overdue", "$0", "No overdue", delta_color="off")
    with c3:
        nyd_pct = (not_yet_due_amount / total_outstanding * 100) if total_outstanding > 0 else 0
        st.metric(
            "🟢 Not Yet Due",
            _fmt_currency(not_yet_due_amount),
            f"{nyd_line_count:,} lines · {nyd_pct:.0f}% of total",
            delta_color="off",
        )
    with c4:
        if avg_days > 0:
            severity = "🔴" if avg_days > 90 else "🟠" if avg_days > 45 else "🟢"
            st.metric(
                f"{severity} Avg Days Overdue",
                f"{avg_days} days",
                "weighted by amount",
                delta_color="off",
            )
        else:
            st.metric("🟢 Avg Days Overdue", "0 days", "All within terms", delta_color="off")

    if not has_outstanding:
        st.success("✅ All invoices fully collected — no outstanding balance")
        return

    # -----------------------------------------------------------------
    # ROW 2: Aging Analysis
    # -----------------------------------------------------------------
    if not aging.empty:
        col_aging, col_detail = st.columns([3, 2])

        with col_aging:
            aging_mode = getattr(aging, 'attrs', {}).get('aging_mode', 'invoice_age')
            title = "📅 Aging by Due Date" if aging_mode == 'overdue' else "📅 Aging by Invoice Date"
            st.markdown(f"##### {title}")
            chart = _build_aging_chart(aging)
            st.altair_chart(chart, width="stretch")

        with col_detail:
            st.markdown("##### 📋 Aging Detail")
            display = aging.copy()
            display['Amount'] = display['amount'].apply(lambda x: f"${x:,.0f}")
            display['Share'] = display['share'].apply(lambda x: f"{x:.0%}")
            display['Lines'] = display['count'].astype(int)
            st.dataframe(
                display[['bucket', 'Amount', 'Share', 'Lines']].rename(
                    columns={'bucket': 'Aging Bucket'}
                ),
                hide_index=True,
                width="stretch",
            )

    # -----------------------------------------------------------------
    # ROW 3: Collection Trend (full-width)
    # NOTE: "Top Outstanding Customers" removed — now in Drill-Down tab
    # -----------------------------------------------------------------
    has_trend = not by_month.empty and len(by_month) >= 2

    if has_trend:
        st.markdown("##### 📈 Monthly Collection Trend")
        chart = _build_collection_trend_chart(by_month)
        st.altair_chart(chart, width="stretch")

    # -----------------------------------------------------------------
    # ROW 4: Collection by Entity
    # -----------------------------------------------------------------
    if not by_entity.empty and len(by_entity) > 1:
        st.markdown("##### 🏢 Collection by Entity")
        display_ent = by_entity.copy()
        display_ent['Invoiced'] = display_ent['total_invoiced'].apply(lambda x: f"${x:,.0f}")
        display_ent['Collected'] = display_ent['collected'].apply(lambda x: f"${x:,.0f}")
        display_ent['Outstanding'] = display_ent['outstanding'].apply(lambda x: f"${x:,.0f}")
        display_ent['Rate'] = display_ent['collection_rate'].apply(lambda x: f"{x:.0%}")
        st.dataframe(
            display_ent[['legal_entity', 'Invoiced', 'Collected', 'Outstanding', 'Rate']].rename(
                columns={'legal_entity': 'Legal Entity'}
            ),
            hide_index=True,
            width="stretch",
        )

    # NOTE: "Collection by Salesperson" removed — now shown in Drill-Down tab only


# =============================================================================
# CHARTS
# =============================================================================

def _build_aging_chart(aging_df: pd.DataFrame) -> alt.Chart:
    """Horizontal bar chart for aging buckets with color coding."""
    df = aging_df.copy()
    df['bucket_order'] = range(len(df))

    color_list = ['#28a745', '#ffc107', '#ff8c00', '#dc3545', '#8b0000']
    domain = df['bucket'].tolist()
    range_colors = color_list[:len(domain)]

    bars = alt.Chart(df).mark_bar().encode(
        y=alt.Y('bucket:N', sort=alt.EncodingSortField(field='bucket_order'),
                title=None, axis=alt.Axis(labelLimit=150)),
        x=alt.X('amount:Q', title='Outstanding (USD)', axis=alt.Axis(format='~s')),
        color=alt.Color('bucket:N', scale=alt.Scale(
            domain=domain, range=range_colors
        ), legend=None),
        tooltip=[
            alt.Tooltip('bucket:N', title='Bucket'),
            alt.Tooltip('amount:Q', title='Amount', format='$,.0f'),
            alt.Tooltip('count:Q', title='Line Items'),
            alt.Tooltip('share:Q', title='Share', format='.0%'),
        ]
    )

    text_labels = alt.Chart(df).mark_text(
        align='left', dx=4, fontSize=11
    ).encode(
        y=alt.Y('bucket:N', sort=alt.EncodingSortField(field='bucket_order')),
        x=alt.X('amount:Q'),
        text=alt.Text('amount:Q', format='$,.0f'),
    )

    return (bars + text_labels).properties(
        height=35 * max(len(df), 2) + 40,
        title='Outstanding by Aging'
    )


def _build_collection_trend_chart(by_month: pd.DataFrame) -> alt.Chart:
    """Dual-axis: invoiced/collected bars + collection rate line."""
    df = by_month.copy()

    melted = df.melt(
        id_vars=['inv_month', 'collection_rate'],
        value_vars=['invoiced', 'collected'],
        var_name='type', value_name='amount'
    )
    melted['type'] = melted['type'].map({'invoiced': 'Invoiced', 'collected': 'Collected'})

    bars = alt.Chart(melted).mark_bar().encode(
        x=alt.X('inv_month:N', title=None, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y('amount:Q', title='Amount (USD)', axis=alt.Axis(format='~s')),
        color=alt.Color('type:N', scale=alt.Scale(
            domain=['Invoiced', 'Collected'],
            range=['#aec7e8', '#28a745']
        ), legend=alt.Legend(orient='top', title=None)),
        xOffset='type:N',
        tooltip=[
            alt.Tooltip('inv_month:N', title='Month'),
            alt.Tooltip('type:N', title='Type'),
            alt.Tooltip('amount:Q', title='Amount', format='$,.0f'),
        ]
    )

    line = alt.Chart(df).mark_line(
        color='#800080', strokeWidth=2, point=True
    ).encode(
        x=alt.X('inv_month:N'),
        y=alt.Y('collection_rate:Q', title='Collection Rate',
                axis=alt.Axis(format='.0%')),
        tooltip=[
            alt.Tooltip('inv_month:N', title='Month'),
            alt.Tooltip('collection_rate:Q', title='Rate', format='.0%'),
        ]
    )

    return alt.layer(bars, line).resolve_scale(
        y='independent'
    ).properties(height=280, title='Monthly Collection Trend')