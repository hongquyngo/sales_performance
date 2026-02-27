# utils/legal_entity_performance/overview/fragments.py
"""
Streamlit Fragments for Legal Entity Performance - Overview Tab.
Adapted from kpi_center_performance/overview/fragments.py

VERSION: 2.0.0
- monthly_trend_fragment with Customer/Brand/Product Excl filters
- yoy_comparison_fragment with Revenue/GP/GP1 tabs
- overview_tab_fragment as main entry point
"""

import logging
from typing import Dict, Optional
import pandas as pd
import streamlit as st

from .charts import (
    render_kpi_cards,
    build_monthly_trend_dual_chart,
    build_cumulative_dual_chart,
    build_yoy_comparison_chart,
    build_yoy_cumulative_chart,
)
from ..constants import MONTH_ORDER
from ..export_utils import LegalEntityExport

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER: prepare_monthly_summary from processor
# =============================================================================

def _prepare_monthly_summary(
    sales_df: pd.DataFrame,
    revenue_col: str = 'calculated_invoiced_amount_usd',
    gp_col: str = 'invoiced_gross_profit_usd',
    gp1_col: str = 'invoiced_gp1_usd'
) -> pd.DataFrame:
    """Prepare monthly summary from raw sales data (for fragment use)."""
    if sales_df.empty:
        return pd.DataFrame()
    
    df = sales_df.copy()
    if 'invoice_month' not in df.columns:
        if 'inv_date' not in df.columns:
            return pd.DataFrame()
        df['inv_date'] = pd.to_datetime(df['inv_date'], errors='coerce')
        df['invoice_month'] = df['inv_date'].dt.strftime('%b')
    
    agg_dict = {}
    if revenue_col in df.columns:
        agg_dict['revenue'] = (revenue_col, 'sum')
    if gp_col in df.columns:
        agg_dict['gross_profit'] = (gp_col, 'sum')
    if gp1_col in df.columns:
        agg_dict['gp1'] = (gp1_col, 'sum')
    
    if not agg_dict:
        return pd.DataFrame()
    
    monthly = df.groupby('invoice_month').agg(**agg_dict).reset_index()
    monthly.rename(columns={'invoice_month': 'month'}, inplace=True)
    
    if 'revenue' in monthly.columns and 'gross_profit' in monthly.columns:
        monthly['gp_percent'] = (monthly['gross_profit'] / monthly['revenue'] * 100).fillna(0).round(1)
    
    # Sort by month order
    monthly['month_order'] = monthly['month'].map({m: i for i, m in enumerate(MONTH_ORDER)})
    monthly = monthly.sort_values('month_order').drop(columns=['month_order'])
    
    return monthly.reset_index(drop=True)


# =============================================================================
# MONTHLY TREND FRAGMENT - Synced with KPI center
# =============================================================================

@st.fragment
def monthly_trend_fragment(
    sales_df: pd.DataFrame,
    filter_values: Dict = None,
    fragment_key: str = "le_trend"
):
    """
    Monthly trend chart with Customer/Brand/Product Excl filters.
    Synced with KPI center monthly_trend_fragment.
    """
    if sales_df.empty:
        st.info("No sales data for trend analysis")
        return
    
    # Header
    col_header, col_help = st.columns([6, 1])
    with col_header:
        st.subheader("📊 Monthly Trend & Cumulative")
    with col_help:
        with st.popover("ℹ️"):
            st.markdown("""
**📊 Monthly Trend & Cumulative**

**Charts:**
- **Monthly Trend**: Revenue (orange) and Gross Profit (blue) bars with GP% line overlay
- **Cumulative Performance**: Running total of Revenue and GP over the year

**Filters:**
- **Customer/Brand/Product**: Filter data by specific selections
- **Excl**: Exclude selected items instead of including them
            """)
    
    # Filters row
    col_cust, col_brand, col_prod = st.columns(3)
    
    with col_cust:
        subcol1, subcol2 = st.columns([4, 1])
        with subcol1:
            st.markdown("**Customer**")
        with subcol2:
            excl_customer = st.checkbox("Excl", key=f"{fragment_key}_excl_customer")
        customers = ['All customers...'] + sorted(sales_df['customer'].dropna().unique().tolist())
        selected_customer = st.selectbox(
            "Customer", customers, key=f"{fragment_key}_customer",
            label_visibility="collapsed"
        )
    
    with col_brand:
        subcol1, subcol2 = st.columns([4, 1])
        with subcol1:
            st.markdown("**Brand**")
        with subcol2:
            excl_brand = st.checkbox("Excl", key=f"{fragment_key}_excl_brand")
        brands = ['All brands...'] + sorted(sales_df['brand'].dropna().unique().tolist())
        selected_brand = st.selectbox(
            "Brand", brands, key=f"{fragment_key}_brand",
            label_visibility="collapsed"
        )
    
    with col_prod:
        subcol1, subcol2 = st.columns([4, 1])
        with subcol1:
            st.markdown("**Product**")
        with subcol2:
            excl_product = st.checkbox("Excl", key=f"{fragment_key}_excl_product")
        products = ['All products...'] + sorted(sales_df['product_pn'].dropna().unique().tolist()[:100])
        selected_product = st.selectbox(
            "Product", products, key=f"{fragment_key}_product",
            label_visibility="collapsed"
        )
    
    # Apply filters
    filtered_df = sales_df.copy()
    
    if selected_customer != 'All customers...':
        if excl_customer:
            filtered_df = filtered_df[filtered_df['customer'] != selected_customer]
        else:
            filtered_df = filtered_df[filtered_df['customer'] == selected_customer]
    
    if selected_brand != 'All brands...':
        if excl_brand:
            filtered_df = filtered_df[filtered_df['brand'] != selected_brand]
        else:
            filtered_df = filtered_df[filtered_df['brand'] == selected_brand]
    
    if selected_product != 'All products...':
        if excl_product:
            filtered_df = filtered_df[filtered_df['product_pn'] != selected_product]
        else:
            filtered_df = filtered_df[filtered_df['product_pn'] == selected_product]
    
    if filtered_df.empty:
        st.warning("No data matches the selected filters")
        return
    
    monthly_df = _prepare_monthly_summary(filtered_df)
    
    if monthly_df.empty:
        st.warning("Could not prepare monthly summary")
        return
    
    # Charts - 2 columns like KPI center
    chart_col1, chart_col2 = st.columns(2)
    
    with chart_col1:
        st.markdown("**📊 Monthly Trend**")
        trend_chart = build_monthly_trend_dual_chart(
            monthly_df=monthly_df,
            show_gp_percent_line=True
        )
        st.altair_chart(trend_chart, use_container_width=True)
    
    with chart_col2:
        st.markdown("**📈 Cumulative Performance**")
        cumulative_chart = build_cumulative_dual_chart(monthly_df=monthly_df)
        st.altair_chart(cumulative_chart, use_container_width=True)


# =============================================================================
# YOY COMPARISON FRAGMENT - Synced with KPI center
# =============================================================================

@st.fragment
def yoy_comparison_fragment(
    sales_df: pd.DataFrame,
    filter_values: Dict,
    prev_sales_df: pd.DataFrame = None,
    unified_cache: dict = None,
    fragment_key: str = "le_yoy"
):
    """
    Year-over-Year comparison with tabs for Revenue/GP/GP1.
    Synced with KPI center yoy_comparison_fragment.
    """
    col_header, col_help = st.columns([6, 1])
    with col_header:
        st.subheader("📊 Year-over-Year Comparison")
    with col_help:
        with st.popover("ℹ️"):
            st.markdown("""
**📊 Year-over-Year Comparison**

Compares current period with same period in previous year.

- **Monthly Bars**: Grouped bars comparing each month
- **Cumulative Lines**: Running total comparison
- **Tabs**: Switch between Revenue, Gross Profit, and GP1
            """)
    
    year = filter_values.get('year', 2025)
    prev_year = year - 1
    
    # Prepare monthly summaries
    current_monthly = _prepare_monthly_summary(sales_df)
    
    # Get prev year data from passed param or from cache
    if prev_sales_df is None or prev_sales_df.empty:
        if unified_cache:
            all_sales = unified_cache.get('sales_raw_df', pd.DataFrame())
            if not all_sales.empty and 'invoice_year' in all_sales.columns:
                prev_sales_df = all_sales[all_sales['invoice_year'] == prev_year]
    
    prev_monthly = _prepare_monthly_summary(prev_sales_df) if prev_sales_df is not None else pd.DataFrame()
    
    if current_monthly.empty and prev_monthly.empty:
        st.info("No data available for comparison")
        return
    
    # Tabs: Revenue / GP / GP1
    tab_rev, tab_gp, tab_gp1 = st.tabs(["💰 Revenue", "📈 Gross Profit", "📊 GP1"])
    
    for tab, metric_name, metric_display in [
        (tab_rev, 'Revenue', '💰 Revenue'),
        (tab_gp, 'Gross Profit', '📈 Gross Profit'),
        (tab_gp1, 'GP1', '📊 GP1'),
    ]:
        with tab:
            # Summary metrics
            metric_col_map = {'Revenue': 'revenue', 'Gross Profit': 'gross_profit', 'GP1': 'gp1'}
            col = metric_col_map.get(metric_name, 'revenue')
            
            curr_total = current_monthly[col].sum() if not current_monthly.empty and col in current_monthly.columns else 0
            prev_total = prev_monthly[col].sum() if not prev_monthly.empty and col in prev_monthly.columns else 0
            yoy_pct = ((curr_total - prev_total) / abs(prev_total) * 100) if prev_total != 0 else None
            
            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric(f"{year} {metric_name}", f"${curr_total:,.0f}")
            with m2:
                st.metric(f"{prev_year} {metric_name}", f"${prev_total:,.0f}")
            with m3:
                st.metric("YoY Change", f"{yoy_pct:+.1f}%" if yoy_pct is not None else "N/A")
            
            # Charts
            chart_col1, chart_col2 = st.columns(2)
            
            with chart_col1:
                st.markdown(f"**Monthly {metric_name}**")
                yoy_chart = build_yoy_comparison_chart(
                    current_df=current_monthly, previous_df=prev_monthly,
                    metric=metric_name, current_year=year, previous_year=prev_year
                )
                st.altair_chart(yoy_chart, use_container_width=True)
            
            with chart_col2:
                st.markdown(f"**Cumulative {metric_name}**")
                cum_chart = build_yoy_cumulative_chart(
                    current_df=current_monthly, previous_df=prev_monthly,
                    metric=metric_name, current_year=year, previous_year=prev_year
                )
                st.altair_chart(cum_chart, use_container_width=True)


# =============================================================================
# OVERVIEW TAB FRAGMENT - Main entry point
# =============================================================================

def overview_tab_fragment(
    sales_df: pd.DataFrame,
    overview_metrics: Dict,
    yoy_metrics: Optional[Dict],
    monthly_df: pd.DataFrame,
    entity_summary_df: pd.DataFrame,
    backlog_metrics: Dict,
    active_filters: Dict,
    prev_sales_df: pd.DataFrame = None,
    unified_cache: Dict = None,
):
    """
    Render the complete Overview tab.
    Adapted from kpi_center_performance/overview/fragments.py overview_tab_fragment.
    """
    # =========================================================================
    # SECTION 1: KPI CARDS
    # =========================================================================
    render_kpi_cards(
        metrics=overview_metrics,
        yoy_metrics=yoy_metrics,
        backlog_metrics=backlog_metrics,
    )
    
    st.divider()
    
    # =========================================================================
    # SECTION 2: MONTHLY TREND (with fragment filters)
    # =========================================================================
    monthly_trend_fragment(
        sales_df=sales_df,
        filter_values=active_filters,
        fragment_key="le_trend"
    )
    
    st.divider()
    
    # =========================================================================
    # SECTION 3: YOY COMPARISON
    # =========================================================================
    if active_filters.get('show_yoy', True):
        yoy_comparison_fragment(
            sales_df=sales_df,
            filter_values=active_filters,
            prev_sales_df=prev_sales_df,
            unified_cache=unified_cache,
            fragment_key="le_yoy"
        )
        st.divider()
    
    # =========================================================================
    # SECTION 4: ENTITY BREAKDOWN TABLE
    # =========================================================================
    if not entity_summary_df.empty:
        st.subheader("🏢 Entity Performance")
        st.dataframe(
            entity_summary_df,
            column_config={
                'legal_entity': 'Legal Entity',
                'revenue': st.column_config.NumberColumn('Revenue (USD)', format="$%,.0f"),
                'gross_profit': st.column_config.NumberColumn('GP (USD)', format="$%,.0f"),
                'gp1': st.column_config.NumberColumn('GP1 (USD)', format="$%,.0f"),
                'commission': st.column_config.NumberColumn('Commission', format="$%,.0f"),
                'gp_percent': st.column_config.NumberColumn('GP%', format="%.1f%%"),
                'orders': 'Invoices', 'customers': 'Customers',
                'legal_entity_id': None,
            },
            use_container_width=True, hide_index=True,
        )
    
    # =========================================================================
    # SECTION 5: EXPORT
    # =========================================================================
    with st.expander("📥 Export Report"):
        LegalEntityExport.render_download_button(
            df=entity_summary_df if not entity_summary_df.empty else sales_df,
            filename=f"legal_entity_performance_{active_filters.get('year', '')}",
            label="📥 Download",
            key="le_overview_export"
        )
