# utils/salesperson_performance/charts.py
"""
Altair Chart Builders for Salesperson Performance

All visualization components using Altair:
- KPI summary cards (using st.metric)
- Monthly trend charts (bar + line)
- Cumulative charts
- Achievement comparison charts
- YoY comparison charts
- Top customers/brands Pareto charts

CHANGELOG:
- v1.1.0: Updated NEW BUSINESS section tooltips to reflect correct business logic
          - New Customers: "new to COMPANY" (not "new to salesperson")
          - New Products: "first sale ever to ANY customer"
          - New Business Revenue: "first customer-product combo"
"""

import logging
from typing import Dict, Optional, List
import pandas as pd
import altair as alt
import streamlit as st

from .constants import COLORS, MONTH_ORDER, CHART_WIDTH, CHART_HEIGHT

logger = logging.getLogger(__name__)


class SalespersonCharts:
    """
    Chart builders for salesperson performance dashboard.
    
    All methods are static - can be called without instantiation.
    
    Usage:
        SalespersonCharts.render_kpi_cards(metrics, yoy_metrics, complex_kpis)
        chart = SalespersonCharts.build_monthly_trend_chart(monthly_df)
        st.altair_chart(chart, use_container_width=True)
    """
    
    # =========================================================================
    # KPI CARDS (Using st.metric)
    # =========================================================================
    
    @staticmethod
    def render_kpi_cards(
        metrics: Dict,
        yoy_metrics: Dict = None,
        complex_kpis: Dict = None,
        backlog_metrics: Dict = None,
        overall_achievement: Dict = None,
        show_complex: bool = True,
        show_backlog: bool = True,
        # NEW v1.2.0: Detail dataframes for popup buttons
        new_customers_df: pd.DataFrame = None,
        new_products_df: pd.DataFrame = None,
        new_business_df: pd.DataFrame = None,
        # NEW v1.5.0: Line-by-line new business combo detail
        new_business_detail_df: pd.DataFrame = None
    ):
        """
        Render KPI summary cards using Streamlit metrics with visual grouping.
        
        Layout:
        - 💰 PERFORMANCE: 
          Row 1: Revenue, GP (value), GP1 (value), Overall Achievement
          Row 2: Customers, GP%, GP1%, Orders
        - 📦 PIPELINE & FORECAST: Backlog, In-Period, Forecast, GAP
        - 🆕 NEW BUSINESS: New Customers, New Products, New Business Revenue
        
        Args:
            metrics: Overview metrics dict
            yoy_metrics: YoY comparison metrics (optional)
            complex_kpis: Complex KPI metrics (optional)
            backlog_metrics: Backlog and forecast metrics (optional)
            overall_achievement: Overall weighted KPI achievement (optional)
            show_complex: Whether to show complex KPI section
            show_backlog: Whether to show backlog/forecast section
            new_customers_df: DataFrame with new customer details for popup (optional)
            new_products_df: DataFrame with new product details for popup (optional)
            new_business_df: DataFrame with new business revenue by salesperson (optional)
            new_business_detail_df: DataFrame with new business combo detail (optional, v1.5.0)
        """
        # =====================================================================
        # 💰 PERFORMANCE SECTION
        # =====================================================================
        with st.container(border=True):
            st.markdown("**💰 PERFORMANCE**")
            
            # Row 1: Revenue | GP | GP1 | Overall Achievement
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                delta = None
                if yoy_metrics and yoy_metrics.get('total_revenue_yoy') is not None:
                    delta = f"{yoy_metrics['total_revenue_yoy']:+.1f}% YoY"
                
                st.metric(
                    label="Revenue",
                    value=f"${metrics['total_revenue']:,.0f}",
                    delta=delta,
                    help="Total invoiced revenue (split-adjusted). Formula: Σ sales_by_split_usd"
                )
            
            with col2:
                # GP value with YoY delta
                delta = None
                if yoy_metrics and yoy_metrics.get('total_gp_yoy') is not None:
                    delta = f"{yoy_metrics['total_gp_yoy']:+.1f}% YoY"
                st.metric(
                    label="Gross Profit",
                    value=f"${metrics['total_gp']:,.0f}",
                    delta=delta,
                    help="Revenue minus COGS (split-adjusted). Formula: Σ gross_profit_by_split_usd"
                )
            
            with col3:
                # GP1 value with YoY delta
                delta = None
                if yoy_metrics and yoy_metrics.get('total_gp1_yoy') is not None:
                    delta = f"{yoy_metrics['total_gp1_yoy']:+.1f}% YoY"
                st.metric(
                    label="GP1",
                    value=f"${metrics['total_gp1']:,.0f}",
                    delta=delta,
                    help="Gross Profit after deducting broker commission. Formula: GP - Broker Commission (split-adjusted)"
                )
            
            with col4:
                # Overall KPI Achievement (weighted)
                if overall_achievement and overall_achievement.get('overall_achievement') is not None:
                    achievement = overall_achievement['overall_achievement']
                    delta_color = "normal" if achievement >= 100 else "inverse"
                    kpi_count = overall_achievement.get('kpi_count', 0)
                    st.metric(
                        label="Overall Achievement",
                        value=f"{achievement:.1f}%",
                        delta=f"weighted avg of {kpi_count} KPIs",
                        delta_color=delta_color,
                        help="Weighted average of all KPI achievements. Formula: Σ(KPI_Achievement × Weight) / Σ Weight. Each KPI's target is prorated based on period type."
                    )
                elif metrics.get('revenue_achievement') is not None:
                    # Fallback to revenue achievement if no overall
                    achievement = metrics['revenue_achievement']
                    delta_color = "normal" if achievement >= 100 else "inverse"
                    st.metric(
                        label="Achievement",
                        value=f"{achievement:.1f}%",
                        delta=f"vs ${metrics.get('revenue_target', 0):,.0f} target",
                        delta_color=delta_color,
                        help="Revenue achievement vs prorated target. Formula: Actual Revenue / Prorated Target × 100%"
                    )
                else:
                    st.metric(
                        label="Achievement",
                        value="N/A",
                        delta="No target set",
                        help="No KPI targets assigned for selected salespeople"
                    )
            
            # Row 2: Customers | GP% | GP1% | Orders
            col5, col6, col7, col8 = st.columns(4)
            
            with col5:
                delta = None
                if yoy_metrics and yoy_metrics.get('total_customers_yoy') is not None:
                    delta = f"{yoy_metrics['total_customers_yoy']:+.1f}% YoY"
                
                st.metric(
                    label="Customers",
                    value=f"{metrics['total_customers']:,}",
                    delta=delta,
                    help="Unique customers with invoices in period. Formula: COUNT(DISTINCT customer_id)"
                )
            
            with col6:
                # GP% standalone
                st.metric(
                    label="GP %",
                    value=f"{metrics['gp_percent']:.1f}%",
                    delta="margin",
                    delta_color="off",
                    help="Gross profit margin. Formula: Gross Profit / Revenue × 100%"
                )
            
            with col7:
                # GP1% standalone
                st.metric(
                    label="GP1 %",
                    value=f"{metrics['gp1_percent']:.1f}%",
                    delta="margin",
                    delta_color="off",
                    help="GP1 margin (after broker commission). Formula: GP1 / Revenue × 100%"
                )
            
            with col8:
                st.metric(
                    label="Orders",
                    value=f"{metrics['total_orders']:,}",
                    help="Unique order confirmations in period. Formula: COUNT(DISTINCT oc_number)"
                )
        
        # =====================================================================
        # 📦 PIPELINE & FORECAST SECTION
        # =====================================================================
        if show_backlog and backlog_metrics:
            with st.container(border=True):
                col_header, col_help = st.columns([6, 1])
                with col_header:
                    st.markdown("**📦 PIPELINE & FORECAST**")
                with col_help:
                    with st.popover("ℹ️ Help"):
                        st.markdown("""
                        **📦 Pipeline & Forecast Definitions**
                        
                        | Metric | Formula | Description |
                        |--------|---------|-------------|
                        | Total Backlog | `Σ backlog_sales_by_split_usd` | All outstanding orders not yet invoiced |
                        | In-Period Backlog | `Σ backlog WHERE ETD in period` | Backlog expected to ship within selected period |
                        | Forecast | `Invoiced + In-Period Backlog` | Projected total for the period |
                        | GAP/Surplus | `Forecast - Target` | Difference from prorated target |
                        
                        **Key Concepts:**
                        - **ETD** = Estimated Time of Departure
                        - **Backlog** = Orders confirmed but not yet invoiced
                        - **Target** is prorated: YTD uses `Annual × (elapsed months / 12)`
                        - Positive GAP = Surplus (ahead of target)
                        - Negative GAP = Need more sales to hit target
                        """)
                
                col_b1, col_b2, col_b3, col_b4 = st.columns(4)
                
                with col_b1:
                    st.metric(
                        label="Total Backlog",
                        value=f"${backlog_metrics.get('total_backlog_revenue', 0):,.0f}",
                        delta=f"{backlog_metrics.get('backlog_orders', 0):,} orders",
                        delta_color="off",
                        help="All outstanding orders (split-adjusted). Formula: Σ backlog_sales_by_split_usd from all pending OCs"
                    )
                
                with col_b2:
                    coverage = backlog_metrics.get('backlog_coverage_percent')
                    delta_str = f"{coverage:.0f}% of target" if coverage else None
                    st.metric(
                        label="In-Period Backlog",
                        value=f"${backlog_metrics.get('in_period_backlog_revenue', 0):,.0f}",
                        delta=delta_str,
                        delta_color="off",
                        help="Backlog with ETD within selected period. This is expected to convert to invoiced revenue within the period."
                    )
                
                with col_b3:
                    forecast_revenue = backlog_metrics.get('forecast_revenue')
                    forecast_achievement = backlog_metrics.get('forecast_achievement_revenue')
                    
                    # Handle None for historical periods
                    if forecast_revenue is not None:
                        delta_str = f"{forecast_achievement:.0f}% of target" if forecast_achievement else None
                        delta_color = "normal" if forecast_achievement and forecast_achievement >= 100 else "inverse"
                        st.metric(
                            label="Forecast",
                            value=f"${forecast_revenue:,.0f}",
                            delta=delta_str,
                            delta_color=delta_color if delta_str else "off",
                            help="Projected period total. Formula: Current Invoiced Revenue + In-Period Backlog"
                        )
                    else:
                        # Historical period - forecast not applicable
                        st.metric(
                            label="Forecast",
                            value="N/A",
                            delta="Historical period",
                            delta_color="off",
                            help="Forecast is not available for historical periods (end date is in the past)"
                        )
                
                with col_b4:
                    gap = backlog_metrics.get('gap_revenue')
                    gap_percent = backlog_metrics.get('gap_revenue_percent')
                    
                    if gap is not None:
                        if gap >= 0:
                            gap_label = "Surplus"
                            delta_color = "normal"
                        else:
                            gap_label = "GAP"
                            delta_color = "inverse"
                        
                        delta_str = f"{gap_percent:+.1f}%" if gap_percent else None
                        st.metric(
                            label=gap_label,
                            value=f"${gap:+,.0f}",
                            delta=delta_str,
                            delta_color=delta_color,
                            help="Forecast vs Target difference. Formula: Forecast - Prorated Target. Positive = ahead of target, Negative = behind target"
                        )
                    else:
                        st.metric(
                            label="GAP",
                            value="N/A",
                            delta="No target",
                            delta_color="off"
                        )
        
        # =====================================================================
        # 🆕 NEW BUSINESS SECTION (UPDATED v1.2.0 with Detail Popovers)
        # =====================================================================
        if show_complex and complex_kpis:
            with st.container(border=True):
                col_header, col_help = st.columns([6, 1])
                with col_header:
                    st.markdown("**🆕 NEW BUSINESS**")
                with col_help:
                    with st.popover("ℹ️ Help"):
                        st.markdown("""
                        **🆕 New Business Metrics Definitions**
                        
                        | Metric | Definition | Lookback |
                        |--------|------------|----------|
                        | New Customers | Customers with **first invoice to COMPANY** in period | 5 years |
                        | New Products | Products with **first sale ever** in period | 5 years |
                        | New Business Revenue | Revenue from **first product-customer combo** | 5 years |
                        
                        **Counting Method:**
                        - Values are **proportionally counted** based on split %
                        - Example: If salesperson has 50% split on a new customer, they get 0.5 new customer credit
                        
                        **"New" Definitions:**
                        - **New Customer**: Customer has NEVER purchased from the company before (globally, any salesperson). Credit goes to salesperson who made the first sale.
                        - **New Product**: Product has NEVER been sold to ANY customer before. Credit goes to salesperson who introduced it.
                        - **New Business Revenue**: Revenue from first time a specific product is sold to a specific customer.
                        
                        **Lookback Period:** 5 years from period start date
                        
                        **Formula Summary:**
                        - New Customer Count = Σ(split_rate / 100) for each first-time customer
                        - New Product Count = Σ(split_rate / 100) for each first-time product
                        - New Business Revenue = Σ(sales_by_split_usd) for first customer-product combos
                        """)
                
                col9, col10, col11 = st.columns(3)
                
                # ---------------------------------------------------------
                # NEW CUSTOMERS with Detail Popover
                # ---------------------------------------------------------
                with col9:
                    metric_col, btn_col = st.columns([4, 1])
                    
                    with metric_col:
                        achievement = complex_kpis.get('new_customer_achievement')
                        delta_str = f"{achievement:.0f}% of target" if achievement else None
                        
                        st.metric(
                            label="New Customers",
                            value=f"{complex_kpis['new_customer_count']:.1f}",
                            delta=delta_str,
                            help="Customers with first-ever invoice to COMPANY in period (5-year lookback)."
                        )
                    
                    with btn_col:
                        if new_customers_df is not None and not new_customers_df.empty:
                            with st.popover("📋"):
                                # Force wider container
                                st.markdown('<div style="min-width:550px"><b>📋 New Customers Detail</b></div>', unsafe_allow_html=True)
                                st.caption(f"Total: {len(new_customers_df)} records")
                                
                                display_cols = ['customer', 'sales_name', 'split_rate_percent', 'first_invoice_date']
                                available_cols = [c for c in display_cols if c in new_customers_df.columns]
                                
                                if available_cols:
                                    display_df = new_customers_df[available_cols].copy()
                                    
                                    # Sort by date descending
                                    if 'first_invoice_date' in display_df.columns:
                                        display_df = display_df.sort_values('first_invoice_date', ascending=False)
                                        display_df['first_invoice_date'] = pd.to_datetime(
                                            display_df['first_invoice_date']
                                        ).dt.strftime('%Y-%m-%d')
                                    
                                    # Format Split %
                                    if 'split_rate_percent' in display_df.columns:
                                        display_df['split_rate_percent'] = display_df['split_rate_percent'].apply(
                                            lambda x: f"{x:.0f}%" if pd.notna(x) else "0%"
                                        )
                                    
                                    # Rename columns
                                    display_df.columns = ['Customer', 'Salesperson', 'Split %', 'First Invoice'][:len(display_df.columns)]
                                    
                                    st.dataframe(
                                        display_df,
                                        use_container_width=True,
                                        hide_index=True,
                                        height=min(400, len(display_df) * 35 + 40)
                                    )
                        else:
                            st.caption("")
                
                # ---------------------------------------------------------
                # NEW PRODUCTS with Detail Popover
                # ---------------------------------------------------------
                with col10:
                    metric_col, btn_col = st.columns([4, 1])
                    
                    with metric_col:
                        achievement = complex_kpis.get('new_product_achievement')
                        delta_str = f"{achievement:.0f}% of target" if achievement else None
                        
                        st.metric(
                            label="New Products",
                            value=f"{complex_kpis['new_product_count']:.1f}",
                            delta=delta_str,
                            help="Products with first-ever sale to ANY customer in period (5-year lookback)."
                        )
                    
                    with btn_col:
                        if new_products_df is not None and not new_products_df.empty:
                            with st.popover("📋"):
                                # Force wider container
                                st.markdown('<div style="min-width:650px"><b>📋 New Products Detail</b></div>', unsafe_allow_html=True)
                                st.caption(f"Total: {len(new_products_df)} records")
                                
                                # Create display dataframe with formatted product info
                                display_df = new_products_df.copy()
                                
                                # UPDATED v1.5.0: Format product as "pt_code | Name | Package size"
                                def format_product(row):
                                    parts = []
                                    if pd.notna(row.get('pt_code')) and row.get('pt_code'):
                                        parts.append(str(row['pt_code']))
                                    if pd.notna(row.get('product_pn')) and row.get('product_pn'):
                                        parts.append(str(row['product_pn']))
                                    if pd.notna(row.get('package_size')) and row.get('package_size'):
                                        parts.append(str(row['package_size']))
                                    return ' | '.join(parts) if parts else 'N/A'
                                
                                display_df['product_display'] = display_df.apply(format_product, axis=1)
                                
                                # Select columns for display
                                display_cols = ['product_display', 'brand', 'sales_name', 'split_rate_percent', 'first_sale_date']
                                available_cols = [c for c in display_cols if c in display_df.columns]
                                
                                if available_cols:
                                    display_df = display_df[available_cols].copy()
                                    
                                    # Sort by date descending
                                    if 'first_sale_date' in display_df.columns:
                                        display_df = display_df.sort_values('first_sale_date', ascending=False)
                                        display_df['first_sale_date'] = pd.to_datetime(
                                            display_df['first_sale_date']
                                        ).dt.strftime('%Y-%m-%d')
                                    
                                    # Format Split %
                                    if 'split_rate_percent' in display_df.columns:
                                        display_df['split_rate_percent'] = display_df['split_rate_percent'].apply(
                                            lambda x: f"{x:.0f}%" if pd.notna(x) else "0%"
                                        )
                                    
                                    # Rename columns
                                    display_df.columns = ['Product', 'Brand', 'Salesperson', 'Split %', 'First Sale'][:len(display_df.columns)]
                                    
                                    st.dataframe(
                                        display_df,
                                        use_container_width=True,
                                        hide_index=True,
                                        height=min(400, len(display_df) * 35 + 40)
                                    )
                        else:
                            st.caption("")
                
                # ---------------------------------------------------------
                # NEW BUSINESS REVENUE with Detail Popover
                # UPDATED v1.5.0: Show line-by-line combo detail
                # ---------------------------------------------------------
                with col11:
                    metric_col, btn_col = st.columns([4, 1])
                    
                    with metric_col:
                        achievement = complex_kpis.get('new_business_achievement')
                        delta_str = f"{achievement:.0f}% of target" if achievement else None
                        
                        st.metric(
                            label="New Business Revenue",
                            value=f"${complex_kpis['new_business_revenue']:,.0f}",
                            delta=delta_str,
                            help="Revenue from first-time product-customer combinations (5-year lookback)."
                        )
                    
                    with btn_col:
                        # Prefer detail_df if available, fallback to aggregated df
                        detail_df = new_business_detail_df if new_business_detail_df is not None else new_business_df
                        
                        if detail_df is not None and not detail_df.empty:
                            with st.popover("📋"):
                                # Force wider container for detailed view
                                st.markdown('<div style="min-width:750px"><b>📋 New Business Revenue Detail</b></div>', unsafe_allow_html=True)
                                
                                # Check if this is detailed data (has customer column) or aggregated
                                is_detail_data = 'customer' in detail_df.columns
                                
                                if is_detail_data:
                                    st.caption(f"New Customer-Product Combos | Total: {len(detail_df)} records")
                                    
                                    display_df = detail_df.copy()
                                    
                                    # Format product as "pt_code | Name | Package size"
                                    def format_product(row):
                                        parts = []
                                        if pd.notna(row.get('pt_code')) and row.get('pt_code'):
                                            parts.append(str(row['pt_code']))
                                        if pd.notna(row.get('product_pn')) and row.get('product_pn'):
                                            parts.append(str(row['product_pn']))
                                        if pd.notna(row.get('package_size')) and row.get('package_size'):
                                            parts.append(str(row['package_size']))
                                        return ' | '.join(parts) if parts else 'N/A'
                                    
                                    display_df['product_display'] = display_df.apply(format_product, axis=1)
                                    
                                    # Select and order columns for display
                                    display_cols = ['customer', 'product_display', 'brand', 'sales_name', 
                                                   'split_rate_percent', 'revenue', 'gross_profit', 'first_combo_date']
                                    available_cols = [c for c in display_cols if c in display_df.columns]
                                    display_df = display_df[available_cols].copy()
                                    
                                    # Sort by revenue descending
                                    if 'revenue' in display_df.columns:
                                        display_df = display_df.sort_values('revenue', ascending=False)
                                    
                                    # Format columns
                                    if 'first_combo_date' in display_df.columns:
                                        display_df['first_combo_date'] = pd.to_datetime(
                                            display_df['first_combo_date']
                                        ).dt.strftime('%Y-%m-%d')
                                    
                                    if 'split_rate_percent' in display_df.columns:
                                        display_df['split_rate_percent'] = display_df['split_rate_percent'].apply(
                                            lambda x: f"{x:.0f}%" if pd.notna(x) else "0%"
                                        )
                                    
                                    if 'revenue' in display_df.columns:
                                        display_df['revenue'] = display_df['revenue'].apply(
                                            lambda x: f"${x:,.0f}" if pd.notna(x) else "$0"
                                        )
                                    
                                    if 'gross_profit' in display_df.columns:
                                        display_df['gross_profit'] = display_df['gross_profit'].apply(
                                            lambda x: f"${x:,.0f}" if pd.notna(x) else "$0"
                                        )
                                    
                                    # Rename columns for display
                                    col_rename = {
                                        'customer': 'Customer',
                                        'product_display': 'Product',
                                        'brand': 'Brand',
                                        'sales_name': 'Salesperson',
                                        'split_rate_percent': 'Split %',
                                        'revenue': 'Revenue',
                                        'gross_profit': 'GP',
                                        'first_combo_date': 'First Sale'
                                    }
                                    display_df = display_df.rename(columns=col_rename)
                                    
                                    st.dataframe(
                                        display_df,
                                        use_container_width=True,
                                        hide_index=True,
                                        height=min(400, len(display_df) * 35 + 40)
                                    )
                                else:
                                    # Fallback: Show aggregated by salesperson (backward compatible)
                                    st.caption(f"By Salesperson | Total: {len(detail_df)} records")
                                    
                                    display_cols = ['sales_name', 'new_business_revenue', 'new_business_gp', 'new_combos_count']
                                    available_cols = [c for c in display_cols if c in detail_df.columns]
                                    
                                    if available_cols:
                                        display_df = detail_df[available_cols].copy()
                                        
                                        if 'new_business_revenue' in display_df.columns:
                                            display_df = display_df.sort_values('new_business_revenue', ascending=False)
                                            display_df['new_business_revenue'] = display_df['new_business_revenue'].apply(
                                                lambda x: f"${x:,.0f}" if pd.notna(x) else "$0"
                                            )
                                        if 'new_business_gp' in display_df.columns:
                                            display_df['new_business_gp'] = display_df['new_business_gp'].apply(
                                                lambda x: f"${x:,.0f}" if pd.notna(x) else "$0"
                                            )
                                        if 'new_combos_count' in display_df.columns:
                                            display_df['new_combos_count'] = display_df['new_combos_count'].apply(
                                                lambda x: f"{int(x):,}" if pd.notna(x) else "0"
                                            )
                                        
                                        display_df.columns = ['Salesperson', 'Revenue', 'Gross Profit', 'New Combos'][:len(display_df.columns)]
                                        
                                        st.dataframe(
                                            display_df,
                                            use_container_width=True,
                                            hide_index=True,
                                            height=min(400, len(display_df) * 35 + 40)
                                        )
                        else:
                            st.caption("")
    
    # =========================================================================
    # MONTHLY TREND CHART
    # =========================================================================
    
    @staticmethod
    def build_monthly_trend_chart(
        monthly_df: pd.DataFrame,
        show_gp1: bool = False,
        title: str = "📊 Monthly Revenue, Gross Profit & GP%"
    ) -> alt.Chart:
        """
        Build monthly trend chart with bars (Revenue, GP) and line (GP%).
        
        Args:
            monthly_df: Monthly summary data
            show_gp1: Whether to include GP1 in bars
            title: Chart title
            
        Returns:
            Altair chart
        """
        if monthly_df.empty:
            return SalespersonCharts._empty_chart("No data available")
        
        # Prepare data for bar chart
        value_vars = ['revenue', 'gross_profit']
        if show_gp1:
            value_vars.append('gp1')
        
        bar_data = monthly_df.melt(
            id_vars=['invoice_month'],
            value_vars=value_vars,
            var_name='Metric',
            value_name='Amount'
        )
        
        # Map metric names for display
        metric_map = {
            'revenue': 'Revenue',
            'gross_profit': 'Gross Profit',
            'gp1': 'GP1'
        }
        bar_data['Metric'] = bar_data['Metric'].map(metric_map)
        
        # Color scale
        domain = ['Revenue', 'Gross Profit']
        range_colors = [COLORS['revenue'], COLORS['gross_profit']]
        if show_gp1:
            domain.append('GP1')
            range_colors.append(COLORS['gp1'])
        
        color_scale = alt.Scale(domain=domain, range=range_colors)
        
        # Bar chart
        bars = alt.Chart(bar_data).mark_bar().encode(
            x=alt.X('invoice_month:N', sort=MONTH_ORDER, title='Month'),
            y=alt.Y('Amount:Q', title='Amount (USD)', axis=alt.Axis(format='~s')),
            color=alt.Color('Metric:N', scale=color_scale, legend=alt.Legend(orient='bottom')),
            xOffset='Metric:N',
            tooltip=[
                alt.Tooltip('invoice_month:N', title='Month'),
                alt.Tooltip('Metric:N', title='Metric'),
                alt.Tooltip('Amount:Q', title='Amount', format=',.0f')
            ]
        )
        
        # Value labels on bars
        bar_text = alt.Chart(bar_data).mark_text(
            align='center', baseline='bottom', dy=-5, fontSize=10
        ).encode(
            x=alt.X('invoice_month:N', sort=MONTH_ORDER),
            y=alt.Y('Amount:Q'),
            text=alt.Text('Amount:Q', format=',.0f'),
            xOffset='Metric:N',
            color=alt.value(COLORS['text_dark'])
        )
        
        # GP% line chart
        line = alt.Chart(monthly_df).mark_line(
            point=True,
            color=COLORS['gross_profit_percent'],
            strokeWidth=2
        ).encode(
            x=alt.X('invoice_month:N', sort=MONTH_ORDER),
            y=alt.Y('gp_percent:Q', title='GP %', axis=alt.Axis(format='.0f')),
            tooltip=[
                alt.Tooltip('invoice_month:N', title='Month'),
                alt.Tooltip('gp_percent:Q', title='GP %', format='.2f')
            ]
        )
        
        # GP% text labels
        line_text = alt.Chart(monthly_df).mark_text(
            align='center', baseline='bottom', dy=-8, fontSize=10,
            color=COLORS['gross_profit_percent']
        ).encode(
            x=alt.X('invoice_month:N', sort=MONTH_ORDER),
            y=alt.Y('gp_percent:Q'),
            text=alt.Text('gp_percent:Q', format='.1f')
        )
        
        # Combine with independent Y scales
        chart = alt.layer(bars, bar_text, line, line_text).resolve_scale(
            y='independent'
        ).properties(
            width=CHART_WIDTH,
            height=CHART_HEIGHT,
            title=title
        )
        
        return chart
    
    # =========================================================================
    # CUMULATIVE CHART
    # =========================================================================
    
    @staticmethod
    def build_cumulative_chart(
        monthly_df: pd.DataFrame,
        title: str = "📈 Cumulative Revenue & Gross Profit"
    ) -> alt.Chart:
        """
        Build cumulative revenue and GP chart.
        
        Args:
            monthly_df: Monthly summary with cumulative columns
            title: Chart title
            
        Returns:
            Altair chart
        """
        if monthly_df.empty:
            return SalespersonCharts._empty_chart("No data available")
        
        # Melt for line chart
        cumulative_data = monthly_df.melt(
            id_vars=['invoice_month'],
            value_vars=['cumulative_revenue', 'cumulative_gp'],
            var_name='Metric',
            value_name='Amount'
        )
        
        metric_map = {
            'cumulative_revenue': 'Cumulative Revenue',
            'cumulative_gp': 'Cumulative Gross Profit'
        }
        cumulative_data['Metric'] = cumulative_data['Metric'].map(metric_map)
        
        color_scale = alt.Scale(
            domain=['Cumulative Revenue', 'Cumulative Gross Profit'],
            range=[COLORS['revenue'], COLORS['gross_profit']]
        )
        
        # Line chart
        lines = alt.Chart(cumulative_data).mark_line(point=True, strokeWidth=2).encode(
            x=alt.X('invoice_month:N', sort=MONTH_ORDER, title='Month'),
            y=alt.Y('Amount:Q', title='Cumulative Amount (USD)', axis=alt.Axis(format='~s')),
            color=alt.Color('Metric:N', scale=color_scale, legend=alt.Legend(orient='bottom')),
            tooltip=[
                alt.Tooltip('invoice_month:N', title='Month'),
                alt.Tooltip('Metric:N', title='Metric'),
                alt.Tooltip('Amount:Q', title='Amount', format=',.0f')
            ]
        )
        
        # Value labels
        text = alt.Chart(cumulative_data).mark_text(
            align='center', baseline='bottom', dy=-8, fontSize=10
        ).encode(
            x=alt.X('invoice_month:N', sort=MONTH_ORDER),
            y=alt.Y('Amount:Q'),
            text=alt.Text('Amount:Q', format=',.0f'),
            color=alt.Color('Metric:N', scale=color_scale, legend=None)
        )
        
        chart = alt.layer(lines, text).properties(
            width=CHART_WIDTH,
            height=CHART_HEIGHT,
            title=title
        )
        
        return chart
    
    # =========================================================================
    # ACHIEVEMENT CHART (Actual vs Target)
    # =========================================================================
    
    @staticmethod
    def build_achievement_chart(
        summary_df: pd.DataFrame,
        metric: str = 'revenue',
        title: str = "🎯 Revenue Achievement by Salesperson"
    ) -> alt.Chart:
        """
        Build horizontal bar chart comparing actual vs target.
        
        Args:
            summary_df: Salesperson summary with achievement columns
            metric: 'revenue' or 'gross_profit'
            title: Chart title
            
        Returns:
            Altair chart
        """
        if summary_df.empty:
            return SalespersonCharts._empty_chart("No data available")
        
        # Prepare data
        df = summary_df.copy()
        
        if metric == 'revenue':
            actual_col = 'revenue'
            target_col = 'revenue_target'
            achievement_col = 'revenue_achievement'
        else:
            actual_col = 'gross_profit'
            target_col = 'gp_target'
            achievement_col = 'gp_achievement'
        
        # Ensure columns exist
        if actual_col not in df.columns:
            return SalespersonCharts._empty_chart("Data not available")
        
        df = df.sort_values(actual_col, ascending=True)
        
        # Determine color based on achievement
        if achievement_col in df.columns:
            df['color_flag'] = df[achievement_col] >= 100
        else:
            df['color_flag'] = True
        
        # Bar chart
        bars = alt.Chart(df).mark_bar().encode(
            y=alt.Y('sales_name:N', sort='-x', title=''),
            x=alt.X(f'{actual_col}:Q', title=f'{metric.replace("_", " ").title()} (USD)'),
            color=alt.condition(
                alt.datum.color_flag,
                alt.value(COLORS['achievement_good']),
                alt.value(COLORS['achievement_bad'])
            ),
            tooltip=[
                alt.Tooltip('sales_name:N', title='Salesperson'),
                alt.Tooltip(f'{actual_col}:Q', title='Actual', format=',.0f'),
                alt.Tooltip(f'{target_col}:Q', title='Target', format=',.0f') if target_col in df.columns else alt.value(''),
                alt.Tooltip(f'{achievement_col}:Q', title='Achievement %', format='.1f') if achievement_col in df.columns else alt.value('')
            ]
        )
        
        # Achievement % text
        if achievement_col in df.columns:
            text = alt.Chart(df).mark_text(
                align='left', dx=5, fontSize=11
            ).encode(
                y=alt.Y('sales_name:N', sort='-x'),
                x=alt.X(f'{actual_col}:Q'),
                text=alt.Text(f'{achievement_col}:Q', format='.0f'),
                color=alt.value(COLORS['text_dark'])
            )
            
            chart = alt.layer(bars, text)
        else:
            chart = bars
        
        chart = chart.properties(
            width=CHART_WIDTH,
            height=max(300, len(df) * 30),
            title=title
        )
        
        return chart
    
    # =========================================================================
    # YoY COMPARISON CHART
    # =========================================================================
    
    @staticmethod
    def build_yoy_comparison_chart(
        current_df: pd.DataFrame,
        previous_df: pd.DataFrame,
        metric: str = 'revenue',
        title: str = "📊 Year-over-Year Comparison"
    ) -> alt.Chart:
        """
        Build grouped bar chart comparing current vs previous year.
        
        Args:
            current_df: Current period monthly data
            previous_df: Previous year monthly data
            metric: Column name to compare
            title: Chart title
            
        Returns:
            Altair chart
        """
        metric_map = {
            'revenue': 'sales_by_split_usd',
            'gross_profit': 'gross_profit_by_split_usd',
            'gp1': 'gp1_by_split_usd'
        }
        
        col = metric_map.get(metric, metric)
        
        # Aggregate by month
        def agg_monthly(df, year_label):
            if df.empty:
                return pd.DataFrame()
            
            monthly = df.groupby('invoice_month')[col].sum().reset_index()
            monthly['Year'] = year_label
            monthly.columns = ['invoice_month', 'Amount', 'Year']
            return monthly
        
        current_monthly = agg_monthly(current_df, 'Current Year')
        previous_monthly = agg_monthly(previous_df, 'Previous Year')
        
        combined = pd.concat([current_monthly, previous_monthly], ignore_index=True)
        
        if combined.empty:
            return SalespersonCharts._empty_chart("No data available")
        
        # Chart
        chart = alt.Chart(combined).mark_bar().encode(
            x=alt.X('invoice_month:N', sort=MONTH_ORDER, title='Month'),
            y=alt.Y('Amount:Q', title='Amount (USD)', axis=alt.Axis(format='~s')),
            color=alt.Color('Year:N', scale=alt.Scale(
                domain=['Current Year', 'Previous Year'],
                range=[COLORS['current_year'], COLORS['previous_year']]
            ), legend=alt.Legend(orient='bottom')),
            xOffset='Year:N',
            tooltip=[
                alt.Tooltip('invoice_month:N', title='Month'),
                alt.Tooltip('Year:N', title='Year'),
                alt.Tooltip('Amount:Q', title='Amount', format=',.0f')
            ]
        ).properties(
            width=CHART_WIDTH,
            height=CHART_HEIGHT,
            title=title
        )
        
        return chart
    
    # =========================================================================
    # CUMULATIVE YoY COMPARISON CHART
    # =========================================================================
    
    @staticmethod
    def build_cumulative_yoy_chart(
        current_df: pd.DataFrame,
        previous_df: pd.DataFrame,
        metric: str = 'revenue',
        title: str = "📈 Cumulative YoY Comparison"
    ) -> alt.Chart:
        """
        Build line chart comparing cumulative current vs previous year.
        
        Args:
            current_df: Current period sales data
            previous_df: Previous year sales data
            metric: 'revenue', 'gross_profit', or 'gp1'
            title: Chart title
            
        Returns:
            Altair chart with two lines (Current Year, Previous Year)
        """
        metric_map = {
            'revenue': 'sales_by_split_usd',
            'gross_profit': 'gross_profit_by_split_usd',
            'gp1': 'gp1_by_split_usd'
        }
        
        col = metric_map.get(metric, metric)
        
        def calc_cumulative(df, year_label):
            """Calculate cumulative by month."""
            if df.empty:
                return pd.DataFrame()
            
            # Aggregate by month first
            monthly = df.groupby('invoice_month')[col].sum().reset_index()
            monthly.columns = ['month', 'amount']
            
            # Ensure all months present and in order
            all_months = pd.DataFrame({'month': MONTH_ORDER})
            monthly = all_months.merge(monthly, on='month', how='left').fillna(0)
            
            # Calculate cumulative
            monthly['cumulative'] = monthly['amount'].cumsum()
            monthly['Year'] = year_label
            
            # Add month order for sorting
            monthly['month_order'] = monthly['month'].apply(lambda x: MONTH_ORDER.index(x))
            
            return monthly
        
        current_cum = calc_cumulative(current_df, 'Current Year')
        previous_cum = calc_cumulative(previous_df, 'Previous Year')
        
        combined = pd.concat([current_cum, previous_cum], ignore_index=True)
        
        if combined.empty or combined['cumulative'].sum() == 0:
            return SalespersonCharts._empty_chart("No data available")
        
        # Filter out months with no data for current year (future months)
        current_max_month = current_cum[current_cum['amount'] > 0]['month_order'].max()
        if pd.notna(current_max_month):
            # For current year, only show up to the latest month with data
            current_filtered = current_cum[current_cum['month_order'] <= current_max_month]
            # For previous year, show all months
            combined = pd.concat([current_filtered, previous_cum], ignore_index=True)
        
        # Color scale
        color_scale = alt.Scale(
            domain=['Current Year', 'Previous Year'],
            range=[COLORS['current_year'], COLORS['previous_year']]
        )
        
        # Line chart
        lines = alt.Chart(combined).mark_line(
            point=alt.OverlayMarkDef(size=60),
            strokeWidth=2.5
        ).encode(
            x=alt.X('month:N', sort=MONTH_ORDER, title='Month'),
            y=alt.Y('cumulative:Q', title='Cumulative Amount (USD)', axis=alt.Axis(format='~s')),
            color=alt.Color('Year:N', scale=color_scale, legend=alt.Legend(orient='bottom')),
            strokeDash=alt.condition(
                alt.datum.Year == 'Previous Year',
                alt.value([5, 5]),  # Dashed for previous year
                alt.value([0])      # Solid for current year
            ),
            tooltip=[
                alt.Tooltip('month:N', title='Month'),
                alt.Tooltip('Year:N', title='Year'),
                alt.Tooltip('amount:Q', title='Monthly', format=',.0f'),
                alt.Tooltip('cumulative:Q', title='Cumulative', format=',.0f')
            ]
        )
        
        # Add area fill for visual distinction (subtle)
        area_current = alt.Chart(combined[combined['Year'] == 'Current Year']).mark_area(
            opacity=0.1,
            color=COLORS['current_year']
        ).encode(
            x=alt.X('month:N', sort=MONTH_ORDER),
            y=alt.Y('cumulative:Q')
        )
        
        # Value labels at end points
        last_points_list = []
        for year_label in ['Current Year', 'Previous Year']:
            year_data = combined[combined['Year'] == year_label]
            valid_data = year_data[year_data['cumulative'] > 0]
            if not valid_data.empty:
                last_points_list.append(valid_data.iloc[-1].to_dict())
        
        if last_points_list:
            last_points_df = pd.DataFrame(last_points_list)
            
            text = alt.Chart(last_points_df).mark_text(
                align='left',
                dx=8,
                dy=-5,
                fontSize=11,
                fontWeight='bold'
            ).encode(
                x=alt.X('month:N', sort=MONTH_ORDER),
                y=alt.Y('cumulative:Q'),
                text=alt.Text('cumulative:Q', format=',.0f'),
                color=alt.Color('Year:N', scale=color_scale, legend=None)
            )
            
            chart = alt.layer(area_current, lines, text)
        else:
            chart = alt.layer(area_current, lines)
        
        chart = chart.properties(
            width=CHART_WIDTH,
            height=300,
            title=title
        )
        
        return chart
    
    # =========================================================================
    # TOP CUSTOMERS/BRANDS PARETO CHART
    # =========================================================================
    
    @staticmethod
    def build_top_customers_chart(
        top_df: pd.DataFrame,
        metric: str = 'gross_profit',
        title: str = ""
    ) -> alt.Chart:
        """
        Build Pareto chart (bar + cumulative line) for top customers.
        
        Args:
            top_df: Top customers data from prepare_top_customers_by_metric
            metric: 'revenue', 'gross_profit', or 'gp1'
            title: Chart title (auto-generated if empty)
            
        Returns:
            Altair chart
        """
        if top_df.empty:
            return SalespersonCharts._empty_chart("No data available")
        
        df = top_df.copy()
        
        # Metric display names
        metric_labels = {
            'revenue': 'Revenue',
            'gross_profit': 'Gross Profit',
            'gp1': 'GP1'
        }
        metric_label = metric_labels.get(metric, 'Gross Profit')
        
        # Metric colors
        metric_colors = {
            'revenue': COLORS['revenue'],
            'gross_profit': COLORS['gross_profit'],
            'gp1': COLORS['gp1']
        }
        bar_color = metric_colors.get(metric, COLORS['gross_profit'])
        
        # Auto-generate title if not provided
        if not title:
            title = f"🏆 Top 80% Customers by {metric_label}"
        
        # Check if metric column exists
        if metric not in df.columns:
            return SalespersonCharts._empty_chart(f"No {metric} data available")
        
        # Bar chart
        bars = alt.Chart(df).mark_bar().encode(
            x=alt.X('customer:N', sort='-y', title='Customer'),
            y=alt.Y(f'{metric}:Q', title=f'{metric_label} (USD)', axis=alt.Axis(format='~s')),
            color=alt.value(bar_color),
            tooltip=[
                alt.Tooltip('customer:N', title='Customer'),
                alt.Tooltip(f'{metric}:Q', title=metric_label, format=',.0f'),
                alt.Tooltip('percent_contribution:Q', title='% of Total', format='.2f')
            ]
        )
        
        # Bar text labels
        bar_text = alt.Chart(df).mark_text(
            align='center', baseline='bottom', dy=-5, fontSize=10
        ).encode(
            x=alt.X('customer:N', sort='-y'),
            y=alt.Y(f'{metric}:Q'),
            text=alt.Text(f'{metric}:Q', format=',.0f'),
            color=alt.value(COLORS['text_dark'])
        )
        
        # Cumulative % line
        line = alt.Chart(df).mark_line(
            point=True,
            color=COLORS['gross_profit_percent'],
            strokeWidth=2
        ).encode(
            x=alt.X('customer:N', sort='-y'),
            y=alt.Y('cumulative_percent:Q', title='Cumulative %', axis=alt.Axis(format='.0%')),
            tooltip=[
                alt.Tooltip('customer:N', title='Customer'),
                alt.Tooltip('cumulative_percent:Q', title='Cumulative %', format='.2%')
            ]
        )
        
        # Line text labels
        line_text = alt.Chart(df).mark_text(
            align='center', baseline='bottom', dy=-8, fontSize=10,
            color=COLORS['gross_profit_percent']
        ).encode(
            x=alt.X('customer:N', sort='-y'),
            y=alt.Y('cumulative_percent:Q'),
            text=alt.Text('cumulative_percent:Q', format='.1%')
        )
        
        # Combine with independent scales
        chart = alt.layer(bars, bar_text, line, line_text).resolve_scale(
            y='independent'
        ).properties(
            width=CHART_WIDTH,
            height=CHART_HEIGHT,
            title=title
        )
        
        return chart
    
    @staticmethod
    def build_top_brands_chart(
        top_df: pd.DataFrame,
        metric: str = 'gross_profit',
        title: str = ""
    ) -> alt.Chart:
        """
        Build Pareto chart for top brands.
        
        Args:
            top_df: Top brands data from prepare_top_brands_by_metric
            metric: 'revenue', 'gross_profit', or 'gp1'
            title: Chart title (auto-generated if empty)
        """
        if top_df.empty:
            return SalespersonCharts._empty_chart("No data available")
        
        df = top_df.copy()
        
        # Metric display names
        metric_labels = {
            'revenue': 'Revenue',
            'gross_profit': 'Gross Profit',
            'gp1': 'GP1'
        }
        metric_label = metric_labels.get(metric, 'Gross Profit')
        
        # Metric colors
        metric_colors = {
            'revenue': COLORS['revenue'],
            'gross_profit': COLORS['gross_profit'],
            'gp1': COLORS['gp1']
        }
        bar_color = metric_colors.get(metric, COLORS['gross_profit'])
        
        # Auto-generate title if not provided
        if not title:
            title = f"🏆 Top 80% Brands by {metric_label}"
        
        # Check if metric column exists
        if metric not in df.columns:
            return SalespersonCharts._empty_chart(f"No {metric} data available")
        
        # Bar chart
        bars = alt.Chart(df).mark_bar().encode(
            x=alt.X('brand:N', sort='-y', title='Brand'),
            y=alt.Y(f'{metric}:Q', title=f'{metric_label} (USD)', axis=alt.Axis(format='~s')),
            color=alt.value(bar_color),
            tooltip=[
                alt.Tooltip('brand:N', title='Brand'),
                alt.Tooltip(f'{metric}:Q', title=metric_label, format=',.0f'),
                alt.Tooltip('percent_contribution:Q', title='% of Total', format='.2f')
            ]
        )
        
        bar_text = alt.Chart(df).mark_text(
            align='center', baseline='bottom', dy=-5, fontSize=10
        ).encode(
            x=alt.X('brand:N', sort='-y'),
            y=alt.Y(f'{metric}:Q'),
            text=alt.Text(f'{metric}:Q', format=',.0f'),
            color=alt.value(COLORS['text_dark'])
        )
        
        # Cumulative line
        line = alt.Chart(df).mark_line(
            point=True,
            color=COLORS['gross_profit_percent'],
            strokeWidth=2
        ).encode(
            x=alt.X('brand:N', sort='-y'),
            y=alt.Y('cumulative_percent:Q', title='Cumulative %', axis=alt.Axis(format='.0%')),
            tooltip=[
                alt.Tooltip('brand:N', title='Brand'),
                alt.Tooltip('cumulative_percent:Q', title='Cumulative %', format='.2%')
            ]
        )
        
        line_text = alt.Chart(df).mark_text(
            align='center', baseline='bottom', dy=-8, fontSize=10,
            color=COLORS['gross_profit_percent']
        ).encode(
            x=alt.X('brand:N', sort='-y'),
            y=alt.Y('cumulative_percent:Q'),
            text=alt.Text('cumulative_percent:Q', format='.1%')
        )
        
        chart = alt.layer(bars, bar_text, line, line_text).resolve_scale(
            y='independent'
        ).properties(
            width=CHART_WIDTH,
            height=CHART_HEIGHT,
            title=title
        )
        
        return chart
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    @staticmethod
    def _empty_chart(message: str = "No data available") -> alt.Chart:
        """Create an empty chart with a message."""
        return alt.Chart(pd.DataFrame({'note': [message]})).mark_text(
            text=message,
            fontSize=16,
            color=COLORS['text_light']
        ).properties(
            width=CHART_WIDTH,
            height=200
        )
    
    # =========================================================================
    # BACKLOG & FORECAST CHARTS
    # =========================================================================
    
    @staticmethod
    def build_forecast_waterfall_chart(
        backlog_metrics: Dict,
        metric: str = 'revenue',
        title: str = ""
    ) -> alt.Chart:
        """
        Build a waterfall-style chart showing Invoiced + Backlog = Forecast vs Target.
        
        Args:
            backlog_metrics: Dict with backlog metrics
            metric: 'revenue', 'gp', or 'gp1'
            title: Chart title
            
        Returns:
            Altair chart
        """
        if not backlog_metrics:
            return SalespersonCharts._empty_chart("No backlog data")
        
        # Map metric to keys
        metric_keys = {
            'revenue': {
                'invoiced': 'current_invoiced_revenue',
                'backlog': 'in_period_backlog_revenue',
                'target': 'revenue_target',
                'forecast': 'forecast_revenue',
                'label': 'Revenue'
            },
            'gp': {
                'invoiced': 'current_invoiced_gp',
                'backlog': 'in_period_backlog_gp',
                'target': 'gp_target',
                'forecast': 'forecast_gp',
                'label': 'Gross Profit'
            },
            'gp1': {
                'invoiced': 'current_invoiced_gp1',
                'backlog': 'in_period_backlog_gp1',
                'target': 'gp1_target',
                'forecast': 'forecast_gp1',
                'label': 'GP1'
            }
        }
        
        keys = metric_keys.get(metric, metric_keys['revenue'])
        
        # Get values with fallback
        invoiced = backlog_metrics.get(keys['invoiced'], 0) or 0
        backlog = backlog_metrics.get(keys['backlog'], 0) or 0
        target = backlog_metrics.get(keys['target'], 0) or 0
        forecast = backlog_metrics.get(keys['forecast'], invoiced + backlog) or (invoiced + backlog)
        
        # Auto-generate title if not provided
        if not title:
            title = f"🔮 {keys['label']} Forecast vs Target"
        
        # Prepare data for stacked bar
        data = pd.DataFrame([
            {
                'category': 'Performance',
                'component': '✅ Invoiced',
                'value': invoiced,
                'order': 1
            },
            {
                'category': 'Performance',
                'component': '📅 In-Period Backlog',
                'value': backlog,
                'order': 2
            },
            {
                'category': 'Target',
                'component': '🎯 Target',
                'value': target,
                'order': 1
            }
        ])
        
        # Color scale
        color_scale = alt.Scale(
            domain=['✅ Invoiced', '📅 In-Period Backlog', '🎯 Target'],
            range=[COLORS['gross_profit'], COLORS['new_customer'], COLORS['target']]
        )
        
        # Stacked bar chart
        bars = alt.Chart(data).mark_bar(size=60).encode(
            x=alt.X('category:N', title='', axis=alt.Axis(labelAngle=0)),
            y=alt.Y('value:Q', title='Amount (USD)', axis=alt.Axis(format='~s'), stack='zero'),
            color=alt.Color('component:N', scale=color_scale, legend=alt.Legend(orient='bottom')),
            order=alt.Order('order:Q'),
            tooltip=[
                alt.Tooltip('category:N', title='Category'),
                alt.Tooltip('component:N', title='Component'),
                alt.Tooltip('value:Q', title='Amount', format=',.0f')
            ]
        )
        
        # Add forecast line (use calculated forecast value)
        forecast_line = alt.Chart(pd.DataFrame({'y': [forecast]})).mark_rule(
            color=COLORS['gross_profit_percent'],
            strokeWidth=2,
            strokeDash=[5, 5]
        ).encode(
            y='y:Q'
        )
        
        # Add forecast label
        forecast_text = alt.Chart(pd.DataFrame({
            'x': ['Target'],
            'y': [forecast],
            'label': [f'Forecast: ${forecast:,.0f}']
        })).mark_text(
            align='left',
            dx=35,
            fontSize=12,
            fontWeight='bold',
            color=COLORS['gross_profit_percent']
        ).encode(
            x='x:N',
            y='y:Q',
            text='label:N'
        )
        
        chart = alt.layer(bars, forecast_line, forecast_text).properties(
            width=400,
            height=350,
            title=title
        )
        
        return chart
    
    @staticmethod
    def build_backlog_by_month_chart(
        monthly_df: pd.DataFrame,
        invoiced_monthly_df: pd.DataFrame = None,
        title: str = "📅 Backlog by ETD Month"
    ) -> alt.Chart:
        """
        Build bar chart showing backlog distribution by ETD month.
        Optionally overlay with invoiced data for comparison.
        
        Args:
            monthly_df: Backlog by month data
            invoiced_monthly_df: Optional invoiced by month for comparison
            title: Chart title
            
        Returns:
            Altair chart
        """
        if monthly_df.empty:
            return SalespersonCharts._empty_chart("No backlog data")
        
        df = monthly_df.copy()
        
        # Ensure month column exists
        if 'month' not in df.columns and 'etd_month' in df.columns:
            df = df.rename(columns={'etd_month': 'month'})
        
        # Bar chart for backlog
        bars = alt.Chart(df).mark_bar(color=COLORS['new_customer']).encode(
            x=alt.X('month:N', sort=MONTH_ORDER, title='ETD Month'),
            y=alt.Y('backlog_revenue:Q', title='Backlog (USD)', axis=alt.Axis(format='~s')),
            tooltip=[
                alt.Tooltip('month:N', title='Month'),
                alt.Tooltip('backlog_revenue:Q', title='Backlog', format=',.0f'),
                alt.Tooltip('order_count:Q', title='Orders')
            ]
        )
        
        # Text labels
        text = alt.Chart(df).mark_text(
            align='center',
            baseline='bottom',
            dy=-5,
            fontSize=10,
            color=COLORS['text_dark']
        ).encode(
            x=alt.X('month:N', sort=MONTH_ORDER),
            y=alt.Y('backlog_revenue:Q'),
            text=alt.Text('backlog_revenue:Q', format=',.0f')
        )
        
        chart = alt.layer(bars, text).properties(
            width=CHART_WIDTH,
            height=300,
            title=title
        )
        
        return chart
    
    @staticmethod
    def build_gap_analysis_chart(
        backlog_metrics: Dict,
        metrics_to_show: list = None,
        title: str = "📊 Target vs Forecast Analysis"
    ) -> alt.Chart:
        """
        Build a bullet/progress chart showing current progress, forecast, and target.
        Supports multiple metrics (Revenue, GP, GP1).
        
        Args:
            backlog_metrics: Dict with backlog metrics
            metrics_to_show: List of metrics to show ['revenue', 'gp', 'gp1']. Default: all 3
            title: Chart title
            
        Returns:
            Altair chart
        """
        if not backlog_metrics:
            return SalespersonCharts._empty_chart("No data available")
        
        if metrics_to_show is None:
            metrics_to_show = ['revenue', 'gp', 'gp1']
        
        # Define metric configurations
        metric_configs = {
            'revenue': {
                'target_key': 'revenue_target',
                'invoiced_key': 'current_invoiced_revenue',
                'forecast_key': 'forecast_revenue',
                'label': 'Revenue'
            },
            'gp': {
                'target_key': 'gp_target',
                'invoiced_key': 'current_invoiced_gp',
                'forecast_key': 'forecast_gp',
                'label': 'Gross Profit'
            },
            'gp1': {
                'target_key': 'gp1_target',
                'invoiced_key': 'current_invoiced_gp1',
                'forecast_key': 'forecast_gp1',
                'label': 'GP1'
            }
        }
        
        # Build data for all metrics
        all_data = []
        for metric_name in metrics_to_show:
            if metric_name not in metric_configs:
                continue
            
            config = metric_configs[metric_name]
            target = backlog_metrics.get(config['target_key'], 0) or 0
            invoiced = backlog_metrics.get(config['invoiced_key'], 0) or 0
            forecast = backlog_metrics.get(config['forecast_key'], invoiced) or invoiced
            
            if target == 0:
                continue
            
            invoiced_pct = (invoiced / target) * 100
            forecast_pct = (forecast / target) * 100
            
            all_data.extend([
                {'metric': config['label'], 'type': 'Invoiced', 'value': invoiced, 'percent': invoiced_pct},
                {'metric': config['label'], 'type': 'Forecast', 'value': forecast, 'percent': forecast_pct},
                {'metric': config['label'], 'type': 'Target', 'value': target, 'percent': 100},
            ])
        
        if not all_data:
            return SalespersonCharts._empty_chart("No target set")
        
        data = pd.DataFrame(all_data)
        
        # Base bar (target as background)
        base = alt.Chart(data[data['type'] == 'Target']).mark_bar(
            color='#e0e0e0',
            size=40
        ).encode(
            x=alt.X('value:Q', title='Amount (USD)', axis=alt.Axis(format='~s')),
            y=alt.Y('metric:N', title='', sort=['Revenue', 'Gross Profit', 'GP1'])
        )
        
        # Forecast bar
        forecast_bar = alt.Chart(data[data['type'] == 'Forecast']).mark_bar(
            color=COLORS['new_customer'],
            size=25
        ).encode(
            x=alt.X('value:Q'),
            y=alt.Y('metric:N', sort=['Revenue', 'Gross Profit', 'GP1']),
            tooltip=[
                alt.Tooltip('metric:N', title='Metric'),
                alt.Tooltip('type:N', title='Type'),
                alt.Tooltip('value:Q', title='Amount', format=',.0f'),
                alt.Tooltip('percent:Q', title='% of Target', format='.1f')
            ]
        )
        
        # Invoiced bar (innermost)
        invoiced_bar = alt.Chart(data[data['type'] == 'Invoiced']).mark_bar(
            color=COLORS['gross_profit'],
            size=15
        ).encode(
            x=alt.X('value:Q'),
            y=alt.Y('metric:N', sort=['Revenue', 'Gross Profit', 'GP1']),
            tooltip=[
                alt.Tooltip('metric:N', title='Metric'),
                alt.Tooltip('type:N', title='Type'),
                alt.Tooltip('value:Q', title='Amount', format=',.0f'),
                alt.Tooltip('percent:Q', title='% of Target', format='.1f')
            ]
        )
        
        # Target line
        target_rule = alt.Chart(data[data['type'] == 'Target']).mark_tick(
            color=COLORS['target'],
            thickness=3,
            size=50
        ).encode(
            x=alt.X('value:Q'),
            y=alt.Y('metric:N', sort=['Revenue', 'Gross Profit', 'GP1'])
        )
        
        # Achievement % text at end
        forecast_data = data[data['type'] == 'Forecast'].copy()
        text = alt.Chart(forecast_data).mark_text(
            align='left',
            dx=5,
            fontSize=11,
            fontWeight='bold'
        ).encode(
            x=alt.X('value:Q'),
            y=alt.Y('metric:N', sort=['Revenue', 'Gross Profit', 'GP1']),
            text=alt.Text('percent:Q', format='.0f'),
            color=alt.condition(
                alt.datum.percent >= 100,
                alt.value(COLORS['achievement_good']),
                alt.value(COLORS['achievement_bad'])
            )
        )
        
        num_metrics = len([m for m in metrics_to_show if m in metric_configs])
        chart_height = max(120, num_metrics * 60)
        
        chart = alt.layer(base, forecast_bar, invoiced_bar, target_rule, text).properties(
            width=CHART_WIDTH,
            height=chart_height,
            title=title
        )
        
        return chart
    
    # =========================================================================
    # MULTI-YEAR COMPARISON CHARTS
    # =========================================================================
    
    @staticmethod
    def build_multi_year_monthly_chart(
        sales_df: pd.DataFrame,
        years: List[int],
        metric: str = 'revenue',
        title: str = ""
    ) -> alt.Chart:
        """
        Build grouped bar chart comparing multiple years by month.
        
        Args:
            sales_df: Sales data containing multiple years
            years: List of years to compare [2023, 2024, 2025]
            metric: 'revenue', 'gross_profit', or 'gp1'
            title: Chart title
            
        Returns:
            Altair grouped bar chart
        """
        metric_map = {
            'revenue': 'sales_by_split_usd',
            'gross_profit': 'gross_profit_by_split_usd',
            'gp1': 'gp1_by_split_usd'
        }
        
        col = metric_map.get(metric, 'sales_by_split_usd')
        
        if sales_df.empty:
            return SalespersonCharts._empty_chart("No data available")
        
        # Aggregate by year and month
        df = sales_df.copy()
        df['year'] = pd.to_datetime(df['inv_date']).dt.year
        
        monthly = df.groupby(['year', 'invoice_month'])[col].sum().reset_index()
        monthly.columns = ['year', 'month', 'amount']
        
        # Filter to selected years
        monthly = monthly[monthly['year'].isin(years)]
        
        if monthly.empty:
            return SalespersonCharts._empty_chart("No data for selected years")
        
        # Convert year to string for proper categorical handling
        monthly['year'] = monthly['year'].astype(str)
        
        # Generate color scale for years
        year_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
        color_scale = alt.Scale(
            domain=[str(y) for y in sorted(years)],
            range=year_colors[:len(years)]
        )
        
        # Grouped bar chart
        bars = alt.Chart(monthly).mark_bar().encode(
            x=alt.X('month:N', sort=MONTH_ORDER, title='Month'),
            y=alt.Y('amount:Q', title=f'{metric.replace("_", " ").title()} (USD)', axis=alt.Axis(format='~s')),
            color=alt.Color('year:N', scale=color_scale, title='Year', legend=alt.Legend(orient='bottom')),
            xOffset=alt.XOffset('year:N', sort=[str(y) for y in sorted(years)]),
            tooltip=[
                alt.Tooltip('month:N', title='Month'),
                alt.Tooltip('year:N', title='Year'),
                alt.Tooltip('amount:Q', title='Amount', format=',.0f')
            ]
        )
        
        chart = bars.properties(
            width=CHART_WIDTH,
            height=350,
            title=title if title else f"Monthly {metric.replace('_', ' ').title()} by Year"
        )
        
        return chart
    
    @staticmethod
    def build_multi_year_cumulative_chart(
        sales_df: pd.DataFrame,
        years: List[int],
        metric: str = 'revenue',
        title: str = ""
    ) -> alt.Chart:
        """
        Build cumulative line chart comparing multiple years.
        
        Args:
            sales_df: Sales data containing multiple years
            years: List of years to compare [2023, 2024, 2025]
            metric: 'revenue', 'gross_profit', or 'gp1'
            title: Chart title
            
        Returns:
            Altair line chart with multiple lines (one per year)
        """
        metric_map = {
            'revenue': 'sales_by_split_usd',
            'gross_profit': 'gross_profit_by_split_usd',
            'gp1': 'gp1_by_split_usd'
        }
        
        col = metric_map.get(metric, 'sales_by_split_usd')
        
        if sales_df.empty:
            return SalespersonCharts._empty_chart("No data available")
        
        df = sales_df.copy()
        df['year'] = pd.to_datetime(df['inv_date']).dt.year
        
        # Calculate cumulative for each year
        cumulative_data = []
        
        for year in sorted(years):
            year_df = df[df['year'] == year]
            if year_df.empty:
                continue
            
            # Aggregate by month
            monthly = year_df.groupby('invoice_month')[col].sum().reset_index()
            monthly.columns = ['month', 'amount']
            
            # Ensure all months present
            all_months = pd.DataFrame({'month': MONTH_ORDER})
            monthly = all_months.merge(monthly, on='month', how='left').fillna(0)
            
            # Add month order for sorting
            monthly['month_order'] = monthly['month'].apply(lambda x: MONTH_ORDER.index(x))
            monthly = monthly.sort_values('month_order')
            
            # Calculate cumulative
            monthly['cumulative'] = monthly['amount'].cumsum()
            monthly['year'] = str(year)
            
            # For current/incomplete years, only show months with data
            if monthly['amount'].sum() > 0:
                last_valid_month = monthly[monthly['amount'] > 0]['month_order'].max()
                monthly = monthly[monthly['month_order'] <= last_valid_month]
            
            cumulative_data.append(monthly)
        
        if not cumulative_data:
            return SalespersonCharts._empty_chart("No data for selected years")
        
        combined = pd.concat(cumulative_data, ignore_index=True)
        
        # Generate color scale for years
        year_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
        color_scale = alt.Scale(
            domain=[str(y) for y in sorted(years)],
            range=year_colors[:len(years)]
        )
        
        # Line chart
        lines = alt.Chart(combined).mark_line(
            point=alt.OverlayMarkDef(size=50),
            strokeWidth=2.5
        ).encode(
            x=alt.X('month:N', sort=MONTH_ORDER, title='Month'),
            y=alt.Y('cumulative:Q', title=f'Cumulative {metric.replace("_", " ").title()} (USD)', axis=alt.Axis(format='~s')),
            color=alt.Color('year:N', scale=color_scale, title='Year', legend=alt.Legend(orient='bottom')),
            tooltip=[
                alt.Tooltip('month:N', title='Month'),
                alt.Tooltip('year:N', title='Year'),
                alt.Tooltip('amount:Q', title='Monthly', format=',.0f'),
                alt.Tooltip('cumulative:Q', title='Cumulative', format=',.0f')
            ]
        )
        
        # Add end-point labels
        last_points_list = []
        for year in sorted(years):
            year_data = combined[combined['year'] == str(year)]
            if not year_data.empty and year_data['cumulative'].sum() > 0:
                last_points_list.append(year_data.iloc[-1].to_dict())
        
        if last_points_list:
            last_points_df = pd.DataFrame(last_points_list)
            
            text = alt.Chart(last_points_df).mark_text(
                align='left',
                dx=8,
                dy=-5,
                fontSize=11,
                fontWeight='bold'
            ).encode(
                x=alt.X('month:N', sort=MONTH_ORDER),
                y=alt.Y('cumulative:Q'),
                text=alt.Text('cumulative:Q', format=',.0f'),
                color=alt.Color('year:N', scale=color_scale, legend=None)
            )
            
            chart = alt.layer(lines, text)
        else:
            chart = lines
        
        chart = chart.properties(
            width=CHART_WIDTH,
            height=350,
            title=title if title else f"Cumulative {metric.replace('_', ' ').title()} by Year"
        )
        
        return chart
    
    @staticmethod
    def build_multi_year_summary_table(
        sales_df: pd.DataFrame,
        years: List[int],
        metric: str = 'revenue'
    ) -> pd.DataFrame:
        """
        Build summary table for multi-year comparison.
        
        Args:
            sales_df: Sales data containing multiple years
            years: List of years to compare
            metric: 'revenue', 'gross_profit', or 'gp1'
            
        Returns:
            DataFrame with yearly totals and YoY growth
        """
        metric_map = {
            'revenue': 'sales_by_split_usd',
            'gross_profit': 'gross_profit_by_split_usd',
            'gp1': 'gp1_by_split_usd'
        }
        
        col = metric_map.get(metric, 'sales_by_split_usd')
        
        if sales_df.empty:
            return pd.DataFrame()
        
        df = sales_df.copy()
        df['year'] = pd.to_datetime(df['inv_date']).dt.year
        
        # Aggregate by year
        yearly = df.groupby('year')[col].sum().reset_index()
        yearly.columns = ['Year', 'Total']
        yearly = yearly[yearly['Year'].isin(years)].sort_values('Year')
        
        # Calculate YoY growth
        yearly['YoY Growth'] = yearly['Total'].pct_change() * 100
        yearly['YoY Growth'] = yearly['YoY Growth'].apply(
            lambda x: f"{x:+.1f}%" if pd.notna(x) else "-"
        )
        
        return yearly