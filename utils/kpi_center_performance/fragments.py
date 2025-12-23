# utils/kpi_center_performance/fragments.py
"""
Streamlit Fragments for KPI Center Performance

Reusable UI components using @st.fragment for partial reruns.

VERSION: 2.3.0
CHANGELOG:
- v2.3.0: Phase 3 - Pareto Analysis:
          - top_performers_fragment(): Customer/Brand/Product analysis
          - 80/20 concentration insights
          - Interactive charts and recommendations
- v2.2.0: Phase 2 enhancements:
          - sales_detail_fragment: Added summary metrics cards at top
          - backlog_list_fragment: Added total_backlog_df for overall totals
          - monthly_trend_fragment: Added targets overlay option
- v2.0.0: Added risk indicators to backlog list
          Added enhanced filtering options

Components:
- monthly_trend_fragment: Monthly performance charts with targets
- yoy_comparison_fragment: Year-over-Year comparison
- sales_detail_fragment: Transaction list with filters and summary cards
- pivot_analysis_fragment: Configurable pivot tables
- backlog_list_fragment: Backlog detail with risk indicators
- kpi_center_ranking_fragment: Performance ranking
- top_performers_fragment: Pareto / Top performers analysis (NEW)
- export_report_fragment: Excel report generation
"""

import logging
from typing import Dict, Optional, List
import pandas as pd
import streamlit as st

from .charts import KPICenterCharts
from .constants import MONTH_ORDER

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _clean_dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Clean dataframe for display - handle NaN, dates, etc."""
    if df.empty:
        return df
    
    df = df.copy()
    
    # Convert date columns
    date_cols = ['inv_date', 'oc_date', 'etd', 'first_sale_date']
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    
    # Fill NaN for string columns
    str_cols = df.select_dtypes(include=['object']).columns
    df[str_cols] = df[str_cols].fillna('')
    
    return df


def _format_currency(value) -> str:
    """Format number as currency."""
    try:
        return f"${value:,.0f}"
    except:
        return str(value)


def _format_percent(value) -> str:
    try:
        return f"{value:.1f}%"
    except:
        return str(value)


def _add_risk_indicator(days_until_etd) -> str:
    try:
        days = float(days_until_etd)
        if pd.isna(days):
            return "⚪"
        if days < 0:
            return "🔴"
        elif days <= 7:
            return "🟡"
        elif days <= 30:
            return "🟢"
        else:
            return "⚪"
    except:
        return "⚪"


# =============================================================================
# MONTHLY TREND FRAGMENT - ENHANCED v2.2.0 with Targets
# =============================================================================

@st.fragment
def monthly_trend_fragment(
    sales_df: pd.DataFrame,
    filter_values: Dict,
    targets_df: pd.DataFrame = None,
    show_cumulative: bool = True
):
    """
    Monthly trend chart with optional targets overlay.
    
    Args:
        sales_df: Sales data DataFrame
        filter_values: Current filter settings
        targets_df: Optional targets DataFrame for overlay
        show_cumulative: Whether to show cumulative toggle
    """
    if sales_df.empty:
        st.info("No sales data for trend analysis")
        return
    
    col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
    
    with col1:
        customers = ['All'] + sorted(sales_df['customer'].dropna().unique().tolist())
        selected_customer = st.selectbox("Customer", customers, key="trend_customer_filter")
    
    with col2:
        brands = ['All'] + sorted(sales_df['brand'].dropna().unique().tolist())
        selected_brand = st.selectbox("Brand", brands, key="trend_brand_filter")
    
    with col3:
        metric = st.selectbox("Metric", ["Revenue", "Gross Profit", "GP1"], key="trend_metric_selector")
    
    with col4:
        # NEW v2.2.0: Target overlay toggle
        show_target = st.checkbox("Show Target", value=True, key="trend_show_target",
                                  help="Overlay monthly target line on chart")
    
    filtered_df = sales_df.copy()
    
    if selected_customer != 'All':
        filtered_df = filtered_df[filtered_df['customer'] == selected_customer]
    if selected_brand != 'All':
        filtered_df = filtered_df[filtered_df['brand'] == selected_brand]
    
    if filtered_df.empty:
        st.warning("No data matches the selected filters")
        return
    
    if 'invoice_month' not in filtered_df.columns:
        if 'inv_date' in filtered_df.columns:
            filtered_df['inv_date'] = pd.to_datetime(filtered_df['inv_date'], errors='coerce')
            filtered_df['invoice_month'] = filtered_df['inv_date'].dt.strftime('%b')
        else:
            st.warning("Cannot determine month from data")
            return
    
    metric_col_map = {'Revenue': 'sales_by_kpi_center_usd', 'Gross Profit': 'gross_profit_by_kpi_center_usd', 'GP1': 'gp1_by_kpi_center_usd'}
    value_col = metric_col_map.get(metric, 'sales_by_kpi_center_usd')
    
    if value_col not in filtered_df.columns:
        st.warning(f"Column {value_col} not available")
        return
    
    monthly = filtered_df.groupby('invoice_month').agg({value_col: 'sum'}).reset_index()
    monthly.columns = ['month', 'revenue' if metric == 'Revenue' else 'gross_profit' if metric == 'Gross Profit' else 'gp1']
    monthly['month_order'] = monthly['month'].map({m: i for i, m in enumerate(MONTH_ORDER)})
    monthly = monthly.sort_values('month_order')
    
    # NEW v2.2.0: Calculate monthly target from targets_df
    monthly_target = None
    if show_target and targets_df is not None and not targets_df.empty:
        # Map metric to KPI name
        kpi_name_map = {'Revenue': 'revenue', 'Gross Profit': 'gross_profit', 'GP1': 'gross_profit_1'}
        kpi_name = kpi_name_map.get(metric, 'revenue')
        
        # Sum annual targets for this KPI type
        mask = targets_df['kpi_name'].str.lower() == kpi_name.lower()
        annual_target = targets_df[mask]['annual_target_value_numeric'].sum()
        
        if annual_target > 0:
            monthly_target = annual_target / 12
    
    chart = KPICenterCharts.build_monthly_trend_chart(
        monthly_df=monthly, 
        metric=metric,
        show_target=show_target and monthly_target is not None,
        target_value=monthly_target
    )
    st.altair_chart(chart, use_container_width=True)
    
    # Summary table
    st.markdown("**Monthly Summary**")
    display_df = monthly[['month', monthly.columns[1]]].copy()
    display_df.columns = ['Month', metric]
    
    # Add target column if available
    if monthly_target is not None and show_target:
        display_df['Target'] = monthly_target
        display_df['Achievement %'] = (display_df[metric] / monthly_target * 100).round(1)
    
    st.dataframe(display_df, hide_index=True, column_config={
        'Revenue': st.column_config.NumberColumn(format="$%,.0f"),
        'Gross Profit': st.column_config.NumberColumn(format="$%,.0f"),
        'GP1': st.column_config.NumberColumn(format="$%,.0f"),
        'Target': st.column_config.NumberColumn(format="$%,.0f"),
        'Achievement %': st.column_config.NumberColumn(format="%.1f%%"),
    }, use_container_width=True)


# =============================================================================
# YOY COMPARISON FRAGMENT
# =============================================================================

@st.fragment
def yoy_comparison_fragment(queries, filter_values: Dict, current_year: int):
    from datetime import date
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        compare_year = st.selectbox("Compare with", 
                                    [current_year - 1, current_year - 2, current_year - 3],
                                    key="yoy_compare_year")
    
    start_date = filter_values['start_date']
    end_date = filter_values['end_date']
    kpi_center_ids = filter_values.get('kpi_center_ids', [])
    entity_ids = filter_values.get('entity_ids', [])
    
    current_sales = queries.get_sales_data(start_date=start_date, end_date=end_date, 
                                           kpi_center_ids=kpi_center_ids, entity_ids=entity_ids if entity_ids else None)
    
    try:
        compare_start = date(compare_year, start_date.month, start_date.day)
        compare_end = date(compare_year, end_date.month, end_date.day)
    except ValueError:
        compare_start = date(compare_year, start_date.month, 28)
        compare_end = date(compare_year, end_date.month, 28)
    
    compare_sales = queries.get_sales_data(start_date=compare_start, end_date=compare_end,
                                           kpi_center_ids=kpi_center_ids, entity_ids=entity_ids if entity_ids else None)
    
    if filter_values.get('exclude_internal_revenue', True):
        if not current_sales.empty and 'customer_type' in current_sales.columns:
            current_sales = current_sales[current_sales['customer_type'] != 'Internal']
        if not compare_sales.empty and 'customer_type' in compare_sales.columns:
            compare_sales = compare_sales[compare_sales['customer_type'] != 'Internal']
    
    with col2:
        metric = st.radio("Metric", ["Revenue", "Gross Profit", "GP1"], horizontal=True, key="yoy_metric")
    
    def prepare_monthly(df, metric):
        if df.empty: return pd.DataFrame()
        df = df.copy()
        if 'inv_date' in df.columns:
            df['inv_date'] = pd.to_datetime(df['inv_date'], errors='coerce')
            df['month'] = df['inv_date'].dt.strftime('%b')
        elif 'invoice_month' in df.columns:
            df['month'] = df['invoice_month']
        else:
            return pd.DataFrame()
        metric_col_map = {"Revenue": "sales_by_kpi_center_usd", "Gross Profit": "gross_profit_by_kpi_center_usd", "GP1": "gp1_by_kpi_center_usd"}
        col_name = metric_col_map[metric]
        if col_name not in df.columns: return pd.DataFrame()
        return df.groupby('month')[col_name].sum().reset_index()
    
    current_monthly = prepare_monthly(current_sales, metric)
    compare_monthly = prepare_monthly(compare_sales, metric)
    
    chart = KPICenterCharts.build_yoy_comparison_chart(current_df=current_monthly, previous_df=compare_monthly,
                                                       metric=metric, current_year=current_year, previous_year=compare_year)
    st.altair_chart(chart, use_container_width=True)
    
    col_map = {"Revenue": "sales_by_kpi_center_usd", "Gross Profit": "gross_profit_by_kpi_center_usd", "GP1": "gp1_by_kpi_center_usd"}
    col_name = col_map[metric]
    current_total = current_sales[col_name].sum() if not current_sales.empty and col_name in current_sales.columns else 0
    compare_total = compare_sales[col_name].sum() if not compare_sales.empty and col_name in compare_sales.columns else 0
    
    col_curr, col_prev, col_change = st.columns(3)
    with col_curr:
        st.metric(label=f"{current_year} {metric}", value=_format_currency(current_total))
    with col_prev:
        st.metric(label=f"{compare_year} {metric}", value=_format_currency(compare_total))
    with col_change:
        if compare_total > 0:
            change_pct = ((current_total - compare_total) / compare_total) * 100
            st.metric(label="YoY Change", value=f"{change_pct:+.1f}%", delta=_format_currency(current_total - compare_total))
        else:
            st.metric(label="YoY Change", value="N/A", delta="No previous data")


# =============================================================================
# SALES DETAIL FRAGMENT - ENHANCED v2.2.0 with Summary Cards
# =============================================================================

@st.fragment
def sales_detail_fragment(sales_df: pd.DataFrame, filter_values: Dict):
    """
    Sales transaction detail with summary metrics cards and filters.
    
    NEW v2.2.0: Added summary metrics cards at top showing totals.
    """
    if sales_df.empty:
        st.info("No sales data available")
        return
    
    st.subheader("📋 Sales Transactions")
    
    # NEW v2.2.0: Summary Metrics Cards at top
    with st.container(border=True):
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        
        total_revenue = sales_df['sales_by_kpi_center_usd'].sum() if 'sales_by_kpi_center_usd' in sales_df.columns else 0
        total_gp = sales_df['gross_profit_by_kpi_center_usd'].sum() if 'gross_profit_by_kpi_center_usd' in sales_df.columns else 0
        total_gp1 = sales_df['gp1_by_kpi_center_usd'].sum() if 'gp1_by_kpi_center_usd' in sales_df.columns else 0
        total_orders = sales_df['inv_number'].nunique() if 'inv_number' in sales_df.columns else len(sales_df)
        
        with col_m1:
            st.metric("💰 Total Revenue", f"${total_revenue:,.0f}")
        with col_m2:
            st.metric("📈 Gross Profit", f"${total_gp:,.0f}")
        with col_m3:
            st.metric("📊 GP1", f"${total_gp1:,.0f}")
        with col_m4:
            st.metric("📋 Orders", f"{total_orders:,}")
    
    # Filters
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        search = st.text_input("🔍 Search", placeholder="Customer, Product, Invoice...", key="detail_search")
    with col2:
        kpi_centers = ['All'] + sorted(sales_df['kpi_center'].dropna().unique().tolist())
        selected_kc = st.selectbox("🎯 KPI Center", kpi_centers, key="detail_kpi_center")
    with col3:
        brands = ['All'] + sorted(sales_df['brand'].dropna().unique().tolist())
        selected_brand = st.selectbox("🏷️ Brand", brands, key="detail_brand")
    with col4:
        min_revenue = st.number_input("💰 Min Revenue", min_value=0, value=0, step=1000, key="detail_min_revenue")
    
    filtered_df = sales_df.copy()
    
    if search:
        search_lower = search.lower()
        mask = pd.Series([False] * len(filtered_df), index=filtered_df.index)
        for col in ['customer', 'product_pn', 'inv_number', 'oc_number', 'pt_code']:
            if col in filtered_df.columns:
                mask |= filtered_df[col].fillna('').astype(str).str.lower().str.contains(search_lower)
        filtered_df = filtered_df[mask]
    
    if selected_kc != 'All':
        filtered_df = filtered_df[filtered_df['kpi_center'] == selected_kc]
    if selected_brand != 'All':
        filtered_df = filtered_df[filtered_df['brand'] == selected_brand]
    if min_revenue > 0:
        filtered_df = filtered_df[filtered_df['sales_by_kpi_center_usd'] >= min_revenue]
    
    # Filtered totals
    filtered_revenue = filtered_df['sales_by_kpi_center_usd'].sum() if 'sales_by_kpi_center_usd' in filtered_df.columns else 0
    filtered_gp = filtered_df['gross_profit_by_kpi_center_usd'].sum() if 'gross_profit_by_kpi_center_usd' in filtered_df.columns else 0
    
    st.caption(f"📊 {len(filtered_df):,} of {len(sales_df):,} transactions • Revenue: ${filtered_revenue:,.0f} • GP: ${filtered_gp:,.0f}")
    
    if filtered_df.empty:
        st.warning("No transactions match the filters")
        return
    
    display_cols = ['inv_date', 'inv_number', 'vat_number', 'kpi_center', 'kpi_type', 'customer', 'customer_code',
                    'product_pn', 'pt_code', 'brand', 'sales_by_kpi_center_usd', 'gross_profit_by_kpi_center_usd',
                    'gp1_by_kpi_center_usd', 'split_rate_percent']
    display_cols = [c for c in display_cols if c in filtered_df.columns]
    display_df = _clean_dataframe_for_display(filtered_df[display_cols].head(500).copy())
    
    column_config = {
        'inv_date': st.column_config.DateColumn('📅 Date', width='small'),
        'inv_number': st.column_config.TextColumn('Invoice #', width='small'),
        'vat_number': st.column_config.TextColumn('VAT #', width='small'),
        'kpi_center': st.column_config.TextColumn('🎯 KPI Center'),
        'kpi_type': st.column_config.TextColumn('Type', width='small'),
        'customer': st.column_config.TextColumn('👤 Customer'),
        'customer_code': st.column_config.TextColumn('Code', width='small'),
        'product_pn': st.column_config.TextColumn('📦 Product'),
        'pt_code': st.column_config.TextColumn('PT Code', width='small'),
        'brand': st.column_config.TextColumn('🏷️ Brand', width='small'),
        'sales_by_kpi_center_usd': st.column_config.NumberColumn('💰 Revenue', format="$%,.0f"),
        'gross_profit_by_kpi_center_usd': st.column_config.NumberColumn('📈 GP', format="$%,.0f"),
        'gp1_by_kpi_center_usd': st.column_config.NumberColumn('GP1', format="$%,.0f"),
        'split_rate_percent': st.column_config.NumberColumn('Split %', format="%.0f%%", width='small'),
    }
    
    st.dataframe(display_df, hide_index=True, column_config=column_config, use_container_width=True)
    if len(filtered_df) > 500:
        st.caption("⚠️ Showing first 500 rows. Use Export for complete data.")


# =============================================================================
# PIVOT ANALYSIS FRAGMENT
# =============================================================================

@st.fragment
def pivot_analysis_fragment(sales_df: pd.DataFrame):
    if sales_df.empty:
        st.info("No data for pivot analysis")
        return
    
    st.subheader("📊 Pivot Analysis")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        row_options = [c for c in ['kpi_center', 'customer', 'brand', 'product_pn', 'invoice_month', 'kpi_type'] if c in sales_df.columns]
        rows = st.selectbox("Rows", row_options, key="pivot_rows")
    with col2:
        col_options = ['None'] + [c for c in row_options if c != rows]
        columns = st.selectbox("Columns", col_options, key="pivot_columns")
    with col3:
        values = st.selectbox("Values", ["Revenue", "Gross Profit", "GP1", "Count"], key="pivot_values")
    
    value_map = {"Revenue": 'sales_by_kpi_center_usd', "Gross Profit": 'gross_profit_by_kpi_center_usd', "GP1": 'gp1_by_kpi_center_usd', "Count": 'inv_number'}
    value_col = value_map[values]
    aggfunc = 'sum' if values != 'Count' else 'nunique'
    
    if value_col not in sales_df.columns:
        st.warning(f"Column {value_col} not available")
        return
    
    if columns == 'None':
        pivot = sales_df.groupby(rows)[value_col].agg(aggfunc).reset_index()
        pivot.columns = [rows, values]
        pivot = pivot.sort_values(values, ascending=False)
    else:
        pivot = pd.pivot_table(sales_df, values=value_col, index=rows, columns=columns, aggfunc=aggfunc, fill_value=0).reset_index()
    
    st.dataframe(_clean_dataframe_for_display(pivot.head(100)), hide_index=True, use_container_width=True)


# =============================================================================
# BACKLOG LIST FRAGMENT - ENHANCED v2.2.0 with Overall Totals
# =============================================================================

@st.fragment
def backlog_list_fragment(
    backlog_df: pd.DataFrame, 
    filter_values: Dict,
    total_backlog_df: pd.DataFrame = None
):
    """
    Backlog detail with risk indicators and filters.
    
    Args:
        backlog_df: Filtered backlog detail DataFrame
        filter_values: Current filter settings
        total_backlog_df: Optional overall backlog summary for comparison
                         NEW v2.2.0: Shows filtered vs total comparison
    """
    if backlog_df.empty:
        st.info("No backlog data available")
        return
    
    st.subheader("📦 Backlog Detail")
    
    # NEW v2.2.0: Summary cards showing filtered vs total
    if total_backlog_df is not None and not total_backlog_df.empty:
        with st.container(border=True):
            col_s1, col_s2, col_s3, col_s4 = st.columns(4)
            
            # Overall totals
            overall_revenue = total_backlog_df['total_backlog_usd'].sum() if 'total_backlog_usd' in total_backlog_df.columns else 0
            overall_gp = total_backlog_df['total_backlog_gp_usd'].sum() if 'total_backlog_gp_usd' in total_backlog_df.columns else 0
            overall_orders = int(total_backlog_df['backlog_orders'].sum()) if 'backlog_orders' in total_backlog_df.columns else 0
            
            # Detail totals
            detail_revenue = backlog_df['backlog_by_kpi_center_usd'].sum() if 'backlog_by_kpi_center_usd' in backlog_df.columns else 0
            detail_gp = backlog_df['backlog_gp_by_kpi_center_usd'].sum() if 'backlog_gp_by_kpi_center_usd' in backlog_df.columns else 0
            detail_orders = len(backlog_df)
            
            with col_s1:
                st.metric("💰 Total Backlog", f"${overall_revenue:,.0f}",
                         help="Total backlog across all KPI Centers")
            with col_s2:
                st.metric("📈 Total GP", f"${overall_gp:,.0f}")
            with col_s3:
                st.metric("📋 Total Orders", f"{overall_orders:,}")
            with col_s4:
                # Show overdue count from detail
                overdue_count = len(backlog_df[backlog_df.get('days_until_etd', pd.Series()) < 0]) if 'days_until_etd' in backlog_df.columns else 0
                st.metric("🔴 Overdue", f"{overdue_count:,}",
                         help="Orders with ETD in the past")
    
    # Filters
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        search = st.text_input("🔍 Search", placeholder="Customer, Product, OC#...", key="backlog_search")
    with col2:
        kpi_centers = ['All'] + sorted(backlog_df['kpi_center'].dropna().unique().tolist())
        selected_kc = st.selectbox("🎯 KPI Center", kpi_centers, key="backlog_kpi_center")
    with col3:
        etd_filter_options = ['All', '🔴 Overdue', '🟡 At Risk (7 days)', '🟢 On Track']
        selected_etd_filter = st.selectbox("⚠️ ETD Status", etd_filter_options, key="backlog_etd_filter")
    with col4:
        status_options = ['All'] + (backlog_df['pending_type'].dropna().unique().tolist() if 'pending_type' in backlog_df.columns else [])
        selected_status = st.selectbox("📋 Status", status_options, key="backlog_status")
    
    filtered_df = backlog_df.copy()
    
    if 'days_until_etd' in filtered_df.columns:
        filtered_df['risk_indicator'] = filtered_df['days_until_etd'].apply(_add_risk_indicator)
    
    if search:
        search_lower = search.lower()
        mask = pd.Series([False] * len(filtered_df), index=filtered_df.index)
        for col in ['customer', 'product_pn', 'oc_number', 'pt_code']:
            if col in filtered_df.columns:
                mask |= filtered_df[col].fillna('').astype(str).str.lower().str.contains(search_lower)
        filtered_df = filtered_df[mask]
    
    if selected_kc != 'All':
        filtered_df = filtered_df[filtered_df['kpi_center'] == selected_kc]
    
    if selected_etd_filter != 'All' and 'days_until_etd' in filtered_df.columns:
        if selected_etd_filter == '🔴 Overdue':
            filtered_df = filtered_df[filtered_df['days_until_etd'] < 0]
        elif selected_etd_filter == '🟡 At Risk (7 days)':
            filtered_df = filtered_df[(filtered_df['days_until_etd'] >= 0) & (filtered_df['days_until_etd'] <= 7)]
        elif selected_etd_filter == '🟢 On Track':
            filtered_df = filtered_df[filtered_df['days_until_etd'] > 7]
    
    if selected_status != 'All' and 'pending_type' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['pending_type'] == selected_status]
    
    total_backlog = filtered_df['backlog_by_kpi_center_usd'].sum() if 'backlog_by_kpi_center_usd' in filtered_df.columns else 0
    overdue_count = len(filtered_df[filtered_df.get('days_until_etd', pd.Series()) < 0]) if 'days_until_etd' in filtered_df.columns else 0
    st.caption(f"📦 {len(filtered_df):,} items • Filtered Total: ${total_backlog:,.0f}{f' • 🔴 {overdue_count} overdue' if overdue_count > 0 else ''}")
    
    if filtered_df.empty:
        st.warning("No backlog matches the filters")
        return
    
    display_cols = ['risk_indicator', 'oc_number', 'oc_date', 'etd', 'customer', 'product_pn', 'brand', 'kpi_center', 'kpi_type',
                    'backlog_by_kpi_center_usd', 'backlog_gp_by_kpi_center_usd', 'days_until_etd', 'days_since_order', 'pending_type', 'split_rate_percent']
    display_cols = [c for c in display_cols if c in filtered_df.columns]
    display_df = _clean_dataframe_for_display(filtered_df[display_cols].head(500).copy())
    
    column_config = {
        'risk_indicator': st.column_config.TextColumn('⚠️', width='small'),
        'oc_number': st.column_config.TextColumn('OC #'),
        'oc_date': st.column_config.DateColumn('📅 OC Date', width='small'),
        'etd': st.column_config.DateColumn('🚚 ETD', width='small'),
        'customer': st.column_config.TextColumn('👤 Customer'),
        'product_pn': st.column_config.TextColumn('📦 Product'),
        'brand': st.column_config.TextColumn('🏷️ Brand', width='small'),
        'kpi_center': st.column_config.TextColumn('🎯 KPI Center'),
        'kpi_type': st.column_config.TextColumn('Type', width='small'),
        'backlog_by_kpi_center_usd': st.column_config.NumberColumn('💰 Amount', format="$%,.0f"),
        'backlog_gp_by_kpi_center_usd': st.column_config.NumberColumn('📈 GP', format="$%,.0f"),
        'days_until_etd': st.column_config.NumberColumn('Days to ETD', width='small'),
        'days_since_order': st.column_config.NumberColumn('Days Open', width='small'),
        'pending_type': st.column_config.TextColumn('Status', width='small'),
        'split_rate_percent': st.column_config.NumberColumn('Split %', format="%.0f%%", width='small'),
    }
    
    st.dataframe(display_df, hide_index=True, column_config=column_config, use_container_width=True)
    if len(filtered_df) > 500:
        st.caption("⚠️ Showing first 500 rows. Export for complete data.")


# =============================================================================
# KPI CENTER RANKING FRAGMENT
# =============================================================================

@st.fragment
def kpi_center_ranking_fragment(ranking_df: pd.DataFrame, show_targets: bool = True):
    if ranking_df.empty:
        st.info("No ranking data available")
        return
    
    metric = st.radio("Rank by", ["Revenue", "Gross Profit", "GP1", "Customers"], horizontal=True, key="ranking_metric")
    metric_col_map = {"Revenue": "revenue", "Gross Profit": "gross_profit", "GP1": "gp1", "Customers": "customers"}
    sort_col = metric_col_map[metric]
    
    if sort_col not in ranking_df.columns:
        st.warning(f"Column {sort_col} not available")
        return
    
    sorted_df = ranking_df.sort_values(sort_col, ascending=False).copy()
    sorted_df.insert(0, 'rank', range(1, len(sorted_df) + 1))
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        try:
            chart = KPICenterCharts.build_kpi_center_ranking_chart(sorted_df, metric=sort_col, top_n=10)
            st.altair_chart(chart, use_container_width=True)
        except Exception as e:
            logger.warning(f"Could not render ranking chart: {e}")
    
    with col2:
        display_cols = ['rank', 'kpi_center', 'revenue', 'gross_profit', 'gp1', 'customers']
        if show_targets and 'revenue_achievement' in sorted_df.columns:
            display_cols.append('revenue_achievement')
        display_cols = [c for c in display_cols if c in sorted_df.columns]
        display_df = sorted_df[display_cols].head(15).copy()
        
        column_config = {
            'rank': st.column_config.NumberColumn('🏆', width='small'),
            'kpi_center': st.column_config.TextColumn('KPI Center'),
            'revenue': st.column_config.NumberColumn('Revenue', format="$%,.0f"),
            'gross_profit': st.column_config.NumberColumn('GP', format="$%,.0f"),
            'gp1': st.column_config.NumberColumn('GP1', format="$%,.0f"),
            'customers': st.column_config.NumberColumn('Customers'),
            'revenue_achievement': st.column_config.ProgressColumn('Achievement', min_value=0, max_value=150, format='%.0f%%'),
        }
        st.dataframe(display_df, hide_index=True, column_config=column_config, use_container_width=True)


# =============================================================================
# TOP PERFORMERS / PARETO ANALYSIS FRAGMENT - NEW v2.3.0
# =============================================================================

@st.fragment
def top_performers_fragment(
    sales_df: pd.DataFrame,
    filter_values: Dict,
    metrics_calculator = None
):
    """
    Top Performers / Pareto Analysis fragment.
    
    Shows:
    - Top Customers by Revenue/GP/GP1
    - Top Brands by Revenue/GP/GP1
    - Concentration analysis (80/20 rule)
    
    Args:
        sales_df: Sales data DataFrame
        filter_values: Current filter settings
        metrics_calculator: Optional KPICenterMetrics instance
    """
    if sales_df.empty:
        st.info("No sales data for analysis")
        return
    
    st.subheader("📊 Top Performers Analysis")
    
    # Controls
    col1, col2, col3 = st.columns(3)
    
    with col1:
        analysis_type = st.radio(
            "Analyze by",
            ["Customers", "Brands", "Products"],
            horizontal=True,
            key="pareto_analysis_type"
        )
    
    with col2:
        metric = st.selectbox(
            "Metric",
            ["Revenue", "Gross Profit", "GP1"],
            key="pareto_metric"
        )
    
    with col3:
        top_percent = st.slider(
            "Show top %",
            min_value=50,
            max_value=100,
            value=80,
            step=5,
            key="pareto_top_percent",
            help="Show items that make up this % of total"
        )
    
    # Map metric to column
    metric_col_map = {
        'Revenue': 'sales_by_kpi_center_usd',
        'Gross Profit': 'gross_profit_by_kpi_center_usd',
        'GP1': 'gp1_by_kpi_center_usd'
    }
    value_col = metric_col_map.get(metric, 'sales_by_kpi_center_usd')
    
    if value_col not in sales_df.columns:
        st.warning(f"Column {value_col} not available")
        return
    
    # Prepare data based on analysis type
    if analysis_type == "Customers":
        group_col = 'customer'
        id_col = 'customer_id'
        label = "Customer"
    elif analysis_type == "Brands":
        group_col = 'brand'
        id_col = 'brand'
        label = "Brand"
    else:  # Products
        group_col = 'product_pn'
        id_col = 'product_id' if 'product_id' in sales_df.columns else 'product_pn'
        label = "Product"
    
    if group_col not in sales_df.columns:
        st.warning(f"Column {group_col} not available")
        return
    
    # Aggregate data
    agg_data = sales_df.groupby(group_col).agg({
        'sales_by_kpi_center_usd': 'sum',
        'gross_profit_by_kpi_center_usd': 'sum',
        'gp1_by_kpi_center_usd': 'sum' if 'gp1_by_kpi_center_usd' in sales_df.columns else 'count',
        'inv_number': 'nunique' if 'inv_number' in sales_df.columns else 'count'
    }).reset_index()
    
    agg_data.columns = [group_col, 'revenue', 'gross_profit', 'gp1', 'orders']
    
    if 'gp1_by_kpi_center_usd' not in sales_df.columns:
        agg_data['gp1'] = 0
    
    # Sort and calculate cumulative
    metric_lower = metric.lower().replace(' ', '_')
    agg_data = agg_data.sort_values(metric_lower, ascending=False)
    
    total = agg_data[metric_lower].sum()
    if total == 0:
        st.warning("No data to analyze")
        return
    
    agg_data['cumulative'] = agg_data[metric_lower].cumsum()
    agg_data['cumulative_percent'] = (agg_data['cumulative'] / total * 100).round(1)
    agg_data['percent'] = (agg_data[metric_lower] / total * 100).round(1)
    agg_data['rank'] = range(1, len(agg_data) + 1)
    
    # Filter to top percent
    cutoff_mask = agg_data['cumulative_percent'] <= top_percent
    if not cutoff_mask.any():
        # Include at least the first row
        top_data = agg_data.head(1).copy()
    else:
        # Include the first item that exceeds the threshold
        first_exceed = (~cutoff_mask).idxmax() if (~cutoff_mask).any() else len(agg_data) - 1
        top_data = agg_data.loc[:first_exceed].copy()
    
    # Summary metrics
    st.markdown("---")
    
    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    
    top_count = len(top_data)
    total_count = len(agg_data)
    top_value = top_data[metric_lower].sum()
    concentration = (top_count / total_count * 100) if total_count > 0 else 0
    
    with col_s1:
        st.metric(
            f"Top {label}s",
            f"{top_count:,}",
            f"of {total_count:,} total",
            help=f"Number of {label.lower()}s making up {top_percent}% of {metric}"
        )
    
    with col_s2:
        st.metric(
            f"Top {top_percent}% {metric}",
            f"${top_value:,.0f}",
            f"{(top_value/total*100):.1f}% of total"
        )
    
    with col_s3:
        st.metric(
            "Concentration",
            f"{concentration:.1f}%",
            help=f"{concentration:.1f}% of {label.lower()}s generate {top_percent}% of {metric}"
        )
    
    with col_s4:
        avg_per_item = top_value / top_count if top_count > 0 else 0
        st.metric(
            f"Avg per {label}",
            f"${avg_per_item:,.0f}"
        )
    
    # Display charts and table
    chart_col, table_col = st.columns([1.2, 1])
    
    with chart_col:
        # Top performers chart
        try:
            chart = KPICenterCharts.build_top_performers_chart(
                data_df=top_data,
                value_col=metric_lower,
                label_col=group_col,
                top_n=min(15, len(top_data)),
                title=f"Top {label}s by {metric}",
                show_percent=True
            )
            st.altair_chart(chart, use_container_width=True)
        except Exception as e:
            logger.warning(f"Could not render chart: {e}")
            st.warning("Could not render chart")
    
    with table_col:
        # Display table
        display_df = top_data[[group_col, 'revenue', 'gross_profit', 'gp1', 'orders', 'percent', 'cumulative_percent']].copy()
        display_df.insert(0, 'Rank', range(1, len(display_df) + 1))
        
        st.dataframe(
            display_df.head(20),
            hide_index=True,
            column_config={
                'Rank': st.column_config.NumberColumn('🏆', width='small'),
                group_col: st.column_config.TextColumn(label),
                'revenue': st.column_config.NumberColumn('Revenue', format='$%,.0f'),
                'gross_profit': st.column_config.NumberColumn('GP', format='$%,.0f'),
                'gp1': st.column_config.NumberColumn('GP1', format='$%,.0f'),
                'orders': st.column_config.NumberColumn('Orders'),
                'percent': st.column_config.NumberColumn('% Share', format='%.1f%%'),
                'cumulative_percent': st.column_config.NumberColumn('Cum %', format='%.1f%%'),
            },
            use_container_width=True
        )
        
        if len(top_data) > 20:
            st.caption(f"Showing top 20 of {len(top_data)} {label.lower()}s")
    
    # 80/20 Analysis insight
    st.markdown("---")
    
    # Find how many items make up 80%
    mask_80 = agg_data['cumulative_percent'] <= 80
    if mask_80.any():
        first_exceed_80 = (~mask_80).idxmax() if (~mask_80).any() else len(agg_data) - 1
        count_80 = len(agg_data.loc[:first_exceed_80])
        percent_of_total = (count_80 / total_count * 100) if total_count > 0 else 0
        
        with st.expander("💡 80/20 Analysis Insight", expanded=True):
            st.markdown(f"""
**Pareto Principle Analysis:**

- **{count_80:,} {label.lower()}s** ({percent_of_total:.1f}% of total) generate **80%** of {metric}
- This indicates {'high' if percent_of_total < 30 else 'moderate' if percent_of_total < 50 else 'distributed'} revenue concentration

**Recommendations:**
{_get_concentration_recommendations(percent_of_total, label)}
            """)


def _get_concentration_recommendations(concentration_percent: float, entity: str) -> str:
    """Generate recommendations based on concentration level."""
    if concentration_percent < 20:
        return f"""
- ⚠️ Very high concentration risk - top {entity.lower()}s are critical
- Focus on relationship management for key accounts
- Develop contingency plans for top {entity.lower()} churn
- Consider diversification strategies
"""
    elif concentration_percent < 35:
        return f"""
- 📊 Healthy concentration with some key accounts
- Continue nurturing top {entity.lower()} relationships
- Identify growth potential in mid-tier {entity.lower()}s
- Monitor dependency on largest {entity.lower()}s
"""
    else:
        return f"""
- ✅ Well-distributed across {entity.lower()}s
- Good diversification reduces single-point-of-failure risk
- Focus on improving average order value
- Identify opportunities to consolidate wallet share
"""


# =============================================================================
# EXPORT REPORT FRAGMENT
# =============================================================================

@st.fragment
def export_report_fragment(metrics: Dict, complex_kpis: Dict, pipeline_metrics: Dict, filter_values: Dict,
                           yoy_metrics: Dict = None, kpi_center_summary_df: pd.DataFrame = None,
                           monthly_df: pd.DataFrame = None, sales_detail_df: pd.DataFrame = None,
                           backlog_summary_df: pd.DataFrame = None, backlog_detail_df: pd.DataFrame = None,
                           backlog_by_month_df: pd.DataFrame = None):
    from .export import KPICenterExport
    
    st.subheader("📥 Export Report")
    
    with st.expander("ℹ️ Export Options"):
        st.markdown("""
**Excel Report includes:**
- Summary sheet with all KPI metrics
- KPI Center breakdown
- Monthly trend data
- Sales transaction details (up to 10,000 rows)
- Backlog summary and details
        """)
    
    if st.button("🔄 Generate Excel Report", key="generate_report_btn", type="primary"):
        with st.spinner("Generating report..."):
            try:
                exporter = KPICenterExport()
                excel_bytes = exporter.create_comprehensive_report(
                    metrics=metrics, complex_kpis=complex_kpis, pipeline_metrics=pipeline_metrics,
                    filters=filter_values, yoy_metrics=yoy_metrics, kpi_center_summary_df=kpi_center_summary_df,
                    monthly_df=monthly_df, sales_detail_df=sales_detail_df, backlog_summary_df=backlog_summary_df,
                    backlog_detail_df=backlog_detail_df, backlog_by_month_df=backlog_by_month_df,
                )
                st.session_state['kpi_center_export_data'] = excel_bytes
                st.success("✅ Report generated! Click download below.")
            except Exception as e:
                logger.error(f"Export error: {e}")
                st.error(f"Failed to generate report: {e}")
    
    if 'kpi_center_export_data' in st.session_state:
        year = filter_values.get('year', 2025)
        period = filter_values.get('period_type', 'YTD')
        filename = f"kpi_center_performance_{year}_{period}.xlsx"
        st.download_button(label="⬇️ Download Excel Report", data=st.session_state['kpi_center_export_data'],
                          file_name=filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                          key="download_report_btn")