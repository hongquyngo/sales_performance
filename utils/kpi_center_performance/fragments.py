# utils/kpi_center_performance/fragments.py
"""
Streamlit Fragments for KPI Center Performance

VERSION: 3.0.2
CHANGELOG:
- v3.0.2: BUGFIX render_multiselect_filter doesn't have placeholder parameter
- v3.0.1: BUGFIX backlog_by_etd_fragment filter not working:
          - Problem: backlog_by_month_df was pre-aggregated without kpi_center_id,
            so client-side filter didn't work
          - Solution: Changed to receive backlog_detail_df (already filtered)
            and aggregate within fragment
          - Now correctly shows only selected KPI Centers' backlog
- v3.0.0: SYNCED Backlog tab with Salesperson module:
          - backlog_list_fragment(): 7 summary cards, 5 filters with Excl option
          - NEW backlog_by_etd_fragment(): 3 view modes (Timeline/Stacked/Single Year)
          - NEW backlog_risk_analysis_fragment(): Risk categorization + Overdue table
          - Full parity with Salesperson Backlog Analysis tab
- v2.6.0: REFACTORED sales_detail_fragment (SYNCED with Salesperson page):
          - 7 summary metrics cards (Revenue, GP, GP1, Orders, Customers, Avg Order, Avg GP/Cust)
          - 5 filter columns: Customer, Brand, Product (multiselect), OC#/Customer PO (text), Min Amount (number)
          - All filters have Excl checkbox for exclude mode
          - Calculate original values (pre-split): Total Revenue, Total GP
          - Format Product display: "PT Code | Name | Package Size"
          - Format OC/PO display: "OC#\\n(PO: xxx)"
          - Detailed column config with comprehensive tooltips
          - Column Legend expander with formula explanations
          - Export Filtered View button
          - UPDATED pivot_analysis_fragment: default to Gross Profit like SP
- v2.5.0: ADDED Multi-Year Comparison (synced with Salesperson page):
          - yoy_comparison_fragment: Now detects actual years in data
          - >= 2 years → Multi-Year Comparison with grouped bars & cumulative lines
          - 0-1 years → Traditional YoY Comparison (current vs previous)
          - Removed debug print statements
- v2.4.0: SYNCED UI with Salesperson Performance page:
          - monthly_trend_fragment: 2 charts side-by-side (Monthly Trend + Cumulative)
            with Customer/Brand/Product Excl filters
          - yoy_comparison_fragment: Tabs (Revenue/GP/GP1), summary metrics,
            2 charts (Monthly Comparison + Cumulative)
          - All filters now have Excl checkbox like SP page
- v2.3.0: Phase 3 - Pareto Analysis
- v2.2.0: Phase 2 enhancements
"""

import logging
from typing import Dict, Optional, List
from datetime import datetime
import pandas as pd
import streamlit as st

from .charts import KPICenterCharts
from .constants import MONTH_ORDER

from .filters import (
    FilterResult,
    TextSearchResult,
    NumberRangeResult,
    render_multiselect_filter,
    apply_multiselect_filter,
    render_text_search_filter,
    apply_text_search_filter,
    render_number_filter,
    apply_number_filter,
)

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _clean_dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Clean dataframe for display."""
    if df.empty:
        return df
    
    df = df.copy()
    
    date_cols = ['inv_date', 'oc_date', 'etd', 'first_sale_date']
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    
    str_cols = df.select_dtypes(include=['object']).columns
    df[str_cols] = df[str_cols].fillna('')
    
    return df


def _prepare_monthly_summary(sales_df: pd.DataFrame, debug_label: str = "") -> pd.DataFrame:
    """Prepare monthly summary from sales data."""
    if sales_df.empty:
        return pd.DataFrame()
    
    df = sales_df.copy()
    
    # Ensure invoice_month column
    if 'invoice_month' not in df.columns:
        if 'inv_date' in df.columns:
            df['inv_date'] = pd.to_datetime(df['inv_date'], errors='coerce')
            df['invoice_month'] = df['inv_date'].dt.strftime('%b')
        else:
            return pd.DataFrame()
    
    # Aggregate by month
    try:
        monthly = df.groupby('invoice_month').agg({
            'sales_by_kpi_center_usd': 'sum',
            'gross_profit_by_kpi_center_usd': 'sum',
            'gp1_by_kpi_center_usd': 'sum' if 'gp1_by_kpi_center_usd' in df.columns else 'first',
            'inv_number': pd.Series.nunique,
            'customer_id': pd.Series.nunique
        }).reset_index()
        
        monthly.columns = ['month', 'revenue', 'gross_profit', 'gp1', 'orders', 'customers']
    except Exception as e:
        logger.error(f"Error in _prepare_monthly_summary: {e}")
        return pd.DataFrame()
    
    # Add GP%
    monthly['gp_percent'] = (monthly['gross_profit'] / monthly['revenue'] * 100).fillna(0).round(1)
    
    # Sort by month order
    monthly['month_order'] = monthly['month'].map({m: i for i, m in enumerate(MONTH_ORDER)})
    monthly = monthly.sort_values('month_order')
    
    return monthly


# =============================================================================
# MONTHLY TREND FRAGMENT - UPDATED v2.4.0 to match SP page
# =============================================================================

@st.fragment
def monthly_trend_fragment(
    sales_df: pd.DataFrame,
    filter_values: Dict = None,
    targets_df: pd.DataFrame = None,
    fragment_key: str = "kpc_trend"
):
    """
    Monthly trend chart with Customer/Brand/Product Excl filters.
    SYNCED with Salesperson page (Image 1 & 2).
    
    Shows:
    - Monthly Trend: Revenue + GP bars with GP% line
    - Cumulative Performance: Cumulative Revenue + GP lines
    """
    if sales_df.empty:
        st.info("No sales data for trend analysis")
        return
    
    # Header with Help button
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
    
    # =========================================================================
    # FILTERS ROW - SYNCED with SP page
    # =========================================================================
    
    # Customer filter with Excl checkbox
    col_cust, col_brand, col_prod = st.columns(3)
    
    with col_cust:
        subcol1, subcol2 = st.columns([3, 1])
        with subcol1:
            st.markdown("**Customer**")
        with subcol2:
            excl_customer = st.checkbox("Excl", key=f"{fragment_key}_excl_customer", 
                                       help="Exclude selected customers")
        
        customers = ['All customers...'] + sorted(sales_df['customer'].dropna().unique().tolist())
        selected_customer = st.selectbox(
            "Customer", 
            customers, 
            key=f"{fragment_key}_customer",
            label_visibility="collapsed"
        )
    
    with col_brand:
        subcol1, subcol2 = st.columns([3, 1])
        with subcol1:
            st.markdown("**Brand**")
        with subcol2:
            excl_brand = st.checkbox("Excl", key=f"{fragment_key}_excl_brand",
                                    help="Exclude selected brands")
        
        brands = ['All brands...'] + sorted(sales_df['brand'].dropna().unique().tolist())
        selected_brand = st.selectbox(
            "Brand", 
            brands, 
            key=f"{fragment_key}_brand",
            label_visibility="collapsed"
        )
    
    with col_prod:
        subcol1, subcol2 = st.columns([3, 1])
        with subcol1:
            st.markdown("**Product**")
        with subcol2:
            excl_product = st.checkbox("Excl", key=f"{fragment_key}_excl_product",
                                      help="Exclude selected products")
        
        products = ['All products...'] + sorted(sales_df['product_pn'].dropna().unique().tolist()[:100])
        selected_product = st.selectbox(
            "Product", 
            products, 
            key=f"{fragment_key}_product",
            label_visibility="collapsed"
        )
    
    # =========================================================================
    # APPLY FILTERS
    # =========================================================================
    
    filtered_df = sales_df.copy()
    
    # Customer filter
    if selected_customer != 'All customers...':
        if excl_customer:
            filtered_df = filtered_df[filtered_df['customer'] != selected_customer]
        else:
            filtered_df = filtered_df[filtered_df['customer'] == selected_customer]
    
    # Brand filter
    if selected_brand != 'All brands...':
        if excl_brand:
            filtered_df = filtered_df[filtered_df['brand'] != selected_brand]
        else:
            filtered_df = filtered_df[filtered_df['brand'] == selected_brand]
    
    # Product filter
    if selected_product != 'All products...':
        if excl_product:
            filtered_df = filtered_df[filtered_df['product_pn'] != selected_product]
        else:
            filtered_df = filtered_df[filtered_df['product_pn'] == selected_product]
    
    if filtered_df.empty:
        st.warning("No data matches the selected filters")
        return
    
    # =========================================================================
    # PREPARE MONTHLY DATA
    # =========================================================================
    
    monthly_df = _prepare_monthly_summary(filtered_df)
    
    if monthly_df.empty:
        st.warning("Could not prepare monthly summary")
        return
    
    # =========================================================================
    # CHARTS - 2 columns like SP page
    # =========================================================================
    
    chart_col1, chart_col2 = st.columns(2)
    
    with chart_col1:
        st.markdown("**📊 Monthly Trend**")
        trend_chart = KPICenterCharts.build_monthly_trend_dual_chart(
            monthly_df=monthly_df,
            show_gp_percent_line=True
        )
        st.altair_chart(trend_chart, use_container_width=True)
    
    with chart_col2:
        st.markdown("**📈 Cumulative Performance**")
        cumulative_chart = KPICenterCharts.build_cumulative_dual_chart(
            monthly_df=monthly_df
        )
        st.altair_chart(cumulative_chart, use_container_width=True)


# =============================================================================
# YOY COMPARISON FRAGMENT - UPDATED v2.5.0 with Multi-Year support
# =============================================================================

@st.fragment
def yoy_comparison_fragment(
    queries,
    filter_values: Dict,
    current_year: int = None,
    sales_df: pd.DataFrame = None,
    raw_cached_data: dict = None,
    fragment_key: str = "kpc_yoy"
):
    """
    Year-over-Year / Multi-Year comparison with tabs and filters.
    
    UPDATED v2.5.0: Added Multi-Year Comparison (synced with Salesperson page)
    - Detects actual years in data
    - If >= 2 years → Multi-Year Comparison (grouped bars, cumulative lines)
    - If 0-1 years → YoY Comparison (current vs previous year)
    
    Shows:
    - Tabs: Revenue / Gross Profit / GP1
    - Summary metrics (yearly totals with YoY growth)
    - Monthly comparison charts
    - Cumulative performance charts
    """
    from datetime import date
    
    # Header
    st.subheader("📊 Year-over-Year Comparison")
    
    if current_year is None:
        current_year = filter_values.get('year', date.today().year)
    
    # =========================================================================
    # FILTERS ROW - SYNCED with SP page
    # =========================================================================
    
    col_cust, col_brand, col_prod = st.columns(3)
    
    with col_cust:
        subcol1, subcol2 = st.columns([3, 1])
        with subcol1:
            st.markdown("**Customer**")
        with subcol2:
            excl_customer = st.checkbox("Excl", key=f"{fragment_key}_excl_customer",
                                       help="Exclude selected customers")
        
        if sales_df is not None and not sales_df.empty:
            customers = ['All customers...'] + sorted(sales_df['customer'].dropna().unique().tolist())
        else:
            customers = ['All customers...']
        
        selected_customer = st.selectbox(
            "Customer",
            customers,
            key=f"{fragment_key}_customer",
            label_visibility="collapsed"
        )
    
    with col_brand:
        subcol1, subcol2 = st.columns([3, 1])
        with subcol1:
            st.markdown("**Brand**")
        with subcol2:
            excl_brand = st.checkbox("Excl", key=f"{fragment_key}_excl_brand",
                                    help="Exclude selected brands")
        
        if sales_df is not None and not sales_df.empty:
            brands = ['All brands...'] + sorted(sales_df['brand'].dropna().unique().tolist())
        else:
            brands = ['All brands...']
        
        selected_brand = st.selectbox(
            "Brand",
            brands,
            key=f"{fragment_key}_brand",
            label_visibility="collapsed"
        )
    
    with col_prod:
        subcol1, subcol2 = st.columns([3, 1])
        with subcol1:
            st.markdown("**Product**")
        with subcol2:
            excl_product = st.checkbox("Excl", key=f"{fragment_key}_excl_product",
                                      help="Exclude selected products")
        
        if sales_df is not None and not sales_df.empty:
            products = ['All products...'] + sorted(sales_df['product_pn'].dropna().unique().tolist()[:100])
        else:
            products = ['All products...']
        
        selected_product = st.selectbox(
            "Product",
            products,
            key=f"{fragment_key}_product",
            label_visibility="collapsed"
        )
    
    # =========================================================================
    # APPLY LOCAL FILTERS TO SALES DATA
    # =========================================================================
    
    def apply_local_filters(df):
        """Apply Customer/Brand/Product filters."""
        if df.empty:
            return df
        
        result = df.copy()
        
        if selected_customer != 'All customers...':
            if excl_customer:
                result = result[result['customer'] != selected_customer]
            else:
                result = result[result['customer'] == selected_customer]
        
        if selected_brand != 'All brands...':
            if excl_brand:
                result = result[result['brand'] != selected_brand]
            else:
                result = result[result['brand'] == selected_brand]
        
        if selected_product != 'All products...':
            if excl_product:
                result = result[result['product_pn'] != selected_product]
            else:
                result = result[result['product_pn'] == selected_product]
        
        return result
    
    # Apply filters to main sales_df
    yoy_sales_df = apply_local_filters(sales_df) if sales_df is not None else pd.DataFrame()
    
    # Show filter summary
    active_filters = []
    if selected_customer != 'All customers...':
        mode = "excl" if excl_customer else "incl"
        active_filters.append(f"Customer ({mode})")
    if selected_brand != 'All brands...':
        mode = "excl" if excl_brand else "incl"
        active_filters.append(f"Brand ({mode})")
    if selected_product != 'All products...':
        mode = "excl" if excl_product else "incl"
        active_filters.append(f"Product ({mode})")
    
    if active_filters:
        st.caption(f"🔍 Filters: {' | '.join(active_filters)}")
    
    # =========================================================================
    # DETECT ACTUAL YEARS IN DATA (key logic from Salesperson page)
    # =========================================================================
    
    if not yoy_sales_df.empty and 'invoice_year' in yoy_sales_df.columns:
        actual_years = sorted(yoy_sales_df['invoice_year'].dropna().unique().astype(int).tolist())
    elif not yoy_sales_df.empty and 'inv_date' in yoy_sales_df.columns:
        yoy_sales_df['_year'] = pd.to_datetime(yoy_sales_df['inv_date'], errors='coerce').dt.year
        actual_years = sorted(yoy_sales_df['_year'].dropna().unique().astype(int).tolist())
    else:
        actual_years = []
    
    # =========================================================================
    # BRANCH BASED ON YEAR COUNT
    # =========================================================================
    
    if len(actual_years) >= 2:
        # =================================================================
        # MULTI-YEAR COMPARISON (2+ years of actual data)
        # =================================================================
        years_str = ', '.join(map(str, actual_years))
        st.markdown(f"### 📊 Multi-Year Comparison ({years_str})")
        st.caption(f"ℹ️ Comparing performance across years with actual data in selected date range.")
        
        # Create 3 tabs for each metric
        my_tab1, my_tab2, my_tab3 = st.tabs(["💰 Revenue", "📈 Gross Profit", "📊 GP1"])
        
        # Tab 1: Revenue
        with my_tab1:
            summary_df = KPICenterCharts.build_multi_year_summary_table(
                sales_df=yoy_sales_df,
                years=actual_years,
                metric='revenue'
            )
            
            if not summary_df.empty:
                cols = st.columns(len(actual_years))
                for idx, (_, row) in enumerate(summary_df.iterrows()):
                    with cols[idx]:
                        yoy_val = row['YoY Growth']
                        delta_color = "normal" if yoy_val != '-' and '+' in str(yoy_val) else "inverse" if yoy_val != '-' else "off"
                        st.metric(
                            label=f"{int(row['Year'])} Revenue",
                            value=f"${row['Total']:,.0f}",
                            delta=yoy_val if yoy_val != '-' else None,
                            delta_color=delta_color
                        )
            
            st.divider()
            
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                st.markdown("##### 📊 Monthly Revenue by Year")
                monthly_chart = KPICenterCharts.build_multi_year_monthly_chart(
                    sales_df=yoy_sales_df,
                    years=actual_years,
                    metric='revenue',
                    title=""
                )
                st.altair_chart(monthly_chart, use_container_width=True)
            
            with col_c2:
                st.markdown("##### 📈 Cumulative Revenue by Year")
                cum_chart = KPICenterCharts.build_multi_year_cumulative_chart(
                    sales_df=yoy_sales_df,
                    years=actual_years,
                    metric='revenue',
                    title=""
                )
                st.altair_chart(cum_chart, use_container_width=True)
        
        # Tab 2: Gross Profit
        with my_tab2:
            summary_df = KPICenterCharts.build_multi_year_summary_table(
                sales_df=yoy_sales_df,
                years=actual_years,
                metric='gross_profit'
            )
            
            if not summary_df.empty:
                cols = st.columns(len(actual_years))
                for idx, (_, row) in enumerate(summary_df.iterrows()):
                    with cols[idx]:
                        yoy_val = row['YoY Growth']
                        delta_color = "normal" if yoy_val != '-' and '+' in str(yoy_val) else "inverse" if yoy_val != '-' else "off"
                        st.metric(
                            label=f"{int(row['Year'])} GP",
                            value=f"${row['Total']:,.0f}",
                            delta=yoy_val if yoy_val != '-' else None,
                            delta_color=delta_color
                        )
            
            st.divider()
            
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                st.markdown("##### 📊 Monthly Gross Profit by Year")
                monthly_chart = KPICenterCharts.build_multi_year_monthly_chart(
                    sales_df=yoy_sales_df,
                    years=actual_years,
                    metric='gross_profit',
                    title=""
                )
                st.altair_chart(monthly_chart, use_container_width=True)
            
            with col_c2:
                st.markdown("##### 📈 Cumulative Gross Profit by Year")
                cum_chart = KPICenterCharts.build_multi_year_cumulative_chart(
                    sales_df=yoy_sales_df,
                    years=actual_years,
                    metric='gross_profit',
                    title=""
                )
                st.altair_chart(cum_chart, use_container_width=True)
        
        # Tab 3: GP1
        with my_tab3:
            summary_df = KPICenterCharts.build_multi_year_summary_table(
                sales_df=yoy_sales_df,
                years=actual_years,
                metric='gp1'
            )
            
            if not summary_df.empty:
                cols = st.columns(len(actual_years))
                for idx, (_, row) in enumerate(summary_df.iterrows()):
                    with cols[idx]:
                        yoy_val = row['YoY Growth']
                        delta_color = "normal" if yoy_val != '-' and '+' in str(yoy_val) else "inverse" if yoy_val != '-' else "off"
                        st.metric(
                            label=f"{int(row['Year'])} GP1",
                            value=f"${row['Total']:,.0f}",
                            delta=yoy_val if yoy_val != '-' else None,
                            delta_color=delta_color
                        )
            
            st.divider()
            
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                st.markdown("##### 📊 Monthly GP1 by Year")
                monthly_chart = KPICenterCharts.build_multi_year_monthly_chart(
                    sales_df=yoy_sales_df,
                    years=actual_years,
                    metric='gp1',
                    title=""
                )
                st.altair_chart(monthly_chart, use_container_width=True)
            
            with col_c2:
                st.markdown("##### 📈 Cumulative GP1 by Year")
                cum_chart = KPICenterCharts.build_multi_year_cumulative_chart(
                    sales_df=yoy_sales_df,
                    years=actual_years,
                    metric='gp1',
                    title=""
                )
                st.altair_chart(cum_chart, use_container_width=True)
    
    else:
        # =================================================================
        # YOY COMPARISON (0 or 1 year of actual data)
        # =================================================================
        
        # Determine primary year
        if len(actual_years) == 1:
            primary_year = actual_years[0]
        else:
            primary_year = filter_values.get('end_date', date.today()).year
        
        previous_year = primary_year - 1
        
        st.markdown(f"### 📅 {primary_year} vs {previous_year}")
        
        # Load previous year data
        start_date = filter_values.get('start_date', date(primary_year, 1, 1))
        end_date = filter_values.get('end_date', date.today())
        kpi_center_ids = filter_values.get('kpi_center_ids', [])
        entity_ids = filter_values.get('entity_ids', [])
        exclude_internal = filter_values.get('exclude_internal_revenue', True)
        
        # Calculate previous year date range
        try:
            prev_start = date(start_date.year - 1, start_date.month, start_date.day)
            prev_end = date(end_date.year - 1, end_date.month, end_date.day)
        except ValueError:
            prev_start = date(start_date.year - 1, start_date.month, 28)
            prev_end = date(end_date.year - 1, end_date.month, 28)
        
        # Try to get from cache first
        previous_df = pd.DataFrame()
        cache_hit = False
        
        if raw_cached_data and 'sales_df' in raw_cached_data:
            cached_sales = raw_cached_data['sales_df']
            
            if cached_sales is not None and not cached_sales.empty and 'inv_date' in cached_sales.columns:
                cached_sales = cached_sales.copy()
                cached_sales['inv_date'] = pd.to_datetime(cached_sales['inv_date'], errors='coerce')
                cached_years = cached_sales['inv_date'].dt.year.unique().tolist()
                
                if previous_year in cached_years:
                    previous_df = cached_sales[
                        (cached_sales['inv_date'] >= pd.Timestamp(prev_start)) &
                        (cached_sales['inv_date'] <= pd.Timestamp(prev_end))
                    ].copy()
                    
                    if kpi_center_ids and 'kpi_center_id' in previous_df.columns:
                        previous_df = previous_df[previous_df['kpi_center_id'].isin(kpi_center_ids)]
                    if entity_ids and 'legal_entity_id' in previous_df.columns:
                        previous_df = previous_df[previous_df['legal_entity_id'].isin(entity_ids)]
                    
                    cache_hit = True
        
        # If not in cache, query DB
        if not cache_hit:
            try:
                previous_df = queries.get_sales_data(
                    start_date=prev_start,
                    end_date=prev_end,
                    kpi_center_ids=kpi_center_ids if kpi_center_ids else None,
                    entity_ids=entity_ids if entity_ids else None
                )
            except Exception as e:
                logger.error(f"Error querying previous year data: {e}")
                previous_df = pd.DataFrame()
        
        # Exclude internal revenue
        if exclude_internal and not previous_df.empty and 'customer_type' in previous_df.columns:
            previous_df = previous_df[previous_df['customer_type'] != 'Internal']
        
        # Apply local filters to previous year
        previous_filtered = apply_local_filters(previous_df)
        
        # Prepare monthly summaries
        current_monthly = _prepare_monthly_summary(yoy_sales_df, debug_label="current")
        previous_monthly = _prepare_monthly_summary(previous_filtered, debug_label="previous")
        
        if previous_monthly.empty:
            st.info(f"No data available for {previous_year} comparison")
            return
        
        # Tabs: Revenue / Gross Profit / GP1
        tab_rev, tab_gp, tab_gp1 = st.tabs(["💰 Revenue", "📈 Gross Profit", "📊 GP1"])
        
        for tab, metric_name, metric_col in [
            (tab_rev, "Revenue", "revenue"),
            (tab_gp, "Gross Profit", "gross_profit"),
            (tab_gp1, "GP1", "gp1")
        ]:
            with tab:
                current_total = current_monthly[metric_col].sum() if not current_monthly.empty and metric_col in current_monthly.columns else 0
                previous_total = previous_monthly[metric_col].sum() if not previous_monthly.empty and metric_col in previous_monthly.columns else 0
                
                if previous_total > 0:
                    yoy_change = ((current_total - previous_total) / previous_total * 100)
                    yoy_diff = current_total - previous_total
                else:
                    yoy_change = 0
                    yoy_diff = current_total
                
                col_curr, col_prev = st.columns(2)
                
                with col_curr:
                    st.markdown(f"**{primary_year} {metric_name}**")
                    st.markdown(f"### ${current_total:,.0f}")
                    if yoy_change != 0:
                        color = "green" if yoy_change > 0 else "red"
                        arrow = "↑" if yoy_change > 0 else "↓"
                        st.markdown(f":{color}[{arrow} {yoy_change:+.1f}% YoY]")
                
                with col_prev:
                    st.markdown(f"**{previous_year} {metric_name}**")
                    st.markdown(f"### ${previous_total:,.0f}")
                    st.markdown(f"↑ ${yoy_diff:+,.0f} difference" if yoy_diff != 0 else "")
                
                st.markdown("")
                
                chart_col1, chart_col2 = st.columns(2)
                
                with chart_col1:
                    st.markdown(f"**📊 Monthly {metric_name} Comparison**")
                    comparison_chart = KPICenterCharts.build_yoy_comparison_chart(
                        current_df=current_monthly,
                        previous_df=previous_monthly,
                        metric=metric_name,
                        current_year=primary_year,
                        previous_year=previous_year
                    )
                    st.altair_chart(comparison_chart, use_container_width=True)
                
                with chart_col2:
                    st.markdown(f"**📈 Cumulative {metric_name}**")
                    cumulative_chart = KPICenterCharts.build_yoy_cumulative_chart(
                        current_df=current_monthly,
                        previous_df=previous_monthly,
                        metric=metric_name,
                        current_year=primary_year,
                        previous_year=previous_year
                    )
                    st.altair_chart(cumulative_chart, use_container_width=True)


# =============================================================================
# SALES DETAIL FRAGMENT - REFACTORED v2.6.0 (SYNCED with Salesperson)
# =============================================================================

@st.fragment
def sales_detail_fragment(
    sales_df: pd.DataFrame,
    filter_values: Dict = None,
    overview_metrics: Dict = None,
    fragment_key: str = "kpc_sales"
):
    """
    Fragment for Sales Detail transaction list with filters.
    
    REFACTORED v2.6.0: Fully synced with Salesperson Performance page.
    - 7 summary metrics cards
    - 5 filter columns with Excl checkboxes
    - Original value calculation (pre-split)
    - Formatted Product and OC/PO display
    - Detailed column config with tooltips
    - Column Legend expander
    - Export Filtered View button
    """
    if sales_df.empty:
        st.info("No sales data for selected period")
        return
    
    # =================================================================
    # SUMMARY METRICS CARDS (7 columns - SYNCED with Salesperson)
    # =================================================================
    col_s1, col_s2, col_s3, col_s4, col_s5, col_s6, col_s7 = st.columns(7)
    
    total_revenue = sales_df['sales_by_kpi_center_usd'].sum()
    total_gp = sales_df['gross_profit_by_kpi_center_usd'].sum()
    total_gp1 = sales_df['gp1_by_kpi_center_usd'].sum() if 'gp1_by_kpi_center_usd' in sales_df.columns else 0
    gp_percent = (total_gp / total_revenue * 100) if total_revenue > 0 else 0
    total_invoices = sales_df['inv_number'].nunique()
    total_orders = sales_df['oc_number'].nunique() if 'oc_number' in sales_df.columns else total_invoices
    total_customers = sales_df['customer_id'].nunique()
    
    with col_s1:
        st.metric(
            "💰 Revenue",
            f"${total_revenue:,.0f}",
            delta=f"{total_invoices:,} invoices",
            delta_color="off",
            help="Total revenue from all transactions (split-adjusted)"
        )
    with col_s2:
        st.metric(
            "📈 Gross Profit",
            f"${total_gp:,.0f}",
            delta=f"{gp_percent:.1f}% margin",
            delta_color="off",
            help="Total gross profit (split-adjusted)"
        )
    with col_s3:
        st.metric(
            "📊 GP1",
            f"${total_gp1:,.0f}",
            delta_color="off",
            help="GP1 = GP - (Broker Commission × 1.2)"
        )
    with col_s4:
        st.metric(
            "📋 Orders",
            f"{total_orders:,}",
            delta_color="off",
            help="Number of unique order confirmations"
        )
    with col_s5:
        st.metric(
            "👥 Customers",
            f"{total_customers:,}",
            delta_color="off",
            help="Number of unique customers"
        )
    with col_s6:
        # Average order value
        avg_order = total_revenue / total_orders if total_orders > 0 else 0
        st.metric(
            "📦 Avg Order",
            f"${avg_order:,.0f}",
            delta_color="off",
            help="Average revenue per order"
        )
    with col_s7:
        # Average GP per customer
        avg_gp_customer = total_gp / total_customers if total_customers > 0 else 0
        st.metric(
            "💵 Avg GP/Cust",
            f"${avg_gp_customer:,.0f}",
            delta_color="off",
            help="Average gross profit per customer"
        )
    
    st.divider()
    
    # =================================================================
    # IMPROVED FILTERS - 5 columns with Excl option (SYNCED with Salesperson)
    # =================================================================
    col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns(5)
    
    # Customer filter
    with col_f1:
        customer_options = sorted(sales_df['customer'].dropna().unique().tolist())
        customer_filter = render_multiselect_filter(
            label="Customer",
            options=customer_options,
            key=f"{fragment_key}_customer"
        )
    
    # Brand filter
    with col_f2:
        brand_options = sorted(sales_df['brand'].dropna().unique().tolist())
        brand_filter = render_multiselect_filter(
            label="Brand",
            options=brand_options,
            key=f"{fragment_key}_brand"
        )
    
    # Product filter
    with col_f3:
        product_options = sorted(sales_df['product_pn'].dropna().unique().tolist())[:100]
        product_filter = render_multiselect_filter(
            label="Product",
            options=product_options,
            key=f"{fragment_key}_product"
        )
    
    # OC# / Customer PO search
    with col_f4:
        oc_po_filter = render_text_search_filter(
            label="OC# / Customer PO",
            key=f"{fragment_key}_oc_po",
            placeholder="Search..."
        )
    
    # Min Amount filter
    with col_f5:
        amount_filter = render_number_filter(
            label="Min Amount ($)",
            key=f"{fragment_key}_min_amount",
            default_min=0,
            step=1000
        )
    
    # =================================================================
    # APPLY ALL FILTERS
    # =================================================================
    filtered_df = sales_df.copy()
    
    # Apply multiselect filters
    filtered_df = apply_multiselect_filter(filtered_df, 'customer', customer_filter)
    filtered_df = apply_multiselect_filter(filtered_df, 'brand', brand_filter)
    filtered_df = apply_multiselect_filter(filtered_df, 'product_pn', product_filter)
    
    # Apply text search on multiple columns
    if 'oc_number' in filtered_df.columns or 'customer_po_number' in filtered_df.columns:
        search_columns = []
        if 'oc_number' in filtered_df.columns:
            search_columns.append('oc_number')
        if 'customer_po_number' in filtered_df.columns:
            search_columns.append('customer_po_number')
        filtered_df = apply_text_search_filter(
            filtered_df, 
            columns=search_columns,
            search_result=oc_po_filter
        )
    
    # Apply number filter
    filtered_df = apply_number_filter(filtered_df, 'sales_by_kpi_center_usd', amount_filter)
    
    # =================================================================
    # Show filter summary
    # =================================================================
    active_filters = []
    if customer_filter.is_active:
        mode = "excl" if customer_filter.excluded else "incl"
        active_filters.append(f"Customer: {len(customer_filter.selected)} ({mode})")
    if brand_filter.is_active:
        mode = "excl" if brand_filter.excluded else "incl"
        active_filters.append(f"Brand: {len(brand_filter.selected)} ({mode})")
    if product_filter.is_active:
        mode = "excl" if product_filter.excluded else "incl"
        active_filters.append(f"Product: {len(product_filter.selected)} ({mode})")
    if oc_po_filter.is_active:
        mode = "excl" if oc_po_filter.excluded else "incl"
        active_filters.append(f"OC/PO: '{oc_po_filter.query}' ({mode})")
    if amount_filter.is_active:
        mode = "excl" if amount_filter.excluded else "incl"
        active_filters.append(f"Amount: ≥${amount_filter.min_value:,.0f} ({mode})")
    
    if active_filters:
        st.caption(f"🔍 Active filters: {' | '.join(active_filters)}")
    
    # =================================================================
    # Calculate Original (pre-split) values
    # Formula: Original = Split Value / (Split % / 100)
    # Note: GP1 is calculated field, no "original" value exists
    # =================================================================
    filtered_df = filtered_df.copy()
    
    # Avoid division by zero - default to 100% if split is 0 or missing
    if 'split_rate_percent' in filtered_df.columns:
        split_pct = filtered_df['split_rate_percent'].replace(0, 100).fillna(100) / 100
    else:
        split_pct = 1.0
    
    # Calculate original values (before split) - only Revenue and GP
    filtered_df['total_revenue_usd'] = filtered_df['sales_by_kpi_center_usd'] / split_pct
    filtered_df['total_gp_usd'] = filtered_df['gross_profit_by_kpi_center_usd'] / split_pct
    
    # =================================================================
    # Format Product as "pt_code | Name | Package size"
    # =================================================================
    def format_product_display(row):
        parts = []
        if pd.notna(row.get('pt_code')) and row.get('pt_code'):
            parts.append(str(row['pt_code']))
        if pd.notna(row.get('product_pn')) and row.get('product_pn'):
            parts.append(str(row['product_pn']))
        if pd.notna(row.get('package_size')) and row.get('package_size'):
            parts.append(str(row['package_size']))
        return ' | '.join(parts) if parts else str(row.get('product_pn', 'N/A'))
    
    filtered_df['product_display'] = filtered_df.apply(format_product_display, axis=1)
    
    # =================================================================
    # Format OC with Customer PO: "OC#\n(PO: xxx)"
    # =================================================================
    def format_oc_po(row):
        oc = str(row.get('oc_number', '')) if pd.notna(row.get('oc_number')) else ''
        po = str(row.get('customer_po_number', '')) if pd.notna(row.get('customer_po_number')) else ''
        if oc and po:
            return f"{oc}\n(PO: {po})"
        elif oc:
            return oc
        elif po:
            return f"(PO: {po})"
        return ''
    
    if 'oc_number' in filtered_df.columns:
        filtered_df['oc_po_display'] = filtered_df.apply(format_oc_po, axis=1)
    
    # =================================================================
    # Display columns - reordered with new formatted columns
    # =================================================================
    display_columns = [
        'inv_date', 'inv_number', 'oc_po_display', 'customer', 'product_display', 'brand',
        'total_revenue_usd', 'total_gp_usd',  # Original values (Revenue, GP only)
        'split_rate_percent',
        'sales_by_kpi_center_usd', 'gross_profit_by_kpi_center_usd', 'gp1_by_kpi_center_usd',  # Split values
        'kpi_center'
    ]
    available_cols = [c for c in display_columns if c in filtered_df.columns]
    
    st.markdown(f"**Showing {len(filtered_df):,} transactions** (of {len(sales_df):,} total)")
    
    # Prepare display dataframe
    display_detail = filtered_df[available_cols].head(500).copy()
    
    # =================================================================
    # Configure columns with tooltips using st.column_config
    # =================================================================
    column_config = {
        'inv_date': st.column_config.DateColumn(
            "Date",
            help="Invoice date"
        ),
        'inv_number': st.column_config.TextColumn(
            "Invoice#",
            help="Invoice number"
        ),
        'oc_po_display': st.column_config.TextColumn(
            "OC / PO",
            help="Order Confirmation number and Customer PO",
            width="medium"
        ),
        'customer': st.column_config.TextColumn(
            "Customer",
            help="Customer name",
            width="medium"
        ),
        'product_display': st.column_config.TextColumn(
            "Product",
            help="Product: PT Code | Name | Package Size",
            width="large"
        ),
        'brand': st.column_config.TextColumn(
            "Brand",
            help="Product brand/manufacturer"
        ),
        # Original values (before split)
        'total_revenue_usd': st.column_config.NumberColumn(
            "Total Revenue",
            help="💰 ORIGINAL invoice revenue (100% of line item)\n\nThis is the full value BEFORE applying KPI Center split.",
            format="$%.0f"
        ),
        'total_gp_usd': st.column_config.NumberColumn(
            "Total GP",
            help="📈 ORIGINAL gross profit (100% of line item)\n\nFormula: Revenue - COGS\n\nThis is the full GP BEFORE applying KPI Center split.",
            format="$%.0f"
        ),
        # Split percentage
        'split_rate_percent': st.column_config.NumberColumn(
            "Split %",
            help="👥 KPI Center credit split percentage\n\nThis KPI Center receives this % of the total revenue/GP/GP1.\n\n100% = Full credit\n50% = Shared equally with another KPI Center",
            format="%.0f%%"
        ),
        # Split values (after split)
        'sales_by_kpi_center_usd': st.column_config.NumberColumn(
            "Revenue",
            help="💰 CREDITED revenue for this KPI Center\n\n📐 Formula: Total Revenue × Split %\n\nThis is the revenue credited to this KPI Center after applying their split percentage.",
            format="$%.0f"
        ),
        'gross_profit_by_kpi_center_usd': st.column_config.NumberColumn(
            "GP",
            help="📈 CREDITED gross profit for this KPI Center\n\n📐 Formula: Total GP × Split %\n\nThis is the GP credited to this KPI Center after applying their split percentage.",
            format="$%.0f"
        ),
        'gp1_by_kpi_center_usd': st.column_config.NumberColumn(
            "GP1",
            help="📊 CREDITED GP1 for this KPI Center\n\n📐 Formula: (GP - Broker Commission × 1.2) × Split %\n\nGP1 is calculated from GP after deducting commission, then split.",
            format="$%.0f"
        ),
        'kpi_center': st.column_config.TextColumn(
            "KPI Center",
            help="KPI Center receiving credit for this transaction"
        ),
    }
    
    # Display table with column configuration
    st.dataframe(
        display_detail,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        height=500
    )
    
    # Legend for quick reference
    with st.expander("📖 Column Legend", expanded=False):
        st.markdown("""
        | Column | Description | Formula |
        |--------|-------------|---------|
        | **OC / PO** | Order Confirmation & Customer PO | Combined display |
        | **Product** | PT Code \\| Name \\| Package Size | Formatted product info |
        | **Total Revenue** | Original invoice amount (100%) | Full line item value |
        | **Total GP** | Original gross profit (100%) | Revenue - COGS |
        | **Split %** | Credit allocation to KPI Center | Assigned by KPI split rules |
        | **Revenue** | Credited revenue | Total Revenue × Split % |
        | **GP** | Credited gross profit | Total GP × Split % |
        | **GP1** | Credited GP1 | (GP - Broker Commission × 1.2) × Split % |
        
        > 💡 **Note:** GP1 is a calculated field (GP minus commission), so there's no "original" GP1 value.
        
        > 💡 **Tip:** Hover over column headers to see detailed tooltips.
        """)
    
    # Export filtered view button
    st.caption("💡 For full report with all data, use **Export Report** section")
    if st.button("📥 Export Filtered View", key=f"{fragment_key}_export", help="Export only the filtered transactions shown above"):
        from .export import KPICenterExport
        
        exporter = KPICenterExport()
        excel_bytes = exporter.create_report(
            summary_df=pd.DataFrame(),
            monthly_df=pd.DataFrame(),
            metrics=overview_metrics or {},
            filters=filter_values or {},
            detail_df=filtered_df
        )
        st.download_button(
            label="⬇️ Download Filtered Data",
            data=excel_bytes,
            file_name=f"kpi_center_filtered_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


# =============================================================================
# PIVOT ANALYSIS FRAGMENT - UPDATED v2.6.0 (SYNCED with Salesperson)
# =============================================================================

@st.fragment
def pivot_analysis_fragment(
    sales_df: pd.DataFrame,
    fragment_key: str = "kpc_pivot"
):
    """
    Configurable pivot table analysis.
    
    SYNCED with Salesperson page:
    - Same layout: 3 columns for Rows/Columns/Values
    - Same default: customer / invoice_month / Gross Profit
    - Same styling: background_gradient on Total column
    - Same month ordering: Jan → Dec
    """
    if sales_df.empty:
        st.info("No data for pivot analysis")
        return
    
    st.subheader("📊 Pivot Analysis")
    
    # Pivot configuration - 3 columns like Salesperson
    col_p1, col_p2, col_p3 = st.columns(3)
    
    with col_p1:
        # Row options - kpi_center instead of sales_name
        row_options = ['customer', 'brand', 'kpi_center', 'product_pn', 'legal_entity']
        row_options = [r for r in row_options if r in sales_df.columns]
        pivot_rows = st.selectbox("Rows", row_options, index=0, key=f"{fragment_key}_rows")
    
    with col_p2:
        # Column options - kpi_center instead of sales_name
        col_options = ['invoice_month', 'brand', 'customer', 'kpi_center']
        pivot_cols = st.selectbox("Columns", col_options, index=0, key=f"{fragment_key}_cols")
    
    with col_p3:
        # Value options with friendly labels - DEFAULT index=1 (Gross Profit) like SP
        value_options = ['sales_by_kpi_center_usd', 'gross_profit_by_kpi_center_usd', 'gp1_by_kpi_center_usd']
        value_options = [v for v in value_options if v in sales_df.columns]
        
        # Default to Gross Profit (index=1) if available
        default_idx = 1 if len(value_options) > 1 else 0
        
        pivot_values = st.selectbox(
            "Values", 
            value_options, 
            index=default_idx, 
            key=f"{fragment_key}_values",
            format_func=lambda x: x.replace('_by_kpi_center_usd', '').replace('_', ' ').title()
        )
    
    # Ensure month column exists
    df = sales_df.copy()
    if 'invoice_month' not in df.columns and 'inv_date' in df.columns:
        df['inv_date'] = pd.to_datetime(df['inv_date'], errors='coerce')
        df['invoice_month'] = df['inv_date'].dt.strftime('%b')
    
    # Create pivot
    if pivot_rows in df.columns and (pivot_cols in df.columns or pivot_cols == 'invoice_month'):
        pivot_df = df.pivot_table(
            values=pivot_values,
            index=pivot_rows,
            columns=pivot_cols,
            aggfunc='sum',
            fill_value=0
        )
        
        # Add totals
        pivot_df['Total'] = pivot_df.sum(axis=1)
        pivot_df = pivot_df.sort_values('Total', ascending=False)
        
        # Reorder columns (months) - Jan → Dec like Salesperson
        if pivot_cols == 'invoice_month':
            month_cols = [m for m in MONTH_ORDER if m in pivot_df.columns]
            other_cols = [c for c in pivot_df.columns if c not in MONTH_ORDER and c != 'Total']
            pivot_df = pivot_df[month_cols + other_cols + ['Total']]
        
        # Display with same styling as Salesperson
        st.dataframe(
            pivot_df.style.format("${:,.0f}").background_gradient(cmap='Blues', subset=['Total']),
            use_container_width=True,
            height=500
        )
    else:
        st.warning("Selected columns not available in data")


# =============================================================================
# BACKLOG LIST FRAGMENT - SYNCED v3.0.0 with Salesperson module
# =============================================================================

@st.fragment
def backlog_list_fragment(
    backlog_df: pd.DataFrame,
    filter_values: Dict = None,
    total_backlog_df: pd.DataFrame = None,
    fragment_key: str = "kpc_backlog"
):
    """
    Backlog List fragment with filters.
    
    SYNCED v3.0.0 with Salesperson module:
    - 7 summary metric cards
    - 5 filter columns with Excl option
    - Formatted data table with column config
    
    Args:
        backlog_df: Detailed backlog records (line items)
        filter_values: Current filter values (for date range)
        total_backlog_df: Aggregated backlog totals (for accurate summary)
        fragment_key: Unique key prefix for widgets
    """
    from datetime import date
    from .metrics import KPICenterMetrics
    
    if backlog_df.empty:
        st.info("📦 No backlog data available")
        return
    
    # =========================================================================
    # CALCULATE IN-PERIOD BACKLOG ANALYSIS
    # =========================================================================
    if filter_values:
        start_date = filter_values.get('start_date', date.today())
        end_date = filter_values.get('end_date', date.today())
    else:
        start_date = date.today()
        end_date = date.today()
    
    in_period_analysis = KPICenterMetrics.analyze_in_period_backlog(
        backlog_detail_df=backlog_df,
        start_date=start_date,
        end_date=end_date
    )
    
    # =========================================================================
    # SUMMARY CARDS - 7 columns (synced with Salesperson)
    # =========================================================================
    col_s1, col_s2, col_s3, col_s4, col_s5, col_s6, col_s7 = st.columns(7)
    
    # Detect column names (KPI Center uses different column names than Salesperson)
    value_col = None
    gp_col = None
    for col_name in ['backlog_by_kpi_center_usd', 'backlog_usd', 'backlog_revenue']:
        if col_name in backlog_df.columns:
            value_col = col_name
            break
    for col_name in ['backlog_gp_by_kpi_center_usd', 'backlog_gp_usd', 'backlog_gp']:
        if col_name in backlog_df.columns:
            gp_col = col_name
            break
    
    # Use aggregated totals if available, else calculate from detail
    if total_backlog_df is not None and not total_backlog_df.empty:
        # Check for various column name patterns
        total_backlog_value = 0
        total_backlog_gp = 0
        total_orders = 0
        total_customers = 0
        
        for col in ['total_backlog_revenue', 'backlog_revenue', 'backlog_usd']:
            if col in total_backlog_df.columns:
                total_backlog_value = total_backlog_df[col].sum()
                break
        
        for col in ['total_backlog_gp', 'backlog_gp', 'backlog_gp_usd']:
            if col in total_backlog_df.columns:
                total_backlog_gp = total_backlog_df[col].sum()
                break
        
        if 'backlog_orders' in total_backlog_df.columns:
            total_orders = int(total_backlog_df['backlog_orders'].sum())
        else:
            total_orders = backlog_df['oc_number'].nunique() if 'oc_number' in backlog_df.columns else len(backlog_df)
        
        if 'backlog_customers' in total_backlog_df.columns:
            total_customers = int(total_backlog_df['backlog_customers'].sum())
        else:
            total_customers = backlog_df['customer_id'].nunique() if 'customer_id' in backlog_df.columns else backlog_df['customer'].nunique()
    else:
        # Fallback: calculate from detail
        total_backlog_value = backlog_df[value_col].sum() if value_col else 0
        total_backlog_gp = backlog_df[gp_col].sum() if gp_col else 0
        total_orders = backlog_df['oc_number'].nunique() if 'oc_number' in backlog_df.columns else len(backlog_df)
        total_customers = backlog_df['customer_id'].nunique() if 'customer_id' in backlog_df.columns else backlog_df['customer'].nunique()
    
    with col_s1:
        st.metric(
            "💰 Total Backlog", 
            f"${total_backlog_value:,.0f}", 
            f"{total_orders:,} orders",
            delta_color="off",
            help="All pending orders from selected KPI Centers"
        )
    with col_s2:
        st.metric(
            "📈 Total GP", 
            f"${total_backlog_gp:,.0f}",
            f"{total_customers:,} customers",
            delta_color="off",
            help="Total gross profit from all pending orders"
        )
    with col_s3:
        in_period_value = in_period_analysis.get('total_value', 0)
        in_period_count = in_period_analysis.get('total_count', 0)
        st.metric(
            "📅 In-Period",
            f"${in_period_value:,.0f}",
            f"{in_period_count:,} orders",
            delta_color="off",
            help="Backlog with ETD within selected date range"
        )
    with col_s4:
        in_period_gp = in_period_analysis.get('total_gp', 0)
        st.metric(
            "📊 In-Period GP",
            f"${in_period_gp:,.0f}",
            delta_color="off",
            help="Gross profit from in-period backlog"
        )
    with col_s5:
        on_track_value = in_period_analysis.get('on_track_value', 0)
        on_track_count = in_period_analysis.get('on_track_count', 0)
        st.metric(
            "✅ On Track",
            f"${on_track_value:,.0f}",
            f"{on_track_count:,} orders",
            delta_color="off",
            help="In-period orders with ETD ≥ today"
        )
    with col_s6:
        overdue_value = in_period_analysis.get('overdue_value', 0)
        overdue_count = in_period_analysis.get('overdue_count', 0)
        st.metric(
            "⚠️ Overdue",
            f"${overdue_value:,.0f}",
            f"{overdue_count:,} orders",
            delta_color="inverse" if overdue_count > 0 else "off",
            help="In-period orders with ETD < today (past due)"
        )
    with col_s7:
        status = in_period_analysis.get('status', 'unknown')
        status_display = "HEALTHY ✅" if status == 'healthy' else "HAS OVERDUE ⚠️"
        st.metric(
            "📊 Status",
            status_display,
            help="HEALTHY = no overdue orders"
        )
    
    st.divider()
    
    # =========================================================================
    # FILTERS - 5 columns with Excl checkbox (synced with Salesperson)
    # =========================================================================
    col_bf1, col_bf2, col_bf3, col_bf4, col_bf5 = st.columns(5)
    
    # Customer filter
    with col_bf1:
        bl_customer_options = sorted(backlog_df['customer'].dropna().unique().tolist())
        bl_customer_filter = render_multiselect_filter(
            label="Customer",
            options=bl_customer_options,
            key=f"{fragment_key}_customer"
        )
    
    # Brand filter
    with col_bf2:
        bl_brand_options = sorted(backlog_df['brand'].dropna().unique().tolist()) if 'brand' in backlog_df.columns else []
        bl_brand_filter = render_multiselect_filter(
            label="Brand",
            options=bl_brand_options,
            key=f"{fragment_key}_brand"
        )
    
    # Product filter
    with col_bf3:
        bl_product_options = sorted(backlog_df['product_pn'].dropna().unique().tolist())[:100] if 'product_pn' in backlog_df.columns else []
        bl_product_filter = render_multiselect_filter(
            label="Product",
            options=bl_product_options,
            key=f"{fragment_key}_product"
        )
    
    # OC# / Customer PO search
    with col_bf4:
        bl_oc_po_filter = render_text_search_filter(
            label="OC# / Customer PO",
            key=f"{fragment_key}_oc_po"
        )
    
    # Status filter
    with col_bf5:
        pending_col = 'pending_type' if 'pending_type' in backlog_df.columns else 'status'
        bl_status_options = backlog_df[pending_col].dropna().unique().tolist() if pending_col in backlog_df.columns else []
        bl_status_filter = render_multiselect_filter(
            label="Status",
            options=bl_status_options,
            key=f"{fragment_key}_status"
        )
    
    # =========================================================================
    # APPLY FILTERS
    # =========================================================================
    filtered_backlog = backlog_df.copy()
    
    # Apply multiselect filters
    filtered_backlog = apply_multiselect_filter(filtered_backlog, 'customer', bl_customer_filter)
    filtered_backlog = apply_multiselect_filter(filtered_backlog, 'brand', bl_brand_filter)
    filtered_backlog = apply_multiselect_filter(filtered_backlog, 'product_pn', bl_product_filter)
    filtered_backlog = apply_multiselect_filter(filtered_backlog, pending_col, bl_status_filter)
    
    # Apply text search on multiple columns
    search_cols = ['oc_number']
    if 'customer_po_number' in backlog_df.columns:
        search_cols.append('customer_po_number')
    elif 'customer_po' in backlog_df.columns:
        search_cols.append('customer_po')
    
    filtered_backlog = apply_text_search_filter(
        filtered_backlog, 
        columns=search_cols,
        search_result=bl_oc_po_filter
    )
    
    # =========================================================================
    # SHOW FILTER SUMMARY
    # =========================================================================
    active_bl_filters = []
    if bl_customer_filter.is_active:
        mode = "excl" if bl_customer_filter.excluded else "incl"
        active_bl_filters.append(f"Customer: {len(bl_customer_filter.selected)} ({mode})")
    if bl_brand_filter.is_active:
        mode = "excl" if bl_brand_filter.excluded else "incl"
        active_bl_filters.append(f"Brand: {len(bl_brand_filter.selected)} ({mode})")
    if bl_product_filter.is_active:
        mode = "excl" if bl_product_filter.excluded else "incl"
        active_bl_filters.append(f"Product: {len(bl_product_filter.selected)} ({mode})")
    if bl_oc_po_filter.is_active:
        mode = "excl" if bl_oc_po_filter.excluded else "incl"
        active_bl_filters.append(f"OC/PO: '{bl_oc_po_filter.query}' ({mode})")
    if bl_status_filter.is_active:
        mode = "excl" if bl_status_filter.excluded else "incl"
        active_bl_filters.append(f"Status: {len(bl_status_filter.selected)} ({mode})")
    
    if active_bl_filters:
        st.caption(f"🔍 Active filters: {' | '.join(active_bl_filters)}")
    
    # =========================================================================
    # FORMAT DISPLAY COLUMNS
    # =========================================================================
    
    # Format Product as "pt_code | Name | Package size"
    def format_product_display(row):
        parts = []
        if pd.notna(row.get('pt_code')) and row.get('pt_code'):
            parts.append(str(row['pt_code']))
        if pd.notna(row.get('product_pn')) and row.get('product_pn'):
            parts.append(str(row['product_pn']))
        if pd.notna(row.get('package_size')) and row.get('package_size'):
            parts.append(str(row['package_size']))
        return ' | '.join(parts) if parts else str(row.get('product_pn', 'N/A'))
    
    filtered_backlog = filtered_backlog.copy()
    filtered_backlog['product_display'] = filtered_backlog.apply(format_product_display, axis=1)
    
    # Format OC with Customer PO
    def format_oc_po(row):
        oc = str(row.get('oc_number', '')) if pd.notna(row.get('oc_number')) else ''
        po_col = 'customer_po_number' if 'customer_po_number' in row.index else 'customer_po'
        po = str(row.get(po_col, '')) if pd.notna(row.get(po_col)) else ''
        if oc and po:
            return f"{oc}\n(PO: {po})"
        elif oc:
            return oc
        elif po:
            return f"(PO: {po})"
        return ''
    
    filtered_backlog['oc_po_display'] = filtered_backlog.apply(format_oc_po, axis=1)
    
    st.markdown(f"**Showing {len(filtered_backlog):,} backlog items** (of {len(backlog_df):,} total)")
    
    # =========================================================================
    # DATA TABLE WITH COLUMN CONFIG
    # =========================================================================
    
    # Determine which columns to display based on what's available
    oc_date_col = 'oc_date' if 'oc_date' in filtered_backlog.columns else None
    etd_col = 'etd' if 'etd' in filtered_backlog.columns else None
    kpi_center_col = 'kpi_center' if 'kpi_center' in filtered_backlog.columns else 'kpi_center_name'
    
    backlog_display_cols = ['oc_po_display']
    if oc_date_col:
        backlog_display_cols.append(oc_date_col)
    if etd_col:
        backlog_display_cols.append(etd_col)
    backlog_display_cols.extend(['customer', 'product_display', 'brand'])
    if value_col:
        backlog_display_cols.append(value_col)
    if gp_col:
        backlog_display_cols.append(gp_col)
    backlog_display_cols.append('days_until_etd')
    backlog_display_cols.append(pending_col)
    if kpi_center_col in filtered_backlog.columns:
        backlog_display_cols.append(kpi_center_col)
    
    available_bl_cols = [c for c in backlog_display_cols if c in filtered_backlog.columns]
    
    display_bl = filtered_backlog[available_bl_cols].head(500).copy()
    
    # Column configuration
    column_config = {
        'oc_po_display': st.column_config.TextColumn(
            "OC / PO",
            help="Order Confirmation and Customer PO",
            width="medium"
        ),
        'oc_date': st.column_config.DateColumn(
            "OC Date",
            help="Order confirmation date"
        ),
        'etd': st.column_config.DateColumn(
            "ETD",
            help="Estimated time of departure"
        ),
        'customer': st.column_config.TextColumn(
            "Customer",
            help="Customer name",
            width="medium"
        ),
        'product_display': st.column_config.TextColumn(
            "Product",
            help="Product: PT Code | Name | Package Size",
            width="large"
        ),
        'brand': st.column_config.TextColumn(
            "Brand",
            help="Product brand/manufacturer"
        ),
        'days_until_etd': st.column_config.NumberColumn(
            "Days to ETD",
            help="Days until ETD (negative = overdue)"
        ),
        'pending_type': st.column_config.TextColumn(
            "Status",
            help="Both Pending / Delivery Pending / Invoice Pending"
        ),
        'status': st.column_config.TextColumn(
            "Status",
            help="Order status"
        ),
        'kpi_center': st.column_config.TextColumn(
            "KPI Center",
            help="KPI Center receiving credit"
        ),
        'kpi_center_name': st.column_config.TextColumn(
            "KPI Center",
            help="KPI Center receiving credit"
        ),
    }
    
    # Add dynamic column configs for value columns
    if value_col:
        column_config[value_col] = st.column_config.NumberColumn(
            "Amount",
            help="Backlog amount (split-adjusted)",
            format="$%.0f"
        )
    if gp_col:
        column_config[gp_col] = st.column_config.NumberColumn(
            "GP",
            help="Backlog gross profit (split-adjusted)",
            format="$%.0f"
        )
    
    st.dataframe(
        display_bl,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        height=400
    )


# =============================================================================
# BACKLOG BY ETD FRAGMENT - NEW v3.0.0 (synced with Salesperson)
# FIX v3.0.1: Use backlog_detail_df and aggregate in fragment to fix filter bug
# =============================================================================

@st.fragment
def backlog_by_etd_fragment(
    backlog_detail_df: pd.DataFrame,
    current_year: int = None,
    fragment_key: str = "kpc_backlog_etd"
):
    """
    Fragment for Backlog by ETD Month with multi-year support.
    
    SYNCED v3.0.0 with Salesperson module:
    - Timeline view: Chronological across all years
    - Stacked by Month: Compare same months across years
    - Single Year: One year only with selector
    
    FIX v3.0.1: Changed from backlog_by_month_df to backlog_detail_df
    - Previous: Used pre-aggregated data that wasn't filtered by KPI Center
    - Now: Uses detail data (already filtered) and aggregates in fragment
    
    Args:
        backlog_detail_df: Detailed backlog records (already filtered by KPI Center)
        current_year: Current filter year (for Single Year default)
        fragment_key: Unique key prefix for widgets
    """
    from datetime import datetime
    
    st.markdown("#### 📅 Backlog by ETD Month")
    
    if backlog_detail_df.empty:
        st.info("No backlog data available")
        return
    
    # =========================================================================
    # AGGREGATE FROM DETAIL DATA (FIX for filter bug)
    # =========================================================================
    df = backlog_detail_df.copy()
    
    # Ensure ETD is datetime and extract year/month
    if 'etd' not in df.columns:
        st.warning("Missing ETD column in backlog data")
        return
    
    df['etd'] = pd.to_datetime(df['etd'], errors='coerce')
    df = df.dropna(subset=['etd'])
    
    if df.empty:
        st.info("No valid ETD dates in backlog")
        return
    
    df['etd_year'] = df['etd'].dt.year
    df['etd_month'] = df['etd'].dt.strftime('%b')
    
    # Detect value columns
    value_col = None
    gp_col_detail = None
    for col_name in ['backlog_by_kpi_center_usd', 'backlog_usd', 'backlog_revenue', 'backlog_sales_by_split_usd']:
        if col_name in df.columns:
            value_col = col_name
            break
    for col_name in ['backlog_gp_by_kpi_center_usd', 'backlog_gp_usd', 'backlog_gp', 'backlog_gp_by_split_usd']:
        if col_name in df.columns:
            gp_col_detail = col_name
            break
    
    if not value_col:
        st.warning("Missing backlog value column")
        return
    
    # Aggregate by year and month
    agg_dict = {value_col: 'sum'}
    if gp_col_detail:
        agg_dict[gp_col_detail] = 'sum'
    if 'oc_number' in df.columns:
        agg_dict['oc_number'] = pd.Series.nunique
    
    df_years = df.groupby(['etd_year', 'etd_month']).agg(agg_dict).reset_index()
    
    # Rename columns for consistency
    df_years = df_years.rename(columns={
        value_col: 'backlog_revenue',
        gp_col_detail: 'backlog_gp' if gp_col_detail else None,
        'oc_number': 'order_count'
    })
    df_years = df_years.dropna(axis=1, how='all')  # Remove None columns
    
    # =========================================================================
    # REST OF FRAGMENT LOGIC
    # =========================================================================
    
    unique_years = sorted(df_years['etd_year'].unique())
    unique_years = [y for y in unique_years if y > 2000]  # Filter valid years
    
    if not unique_years:
        st.info("No valid ETD dates in backlog")
        return
    
    # Show year info if multi-year
    if len(unique_years) > 1:
        year_list = ', '.join(map(str, unique_years))
        st.info(f"📆 Backlog spans {len(unique_years)} years: {year_list}")
    
    # View mode selector
    col_view, col_spacer = st.columns([2, 4])
    with col_view:
        view_mode = st.radio(
            "View Mode",
            options=["Timeline", "Stacked by Month", "Single Year"],
            horizontal=True,
            key=f"{fragment_key}_view_mode",
            help="Timeline: Chronological view | Stacked: Compare months across years | Single Year: One year only"
        )
    
    # Column names after aggregation
    revenue_col = 'backlog_revenue'
    gp_col = 'backlog_gp' if 'backlog_gp' in df_years.columns else None
    order_col = 'order_count' if 'order_count' in df_years.columns else None
    
    if view_mode == "Timeline":
        # =============================================================
        # TIMELINE VIEW - Chronological across all years
        # =============================================================
        
        # Create year_month label for timeline
        df_timeline = df_years.copy()
        df_timeline['year_month'] = df_timeline['etd_month'] + "'" + df_timeline['etd_year'].astype(str).str[-2:]
        
        # Sort chronologically
        month_to_num = {m: i for i, m in enumerate(MONTH_ORDER)}
        df_timeline['sort_key'] = df_timeline['etd_year'] * 100 + df_timeline['etd_month'].map(month_to_num)
        df_timeline = df_timeline.sort_values('sort_key')
        
        if revenue_col and df_timeline[revenue_col].sum() > 0:
            # Build chart
            chart = KPICenterCharts.build_backlog_by_month_chart_multiyear(
                monthly_df=df_timeline,
                revenue_col=revenue_col,
                title=""
            )
            st.altair_chart(chart, use_container_width=True)
            
            # Data table
            display_cols = ['year_month', 'etd_year']
            if revenue_col:
                display_cols.append(revenue_col)
            if gp_col:
                display_cols.append(gp_col)
            if order_col in df_timeline.columns:
                display_cols.append(order_col)
            
            display_cols = [c for c in display_cols if c in df_timeline.columns]
            
            format_dict = {}
            if revenue_col:
                format_dict[revenue_col] = '${:,.0f}'
            if gp_col:
                format_dict[gp_col] = '${:,.0f}'
            
            st.dataframe(
                df_timeline[display_cols].style.format(format_dict),
                use_container_width=True,
                hide_index=True,
                height=400
            )
        else:
            st.info("No backlog data to display")
    
    elif view_mode == "Stacked by Month":
        # =============================================================
        # STACKED VIEW - Compare same months across years
        # =============================================================
        
        if revenue_col and df_years[revenue_col].sum() > 0:
            chart = KPICenterCharts.build_backlog_by_month_stacked(
                monthly_df=df_years,
                revenue_col=revenue_col,
                title=""
            )
            st.altair_chart(chart, use_container_width=True)
            
            # Pivot table: months as rows, years as columns
            pivot_df = df_years.pivot_table(
                index='etd_month',
                columns='etd_year',
                values=revenue_col,
                aggfunc='sum',
                fill_value=0
            )
            # Reorder months
            pivot_df = pivot_df.reindex(MONTH_ORDER)
            pivot_df = pivot_df.dropna(how='all')
            
            # Add total column
            pivot_df['Total'] = pivot_df.sum(axis=1)
            
            st.dataframe(
                pivot_df.style.format('${:,.0f}'),
                use_container_width=True
            )
        else:
            st.info("No backlog data to display")
    
    else:  # Single Year
        # =============================================================
        # SINGLE YEAR VIEW - Original behavior with year selector
        # =============================================================
        col_year, _ = st.columns([2, 4])
        with col_year:
            # Default to current_year if available, else first year
            default_idx = 0
            if current_year and current_year in unique_years:
                default_idx = unique_years.index(current_year)
            elif unique_years:
                # Default to latest year
                default_idx = len(unique_years) - 1
            
            selected_year = st.selectbox(
                "Select Year",
                options=unique_years,
                index=default_idx,
                key=f"{fragment_key}_year_select"
            )
        
        year_data = df_years[df_years['etd_year'] == selected_year].copy()
        
        if not year_data.empty and revenue_col and year_data[revenue_col].sum() > 0:
            # Sort by month order
            month_to_num = {m: i for i, m in enumerate(MONTH_ORDER)}
            year_data['month_order'] = year_data['etd_month'].map(month_to_num)
            year_data = year_data.sort_values('month_order')
            
            chart = KPICenterCharts.build_backlog_by_month_chart(
                monthly_df=year_data,
                revenue_col=revenue_col,
                gp_col=gp_col,
                month_col='etd_month',
                title=f"Backlog by ETD Month - {selected_year}"
            )
            st.altair_chart(chart, use_container_width=True)
            
            # Monthly table
            display_cols = ['etd_month']
            if revenue_col:
                display_cols.append(revenue_col)
            if gp_col:
                display_cols.append(gp_col)
            if order_col in year_data.columns:
                display_cols.append(order_col)
            
            display_cols = [c for c in display_cols if c in year_data.columns]
            
            format_dict = {}
            if revenue_col:
                format_dict[revenue_col] = '${:,.0f}'
            if gp_col:
                format_dict[gp_col] = '${:,.0f}'
            
            st.dataframe(
                year_data[display_cols].style.format(format_dict),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info(f"No backlog data for {selected_year}")


# =============================================================================
# BACKLOG RISK ANALYSIS FRAGMENT - NEW v3.0.0 (synced with Salesperson)
# =============================================================================

@st.fragment
def backlog_risk_analysis_fragment(
    backlog_df: pd.DataFrame,
    fragment_key: str = "kpc_backlog_risk"
):
    """
    Fragment for Backlog Risk Analysis.
    
    SYNCED v3.0.0 with Salesperson module:
    - 4 risk category cards: Overdue, This Week, This Month, On Track
    - Overdue orders detail table
    
    Args:
        backlog_df: Detailed backlog records with days_until_etd column
        fragment_key: Unique key prefix for widgets
    """
    st.markdown("#### ⚠️ Backlog Risk Analysis")
    
    if backlog_df.empty:
        st.info("No backlog data for risk analysis")
        return
    
    # Ensure days_until_etd is numeric
    backlog_risk = backlog_df.copy()
    if 'days_until_etd' not in backlog_risk.columns:
        st.warning("Missing days_until_etd column for risk analysis")
        return
    
    backlog_risk['days_until_etd'] = pd.to_numeric(
        backlog_risk['days_until_etd'], errors='coerce'
    )
    
    # Detect value column
    value_col = None
    gp_col = None
    for col in ['backlog_by_kpi_center_usd', 'backlog_usd', 'backlog_revenue']:
        if col in backlog_risk.columns:
            value_col = col
            break
    for col in ['backlog_gp_by_kpi_center_usd', 'backlog_gp_usd', 'backlog_gp']:
        if col in backlog_risk.columns:
            gp_col = col
            break
    
    if not value_col:
        st.warning("Missing backlog value column")
        return
    
    # Categorize by risk level
    overdue = backlog_risk[backlog_risk['days_until_etd'] < 0]
    this_week = backlog_risk[
        (backlog_risk['days_until_etd'] >= 0) & 
        (backlog_risk['days_until_etd'] <= 7)
    ]
    this_month = backlog_risk[
        (backlog_risk['days_until_etd'] > 7) & 
        (backlog_risk['days_until_etd'] <= 30)
    ]
    on_track = backlog_risk[backlog_risk['days_until_etd'] > 30]
    
    # =========================================================================
    # RISK SUMMARY CARDS - 4 columns
    # =========================================================================
    col_r1, col_r2, col_r3, col_r4 = st.columns(4)
    
    with col_r1:
        st.metric(
            "🔴 Overdue",
            f"${overdue[value_col].sum():,.0f}",
            delta=f"{len(overdue)} orders",
            delta_color="inverse"
        )
    
    with col_r2:
        st.metric(
            "🟠 This Week",
            f"${this_week[value_col].sum():,.0f}",
            delta=f"{len(this_week)} orders",
            delta_color="off"
        )
    
    with col_r3:
        st.metric(
            "🟡 This Month",
            f"${this_month[value_col].sum():,.0f}",
            delta=f"{len(this_month)} orders",
            delta_color="off"
        )
    
    with col_r4:
        st.metric(
            "🟢 On Track",
            f"${on_track[value_col].sum():,.0f}",
            delta=f"{len(on_track)} orders",
            delta_color="off"
        )
    
    st.divider()
    
    # =========================================================================
    # OVERDUE ORDERS TABLE
    # =========================================================================
    if not overdue.empty:
        st.markdown("##### 🔴 Overdue Orders (ETD Passed)")
        
        # Sort by most overdue first
        overdue_sorted = overdue.sort_values('days_until_etd', ascending=True)
        
        # Calculate days overdue (positive number)
        overdue_sorted['days_overdue'] = -overdue_sorted['days_until_etd']
        
        # Determine display columns
        kpi_center_col = 'kpi_center' if 'kpi_center' in overdue_sorted.columns else 'kpi_center_name'
        oc_col = 'oc_number' if 'oc_number' in overdue_sorted.columns else None
        
        display_cols = []
        if oc_col:
            display_cols.append(oc_col)
        display_cols.extend(['etd', 'customer', 'product_pn', 'brand', value_col])
        if gp_col:
            display_cols.append(gp_col)
        display_cols.append('days_overdue')
        if 'pending_type' in overdue_sorted.columns:
            display_cols.append('pending_type')
        elif 'status' in overdue_sorted.columns:
            display_cols.append('status')
        if kpi_center_col in overdue_sorted.columns:
            display_cols.append(kpi_center_col)
        
        available_cols = [c for c in display_cols if c in overdue_sorted.columns]
        
        column_config = {
            'oc_number': st.column_config.TextColumn("OC / PO", width="medium"),
            'etd': st.column_config.DateColumn("ETD"),
            'customer': st.column_config.TextColumn("Customer", width="medium"),
            'product_pn': st.column_config.TextColumn("Product", width="large"),
            'brand': "Brand",
            'days_overdue': st.column_config.NumberColumn("Days Overdue"),
            'pending_type': "Status",
            'status': "Status",
            'kpi_center': "KPI Center",
            'kpi_center_name': "KPI Center",
        }
        
        # Add value column config
        column_config[value_col] = st.column_config.NumberColumn("Amount", format="$%.0f")
        if gp_col:
            column_config[gp_col] = st.column_config.NumberColumn("GP", format="$%.0f")
        
        st.dataframe(
            overdue_sorted[available_cols].head(100),
            column_config=column_config,
            use_container_width=True,
            hide_index=True,
            height=400
        )
    else:
        st.success("✅ No overdue orders - all backlog is on track!")


# =============================================================================
# KPI ASSIGNMENTS FRAGMENT (My KPIs Tab) - NEW v3.1.0
# =============================================================================

@st.fragment
def kpi_assignments_fragment(
    targets_df: pd.DataFrame,
    fragment_key: str = "kpc_assignments"
):
    """
    KPI Assignments fragment with improved UI.
    
    NEW v3.1.0: Synced with Salesperson page - improved table formatting.
    
    Args:
        targets_df: KPI targets DataFrame
        fragment_key: Unique key prefix for widgets
    """
    if targets_df.empty:
        st.info("📋 No KPI assignments found for selected KPI Centers and year")
        return
    
    # KPI icons mapping
    kpi_icons = {
        'revenue': '💰',
        'gross_profit': '📈',
        'gross_profit_1': '📊',
        'gp1': '📊',
        'num_new_customers': '👥',
        'num_new_products': '📦',
        'new_business_revenue': '💼',
    }
    
    # Group by KPI Center
    for kpi_center_id in targets_df['kpi_center_id'].unique():
        kc_targets = targets_df[targets_df['kpi_center_id'] == kpi_center_id].copy()
        kc_name = kc_targets['kpi_center_name'].iloc[0] if 'kpi_center_name' in kc_targets.columns else f"KPI Center {kpi_center_id}"
        
        with st.expander(f"🎯 {kc_name}", expanded=True):
            # Prepare display dataframe
            display_df = kc_targets.copy()
            
            # Format KPI name with icon
            if 'kpi_name' in display_df.columns:
                display_df['KPI'] = display_df['kpi_name'].apply(
                    lambda x: f"{kpi_icons.get(str(x).lower(), '📋')} {str(x).replace('_', ' ').title()}" if pd.notna(x) else ''
                )
            
            # Select columns for display
            display_cols = ['KPI', 'annual_target_value', 'monthly_target_value', 
                          'quarterly_target_value', 'unit_of_measure', 'weight_numeric']
            available_cols = [c for c in display_cols if c in display_df.columns]
            
            if not available_cols:
                available_cols = [c for c in display_df.columns if c not in ['kpi_center_id', 'kpi_center_name', 'kpi_type_id']]
            
            st.dataframe(
                display_df[available_cols],
                use_container_width=True,
                hide_index=True,
                column_config={
                    'KPI': st.column_config.TextColumn('KPI', width='medium'),
                    'annual_target_value': st.column_config.TextColumn('Annual Target', width='small'),
                    'monthly_target_value': st.column_config.TextColumn('Monthly', width='small'),
                    'quarterly_target_value': st.column_config.TextColumn('Quarterly', width='small'),
                    'unit_of_measure': st.column_config.TextColumn('Unit', width='small'),
                    'weight_numeric': st.column_config.NumberColumn('Weight %', format='%.0f%%', width='small'),
                }
            )


# =============================================================================
# KPI PROGRESS FRAGMENT (Progress Tab) - NEW v3.1.0
# =============================================================================

@st.fragment
def kpi_progress_fragment(
    kpi_progress_data: list,
    period_type: str = 'YTD',
    year: int = None,
    fragment_key: str = "kpc_progress"
):
    """
    KPI Progress fragment with progress bars.
    
    NEW v3.1.0: Synced with Salesperson page - progress bars with achievement %.
    
    Args:
        kpi_progress_data: List of dicts from metrics.get_kpi_progress_data()
        period_type: Current period type for display
        year: Current year
        fragment_key: Unique key prefix
    """
    if not kpi_progress_data:
        st.info("📊 No KPI progress data available")
        return
    
    # Explanatory Note (collapsible)
    with st.expander("ℹ️ How KPI Progress is calculated", expanded=False):
        st.markdown(f"""
**📐 Calculation Method**

Achievement % is calculated using **Prorated Target** based on the selected period type:

| Period Type | Target Proration |
|-------------|------------------|
| **YTD** | Annual Target × (Elapsed Days / 365) |
| **QTD** | Annual Target / 4 × (Elapsed Days in Quarter / Days in Quarter) |
| **MTD** | Annual Target / 12 × (Day of Month / Days in Month) |
| **Custom** | Annual Target × (Days in Period / 365) |

**Current Settings:** {period_type} for {year}

**📊 Why Prorated?**

Using prorated targets allows fair comparison:
- In June (YTD), achieving 50% of annual target = 100% achievement
- This is consistent with how **Overall Achievement** is calculated

**🎯 KPI Center Filtering**

Each KPI only counts actuals from KPI Centers who have that specific KPI target assigned.
This ensures accurate achievement measurement when viewing multiple KPI Centers.
        """)
    
    # Display progress for each KPI
    for kpi in kpi_progress_data:
        display_name = kpi['display_name']
        actual = kpi['actual']
        prorated_target = kpi['prorated_target']
        annual_target = kpi['annual_target']
        achievement = kpi['achievement']
        is_currency = kpi['is_currency']
        kpi_center_count = kpi['kpi_center_count']
        
        # Format values
        if is_currency:
            actual_str = f"${actual:,.0f}"
            prorated_str = f"${prorated_target:,.0f}"
            annual_str = f"${annual_target:,.0f}"
        else:
            actual_str = f"{actual:.1f}"
            prorated_str = f"{prorated_target:.1f}"
            annual_str = f"{annual_target:.0f}"
        
        # KPI Header
        st.markdown(f"**{display_name}**")
        
        # Progress bar (cap at 100% for display)
        progress_value = min(achievement / 100, 1.0)
        st.progress(progress_value)
        
        # Caption with details
        st.caption(f"{actual_str} / {prorated_str} prorated ({annual_str} annual) • {kpi_center_count} KPI Centers")
        
        # Achievement badge with color
        col_badge, col_spacer = st.columns([1, 5])
        with col_badge:
            if achievement >= 100:
                st.success(f"✅ {achievement:.1f}%")
            elif achievement >= 80:
                st.warning(f"🟡 {achievement:.1f}%")
            else:
                st.error(f"🔴 {achievement:.1f}%")
        
        st.markdown("---")


# =============================================================================
# KPI CENTER RANKING FRAGMENT - UPDATED v3.1.0 with medals
# =============================================================================

@st.fragment
def kpi_center_ranking_fragment(
    ranking_df: pd.DataFrame,
    show_targets: bool = True,
    fragment_key: str = "kpc_ranking"
):
    """
    KPI Center performance ranking table.
    
    UPDATED v3.1.0: Added medals (🥇🥈🥉), sortable dropdown, achievement column with gradient.
    Synced with Salesperson Team Ranking UI.
    """
    if ranking_df.empty:
        st.info("No ranking data available")
        return
    
    # Rank by dropdown with expander style
    with st.expander("📊 Rank by", expanded=True):
        sort_options = ['KPI Achievement %', 'Revenue', 'Gross Profit', 'GP1', 'GP %', 'Customers']
        if not show_targets:
            sort_options.remove('KPI Achievement %')
        
        sort_by = st.selectbox(
            "Select ranking criteria",
            sort_options,
            key=f"{fragment_key}_sort",
            label_visibility="collapsed"
        )
    
    # Map sort selection
    sort_col_map = {
        'KPI Achievement %': 'revenue_achievement',
        'Revenue': 'revenue',
        'Gross Profit': 'gross_profit',
        'GP1': 'gp1',
        'GP %': 'gp_percent',
        'Customers': 'customers'
    }
    sort_col = sort_col_map.get(sort_by, 'revenue')
    
    if sort_col not in ranking_df.columns:
        sort_col = 'revenue'
    
    # Sort descending
    sorted_df = ranking_df.sort_values(sort_col, ascending=False).copy()
    
    # Add rank with medals
    def get_rank_display(rank):
        if rank == 1:
            return "🥇"
        elif rank == 2:
            return "🥈"
        elif rank == 3:
            return "🥉"
        else:
            return f"#{rank}"
    
    sorted_df.insert(0, 'Rank', [get_rank_display(i) for i in range(1, len(sorted_df) + 1)])
    
    # Select display columns
    display_cols = ['Rank', 'kpi_center', 'revenue', 'gross_profit', 'gp1', 'gp_percent', 'customers']
    if show_targets and 'revenue_achievement' in sorted_df.columns:
        display_cols.append('revenue_achievement')
    
    available_cols = [c for c in display_cols if c in sorted_df.columns]
    
    # Column configuration
    column_config = {
        'Rank': st.column_config.TextColumn('Rank', width='small'),
        'kpi_center': st.column_config.TextColumn('KPI Center', width='medium'),
        'revenue': st.column_config.NumberColumn('Revenue', format='$%,.0f'),
        'gross_profit': st.column_config.NumberColumn('Gross Profit', format='$%,.0f'),
        'gp1': st.column_config.NumberColumn('GP1', format='$%,.0f'),
        'gp_percent': st.column_config.NumberColumn('GP %', format='%.1f%%'),
        'customers': st.column_config.NumberColumn('Customers', format='%d'),
    }
    
    if show_targets and 'revenue_achievement' in sorted_df.columns:
        column_config['revenue_achievement'] = st.column_config.ProgressColumn(
            'Achievement %',
            min_value=0,
            max_value=150,
            format='%.1f%%'
        )
    
    st.dataframe(
        sorted_df[available_cols],
        hide_index=True,
        column_config=column_config,
        use_container_width=True
    )
    
    # Footer note
    st.caption(f"⭐ Ranked by **{sort_by}** (highest first)")


# =============================================================================
# TOP PERFORMERS FRAGMENT - kept from v2.3.0
# =============================================================================

@st.fragment
def top_performers_fragment(
    sales_df: pd.DataFrame,
    filter_values: Dict = None,
    metrics_calculator = None,
    fragment_key: str = "kpc_top"
):
    """Top performers / Pareto analysis."""
    if sales_df.empty:
        st.info("No data for analysis")
        return
    
    st.subheader("🏆 Top Performers Analysis")
    
    # Controls
    col1, col2, col3 = st.columns(3)
    
    with col1:
        group_by = st.selectbox(
            "Analyze by",
            ["Customer", "Brand", "Product"],
            key=f"{fragment_key}_group"
        )
    
    with col2:
        metric = st.selectbox(
            "Metric",
            ["Revenue", "Gross Profit", "GP1"],
            key=f"{fragment_key}_metric"
        )
    
    with col3:
        top_percent = st.slider(
            "Show top %",
            min_value=50,
            max_value=100,
            value=80,
            step=5,
            key=f"{fragment_key}_pct"
        )
    
    # Map selections
    group_col_map = {
        "Customer": "customer",
        "Brand": "brand",
        "Product": "product_pn"
    }
    group_col = group_col_map.get(group_by, "customer")
    
    metric_col_map = {
        "Revenue": "sales_by_kpi_center_usd",
        "Gross Profit": "gross_profit_by_kpi_center_usd",
        "GP1": "gp1_by_kpi_center_usd"
    }
    value_col = metric_col_map.get(metric, "sales_by_kpi_center_usd")
    
    # Aggregate
    agg_df = sales_df.groupby(group_col).agg({
        'sales_by_kpi_center_usd': 'sum',
        'gross_profit_by_kpi_center_usd': 'sum',
        'gp1_by_kpi_center_usd': 'sum' if 'gp1_by_kpi_center_usd' in sales_df.columns else 'first',
        'inv_number': pd.Series.nunique
    }).reset_index()
    
    agg_df.columns = [group_col, 'revenue', 'gross_profit', 'gp1', 'orders']
    
    # Sort and calculate cumulative
    metric_lower = metric.lower().replace(' ', '_')
    agg_df = agg_df.sort_values(metric_lower, ascending=False)
    
    total = agg_df[metric_lower].sum()
    if total == 0:
        st.warning("No data to analyze")
        return
    
    agg_df['cumulative'] = agg_df[metric_lower].cumsum()
    agg_df['cumulative_percent'] = (agg_df['cumulative'] / total * 100).round(1)
    agg_df['percent'] = (agg_df[metric_lower] / total * 100).round(1)
    
    # Filter to top percent
    top_data = agg_df[agg_df['cumulative_percent'] <= top_percent].copy()
    if top_data.empty:
        top_data = agg_df.head(1).copy()
    
    # Summary metrics
    st.divider()
    
    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    
    top_count = len(top_data)
    total_count = len(agg_df)
    top_value = top_data[metric_lower].sum()
    concentration = (top_count / total_count * 100) if total_count > 0 else 0
    
    with col_s1:
        st.metric(f"Top {group_by}s", f"{top_count:,}", f"of {total_count:,} total")
    
    with col_s2:
        st.metric(f"Top {top_percent}% {metric}", f"${top_value:,.0f}",
                 f"{(top_value/total*100):.1f}% of total")
    
    with col_s3:
        st.metric("Concentration", f"{concentration:.1f}%")
    
    with col_s4:
        avg_per = top_value / top_count if top_count > 0 else 0
        st.metric(f"Avg per {group_by}", f"${avg_per:,.0f}")
    
    # Chart and table
    chart_col, table_col = st.columns([1.2, 1])
    
    with chart_col:
        chart = KPICenterCharts.build_top_performers_chart(
            data_df=top_data,
            value_col=metric_lower,
            label_col=group_col,
            top_n=min(15, len(top_data)),
            title=f"Top {group_by}s by {metric}"
        )
        st.altair_chart(chart, use_container_width=True)
    
    with table_col:
        display_df = top_data[[group_col, 'revenue', 'gross_profit', 'gp1', 'orders', 'percent', 'cumulative_percent']].copy()
        display_df.insert(0, 'Rank', range(1, len(display_df) + 1))
        
        st.dataframe(
            display_df.head(20),
            hide_index=True,
            column_config={
                'Rank': st.column_config.NumberColumn('🏆', width='small'),
                group_col: group_by,
                'revenue': st.column_config.NumberColumn('Revenue', format='$%,.0f'),
                'gross_profit': st.column_config.NumberColumn('GP', format='$%,.0f'),
                'gp1': st.column_config.NumberColumn('GP1', format='$%,.0f'),
                'orders': 'Orders',
                'percent': st.column_config.NumberColumn('% Share', format='%.1f%%'),
                'cumulative_percent': st.column_config.NumberColumn('Cum %', format='%.1f%%'),
            },
            use_container_width=True
        )


# =============================================================================
# EXPORT REPORT FRAGMENT
# =============================================================================

@st.fragment
def export_report_fragment(
    metrics: Dict,
    complex_kpis: Dict,
    pipeline_metrics: Dict,
    filter_values: Dict,
    yoy_metrics: Dict = None,
    kpi_center_summary_df: pd.DataFrame = None,
    monthly_df: pd.DataFrame = None,
    sales_detail_df: pd.DataFrame = None,
    backlog_summary_df: pd.DataFrame = None,
    backlog_detail_df: pd.DataFrame = None,
    backlog_by_month_df: pd.DataFrame = None
):
    """Excel report generation fragment."""
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
                    metrics=metrics,
                    complex_kpis=complex_kpis,
                    pipeline_metrics=pipeline_metrics,
                    filters=filter_values,
                    yoy_metrics=yoy_metrics,
                    kpi_center_summary_df=kpi_center_summary_df,
                    monthly_df=monthly_df,
                    sales_detail_df=sales_detail_df,
                    backlog_summary_df=backlog_summary_df,
                    backlog_detail_df=backlog_detail_df,
                    backlog_by_month_df=backlog_by_month_df,
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
        st.download_button(
            label="⬇️ Download Excel Report",
            data=st.session_state['kpi_center_export_data'],
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_report_btn"
        )