# utils/salesperson_performance/fragments.py
"""
Streamlit Fragments for Salesperson Performance

Uses @st.fragment to enable partial reruns for filter-heavy sections.
Each fragment only reruns when its internal widgets change,
NOT when sidebar filters or other sections change.

VERSION: 2.3.0 - Added summary metrics to Sales Detail

CHANGELOG:
- v2.3.0: ADDED summary metrics cards to sales_detail_fragment
          - Revenue, GP, GP1, Orders, Customers, Avg Order, Avg GP/Cust
          - Consistent pattern with Backlog List fragment
          - Professional dashboard appearance
- v2.2.0: IMPROVED help text in backlog_list_fragment
          - Consistent English help text for all metrics
          - Clarified scope: "all selected employees" vs KPI-filtered
- v2.1.0: FIXED backlog_list_fragment summary card accuracy
          - Added total_backlog_df parameter for accurate aggregated totals
          - Summary cards now use aggregated data instead of sum from detail
          - Fixes mismatch between Backlog Tab and Overview totals
- v2.0.0: Complete rewrite with 100% code from original file
          - Monthly Trend: Full filters + charts (lines 645-732)
          - YoY Comparison: Full multi-year + single-year logic (lines 742-1122)
          - Sales Detail: Full filters + formatting + export (lines 1611-1881)
          - Pivot Analysis: Full pivot config (lines 1883-1928)
          - Backlog List: Full filters + formatting (lines 1969-2237)
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date
from typing import Dict, List, Optional, Any

from .metrics import SalespersonMetrics
from .charts import SalespersonCharts
from .export import SalespersonExport
from .constants import MONTH_ORDER

from .filters import (
    render_multiselect_filter,
    apply_multiselect_filter,
    render_text_search_filter,
    apply_text_search_filter,
    render_number_filter,
    apply_number_filter,
)


# =============================================================================
# FRAGMENT: MONTHLY TREND SECTION (Tab 1)
# Lines 645-732 from original file - 100% code preserved
# =============================================================================

@st.fragment
def monthly_trend_fragment(
    sales_df: pd.DataFrame,
    targets_df: pd.DataFrame,
    fragment_key: str = "trend"
):
    """
    Fragment for Monthly Trend & Cumulative charts with drill-down filters.
    
    100% code from original file lines 645-732.
    """
    # ==========================================================================
    # MONTHLY TREND + CUMULATIVE - WITH DRILL-DOWN FILTERS
    # ==========================================================================
    col_trend_header, col_trend_help = st.columns([6, 1])
    with col_trend_header:
        st.subheader("📊 Monthly Trend & Cumulative")
    with col_trend_help:
        with st.popover("ℹ️"):
            st.markdown("""
            **Filter by Customer/Brand/Product** to drill-down into specific segments.
            
            Use **Excl** checkbox to exclude selected items instead of filtering to them.
            """)
    
    # --- Drill-down filters ---
    col_tf1, col_tf2, col_tf3 = st.columns(3)
    
    with col_tf1:
        trend_customer_options = sorted(sales_df['customer'].dropna().unique().tolist()) if not sales_df.empty else []
        trend_customer_filter = render_multiselect_filter(
            label="Customer",
            options=trend_customer_options,
            key=f"{fragment_key}_customer",
            placeholder="All customers..."
        )
    
    with col_tf2:
        trend_brand_options = sorted(sales_df['brand'].dropna().unique().tolist()) if not sales_df.empty else []
        trend_brand_filter = render_multiselect_filter(
            label="Brand",
            options=trend_brand_options,
            key=f"{fragment_key}_brand",
            placeholder="All brands..."
        )
    
    with col_tf3:
        trend_product_options = sorted(sales_df['product_pn'].dropna().unique().tolist())[:100] if not sales_df.empty else []
        trend_product_filter = render_multiselect_filter(
            label="Product",
            options=trend_product_options,
            key=f"{fragment_key}_product",
            placeholder="All products..."
        )
    
    # Apply filters to sales data for this section
    trend_sales_df = sales_df.copy() if not sales_df.empty else pd.DataFrame()
    trend_sales_df = apply_multiselect_filter(trend_sales_df, 'customer', trend_customer_filter)
    trend_sales_df = apply_multiselect_filter(trend_sales_df, 'brand', trend_brand_filter)
    trend_sales_df = apply_multiselect_filter(trend_sales_df, 'product_pn', trend_product_filter)
    
    # Show filter summary
    trend_active_filters = []
    if trend_customer_filter.is_active:
        mode = "excl" if trend_customer_filter.excluded else "incl"
        trend_active_filters.append(f"Customer: {len(trend_customer_filter.selected)} ({mode})")
    if trend_brand_filter.is_active:
        mode = "excl" if trend_brand_filter.excluded else "incl"
        trend_active_filters.append(f"Brand: {len(trend_brand_filter.selected)} ({mode})")
    if trend_product_filter.is_active:
        mode = "excl" if trend_product_filter.excluded else "incl"
        trend_active_filters.append(f"Product: {len(trend_product_filter.selected)} ({mode})")
    
    if trend_active_filters:
        st.caption(f"🔍 Filters: {' | '.join(trend_active_filters)}")
    
    # Calculate monthly summary with filtered data
    trend_metrics_calc = SalespersonMetrics(trend_sales_df, targets_df)
    monthly_summary = trend_metrics_calc.prepare_monthly_summary()
    
    # Monthly charts
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("##### 📊 Monthly Trend")
        monthly_chart = SalespersonCharts.build_monthly_trend_chart(
            monthly_df=monthly_summary,
            show_gp1=False,
            title=""
        )
        st.altair_chart(monthly_chart, use_container_width=True)
    
    with col2:
        st.markdown("##### 📈 Cumulative Performance")
        cumulative_chart = SalespersonCharts.build_cumulative_chart(
            monthly_df=monthly_summary,
            title=""
        )
        st.altair_chart(cumulative_chart, use_container_width=True)


# =============================================================================
# FRAGMENT: YOY COMPARISON SECTION (Tab 1)
# Lines 742-1122 from original file - 100% code preserved
# =============================================================================

@st.fragment
def yoy_comparison_fragment(
    sales_df: pd.DataFrame,
    queries,  # SalespersonQueries instance
    filter_values: Dict,
    fragment_key: str = "yoy"
):
    """
    Fragment for Year-over-Year comparison with drill-down filters.
    
    100% code from original file lines 742-1122.
    Includes both multi-year and single-year comparison logic.
    """
    # --- Header with help ---
    col_yc_header, col_yc_help = st.columns([6, 1])
    with col_yc_header:
        st.subheader("📊 Year-over-Year Comparison")
    with col_yc_help:
        with st.popover("ℹ️"):
            st.markdown("""
            **Filter by Customer/Brand/Product** to compare YoY performance for specific segments.
            
            Use **Excl** checkbox to exclude selected items instead of filtering to them.
            """)
    
    # --- Drill-down filters for YoY section ---
    col_yf1, col_yf2, col_yf3 = st.columns(3)
    
    with col_yf1:
        yoy_customer_options = sorted(sales_df['customer'].dropna().unique().tolist()) if not sales_df.empty else []
        yoy_customer_filter = render_multiselect_filter(
            label="Customer",
            options=yoy_customer_options,
            key=f"{fragment_key}_customer",
            placeholder="All customers..."
        )
    
    with col_yf2:
        yoy_brand_options = sorted(sales_df['brand'].dropna().unique().tolist()) if not sales_df.empty else []
        yoy_brand_filter = render_multiselect_filter(
            label="Brand",
            options=yoy_brand_options,
            key=f"{fragment_key}_brand",
            placeholder="All brands..."
        )
    
    with col_yf3:
        yoy_product_options = sorted(sales_df['product_pn'].dropna().unique().tolist())[:100] if not sales_df.empty else []
        yoy_product_filter = render_multiselect_filter(
            label="Product",
            options=yoy_product_options,
            key=f"{fragment_key}_product",
            placeholder="All products..."
        )
    
    # Apply filters to sales data for YoY section
    yoy_sales_df = sales_df.copy() if not sales_df.empty else pd.DataFrame()
    yoy_sales_df = apply_multiselect_filter(yoy_sales_df, 'customer', yoy_customer_filter)
    yoy_sales_df = apply_multiselect_filter(yoy_sales_df, 'brand', yoy_brand_filter)
    yoy_sales_df = apply_multiselect_filter(yoy_sales_df, 'product_pn', yoy_product_filter)
    
    # Show filter summary
    yoy_active_filters = []
    if yoy_customer_filter.is_active:
        mode = "excl" if yoy_customer_filter.excluded else "incl"
        yoy_active_filters.append(f"Customer: {len(yoy_customer_filter.selected)} ({mode})")
    if yoy_brand_filter.is_active:
        mode = "excl" if yoy_brand_filter.excluded else "incl"
        yoy_active_filters.append(f"Brand: {len(yoy_brand_filter.selected)} ({mode})")
    if yoy_product_filter.is_active:
        mode = "excl" if yoy_product_filter.excluded else "incl"
        yoy_active_filters.append(f"Product: {len(yoy_product_filter.selected)} ({mode})")
    
    if yoy_active_filters:
        st.caption(f"🔍 Filters: {' | '.join(yoy_active_filters)}")
    
    # Get years that actually have sales data (not just from date range)
    if not yoy_sales_df.empty and 'invoice_year' in yoy_sales_df.columns:
        actual_years = sorted(yoy_sales_df['invoice_year'].dropna().unique().astype(int).tolist())
    else:
        actual_years = []
    
    # Decide comparison type based on ACTUAL DATA, not date range
    if len(actual_years) >= 2:
        # =====================================================================
        # MULTI-YEAR COMPARISON (2+ years of actual data)
        # =====================================================================
        years_str = ', '.join(map(str, actual_years))
        st.subheader(f"📊 Multi-Year Comparison ({years_str})")
        st.caption(f"ℹ️ Comparing performance across years with actual data in selected date range.")
        
        # Create 3 tabs for each metric
        my_tab1, my_tab2, my_tab3 = st.tabs(["💰 Revenue", "📈 Gross Profit", "📊 GP1"])
        
        # Tab 1: Revenue
        with my_tab1:
            # Summary table
            summary_df = SalespersonCharts.build_multi_year_summary_table(
                sales_df=yoy_sales_df,
                years=actual_years,
                metric='revenue'
            )
            
            if not summary_df.empty:
                # Display yearly totals
                cols = st.columns(len(actual_years) + 1)
                for idx, (_, row) in enumerate(summary_df.iterrows()):
                    with cols[idx]:
                        st.metric(
                            label=f"{int(row['Year'])} Revenue",
                            value=f"${row['Total']:,.0f}",
                            delta=row['YoY Growth'] if row['YoY Growth'] != '-' else None,
                            delta_color="normal" if row['YoY Growth'] != '-' and '+' in str(row['YoY Growth']) else "inverse" if row['YoY Growth'] != '-' else "off"
                        )
            
            st.divider()
            
            # Charts side by side
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                st.markdown("##### 📊 Monthly Revenue by Year")
                monthly_chart = SalespersonCharts.build_multi_year_monthly_chart(
                    sales_df=yoy_sales_df,
                    years=actual_years,
                    metric='revenue',
                    title=""
                )
                st.altair_chart(monthly_chart, use_container_width=True)
            
            with col_c2:
                st.markdown("##### 📈 Cumulative Revenue by Year")
                cum_chart = SalespersonCharts.build_multi_year_cumulative_chart(
                    sales_df=yoy_sales_df,
                    years=actual_years,
                    metric='revenue',
                    title=""
                )
                st.altair_chart(cum_chart, use_container_width=True)
        
        # Tab 2: Gross Profit
        with my_tab2:
            summary_df = SalespersonCharts.build_multi_year_summary_table(
                sales_df=yoy_sales_df,
                years=actual_years,
                metric='gross_profit'
            )
            
            if not summary_df.empty:
                cols = st.columns(len(actual_years) + 1)
                for idx, (_, row) in enumerate(summary_df.iterrows()):
                    with cols[idx]:
                        st.metric(
                            label=f"{int(row['Year'])} GP",
                            value=f"${row['Total']:,.0f}",
                            delta=row['YoY Growth'] if row['YoY Growth'] != '-' else None,
                            delta_color="normal" if row['YoY Growth'] != '-' and '+' in str(row['YoY Growth']) else "inverse" if row['YoY Growth'] != '-' else "off"
                        )
            
            st.divider()
            
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                st.markdown("##### 📊 Monthly Gross Profit by Year")
                monthly_chart = SalespersonCharts.build_multi_year_monthly_chart(
                    sales_df=yoy_sales_df,
                    years=actual_years,
                    metric='gross_profit',
                    title=""
                )
                st.altair_chart(monthly_chart, use_container_width=True)
            
            with col_c2:
                st.markdown("##### 📈 Cumulative Gross Profit by Year")
                cum_chart = SalespersonCharts.build_multi_year_cumulative_chart(
                    sales_df=yoy_sales_df,
                    years=actual_years,
                    metric='gross_profit',
                    title=""
                )
                st.altair_chart(cum_chart, use_container_width=True)
        
        # Tab 3: GP1
        with my_tab3:
            summary_df = SalespersonCharts.build_multi_year_summary_table(
                sales_df=yoy_sales_df,
                years=actual_years,
                metric='gp1'
            )
            
            if not summary_df.empty:
                cols = st.columns(len(actual_years) + 1)
                for idx, (_, row) in enumerate(summary_df.iterrows()):
                    with cols[idx]:
                        st.metric(
                            label=f"{int(row['Year'])} GP1",
                            value=f"${row['Total']:,.0f}",
                            delta=row['YoY Growth'] if row['YoY Growth'] != '-' else None,
                            delta_color="normal" if row['YoY Growth'] != '-' and '+' in str(row['YoY Growth']) else "inverse" if row['YoY Growth'] != '-' else "off"
                        )
            
            st.divider()
            
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                st.markdown("##### 📊 Monthly GP1 by Year")
                monthly_chart = SalespersonCharts.build_multi_year_monthly_chart(
                    sales_df=yoy_sales_df,
                    years=actual_years,
                    metric='gp1',
                    title=""
                )
                st.altair_chart(monthly_chart, use_container_width=True)
            
            with col_c2:
                st.markdown("##### 📈 Cumulative GP1 by Year")
                cum_chart = SalespersonCharts.build_multi_year_cumulative_chart(
                    sales_df=yoy_sales_df,
                    years=actual_years,
                    metric='gp1',
                    title=""
                )
                st.altair_chart(cum_chart, use_container_width=True)
    
    else:
        # =====================================================================
        # YOY COMPARISON (0 or 1 year of actual data)
        # =====================================================================
        
        # Determine primary year for comparison
        if len(actual_years) == 1:
            primary_year = actual_years[0]
        else:
            primary_year = filter_values['end_date'].year
        
        st.markdown(f"##### 📅 {primary_year} vs {primary_year - 1}")
        
        # Load previous year data
        previous_sales_df = queries.get_previous_year_data(
            start_date=filter_values['start_date'],
            end_date=filter_values['end_date'],
            employee_ids=filter_values['employee_ids'],
            entity_ids=filter_values['entity_ids'] if filter_values['entity_ids'] else None
        )
        
        # Apply same filters to previous year data
        if not previous_sales_df.empty:
            previous_sales_df = apply_multiselect_filter(previous_sales_df, 'customer', yoy_customer_filter)
            previous_sales_df = apply_multiselect_filter(previous_sales_df, 'brand', yoy_brand_filter)
            previous_sales_df = apply_multiselect_filter(previous_sales_df, 'product_pn', yoy_product_filter)
        
        if not previous_sales_df.empty:
            # Create 3 tabs for each metric
            yoy_tab1, yoy_tab2, yoy_tab3 = st.tabs(["💰 Revenue", "📈 Gross Profit", "📊 GP1"])
            
            # Tab 1: Revenue
            with yoy_tab1:
                current_total = yoy_sales_df['sales_by_split_usd'].sum() if not yoy_sales_df.empty else 0
                previous_total = previous_sales_df['sales_by_split_usd'].sum() if not previous_sales_df.empty else 0
                yoy_change = ((current_total - previous_total) / previous_total * 100) if previous_total > 0 else 0
                yoy_abs = current_total - previous_total
                
                col_s1, col_s2, col_s3 = st.columns([2, 2, 1])
                with col_s1:
                    st.metric(
                        label=f"{primary_year} Revenue",
                        value=f"${current_total:,.0f}",
                        delta=f"{yoy_change:+.1f}% YoY",
                        delta_color="normal" if yoy_change >= 0 else "inverse"
                    )
                with col_s2:
                    st.metric(
                        label=f"{primary_year - 1} Revenue",
                        value=f"${previous_total:,.0f}",
                        delta=f"${yoy_abs:+,.0f} difference",
                        delta_color="off"
                    )
                
                st.divider()
                
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    st.markdown("##### 📊 Monthly Revenue Comparison")
                    yoy_chart = SalespersonCharts.build_yoy_comparison_chart(
                        current_df=yoy_sales_df,
                        previous_df=previous_sales_df,
                        metric='revenue',
                        title=""
                    )
                    st.altair_chart(yoy_chart, use_container_width=True)
                
                with col_c2:
                    st.markdown("##### 📈 Cumulative Revenue")
                    cum_chart = SalespersonCharts.build_cumulative_yoy_chart(
                        current_df=yoy_sales_df,
                        previous_df=previous_sales_df,
                        metric='revenue',
                        title=""
                    )
                    st.altair_chart(cum_chart, use_container_width=True)
            
            # Tab 2: Gross Profit
            with yoy_tab2:
                current_total = yoy_sales_df['gross_profit_by_split_usd'].sum() if not yoy_sales_df.empty else 0
                previous_total = previous_sales_df['gross_profit_by_split_usd'].sum() if not previous_sales_df.empty else 0
                yoy_change = ((current_total - previous_total) / previous_total * 100) if previous_total > 0 else 0
                yoy_abs = current_total - previous_total
                
                col_s1, col_s2, col_s3 = st.columns([2, 2, 1])
                with col_s1:
                    st.metric(
                        label=f"{primary_year} Gross Profit",
                        value=f"${current_total:,.0f}",
                        delta=f"{yoy_change:+.1f}% YoY",
                        delta_color="normal" if yoy_change >= 0 else "inverse"
                    )
                with col_s2:
                    st.metric(
                        label=f"{primary_year - 1} Gross Profit",
                        value=f"${previous_total:,.0f}",
                        delta=f"${yoy_abs:+,.0f} difference",
                        delta_color="off"
                    )
                
                st.divider()
                
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    st.markdown("##### 📊 Monthly Gross Profit Comparison")
                    yoy_chart = SalespersonCharts.build_yoy_comparison_chart(
                        current_df=yoy_sales_df,
                        previous_df=previous_sales_df,
                        metric='gross_profit',
                        title=""
                    )
                    st.altair_chart(yoy_chart, use_container_width=True)
                
                with col_c2:
                    st.markdown("##### 📈 Cumulative Gross Profit")
                    cum_chart = SalespersonCharts.build_cumulative_yoy_chart(
                        current_df=yoy_sales_df,
                        previous_df=previous_sales_df,
                        metric='gross_profit',
                        title=""
                    )
                    st.altair_chart(cum_chart, use_container_width=True)
            
            # Tab 3: GP1
            with yoy_tab3:
                current_total = yoy_sales_df['gp1_by_split_usd'].sum() if not yoy_sales_df.empty else 0
                previous_total = previous_sales_df['gp1_by_split_usd'].sum() if not previous_sales_df.empty else 0
                yoy_change = ((current_total - previous_total) / previous_total * 100) if previous_total > 0 else 0
                yoy_abs = current_total - previous_total
                
                col_s1, col_s2, col_s3 = st.columns([2, 2, 1])
                with col_s1:
                    st.metric(
                        label=f"{primary_year} GP1",
                        value=f"${current_total:,.0f}",
                        delta=f"{yoy_change:+.1f}% YoY",
                        delta_color="normal" if yoy_change >= 0 else "inverse"
                    )
                with col_s2:
                    st.metric(
                        label=f"{primary_year - 1} GP1",
                        value=f"${previous_total:,.0f}",
                        delta=f"${yoy_abs:+,.0f} difference",
                        delta_color="off"
                    )
                
                st.divider()
                
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    st.markdown("##### 📊 Monthly GP1 Comparison")
                    yoy_chart = SalespersonCharts.build_yoy_comparison_chart(
                        current_df=yoy_sales_df,
                        previous_df=previous_sales_df,
                        metric='gp1',
                        title=""
                    )
                    st.altair_chart(yoy_chart, use_container_width=True)
                
                with col_c2:
                    st.markdown("##### 📈 Cumulative GP1")
                    cum_chart = SalespersonCharts.build_cumulative_yoy_chart(
                        current_df=yoy_sales_df,
                        previous_df=previous_sales_df,
                        metric='gp1',
                        title=""
                    )
                    st.altair_chart(cum_chart, use_container_width=True)
        else:
            st.info(f"No data available for {primary_year - 1} comparison")


# =============================================================================
# FRAGMENT: SALES DETAIL TRANSACTION LIST (Tab 2)
# Lines 1611-1881 from original file - 100% code preserved
# UPDATED v2.3.0: Added summary metrics cards for consistency with Backlog List
# =============================================================================

@st.fragment
def sales_detail_fragment(
    sales_df: pd.DataFrame,
    overview_metrics: Dict,
    filter_values: Dict,
    fragment_key: str = "detail"
):
    """
    Fragment for Sales Detail transaction list with filters.
    
    100% code from original file lines 1611-1881.
    Includes: filters, original value calculation, formatting, export.
    
    UPDATED v2.3.0: Added summary metrics cards at top for consistency.
    """
    if sales_df.empty:
        st.info("No sales data for selected period")
        return
    
    # =================================================================
    # SUMMARY METRICS CARDS (NEW v2.3.0)
    # Consistent with Backlog List pattern
    # =================================================================
    col_s1, col_s2, col_s3, col_s4, col_s5, col_s6, col_s7 = st.columns(7)
    
    total_revenue = sales_df['sales_by_split_usd'].sum()
    total_gp = sales_df['gross_profit_by_split_usd'].sum()
    total_gp1 = sales_df['gp1_by_split_usd'].sum()
    gp_percent = (total_gp / total_revenue * 100) if total_revenue > 0 else 0
    total_invoices = sales_df['inv_number'].nunique()
    total_orders = sales_df['oc_number'].nunique()
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
    # IMPROVED FILTERS - MultiSelect with Excluded option
    # =================================================================
    col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns(5)
    
    # Customer filter
    with col_f1:
        customer_options = sorted(sales_df['customer'].dropna().unique().tolist())
        customer_filter = render_multiselect_filter(
            label="Customer",
            options=customer_options,
            key=f"{fragment_key}_customer",
            placeholder="All customers..."
        )
    
    # Brand filter
    with col_f2:
        brand_options = sorted(sales_df['brand'].dropna().unique().tolist())
        brand_filter = render_multiselect_filter(
            label="Brand",
            options=brand_options,
            key=f"{fragment_key}_brand",
            placeholder="All brands..."
        )
    
    # Product filter
    with col_f3:
        product_options = sorted(sales_df['product_pn'].dropna().unique().tolist())[:100]
        product_filter = render_multiselect_filter(
            label="Product",
            options=product_options,
            key=f"{fragment_key}_product",
            placeholder="All products..."
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
    filtered_df = apply_text_search_filter(
        filtered_df, 
        columns=['oc_number', 'customer_po_number'],
        search_result=oc_po_filter
    )
    
    # Apply number filter
    filtered_df = apply_number_filter(filtered_df, 'sales_by_split_usd', amount_filter)
    
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
    
    # Avoid division by zero
    split_pct = filtered_df['split_rate_percent'].replace(0, 100) / 100
    
    # Calculate original values (before split) - only Revenue and GP
    filtered_df['total_revenue_usd'] = filtered_df['sales_by_split_usd'] / split_pct
    filtered_df['total_gp_usd'] = filtered_df['gross_profit_by_split_usd'] / split_pct
    
    # =================================================================
    # NEW: Format Product as "pt_code | Name | Package size"
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
    # NEW: Format OC with Customer PO
    # Format: OC#\n(PO: xxx)
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
    
    filtered_df['oc_po_display'] = filtered_df.apply(format_oc_po, axis=1)
    
    # Display columns - reordered with new formatted columns
    display_columns = [
        'inv_date', 'inv_number', 'oc_po_display', 'customer', 'product_display', 'brand',
        'total_revenue_usd', 'total_gp_usd',  # Original values (Revenue, GP only)
        'split_rate_percent',
        'sales_by_split_usd', 'gross_profit_by_split_usd', 'gp1_by_split_usd',  # Split values
        'sales_name'
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
            help="💰 ORIGINAL invoice revenue (100% of line item)\n\nThis is the full value BEFORE applying sales split.",
            format="$%.0f"
        ),
        'total_gp_usd': st.column_config.NumberColumn(
            "Total GP",
            help="📈 ORIGINAL gross profit (100% of line item)\n\nFormula: Revenue - COGS\n\nThis is the full GP BEFORE applying sales split.",
            format="$%.0f"
        ),
        # Split percentage
        'split_rate_percent': st.column_config.NumberColumn(
            "Split %",
            help="👥 Sales credit split percentage\n\nThis salesperson receives this % of the total revenue/GP/GP1.\n\n100% = Full credit\n50% = Shared equally with another salesperson",
            format="%.0f%%"
        ),
        # Split values (after split)
        'sales_by_split_usd': st.column_config.NumberColumn(
            "Revenue",
            help="💰 CREDITED revenue for this salesperson\n\n📐 Formula: Total Revenue × Split %\n\nThis is the revenue credited to this salesperson after applying their split percentage.",
            format="$%.0f"
        ),
        'gross_profit_by_split_usd': st.column_config.NumberColumn(
            "GP",
            help="📈 CREDITED gross profit for this salesperson\n\n📐 Formula: Total GP × Split %\n\nThis is the GP credited to this salesperson after applying their split percentage.",
            format="$%.0f"
        ),
        'gp1_by_split_usd': st.column_config.NumberColumn(
            "GP1",
            help="📊 CREDITED GP1 for this salesperson\n\n📐 Formula: (GP - Broker Commission × 1.2) × Split %\n\nGP1 is calculated from GP after deducting commission, then split.",
            format="$%.0f"
        ),
        'sales_name': st.column_config.TextColumn(
            "Salesperson",
            help="Salesperson receiving credit for this transaction"
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
        | **Product** | PT Code \| Name \| Package Size | Formatted product info |
        | **Total Revenue** | Original invoice amount (100%) | Full line item value |
        | **Total GP** | Original gross profit (100%) | Revenue - COGS |
        | **Split %** | Credit allocation to salesperson | Assigned by sales split rules |
        | **Revenue** | Credited revenue | Total Revenue × Split % |
        | **GP** | Credited gross profit | Total GP × Split % |
        | **GP1** | Credited GP1 | (GP - Broker Commission × 1.2) × Split % |
        
        > 💡 **Note:** GP1 is a calculated field (GP minus commission), so there's no "original" GP1 value.
        
        > 💡 **Tip:** Hover over column headers to see detailed tooltips.
        """)
    
    # Export button
    if st.button("📥 Export to Excel", key=f"{fragment_key}_export"):
        exporter = SalespersonExport()
        excel_bytes = exporter.create_report(
            summary_df=pd.DataFrame(),
            monthly_df=pd.DataFrame(),
            metrics=overview_metrics,
            filters=filter_values,
            detail_df=filtered_df
        )
        st.download_button(
            label="⬇️ Download",
            data=excel_bytes,
            file_name=f"sales_detail_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


# =============================================================================
# FRAGMENT: PIVOT ANALYSIS (Tab 2)
# Lines 1883-1928 from original file - 100% code preserved
# =============================================================================

@st.fragment
def pivot_analysis_fragment(
    sales_df: pd.DataFrame,
    fragment_key: str = "pivot"
):
    """
    Fragment for Pivot Analysis with configurable rows/columns/metric.
    
    100% code from original file lines 1883-1928.
    """
    if sales_df.empty:
        st.info("No data for pivot analysis")
        return
    
    st.markdown("#### 📊 Pivot Analysis")
    
    # Pivot configuration
    col_p1, col_p2, col_p3 = st.columns(3)
    
    with col_p1:
        row_options = ['customer', 'brand', 'sales_name', 'product_pn', 'legal_entity']
        pivot_rows = st.selectbox("Rows", row_options, index=0, key=f"{fragment_key}_rows")
    
    with col_p2:
        col_options = ['invoice_month', 'brand', 'customer', 'sales_name']
        pivot_cols = st.selectbox("Columns", col_options, index=0, key=f"{fragment_key}_cols")
    
    with col_p3:
        value_options = ['sales_by_split_usd', 'gross_profit_by_split_usd', 'gp1_by_split_usd']
        pivot_values = st.selectbox("Values", value_options, index=1, key=f"{fragment_key}_values",
                                   format_func=lambda x: x.replace('_by_split_usd', '').replace('_', ' ').title())
    
    # Create pivot
    if pivot_rows in sales_df.columns and pivot_cols in sales_df.columns:
        pivot_df = sales_df.pivot_table(
            values=pivot_values,
            index=pivot_rows,
            columns=pivot_cols,
            aggfunc='sum',
            fill_value=0
        )
        
        # Add totals
        pivot_df['Total'] = pivot_df.sum(axis=1)
        pivot_df = pivot_df.sort_values('Total', ascending=False)
        
        # Reorder columns (months)
        if pivot_cols == 'invoice_month':
            month_cols = [m for m in MONTH_ORDER if m in pivot_df.columns]
            other_cols = [c for c in pivot_df.columns if c not in MONTH_ORDER and c != 'Total']
            pivot_df = pivot_df[month_cols + other_cols + ['Total']]
        
        st.dataframe(
            pivot_df.style.format("${:,.0f}").background_gradient(cmap='Blues', subset=['Total']),
            use_container_width=True,
            height=500
        )
    else:
        st.warning("Selected columns not available in data")


# =============================================================================
# FRAGMENT: BACKLOG LIST (Tab 3)
# Lines 1969-2237 from original file - 100% code preserved
# =============================================================================

@st.fragment
def backlog_list_fragment(
    backlog_df: pd.DataFrame,
    in_period_backlog_analysis: Dict,
    total_backlog_df: pd.DataFrame = None,  # NEW v2.1.0: for accurate totals
    fragment_key: str = "backlog"
):
    """
    Fragment for Backlog List with filters.
    
    100% code from original file lines 1969-2237.
    Includes: summary cards, filters, formatting, display.
    
    UPDATED v2.1.0: Added total_backlog_df parameter
    - When provided, uses aggregated values for summary cards
    - When not provided (backward compat), calculates from backlog_df
    """
    if backlog_df.empty:
        st.info("📦 No backlog data available")
        return
    
    # Summary cards - Combined Total + In-Period + Overdue info
    col_s1, col_s2, col_s3, col_s4, col_s5, col_s6, col_s7 = st.columns(7)
    
    # UPDATED v2.1.0: Use aggregated totals if available, else calculate from detail
    if total_backlog_df is not None and not total_backlog_df.empty:
        # Use aggregated data for accurate totals
        total_backlog_value = total_backlog_df['total_backlog_revenue'].sum()
        total_backlog_gp = total_backlog_df['total_backlog_gp'].sum()
        total_orders = int(total_backlog_df['backlog_orders'].sum()) if 'backlog_orders' in total_backlog_df.columns else backlog_df['oc_number'].nunique()
        total_customers = int(total_backlog_df['backlog_customers'].sum()) if 'backlog_customers' in total_backlog_df.columns else backlog_df['customer_id'].nunique()
    else:
        # Fallback: calculate from detail (may be truncated if LIMIT was used)
        total_backlog_value = backlog_df['backlog_sales_by_split_usd'].sum()
        total_backlog_gp = backlog_df['backlog_gp_by_split_usd'].sum()
        total_orders = backlog_df['oc_number'].nunique()
        total_customers = backlog_df['customer_id'].nunique()
    
    with col_s1:
        st.metric(
            "💰 Total Backlog", 
            f"${total_backlog_value:,.0f}", 
            f"{total_orders:,} orders",
            delta_color="off",
            help="All pending orders from selected employees (not filtered by date)"
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
        in_period_value = in_period_backlog_analysis.get('total_value', 0)
        in_period_count = in_period_backlog_analysis.get('total_count', 0)
        st.metric(
            "📅 In-Period",
            f"${in_period_value:,.0f}",
            f"{in_period_count:,} orders",
            delta_color="off",
            help="Backlog with ETD within selected date range (all selected employees)"
        )
    with col_s4:
        in_period_gp = in_period_backlog_analysis.get('total_gp', 0)
        st.metric(
            "📊 In-Period GP",
            f"${in_period_gp:,.0f}",
            delta_color="off",
            help="Gross profit from in-period backlog"
        )
    with col_s5:
        on_track_value = in_period_backlog_analysis.get('on_track_value', 0)
        on_track_count = in_period_backlog_analysis.get('on_track_count', 0)
        st.metric(
            "✅ On Track",
            f"${on_track_value:,.0f}",
            f"{on_track_count:,} orders",
            delta_color="off",
            help="In-period orders with ETD ≥ today (still on schedule)"
        )
    with col_s6:
        overdue_value = in_period_backlog_analysis.get('overdue_value', 0)
        overdue_count = in_period_backlog_analysis.get('overdue_count', 0)
        st.metric(
            "⚠️ Overdue",
            f"${overdue_value:,.0f}",
            f"{overdue_count:,} orders",
            delta_color="inverse" if overdue_count > 0 else "off",
            help="In-period orders with ETD < today (past due, needs attention)"
        )
    with col_s7:
        status = in_period_backlog_analysis.get('status', 'unknown')
        status_display = "HEALTHY ✅" if status == 'healthy' else "HAS OVERDUE ⚠️"
        st.metric(
            "📊 Status",
            status_display,
            help="HEALTHY = no overdue orders, HAS OVERDUE = some orders past ETD"
        )
    
    st.divider()
    
    # =================================================================
    # IMPROVED FILTERS - MultiSelect with Excluded option
    # =================================================================
    col_bf1, col_bf2, col_bf3, col_bf4, col_bf5 = st.columns(5)
    
    # Customer filter
    with col_bf1:
        bl_customer_options = sorted(backlog_df['customer'].dropna().unique().tolist())
        bl_customer_filter = render_multiselect_filter(
            label="Customer",
            options=bl_customer_options,
            key=f"{fragment_key}_customer",
            placeholder="All customers..."
        )
    
    # Brand filter
    with col_bf2:
        bl_brand_options = sorted(backlog_df['brand'].dropna().unique().tolist())
        bl_brand_filter = render_multiselect_filter(
            label="Brand",
            options=bl_brand_options,
            key=f"{fragment_key}_brand",
            placeholder="All brands..."
        )
    
    # Product filter
    with col_bf3:
        bl_product_options = sorted(backlog_df['product_pn'].dropna().unique().tolist())[:100]
        bl_product_filter = render_multiselect_filter(
            label="Product",
            options=bl_product_options,
            key=f"{fragment_key}_product",
            placeholder="All products..."
        )
    
    # OC# / Customer PO search
    with col_bf4:
        bl_oc_po_filter = render_text_search_filter(
            label="OC# / Customer PO",
            key=f"{fragment_key}_oc_po",
            placeholder="Search..."
        )
    
    # Status filter
    with col_bf5:
        bl_status_options = backlog_df['pending_type'].dropna().unique().tolist()
        bl_status_filter = render_multiselect_filter(
            label="Status",
            options=bl_status_options,
            key=f"{fragment_key}_status",
            placeholder="All statuses..."
        )
    
    # =================================================================
    # APPLY ALL FILTERS
    # =================================================================
    filtered_backlog = backlog_df.copy()
    
    # Apply multiselect filters
    filtered_backlog = apply_multiselect_filter(filtered_backlog, 'customer', bl_customer_filter)
    filtered_backlog = apply_multiselect_filter(filtered_backlog, 'brand', bl_brand_filter)
    filtered_backlog = apply_multiselect_filter(filtered_backlog, 'product_pn', bl_product_filter)
    filtered_backlog = apply_multiselect_filter(filtered_backlog, 'pending_type', bl_status_filter)
    
    # Apply text search on multiple columns
    filtered_backlog = apply_text_search_filter(
        filtered_backlog, 
        columns=['oc_number', 'customer_po_number'] if 'customer_po_number' in backlog_df.columns else ['oc_number'],
        search_result=bl_oc_po_filter
    )
    
    # =================================================================
    # Show filter summary
    # =================================================================
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
    
    # =================================================================
    # NEW: Format Product as "pt_code | Name | Package size"
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
    
    filtered_backlog = filtered_backlog.copy()
    filtered_backlog['product_display'] = filtered_backlog.apply(format_product_display, axis=1)
    
    # =================================================================
    # NEW: Format OC with Customer PO
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
    
    filtered_backlog['oc_po_display'] = filtered_backlog.apply(format_oc_po, axis=1)
    
    st.markdown(f"**Showing {len(filtered_backlog):,} backlog items** (of {len(backlog_df):,} total)")
    
    # Display with column configuration
    backlog_display_cols = ['oc_po_display', 'oc_date', 'etd', 'customer', 'product_display', 'brand',
                           'backlog_sales_by_split_usd', 'backlog_gp_by_split_usd', 
                           'days_until_etd', 'pending_type', 'sales_name']
    available_bl_cols = [c for c in backlog_display_cols if c in filtered_backlog.columns]
    
    display_bl = filtered_backlog[available_bl_cols].head(200).copy()
    
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
        'backlog_sales_by_split_usd': st.column_config.NumberColumn(
            "Amount",
            help="Backlog amount (split-adjusted)",
            format="$%.0f"
        ),
        'backlog_gp_by_split_usd': st.column_config.NumberColumn(
            "GP",
            help="Backlog gross profit (split-adjusted)",
            format="$%.0f"
        ),
        'days_until_etd': st.column_config.NumberColumn(
            "Days to ETD",
            help="Days until ETD (negative = overdue)"
        ),
        'pending_type': st.column_config.TextColumn(
            "Status",
            help="Both Pending / Delivery Pending / Invoice Pending"
        ),
        'sales_name': st.column_config.TextColumn(
            "Salesperson",
            help="Salesperson receiving credit"
        ),
    }
    
    st.dataframe(
        display_bl,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        height=400
    )


# =============================================================================
# EXPORT ALL FRAGMENTS
# =============================================================================

__all__ = [
    'monthly_trend_fragment',
    'yoy_comparison_fragment',
    'sales_detail_fragment',
    'pivot_analysis_fragment',
    'backlog_list_fragment',
]