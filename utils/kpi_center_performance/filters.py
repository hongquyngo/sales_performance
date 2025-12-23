# utils/kpi_center_performance/filters.py
"""
Sidebar Filter Components for KPI Center Performance

Renders filter UI elements:
- Period selector (YTD/QTD/MTD/Custom) with radio buttons
- Year selector
- KPI Center selector with type grouping
- Entity selector
- Internal revenue filter
- YoY comparison toggle
- KPI Type filter
- Refresh button with cache info

VERSION: 2.0.0
CHANGELOG:
- v2.0.0: Added Refresh button with cache info display
          Filter summary shows immediately (not just on submit)
          Improved help text and tooltips
          Added smart caching session state management
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
import streamlit as st
from sqlalchemy import text

from .constants import PERIOD_TYPES, MONTH_ORDER, KPI_CENTER_TYPES
from .access_control import AccessControl

logger = logging.getLogger(__name__)


# =============================================================================
# KPI ASSIGNMENT HELPER
# =============================================================================

def _get_kpi_centers_with_assignments(years: List[int]) -> List[int]:
    """
    Get list of KPI Center IDs that have KPI assignments in given years.
    
    Args:
        years: List of years to check
        
    Returns:
        List of kpi_center_ids with KPI assignments
    """
    if not years:
        return []
    
    try:
        from utils.db import get_db_engine
        engine = get_db_engine()
        
        query = """
            SELECT DISTINCT kpi_center_id 
            FROM sales_kpi_center_assignments_view 
            WHERE year IN :years
            ORDER BY kpi_center_id
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(query), {'years': tuple(years)})
            return [row[0] for row in result]
            
    except Exception as e:
        logger.error(f"Error fetching KPI Centers with assignments: {e}")
        return []


# =============================================================================
# MULTISELECT FILTER WITH EXCLUDED OPTION
# =============================================================================

@dataclass
class FilterResult:
    """
    Result from a multiselect filter with excluded option.
    """
    selected: List[Any]
    excluded: bool
    is_active: bool
    
    def __repr__(self) -> str:
        mode = "EXCLUDE" if self.excluded else "INCLUDE"
        return f"FilterResult({len(self.selected)} items, {mode}, active={self.is_active})"


def render_multiselect_filter(
    label: str,
    options: List[Any],
    key: str,
    default_excluded: bool = False,
    placeholder: str = "Select...",
    help_text: str = None,
    max_selections: int = None,
    container = None
) -> FilterResult:
    """
    Render a multiselect filter with an "Excl" (Excluded) checkbox.
    """
    ctx = container if container else st
    
    # Header row with label and Excl checkbox
    col_label, col_excl = ctx.columns([4, 1])
    
    with col_label:
        ctx.markdown(f"**{label}**")
    
    with col_excl:
        excluded = ctx.checkbox(
            "Excl",
            value=default_excluded,
            key=f"{key}_excl",
            help="Tick to EXCLUDE selected items instead of filtering to them"
        )
    
    # Multiselect
    selected = ctx.multiselect(
        label=label,
        options=options,
        default=[],
        key=f"{key}_select",
        placeholder=placeholder,
        help=help_text,
        max_selections=max_selections,
        label_visibility="collapsed"
    )
    
    # Determine if filter is active
    is_active = len(selected) > 0
    
    return FilterResult(
        selected=selected,
        excluded=excluded,
        is_active=is_active
    )


def apply_multiselect_filter(
    df: pd.DataFrame,
    column: str,
    filter_result: FilterResult
) -> pd.DataFrame:
    """
    Apply multiselect filter to a DataFrame.
    """
    if df.empty or not filter_result.is_active:
        return df
    
    if column not in df.columns:
        logger.warning(f"Column '{column}' not found in DataFrame")
        return df
    
    if filter_result.excluded:
        return df[~df[column].isin(filter_result.selected)]
    else:
        return df[df[column].isin(filter_result.selected)]


def render_text_search_filter(
    label: str,
    key: str,
    placeholder: str = "Search...",
    help_text: str = None,
    container = None
) -> str:
    """Render a text search input."""
    ctx = container if container else st
    
    return ctx.text_input(
        label,
        value="",
        key=key,
        placeholder=placeholder,
        help=help_text
    )


def apply_text_search_filter(
    df: pd.DataFrame,
    columns: List[str],
    search_text: str
) -> pd.DataFrame:
    """Apply text search filter across multiple columns."""
    if df.empty or not search_text:
        return df
    
    search_lower = search_text.lower()
    
    mask = pd.Series([False] * len(df), index=df.index)
    for col in columns:
        if col in df.columns:
            mask |= df[col].astype(str).str.lower().str.contains(search_lower, na=False)
    
    return df[mask]


def render_number_filter(
    label: str,
    key: str,
    min_val: float = None,
    max_val: float = None,
    default_val: float = None,
    step: float = 1.0,
    help_text: str = None,
    container = None
) -> Optional[float]:
    """Render a number input filter."""
    ctx = container if container else st
    
    return ctx.number_input(
        label,
        min_value=min_val,
        max_value=max_val,
        value=default_val,
        step=step,
        key=key,
        help=help_text
    )


# =============================================================================
# SESSION STATE MANAGEMENT FOR SMART CACHING (NEW v2.0.0)
# =============================================================================

def _get_cached_year_range() -> Tuple[Optional[int], Optional[int]]:
    """Get current cached year range from session state."""
    return (
        st.session_state.get('_kpc_cached_start_year'),
        st.session_state.get('_kpc_cached_end_year')
    )


def _set_cached_year_range(start_year: int, end_year: int):
    """Set cached year range in session state."""
    st.session_state['_kpc_cached_start_year'] = start_year
    st.session_state['_kpc_cached_end_year'] = end_year


def _get_applied_filters() -> Optional[Dict]:
    """Get last applied filters from session state."""
    return st.session_state.get('_kpc_applied_filters')


def _set_applied_filters(filters: Dict):
    """Store applied filters in session state."""
    st.session_state['_kpc_applied_filters'] = filters.copy()


def clear_data_cache():
    """Clear all cached data - called by Refresh button."""
    keys_to_clear = [
        '_kpc_cached_start_year',
        '_kpc_cached_end_year',
        '_kpc_raw_cached_data',
        '_kpc_applied_filters'
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]
    
    # Also clear st.cache_data
    st.cache_data.clear()
    logger.info("Data cache cleared")


# =============================================================================
# MAIN FILTER CLASS
# =============================================================================

class KPICenterFilters:
    """
    Filter UI components for KPI Center Performance page.
    
    Renders all sidebar filters and handles validation.
    
    Usage:
        filters = KPICenterFilters(access)
        filter_values = filters.render_sidebar_filters(kpi_center_df, entity_df)
    """
    
    def __init__(self, access: AccessControl):
        """Initialize with access control."""
        self.access = access
    
    def render_sidebar_filters(
        self,
        kpi_center_df: pd.DataFrame,
        entity_df: pd.DataFrame = None,
        available_years: List[int] = None
    ) -> Dict:
        """
        Render all sidebar filters inside a form.
        
        Returns:
            Dictionary of filter values
        """
        st.sidebar.title("🎯 KPI Center Filters")
        
        # Show access info
        self._render_access_info()
        
        st.sidebar.divider()
        
        # Use form to batch updates
        with st.sidebar.form("kpi_center_filters"):
            # Period Type
            period_type = st.radio(
                "📅 Period",
                options=PERIOD_TYPES,
                horizontal=True,
                key="filter_period_type",
                help="YTD: Year to Date | QTD: Quarter to Date | MTD: Month to Date | Custom: Select dates"
            )
            
            # Year
            current_year = datetime.now().year
            years = available_years or [current_year, current_year - 1, current_year - 2]
            year = st.selectbox(
                "Year",
                options=years,
                index=0,
                key="filter_year"
            )
            
            # Date range (for Custom or override)
            col_start, col_end = st.columns(2)
            
            with col_start:
                custom_start = st.date_input(
                    "Start Date",
                    value=date(year, 1, 1),
                    key="filter_start_date",
                    help="Only used when Period = Custom"
                )
            
            with col_end:
                custom_end = st.date_input(
                    "End Date",
                    value=min(date.today(), date(year, 12, 31)),
                    key="filter_end_date",
                    help="Only used when Period = Custom"
                )
            
            st.divider()
            
            # Only with KPI assignment checkbox
            only_with_kpi = st.checkbox(
                "Only with KPI assignment",
                value=True,
                key="filter_only_with_kpi",
                help="Show only KPI Centers that have KPI targets assigned for the selected year"
            )
            
            # KPI Center selector
            kpi_center_ids = self._render_kpi_center_filter(
                kpi_center_df, year, only_with_kpi
            )
            
            # KPI Type filter (TERRITORY, INTERNAL, etc.)
            kpi_type_filter = self._render_kpi_type_filter(kpi_center_df)
            
            # Entity filter
            entity_ids = []
            if entity_df is not None and not entity_df.empty:
                entity_ids = self._render_entity_filter(entity_df)
            
            st.divider()
            
            # Exclude internal revenue
            exclude_internal = st.checkbox(
                "Exclude internal revenue",
                value=True,
                key="filter_exclude_internal",
                help="Filter out sales to internal companies"
            )
            
            # YoY comparison toggle
            show_yoy = st.checkbox(
                "Show YoY comparison",
                value=True,
                key="filter_show_yoy",
                help="Show Year-over-Year comparison metrics"
            )
            
            # Submit button
            submitted = st.form_submit_button(
                "Apply Filters",
                use_container_width=True,
                type="primary"
            )
        
        # =====================================================================
        # REFRESH BUTTON (NEW v2.0.0) - Outside form
        # =====================================================================
        st.sidebar.divider()
        
        col_r1, col_r2 = st.sidebar.columns([1, 1])
        
        with col_r1:
            if st.button("🔄 Refresh", use_container_width=True, 
                        help="Reload data from database"):
                clear_data_cache()
                st.rerun()
        
        with col_r2:
            # Show cache info
            cached_start, cached_end = _get_cached_year_range()
            if cached_start and cached_end:
                st.caption(f"📦 {cached_start}-{cached_end}")
            else:
                st.caption("📦 No cache")
        
        # Calculate dates based on period type
        start_date, end_date = self._get_period_dates(
            period_type, year, custom_start, custom_end
        )
        
        # Store in session state
        filter_values = {
            'period_type': period_type,
            'year': year,
            'start_date': start_date,
            'end_date': end_date,
            'kpi_center_ids': kpi_center_ids,
            'kpi_type_filter': kpi_type_filter,
            'entity_ids': entity_ids,
            'exclude_internal_revenue': exclude_internal,
            'show_yoy': show_yoy,
            'only_with_kpi': only_with_kpi,
            'submitted': submitted,
        }
        
        # Always show filter summary (not just on submit) - v2.0.0
        self._show_filter_summary(filter_values)
        
        return filter_values
    
    # =========================================================================
    # PERIOD HANDLING
    # =========================================================================
    
    def _get_period_dates(
        self,
        period_type: str,
        year: int,
        custom_start: date,
        custom_end: date
    ) -> Tuple[date, date]:
        """Calculate start and end dates based on period type."""
        
        if period_type == 'Custom':
            return custom_start, custom_end
        
        today = date.today()
        year = int(year)
        
        if period_type == 'YTD':
            start = date(year, 1, 1)
            if year == today.year:
                end = today
            else:
                end = date(year, 12, 31)
        
        elif period_type == 'QTD':
            current_quarter = (today.month - 1) // 3 + 1
            quarter_start_month = (current_quarter - 1) * 3 + 1
            start = date(year, quarter_start_month, 1)
            if year == today.year:
                end = today
            else:
                end = date(year, 12, 31)
        
        elif period_type == 'MTD':
            if year == today.year:
                start = date(year, today.month, 1)
                end = today
            else:
                start = date(year, 12, 1)
                end = date(year, 12, 31)
        
        else:
            start = date(year, 1, 1)
            end = min(today, date(year, 12, 31))
        
        return start, end
    
    # =========================================================================
    # KPI CENTER FILTER
    # =========================================================================
    
    def _render_kpi_center_filter(
        self,
        kpi_center_df: pd.DataFrame,
        year: int,
        only_with_kpi: bool
    ) -> List[int]:
        """Render KPI Center filter."""
        if kpi_center_df.empty:
            st.warning("No KPI Centers available")
            return []
        
        # Filter to those with KPI assignment if requested
        if only_with_kpi:
            kpi_centers_with_assignment = _get_kpi_centers_with_assignments([year])
            if kpi_centers_with_assignment:
                kpi_center_df = kpi_center_df[
                    kpi_center_df['kpi_center_id'].isin(kpi_centers_with_assignment)
                ]
        
        if kpi_center_df.empty:
            st.warning("No KPI Centers with assignments for this year")
            return []
        
        # Build options grouped by type
        all_kpi_centers = kpi_center_df['kpi_center_name'].tolist()
        id_map = dict(zip(
            kpi_center_df['kpi_center_name'],
            kpi_center_df['kpi_center_id']
        ))
        
        options = ['All'] + all_kpi_centers
        
        selected = st.multiselect(
            "🎯 KPI Center",
            options=options,
            default=['All'],
            key="filter_kpi_center"
        )
        
        # Convert to IDs
        if 'All' in selected or not selected:
            return list(id_map.values())
        
        return [id_map[name] for name in selected if name in id_map]
    
    # =========================================================================
    # KPI TYPE FILTER
    # =========================================================================
    
    def _render_kpi_type_filter(
        self,
        kpi_center_df: pd.DataFrame
    ) -> Optional[str]:
        """Render KPI Type filter (TERRITORY, INTERNAL, etc.)."""
        if kpi_center_df.empty or 'kpi_type' not in kpi_center_df.columns:
            return None
        
        types = kpi_center_df['kpi_type'].dropna().unique().tolist()
        
        if not types:
            return None
        
        options = ['All Types'] + sorted(types)
        
        selected = st.selectbox(
            "KPI Type",
            options=options,
            index=0,
            key="filter_kpi_type",
            help="Filter by KPI Center type (e.g., TERRITORY, INTERNAL)"
        )
        
        if selected == 'All Types':
            return None
        
        return selected
    
    # =========================================================================
    # ENTITY FILTER
    # =========================================================================
    
    def _render_entity_filter(
        self,
        entity_df: pd.DataFrame
    ) -> List[int]:
        """Render entity (legal entity) filter."""
        if entity_df.empty:
            return []
        
        options = ['All Entities'] + entity_df['entity_name'].tolist()
        id_map = dict(zip(
            entity_df['entity_name'],
            entity_df['entity_id']
        ))
        
        selected = st.multiselect(
            "🏢 Legal Entity",
            options=options,
            default=['All Entities'],
            key="filter_entity"
        )
        
        if 'All Entities' in selected or not selected:
            return []  # No filter - return empty list to indicate "all"
        
        return [id_map[name] for name in selected if name in id_map]
    
    # =========================================================================
    # ACCESS INFO
    # =========================================================================
    
    def _render_access_info(self):
        """Display access level info in sidebar."""
        if self.access.can_access_page():
            st.sidebar.caption("🔓 Full Access - All KPI Centers")
        else:
            st.sidebar.error("🚫 Access Denied")
    
    # =========================================================================
    # FILTER SUMMARY
    # =========================================================================
    
    def _show_filter_summary(self, filters: Dict):
        """Show summary of current filters in sidebar."""
        parts = []
        
        # Period
        parts.append(f"{filters['period_type']} {filters['year']}")
        
        # Date range
        parts.append(
            f"({filters['start_date'].strftime('%b %d')} - "
            f"{filters['end_date'].strftime('%b %d')})"
        )
        
        # KPI Centers count
        kc_count = len(filters.get('kpi_center_ids', []))
        if kc_count == 1:
            parts.append("1 KPI Center")
        elif kc_count > 1:
            parts.append(f"{kc_count} KPI Centers")
        
        # Internal revenue status
        if filters.get('exclude_internal_revenue', True):
            parts.append("excl. internal")
        
        st.sidebar.caption("📊 " + " • ".join(parts))
    
    # =========================================================================
    # STATIC HELPERS
    # =========================================================================
    
    @staticmethod
    def get_filter_summary(filters: Dict) -> str:
        """Get human-readable summary of current filters."""
        parts = []
        
        parts.append(f"{filters['period_type']} {filters['year']}")
        parts.append(
            f"({filters['start_date'].strftime('%b %d')} - "
            f"{filters['end_date'].strftime('%b %d')})"
        )
        
        kc_count = len(filters.get('kpi_center_ids', []))
        if kc_count == 1:
            parts.append("1 KPI Center")
        elif kc_count > 1:
            parts.append(f"{kc_count} KPI Centers")
        
        if filters.get('exclude_internal_revenue', True):
            parts.append("excl. internal")
        
        return " • ".join(parts)
    
    @staticmethod
    def validate_filters(filters: Dict) -> Tuple[bool, Optional[str]]:
        """
        Validate filter values.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check date range
        if filters['start_date'] > filters['end_date']:
            return False, "Start date must be before end date"
        
        # Check KPI Center selection
        if not filters.get('kpi_center_ids'):
            return False, "Please select at least one KPI Center"
        
        # Check year range
        if filters['year'] < 2010 or filters['year'] > 2100:
            return False, "Invalid year selected"
        
        return True, None


# =============================================================================
# STANDALONE FUNCTIONS
# =============================================================================

def analyze_period(filter_values: Dict) -> Dict:
    """
    Analyze period to determine comparison type and which sections to show.
    
    Returns:
        Dictionary with:
        - is_historical: End date is in the past
        - is_multi_year: Period spans multiple years
        - years_in_period: List of years in period
        - show_backlog: Whether to show backlog/forecast section
        - show_forecast: Whether to show forecast (same as show_backlog)
        - comparison_type: 'multi_year' or 'yoy'
        - forecast_message: Message when forecast not shown
    """
    today = date.today()
    start = filter_values['start_date']
    end = filter_values['end_date']
    
    # Get list of years in period
    years_in_period = list(range(start.year, end.year + 1))
    is_multi_year = len(years_in_period) > 1
    
    # Historical = end date is in the past
    is_historical = end < today
    
    # Only show backlog for current/future periods
    show_backlog = end >= date(today.year, today.month, 1)
    
    # Forecast message
    forecast_message = ""
    if not show_backlog:
        forecast_message = f"📅 Historical period ({end.strftime('%Y-%m-%d')}) - forecast not applicable"
    
    return {
        'is_historical': is_historical,
        'is_multi_year': is_multi_year,
        'years_in_period': years_in_period,
        'show_backlog': show_backlog,
        'show_forecast': show_backlog,
        'comparison_type': 'multi_year' if is_multi_year else 'yoy',
        'forecast_message': forecast_message,
    }
