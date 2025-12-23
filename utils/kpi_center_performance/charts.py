# utils/kpi_center_performance/charts.py
"""
Altair Chart Builders for KPI Center Performance

All visualization components using Altair:
- KPI summary cards (using st.metric) with popup drill-down
- Monthly trend charts (bar + line)
- Cumulative charts
- Achievement comparison charts
- YoY comparison charts
- Top customers/brands Pareto charts
- Pipeline & Forecast section with tabs
- Backlog risk analysis display

VERSION: 2.1.0
CHANGELOG:
- v2.1.0: Fixed kpi_center_count key in _render_pipeline_metric_row
          Fixed convert_pipeline_to_backlog_metrics keys
- v2.0.0: Added popup buttons for Complex KPIs (New Customers/Products/Business)
          Added backlog risk analysis display
          Improved help popovers with detailed explanations
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
    # KPI CARDS (Using st.metric) - UPDATED with popup support
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
        
        Args:
            metrics: Overview metrics dictionary
            yoy_metrics: Year-over-Year comparison metrics
            complex_kpis: Complex KPI values (new customers/products/business)
            backlog_metrics: Backlog metrics (optional)
            overall_achievement: Overall KPI achievement dictionary
            show_complex: Whether to show complex KPIs section
            show_backlog: Whether to show backlog section
            new_customers_df: Detail dataframe for new customers popup
            new_products_df: Detail dataframe for new products popup
            new_business_df: Summary dataframe for new business
            new_business_detail_df: Detail dataframe for new business popup
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
        # 🆕 NEW BUSINESS SECTION (UPDATED with popup buttons)
        # =====================================================================
        if show_complex and complex_kpis:
            with st.container(border=True):
                st.markdown("**🆕 NEW BUSINESS**")
                
                col1, col2, col3 = st.columns(3)
                
                # New Customers with popup
                with col1:
                    new_customers = complex_kpis.get('num_new_customers', 0)
                    
                    # Metric and popup button in same column
                    metric_col, btn_col = st.columns([3, 1])
                    
                    with metric_col:
                        st.metric(
                            label="New Customers",
                            value=f"{new_customers:.0f}",
                            help="Customers new to the COMPANY (first invoice within 5-year lookback falls in selected period)"
                        )
                    
                    with btn_col:
                        if new_customers > 0 and new_customers_df is not None and not new_customers_df.empty:
                            with st.popover("📋", help="View details"):
                                st.markdown("**New Customers Detail**")
                                st.dataframe(
                                    new_customers_df[[
                                        'customer', 'kpi_center', 'first_sale_date',
                                        'first_day_revenue', 'first_day_gp'
                                    ]].head(50) if 'first_sale_date' in new_customers_df.columns else new_customers_df.head(50),
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
                    
                    metric_col, btn_col = st.columns([3, 1])
                    
                    with metric_col:
                        st.metric(
                            label="New Products",
                            value=f"{new_products:.0f}",
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
                
                # New Business Revenue with popup
                with col3:
                    new_biz_rev = complex_kpis.get('new_business_revenue', 0)
                    
                    metric_col, btn_col = st.columns([3, 1])
                    
                    with metric_col:
                        st.metric(
                            label="New Business Revenue",
                            value=f"${new_biz_rev:,.0f}",
                            help="Revenue from customer-product combos first sold in selected period (all revenue from new combos, not just first day)"
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
                                    use_container_width=True
                                )
                                
                                # Summary by KPI Center
                                if new_business_df is not None and not new_business_df.empty:
                                    st.divider()
                                    st.markdown("**Summary by KPI Center**")
                                    st.dataframe(
                                        new_business_df[['kpi_center', 'num_new_combos', 'new_business_revenue', 'new_business_gp']],
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
    # BACKLOG RISK ANALYSIS (NEW v2.0.0)
    # =========================================================================
    
    @staticmethod
    def render_backlog_risk_section(
        risk_analysis: Dict,
        show_detail: bool = True
    ):
        """
        Render backlog risk analysis section.
        
        Args:
            risk_analysis: Dictionary from get_backlog_risk_analysis()
            show_detail: Whether to show detailed breakdown
        """
        if not risk_analysis:
            return
        
        overdue_orders = risk_analysis.get('overdue_orders', 0)
        overdue_revenue = risk_analysis.get('overdue_revenue', 0)
        at_risk_orders = risk_analysis.get('at_risk_orders', 0)
        at_risk_revenue = risk_analysis.get('at_risk_revenue', 0)
        total_backlog = risk_analysis.get('total_backlog', 0)
        overdue_percent = risk_analysis.get('overdue_percent', 0)
        
        # Only show if there's overdue or at-risk
        if overdue_orders == 0 and at_risk_orders == 0:
            return
        
        with st.container(border=True):
            st.markdown("**⚠️ BACKLOG RISK ANALYSIS**")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                delta_color = "inverse" if overdue_orders > 0 else "off"
                st.metric(
                    label="🔴 Overdue Orders",
                    value=f"{overdue_orders:,}",
                    delta=f"ETD passed",
                    delta_color=delta_color,
                    help="Orders with ETD in the past that haven't been invoiced"
                )
            
            with col2:
                st.metric(
                    label="Overdue Revenue",
                    value=f"${overdue_revenue:,.0f}",
                    delta=f"{overdue_percent:.1f}% of total",
                    delta_color="inverse" if overdue_percent > 10 else "off",
                    help="Revenue at risk from overdue orders"
                )
            
            with col3:
                st.metric(
                    label="🟡 At-Risk Orders",
                    value=f"{at_risk_orders:,}",
                    delta="ETD within 7 days",
                    delta_color="off",
                    help="Orders with ETD in the next 7 days"
                )
            
            with col4:
                st.metric(
                    label="At-Risk Revenue",
                    value=f"${at_risk_revenue:,.0f}",
                    help="Revenue from orders due within 7 days"
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
            # Header with help
            col_header, col_help = st.columns([6, 1])
            
            with col_header:
                st.markdown("**📦 PIPELINE & FORECAST**")
            
            with col_help:
                with st.popover("ℹ️ Help"):
                    st.markdown("""
**📦 Pipeline & Forecast**

| Metric | Formula | Description |
|--------|---------|-------------|
| **Total Backlog** | `Σ backlog_by_kpi_center_usd` | All outstanding orders (all KPI Centers) |
| **In-Period** | `Σ backlog WHERE ETD in period` | Backlog expected to ship in period |
| **Target** | `Σ prorated_target` | Sum of prorated annual targets |
| **Forecast** | `Invoiced + In-Period` | Projected total for period |
| **GAP/Surplus** | `Forecast - Target` | Positive = ahead, Negative = behind |

---

**⚠️ KPI Center Filtering**

Each tab shows data from KPI Centers with that specific target:
- **Revenue tab**: KPI Centers with Revenue target
- **GP tab**: KPI Centers with Gross Profit target  
- **GP1 tab**: KPI Centers with GP1 target

This ensures accurate achievement calculation.
                    """)
            
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
        # FIXED: Get total_backlog based on metric name
        if metric_name == "Revenue":
            total_backlog = summary.get('total_backlog_revenue', 0)
        elif metric_name == "Gross Profit":
            total_backlog = summary.get('total_backlog_gp', 0)
        else:  # GP1
            total_backlog = summary.get('total_backlog_gp1', 0)
        
        in_period_backlog = metric_data.get('in_period_backlog', 0)
        target = metric_data.get('target')
        forecast = metric_data.get('forecast')
        gap = metric_data.get('gap')
        gap_percent = metric_data.get('gap_percent')
        forecast_achievement = metric_data.get('forecast_achievement')
        # FIXED: Changed from employee_count to kpi_center_count
        kpi_center_count = metric_data.get('kpi_center_count', 0)
        invoiced = metric_data.get('invoiced', 0)
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
            
            help_text = f"Backlog with ETD in period. From {kpi_center_count} KPI Centers with {metric_name} target."
            if is_estimated:
                help_text += " Estimated using GP1/GP ratio."
            
            st.metric(
                label="In-Period (KPI)",
                value=f"${in_period_backlog:,.0f}",
                delta=delta_str,
                delta_color="off",
                help=help_text
            )
        
        # Column 3: Target
        with col3:
            if target is not None:
                st.metric(
                    label="Target",
                    value=f"${target:,.0f}",
                    delta=f"{kpi_center_count} KPI Centers",
                    delta_color="off",
                    help=f"Prorated annual target for {metric_name}"
                )
            else:
                st.metric(
                    label="Target",
                    value="N/A",
                    help="No target assigned"
                )
        
        # Column 4: Forecast
        if show_forecast:
            with col4:
                if forecast is not None:
                    achievement_delta = f"{forecast_achievement:.0f}% of target" if forecast_achievement else None
                    delta_color = "normal" if forecast_achievement and forecast_achievement >= 100 else "inverse"
                    
                    st.metric(
                        label="Forecast (KPI)",
                        value=f"${forecast:,.0f}",
                        delta=achievement_delta,
                        delta_color=delta_color if achievement_delta else "off",
                        help=f"Invoiced (${invoiced:,.0f}) + In-Period Backlog"
                    )
                else:
                    st.metric(
                        label="Forecast",
                        value="N/A",
                        help="Cannot calculate without target"
                    )
            
            # Column 5: GAP/Surplus
            with col5:
                if gap is not None:
                    gap_label = "Surplus" if gap >= 0 else "GAP"
                    gap_color = "normal" if gap >= 0 else "inverse"
                    gap_delta = f"{gap_percent:+.1f}%" if gap_percent is not None else None
                    
                    st.metric(
                        label=gap_label,
                        value=f"${abs(gap):,.0f}",
                        delta=gap_delta,
                        delta_color=gap_color,
                        help=f"Forecast - Target. Positive = ahead of target."
                    )
                else:
                    st.metric(
                        label="GAP",
                        value="N/A"
                    )
        else:
            # Show placeholder when forecast not shown
            with col4:
                st.metric(
                    label="Forecast",
                    value="—",
                    help="Forecast not shown for historical periods"
                )
            with col5:
                st.metric(
                    label="GAP",
                    value="—"
                )
    
    @staticmethod
    def convert_pipeline_to_backlog_metrics(pipeline_metrics: Dict) -> Dict:
        """
        Convert pipeline metrics format to backlog metrics format for Backlog tab.
        """
        if not pipeline_metrics:
            return {}
        
        summary = pipeline_metrics.get('summary', {})
        revenue_data = pipeline_metrics.get('revenue', {})
        gp_data = pipeline_metrics.get('gross_profit', {})
        
        # FIXED: Correct key names
        return {
            'total_backlog_revenue': summary.get('total_backlog_revenue', 0),
            'total_backlog_gp': summary.get('total_backlog_gp', 0),  # FIXED: was 'total_backlog_gross_profit'
            'in_period_backlog_revenue': revenue_data.get('in_period_backlog', 0),
            'in_period_backlog_gp': gp_data.get('in_period_backlog', 0),
            'backlog_orders': summary.get('backlog_orders', 0),
        }
    
    # =========================================================================
    # MONTHLY TREND CHARTS
    # =========================================================================
    
    @staticmethod
    def build_monthly_trend_chart(
        monthly_df: pd.DataFrame,
        metric: str = "Revenue",
        show_target: bool = True,
        target_value: float = None
    ) -> alt.Chart:
        """
        Build monthly trend bar chart with optional target line.
        
        Args:
            monthly_df: DataFrame with month and metric columns
            metric: Which metric to display
            show_target: Whether to show target line
            target_value: Monthly target value
            
        Returns:
            Altair chart
        """
        if monthly_df.empty:
            return alt.Chart().mark_text().encode(text=alt.value("No data"))
        
        # Map metric name to column
        metric_col_map = {
            'Revenue': 'revenue',
            'Gross Profit': 'gross_profit',
            'GP1': 'gp1'
        }
        value_col = metric_col_map.get(metric, 'revenue')
        
        if value_col not in monthly_df.columns:
            return alt.Chart().mark_text().encode(text=alt.value(f"Column {value_col} not found"))
        
        # Prepare data
        chart_df = monthly_df.copy()
        chart_df['month_order'] = chart_df['month'].map(
            {m: i for i, m in enumerate(MONTH_ORDER)}
        )
        chart_df = chart_df.sort_values('month_order')
        
        # Base bar chart
        bars = alt.Chart(chart_df).mark_bar(
            color=COLORS['primary'],
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
        
        # Add target line if requested
        if show_target and target_value and target_value > 0:
            target_df = pd.DataFrame({'target': [target_value]})
            target_line = alt.Chart(target_df).mark_rule(
                color=COLORS['target'],
                strokeDash=[5, 5],
                strokeWidth=2
            ).encode(
                y='target:Q'
            )
            chart = chart + target_line
        
        return chart.properties(
            width=CHART_WIDTH,
            height=CHART_HEIGHT
        ).configure_axis(
            labelFontSize=11,
            titleFontSize=12
        )
    
    @staticmethod
    def build_cumulative_chart(
        monthly_df: pd.DataFrame,
        metric: str = "Revenue",
        target_df: pd.DataFrame = None
    ) -> alt.Chart:
        """
        Build cumulative line chart with optional target comparison.
        
        Args:
            monthly_df: DataFrame with month and metric columns
            metric: Which metric to display
            target_df: Optional DataFrame with cumulative targets
            
        Returns:
            Altair chart
        """
        if monthly_df.empty:
            return alt.Chart().mark_text().encode(text=alt.value("No data"))
        
        metric_col_map = {
            'Revenue': 'revenue',
            'Gross Profit': 'gross_profit',
            'GP1': 'gp1'
        }
        value_col = metric_col_map.get(metric, 'revenue')
        
        if value_col not in monthly_df.columns:
            return alt.Chart().mark_text().encode(text=alt.value(f"Column {value_col} not found"))
        
        # Calculate cumulative
        chart_df = monthly_df.copy()
        chart_df['month_order'] = chart_df['month'].map(
            {m: i for i, m in enumerate(MONTH_ORDER)}
        )
        chart_df = chart_df.sort_values('month_order')
        chart_df['cumulative'] = chart_df[value_col].cumsum()
        
        # Actual line
        actual_line = alt.Chart(chart_df).mark_line(
            color=COLORS['primary'],
            strokeWidth=3,
            point=True
        ).encode(
            x=alt.X('month:N', sort=MONTH_ORDER, title='Month'),
            y=alt.Y('cumulative:Q', title=f'Cumulative {metric}'),
            tooltip=[
                alt.Tooltip('month:N', title='Month'),
                alt.Tooltip('cumulative:Q', title='Cumulative', format='$,.0f'),
                alt.Tooltip(f'{value_col}:Q', title='Monthly', format='$,.0f')
            ]
        )
        
        chart = actual_line
        
        # Add target line if provided
        if target_df is not None and not target_df.empty:
            target_line = alt.Chart(target_df).mark_line(
                color=COLORS['target'],
                strokeDash=[5, 5],
                strokeWidth=2
            ).encode(
                x=alt.X('month:N', sort=MONTH_ORDER),
                y=alt.Y('cumulative_target:Q')
            )
            chart = chart + target_line
        
        return chart.properties(
            width=CHART_WIDTH,
            height=CHART_HEIGHT
        )
    
    # =========================================================================
    # YOY COMPARISON CHART
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
        Build Year-over-Year comparison chart.
        
        Args:
            current_df: Current year monthly data
            previous_df: Previous year monthly data
            metric: Which metric to compare
            current_year: Current year label
            previous_year: Previous year label
            
        Returns:
            Altair layered chart
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
            curr['year'] = str(current_year) if current_year else 'Current'
            curr['value'] = curr[value_col]
            combined_data.append(curr[['month', 'year', 'value']])
        
        if not previous_df.empty and value_col in previous_df.columns:
            prev = previous_df[['month', value_col]].copy()
            prev['year'] = str(previous_year) if previous_year else 'Previous'
            prev['value'] = prev[value_col]
            combined_data.append(prev[['month', 'year', 'value']])
        
        if not combined_data:
            return alt.Chart().mark_text().encode(text=alt.value("No data"))
        
        chart_df = pd.concat(combined_data, ignore_index=True)
        
        chart = alt.Chart(chart_df).mark_bar().encode(
            x=alt.X('month:N', sort=MONTH_ORDER, title='Month'),
            y=alt.Y('value:Q', title=metric),
            color=alt.Color('year:N', 
                          scale=alt.Scale(range=[COLORS['primary'], COLORS['secondary']]),
                          legend=alt.Legend(title='Year')),
            xOffset='year:N',
            tooltip=[
                alt.Tooltip('month:N', title='Month'),
                alt.Tooltip('year:N', title='Year'),
                alt.Tooltip('value:Q', title=metric, format='$,.0f')
            ]
        ).properties(
            width=CHART_WIDTH,
            height=CHART_HEIGHT
        )
        
        return chart
    
    # =========================================================================
    # RANKING TABLE
    # =========================================================================
    
    @staticmethod
    def render_kpi_center_ranking_table(
        ranking_df: pd.DataFrame,
        show_targets: bool = True,
        limit: int = 20
    ):
        """
        Render KPI Center ranking as a formatted table.
        
        Args:
            ranking_df: DataFrame with KPI Center performance data
            show_targets: Whether to show target and achievement columns
            limit: Maximum rows to display
        """
        if ranking_df.empty:
            st.info("No ranking data available")
            return
        
        # Prepare display columns
        display_df = ranking_df.head(limit).copy()
        
        # Add rank
        display_df.insert(0, 'Rank', range(1, len(display_df) + 1))
        
        # Define column config
        column_config = {
            'Rank': st.column_config.NumberColumn('Rank', width='small'),
            'kpi_center': 'KPI Center',
            'kpi_type': 'Type',
            'total_revenue': st.column_config.NumberColumn('Revenue', format='$%,.0f'),
            'total_gp': st.column_config.NumberColumn('GP', format='$%,.0f'),
            'total_gp1': st.column_config.NumberColumn('GP1', format='$%,.0f'),
            'gp_percent': st.column_config.NumberColumn('GP%', format='%.1f%%'),
            'customer_count': 'Customers',
            'order_count': 'Orders',
        }
        
        if show_targets:
            column_config.update({
                'target': st.column_config.NumberColumn('Target', format='$%,.0f'),
                'achievement': st.column_config.ProgressColumn(
                    'Achievement',
                    min_value=0,
                    max_value=150,
                    format='%.0f%%'
                ),
            })
        
        # Filter to existing columns
        display_cols = [c for c in column_config.keys() if c in display_df.columns or c == 'Rank']
        
        st.dataframe(
            display_df[display_cols] if display_cols else display_df,
            hide_index=True,
            column_config=column_config,
            use_container_width=True
        )
    
    # =========================================================================
    # KPI CENTER RANKING CHART
    # =========================================================================
    
    @staticmethod
    def build_kpi_center_ranking_chart(
        ranking_df: pd.DataFrame,
        metric: str = "revenue",
        top_n: int = 10
    ) -> alt.Chart:
        """
        Build horizontal bar chart for KPI Center ranking.
        
        Args:
            ranking_df: DataFrame with KPI Center performance data
            metric: Column name to rank by
            top_n: Number of top items to show
            
        Returns:
            Altair chart
        """
        if ranking_df.empty:
            return alt.Chart().mark_text().encode(text=alt.value("No data"))
        
        if metric not in ranking_df.columns:
            return alt.Chart().mark_text().encode(text=alt.value(f"Column {metric} not found"))
        
        # Get top N
        chart_df = ranking_df.nlargest(top_n, metric).copy()
        
        # Create chart
        chart = alt.Chart(chart_df).mark_bar(
            color=COLORS['primary'],
            cornerRadiusTopRight=3,
            cornerRadiusBottomRight=3
        ).encode(
            x=alt.X(f'{metric}:Q', title=metric.replace('_', ' ').title()),
            y=alt.Y('kpi_center:N', sort='-x', title='KPI Center'),
            tooltip=[
                alt.Tooltip('kpi_center:N', title='KPI Center'),
                alt.Tooltip(f'{metric}:Q', title=metric.replace('_', ' ').title(), format='$,.0f')
            ]
        ).properties(
            width=CHART_WIDTH,
            height=min(300, top_n * 30)
        )
        
        return chart