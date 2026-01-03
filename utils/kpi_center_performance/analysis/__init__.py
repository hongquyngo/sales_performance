# utils/kpi_center_performance/analysis/__init__.py
"""Analysis tab fragments and charts for KPI Center Performance."""

from .fragments import (
    top_performers_fragment,
)

from .charts import (
    build_pareto_chart,
    build_top_performers_chart,
)

__all__ = [
    # Fragments
    'top_performers_fragment',
    # Charts
    'build_pareto_chart',
    'build_top_performers_chart',
]
