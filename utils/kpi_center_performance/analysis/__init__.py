# utils/kpi_center_performance/analysis/__init__.py
"""
Analysis tab module for KPI Center Performance.

VERSION: 5.0.0

USAGE:
    from utils.kpi_center_performance.analysis import analysis_tab_fragment
    
    # In main page, Tab 3:
    with tab3:
        analysis_tab_fragment(
            sales_df=sales_df,
            prev_sales_df=prev_sales_df,
            filter_values=active_filters,
            metrics_calculator=metrics_calc
        )
"""

from .fragments import (
    # Main entry point
    analysis_tab_fragment,
    # Legacy (backward compatibility)
    top_performers_fragment,
)

from .charts import (
    build_pareto_chart,
    build_top_performers_chart,
    build_mix_pie_chart,
    build_growth_comparison_chart,
)

__all__ = [
    # Main entry point
    'analysis_tab_fragment',
    # Legacy
    'top_performers_fragment',
    # Charts (if needed externally)
    'build_pareto_chart',
    'build_top_performers_chart',
    'build_mix_pie_chart',
    'build_growth_comparison_chart',
]