# utils/kpi_center_performance/filters.py
"""
Sidebar Filter Components for KPI Center Performance

Renders filter UI elements:
- Period selector (YTD/QTD/MTD/Custom) with radio buttons
- Date range (auto-calculated for YTD/QTD/MTD, manual for Custom)
- KPI Center selector with type grouping
- Entity selector
- Internal revenue filter
- YoY comparison toggle
- KPI Type filter
- Refresh button with cache info

VERSION: 2.1.0
CHANGELOG:
- v2.1.0: UPDATED Date Range UI to match Salesperson page
          - Removed Year dropdown (auto-detect from available_years)
          - YTD/QTD/MTD default to latest year in data
          - Compact "Start" / "End" labels
          - Added help tooltip explaining date auto-calculation
          - Added "Date Range" section header
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
        # Exclude mode: remove rows with selected values
        return df[~df[column].isin(filter_result.selected)]
    else:
        # Include mode: keep only rows with selected values
        return df[df[column].isin(filter_result.selected)]


def render_text_search_filter(
    label: str,
    key: str,
    placeholder: str = "Search...",
    help_text: str = None,
    container = None
) -> str:
    """
    Render a text search filter.
    
    Args:
        label: Filter label
        key: Unique key for widget
        placeholder: Placeholder text
        help_text: Optional help tooltip
        container: Optional Streamlit container
        
    Returns:
        Search string (empty if nothing entered)
    """
    ctx = container if container else st
    
    return ctx.text_input(
        label,
        placeholder=placeholder,
        key=key,
        help=help_text,
        label_visibility="collapsed" if not label else "visible"
    )


def apply_text_search_filter(
    df: pd.DataFrame,
    columns: List[str],
    search_text: str,
    case_sensitive: bool = False
) -> pd.DataFrame:
    """
    Apply text search filter across multiple columns.
    
    Args:
        df: DataFrame to filter
        columns: List of columns to search in
        search_text: Text to search for
        case_sensitive: Whether search is case-sensitive
        
    Returns:
        Filtered DataFrame
    """
    if df.empty or not search_text:
        return df
    
    # Build mask for OR across columns
    mask = pd.Series([False] * len(df), index=df.index)
    
    for col in columns:
        if col in df.columns:
            col_str = df[col].fillna('').astype(str)
            if case_sensitive:
                mask = mask | col_str.str.contains(search_text, regex=False)
            else:
                mask = mask | col_str.str.lower().str.contains(search_text.lower(), regex=False)
    
    return df[mask]


def render_number_filter(
    label: str,
    key: str,
    min_value: float = None,
    max_value: float = None,
    default_value: float = None,
    step: float = None,
    help_text: str = None,
    container = None
) -> Optional[float]:
    """
    Render a number input filter.
    """
    ctx = container if container else st
    
    return ctx.number_input(
        label,
        min_value=min_value,
        max_value=max_value,
        value=default_value,
        step=step,
        key=key,
        help=help_text
    )


def apply_number_filter(
    df: pd.DataFrame,
    column: str,
    min_val: float = None,
    max_val: float = None
) -> pd.DataFrame:
    """
    Apply number range filter to DataFrame.
    """
    if df.empty:
        return df
    
    if column not in df.columns:
        return df
    
    result = df.copy()
    
    if min_val is not None:
        result = result[result[column] >= min_val]
    
    if max_val is not None:
        result = result[result[column] <= max_val]
    
    return result


# =============================================================================
# SMART CACHING SESSION STATE
# =============================================================================

def _get_cached_year_range() -> Tuple[Optional[int], Optional[int]]:
    """Get currently cached year range from session state."""
    start = st.session_state.get('_kpc_cached_start_year')
    end = st.session_state.get('_kpc_cached_end_year')
    return start, end


def _set_cached_year_range(start_year: int, end_year: int):
    """Store cached year range in session state."""
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
        filter_values = filters.render_sidebar_filters(kpi_center_df, entity_df, available_years)
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
        
        UPDATED v2.1.0: Date range logic now matches Salesperson page.
        - No Year dropdown - auto-detect from available_years
        - YTD/QTD/MTD default to latest year in data
        
        Returns:
            Dictionary of filter values
        """
        st.sidebar.title("🎯 KPI Center Filters")
        
        # Show access info
        self._render_access_info()
        
        st.sidebar.divider()
        
        # Determine latest year from available data
        current_year = datetime.now().year
        years = available_years or [current_year, current_year - 1, current_year - 2]
        latest_year = max(years) if years else current_year
        
        # Use form to batch updates
        with st.sidebar.form("kpi_center_filters"):
            # =================================================================
            # DATE RANGE SECTION (UPDATED v2.1.0 - Match Salesperson)
            # =================================================================
            st.markdown("**📅 Date Range**")
            st.caption("Applies to Sales data. Backlog shows full pipeline.")
            
            # Period Type
            period_type = st.radio(
                "Period",
                options=PERIOD_TYPES,
                horizontal=True,
                key="filter_period_type",
                help=self._get_period_help_text(latest_year),
                label_visibility="collapsed"
            )
            
            # Calculate default dates based on period type
            default_start, default_end = self._calculate_period_dates(period_type, latest_year)
            
            # Date inputs - compact layout matching Salesperson
            col_start, col_end = st.columns(2)
            
            with col_start:
                custom_start = st.date_input(
                    "Start",
                    value=default_start,
                    key="filter_start_date",
                    help=self._get_start_date_help(period_type, latest_year)
                )
            
            with col_end:
                custom_end = st.date_input(
                    "End",
                    value=default_end,
                    key="filter_end_date",
                    help=self._get_end_date_help(period_type, latest_year)
                )
            
            st.divider()
            
            # =================================================================
            # KPI CENTER FILTERS
            # =================================================================
            
            # Only with KPI assignment checkbox
            only_with_kpi = st.checkbox(
                "Only with KPI assignment",
                value=True,
                key="filter_only_with_kpi",
                help="Show only KPI Centers that have KPI targets assigned for the selected year"
            )
            
            # Determine year for KPI filter based on date range
            filter_year = custom_start.year if custom_start else latest_year
            
            # KPI Center selector
            kpi_center_ids = self._render_kpi_center_filter(
                kpi_center_df, filter_year, only_with_kpi
            )
            
            # KPI Type filter (TERRITORY, INTERNAL, etc.)
            kpi_type_filter = self._render_kpi_type_filter(kpi_center_df)
            
            # Entity filter
            entity_ids = []
            if entity_df is not None and not entity_df.empty:
                entity_ids = self._render_entity_filter(entity_df)
            
            st.divider()
            
            # =================================================================
            # ADDITIONAL OPTIONS
            # =================================================================
            
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
        # REFRESH BUTTON (Outside form)
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
        
        # Calculate final dates based on period type
        start_date, end_date = self._get_period_dates(
            period_type, filter_year, custom_start, custom_end
        )
        
        # Store in session state
        filter_values = {
            'period_type': period_type,
            'year': start_date.year,  # Year derived from dates
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
        
        # Always show filter summary
        self._show_filter_summary(filter_values)
        
        return filter_values
    
    # =========================================================================
    # PERIOD HANDLING (UPDATED v2.1.0)
    # =========================================================================
    
    def _get_period_help_text(self, year: int) -> str:
        """Get detailed help text for period selector."""
        today = date.today()
        
        # YTD dates
        ytd_start = date(year, 1, 1)
        ytd_end = today if year == today.year else date(year, 12, 31)
        
        # QTD dates
        current_quarter = (today.month - 1) // 3 + 1
        quarter_start_month = (current_quarter - 1) * 3 + 1
        qtd_start = date(year, quarter_start_month, 1)
        qtd_end = today if year == today.year else date(year, 12, 31)
        
        # MTD dates
        if year == today.year:
            mtd_start = date(year, today.month, 1)
            mtd_end = today
        else:
            mtd_start = date(year, 12, 1)
            mtd_end = date(year, 12, 31)
        
        return f"""
**Period Types for {year}:**

• **YTD** (Year to Date): {ytd_start.strftime('%b %d')} → {ytd_end.strftime('%b %d, %Y')}
• **QTD** (Quarter to Date): {qtd_start.strftime('%b %d')} → {qtd_end.strftime('%b %d, %Y')}
• **MTD** (Month to Date): {mtd_start.strftime('%b %d')} → {mtd_end.strftime('%b %d, %Y')}
• **Custom**: Select your own date range

Dates are auto-calculated. For Custom, edit the Start/End fields.
        """.strip()
    
    def _get_start_date_help(self, period_type: str, year: int) -> str:
        """Get help text for start date input."""
        if period_type == 'Custom':
            return "Select start date for custom period"
        else:
            return f"Auto-calculated for {period_type}. Switch to 'Custom' to change."
    
    def _get_end_date_help(self, period_type: str, year: int) -> str:
        """Get help text for end date input."""
        if period_type == 'Custom':
            return "Select end date for custom period"
        else:
            return f"Auto-calculated for {period_type}. Switch to 'Custom' to change."
    
    @staticmethod
    def _calculate_period_dates(period_type: str, year: int) -> Tuple[date, date]:
        """
        Calculate default start and end dates for a period type.
        Used for setting initial values in date inputs.
        
        Args:
            period_type: YTD, QTD, MTD, or Custom
            year: Target year (latest year from data)
            
        Returns:
            Tuple of (start_date, end_date)
        """
        today = date.today()
        year = int(year)
        
        if period_type == 'YTD':
            start = date(year, 1, 1)
            end = today if year == today.year else date(year, 12, 31)
        
        elif period_type == 'QTD':
            current_quarter = (today.month - 1) // 3 + 1
            quarter_start_month = (current_quarter - 1) * 3 + 1
            start = date(year, quarter_start_month, 1)
            end = today if year == today.year else date(year, 12, 31)
        
        elif period_type == 'MTD':
            if year == today.year:
                start = date(year, today.month, 1)
                end = today
            else:
                # For past years, show December
                start = date(year, 12, 1)
                end = date(year, 12, 31)
        
        else:  # Custom
            start = date(year, 1, 1)
            end = min(today, date(year, 12, 31))
        
        return start, end
    
    def _get_period_dates(
        self,
        period_type: str,
        year: int,
        custom_start: date,
        custom_end: date
    ) -> Tuple[date, date]:
        """
        Calculate final start and end dates based on period type.
        
        For Custom, uses the provided dates.
        For YTD/QTD/MTD, calculates automatically.
        """
        if period_type == 'Custom':
            return custom_start, custom_end
        
        return self._calculate_period_dates(period_type, year)
    
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
        filtered_df = kpi_center_df.copy()
        hidden_count = 0
        
        if only_with_kpi:
            kpi_centers_with_assignment = _get_kpi_centers_with_assignments([year])
            if kpi_centers_with_assignment:
                original_count = len(filtered_df)
                filtered_df = filtered_df[
                    filtered_df['kpi_center_id'].isin(kpi_centers_with_assignment)
                ]
                hidden_count = original_count - len(filtered_df)
        
        if filtered_df.empty:
            st.warning("No KPI Centers with assignments for this year")
            return []
        
        # Show count of KPI Centers with/without KPI
        if only_with_kpi and hidden_count > 0:
            st.caption(f"📋 {len(filtered_df)} with KPI ({hidden_count} hidden)")
        
        # Build options grouped by type
        all_kpi_centers = filtered_df['kpi_center_name'].tolist()
        id_map = dict(zip(
            filtered_df['kpi_center_name'],
            filtered_df['kpi_center_id']
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