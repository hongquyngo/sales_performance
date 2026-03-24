# utils/salesperson_performance/notification/alert_data_collector.py
"""
Per-Employee Alert Data Collector.

Filters cached data per salesperson and generates individualized:
- Overview metrics (their revenue, GP, GP1, invoices)
- Backlog past ETD (their overdue orders)
- AR overdue (their unpaid invoices)
- KPI achievement (their targets vs actuals)
- Warning bulletin (their alerts only)

Zero SQL — pure Pandas filtering on data already in memory.

Usage:
    from utils.salesperson_performance.notification.alert_data_collector import (
        collect_per_employee_bulletin,
    )

    bulletin, metrics = collect_per_employee_bulletin(
        employee_id=42,
        sales_df=data['sales'],
        backlog_detail_df=data['backlog_detail'],
        ar_outstanding_df=data['ar_outstanding'],
        targets_df=data['targets'],
        active_filters=active_filters,
    )

VERSION: 1.0.0
"""

import logging
from datetime import date
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# FORMATTING
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
# THRESHOLDS (same as warning_bulletin.py)
# =============================================================================

KPI_CRITICAL_RATIO = 0.50
KPI_WARNING_RATIO = 0.75
AR_OVERDUE_90_THRESHOLD = 50_000  # Alert if 90+ day overdue > $50K
AR_OVERDUE_THRESHOLD = 100_000    # Alert if total overdue > $100K
BACKLOG_OVERDUE_MIN_VALUE = 5_000
COMING_DUE_DAYS = 7


# =============================================================================
# PUBLIC API
# =============================================================================

def collect_per_employee_bulletin(
    employee_id: int,
    employee_name: str,
    sales_df: pd.DataFrame,
    backlog_detail_df: pd.DataFrame,
    ar_outstanding_df: pd.DataFrame,
    targets_df: pd.DataFrame,
    active_filters: Dict,
) -> Tuple[Dict, Dict]:
    """
    Generate individualized bulletin for one salesperson.

    Args:
        employee_id:      Employee ID
        employee_name:    Display name
        sales_df:         Filtered sales data (all employees)
        backlog_detail_df: Backlog detail (all employees)
        ar_outstanding_df: AR outstanding (all employees)
        targets_df:       KPI targets (all employees)
        active_filters:   Current filter state

    Returns:
        Tuple of (bulletin_dict, overview_metrics_dict)
        - bulletin: {headline, alerts[], period_label, alert_count, has_critical}
        - metrics: {total_revenue, total_gp, total_gp1, gp_percent, total_invoices, total_customers}
    """
    # =========================================================================
    # 1. FILTER DATA FOR THIS EMPLOYEE
    # =========================================================================
    my_sales = _filter_by_employee(sales_df, employee_id, 'sales_id')
    my_backlog = _filter_by_employee(backlog_detail_df, employee_id, 'sales_id')
    my_ar = _filter_by_employee(ar_outstanding_df, employee_id, 'sales_id')
    my_targets = _filter_by_employee(targets_df, employee_id, 'employee_id')

    # =========================================================================
    # 2. CALCULATE OVERVIEW METRICS
    # =========================================================================
    metrics = _calc_overview(my_sales)

    # =========================================================================
    # 3. GENERATE ALERTS
    # =========================================================================
    alerts: List[Dict] = []

    # 🔴 Critical
    alerts.extend(_check_backlog_past_etd(my_backlog))
    alerts.extend(_check_ar_overdue_90(my_ar))

    # 🟡 Warning
    alerts.extend(_check_kpi_behind(my_sales, my_targets, active_filters))
    alerts.extend(_check_ar_overdue(my_ar))

    # 🔵 Info
    alerts.extend(_check_coming_due(my_ar))

    # =========================================================================
    # 4. BUILD HEADLINE
    # =========================================================================
    headline = _build_headline(metrics, employee_name)

    # =========================================================================
    # 5. BUILD PERIOD LABEL
    # =========================================================================
    period_label = _build_period_label(active_filters)

    bulletin = {
        'headline': headline,
        'alerts': alerts,
        'alert_count': len(alerts),
        'has_critical': any(a['severity'] == 'high' for a in alerts),
        'period_label': period_label,
        'employee_id': employee_id,
        'employee_name': employee_name,
    }

    return bulletin, metrics


# =============================================================================
# DATA FILTERING
# =============================================================================

def _filter_by_employee(
    df: pd.DataFrame,
    employee_id: int,
    id_col: str,
) -> pd.DataFrame:
    """Filter DataFrame to one employee."""
    if df is None or df.empty or id_col not in df.columns:
        return pd.DataFrame()
    return df[df[id_col] == employee_id].copy()


# =============================================================================
# OVERVIEW METRICS
# =============================================================================

def _calc_overview(sales_df: pd.DataFrame) -> Dict:
    """Calculate overview metrics for one salesperson."""
    if sales_df.empty:
        return {
            'total_revenue': 0, 'total_gp': 0, 'total_gp1': 0,
            'gp_percent': 0, 'total_invoices': 0, 'total_customers': 0,
        }

    rev = sales_df['sales_by_split_usd'].sum() if 'sales_by_split_usd' in sales_df.columns else 0
    gp = sales_df['gross_profit_by_split_usd'].sum() if 'gross_profit_by_split_usd' in sales_df.columns else 0
    gp1 = sales_df['gp1_by_split_usd'].sum() if 'gp1_by_split_usd' in sales_df.columns else 0
    invoices = sales_df['inv_number'].nunique() if 'inv_number' in sales_df.columns else 0
    customers = sales_df['customer_id'].nunique() if 'customer_id' in sales_df.columns else 0
    gp_pct = (gp / rev * 100) if rev > 0 else 0

    return {
        'total_revenue': rev,
        'total_gp': gp,
        'total_gp1': gp1,
        'gp_percent': gp_pct,
        'total_invoices': invoices,
        'total_customers': customers,
    }


# =============================================================================
# HEADLINE
# =============================================================================

def _build_headline(metrics: Dict, name: str) -> str:
    rev = metrics.get('total_revenue', 0)
    gp_pct = metrics.get('gp_percent', 0)
    return f"{name}: Revenue {_fmt(rev)} | GP: {gp_pct:.1f}%"


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


# =============================================================================
# 🔴 CRITICAL ALERTS
# =============================================================================

def _check_backlog_past_etd(backlog_df: pd.DataFrame) -> List[Dict]:
    """Orders with ETD in the past — not yet invoiced."""
    if backlog_df.empty or 'etd' not in backlog_df.columns:
        return []

    df = backlog_df.copy()
    df['etd'] = pd.to_datetime(df['etd'], errors='coerce')
    today = pd.Timestamp(date.today())
    overdue = df[df['etd'] < today]

    if overdue.empty:
        return []

    count = overdue['oc_number'].nunique() if 'oc_number' in overdue.columns else len(overdue)
    value = overdue['backlog_sales_by_split_usd'].sum() if 'backlog_sales_by_split_usd' in overdue.columns else 0

    if value < BACKLOG_OVERDUE_MIN_VALUE:
        return []

    return [{
        'severity': 'high', 'icon': '🔴',
        'message': f"{count} orders past ETD, total value {_fmt(value)} — follow up on delivery",
    }]


def _check_ar_overdue_90(ar_df: pd.DataFrame) -> List[Dict]:
    """AR outstanding 90+ days past due."""
    if ar_df.empty:
        return []

    overdue_90 = _get_overdue(ar_df, min_days=90)
    if overdue_90.empty:
        return []

    amount = overdue_90['outstanding_by_split_usd'].sum() if 'outstanding_by_split_usd' in overdue_90.columns else 0
    if amount < AR_OVERDUE_90_THRESHOLD:
        return []

    count = overdue_90['inv_number'].nunique() if 'inv_number' in overdue_90.columns else len(overdue_90)
    return [{
        'severity': 'high', 'icon': '🔴',
        'message': f"{count} invoices overdue 90+ days, total {_fmt(amount)} — escalate collection",
    }]


# =============================================================================
# 🟡 WARNING ALERTS
# =============================================================================

def _check_kpi_behind(
    sales_df: pd.DataFrame,
    targets_df: pd.DataFrame,
    filters: Dict,
) -> List[Dict]:
    """KPI achievement behind expected pace."""
    if targets_df.empty:
        return []

    alerts = []
    elapsed = _get_elapsed_ratio(filters)
    if elapsed is None or elapsed < 0.15:
        return []

    expected_pct = elapsed * 100

    kpi_map = {
        'revenue': 'sales_by_split_usd',
        'gross_profit': 'gross_profit_by_split_usd',
        'gross_profit_1': 'gp1_by_split_usd',
    }

    for _, row in targets_df.iterrows():
        kpi_name = str(row.get('kpi_name', '')).lower().replace(' ', '_')
        annual_target = row.get('annual_target_value_numeric', 0)
        if annual_target <= 0:
            continue

        col = kpi_map.get(kpi_name)
        if not col or col not in sales_df.columns:
            continue

        actual = sales_df[col].sum()
        prorated_target = annual_target * elapsed
        if prorated_target <= 0:
            continue

        achievement = actual / prorated_target * 100
        if achievement < KPI_CRITICAL_RATIO * 100:
            display = kpi_name.replace('_', ' ').title()
            alerts.append({
                'severity': 'medium', 'icon': '🟡',
                'message': (
                    f"{display}: {_fmt(actual)} vs target {_fmt(prorated_target)} "
                    f"({achievement:.0f}% — expected ~{expected_pct:.0f}%)"
                ),
            })
        elif achievement < KPI_WARNING_RATIO * 100:
            display = kpi_name.replace('_', ' ').title()
            alerts.append({
                'severity': 'medium', 'icon': '🟡',
                'message': f"{display} at {achievement:.0f}% of prorated target",
            })

    return alerts[:3]  # Max 3 KPI alerts


def _check_ar_overdue(ar_df: pd.DataFrame) -> List[Dict]:
    """Total AR overdue (all buckets)."""
    if ar_df.empty:
        return []

    overdue = _get_overdue(ar_df, min_days=0)
    if overdue.empty:
        return []

    amount = overdue['outstanding_by_split_usd'].sum() if 'outstanding_by_split_usd' in overdue.columns else 0
    if amount < AR_OVERDUE_THRESHOLD:
        return []

    count = overdue['inv_number'].nunique() if 'inv_number' in overdue.columns else len(overdue)
    return [{
        'severity': 'medium', 'icon': '🟡',
        'message': f"{count} overdue invoices, total {_fmt(amount)} outstanding",
    }]


# =============================================================================
# 🔵 INFO ALERTS
# =============================================================================

def _check_coming_due(ar_df: pd.DataFrame) -> List[Dict]:
    """Invoices due within next 7 days."""
    if ar_df.empty or 'due_date' not in ar_df.columns:
        return []

    df = ar_df.copy()
    df['due_date'] = pd.to_datetime(df['due_date'], errors='coerce')
    today = pd.Timestamp(date.today())
    cutoff = today + pd.Timedelta(days=COMING_DUE_DAYS)

    coming = df[(df['due_date'] >= today) & (df['due_date'] <= cutoff)]
    if coming.empty:
        return []

    count = coming['inv_number'].nunique() if 'inv_number' in coming.columns else len(coming)
    amount = coming['outstanding_by_split_usd'].sum() if 'outstanding_by_split_usd' in coming.columns else 0

    if amount <= 0:
        return []

    return [{
        'severity': 'low', 'icon': '🔵',
        'message': f"{count} invoices ({_fmt(amount)}) due within {COMING_DUE_DAYS} days — follow up on payment",
    }]


# =============================================================================
# HELPERS
# =============================================================================

def _get_overdue(ar_df: pd.DataFrame, min_days: int = 0) -> pd.DataFrame:
    """Get overdue AR rows (due_date < today by at least min_days)."""
    if ar_df.empty or 'due_date' not in ar_df.columns:
        return pd.DataFrame()

    df = ar_df.copy()
    df['due_date'] = pd.to_datetime(df['due_date'], errors='coerce')
    today = pd.Timestamp(date.today())
    cutoff = today - pd.Timedelta(days=min_days)

    return df[df['due_date'] < cutoff]


def _get_elapsed_ratio(filters: Dict) -> Optional[float]:
    """Ratio of time elapsed in period (0.0–1.0)."""
    today = date.today()
    period_type = filters.get('period_type', 'YTD')
    year = filters.get('year', today.year)

    if period_type == 'YTD':
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        total = (end - start).days
        return max(0, min(1, (today - start).days / total)) if total > 0 else None
    elif period_type == 'QTD':
        cq = (today.month - 1) // 3 + 1
        start = date(year, (cq - 1) * 3 + 1, 1)
        q_end_month = cq * 3
        if q_end_month == 12:
            end = date(year, 12, 31)
        else:
            end = date(year, q_end_month + 1, 1)
        total = (end - start).days
        return max(0, min(1, (today - start).days / total)) if total > 0 else None
    elif period_type == 'MTD':
        import calendar
        last_day = calendar.monthrange(year, today.month)[1]
        return max(0, min(1, today.day / last_day))
    elif period_type == 'LY':
        return 1.0
    elif period_type == 'Custom':
        start, end = filters.get('start_date'), filters.get('end_date')
        if start and end:
            total = (end - start).days
            return max(0, min(1, (today - start).days / total)) if total > 0 else None
    return None
