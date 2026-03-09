# utils/salesperson_performance/warning_bulletin.py
"""
Daily Warning Bulletin for Salesperson Performance.
Auto-generates actionable alerts from existing processed data.

Designed for sales team "morning check" — issues only, no fluff:
- Headline: one-line snapshot of current status
- 🔴 Critical: Act today (overdue delivery, severely behind KPI, AR 90+ days)
- 🟡 Warning: Monitor this week (forecast gap, customer decline, margin drop, AR overdue)
- 🔵 Info: Be aware (inactive customers, concentration risk)

ZERO additional SQL queries — pure Pandas on cached data already in session.

VERSION: 1.1.0
CHANGELOG:
- v1.1.0: English-only, removed highlights section (issues-focused bulletin)
- v1.0.0: Initial implementation
"""

import logging
from datetime import date
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import streamlit as st

logger = logging.getLogger(__name__)


# =============================================================================
# ALERT THRESHOLDS (tunable)
# =============================================================================

KPI_CRITICAL_RATIO = 0.50          # Achievement < 50% of expected → critical
KPI_WARNING_RATIO = 0.75           # Achievement < 75% of expected → warning

CUSTOMER_DECLINE_THRESHOLD = 0.25  # Top customer revenue declines > 25%
CUSTOMER_INACTIVE_DAYS = 45        # Major customer hasn't ordered in N days
CONCENTRATION_THRESHOLD = 0.60     # Top 3 customers > 60% of revenue

MARGIN_DROP_THRESHOLD_PP = 1.5     # GP% drops > N percentage points vs LY

AR_OVERDUE_90_RATIO = 0.20         # 90+ day overdue > 20% of outstanding
AR_OVERDUE_RATIO = 0.50            # Total overdue > 50% of outstanding

BACKLOG_OVERDUE_MIN_VALUE = 10_000 # Only alert if overdue backlog > $10K


# =============================================================================
# FORMATTING HELPERS
# =============================================================================

def _fmt(value: float) -> str:
    """$1.2M / $850K / $1,234"""
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:,.1f}M"
    elif abs(value) >= 10_000:
        return f"${value / 1_000:,.0f}K"
    else:
        return f"${value:,.0f}"


# =============================================================================
# MAIN GENERATOR
# =============================================================================

def generate_warning_bulletin(
    overview_metrics: Dict,
    yoy_metrics: Optional[Dict],
    overall_achievement: Optional[Dict],
    pipeline_forecast: Optional[Dict],
    in_period_backlog_analysis: Optional[Dict],
    complex_kpis: Optional[Dict],
    sales_df: pd.DataFrame,
    targets_df: pd.DataFrame = None,
    backlog_detail_df: pd.DataFrame = None,
    ar_outstanding_df: pd.DataFrame = None,
    payment_overview: Optional[Dict] = None,
    active_filters: Dict = None,
    previous_sales_df: pd.DataFrame = None,
) -> Dict:
    """
    Generate warning bulletin from existing processed data.
    Issues and potential issues only — no positive highlights.

    Returns dict with: headline, alerts[], alert_count, has_critical, period_label
    """
    filters = active_filters or {}

    headline = _build_headline(overview_metrics, yoy_metrics, overall_achievement, pipeline_forecast)

    alerts: List[Dict] = []

    # 🔴 Critical — act today
    alerts.extend(_check_backlog_overdue(in_period_backlog_analysis))
    alerts.extend(_check_kpi_critical(overall_achievement, targets_df, filters))
    alerts.extend(_check_ar_overdue_90(payment_overview))

    # 🟡 Warning — monitor this week
    alerts.extend(_check_kpi_at_risk(pipeline_forecast))
    alerts.extend(_check_customer_decline(sales_df, previous_sales_df))
    alerts.extend(_check_margin_erosion(overview_metrics, yoy_metrics))
    alerts.extend(_check_ar_overdue_high(payment_overview))

    # 🔵 Info — be aware
    alerts.extend(_check_inactive_customers(sales_df))
    alerts.extend(_check_concentration(sales_df))

    return {
        'headline': headline,
        'alerts': alerts,
        'alert_count': len(alerts),
        'has_critical': any(a['severity'] == 'high' for a in alerts),
        'period_label': _build_period_label(filters),
    }


# =============================================================================
# HEADLINE & PERIOD
# =============================================================================

def _build_period_label(filters: Dict) -> str:
    period_type = filters.get('period_type', 'YTD')
    year = filters.get('year', date.today().year)
    start = filters.get('start_date')
    end = filters.get('end_date')

    if period_type == 'Custom' and start and end:
        return f"{start.strftime('%d %b')} — {end.strftime('%d %b %Y')}"
    elif period_type == 'QTD' and start:
        q = (start.month - 1) // 3 + 1
        return f"Q{q} {year}"
    elif period_type == 'MTD' and start:
        return f"{start.strftime('%B')} {year}"
    elif period_type == 'LY':
        return f"Full Year {year}"
    return f"YTD {year}"


def _build_headline(
    metrics: Dict, yoy: Optional[Dict],
    overall: Optional[Dict], pipeline: Optional[Dict],
) -> str:
    """One-line: Revenue (+YoY) | GP% | KPI Achievement | Backlog"""
    parts = []

    rev = metrics.get('total_revenue', 0)
    rev_str = f"Revenue: {_fmt(rev)}"
    if yoy and yoy.get('total_revenue_yoy') is not None:
        rev_str += f" ({yoy['total_revenue_yoy']:+.1f}% YoY)"
    parts.append(rev_str)

    parts.append(f"GP: {metrics.get('gp_percent', 0):.1f}%")

    if overall and overall.get('overall_achievement') is not None:
        parts.append(f"KPI: {overall['overall_achievement']:.0f}%")

    if pipeline:
        summary = pipeline.get('summary', {})
        bl_rev = summary.get('total_backlog_revenue', 0)
        bl_orders = summary.get('backlog_orders', 0)
        if bl_orders > 0:
            parts.append(f"Backlog: {_fmt(bl_rev)} ({bl_orders:,} orders)")

    return " | ".join(parts)


# =============================================================================
# 🔴 CRITICAL — act today
# =============================================================================

def _check_backlog_overdue(analysis: Optional[Dict]) -> List[Dict]:
    if not analysis:
        return []
    overdue_count = analysis.get('overdue_count', 0)
    overdue_value = analysis.get('overdue_value', 0)
    if overdue_count <= 0 or overdue_value < BACKLOG_OVERDUE_MIN_VALUE:
        return []
    return [{
        'severity': 'high', 'icon': '🔴',
        'message': (
            f"{overdue_count} orders past ETD, "
            f"total value {_fmt(overdue_value)} — follow up on delivery"
        ),
    }]


def _check_kpi_critical(
    overall: Optional[Dict], targets_df: pd.DataFrame = None, filters: Dict = None,
) -> List[Dict]:
    if not overall or overall.get('overall_achievement') is None:
        return []
    if targets_df is None or targets_df.empty:
        return []

    achievement = overall['overall_achievement']
    elapsed_ratio = _get_elapsed_ratio((filters or {}).get('period_type', 'YTD'), filters)

    if elapsed_ratio is None or elapsed_ratio < 0.25:
        return []

    expected = elapsed_ratio * 100
    if expected > 0 and achievement / expected < KPI_CRITICAL_RATIO:
        return [{
            'severity': 'high', 'icon': '🔴',
            'message': (
                f"Overall KPI at {achievement:.0f}% "
                f"(expected ~{expected:.0f}% at this point) — push sales effort"
            ),
        }]
    return []


def _check_ar_overdue_90(payment_overview: Optional[Dict]) -> List[Dict]:
    if not payment_overview:
        return []
    ar_summary = payment_overview.get('summary', {})
    ar_aging = payment_overview.get('aging_buckets', pd.DataFrame())
    total_outstanding = ar_summary.get('total_outstanding', 0)
    if total_outstanding <= 0:
        return []

    if isinstance(ar_aging, pd.DataFrame) and not ar_aging.empty and 'min_days' in ar_aging.columns:
        bucket_90 = ar_aging[ar_aging['min_days'] >= 91]
        amt = bucket_90['amount'].sum() if not bucket_90.empty else 0
        cnt = int(bucket_90['count'].sum()) if not bucket_90.empty else 0
        ratio = amt / total_outstanding if total_outstanding > 0 else 0

        if amt > 50_000 and ratio >= AR_OVERDUE_90_RATIO:
            return [{
                'severity': 'high', 'icon': '🔴',
                'message': (
                    f"AR overdue 90+ days: {_fmt(amt)} "
                    f"({ratio:.0%} of outstanding, {cnt} line items)"
                ),
            }]
    return []


# =============================================================================
# 🟡 WARNING — monitor this week
# =============================================================================

def _check_kpi_at_risk(pipeline: Optional[Dict]) -> List[Dict]:
    if not pipeline:
        return []
    alerts = []
    for kpi_key, kpi_label in [('revenue', 'Revenue'), ('gp1', 'GP1')]:
        d = pipeline.get(kpi_key, {})
        gap, target, forecast, gap_pct = d.get('gap'), d.get('target'), d.get('forecast'), d.get('gap_percent')
        if gap is None or target is None or target <= 0:
            continue
        if gap < 0 and gap_pct is not None and gap_pct < -10:
            alerts.append({
                'severity': 'medium', 'icon': '🟡',
                'message': (
                    f"{kpi_label} forecast {abs(gap_pct):.0f}% below target "
                    f"(Forecast: {_fmt(forecast)}, Target: {_fmt(target)}, GAP: {_fmt(gap)})"
                ),
            })
    return alerts[:2]


def _check_customer_decline(
    sales_df: pd.DataFrame, prev_sales_df: pd.DataFrame = None,
) -> List[Dict]:
    if prev_sales_df is None or prev_sales_df.empty or sales_df.empty:
        return []
    rev_col = 'sales_by_split_usd'
    if rev_col not in sales_df.columns or 'customer' not in sales_df.columns:
        return []
    if rev_col not in prev_sales_df.columns or 'customer' not in prev_sales_df.columns:
        return []

    # Exclude internal customers
    df_curr = _exclude_internal(sales_df)
    df_prev = _exclude_internal(prev_sales_df)

    curr = df_curr.groupby('customer')[rev_col].sum().reset_index(name='curr_rev')
    prev = df_prev.groupby('customer')[rev_col].sum().reset_index(name='prev_rev')
    merged = curr.merge(prev, on='customer', how='inner')
    if merged.empty:
        return []

    top_prev = merged.nlargest(10, 'prev_rev').copy()
    top_prev['change_pct'] = (top_prev['curr_rev'] - top_prev['prev_rev']) / top_prev['prev_rev']
    top_prev['change_abs'] = top_prev['curr_rev'] - top_prev['prev_rev']
    declining = top_prev[top_prev['change_pct'] < -CUSTOMER_DECLINE_THRESHOLD]

    alerts = []
    for _, row in declining.head(2).iterrows():
        alerts.append({
            'severity': 'medium', 'icon': '🟡',
            'message': (
                f"Customer {row['customer']} down {abs(row['change_pct']):.0%} "
                f"({_fmt(row['change_abs'])} vs LY)"
            ),
        })
    return alerts


def _check_margin_erosion(metrics: Dict, yoy: Optional[Dict]) -> List[Dict]:
    if not yoy:
        return []
    curr_gp_pct = metrics.get('gp_percent', 0)
    total_revenue = metrics.get('total_revenue', 0)
    total_gp = metrics.get('total_gp', 0)
    rev_yoy = yoy.get('total_revenue_yoy')
    gp_yoy = yoy.get('total_gp_yoy')
    if rev_yoy is None or gp_yoy is None or total_revenue <= 0:
        return []

    prev_revenue = total_revenue / (1 + rev_yoy / 100) if rev_yoy != -100 else 0
    prev_gp = total_gp / (1 + gp_yoy / 100) if gp_yoy != -100 else 0
    if prev_revenue <= 0:
        return []

    prev_gp_pct = prev_gp / prev_revenue * 100
    margin_change = curr_gp_pct - prev_gp_pct

    if margin_change < -MARGIN_DROP_THRESHOLD_PP:
        return [{
            'severity': 'medium', 'icon': '🟡',
            'message': (
                f"GP margin dropped {abs(margin_change):.1f}pp vs LY "
                f"({curr_gp_pct:.1f}% vs {prev_gp_pct:.1f}%)"
            ),
        }]
    return []


def _check_ar_overdue_high(payment_overview: Optional[Dict]) -> List[Dict]:
    if not payment_overview:
        return []
    ar_summary = payment_overview.get('summary', {})
    ar_aging = payment_overview.get('aging_buckets', pd.DataFrame())
    total_outstanding = ar_summary.get('total_outstanding', 0)
    if total_outstanding <= 10_000:
        return []

    if isinstance(ar_aging, pd.DataFrame) and not ar_aging.empty and 'min_days' in ar_aging.columns:
        overdue_mask = ar_aging['min_days'] >= 0
        total_overdue = ar_aging.loc[overdue_mask, 'amount'].sum()
        overdue_ratio = total_overdue / total_outstanding if total_outstanding > 0 else 0

        if overdue_ratio >= AR_OVERDUE_RATIO:
            unpaid = ar_summary.get('unpaid_invoices', 0)
            partial = ar_summary.get('partial_invoices', 0)
            return [{
                'severity': 'medium', 'icon': '🟡',
                'message': (
                    f"Overdue is {overdue_ratio:.0%} of total outstanding "
                    f"— {_fmt(total_overdue)} / {_fmt(total_outstanding)} "
                    f"({unpaid} unpaid + {partial} partial)"
                ),
            }]
    return []


# =============================================================================
# 🔵 INFO — be aware
# =============================================================================

def _check_inactive_customers(sales_df: pd.DataFrame) -> List[Dict]:
    if sales_df.empty:
        return []
    rev_col = 'sales_by_split_usd'
    if rev_col not in sales_df.columns or 'inv_date' not in sales_df.columns:
        return []

    # Exclude internal customers
    df = _exclude_internal(sales_df).copy()
    if df.empty:
        return []

    today = pd.Timestamp(date.today())
    df['inv_date'] = pd.to_datetime(df['inv_date'], errors='coerce')

    cust_rev = df.groupby('customer')[rev_col].sum()
    if cust_rev.sum() <= 0:
        return []

    top_customers = cust_rev.nlargest(max(3, int(len(cust_rev) * 0.2)))
    last_order = df.groupby('customer')['inv_date'].max()

    alerts = []
    for cust in top_customers.index:
        if cust not in last_order.index:
            continue
        last_date = last_order[cust]
        if pd.isna(last_date):
            continue
        days_since = (today - last_date).days
        if days_since >= CUSTOMER_INACTIVE_DAYS:
            alerts.append({
                'severity': 'low', 'icon': '🔵',
                'message': (
                    f"Customer {cust} — last order {days_since} days ago "
                    f"(revenue {_fmt(top_customers[cust])})"
                ),
            })
    return alerts[:2]


def _check_concentration(sales_df: pd.DataFrame) -> List[Dict]:
    if sales_df.empty or 'customer' not in sales_df.columns:
        return []
    rev_col = 'sales_by_split_usd'
    if rev_col not in sales_df.columns:
        return []

    # Exclude internal customers
    df = _exclude_internal(sales_df)
    if df.empty:
        return []

    cust_rev = df.groupby('customer')[rev_col].sum().sort_values(ascending=False)
    total = cust_rev.sum()
    if total <= 0 or len(cust_rev) < 5:
        return []

    top3_share = cust_rev.head(3).sum() / total
    if top3_share >= CONCENTRATION_THRESHOLD:
        top3_names = ", ".join(cust_rev.head(3).index.tolist())
        return [{
            'severity': 'low', 'icon': '🔵',
            'message': (
                f"Revenue concentration: top 3 customers account for {top3_share:.0%} "
                f"({top3_names})"
            ),
        }]
    return []


# =============================================================================
# HELPERS
# =============================================================================

def _exclude_internal(df: pd.DataFrame) -> pd.DataFrame:
    """Filter out internal customers (customer_type = 'Internal')."""
    if df.empty or 'customer_type' not in df.columns:
        return df
    return df[df['customer_type'].str.lower() != 'internal']


def _get_elapsed_ratio(period_type: str, filters: Dict = None) -> Optional[float]:
    """Ratio of time elapsed in period (0.0–1.0). None if undetermined."""
    today = date.today()
    filters = filters or {}
    year = filters.get('year', today.year)

    if period_type == 'YTD':
        start, end = date(year, 1, 1), date(year, 12, 31)
        if today >= end:
            return 1.0
        total = (end - start).days
        return max(0, min(1, (today - start).days / total)) if total > 0 else None

    elif period_type == 'QTD':
        cq = (today.month - 1) // 3 + 1
        start = date(year, (cq - 1) * 3 + 1, 1)
        end = date(year, cq * 3 + 1, 1) if cq < 4 else date(year, 12, 31)
        total = (end - start).days
        return max(0, min(1, (today - start).days / total)) if total > 0 else None

    elif period_type == 'MTD':
        import calendar
        start = date(year, today.month, 1)
        last_day = calendar.monthrange(year, today.month)[1]
        total = last_day
        return max(0, min(1, today.day / total)) if total > 0 else None

    elif period_type == 'LY':
        return 1.0

    elif period_type == 'Custom':
        start, end = filters.get('start_date'), filters.get('end_date')
        if start and end:
            total = (end - start).days
            return max(0, min(1, (today - start).days / total)) if total > 0 else None

    return None


def _get_top_ar_customers(ar_outstanding_df: pd.DataFrame, top_n: int = 3) -> List[Dict]:
    """Top customers by outstanding invoice amount (USD) with overdue info."""
    if ar_outstanding_df is None or ar_outstanding_df.empty:
        return []
    df = ar_outstanding_df.copy()

    # Use sales_by_split_usd (USD) — outstanding_amount may be in local currency
    amount_col = 'sales_by_split_usd'
    if amount_col not in df.columns or 'customer' not in df.columns:
        return []

    today = pd.Timestamp(date.today())
    if 'due_date' in df.columns:
        df['due_date'] = pd.to_datetime(df['due_date'], errors='coerce')
        df['days_overdue'] = (today - df['due_date']).dt.days.clip(lower=0)
    else:
        df['days_overdue'] = 0

    cust_agg = df.groupby('customer').agg(
        outstanding=(amount_col, 'sum'),
        invoice_count=('inv_number', 'nunique'),
        max_overdue_days=('days_overdue', 'max'),
    ).reset_index()
    cust_agg = cust_agg.sort_values('outstanding', ascending=False).head(top_n)

    return [
        {
            'customer': row['customer'],
            'outstanding': row['outstanding'],
            'invoice_count': int(row['invoice_count']),
            'max_overdue_days': int(row['max_overdue_days']),
        }
        for _, row in cust_agg.iterrows()
        if row['outstanding'] >= 10_000
    ]


# =============================================================================
# STREAMLIT RENDERER
# =============================================================================

def render_warning_bulletin(
    bulletin: Dict,
    ar_outstanding_df: pd.DataFrame = None,
):
    """
    Render warning bulletin — issues and potential issues only.

    Layout:
      ┌─────────────────────────────────────────────────────┐
      │  ⚡ Daily Bulletin — YTD 2026                       │
      │  Revenue: $2.3M (+11% YoY) | GP: 27.5% | ...       │
      │                                                      │
      │  🔴 Action Required:                                 │
      │  - 269 orders past ETD...                            │
      │                                                      │
      │  🟡 Monitor:                                         │
      │  - Customer X down 52%...                            │
      │                                                      │
      │  🔵 For Your Awareness:                              │
      │  - Customer Y last order 60 days ago...              │
      │                                                      │
      │  OR: ✅ No issues detected                           │
      └─────────────────────────────────────────────────────┘
    """
    period = bulletin.get('period_label', '')
    headline = bulletin.get('headline', '')
    alerts = bulletin.get('alerts', [])

    with st.container(border=True):
        st.markdown(f"#### ⚡ Daily Bulletin — {period}")
        st.markdown(f"**{headline}**")

        if alerts:
            sorted_alerts = sorted(alerts, key=lambda a: {'high': 0, 'medium': 1, 'low': 2}.get(a['severity'], 9))

            high = [a for a in sorted_alerts if a['severity'] == 'high']
            medium = [a for a in sorted_alerts if a['severity'] == 'medium']
            low = [a for a in sorted_alerts if a['severity'] == 'low']

            if high:
                lines = "\n".join(f"- {a['icon']} {a['message']}" for a in high)
                st.error(f"**⚡ Action Required:**\n\n{lines}", icon="🚨")

            if medium:
                lines = "\n".join(f"- {a['icon']} {a['message']}" for a in medium)
                st.warning(f"**👀 Monitor:**\n\n{lines}", icon="⚠️")

            if low:
                lines = "\n".join(f"- {a['icon']} {a['message']}" for a in low)
                st.info(f"**💡 For Your Awareness:**\n\n{lines}", icon="ℹ️")

            # Top AR customers when AR-related alerts exist
            ar_alerts = any(
                'ar' in a['message'].lower() or 'overdue' in a['message'].lower() or 'outstanding' in a['message'].lower()
                for a in alerts if a['severity'] in ('high', 'medium')
            )
            if ar_alerts and ar_outstanding_df is not None:
                top_ar = _get_top_ar_customers(ar_outstanding_df)
                if top_ar:
                    ar_lines = []
                    for c in top_ar:
                        note = f", overdue {c['max_overdue_days']}d" if c['max_overdue_days'] > 0 else ""
                        ar_lines.append(
                            f"- 💰 {c['customer']} — outstanding {_fmt(c['outstanding'])} "
                            f"({c['invoice_count']} invoices{note})"
                        )
                    with st.expander("💰 Top AR Customers", expanded=False):
                        st.markdown("\n".join(ar_lines))

        else:
            st.success("✅ No issues detected — all metrics within normal range")