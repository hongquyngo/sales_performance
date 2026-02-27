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
from datetime import date
import pandas as pd
import streamlit as st

from .charts import (
    render_kpi_cards,
    render_new_business_cards,
    build_forecast_waterfall_chart,
    build_gap_analysis_chart,
    convert_pipeline_to_backlog_metrics,
    _render_backlog_forecast_section,
    build_monthly_trend_dual_chart,
    build_cumulative_dual_chart,
    build_yoy_comparison_chart,
    build_yoy_cumulative_chart,
    build_multi_year_monthly_chart,
    build_multi_year_cumulative_chart,
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
    Year-over-Year / Multi-Year comparison with tabs and filters.
    Synced with KPI Center yoy_comparison_fragment v2.5.0.
    
    - Detects actual years in data
    - If >= 2 years → Multi-Year Comparison (grouped bars, cumulative lines)  
    - If 0-1 years → YoY Comparison (current vs previous year)
    """
    col_header, col_help = st.columns([6, 1])
    with col_header:
        st.subheader("📊 Year-over-Year Comparison")
    with col_help:
        with st.popover("ℹ️ Help"):
            st.markdown("""
**📊 Year-over-Year Comparison**

This section shows **full year** trends for context:
- **Current Year**: YTD performance (selected period)
- **Previous Years**: Full 12-month performance

**Filters:**
- **Customer/Brand/Product**: Filter by specific selections
- **Excl**: Exclude selected items instead of including them
            """)
    
    current_year = filter_values.get('year', date.today().year)
    
    # =========================================================================
    # FILTERS ROW - Customer/Brand/Product with Excl
    # =========================================================================
    col_cust, col_brand, col_prod = st.columns(3)
    
    with col_cust:
        subcol1, subcol2 = st.columns([4, 1])
        with subcol1:
            st.markdown("**Customer**")
        with subcol2:
            excl_customer = st.checkbox("Excl", key=f"{fragment_key}_excl_customer")
        customers = ['All customers...'] + (sorted(sales_df['customer'].dropna().unique().tolist()) if not sales_df.empty else [])
        selected_customer = st.selectbox("Customer", customers, key=f"{fragment_key}_customer", label_visibility="collapsed")
    
    with col_brand:
        subcol1, subcol2 = st.columns([4, 1])
        with subcol1:
            st.markdown("**Brand**")
        with subcol2:
            excl_brand = st.checkbox("Excl", key=f"{fragment_key}_excl_brand")
        brands = ['All brands...'] + (sorted(sales_df['brand'].dropna().unique().tolist()) if not sales_df.empty else [])
        selected_brand = st.selectbox("Brand", brands, key=f"{fragment_key}_brand", label_visibility="collapsed")
    
    with col_prod:
        subcol1, subcol2 = st.columns([4, 1])
        with subcol1:
            st.markdown("**Product**")
        with subcol2:
            excl_product = st.checkbox("Excl", key=f"{fragment_key}_excl_product")
        products = ['All products...'] + (sorted(sales_df['product_pn'].dropna().unique().tolist()[:100]) if not sales_df.empty else [])
        selected_product = st.selectbox("Product", products, key=f"{fragment_key}_product", label_visibility="collapsed")
    
    # =========================================================================
    # LOCAL FILTER FUNCTION
    # =========================================================================
    def apply_local_filters(df):
        if df is None or df.empty:
            return df if df is not None else pd.DataFrame()
        filtered = df.copy()
        if selected_customer != 'All customers...' and 'customer' in filtered.columns:
            if excl_customer:
                filtered = filtered[filtered['customer'] != selected_customer]
            else:
                filtered = filtered[filtered['customer'] == selected_customer]
        if selected_brand != 'All brands...' and 'brand' in filtered.columns:
            if excl_brand:
                filtered = filtered[filtered['brand'] != selected_brand]
            else:
                filtered = filtered[filtered['brand'] == selected_brand]
        if selected_product != 'All products...' and 'product_pn' in filtered.columns:
            if excl_product:
                filtered = filtered[filtered['product_pn'] != selected_product]
            else:
                filtered = filtered[filtered['product_pn'] == selected_product]
        return filtered
    
    if sales_df is None or sales_df.empty:
        st.info("No sales data available for comparison")
        return
    
    # =========================================================================
    # DETECT MULTI-YEAR DATA
    # =========================================================================
    df_check = sales_df.copy()
    if 'inv_date' in df_check.columns:
        df_check['inv_date'] = pd.to_datetime(df_check['inv_date'], errors='coerce')
        df_check['inv_year'] = df_check['inv_date'].dt.year
        unique_years = sorted([int(y) for y in df_check['inv_year'].dropna().unique() if y > 2000])
    else:
        unique_years = [current_year]
    
    # =========================================================================
    # MULTI-YEAR vs YOY
    # =========================================================================
    if len(unique_years) >= 2:
        # =================================================================
        # MULTI-YEAR COMPARISON
        # =================================================================
        st.info(f"📆 Data spans {len(unique_years)} years: {', '.join(map(str, unique_years))}")
        
        multi_year_df = apply_local_filters(sales_df)
        if multi_year_df.empty:
            st.warning("No data matches the selected filters")
            return
        
        multi_year_df['inv_date'] = pd.to_datetime(multi_year_df['inv_date'], errors='coerce')
        multi_year_df['inv_year'] = multi_year_df['inv_date'].dt.year
        multi_year_df['invoice_month'] = multi_year_df['inv_date'].dt.strftime('%b')
        
        # Aggregate by year + month
        agg_dict = {
            'calculated_invoiced_amount_usd': 'sum',
            'invoiced_gross_profit_usd': 'sum',
        }
        if 'invoiced_gp1_usd' in multi_year_df.columns:
            agg_dict['invoiced_gp1_usd'] = 'sum'
        agg_dict['inv_number'] = pd.Series.nunique
        
        monthly_by_year = multi_year_df.groupby(['inv_year', 'invoice_month']).agg(agg_dict).reset_index()
        monthly_by_year.columns = ['year', 'month', 'revenue', 'gross_profit'] + \
            (['gp1'] if 'invoiced_gp1_usd' in multi_year_df.columns else []) + ['orders']
        
        if 'gp1' not in monthly_by_year.columns:
            monthly_by_year['gp1'] = 0
        
        monthly_by_year['month_order'] = monthly_by_year['month'].map({m: i for i, m in enumerate(MONTH_ORDER)})
        monthly_by_year = monthly_by_year.sort_values(['year', 'month_order'])
        
        # Tabs: Revenue / Gross Profit / GP1
        tab_rev, tab_gp, tab_gp1 = st.tabs(["💰 Revenue", "📈 Gross Profit", "📊 GP1"])
        
        for tab, metric_name, metric_col in [
            (tab_rev, "Revenue", "revenue"),
            (tab_gp, "Gross Profit", "gross_profit"),
            (tab_gp1, "GP1", "gp1")
        ]:
            with tab:
                # Year-by-year summary cards with YoY %
                yearly_totals = monthly_by_year.groupby('year')[metric_col].sum().sort_index()
                
                cols = st.columns(min(len(yearly_totals), 8))
                prev_value = None
                for i, (year, value) in enumerate(yearly_totals.items()):
                    with cols[i % len(cols)]:
                        st.markdown(f"**{int(year)} {metric_name}**")
                        st.markdown(f"### ${value:,.0f}")
                        if prev_value is not None and prev_value > 0:
                            yoy_change = (value - prev_value) / prev_value * 100
                            color = "green" if yoy_change > 0 else "red"
                            arrow = "↑" if yoy_change > 0 else "↓"
                            st.markdown(f":{color}[{arrow} {yoy_change:+.1f}% YoY]")
                    prev_value = value
                
                st.markdown("")
                
                # Charts
                chart_col1, chart_col2 = st.columns(2)
                with chart_col1:
                    st.markdown(f"**📊 Monthly {metric_name} by Year**")
                    chart = build_multi_year_monthly_chart(
                        monthly_df=monthly_by_year, metric_col=metric_col, years=unique_years
                    )
                    st.altair_chart(chart, use_container_width=True)
                
                with chart_col2:
                    st.markdown(f"**📈 Cumulative {metric_name}**")
                    chart = build_multi_year_cumulative_chart(
                        monthly_df=monthly_by_year, metric_col=metric_col, years=unique_years
                    )
                    st.altair_chart(chart, use_container_width=True)
    
    else:
        # =================================================================
        # TRADITIONAL YOY (current vs previous year)
        # =================================================================
        prev_year = current_year - 1
        
        yoy_sales_df = apply_local_filters(sales_df)
        if yoy_sales_df.empty:
            st.warning("No data matches the selected filters")
            return
        
        # Get previous year data from cache or passed param
        if prev_sales_df is None or prev_sales_df.empty:
            if unified_cache:
                all_sales = unified_cache.get('sales_raw_df', pd.DataFrame())
                if not all_sales.empty and 'invoice_year' in all_sales.columns:
                    prev_sales_df = all_sales[all_sales['invoice_year'] == prev_year]
        
        previous_filtered = apply_local_filters(prev_sales_df)
        
        current_monthly = _prepare_monthly_summary(yoy_sales_df)
        prev_monthly = _prepare_monthly_summary(previous_filtered) if previous_filtered is not None and not previous_filtered.empty else pd.DataFrame()
        
        if prev_monthly.empty:
            st.info(f"No data available for {prev_year} comparison")
            return
        
        # Tabs
        tab_rev, tab_gp, tab_gp1 = st.tabs(["💰 Revenue", "📈 Gross Profit", "📊 GP1"])
        
        for tab, metric_name, metric_col in [
            (tab_rev, "Revenue", "revenue"),
            (tab_gp, "Gross Profit", "gross_profit"),
            (tab_gp1, "GP1", "gp1")
        ]:
            with tab:
                curr_total = current_monthly[metric_col].sum() if not current_monthly.empty and metric_col in current_monthly.columns else 0
                prev_total = prev_monthly[metric_col].sum() if not prev_monthly.empty and metric_col in prev_monthly.columns else 0
                yoy_pct = ((curr_total - prev_total) / abs(prev_total) * 100) if prev_total != 0 else 0
                
                col_curr, col_prev = st.columns(2)
                with col_curr:
                    st.markdown(f"**{current_year} {metric_name} (YTD)**")
                    st.markdown(f"### ${curr_total:,.0f}")
                    if yoy_pct != 0:
                        color = "green" if yoy_pct > 0 else "red"
                        arrow = "↑" if yoy_pct > 0 else "↓"
                        st.markdown(f":{color}[{arrow} {yoy_pct:+.1f}% vs Full Year]")
                with col_prev:
                    st.markdown(f"**{prev_year} {metric_name} (Full Year)**")
                    st.markdown(f"### ${prev_total:,.0f}")
                    diff = curr_total - prev_total
                    if diff != 0:
                        st.caption(f"Difference: ${diff:+,.0f}")
                
                st.markdown("")
                chart_col1, chart_col2 = st.columns(2)
                
                with chart_col1:
                    st.markdown(f"**📊 Monthly {metric_name} Comparison**")
                    st.altair_chart(build_yoy_comparison_chart(
                        current_monthly, prev_monthly, metric_name, current_year, prev_year
                    ), use_container_width=True)
                
                with chart_col2:
                    st.markdown(f"**📈 Cumulative {metric_name}**")
                    st.altair_chart(build_yoy_cumulative_chart(
                        current_monthly, prev_monthly, metric_name, current_year, prev_year
                    ), use_container_width=True)


# =============================================================================
# OVERVIEW TAB FRAGMENT - Main entry point
# =============================================================================

def overview_tab_fragment(
    sales_df: pd.DataFrame,
    overview_metrics: Dict,
    yoy_metrics: Optional[Dict],
    monthly_df: pd.DataFrame,
    entity_summary_df: pd.DataFrame,
    active_filters: Dict,
    prev_sales_df: pd.DataFrame = None,
    unified_cache: Dict = None,
    # NEW v2.2.0: Complex KPIs
    complex_kpis: Dict = None,
    new_customers_df: pd.DataFrame = None,
    new_products_df: pd.DataFrame = None,
    new_combos_detail_df: pd.DataFrame = None,
    new_business_detail_df: pd.DataFrame = None,
    # NEW v2.2.0: Pipeline metrics (replaces backlog_metrics + in_period_analysis)
    pipeline_metrics: Dict = None,
):
    """
    Render the complete Overview tab.
    
    VERSION: 2.2.0
    - Removed backlog from KPI cards (avoid duplication)
    - Added KPC-style Backlog & Forecast section (5 metrics + waterfall + bullet, 3 tabs)
    - New Business section with detail popovers
    """
    # =========================================================================
    # SECTION 1: KPI CARDS (Performance only, no backlog)
    # =========================================================================
    render_kpi_cards(
        metrics=overview_metrics,
        yoy_metrics=yoy_metrics,
    )
    
    st.divider()
    
    # =========================================================================
    # SECTION 2: NEW BUSINESS
    # =========================================================================
    if complex_kpis:
        render_new_business_cards(
            complex_kpis=complex_kpis,
            new_customers_df=new_customers_df,
            new_products_df=new_products_df,
            new_combos_detail_df=new_combos_detail_df,
            new_business_detail_df=new_business_detail_df,
        )
        st.divider()
    
    # =========================================================================
    # SECTION 3: BACKLOG & FORECAST (Synced with KPC)
    # =========================================================================
    if pipeline_metrics and pipeline_metrics.get('summary', {}).get('backlog_orders', 0) > 0:
        col_bf_header, col_bf_help = st.columns([6, 1])
        with col_bf_header:
            st.subheader("📦 Backlog & Forecast")
        with col_bf_help:
            with st.popover("ℹ️ Help"):
                st.markdown("""
**📦 Backlog & Forecast**

| Metric | Formula | Description |
|--------|---------|-------------|
| **Total Backlog** | `Σ outstanding_amount_usd` | All outstanding orders |
| **In-Period** | `Σ backlog WHERE ETD in period` | Backlog expected to ship in period |
| **Target** | N/A | Legal Entity has no target system |
| **Forecast** | `Invoiced + In-Period` | Projected total |
| **GAP/Surplus** | `Forecast - Target` | Requires target assignment |
                """)
        
        # Overdue warning
        summary = pipeline_metrics.get('summary', {})
        overdue_orders = summary.get('overdue_orders', 0)
        overdue_revenue = summary.get('overdue_revenue', 0)
        if overdue_orders > 0:
            st.warning(f"⚠️ {overdue_orders} orders are past ETD. Value: ${overdue_revenue:,.0f}")
        
        # GP1/GP ratio info
        gp1_gp_ratio = summary.get('gp1_gp_ratio', 1.0)
        if gp1_gp_ratio != 1.0:
            st.caption(f"📊 GP1 backlog estimated using GP1/GP ratio: {gp1_gp_ratio:.2%}")
        
        # Convert to flat format for charts
        chart_backlog_metrics = convert_pipeline_to_backlog_metrics(pipeline_metrics)
        
        revenue_metrics = pipeline_metrics.get('revenue', {})
        gp_metrics = pipeline_metrics.get('gross_profit', {})
        gp1_metrics = pipeline_metrics.get('gp1', {})
        
        bf_tab1, bf_tab2, bf_tab3 = st.tabs(["💰 Revenue", "📈 Gross Profit", "📊 GP1"])
        
        with bf_tab1:
            _render_backlog_forecast_section(
                summary, revenue_metrics, 'revenue',
                chart_backlog_metrics=chart_backlog_metrics
            )
        
        with bf_tab2:
            _render_backlog_forecast_section(
                summary, gp_metrics, 'gp',
                chart_backlog_metrics=chart_backlog_metrics
            )
        
        with bf_tab3:
            _render_backlog_forecast_section(
                summary, gp1_metrics, 'gp1',
                chart_backlog_metrics=chart_backlog_metrics,
                gp1_gp_ratio=gp1_gp_ratio
            )
        
        st.divider()
    
    # =========================================================================
    # SECTION 4: MONTHLY TREND (with fragment filters)
    # =========================================================================
    monthly_trend_fragment(
        sales_df=sales_df,
        filter_values=active_filters,
        fragment_key="le_trend"
    )
    
    st.divider()
    
    # =========================================================================
    # SECTION 5: YOY COMPARISON
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
    # SECTION 6: ENTITY BREAKDOWN TABLE
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
    # SECTION 7: EXPORT
    # =========================================================================
    with st.expander("📥 Export Report"):
        LegalEntityExport.render_download_button(
            df=entity_summary_df if not entity_summary_df.empty else sales_df,
            filename=f"legal_entity_performance_{active_filters.get('year', '')}",
            label="📥 Download",
            key="le_overview_export"
        )