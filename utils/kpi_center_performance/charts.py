# utils/kpi_center_performance/charts.py
"""
Altair Chart Builders for KPI Center Performance

VERSION: 2.5.0
CHANGELOG:
- v2.5.0: ADDED Multi-Year Comparison charts (synced with Salesperson page):
          - build_multi_year_monthly_chart(): Grouped bar chart by year
          - build_multi_year_cumulative_chart(): Cumulative lines by year  
          - build_multi_year_summary_table(): Summary table with YoY growth
          - _empty_chart(): Helper for empty state
- v2.4.0: SYNCED UI with Salesperson Performance page:
          - Added build_forecast_waterfall_chart() for Backlog & Forecast
          - Added build_gap_analysis_chart() for Target vs Forecast comparison
          - Added build_monthly_trend_dual_chart() for Revenue + GP bars with GP% line
          - Added build_cumulative_dual_chart() for cumulative performance
          - Added build_yoy_cumulative_chart() for YoY cumulative comparison
          - Updated render_kpi_cards() with wider popover for New Business
          - Removed render_backlog_risk_section() (merged into Backlog & Forecast)
          - Removed render_pipeline_forecast_section() (now inline in main page)
- v2.3.0: Phase 3 - Pareto Analysis charts
- v2.2.0: Added build_achievement_bar_chart()
"""

import logging
from typing import Dict, Optional, List
import pandas as pd
import altair as alt
import streamlit as st

from .constants import COLORS, MONTH_ORDER, CHART_WIDTH, CHART_HEIGHT

logger = logging.getLogger(__name__)


class KPICenterCharts:
    """Chart builders for KPI Center performance dashboard."""
    
    # =========================================================================
    # KPI CARDS - UPDATED v2.4.0: Wider popover for New Business
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
        new_customers_df: pd.DataFrame = None,
        new_products_df: pd.DataFrame = None,
        new_business_df: pd.DataFrame = None,
        new_business_detail_df: pd.DataFrame = None
    ):
        """
        Render KPI summary cards using Streamlit metrics.
        SYNCED with Salesperson page layout.
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
                    st.metric(
                        label="Overall Achievement",
                        value=f"{achievement:.1f}%",
                        delta=f"weighted avg of {kpi_count} KPIs",
                        delta_color=delta_color,
                        help="Weighted average of all KPI achievements"
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
        
        # =====================================================================
        # 🆕 NEW BUSINESS SECTION - UPDATED v2.4.0: Wider popovers
        # =====================================================================
        if show_complex and complex_kpis:
            with st.container(border=True):
                # Header with Help button
                col_header, col_help = st.columns([5, 1])
                with col_header:
                    st.markdown("**🆕 NEW BUSINESS**")
                with col_help:
                    with st.popover("ℹ️ Help"):
                        st.markdown("""
**🆕 New Business KPIs**

| Metric | Definition |
|--------|------------|
| **New Customers** | Customers with first-ever invoice in selected period (5-year lookback) |
| **New Products** | Products with first-ever sale in selected period |
| **New Business Revenue** | Revenue from customer-product combos first sold in period |

Click 📋 button next to each metric to view details.
                        """)
                
                col1, col2, col3 = st.columns(3)
                
                # New Customers with popup - UPDATED: Use 4:1 ratio for wider metric
                with col1:
                    new_customers = complex_kpis.get('num_new_customers', 0)
                    
                    metric_col, btn_col = st.columns([4, 1])
                    
                    with metric_col:
                        st.metric(
                            label="New Customers",
                            value=f"{new_customers:.1f}",
                            help="Customers new to the COMPANY (first invoice within 5-year lookback falls in selected period)"
                        )
                    
                    with btn_col:
                        if new_customers > 0 and new_customers_df is not None and not new_customers_df.empty:
                            with st.popover("📋", help="View details"):
                                st.markdown("**New Customers Detail**")
                                display_cols = ['customer', 'kpi_center', 'first_sale_date', 'first_day_revenue', 'first_day_gp']
                                display_cols = [c for c in display_cols if c in new_customers_df.columns]
                                st.dataframe(
                                    new_customers_df[display_cols].head(50) if display_cols else new_customers_df.head(50),
                                    hide_index=True,
                                    column_config={
                                        'customer': 'Customer',
                                        'kpi_center': 'KPI Center',
                                        'first_sale_date': 'First Sale',
                                        'first_day_revenue': st.column_config.NumberColumn('Revenue', format="$%,.0f"),
                                        'first_day_gp': st.column_config.NumberColumn('GP', format="$%,.0f"),
                                    },
                                    use_container_width=True
                                )
                
                # New Products with popup
                with col2:
                    new_products = complex_kpis.get('num_new_products', 0)
                    
                    metric_col, btn_col = st.columns([4, 1])
                    
                    with metric_col:
                        st.metric(
                            label="New Products",
                            value=f"{new_products:.1f}",
                            help="Products with their first sale ever (to any customer) in selected period"
                        )
                    
                    with btn_col:
                        if new_products > 0 and new_products_df is not None and not new_products_df.empty:
                            with st.popover("📋", help="View details"):
                                st.markdown("**New Products Detail**")
                                display_cols = ['product_pn', 'brand', 'kpi_center', 'first_sale_date', 'first_day_revenue']
                                display_cols = [c for c in display_cols if c in new_products_df.columns]
                                st.dataframe(
                                    new_products_df[display_cols].head(50) if display_cols else new_products_df.head(50),
                                    hide_index=True,
                                    column_config={
                                        'product_pn': 'Product',
                                        'brand': 'Brand',
                                        'kpi_center': 'KPI Center',
                                        'first_sale_date': 'First Sale',
                                        'first_day_revenue': st.column_config.NumberColumn('Revenue', format="$%,.0f"),
                                    },
                                    use_container_width=True
                                )
                
                # New Business Revenue with popup - UPDATED: Wider popover
                with col3:
                    new_biz_rev = complex_kpis.get('new_business_revenue', 0)
                    
                    metric_col, btn_col = st.columns([4, 1])
                    
                    with metric_col:
                        st.metric(
                            label="New Business Revenue",
                            value=f"${new_biz_rev:,.0f}",
                            help="Revenue from customer-product combos first sold in selected period"
                        )
                    
                    with btn_col:
                        if new_biz_rev > 0 and new_business_detail_df is not None and not new_business_detail_df.empty:
                            with st.popover("📋", help="View details"):
                                st.markdown("**New Business Detail (Customer-Product Combos)**")
                                display_cols = ['customer', 'product_pn', 'brand', 'kpi_center', 
                                               'first_sale_date', 'period_revenue', 'period_gp']
                                display_cols = [c for c in display_cols if c in new_business_detail_df.columns]
                                st.dataframe(
                                    new_business_detail_df[display_cols].head(100) if display_cols else new_business_detail_df.head(100),
                                    hide_index=True,
                                    column_config={
                                        'customer': 'Customer',
                                        'product_pn': 'Product',
                                        'brand': 'Brand',
                                        'kpi_center': 'KPI Center',
                                        'first_sale_date': 'First Sale',
                                        'period_revenue': st.column_config.NumberColumn('Period Revenue', format="$%,.0f"),
                                        'period_gp': st.column_config.NumberColumn('Period GP', format="$%,.0f"),
                                    },
                                    use_container_width=True,
                                    height=400
                                )
                                
                                # Summary by KPI Center
                                if new_business_df is not None and not new_business_df.empty:
                                    st.divider()
                                    st.markdown("**Summary by KPI Center**")
                                    summary_cols = ['kpi_center', 'num_new_combos', 'new_business_revenue', 'new_business_gp']
                                    summary_cols = [c for c in summary_cols if c in new_business_df.columns]
                                    st.dataframe(
                                        new_business_df[summary_cols] if summary_cols else new_business_df,
                                        hide_index=True,
                                        column_config={
                                            'kpi_center': 'KPI Center',
                                            'num_new_combos': 'New Combos',
                                            'new_business_revenue': st.column_config.NumberColumn('Revenue', format="$%,.0f"),
                                            'new_business_gp': st.column_config.NumberColumn('GP', format="$%,.0f"),
                                        },
                                        use_container_width=True
                                    )
    
    # =========================================================================
    # BACKLOG & FORECAST CHARTS - NEW v2.4.0
    # =========================================================================
    
    @staticmethod
    def build_forecast_waterfall_chart(
        backlog_metrics: Dict,
        metric: str = 'revenue',
        title: str = ""
    ) -> alt.Chart:
        """
        Build a waterfall-style chart showing Invoiced + Backlog = Forecast vs Target.
        SYNCED with Salesperson page.
        """
        if not backlog_metrics:
            return alt.Chart().mark_text().encode(text=alt.value("No backlog data"))
        
        # Map metric to keys - use same structure as Salesperson
        metric_keys = {
            'revenue': {
                'invoiced': 'invoiced_revenue',
                'backlog': 'in_period_backlog_revenue',
                'target': 'target_revenue',
                'forecast': 'forecast_revenue',
                'label': 'Revenue'
            },
            'gp': {
                'invoiced': 'invoiced_gp',
                'backlog': 'in_period_backlog_gp',
                'target': 'target_gp',
                'forecast': 'forecast_gp',
                'label': 'Gross Profit'
            },
            'gp1': {
                'invoiced': 'invoiced_gp1',
                'backlog': 'in_period_backlog_gp1',
                'target': 'target_gp1',
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
        
        # Only set title if explicitly provided (not empty string)
        chart_title = title if title else None
        
        # Prepare data for stacked bar - SYNCED with Salesperson
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
        
        # Color scale - SYNCED with Salesperson
        color_scale = alt.Scale(
            domain=['✅ Invoiced', '📅 In-Period Backlog', '🎯 Target'],
            range=[COLORS.get('gross_profit', '#1f77b4'), COLORS.get('new_customer', '#17becf'), COLORS.get('target', '#d62728')]
        )
        
        # Stacked bar chart - SYNCED with Salesperson
        bars = alt.Chart(data).mark_bar(size=60).encode(
            x=alt.X('category:N', title='', axis=alt.Axis(labelAngle=0)),
            y=alt.Y('value:Q', title='Amount (USD)', axis=alt.Axis(format='~s'), stack='zero'),
            color=alt.Color('component:N', scale=color_scale, legend=alt.Legend(orient='bottom')),
            order=alt.Order('order:Q'),
            tooltip=[
                alt.Tooltip('category:N', title='Category'),
                alt.Tooltip('component:N', title='Component'),
                alt.Tooltip('value:Q', title='Amount', format='$,.0f')
            ]
        )
        
        # Add forecast line
        forecast_line = alt.Chart(pd.DataFrame({'y': [forecast]})).mark_rule(
            color=COLORS.get('gross_profit_percent', '#800080'),
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
            color=COLORS.get('gross_profit_percent', '#800080')
        ).encode(
            x='x:N',
            y='y:Q',
            text='label:N'
        )
        
        # Build final chart - only include title if provided
        chart_props = {
            'width': 400,
            'height': 350
        }
        if chart_title:
            chart_props['title'] = chart_title
        
        chart = alt.layer(bars, forecast_line, forecast_text).properties(**chart_props)
        
        return chart
    
    @staticmethod
    def build_gap_analysis_chart(
        backlog_metrics: Dict,
        metrics_to_show: List[str] = ['revenue'],
        title: str = ""
    ) -> alt.Chart:
        """
        Build a bullet/progress chart showing current progress, forecast, and target.
        SYNCED with Salesperson page.
        """
        if not backlog_metrics:
            return alt.Chart().mark_text().encode(text=alt.value("No data available"))
        
        # Define metric configurations
        metric_configs = {
            'revenue': {
                'invoiced_key': 'invoiced_revenue',
                'target_key': 'target_revenue',
                'forecast_key': 'forecast_revenue',
                'label': 'Revenue'
            },
            'gp': {
                'invoiced_key': 'invoiced_gp',
                'target_key': 'target_gp',
                'forecast_key': 'forecast_gp',
                'label': 'Gross Profit'
            },
            'gp1': {
                'invoiced_key': 'invoiced_gp1',
                'target_key': 'target_gp1',
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
            return alt.Chart().mark_text().encode(text=alt.value("No target set"))
        
        data = pd.DataFrame(all_data)
        
        # Only set title if explicitly provided (not empty string)
        chart_title = title if title else None
        
        # Base bar (target as background) - SYNCED with Salesperson
        base = alt.Chart(data[data['type'] == 'Target']).mark_bar(
            color='#e0e0e0',
            size=40
        ).encode(
            x=alt.X('value:Q', title='Amount (USD)', axis=alt.Axis(format='~s')),
            y=alt.Y('metric:N', title='', sort=['Revenue', 'Gross Profit', 'GP1'])
        )
        
        # Forecast bar - SYNCED with Salesperson
        forecast_bar = alt.Chart(data[data['type'] == 'Forecast']).mark_bar(
            color=COLORS.get('new_customer', '#17becf'),
            size=25
        ).encode(
            x=alt.X('value:Q'),
            y=alt.Y('metric:N', sort=['Revenue', 'Gross Profit', 'GP1']),
            tooltip=[
                alt.Tooltip('metric:N', title='Metric'),
                alt.Tooltip('type:N', title='Type'),
                alt.Tooltip('value:Q', title='Amount', format='$,.0f'),
                alt.Tooltip('percent:Q', title='% of Target', format='.1f')
            ]
        )
        
        # Invoiced bar (innermost) - SYNCED with Salesperson
        invoiced_bar = alt.Chart(data[data['type'] == 'Invoiced']).mark_bar(
            color=COLORS.get('gross_profit', '#1f77b4'),
            size=15
        ).encode(
            x=alt.X('value:Q'),
            y=alt.Y('metric:N', sort=['Revenue', 'Gross Profit', 'GP1']),
            tooltip=[
                alt.Tooltip('metric:N', title='Metric'),
                alt.Tooltip('type:N', title='Type'),
                alt.Tooltip('value:Q', title='Amount', format='$,.0f'),
                alt.Tooltip('percent:Q', title='% of Target', format='.1f')
            ]
        )
        
        # Target line/tick - SYNCED with Salesperson
        target_rule = alt.Chart(data[data['type'] == 'Target']).mark_tick(
            color=COLORS.get('target', '#d62728'),
            thickness=3,
            size=50
        ).encode(
            x=alt.X('value:Q'),
            y=alt.Y('metric:N', sort=['Revenue', 'Gross Profit', 'GP1'])
        )
        
        # Achievement % text at end - SYNCED with Salesperson
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
                alt.value(COLORS.get('achievement_good', '#28a745')),
                alt.value(COLORS.get('achievement_bad', '#dc3545'))
            )
        )
        
        # Build final chart - only include title if provided
        chart_props = {
            'width': 'container',
            'height': 80 + len(metrics_to_show) * 50
        }
        if chart_title:
            chart_props['title'] = chart_title
        
        chart = alt.layer(base, forecast_bar, invoiced_bar, target_rule, text).properties(**chart_props)
        
        return chart
    
    # =========================================================================
    # MONTHLY TREND CHARTS - UPDATED v2.4.0
    # =========================================================================
    
    @staticmethod
    def build_monthly_trend_dual_chart(
        monthly_df: pd.DataFrame,
        show_gp_percent_line: bool = True
    ) -> alt.Chart:
        """
        Build monthly trend chart with Revenue + GP bars and GP% line.
        SYNCED with Salesperson page (Image 2).
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
        
        # Remove title to avoid duplicate with fragment markdown
        return chart.properties(
            width='container',
            height=350
        )
    
    @staticmethod
    def build_cumulative_dual_chart(
        monthly_df: pd.DataFrame
    ) -> alt.Chart:
        """
        Build cumulative chart with Revenue + GP lines.
        SYNCED with Salesperson page (Image 2 - Cumulative Performance).
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
        
        # Remove title to avoid duplicate with fragment markdown
        return (lines + labels).properties(
            width='container',
            height=350
        )
    
    # =========================================================================
    # YOY COMPARISON CHARTS - UPDATED v2.4.0
    # =========================================================================
    
    @staticmethod
    def build_yoy_comparison_chart(
        current_df: pd.DataFrame,
        previous_df: pd.DataFrame,
        metric: str = "Revenue",
        current_year: int = None,
        previous_year: int = None
    ) -> alt.Chart:
        """
        Build Year-over-Year comparison chart with grouped bars.
        SYNCED with Salesperson page (Image 3).
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
        
        # Remove title to avoid duplicate with fragment markdown
        return (chart + labels).properties(
            width='container',
            height=350
        )
    
    @staticmethod
    def build_yoy_cumulative_chart(
        current_df: pd.DataFrame,
        previous_df: pd.DataFrame,
        metric: str = "Revenue",
        current_year: int = None,
        previous_year: int = None
    ) -> alt.Chart:
        """
        Build YoY cumulative comparison chart.
        SYNCED with Salesperson page (Image 3 - Cumulative Revenue).
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
        
        # Remove title to avoid duplicate with fragment markdown
        return (chart + labels).properties(
            width='container',
            height=350
        )
    
    # =========================================================================
    # MONTHLY TREND CHART (Simple version for backward compatibility)
    # =========================================================================
    
    @staticmethod
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
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    @staticmethod
    def convert_pipeline_to_backlog_metrics(pipeline_metrics: Dict) -> Dict:
        """Convert pipeline metrics format to backlog metrics format."""
        if not pipeline_metrics:
            return {}
        
        summary = pipeline_metrics.get('summary', {})
        revenue_data = pipeline_metrics.get('revenue', {})
        gp_data = pipeline_metrics.get('gross_profit', {})
        gp1_data = pipeline_metrics.get('gp1', {})
        
        return {
            # Total backlog
            'total_backlog_revenue': summary.get('total_backlog_revenue', 0),
            'total_backlog_gp': summary.get('total_backlog_gp', 0),
            'total_backlog_gp1': summary.get('total_backlog_gp1', 0),
            'backlog_orders': summary.get('backlog_orders', 0),
            
            # In-period backlog
            'in_period_backlog_revenue': revenue_data.get('in_period_backlog', 0),
            'in_period_backlog_gp': gp_data.get('in_period_backlog', 0),
            'in_period_backlog_gp1': gp1_data.get('in_period_backlog', 0),
            
            # Invoiced
            'invoiced_revenue': revenue_data.get('invoiced', 0),
            'invoiced_gp': gp_data.get('invoiced', 0),
            'invoiced_gp1': gp1_data.get('invoiced', 0),
            
            # Targets
            'target_revenue': revenue_data.get('target', 0),
            'target_gp': gp_data.get('target', 0),
            'target_gp1': gp1_data.get('target', 0),
            
            # Forecast
            'forecast_revenue': revenue_data.get('forecast', 0),
            'forecast_gp': gp_data.get('forecast', 0),
            'forecast_gp1': gp1_data.get('forecast', 0),
            
            # GAP
            'gap_revenue': revenue_data.get('gap', 0),
            'gap_gp': gp_data.get('gap', 0),
            'gap_gp1': gp1_data.get('gap', 0),
            
            # Achievement
            'achievement_revenue': revenue_data.get('forecast_achievement', 0),
            'achievement_gp': gp_data.get('forecast_achievement', 0),
            'achievement_gp1': gp1_data.get('forecast_achievement', 0),
            
            # KPI Center count
            'kpi_center_count_revenue': revenue_data.get('kpi_center_count', 0),
            'kpi_center_count_gp': gp_data.get('kpi_center_count', 0),
            'kpi_center_count_gp1': gp1_data.get('kpi_center_count', 0),
        }
    
    # =========================================================================
    # PARETO / TOP PERFORMERS CHARTS (kept from v2.3.0)
    # =========================================================================
    
    @staticmethod
    def build_pareto_chart(
        data_df: pd.DataFrame,
        value_col: str,
        label_col: str,
        title: str = "Pareto Analysis",
        show_cumulative_line: bool = True,
        highlight_80_percent: bool = True
    ) -> alt.Chart:
        """Build Pareto chart with bar + cumulative line."""
        if data_df.empty:
            return alt.Chart().mark_text().encode(text=alt.value("No data"))
        
        chart_df = data_df.sort_values(value_col, ascending=False).head(20).copy()
        
        total = chart_df[value_col].sum()
        if total == 0:
            return alt.Chart().mark_text().encode(text=alt.value("No data"))
        
        chart_df['cumulative'] = chart_df[value_col].cumsum()
        chart_df['cumulative_percent'] = (chart_df['cumulative'] / total * 100).round(1)
        chart_df['percent'] = (chart_df[value_col] / total * 100).round(1)
        chart_df['order'] = range(len(chart_df))
        
        bars = alt.Chart(chart_df).mark_bar(
            color=COLORS.get('primary', '#1f77b4'),
            cornerRadiusTopLeft=3,
            cornerRadiusTopRight=3
        ).encode(
            x=alt.X(f'{label_col}:N', 
                   sort=alt.EncodingSortField(field='order', order='ascending'),
                   title=None,
                   axis=alt.Axis(labelAngle=-45, labelLimit=100)),
            y=alt.Y(f'{value_col}:Q', title='Value'),
            tooltip=[
                alt.Tooltip(f'{label_col}:N', title='Name'),
                alt.Tooltip(f'{value_col}:Q', title='Value', format='$,.0f'),
                alt.Tooltip('percent:Q', title='% of Total', format='.1f'),
                alt.Tooltip('cumulative_percent:Q', title='Cumulative %', format='.1f'),
            ]
        )
        
        chart = bars
        
        if show_cumulative_line:
            line = alt.Chart(chart_df).mark_line(
                color=COLORS.get('secondary', '#aec7e8'),
                strokeWidth=2,
                point=alt.OverlayMarkDef(color=COLORS.get('secondary', '#aec7e8'), size=50)
            ).encode(
                x=alt.X(f'{label_col}:N', sort=alt.EncodingSortField(field='order', order='ascending')),
                y=alt.Y('cumulative_percent:Q', title='Cumulative %', scale=alt.Scale(domain=[0, 105])),
            )
            
            chart = alt.layer(bars, line).resolve_scale(y='independent')
        
        return chart.properties(width='container', height=350, title=title)
    
    @staticmethod
    def build_top_performers_chart(
        data_df: pd.DataFrame,
        value_col: str,
        label_col: str,
        top_n: int = 10,
        title: str = "Top Performers",
        show_percent: bool = True
    ) -> alt.Chart:
        """Build horizontal bar chart for top performers."""
        if data_df.empty:
            return alt.Chart().mark_text().encode(text=alt.value("No data"))
        
        chart_df = data_df.nlargest(top_n, value_col).copy()
        
        total = data_df[value_col].sum()
        if total > 0:
            chart_df['percent'] = (chart_df[value_col] / total * 100).round(1)
        else:
            chart_df['percent'] = 0
        
        bars = alt.Chart(chart_df).mark_bar(
            color=COLORS.get('primary', '#1f77b4'),
            cornerRadiusTopRight=4,
            cornerRadiusBottomRight=4
        ).encode(
            x=alt.X(f'{value_col}:Q', title='Value'),
            y=alt.Y(f'{label_col}:N', sort='-x', title=None),
            tooltip=[
                alt.Tooltip(f'{label_col}:N', title='Name'),
                alt.Tooltip(f'{value_col}:Q', title='Value', format='$,.0f'),
                alt.Tooltip('percent:Q', title='% of Total', format='.1f'),
            ]
        )
        
        chart = bars
        
        if show_percent:
            text = alt.Chart(chart_df).mark_text(
                align='left',
                baseline='middle',
                dx=5,
                fontSize=11
            ).encode(
                x=alt.X(f'{value_col}:Q'),
                y=alt.Y(f'{label_col}:N', sort='-x'),
                text=alt.Text('percent:Q', format='.1f'),
            )
            chart = bars + text
        
        return chart.properties(width='container', height=min(400, top_n * 35), title=title)
    
    # =========================================================================
    # MULTI-YEAR COMPARISON CHARTS (NEW v2.5.0 - synced with Salesperson page)
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
        # KPI Center column mapping (different from Salesperson)
        metric_map = {
            'revenue': 'sales_by_kpi_center_usd',
            'gross_profit': 'gross_profit_by_kpi_center_usd',
            'gp1': 'gp1_by_kpi_center_usd'
        }
        
        col = metric_map.get(metric, 'sales_by_kpi_center_usd')
        
        if sales_df.empty:
            return KPICenterCharts._empty_chart("No data available")
        
        # Aggregate by year and month
        df = sales_df.copy()
        
        # Ensure inv_date is datetime
        if 'inv_date' in df.columns:
            df['inv_date'] = pd.to_datetime(df['inv_date'], errors='coerce')
            df['year'] = df['inv_date'].dt.year
        elif 'invoice_year' in df.columns:
            df['year'] = df['invoice_year'].astype(int)
        else:
            return KPICenterCharts._empty_chart("No date column found")
        
        # Ensure invoice_month exists
        if 'invoice_month' not in df.columns:
            df['invoice_month'] = df['inv_date'].dt.strftime('%b')
        
        monthly = df.groupby(['year', 'invoice_month'])[col].sum().reset_index()
        monthly.columns = ['year', 'month', 'amount']
        
        # Filter to selected years
        monthly = monthly[monthly['year'].isin(years)]
        
        if monthly.empty:
            return KPICenterCharts._empty_chart("No data for selected years")
        
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
        # KPI Center column mapping
        metric_map = {
            'revenue': 'sales_by_kpi_center_usd',
            'gross_profit': 'gross_profit_by_kpi_center_usd',
            'gp1': 'gp1_by_kpi_center_usd'
        }
        
        col = metric_map.get(metric, 'sales_by_kpi_center_usd')
        
        if sales_df.empty:
            return KPICenterCharts._empty_chart("No data available")
        
        df = sales_df.copy()
        
        # Ensure inv_date is datetime
        if 'inv_date' in df.columns:
            df['inv_date'] = pd.to_datetime(df['inv_date'], errors='coerce')
            df['year'] = df['inv_date'].dt.year
        elif 'invoice_year' in df.columns:
            df['year'] = df['invoice_year'].astype(int)
        else:
            return KPICenterCharts._empty_chart("No date column found")
        
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
            return KPICenterCharts._empty_chart("No data for selected years")
        
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
    
    @staticmethod
    def _empty_chart(message: str = "No data") -> alt.Chart:
        """Return an empty chart with a message."""
        return alt.Chart(pd.DataFrame({'text': [message]})).mark_text(
            fontSize=14,
            color='gray'
        ).encode(
            text='text:N'
        ).properties(
            width=400,
            height=200
        )