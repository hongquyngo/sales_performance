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

VERSION: 2.0.0 — Added collect_warning_data(), collect_recipients_warning_summary()
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
        'severity': 'high', 'icon': '🔴', 'category': 'backlog',
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
        'severity': 'high', 'icon': '🔴', 'category': 'ar',
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
                'severity': 'medium', 'icon': '🟡', 'category': 'kpi',
                'message': (
                    f"{display}: {_fmt(actual)} vs target {_fmt(prorated_target)} "
                    f"({achievement:.0f}% — expected ~{expected_pct:.0f}%)"
                ),
            })
        elif achievement < KPI_WARNING_RATIO * 100:
            display = kpi_name.replace('_', ' ').title()
            alerts.append({
                'severity': 'medium', 'icon': '🟡', 'category': 'kpi',
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
        'severity': 'medium', 'icon': '🟡', 'category': 'ar',
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
        'severity': 'low', 'icon': '🔵', 'category': 'payment_coming_due',
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


# =============================================================================
# WARNING EMAIL: ENRICHED DATA (v2.0)
# =============================================================================

def collect_warning_data(
    employee_id: int,
    employee_name: str,
    sales_df: pd.DataFrame,
    backlog_detail_df: pd.DataFrame,
    ar_outstanding_df: pd.DataFrame,
    targets_df: pd.DataFrame,
    active_filters: Dict,
) -> Dict:
    """
    Collect enriched warning data for one salesperson.

    Extends collect_per_employee_bulletin() with:
    - AR aging table (per-bucket breakdown)
    - Customers at risk (per-customer outstanding + invoice list)
    - Structured data for warning email template

    Returns:
        Dict with keys: bulletin, metrics, ar_summary, customers_at_risk
    """
    # 1. Base bulletin + metrics (existing logic)
    bulletin, metrics = collect_per_employee_bulletin(
        employee_id=employee_id,
        employee_name=employee_name,
        sales_df=sales_df,
        backlog_detail_df=backlog_detail_df,
        ar_outstanding_df=ar_outstanding_df,
        targets_df=targets_df,
        active_filters=active_filters,
    )

    # 2. AR detail (enrichment)
    my_ar = _filter_by_employee(ar_outstanding_df, employee_id, 'sales_id')
    my_backlog = _filter_by_employee(backlog_detail_df, employee_id, 'sales_id')
    my_sales = _filter_by_employee(sales_df, employee_id, 'sales_id')
    my_targets = _filter_by_employee(targets_df, employee_id, 'employee_id')

    ar_summary = _build_ar_aging_summary(my_ar)
    customers_at_risk = _build_customers_at_risk(my_ar)

    return {
        'bulletin': bulletin,
        'metrics': metrics,
        'ar_summary': ar_summary,
        'customers_at_risk': customers_at_risk,
        # Raw filtered DataFrames (for Excel attachment)
        'ar_df': my_ar,
        'backlog_df': my_backlog,
        'sales_df': my_sales,
        'targets_df': my_targets,
    }


def _build_ar_aging_summary(ar_df: pd.DataFrame) -> Dict:
    """Build AR aging summary for warning email."""
    if ar_df.empty:
        return {
            'total_outstanding': 0,
            'total_overdue': 0,
            'aging_table': [],
            'worst_bucket': 'OK',
            'overdue_invoice_count': 0,
        }

    out_col = 'outstanding_by_split_usd'
    if out_col not in ar_df.columns:
        return {
            'total_outstanding': 0, 'total_overdue': 0,
            'aging_table': [], 'worst_bucket': 'OK',
            'overdue_invoice_count': 0,
        }

    df = ar_df.copy()
    df[out_col] = pd.to_numeric(df[out_col], errors='coerce').fillna(0)
    outstanding_df = df[df[out_col] > 0.01]

    if outstanding_df.empty:
        return {
            'total_outstanding': 0, 'total_overdue': 0,
            'aging_table': [], 'worst_bucket': 'OK',
            'overdue_invoice_count': 0,
        }

    total_outstanding = outstanding_df[out_col].sum()

    # Aging buckets
    aging_col = 'aging_bucket'
    days_col = 'days_overdue'

    bucket_order = [
        ('90+ days overdue', 91, '🔴'),
        ('61-90 days overdue', 61, '🟠'),
        ('31-60 days overdue', 31, '🟡'),
        ('1-30 days overdue', 1, '🟢'),
        ('Not Yet Due', -999, '✅'),
        ('No Due Date', -999, '⚪'),
    ]

    aging_table = []
    worst_bucket = 'OK'

    if aging_col in outstanding_df.columns and outstanding_df[aging_col].notna().any():
        for bucket_name, min_days, icon in bucket_order:
            bucket_df = outstanding_df[outstanding_df[aging_col] == bucket_name]
            if bucket_df.empty:
                continue
            amount = bucket_df[out_col].sum()
            count = bucket_df['inv_number'].nunique() if 'inv_number' in bucket_df.columns else len(bucket_df)
            share = amount / total_outstanding if total_outstanding > 0 else 0
            aging_table.append({
                'bucket': bucket_name,
                'icon': icon,
                'amount': amount,
                'count': count,
                'share': share,
                'min_days': min_days,
            })
            if worst_bucket == 'OK' and min_days > 0:
                worst_bucket = bucket_name
    elif days_col in outstanding_df.columns:
        outstanding_df[days_col] = pd.to_numeric(outstanding_df[days_col], errors='coerce').fillna(0)
        for bucket_name, min_days, icon in bucket_order:
            if bucket_name == 'Not Yet Due':
                mask = outstanding_df[days_col] < 0
            elif bucket_name == '1-30 days overdue':
                mask = (outstanding_df[days_col] >= 1) & (outstanding_df[days_col] <= 30)
            elif bucket_name == '31-60 days overdue':
                mask = (outstanding_df[days_col] >= 31) & (outstanding_df[days_col] <= 60)
            elif bucket_name == '61-90 days overdue':
                mask = (outstanding_df[days_col] >= 61) & (outstanding_df[days_col] <= 90)
            elif bucket_name == '90+ days overdue':
                mask = outstanding_df[days_col] >= 91
            else:
                continue
            bucket_df = outstanding_df[mask]
            if bucket_df.empty:
                continue
            amount = bucket_df[out_col].sum()
            count = bucket_df['inv_number'].nunique() if 'inv_number' in bucket_df.columns else len(bucket_df)
            share = amount / total_outstanding if total_outstanding > 0 else 0
            aging_table.append({
                'bucket': bucket_name, 'icon': icon,
                'amount': amount, 'count': count, 'share': share,
                'min_days': min_days,
            })
            if worst_bucket == 'OK' and min_days > 0:
                worst_bucket = bucket_name

    # Total overdue
    total_overdue = sum(b['amount'] for b in aging_table if b['min_days'] > 0)
    overdue_inv_count = sum(b['count'] for b in aging_table if b['min_days'] > 0)

    return {
        'total_outstanding': total_outstanding,
        'total_overdue': total_overdue,
        'aging_table': aging_table,
        'worst_bucket': worst_bucket,
        'overdue_invoice_count': overdue_inv_count,
    }


def _build_customers_at_risk(ar_df: pd.DataFrame) -> List[Dict]:
    """Build per-customer risk breakdown for warning email."""
    if ar_df.empty or 'customer' not in ar_df.columns:
        return []

    out_col = 'outstanding_by_split_usd'
    days_col = 'days_overdue'
    if out_col not in ar_df.columns:
        return []

    df = ar_df.copy()
    df[out_col] = pd.to_numeric(df[out_col], errors='coerce').fillna(0)
    if days_col in df.columns:
        df[days_col] = pd.to_numeric(df[days_col], errors='coerce').fillna(0)

    # Only overdue customers
    if days_col in df.columns:
        overdue_df = df[df[days_col] > 0]
    elif 'due_date' in df.columns:
        df['due_date'] = pd.to_datetime(df['due_date'], errors='coerce')
        today = pd.Timestamp(date.today())
        overdue_df = df[df['due_date'] < today]
    else:
        return []

    overdue_df = overdue_df[overdue_df[out_col] > 0.01]
    if overdue_df.empty:
        return []

    customers = []
    for customer, cust_df in overdue_df.groupby('customer'):
        outstanding = cust_df[out_col].sum()
        invoices = sorted(cust_df['inv_number'].unique().tolist()) if 'inv_number' in cust_df.columns else []
        max_days = int(cust_df[days_col].max()) if days_col in cust_df.columns else 0
        aging = cust_df['aging_bucket'].mode().iloc[0] if 'aging_bucket' in cust_df.columns and not cust_df['aging_bucket'].mode().empty else ''

        customers.append({
            'customer': customer,
            'outstanding': outstanding,
            'invoices': invoices[:10],  # Cap at 10 invoice numbers
            'invoice_count': len(invoices),
            'max_days_overdue': max_days,
            'aging_bucket': aging,
        })

    # Sort by outstanding descending, top 10
    customers.sort(key=lambda x: x['outstanding'], reverse=True)
    return customers[:10]


# =============================================================================
# BATCH SUMMARY FOR RECIPIENT TABLE (v2.0)
# =============================================================================

def collect_recipients_warning_summary(
    employee_ids: List[int],
    ar_outstanding_df: pd.DataFrame,
    sales_df: pd.DataFrame,
    backlog_detail_df: pd.DataFrame,
    targets_df: pd.DataFrame,
    active_filters: Dict,
    prefs_cache: Optional[Dict] = None,
) -> pd.DataFrame:
    """
    Build summary table for recipient selection in Send Warning UI.

    Returns DataFrame with one row per employee:
        employee_id, name, overdue_amount, customer_count,
        worst_aging, worst_icon, alert_count, enabled
    """
    rows = []

    # Get names from sales_df
    name_map = {}
    if not sales_df.empty and 'sales_id' in sales_df.columns and 'sales_name' in sales_df.columns:
        name_map = sales_df.drop_duplicates('sales_id').set_index('sales_id')['sales_name'].to_dict()

    for eid in employee_ids:
        name = name_map.get(eid, f"Employee #{eid}")

        # AR summary
        ar_summary = {'total_overdue': 0, 'worst_bucket': 'OK', 'overdue_invoice_count': 0}
        if not ar_outstanding_df.empty and 'sales_id' in ar_outstanding_df.columns:
            my_ar = ar_outstanding_df[ar_outstanding_df['sales_id'] == eid]
            if not my_ar.empty:
                ar_summary = _build_ar_aging_summary(my_ar)

        # Alert count (lightweight — just count, don't build full bulletin)
        alert_count = 0
        try:
            bulletin, _ = collect_per_employee_bulletin(
                employee_id=eid, employee_name=name,
                sales_df=sales_df, backlog_detail_df=backlog_detail_df,
                ar_outstanding_df=ar_outstanding_df, targets_df=targets_df,
                active_filters=active_filters,
            )
            alert_count = bulletin.get('alert_count', 0)
        except Exception:
            pass

        # Customer count at risk
        customer_count = 0
        if not ar_outstanding_df.empty and 'sales_id' in ar_outstanding_df.columns:
            my_ar = ar_outstanding_df[ar_outstanding_df['sales_id'] == eid]
            if not my_ar.empty and 'days_overdue' in my_ar.columns:
                my_ar_overdue = my_ar[pd.to_numeric(my_ar['days_overdue'], errors='coerce').fillna(0) > 0]
                if 'customer' in my_ar_overdue.columns:
                    customer_count = my_ar_overdue['customer'].nunique()

        # Preferences
        enabled = True
        if prefs_cache and eid in prefs_cache:
            master = prefs_cache.get(eid, {}).get('all', {})
            enabled = master.get('enabled', True)

        # Worst aging icon
        icon_map = {
            '90+ days overdue': '🔴', '61-90 days overdue': '🟠',
            '31-60 days overdue': '🟡', '1-30 days overdue': '🟢',
            'Not Yet Due': '✅', 'OK': '✅',
        }
        worst = ar_summary.get('worst_bucket', 'OK')

        rows.append({
            'employee_id': eid,
            'name': name,
            'overdue_amount': ar_summary.get('total_overdue', 0),
            'customer_count': customer_count,
            'worst_aging': worst,
            'worst_icon': icon_map.get(worst, '✅'),
            'alert_count': alert_count,
            'enabled': enabled,
        })

    return pd.DataFrame(rows)


# =============================================================================
# EXCEL ATTACHMENT GENERATOR (v3.0)
# =============================================================================

# Column display configs per language
_EXCEL_TEXTS = {
    'en': {
        'sheet_ar': 'AR Overdue Detail',
        'sheet_backlog': 'Backlog Past ETD',
        'sheet_kpi': 'KPI Summary',
        'sheet_alerts': 'Alert Summary',
        'filename': 'Warning_Detail_{name}_{date}.xlsx',
        'alert_cols': {'icon': 'Severity', 'category': 'Category', 'message': 'Alert Message'},
        'kpi_cols': {'kpi': 'KPI', 'target': 'Annual Target', 'prorated': 'Prorated Target',
                     'actual': 'Actual', 'achievement': 'Achievement %', 'status': 'Status'},
    },
    'vi': {
        'sheet_ar': 'Chi Tiết CN Quá Hạn',
        'sheet_backlog': 'Backlog Quá Hạn ETD',
        'sheet_kpi': 'Tóm Tắt KPI',
        'sheet_alerts': 'Tóm Tắt Cảnh Báo',
        'filename': 'Canh_Bao_{name}_{date}.xlsx',
        'alert_cols': {'icon': 'Mức Độ', 'category': 'Nhóm', 'message': 'Nội Dung Cảnh Báo'},
        'kpi_cols': {'kpi': 'KPI', 'target': 'Mục Tiêu Năm', 'prorated': 'Mục Tiêu Tỷ Lệ',
                     'actual': 'Thực Tế', 'achievement': '% Đạt', 'status': 'Trạng Thái'},
    },
}

# AR column rename mapping
_AR_COLUMNS_EN = {
    'customer': 'Customer',
    'inv_number': 'Invoice #',
    'inv_date': 'Invoice Date',
    'due_date': 'Due Date',
    'days_overdue': 'Days Overdue',
    'outstanding_by_split_usd': 'Outstanding (USD)',
    'aging_bucket': 'Aging Bucket',
}
_AR_COLUMNS_VI = {
    'customer': 'Khách Hàng',
    'inv_number': 'Số Hóa Đơn',
    'inv_date': 'Ngày Hóa Đơn',
    'due_date': 'Ngày Đến Hạn',
    'days_overdue': 'Số Ngày Quá Hạn',
    'outstanding_by_split_usd': 'Công Nợ (USD)',
    'aging_bucket': 'Nhóm Tuổi Nợ',
}

_BACKLOG_COLUMNS_EN = {
    'oc_number': 'OC Number',
    'customer': 'Customer',
    'product_name': 'Product',
    'etd': 'ETD',
    'backlog_sales_by_split_usd': 'Backlog Value (USD)',
}
_BACKLOG_COLUMNS_VI = {
    'oc_number': 'Số OC',
    'customer': 'Khách Hàng',
    'product_name': 'Sản Phẩm',
    'etd': 'Ngày Giao Dự Kiến',
    'backlog_sales_by_split_usd': 'Giá Trị Backlog (USD)',
}


def generate_warning_excel(
    warning_data: Dict,
    active_filters: Dict,
    lang: str = 'en',
) -> Optional[str]:
    """
    Generate Excel attachment with warning detail data.

    Creates a temp .xlsx file with sheets:
    - AR Overdue Detail (sorted by days overdue desc)
    - Backlog Past ETD (sorted by ETD)
    - KPI Summary
    - Alert Summary

    Args:
        warning_data:    Output of collect_warning_data() (includes raw DFs)
        active_filters:  Current filter state
        lang:            'en' or 'vi'

    Returns:
        Path to temp xlsx file, or None if no data.
        Caller must delete the file after use.
    """
    import tempfile
    from datetime import date as _date

    ar_df = warning_data.get('ar_df', pd.DataFrame())
    backlog_df = warning_data.get('backlog_df', pd.DataFrame())
    targets_df = warning_data.get('targets_df', pd.DataFrame())
    sales_df = warning_data.get('sales_df', pd.DataFrame())
    bulletin = warning_data.get('bulletin', {})
    alerts = bulletin.get('alerts', [])
    employee_name = bulletin.get('employee_name', 'Employee')

    # Skip if no data at all
    if ar_df.empty and backlog_df.empty and not alerts:
        return None

    txt = _EXCEL_TEXTS.get(lang, _EXCEL_TEXTS['en'])
    ar_cols = _AR_COLUMNS_VI if lang == 'vi' else _AR_COLUMNS_EN
    bl_cols = _BACKLOG_COLUMNS_VI if lang == 'vi' else _BACKLOG_COLUMNS_EN

    # Build safe filename
    safe_name = employee_name.replace(' ', '_')[:30]
    date_str = _date.today().strftime('%Y%m%d')
    filename = txt['filename'].format(name=safe_name, date=date_str)

    # Create temp file
    tmp = tempfile.NamedTemporaryFile(
        suffix='.xlsx', prefix='warning_', delete=False,
        dir='/tmp',
    )
    tmp_path = tmp.name
    tmp.close()

    try:
        with pd.ExcelWriter(tmp_path, engine='openpyxl') as writer:
            sheet_count = 0

            # ─── Sheet 1: AR Overdue Detail ───
            if not ar_df.empty:
                _write_ar_sheet(writer, ar_df, ar_cols, txt['sheet_ar'])
                sheet_count += 1

            # ─── Sheet 2: Backlog Past ETD ───
            if not backlog_df.empty:
                _write_backlog_sheet(writer, backlog_df, bl_cols, txt['sheet_backlog'])
                sheet_count += 1

            # ─── Sheet 3: KPI Summary ───
            if not targets_df.empty and not sales_df.empty:
                _write_kpi_sheet(
                    writer, sales_df, targets_df,
                    active_filters, txt, lang,
                )
                sheet_count += 1

            # ─── Sheet 4: Alert Summary ───
            if alerts:
                _write_alerts_sheet(writer, alerts, txt)
                sheet_count += 1

            if sheet_count == 0:
                import os
                os.unlink(tmp_path)
                return None

        logger.info(f"Warning Excel generated: {tmp_path} ({sheet_count} sheets)")
        return tmp_path

    except Exception as e:
        logger.error(f"Error generating warning Excel: {e}")
        try:
            import os
            os.unlink(tmp_path)
        except Exception:
            pass
        return None


def _write_ar_sheet(
    writer: pd.ExcelWriter,
    ar_df: pd.DataFrame,
    col_map: Dict[str, str],
    sheet_name: str,
):
    """Write AR overdue detail sheet."""
    # Select and rename available columns
    available = [c for c in col_map.keys() if c in ar_df.columns]
    if not available:
        return

    df = ar_df[available].copy()

    # Sort by days_overdue desc if available
    if 'days_overdue' in df.columns:
        df['days_overdue'] = pd.to_numeric(df['days_overdue'], errors='coerce').fillna(0)
        df = df.sort_values('days_overdue', ascending=False)

    # Only overdue rows (days > 0)
    if 'days_overdue' in df.columns:
        df = df[df['days_overdue'] > 0]

    if df.empty:
        return

    # Format outstanding
    if 'outstanding_by_split_usd' in df.columns:
        df['outstanding_by_split_usd'] = pd.to_numeric(
            df['outstanding_by_split_usd'], errors='coerce'
        ).fillna(0).round(2)

    rename = {c: col_map[c] for c in available}
    df.rename(columns=rename, inplace=True)
    df.to_excel(writer, sheet_name=sheet_name, index=False)

    # Auto-width
    _auto_width(writer, sheet_name, df)


def _write_backlog_sheet(
    writer: pd.ExcelWriter,
    backlog_df: pd.DataFrame,
    col_map: Dict[str, str],
    sheet_name: str,
):
    """Write backlog past ETD sheet."""
    df = backlog_df.copy()

    # Filter to past ETD only
    if 'etd' in df.columns:
        df['etd'] = pd.to_datetime(df['etd'], errors='coerce')
        today = pd.Timestamp(date.today())
        df = df[df['etd'] < today]

    if df.empty:
        return

    available = [c for c in col_map.keys() if c in df.columns]
    if not available:
        return

    df = df[available].copy()

    if 'backlog_sales_by_split_usd' in df.columns:
        df['backlog_sales_by_split_usd'] = pd.to_numeric(
            df['backlog_sales_by_split_usd'], errors='coerce'
        ).fillna(0).round(2)

    if 'etd' in df.columns:
        df = df.sort_values('etd')

    rename = {c: col_map[c] for c in available}
    df.rename(columns=rename, inplace=True)
    df.to_excel(writer, sheet_name=sheet_name, index=False)
    _auto_width(writer, sheet_name, df)


def _write_kpi_sheet(
    writer: pd.ExcelWriter,
    sales_df: pd.DataFrame,
    targets_df: pd.DataFrame,
    active_filters: Dict,
    txt: Dict,
    lang: str,
):
    """Write KPI summary sheet."""
    elapsed = _get_elapsed_ratio(active_filters)
    if elapsed is None or elapsed < 0.05:
        return

    kpi_map = {
        'revenue': 'sales_by_split_usd',
        'gross_profit': 'gross_profit_by_split_usd',
        'gross_profit_1': 'gp1_by_split_usd',
    }

    kpi_txt = txt.get('kpi_cols', _EXCEL_TEXTS['en']['kpi_cols'])
    rows = []

    for _, row in targets_df.iterrows():
        kpi_name = str(row.get('kpi_name', '')).lower().replace(' ', '_')
        annual_target = row.get('annual_target_value_numeric', 0)
        if annual_target <= 0:
            continue

        col = kpi_map.get(kpi_name)
        if not col or col not in sales_df.columns:
            continue

        actual = sales_df[col].sum()
        prorated = annual_target * elapsed
        achievement = (actual / prorated * 100) if prorated > 0 else 0

        status = '✅ On Track' if lang == 'en' else '✅ Đạt'
        if achievement < KPI_CRITICAL_RATIO * 100:
            status = '🔴 Critical' if lang == 'en' else '🔴 Nghiêm Trọng'
        elif achievement < KPI_WARNING_RATIO * 100:
            status = '🟡 Behind' if lang == 'en' else '🟡 Chậm Tiến Độ'

        rows.append({
            kpi_txt['kpi']: kpi_name.replace('_', ' ').title(),
            kpi_txt['target']: round(annual_target, 2),
            kpi_txt['prorated']: round(prorated, 2),
            kpi_txt['actual']: round(actual, 2),
            kpi_txt['achievement']: f"{achievement:.1f}%",
            kpi_txt['status']: status,
        })

    if not rows:
        return

    df = pd.DataFrame(rows)
    sheet_name = txt.get('sheet_kpi', 'KPI Summary')
    df.to_excel(writer, sheet_name=sheet_name, index=False)
    _auto_width(writer, sheet_name, df)


def _write_alerts_sheet(writer: pd.ExcelWriter, alerts: List[Dict], txt: Dict):
    """Write alert summary sheet."""
    alert_cols = txt.get('alert_cols', _EXCEL_TEXTS['en']['alert_cols'])
    category_labels = {
        'backlog': '📦 Backlog',
        'ar': '💰 AR Overdue',
        'kpi': '🎯 KPI',
        'payment_coming_due': '⏰ Payment Due',
    }

    rows = []
    for a in alerts:
        rows.append({
            alert_cols['icon']: a.get('icon', '•'),
            alert_cols['category']: category_labels.get(a.get('category', ''), a.get('category', '')),
            alert_cols['message']: a.get('message', ''),
        })

    df = pd.DataFrame(rows)
    sheet_name = txt.get('sheet_alerts', 'Alert Summary')
    df.to_excel(writer, sheet_name=sheet_name, index=False)
    _auto_width(writer, sheet_name, df)


def _auto_width(writer: pd.ExcelWriter, sheet_name: str, df: pd.DataFrame):
    """Auto-adjust column widths."""
    try:
        ws = writer.sheets[sheet_name]
        for idx, col in enumerate(df.columns):
            max_len = max(
                df[col].astype(str).str.len().max(),
                len(str(col)),
            ) + 3
            max_len = min(max_len, 50)  # Cap at 50
            ws.column_dimensions[chr(65 + idx) if idx < 26 else 'A'].width = max_len
    except Exception:
        pass