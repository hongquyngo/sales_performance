# utils/kpi_center_performance/charts.py
"""
Altair Chart Builders for KPI Center Performance

All visualization components using Altair:
- KPI summary cards (using st.metric)
- Monthly trend charts (bar + line)
- Cumulative charts
- Achievement comparison charts
- YoY comparison charts
- Top customers/brands Pareto charts
- Pipeline & Forecast section with tabs

VERSION: 1.0.0
"""

import logging
from typing import Dict, Optional, List
import pandas as pd
import altair as alt
import streamlit as st

from .constants import COLORS, MONTH_ORDER, CHART_WIDTH, CHART_HEIGHT

logger = logging.getLogger(__name__)


class KPICenterCharts:
    """
    Chart builders for KPI Center performance dashboard.
    
    All methods are static - can be called without instantiation.
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
        new_customers_df: pd.DataFrame = None,
        new_products_df: pd.DataFrame = None,
        new_business_df: pd.DataFrame = None,
        new_business_detail_df: pd.DataFrame = None
    ):
        """
        Render KPI summary cards using Streamlit metrics.
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
                        help="Weighted average of all KPI achievements. Formula: Σ(KPI_Achievement × Weight) / Σ Weight"
                    )
                elif metrics.get('revenue_achievement') is not None:
                    achievement = metrics['revenue_achievement']
                    delta_color = "normal" if achievement >= 100 else "inverse"
                    st.metric(
                        label="Achievement",
                        value=f"{achievement:.1f}%",
                        delta=f"vs ${metrics.get('revenue_target', 0):,.0f} target",
                        delta_color=delta_color,
                        help="Revenue achievement vs prorated target"
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
                    help="Gross Profit Margin. Formula: GP / Revenue × 100%"
                )
            
            with col7:
                st.metric(
                    label="GP1 %",
                    value=f"{metrics['gp1_percent']:.1f}%",
                    help="GP1 Margin. Formula: GP1 / Revenue × 100%"
                )
            
            with col8:
                st.metric(
                    label="Orders",
                    value=f"{metrics['total_orders']:,}",
                    help="Unique invoices in period"
                )
        
        # =====================================================================
        # 🆕 NEW BUSINESS SECTION
        # =====================================================================
        if show_complex and complex_kpis:
            with st.container(border=True):
                st.markdown("**🆕 NEW BUSINESS**")
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    new_customers = complex_kpis.get('num_new_customers', 0)
                    st.metric(
                        label="New Customers",
                        value=f"{new_customers:.0f}",
                        help="Customers new to the COMPANY (first invoice within lookback period falls in selected date range)"
                    )
                
                with col2:
                    new_products = complex_kpis.get('num_new_products', 0)
                    st.metric(
                        label="New Products",
                        value=f"{new_products:.0f}",
                        help="Products with their first sale ever (to any customer) in selected period"
                    )
                
                with col3:
                    new_biz_rev = complex_kpis.get('new_business_revenue', 0)
                    st.metric(
                        label="New Business Revenue",
                        value=f"${new_biz_rev:,.0f}",
                        help="Revenue from customer-product combos first sold in selected period"
                    )
    
    # =========================================================================
    # PIPELINE & FORECAST SECTION
    # =========================================================================
    
    @staticmethod
    def render_pipeline_forecast_section(
        pipeline_metrics: Dict,
        show_forecast: bool = True
    ):
        """
        Render Pipeline & Forecast section with tabs for Revenue/GP/GP1.
        """
        if not pipeline_metrics:
            st.info("No pipeline data available")
            return
        
        with st.container(border=True):
            st.markdown("**📦 PIPELINE & FORECAST**")
            
            # Get period context
            period_context = pipeline_metrics.get('period_context', {})
            show_forecast = period_context.get('show_forecast', True)
            
            if not show_forecast:
                st.caption(period_context.get('forecast_message', ''))
            
            # Create tabs for each metric
            tab_rev, tab_gp, tab_gp1 = st.tabs(["💵 Revenue", "📈 Gross Profit", "📊 GP1"])
            
            with tab_rev:
                KPICenterCharts._render_pipeline_metric_row(
                    metric_data=pipeline_metrics.get('revenue', {}),
                    metric_name="Revenue",
                    summary=pipeline_metrics.get('summary', {}),
                    show_forecast=show_forecast
                )
            
            with tab_gp:
                KPICenterCharts._render_pipeline_metric_row(
                    metric_data=pipeline_metrics.get('gross_profit', {}),
                    metric_name="Gross Profit",
                    summary=pipeline_metrics.get('summary', {}),
                    show_forecast=show_forecast
                )
            
            with tab_gp1:
                KPICenterCharts._render_pipeline_metric_row(
                    metric_data=pipeline_metrics.get('gp1', {}),
                    metric_name="GP1",
                    summary=pipeline_metrics.get('summary', {}),
                    show_forecast=show_forecast,
                    is_estimated=True,
                    gp1_gp_ratio=pipeline_metrics.get('summary', {}).get('gp1_gp_ratio', 1.0)
                )
    
    @staticmethod
    def _render_pipeline_metric_row(
        metric_data: Dict,
        metric_name: str,
        summary: Dict,
        show_forecast: bool = True,
        is_estimated: bool = False,
        gp1_gp_ratio: float = 1.0
    ):
        """Render a single row of pipeline metrics."""
        total_backlog = summary.get(f'total_backlog_{metric_name.lower().replace(" ", "_")}', 
                                   summary.get('total_backlog_revenue', 0))
        in_period_backlog = metric_data.get('in_period_backlog', 0)
        target = metric_data.get('target')
        forecast = metric_data.get('forecast')
        gap = metric_data.get('gap')
        gap_percent = metric_data.get('gap_percent')
        forecast_achievement = metric_data.get('forecast_achievement')
        employee_count = metric_data.get('employee_count', 0)
        backlog_orders = summary.get('backlog_orders', 0)
        
        col1, col2, col3, col4, col5 = st.columns(5)
        
        # Column 1: Total Backlog
        with col1:
            help_text = f"All outstanding {metric_name.lower()} from pending orders."
            if is_estimated:
                help_text += f" Estimated using GP1/GP ratio ({gp1_gp_ratio:.2%})."
            
            st.metric(
                label="Total Backlog",
                value=f"${total_backlog:,.0f}",
                delta=f"{backlog_orders:,} orders" if backlog_orders else None,
                delta_color="off",
                help=help_text
            )
        
        # Column 2: In-Period Backlog
        with col2:
            backlog_vs_target = None
            if target and target > 0:
                backlog_vs_target = (in_period_backlog / target * 100)
            
            delta_str = f"{backlog_vs_target:.0f}% of target" if backlog_vs_target else None
            
            help_text = f"Backlog with ETD in period. Only from {employee_count} KPI Centers with {metric_name} target."
            if is_estimated:
                help_text += " Estimated using GP1/GP ratio."
            
            st.metric(
                label="In-Period Backlog",
                value=f"${in_period_backlog:,.0f}",
                delta=delta_str,
                delta_color="off",
                help=help_text
            )
        
        # Column 3: Target
        with col3:
            if target is not None and target > 0:
                st.metric(
                    label="Target (Prorated)",
                    value=f"${target:,.0f}",
                    delta=f"{employee_count} KPI Centers",
                    delta_color="off",
                    help=f"Sum of prorated {metric_name} targets from {employee_count} KPI Centers"
                )
            else:
                st.metric(
                    label="Target (Prorated)",
                    value="N/A",
                    delta="No KPI assigned",
                    delta_color="off"
                )
        
        # Column 4: Forecast
        with col4:
            if show_forecast and forecast is not None:
                delta_color = "normal" if forecast_achievement and forecast_achievement >= 100 else "inverse"
                delta_str = f"{forecast_achievement:.0f}% of target" if forecast_achievement else None
                
                st.metric(
                    label="Forecast",
                    value=f"${forecast:,.0f}",
                    delta=delta_str,
                    delta_color=delta_color if delta_str else "off",
                    help=f"Invoiced + In-Period Backlog"
                )
            else:
                st.metric(
                    label="Forecast",
                    value="N/A",
                    delta="Historical period",
                    delta_color="off"
                )
        
        # Column 5: GAP
        with col5:
            if show_forecast and gap is not None:
                if gap >= 0:
                    label = "Surplus ✅"
                    delta_color = "normal"
                else:
                    label = "GAP ⚠️"
                    delta_color = "inverse"
                
                delta_str = f"{gap_percent:+.1f}%" if gap_percent is not None else None
                
                st.metric(
                    label=label,
                    value=f"${gap:+,.0f}",
                    delta=delta_str,
                    delta_color=delta_color,
                    help="Forecast - Target. Positive = ahead, Negative = behind."
                )
            else:
                reason = "No target" if target is None else "Historical period"
                st.metric(
                    label="GAP",
                    value="N/A",
                    delta=reason,
                    delta_color="off"
                )
    
    # =========================================================================
    # MONTHLY TREND CHART
    # =========================================================================
    
    @staticmethod
    def build_monthly_trend_chart(
        monthly_df: pd.DataFrame,
        show_gp1: bool = False,
        title: str = "Monthly Trend"
    ) -> alt.Chart:
        """
        Build monthly trend chart with bars for revenue and line for GP.
        """
        if monthly_df.empty:
            return alt.Chart().mark_text().encode(
                text=alt.value("No data available")
            )
        
        df = monthly_df.copy()
        
        # Ensure month order
        df['month_order'] = df['invoice_month'].apply(
            lambda x: MONTH_ORDER.index(x) if x in MONTH_ORDER else 12
        )
        df = df.sort_values('month_order')
        
        # Base chart
        base = alt.Chart(df).encode(
            x=alt.X('invoice_month:N', 
                   sort=MONTH_ORDER, 
                   title='Month',
                   axis=alt.Axis(labelAngle=0))
        )
        
        # Revenue bars
        revenue_bars = base.mark_bar(color=COLORS['revenue'], opacity=0.7).encode(
            y=alt.Y('revenue:Q', title='Revenue (USD)'),
            tooltip=[
                alt.Tooltip('invoice_month:N', title='Month'),
                alt.Tooltip('revenue:Q', title='Revenue', format='$,.0f'),
                alt.Tooltip('gross_profit:Q', title='GP', format='$,.0f'),
                alt.Tooltip('gp_percent:Q', title='GP%', format='.1f')
            ]
        )
        
        # GP line
        gp_line = base.mark_line(
            color=COLORS['gross_profit'], 
            strokeWidth=3,
            point=True
        ).encode(
            y=alt.Y('gross_profit:Q'),
            tooltip=[
                alt.Tooltip('invoice_month:N', title='Month'),
                alt.Tooltip('gross_profit:Q', title='GP', format='$,.0f')
            ]
        )
        
        chart = alt.layer(revenue_bars, gp_line).resolve_scale(
            y='independent'
        ).properties(
            title=title,
            width='container',
            height=300
        )
        
        return chart
    
    # =========================================================================
    # CUMULATIVE CHART
    # =========================================================================
    
    @staticmethod
    def build_cumulative_chart(
        monthly_df: pd.DataFrame,
        title: str = "Cumulative Performance"
    ) -> alt.Chart:
        """
        Build cumulative performance chart.
        """
        if monthly_df.empty:
            return alt.Chart().mark_text().encode(
                text=alt.value("No data available")
            )
        
        df = monthly_df.copy()
        
        # Ensure month order
        df['month_order'] = df['invoice_month'].apply(
            lambda x: MONTH_ORDER.index(x) if x in MONTH_ORDER else 12
        )
        df = df.sort_values('month_order')
        
        base = alt.Chart(df).encode(
            x=alt.X('invoice_month:N', 
                   sort=MONTH_ORDER, 
                   title='Month',
                   axis=alt.Axis(labelAngle=0))
        )
        
        # Cumulative revenue line
        revenue_line = base.mark_line(
            color=COLORS['revenue'],
            strokeWidth=2,
            point=True
        ).encode(
            y=alt.Y('cumulative_revenue:Q', title='Cumulative (USD)'),
            tooltip=[
                alt.Tooltip('invoice_month:N', title='Month'),
                alt.Tooltip('cumulative_revenue:Q', title='Cum. Revenue', format='$,.0f'),
                alt.Tooltip('cumulative_gp:Q', title='Cum. GP', format='$,.0f')
            ]
        )
        
        # Cumulative GP line
        gp_line = base.mark_line(
            color=COLORS['gross_profit'],
            strokeWidth=2,
            point=True
        ).encode(
            y=alt.Y('cumulative_gp:Q'),
            tooltip=[
                alt.Tooltip('invoice_month:N', title='Month'),
                alt.Tooltip('cumulative_gp:Q', title='Cum. GP', format='$,.0f')
            ]
        )
        
        chart = alt.layer(revenue_line, gp_line).properties(
            title=title,
            width='container',
            height=300
        )
        
        return chart
    
    # =========================================================================
    # YOY COMPARISON CHART
    # =========================================================================
    
    @staticmethod
    def build_yoy_comparison_chart(
        current_df: pd.DataFrame,
        previous_df: pd.DataFrame,
        metric: str = 'revenue',
        current_label: str = 'Current Year',
        previous_label: str = 'Previous Year'
    ) -> alt.Chart:
        """
        Build Year-over-Year comparison chart.
        """
        # Column mapping
        col_map = {
            'revenue': 'sales_by_kpi_center_usd',
            'gross_profit': 'gross_profit_by_kpi_center_usd',
            'gp1': 'gp1_by_kpi_center_usd'
        }
        col = col_map.get(metric, 'sales_by_kpi_center_usd')
        
        # Prepare data
        def prepare_monthly(df, label):
            if df.empty:
                return pd.DataFrame()
            
            df = df.copy()
            if 'invoice_month' not in df.columns:
                if 'inv_date' in df.columns:
                    df['inv_date'] = pd.to_datetime(df['inv_date'], errors='coerce')
                    df['invoice_month'] = df['inv_date'].dt.strftime('%b')
                else:
                    return pd.DataFrame()
            
            monthly = df.groupby('invoice_month')[col].sum().reset_index()
            monthly.columns = ['month', 'value']
            monthly['year'] = label
            return monthly
        
        current_monthly = prepare_monthly(current_df, current_label)
        previous_monthly = prepare_monthly(previous_df, previous_label)
        
        combined = pd.concat([current_monthly, previous_monthly], ignore_index=True)
        
        if combined.empty:
            return alt.Chart().mark_text().encode(text=alt.value("No data"))
        
        # Build chart
        chart = alt.Chart(combined).mark_bar().encode(
            x=alt.X('month:N', sort=MONTH_ORDER, title='Month'),
            y=alt.Y('value:Q', title=f'{metric.replace("_", " ").title()} (USD)'),
            color=alt.Color('year:N', 
                          scale=alt.Scale(
                              domain=[current_label, previous_label],
                              range=[COLORS['current_year'], COLORS['previous_year']]
                          ),
                          title='Period'),
            xOffset='year:N',
            tooltip=[
                alt.Tooltip('month:N', title='Month'),
                alt.Tooltip('year:N', title='Period'),
                alt.Tooltip('value:Q', title='Value', format='$,.0f')
            ]
        ).properties(
            title=f"Year-over-Year Comparison: {metric.replace('_', ' ').title()}",
            width='container',
            height=350
        )
        
        return chart
    
    # =========================================================================
    # KPI CENTER RANKING CHART
    # =========================================================================
    
    @staticmethod
    def build_kpi_center_ranking_chart(
        ranking_df: pd.DataFrame,
        metric: str = 'revenue',
        top_n: int = 10
    ) -> alt.Chart:
        """
        Build horizontal bar chart ranking KPI Centers by metric.
        """
        if ranking_df.empty:
            return alt.Chart().mark_text().encode(text=alt.value("No data"))
        
        df = ranking_df.head(top_n).copy()
        
        # Get metric column
        metric_col = metric if metric in df.columns else 'revenue'
        
        chart = alt.Chart(df).mark_bar(color=COLORS['revenue']).encode(
            x=alt.X(f'{metric_col}:Q', title=f'{metric.replace("_", " ").title()} (USD)'),
            y=alt.Y('kpi_center:N', sort='-x', title='KPI Center'),
            tooltip=[
                alt.Tooltip('kpi_center:N', title='KPI Center'),
                alt.Tooltip(f'{metric_col}:Q', title=metric.replace("_", " ").title(), format='$,.0f'),
                alt.Tooltip('customers:Q', title='Customers'),
                alt.Tooltip('gp_percent:Q', title='GP%', format='.1f')
            ]
        ).properties(
            title=f'Top {top_n} KPI Centers by {metric.replace("_", " ").title()}',
            width='container',
            height=min(400, 40 * top_n)
        )
        
        return chart
    
    # =========================================================================
    # TOP CUSTOMERS/BRANDS PARETO
    # =========================================================================
    
    @staticmethod
    def build_pareto_chart(
        df: pd.DataFrame,
        value_col: str,
        name_col: str,
        title: str = "Pareto Analysis"
    ) -> alt.Chart:
        """
        Build Pareto chart showing cumulative contribution.
        """
        if df.empty:
            return alt.Chart().mark_text().encode(text=alt.value("No data"))
        
        # Sort by value descending
        df = df.sort_values(value_col, ascending=False).head(20).copy()
        df['cumulative_pct'] = df[value_col].cumsum() / df[value_col].sum() * 100
        df['rank'] = range(1, len(df) + 1)
        
        # Base
        base = alt.Chart(df).encode(
            x=alt.X(f'{name_col}:N', sort=None, title='')
        )
        
        # Bars
        bars = base.mark_bar(color=COLORS['revenue']).encode(
            y=alt.Y(f'{value_col}:Q', title='Value (USD)'),
            tooltip=[
                alt.Tooltip(f'{name_col}:N', title='Name'),
                alt.Tooltip(f'{value_col}:Q', title='Value', format='$,.0f'),
                alt.Tooltip('cumulative_pct:Q', title='Cumulative %', format='.1f')
            ]
        )
        
        # Line
        line = base.mark_line(color=COLORS['target'], strokeWidth=2).encode(
            y=alt.Y('cumulative_pct:Q', title='Cumulative %', scale=alt.Scale(domain=[0, 100]))
        )
        
        chart = alt.layer(bars, line).resolve_scale(
            y='independent'
        ).properties(
            title=title,
            width='container',
            height=350
        )
        
        return chart
    
    # =========================================================================
    # HELPER: CONVERT PIPELINE TO BACKLOG METRICS FORMAT
    # =========================================================================
    
    @staticmethod
    def convert_pipeline_to_backlog_metrics(pipeline_metrics: dict) -> dict:
        """
        Convert pipeline_forecast_metrics format to legacy backlog_metrics format.
        """
        if not pipeline_metrics:
            return {}
        
        revenue = pipeline_metrics.get('revenue', {})
        gp = pipeline_metrics.get('gross_profit', {})
        gp1 = pipeline_metrics.get('gp1', {})
        summary = pipeline_metrics.get('summary', {})
        period_context = pipeline_metrics.get('period_context', {})
        
        return {
            'period_context': period_context,
            
            'current_invoiced_revenue': revenue.get('invoiced', 0),
            'in_period_backlog_revenue': revenue.get('in_period_backlog', 0),
            'revenue_target': revenue.get('target'),
            'forecast_revenue': revenue.get('forecast'),
            'gap_revenue': revenue.get('gap'),
            
            'current_invoiced_gp': gp.get('invoiced', 0),
            'in_period_backlog_gp': gp.get('in_period_backlog', 0),
            'gp_target': gp.get('target'),
            'forecast_gp': gp.get('forecast'),
            'gap_gp': gp.get('gap'),
            
            'current_invoiced_gp1': gp1.get('invoiced', 0),
            'in_period_backlog_gp1': gp1.get('in_period_backlog', 0),
            'gp1_target': gp1.get('target'),
            'forecast_gp1': gp1.get('forecast'),
            'gap_gp1': gp1.get('gap'),
            
            'total_backlog_revenue': summary.get('total_backlog_revenue', 0),
            'total_backlog_gp': summary.get('total_backlog_gp', 0),
            'total_backlog_gp1': summary.get('total_backlog_gp1', 0),
            'backlog_orders': summary.get('backlog_orders', 0),
            'gp1_gp_ratio': summary.get('gp1_gp_ratio', 1.0),
        }
