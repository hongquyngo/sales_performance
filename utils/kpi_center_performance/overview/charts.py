# utils/kpi_center_performance/overview/charts.py
"""
Overview Tab Charts for KPI Center Performance

VERSION: 4.3.0
EXTRACTED FROM: charts.py v3.3.2

Contains:
- render_kpi_cards: Main KPI summary cards with popovers
- build_monthly_trend_dual_chart: Revenue + GP bars with GP% line
- build_cumulative_dual_chart: Cumulative Revenue + GP lines
- build_yoy_comparison_chart: Year-over-Year grouped bars
- build_yoy_cumulative_chart: YoY cumulative lines
- build_monthly_trend_chart: Simple trend (backward compat)
- build_multi_year_monthly_chart: Multi-year grouped bars
- build_multi_year_cumulative_chart: Multi-year cumulative lines
- build_multi_year_summary_table: Multi-year summary DataFrame
"""

import logging
from typing import Dict, Optional, List
import pandas as pd
import altair as alt
import streamlit as st

from ..constants import COLORS, MONTH_ORDER, CHART_WIDTH, CHART_HEIGHT
from ..common.charts import empty_chart

logger = logging.getLogger(__name__)


# =============================================================================
# KPI CARDS - UPDATED v3.3.2
# =============================================================================

def render_kpi_cards(
    metrics: Dict,
    yoy_metrics: Dict = None,
    complex_kpis: Dict = None,
    backlog_metrics: Dict = None,
    overall_achievement: Dict = None,
    show_complex: bool = True,
    show_backlog: bool = True,
    new_customers_df: pd.DataFrame = None,
    new_products_df: pd.DataFrame = None,
    new_business_df: pd.DataFrame = None,
    new_business_detail_df: pd.DataFrame = None
):
    """
    Render KPI summary cards using Streamlit metrics.
    SYNCED with Salesperson page layout.
    """
    # =========================================================================
    # 💰 PERFORMANCE SECTION
    # =========================================================================
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
                help="Total invoiced revenue (split-adjusted). Formula: Σ sales_by_kpi_center_usd"
            )
        
        with col2:
            delta = None
            if yoy_metrics and yoy_metrics.get('total_gp_yoy') is not None:
                delta = f"{yoy_metrics['total_gp_yoy']:+.1f}% YoY"
            st.metric(
                label="Gross Profit",
                value=f"${metrics['total_gp']:,.0f}",
                delta=delta,
                help="Revenue minus COGS (split-adjusted). Formula: Σ gross_profit_by_kpi_center_usd"
            )
        
        with col3:
            delta = None
            if yoy_metrics and yoy_metrics.get('total_gp1_yoy') is not None:
                delta = f"{yoy_metrics['total_gp1_yoy']:+.1f}% YoY"
            st.metric(
                label="GP1",
                value=f"${metrics['total_gp1']:,.0f}",
                delta=delta,
                help="Gross Profit after deducting broker commission (split-adjusted)"
            )
        
        with col4:
            if overall_achievement and overall_achievement.get('overall_achievement') is not None:
                achievement = overall_achievement['overall_achievement']
                delta_color = "normal" if achievement >= 100 else "inverse"
                kpi_count = overall_achievement.get('kpi_count', 0)
                calc_method = overall_achievement.get('calculation_method', '')
                
                # UPDATED v3.3.1: More descriptive delta and help text
                if calc_method == 'target_proportion':
                    delta_text = f"target-weighted avg of {kpi_count} KPIs"
                    help_text = (
                        "**Overall KPI Achievement**\n\n"
                        "Formula: Σ(KPI Achievement × Derived Weight)\n\n"
                        "**Weight Derivation:**\n"
                        "- Currency KPIs (Revenue, GP, New Business): Weight = Target Proportion × 80%\n"
                        "- Count KPIs (New Customers, New Products): Equal split of 20%\n\n"
                        "**Note:** Only actuals from KPI Centers WITH that specific target are included."
                    )
                else:
                    delta_text = f"weighted avg of {kpi_count} KPIs"
                    help_text = "Weighted average of all KPI achievements"
                
                st.metric(
                    label="Overall Achievement",
                    value=f"{achievement:.1f}%",
                    delta=delta_text,
                    delta_color=delta_color,
                    help=help_text
                )
            else:
                st.metric(
                    label="Achievement",
                    value="N/A",
                    delta="No target set",
                    help="No KPI targets assigned for selected KPI Centers"
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
                help="Unique customers served in period"
            )
        
        with col6:
            st.metric(
                label="GP %",
                value=f"{metrics['gp_percent']:.1f}%",
                delta="↑ margin" if metrics.get('gp_percent', 0) > 30 else None,
                delta_color="off",
                help="Gross Profit Margin. Formula: GP / Revenue × 100%"
            )
        
        with col7:
            st.metric(
                label="GP1 %",
                value=f"{metrics['gp1_percent']:.1f}%",
                delta="↑ margin" if metrics.get('gp1_percent', 0) > 25 else None,
                delta_color="off",
                help="GP1 Margin. Formula: GP1 / Revenue × 100%"
            )
        
        with col8:
            st.metric(
                label="Orders",
                value=f"{metrics['total_orders']:,}",
                help="Unique invoices in period"
            )
    
    # =========================================================================
    # 🆕 NEW BUSINESS SECTION - SYNCED v2.6.0 with Salesperson page
    # =========================================================================
    if show_complex and complex_kpis:
        with st.container(border=True):
            # Header with Help button
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
                    - Example: If KPI Center has 50% split on a new customer, they get 0.5 new customer credit
                    
                    **"New" Definitions:**
                    - **New Customer**: Customer has NEVER purchased from the company before (globally, any KPI Center). Credit goes to KPI Center who made the first sale.
                    - **New Product**: Product has NEVER been sold to ANY customer before. Credit goes to KPI Center who introduced it.
                    - **New Business Revenue**: Revenue from first time a specific product is sold to a specific customer.
                    
                    **Lookback Period:** 5 years from period start date
                    
                    **Formula Summary:**
                    - New Customer Count = Σ(split_rate / 100) for each first-time customer
                    - New Product Count = Σ(split_rate / 100) for each first-time product
                    - New Business Revenue = Σ(sales_by_kpi_center_usd) for first customer-product combos
                    """)
            
            col1, col2, col3 = st.columns(3)
            
            # ---------------------------------------------------------
            # NEW CUSTOMERS with Detail Popover - UPDATED v2.7.0
            # ---------------------------------------------------------
            with col1:
                new_customers = complex_kpis.get('num_new_customers', 0)
                
                metric_col, btn_col = st.columns([4, 1])
                
                with metric_col:
                    achievement = complex_kpis.get('new_customer_achievement')
                    delta_str = f"{achievement:.0f}% of target" if achievement else None
                    
                    st.metric(
                        label="New Customers",
                        value=f"{new_customers:.1f}",
                        delta=delta_str,
                        help="Customers with first-ever invoice to COMPANY in period (5-year lookback)."
                    )
                
                with btn_col:
                    if new_customers_df is not None and not new_customers_df.empty:
                        with st.popover("📋"):
                            st.markdown('<div style="min-width:550px"><b>📋 New Customers Detail</b></div>', unsafe_allow_html=True)
                            
                            display_df = new_customers_df.copy()
                            
                            # Check if we need to aggregate (multiple KPI Centers per customer)
                            if 'customer_id' in display_df.columns:
                                aggregated = display_df.groupby('customer_id').agg({
                                    'customer': 'first',
                                    'customer_code': 'first',
                                    'kpi_center': lambda x: ', '.join(sorted(set(str(v) for v in x.dropna()))),
                                    'split_rate_percent': 'max',
                                    'first_sale_date': 'first'
                                }).reset_index()
                                display_df = aggregated
                            
                            st.caption(f"Total: {len(display_df)} unique customers")
                            
                            # Format customer as "Customer Name | Code"
                            if 'customer_code' in display_df.columns and 'customer' in display_df.columns:
                                display_df['customer_display'] = display_df.apply(
                                    lambda row: f"{row['customer']} | {row['customer_code']}" 
                                        if pd.notna(row.get('customer_code')) and row.get('customer_code')
                                        else str(row['customer']),
                                    axis=1
                                )
                                display_df = display_df.drop(columns=['customer', 'customer_code', 'customer_id'], errors='ignore')
                                cols_order = ['customer_display'] + [c for c in display_df.columns if c != 'customer_display']
                                display_df = display_df[cols_order]
                            
                            # Sort by date descending
                            date_col = 'first_sale_date' if 'first_sale_date' in display_df.columns else 'first_invoice_date'
                            if date_col in display_df.columns:
                                display_df = display_df.sort_values(date_col, ascending=False)
                                display_df[date_col] = pd.to_datetime(display_df[date_col]).dt.strftime('%Y-%m-%d')
                            
                            # Split % format
                            if 'split_rate_percent' in display_df.columns:
                                display_df['split_rate_percent'] = display_df['split_rate_percent'].apply(
                                    lambda x: f"{x:.0f}%" if pd.notna(x) else "0%"
                                )
                            
                            # Rename columns
                            col_rename = {
                                'customer_display': 'Customer',
                                'customer': 'Customer',
                                'kpi_center': 'KPI Center',
                                'split_rate_percent': 'Split %',
                                'first_sale_date': 'First Invoice',
                                'first_invoice_date': 'First Invoice'
                            }
                            display_df = display_df.rename(columns=col_rename)
                            
                            st.dataframe(
                                display_df,
                                use_container_width=True,
                                hide_index=True,
                                height=min(400, len(display_df) * 35 + 40)
                            )
                    else:
                        st.caption("")
            
            # ---------------------------------------------------------
            # NEW PRODUCTS with Detail Popover - UPDATED v2.7.0
            # ---------------------------------------------------------
            with col2:
                new_products = complex_kpis.get('num_new_products', 0)
                
                metric_col, btn_col = st.columns([4, 1])
                
                with metric_col:
                    achievement = complex_kpis.get('new_product_achievement')
                    delta_str = f"{achievement:.0f}% of target" if achievement else None
                    
                    st.metric(
                        label="New Products",
                        value=f"{new_products:.1f}",
                        delta=delta_str,
                        help="Products with first-ever sale to ANY customer in period (5-year lookback)."
                    )
                
                with btn_col:
                    if new_products_df is not None and not new_products_df.empty:
                        with st.popover("📋"):
                            st.markdown('<div style="min-width:650px"><b>📋 New Products Detail</b></div>', unsafe_allow_html=True)
                            
                            display_df = new_products_df.copy()
                            
                            # Check if we need to aggregate (multiple KPI Centers per product)
                            if 'product_id' in display_df.columns:
                                agg_dict = {
                                    'kpi_center': lambda x: ', '.join(sorted(set(str(v) for v in x.dropna()))),
                                    'split_rate_percent': 'max',
                                    'first_sale_date': 'first'
                                }
                                if 'product_pn' in display_df.columns:
                                    agg_dict['product_pn'] = 'first'
                                if 'pt_code' in display_df.columns:
                                    agg_dict['pt_code'] = 'first'
                                if 'brand' in display_df.columns:
                                    agg_dict['brand'] = 'first'
                                
                                aggregated = display_df.groupby('product_id').agg(agg_dict).reset_index()
                                display_df = aggregated
                            
                            st.caption(f"Total: {len(display_df)} unique products")
                            
                            # Format product as "pt_code | Name"
                            def format_product(row):
                                parts = []
                                if pd.notna(row.get('pt_code')) and row.get('pt_code'):
                                    parts.append(str(row['pt_code']))
                                if pd.notna(row.get('product_pn')) and row.get('product_pn'):
                                    parts.append(str(row['product_pn']))
                                return ' | '.join(parts) if parts else 'N/A'
                            
                            display_df['product_display'] = display_df.apply(format_product, axis=1)
                            
                            # Select columns for display
                            display_cols = ['product_display', 'brand', 'kpi_center', 'split_rate_percent', 'first_sale_date']
                            available_cols = [c for c in display_cols if c in display_df.columns]
                            
                            if available_cols:
                                display_df = display_df[available_cols].copy()
                                
                                # Sort by date descending
                                if 'first_sale_date' in display_df.columns:
                                    display_df = display_df.sort_values('first_sale_date', ascending=False)
                                    display_df['first_sale_date'] = pd.to_datetime(display_df['first_sale_date']).dt.strftime('%Y-%m-%d')
                                
                                # Split % format
                                if 'split_rate_percent' in display_df.columns:
                                    display_df['split_rate_percent'] = display_df['split_rate_percent'].apply(
                                        lambda x: f"{x:.0f}%" if pd.notna(x) else "0%"
                                    )
                                
                                # Rename columns
                                display_df.columns = ['Product', 'Brand', 'KPI Center', 'Split %', 'First Sale'][:len(display_df.columns)]
                                
                                st.dataframe(
                                    display_df,
                                    use_container_width=True,
                                    hide_index=True,
                                    height=min(400, len(display_df) * 35 + 40)
                                )
                    else:
                        st.caption("")
            
            # ---------------------------------------------------------
            # NEW BUSINESS REVENUE with Detail Popover - SYNCED v2.6.0
            # ---------------------------------------------------------
            with col3:
                new_biz_rev = complex_kpis.get('new_business_revenue', 0)
                
                metric_col, btn_col = st.columns([4, 1])
                
                with metric_col:
                    achievement = complex_kpis.get('new_business_achievement')
                    delta_str = f"{achievement:.0f}% of target" if achievement else None
                    
                    st.metric(
                        label="New Business Revenue",
                        value=f"${new_biz_rev:,.0f}",
                        delta=delta_str,
                        help="Revenue from first-time product-customer combinations (5-year lookback)."
                    )
                
                with btn_col:
                    detail_df = new_business_detail_df if new_business_detail_df is not None else new_business_df
                    
                    if detail_df is not None and not detail_df.empty:
                        with st.popover("📋"):
                            st.markdown('<div style="min-width:800px"><b>📋 New Business Revenue Detail</b></div>', unsafe_allow_html=True)
                            
                            is_detail_data = 'customer' in detail_df.columns
                            
                            if is_detail_data:
                                st.caption(f"New Customer-Product Combos | Total: {len(detail_df)} records")
                                
                                display_df = detail_df.copy()
                                
                                # Format customer as "Customer Name | Code"
                                if 'customer_code' in display_df.columns and 'customer' in display_df.columns:
                                    display_df['customer_display'] = display_df.apply(
                                        lambda row: f"{row['customer']} | {row['customer_code']}" 
                                            if pd.notna(row.get('customer_code')) and row.get('customer_code')
                                            else str(row['customer']),
                                        axis=1
                                    )
                                else:
                                    display_df['customer_display'] = display_df['customer']
                                
                                # Format product as "pt_code | Name"
                                def format_product(row):
                                    parts = []
                                    if pd.notna(row.get('pt_code')) and row.get('pt_code'):
                                        parts.append(str(row['pt_code']))
                                    if pd.notna(row.get('product_pn')) and row.get('product_pn'):
                                        parts.append(str(row['product_pn']))
                                    return ' | '.join(parts) if parts else 'N/A'
                                
                                display_df['product_display'] = display_df.apply(format_product, axis=1)
                                
                                # Select and order columns
                                display_cols = ['customer_display', 'product_display', 'brand', 'kpi_center', 
                                                'split_rate_percent', 'period_revenue', 'period_gp', 'first_sale_date']
                                available_cols = [c for c in display_cols if c in display_df.columns]
                                display_df = display_df[available_cols].copy()
                                
                                # Sort by revenue descending
                                if 'period_revenue' in display_df.columns:
                                    display_df = display_df.sort_values('period_revenue', ascending=False)
                                    display_df['period_revenue'] = display_df['period_revenue'].apply(
                                        lambda x: f"${x:,.0f}" if pd.notna(x) else "$0"
                                    )
                                
                                if 'period_gp' in display_df.columns:
                                    display_df['period_gp'] = display_df['period_gp'].apply(
                                        lambda x: f"${x:,.0f}" if pd.notna(x) else "$0"
                                    )
                                
                                if 'first_sale_date' in display_df.columns:
                                    display_df['first_sale_date'] = pd.to_datetime(display_df['first_sale_date']).dt.strftime('%Y-%m-%d')
                                
                                if 'split_rate_percent' in display_df.columns:
                                    display_df['split_rate_percent'] = display_df['split_rate_percent'].apply(
                                        lambda x: f"{x:.0f}%" if pd.notna(x) else "0%"
                                    )
                                
                                # Rename columns
                                col_rename = {
                                    'customer_display': 'Customer',
                                    'product_display': 'Product',
                                    'brand': 'Brand',
                                    'kpi_center': 'KPI Center',
                                    'split_rate_percent': 'Split %',
                                    'period_revenue': 'Revenue',
                                    'period_gp': 'GP',
                                    'first_sale_date': 'First Sale'
                                }
                                display_df = display_df.rename(columns=col_rename)
                                
                                st.dataframe(
                                    display_df,
                                    use_container_width=True,
                                    hide_index=True,
                                    height=min(400, len(display_df) * 35 + 40)
                                )
                            else:
                                # Fallback: Show aggregated by KPI Center
                                st.caption(f"By KPI Center | Total: {len(detail_df)} records")
                                
                                display_cols = ['kpi_center', 'new_business_revenue', 'new_business_gp', 'num_new_combos']
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
                                    if 'num_new_combos' in display_df.columns:
                                        display_df['num_new_combos'] = display_df['num_new_combos'].apply(
                                            lambda x: f"{int(x):,}" if pd.notna(x) else "0"
                                        )
                                    
                                    display_df.columns = ['KPI Center', 'Revenue', 'Gross Profit', 'New Combos'][:len(display_df.columns)]
                                    
                                    st.dataframe(
                                        display_df,
                                        use_container_width=True,
                                        hide_index=True,
                                        height=min(400, len(display_df) * 35 + 40)
                                    )
                    else:
                        st.caption("")


# =============================================================================
# MONTHLY TREND CHARTS - UPDATED v2.4.0
# =============================================================================

def build_monthly_trend_dual_chart(
    monthly_df: pd.DataFrame,
    show_gp_percent_line: bool = True
) -> alt.Chart:
    """
    Build monthly trend chart with Revenue + GP bars and GP% line.
    SYNCED with Salesperson page.
    """
    if monthly_df.empty:
        return alt.Chart().mark_text().encode(text=alt.value("No data"))
    
    chart_df = monthly_df.copy()
    
    # Ensure month order
    chart_df['month_order'] = chart_df['month'].map(
        {m: i for i, m in enumerate(MONTH_ORDER)}
    )
    chart_df = chart_df.sort_values('month_order')
    
    # Calculate GP% if not present
    if 'gp_percent' not in chart_df.columns:
        chart_df['gp_percent'] = (chart_df['gross_profit'] / chart_df['revenue'] * 100).fillna(0)
    
    # Prepare data for grouped bars
    bar_data = []
    for _, row in chart_df.iterrows():
        bar_data.append({
            'month': row['month'],
            'month_order': row['month_order'],
            'metric': 'Revenue',
            'value': row.get('revenue', 0),
            'gp_percent': row.get('gp_percent', 0)
        })
        bar_data.append({
            'month': row['month'],
            'month_order': row['month_order'],
            'metric': 'Gross Profit',
            'value': row.get('gross_profit', 0),
            'gp_percent': row.get('gp_percent', 0)
        })
    
    bar_df = pd.DataFrame(bar_data)
    
    # Color mapping
    color_scale = alt.Scale(
        domain=['Revenue', 'Gross Profit'],
        range=[COLORS.get('revenue', '#FFA500'), COLORS.get('gross_profit', '#1f77b4')]
    )
    
    # Grouped bars
    bars = alt.Chart(bar_df).mark_bar(
        cornerRadiusTopLeft=2,
        cornerRadiusTopRight=2
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER, title='Month', axis=alt.Axis(labelAngle=0)),
        y=alt.Y('value:Q', title='Amount (USD)', axis=alt.Axis(format='~s')),
        color=alt.Color('metric:N', scale=color_scale, legend=alt.Legend(title='Metric', orient='bottom')),
        xOffset='metric:N',
        tooltip=[
            alt.Tooltip('month:N', title='Month'),
            alt.Tooltip('metric:N', title='Metric'),
            alt.Tooltip('value:Q', title='Amount', format='$,.0f'),
        ]
    )
    
    # Add data labels on bars
    bar_labels = alt.Chart(bar_df).mark_text(
        align='center',
        baseline='bottom',
        dy=-5,
        fontSize=9
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER),
        y=alt.Y('value:Q'),
        xOffset='metric:N',
        text=alt.Text('value:Q', format=',.0f'),
        color=alt.value('#333333')
    )
    
    chart = bars + bar_labels
    
    # Add GP% line if requested
    if show_gp_percent_line:
        line_df = chart_df[['month', 'month_order', 'gp_percent']].copy()
        
        line = alt.Chart(line_df).mark_line(
            color=COLORS.get('gross_profit_percent', '#800080'),
            strokeWidth=2,
            point=alt.OverlayMarkDef(color=COLORS.get('gross_profit_percent', '#800080'), size=40)
        ).encode(
            x=alt.X('month:N', sort=MONTH_ORDER),
            y=alt.Y('gp_percent:Q', title='GP %', axis=alt.Axis(format='.0f')),
            tooltip=[
                alt.Tooltip('month:N', title='Month'),
                alt.Tooltip('gp_percent:Q', title='GP %', format='.1f'),
            ]
        )
        
        # GP% text labels on line points
        line_labels = alt.Chart(line_df).mark_text(
            align='center',
            baseline='bottom',
            dy=-8,
            fontSize=9,
            color=COLORS.get('gross_profit_percent', '#800080')
        ).encode(
            x=alt.X('month:N', sort=MONTH_ORDER),
            y=alt.Y('gp_percent:Q'),
            text=alt.Text('gp_percent:Q', format='.1f')
        )
        
        # Layer with independent y-axes
        chart = alt.layer(bars + bar_labels, line + line_labels).resolve_scale(y='independent')
    
    return chart.properties(
        width='container',
        height=350
    )


def build_cumulative_dual_chart(
    monthly_df: pd.DataFrame
) -> alt.Chart:
    """
    Build cumulative chart with Revenue + GP lines.
    SYNCED with Salesperson page.
    """
    if monthly_df.empty:
        return alt.Chart().mark_text().encode(text=alt.value("No data"))
    
    chart_df = monthly_df.copy()
    
    # Ensure month order
    chart_df['month_order'] = chart_df['month'].map(
        {m: i for i, m in enumerate(MONTH_ORDER)}
    )
    chart_df = chart_df.sort_values('month_order')
    
    # Calculate cumulative
    chart_df['cumulative_revenue'] = chart_df['revenue'].cumsum()
    chart_df['cumulative_gp'] = chart_df['gross_profit'].cumsum()
    
    # Prepare data for lines
    line_data = []
    for _, row in chart_df.iterrows():
        line_data.append({
            'month': row['month'],
            'month_order': row['month_order'],
            'metric': 'Cumulative Revenue',
            'value': row['cumulative_revenue']
        })
        line_data.append({
            'month': row['month'],
            'month_order': row['month_order'],
            'metric': 'Cumulative Gross Profit',
            'value': row['cumulative_gp']
        })
    
    line_df = pd.DataFrame(line_data)
    
    # Color scale
    color_scale = alt.Scale(
        domain=['Cumulative Revenue', 'Cumulative Gross Profit'],
        range=[COLORS.get('revenue', '#FFA500'), COLORS.get('gross_profit', '#1f77b4')]
    )
    
    lines = alt.Chart(line_df).mark_line(
        strokeWidth=2,
        point=alt.OverlayMarkDef(size=50)
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER, title='Month', axis=alt.Axis(labelAngle=0)),
        y=alt.Y('value:Q', title='Cumulative Amount (USD)', axis=alt.Axis(format='~s')),
        color=alt.Color('metric:N', scale=color_scale, legend=alt.Legend(title='Metric', orient='bottom')),
        tooltip=[
            alt.Tooltip('month:N', title='Month'),
            alt.Tooltip('metric:N', title='Metric'),
            alt.Tooltip('value:Q', title='Amount', format='$,.0f'),
        ]
    )
    
    # Add data labels on line points
    labels = alt.Chart(line_df).mark_text(
        align='left',
        baseline='middle',
        dx=5,
        fontSize=9
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER),
        y=alt.Y('value:Q'),
        text=alt.Text('value:Q', format=',.0f'),
        color=alt.Color('metric:N', scale=color_scale, legend=None)
    )
    
    return (lines + labels).properties(
        width='container',
        height=350
    )


# =============================================================================
# YOY COMPARISON CHARTS - UPDATED v2.4.0
# =============================================================================

def build_yoy_comparison_chart(
    current_df: pd.DataFrame,
    previous_df: pd.DataFrame,
    metric: str = "Revenue",
    current_year: int = None,
    previous_year: int = None
) -> alt.Chart:
    """
    Build Year-over-Year comparison chart with grouped bars.
    SYNCED with Salesperson page.
    """
    if current_df.empty and previous_df.empty:
        return alt.Chart().mark_text().encode(text=alt.value("No data"))
    
    metric_col_map = {
        'Revenue': 'revenue',
        'Gross Profit': 'gross_profit',
        'GP1': 'gp1'
    }
    value_col = metric_col_map.get(metric, 'revenue')
    
    # Prepare combined data
    combined_data = []
    
    if not current_df.empty and value_col in current_df.columns:
        curr = current_df[['month', value_col]].copy()
        curr['year'] = f'Current Year' if current_year is None else str(current_year)
        curr['year_type'] = 'Current Year'
        curr['value'] = curr[value_col]
        combined_data.append(curr[['month', 'year', 'year_type', 'value']])
    
    if not previous_df.empty and value_col in previous_df.columns:
        prev = previous_df[['month', value_col]].copy()
        prev['year'] = f'Previous Year' if previous_year is None else str(previous_year)
        prev['year_type'] = 'Previous Year'
        prev['value'] = prev[value_col]
        combined_data.append(prev[['month', 'year', 'year_type', 'value']])
    
    if not combined_data:
        return alt.Chart().mark_text().encode(text=alt.value("No data"))
    
    chart_df = pd.concat(combined_data, ignore_index=True)
    
    # Color scale
    color_scale = alt.Scale(
        domain=['Current Year', 'Previous Year'],
        range=[COLORS.get('current_year', '#1f77b4'), COLORS.get('previous_year', '#aec7e8')]
    )
    
    chart = alt.Chart(chart_df).mark_bar(
        cornerRadiusTopLeft=2,
        cornerRadiusTopRight=2
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER, title='Month', axis=alt.Axis(labelAngle=0)),
        y=alt.Y('value:Q', title=metric, axis=alt.Axis(format='~s')),
        color=alt.Color('year_type:N', scale=color_scale, legend=alt.Legend(title='Year', orient='bottom')),
        xOffset='year_type:N',
        tooltip=[
            alt.Tooltip('month:N', title='Month'),
            alt.Tooltip('year:N', title='Year'),
            alt.Tooltip('value:Q', title=metric, format='$,.0f')
        ]
    )
    
    # Add data labels on bars
    labels = alt.Chart(chart_df).mark_text(
        align='center',
        baseline='bottom',
        dy=-5,
        fontSize=9
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER),
        y=alt.Y('value:Q'),
        xOffset='year_type:N',
        text=alt.Text('value:Q', format=',.0f'),
        color=alt.value('#333333')
    )
    
    return (chart + labels).properties(
        width='container',
        height=350
    )


def build_yoy_cumulative_chart(
    current_df: pd.DataFrame,
    previous_df: pd.DataFrame,
    metric: str = "Revenue",
    current_year: int = None,
    previous_year: int = None
) -> alt.Chart:
    """
    Build YoY cumulative comparison chart.
    SYNCED with Salesperson page.
    """
    if current_df.empty and previous_df.empty:
        return alt.Chart().mark_text().encode(text=alt.value("No data"))
    
    metric_col_map = {
        'Revenue': 'revenue',
        'Gross Profit': 'gross_profit',
        'GP1': 'gp1'
    }
    value_col = metric_col_map.get(metric, 'revenue')
    
    # Prepare data
    line_data = []
    
    if not current_df.empty and value_col in current_df.columns:
        curr = current_df.copy()
        curr['month_order'] = curr['month'].map({m: i for i, m in enumerate(MONTH_ORDER)})
        curr = curr.sort_values('month_order')
        curr['cumulative'] = curr[value_col].cumsum()
        
        for _, row in curr.iterrows():
            line_data.append({
                'month': row['month'],
                'month_order': row['month_order'],
                'year': 'Current Year',
                'value': row['cumulative']
            })
    
    if not previous_df.empty and value_col in previous_df.columns:
        prev = previous_df.copy()
        prev['month_order'] = prev['month'].map({m: i for i, m in enumerate(MONTH_ORDER)})
        prev = prev.sort_values('month_order')
        prev['cumulative'] = prev[value_col].cumsum()
        
        for _, row in prev.iterrows():
            line_data.append({
                'month': row['month'],
                'month_order': row['month_order'],
                'year': 'Previous Year',
                'value': row['cumulative']
            })
    
    if not line_data:
        return alt.Chart().mark_text().encode(text=alt.value("No data"))
    
    chart_df = pd.DataFrame(line_data)
    
    # Color scale
    color_scale = alt.Scale(
        domain=['Current Year', 'Previous Year'],
        range=[COLORS.get('current_year', '#1f77b4'), COLORS.get('previous_year', '#aec7e8')]
    )
    
    chart = alt.Chart(chart_df).mark_line(
        strokeWidth=2,
        point=alt.OverlayMarkDef(size=50)
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER, title='Month', axis=alt.Axis(labelAngle=0)),
        y=alt.Y('value:Q', title=f'Cumulative {metric}', axis=alt.Axis(format='~s')),
        color=alt.Color('year:N', scale=color_scale, legend=alt.Legend(title='Year', orient='bottom')),
        strokeDash=alt.condition(
            alt.datum.year == 'Previous Year',
            alt.value([5, 5]),
            alt.value([0])
        ),
        tooltip=[
            alt.Tooltip('month:N', title='Month'),
            alt.Tooltip('year:N', title='Year'),
            alt.Tooltip('value:Q', title=f'Cumulative {metric}', format='$,.0f')
        ]
    )
    
    # Add data labels on line points
    labels = alt.Chart(chart_df).mark_text(
        align='left',
        baseline='middle',
        dx=5,
        fontSize=9
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER),
        y=alt.Y('value:Q'),
        text=alt.Text('value:Q', format=',.0f'),
        color=alt.Color('year:N', scale=color_scale, legend=None)
    )
    
    return (chart + labels).properties(
        width='container',
        height=350
    )


# =============================================================================
# MONTHLY TREND CHART (Simple version for backward compatibility)
# =============================================================================

def build_monthly_trend_chart(
    monthly_df: pd.DataFrame,
    metric: str = "Revenue",
    show_target: bool = True,
    target_value: float = None
) -> alt.Chart:
    """Build simple monthly trend bar chart with optional target line."""
    if monthly_df.empty:
        return alt.Chart().mark_text().encode(text=alt.value("No data"))
    
    metric_col_map = {'Revenue': 'revenue', 'Gross Profit': 'gross_profit', 'GP1': 'gp1'}
    value_col = metric_col_map.get(metric, 'revenue')
    
    if value_col not in monthly_df.columns:
        return alt.Chart().mark_text().encode(text=alt.value(f"Column {value_col} not found"))
    
    chart_df = monthly_df.copy()
    chart_df['month_order'] = chart_df['month'].map({m: i for i, m in enumerate(MONTH_ORDER)})
    chart_df = chart_df.sort_values('month_order')
    
    bars = alt.Chart(chart_df).mark_bar(
        color=COLORS.get('primary', '#1f77b4'),
        cornerRadiusTopLeft=3,
        cornerRadiusTopRight=3
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER, title='Month'),
        y=alt.Y(f'{value_col}:Q', title=metric),
        tooltip=[
            alt.Tooltip('month:N', title='Month'),
            alt.Tooltip(f'{value_col}:Q', title=metric, format='$,.0f')
        ]
    )
    
    chart = bars
    
    if show_target and target_value and target_value > 0:
        target_df = pd.DataFrame({'target': [target_value]})
        target_line = alt.Chart(target_df).mark_rule(
            color=COLORS.get('target', '#d62728'),
            strokeDash=[5, 5],
            strokeWidth=2
        ).encode(y='target:Q')
        chart = chart + target_line
    
    return chart.properties(width='container', height=300)


# =============================================================================
# MULTI-YEAR COMPARISON CHARTS (NEW v2.5.0)
# =============================================================================

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
    # KPI Center column mapping
    metric_map = {
        'revenue': 'sales_by_kpi_center_usd',
        'gross_profit': 'gross_profit_by_kpi_center_usd',
        'gp1': 'gp1_by_kpi_center_usd'
    }
    
    col = metric_map.get(metric, 'sales_by_kpi_center_usd')
    
    if sales_df.empty:
        return empty_chart("No data available")
    
    # Aggregate by year and month
    df = sales_df.copy()
    
    # Ensure inv_date is datetime
    if 'inv_date' in df.columns:
        df['inv_date'] = pd.to_datetime(df['inv_date'], errors='coerce')
        df['year'] = df['inv_date'].dt.year
    elif 'invoice_year' in df.columns:
        df['year'] = df['invoice_year'].astype(int)
    else:
        return empty_chart("No date column found")
    
    # Ensure invoice_month exists
    if 'invoice_month' not in df.columns:
        df['invoice_month'] = df['inv_date'].dt.strftime('%b')
    
    monthly = df.groupby(['year', 'invoice_month'])[col].sum().reset_index()
    monthly.columns = ['year', 'month', 'amount']
    
    # Filter to selected years
    monthly = monthly[monthly['year'].isin(years)]
    
    if monthly.empty:
        return empty_chart("No data for selected years")
    
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
    # KPI Center column mapping
    metric_map = {
        'revenue': 'sales_by_kpi_center_usd',
        'gross_profit': 'gross_profit_by_kpi_center_usd',
        'gp1': 'gp1_by_kpi_center_usd'
    }
    
    col = metric_map.get(metric, 'sales_by_kpi_center_usd')
    
    if sales_df.empty:
        return empty_chart("No data available")
    
    df = sales_df.copy()
    
    # Ensure inv_date is datetime
    if 'inv_date' in df.columns:
        df['inv_date'] = pd.to_datetime(df['inv_date'], errors='coerce')
        df['year'] = df['inv_date'].dt.year
    elif 'invoice_year' in df.columns:
        df['year'] = df['invoice_year'].astype(int)
    else:
        return empty_chart("No date column found")
    
    # Ensure invoice_month exists
    if 'invoice_month' not in df.columns:
        df['invoice_month'] = df['inv_date'].dt.strftime('%b')
    
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
        return empty_chart("No data for selected years")
    
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
    # KPI Center column mapping
    metric_map = {
        'revenue': 'sales_by_kpi_center_usd',
        'gross_profit': 'gross_profit_by_kpi_center_usd',
        'gp1': 'gp1_by_kpi_center_usd'
    }
    
    col = metric_map.get(metric, 'sales_by_kpi_center_usd')
    
    if sales_df.empty:
        return pd.DataFrame()
    
    df = sales_df.copy()
    
    # Ensure year column exists
    if 'inv_date' in df.columns:
        df['inv_date'] = pd.to_datetime(df['inv_date'], errors='coerce')
        df['year'] = df['inv_date'].dt.year
    elif 'invoice_year' in df.columns:
        df['year'] = df['invoice_year'].astype(int)
    else:
        return pd.DataFrame()
    
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
