# utils/kpi_center_performance/filters.py
"""
Sidebar Filter Components for KPI Center Performance

Renders filter UI elements:
- Period selector (YTD/QTD/MTD/Custom) with radio buttons
- Date range with default from database
- KPI Center selector with type grouping
- Entity selector
- Internal revenue filter
- YoY comparison toggle
- KPI Type filter

VERSION: 2.2.0
CHANGELOG:
- v2.2.0: SYNCED UI with Salesperson page (Issue #xxx)
          - Period definitions now shown as visible text block (not just tooltip)
          - Identical tooltip format for Start/End date inputs
          - Same caption "Applies to Sales data. Backlog shows full pipeline."
          - Consistent visual hierarchy
- v2.1.0: SYNCED Date Range UI with Salesperson page
          - Same layout: Date Range header → Period radio → Start/End inputs
          - Same logic: YTD/QTD/MTD use current_year (today.year)
          - Same tooltip: Shows exact date ranges for current year
          - Date inputs receive default_start_date/default_end_date from DB
          - Year derived from dates, no separate Year dropdown
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


# =============================================================================
# TEXT SEARCH FILTER
# =============================================================================

@dataclass
class TextSearchResult:
    """Result from text search filter."""
    query: str
    excluded: bool
    is_active: bool


def render_text_search_filter(
    label: str,
    key: str,
    placeholder: str = "Search...",
    help_text: str = None,
    container = None
) -> TextSearchResult:
    """
    Render a text search filter with Excl option.
    """
    ctx = container if container else st
    
    # Header row
    col_label, col_excl = ctx.columns([4, 1])
    
    with col_label:
        ctx.markdown(f"**{label}**")
    
    with col_excl:
        excluded = ctx.checkbox(
            "Excl",
            value=False,
            key=f"{key}_excl",
            help="Tick to EXCLUDE items matching search"
        )
    
    # Text input
    query = ctx.text_input(
        label=label,
        placeholder=placeholder,
        key=f"{key}_input",
        help=help_text,
        label_visibility="collapsed"
    )
    
    return TextSearchResult(
        query=query.strip(),
        excluded=excluded,
        is_active=bool(query.strip())
    )


def apply_text_search_filter(
    df: pd.DataFrame,
    columns: List[str],
    search_result: TextSearchResult,
    case_sensitive: bool = False
) -> pd.DataFrame:
    """
    Apply text search filter to DataFrame (searches across multiple columns).
    """
    if df.empty or not search_result.is_active:
        return df
    
    query = search_result.query
    if not case_sensitive:
        query = query.lower()
    
    # Build combined mask across all columns
    combined_mask = pd.Series([False] * len(df), index=df.index)
    
    for column in columns:
        if column in df.columns:
            col_values = df[column].astype(str)
            if not case_sensitive:
                col_values = col_values.str.lower()
            
            mask = col_values.str.contains(query, na=False, regex=False)
            combined_mask = combined_mask | mask
    
    if search_result.excluded:
        return df[~combined_mask]
    else:
        return df[combined_mask]


# =============================================================================
# NUMBER RANGE FILTER
# =============================================================================

@dataclass
class NumberRangeResult:
    """Result from number range filter."""
    min_value: Optional[float]
    max_value: Optional[float]
    excluded: bool
    is_active: bool


def render_number_filter(
    label: str,
    key: str,
    default_min: float = 0,
    step: float = 1000,
    help_text: str = None,
    container = None
) -> NumberRangeResult:
    """
    Render a minimum number filter with Excl option.
    """
    ctx = container if container else st
    
    # Header row
    col_label, col_excl = ctx.columns([4, 1])
    
    with col_label:
        ctx.markdown(f"**{label}**")
    
    with col_excl:
        excluded = ctx.checkbox(
            "Excl",
            value=False,
            key=f"{key}_excl",
            help="Tick to EXCLUDE items matching this condition"
        )
    
    # Number input
    min_value = ctx.number_input(
        label=label,
        value=default_min,
        step=step,
        key=f"{key}_input",
        help=help_text,
        label_visibility="collapsed"
    )
    
    return NumberRangeResult(
        min_value=min_value if min_value > 0 else None,
        max_value=None,
        excluded=excluded,
        is_active=min_value > 0
    )


def apply_number_filter(
    df: pd.DataFrame,
    column: str,
    filter_result: NumberRangeResult
) -> pd.DataFrame:
    """
    Apply number filter to DataFrame.
    """
    if df.empty or not filter_result.is_active:
        return df
    
    if column not in df.columns:
        return df
    
    if filter_result.min_value is not None:
        if filter_result.excluded:
            # Exclude: keep rows BELOW min
            return df[df[column] < filter_result.min_value]
        else:
            # Include: keep rows AT OR ABOVE min
            return df[df[column] >= filter_result.min_value]
    
    return df


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
    
    SYNCED with Salesperson filters v2.2.0:
    - Period definitions shown as visible text block above radio buttons
    - Same date range logic and UI layout
    - Same period type behavior (YTD/QTD/MTD for current_year)
    - Identical tooltip text for Start/End inputs
    - Same caption note about Sales data vs Backlog
    
    Usage:
        filters = KPICenterFilters(access)
        filter_values, submitted = filters.render_filter_form(
            kpi_center_df, entity_df, default_start, default_end
        )
    """
    
    def __init__(self, access: AccessControl):
        """Initialize with access control."""
        self.access = access
    
    def render_filter_form(
        self,
        kpi_center_df: pd.DataFrame,
        entity_df: pd.DataFrame = None,
        default_start_date: date = None,
        default_end_date: date = None
    ) -> Tuple[Dict, bool]:
        """
        Render ALL filters inside a form - only applies when user clicks Apply.
        This prevents page reruns on every filter change.
        
        SYNCED v2.2.0 with Salesperson logic:
        - Period definitions displayed as visible text block (not hidden in tooltip)
        - YTD/QTD/MTD: Auto-calculate for CURRENT YEAR (today.year)
        - Custom: Date inputs enabled for any date range selection
        - Date inputs show default values from database
        - Identical tooltip: "Start/End date for Custom mode. Ignored when YTD/QTD/MTD is selected."
        
        Args:
            kpi_center_df: KPI Center options
            entity_df: Entity options  
            default_start_date: Default start date (from DB - Jan 1 of latest sales year)
            default_end_date: Default end date (from DB - max backlog ETD or today)
        
        Returns:
            Tuple of (filter_values dict, submitted boolean)
        """
        # Default dates if not provided
        today = date.today()
        current_year = today.year
        
        if default_start_date is None:
            default_start_date = date(current_year, 1, 1)
        if default_end_date is None:
            default_end_date = today
        
        # Pre-calculate date ranges for CURRENT YEAR (same as Salesperson)
        current_quarter = (today.month - 1) // 3 + 1
        quarter_start_month = (current_quarter - 1) * 3 + 1
        
        ytd_start = date(current_year, 1, 1)
        ytd_end = today
        
        qtd_start = date(current_year, quarter_start_month, 1)
        qtd_end = today
        
        mtd_start = date(current_year, today.month, 1)
        mtd_end = today
        
        with st.sidebar:
            st.header("🎯 KPI Center Filters")
            
            # Show access info at top
            self._render_access_info()
            
            st.divider()
            
            # =================================================================
            # ALL FILTERS INSIDE FORM - NO RERUN UNTIL "Apply Filters" CLICKED
            # =================================================================
            with st.form("kpi_center_filter_form", border=False):
                
                # =============================================================
                # DATE RANGE SECTION (SYNCED with Salesperson v2.1.0)
                # =============================================================
                st.markdown("**📅 Date Range**")
                st.caption("Applies to Sales data. Backlog shows full pipeline.")
                
                # Display period definitions as visible text block (same as Salesperson)
                # This shows users exactly what each period means BEFORE they select
                st.markdown(
                    f"<div style='font-size: 12px; color: #666; line-height: 1.6; margin-bottom: 8px;'>"
                    f"<b>YTD</b> (Year to Date): Jan 01 → {ytd_end.strftime('%b %d, %Y')}<br>"
                    f"<b>QTD</b> (Q{current_quarter} to Date): {qtd_start.strftime('%b %d')} → {qtd_end.strftime('%b %d, %Y')}<br>"
                    f"<b>MTD</b> ({today.strftime('%B')} to Date): {mtd_start.strftime('%b %d')} → {mtd_end.strftime('%b %d, %Y')}<br>"
                    f"<b>Custom</b>: Select any date range using Start/End inputs"
                    f"</div>",
                    unsafe_allow_html=True
                )
                
                # Period type radio (same layout as Salesperson)
                period_type = st.radio(
                    "Period",
                    options=['YTD', 'QTD', 'MTD', 'Custom'],
                    index=0,  # Default to YTD
                    horizontal=True,
                    key="form_period_type",
                    help="Select time period for analysis"
                )
                
                # Date inputs - ALWAYS VISIBLE but only used for Custom mode
                # Tooltip clearly indicates behavior (same as Salesperson)
                col_start, col_end = st.columns(2)
                
                with col_start:
                    start_date_input = st.date_input(
                        "Start",
                        value=default_start_date,
                        key="form_start_date",
                        help="Start date for Custom mode. Ignored when YTD/QTD/MTD is selected."
                    )
                
                with col_end:
                    end_date_input = st.date_input(
                        "End",
                        value=default_end_date,
                        key="form_end_date",
                        help="End date for Custom mode. Ignored when YTD/QTD/MTD is selected."
                    )
                
                st.divider()
                
                # =============================================================
                # KPI FILTER CHECKBOX
                # =============================================================
                only_with_kpi = st.checkbox(
                    "Only with KPI assignment",
                    value=True,
                    key="form_only_with_kpi",
                    help=(
                        "Show only KPI Centers that have KPI targets assigned for the selected period. "
                        "Uncheck to include all KPI Centers."
                    )
                )
                
                # Pre-fetch KPI Center IDs for filtering
                kpi_check_years = [current_year]
                kpi_center_ids_with_kpi = []
                filtered_kpi_center_df = kpi_center_df.copy()
                
                if only_with_kpi and not kpi_center_df.empty:
                    kpi_center_ids_with_kpi = _get_kpi_centers_with_assignments(kpi_check_years)
                    if kpi_center_ids_with_kpi:
                        filtered_kpi_center_df = kpi_center_df[
                            kpi_center_df['kpi_center_id'].isin(kpi_center_ids_with_kpi)
                        ]
                        excluded_count = len(kpi_center_df) - len(filtered_kpi_center_df)
                        if excluded_count > 0:
                            st.caption(f"📋 {len(filtered_kpi_center_df)} with KPI ({excluded_count} hidden)")
                
                # =============================================================
                # KPI CENTER FILTER
                # =============================================================
                st.markdown("**🎯 KPI Center**")
                
                if filtered_kpi_center_df.empty:
                    kpi_center_ids = []
                    st.warning("No KPI Centers available")
                else:
                    all_kpi_centers = filtered_kpi_center_df['kpi_center_name'].tolist()
                    id_map = dict(zip(
                        filtered_kpi_center_df['kpi_center_name'],
                        filtered_kpi_center_df['kpi_center_id']
                    ))
                    
                    options = ['All'] + all_kpi_centers
                    
                    selected_names = st.multiselect(
                        "Select KPI Centers",
                        options=options,
                        default=['All'],
                        key="form_kpi_center",
                        label_visibility="collapsed"
                    )
                    
                    # Convert to IDs
                    if 'All' in selected_names or not selected_names:
                        kpi_center_ids = list(id_map.values())
                    else:
                        kpi_center_ids = [id_map[name] for name in selected_names if name in id_map]
                
                # =============================================================
                # KPI TYPE FILTER
                # =============================================================
                kpi_type_filter = None
                if not kpi_center_df.empty and 'kpi_type' in kpi_center_df.columns:
                    types = kpi_center_df['kpi_type'].dropna().unique().tolist()
                    if types:
                        kpi_type_options = ['All Types'] + sorted(types)
                        selected_type = st.selectbox(
                            "KPI Type",
                            options=kpi_type_options,
                            index=0,
                            key="form_kpi_type",
                            help="Filter by KPI Center type (e.g., TERRITORY, INTERNAL)"
                        )
                        if selected_type != 'All Types':
                            kpi_type_filter = selected_type
                
                st.divider()
                
                # =============================================================
                # ENTITY FILTER
                # =============================================================
                st.markdown("**🏢 Legal Entity**")
                
                entity_ids = []
                if entity_df is not None and not entity_df.empty:
                    entity_options = ['All'] + entity_df['entity_name'].tolist()
                    entity_id_map = dict(zip(
                        entity_df['entity_name'],
                        entity_df['entity_id']
                    ))
                    
                    selected_entities = st.multiselect(
                        "Select entities",
                        options=entity_options,
                        default=['All'],
                        key="form_entity",
                        label_visibility="collapsed"
                    )
                    
                    if 'All' in selected_entities or not selected_entities:
                        entity_ids = []  # No filter
                    else:
                        entity_ids = [
                            entity_id_map[name]
                            for name in selected_entities
                            if name in entity_id_map
                        ]
                
                st.divider()
                
                # =============================================================
                # EXCLUDE INTERNAL REVENUE
                # =============================================================
                exclude_internal = st.checkbox(
                    "Exclude internal revenue",
                    value=True,
                    key="form_exclude_internal",
                    help=(
                        "Exclude revenue from internal company transactions. "
                        "Gross Profit is kept intact for accurate GP% calculation."
                    )
                )
                
                st.divider()
                
                # =============================================================
                # SUBMIT BUTTON
                # =============================================================
                submitted = st.form_submit_button(
                    "🔍 Apply Filters",
                    use_container_width=True,
                    type="primary"
                )
        
        # =================================================================
        # DETERMINE ACTUAL DATES BASED ON PERIOD TYPE (same as Salesperson)
        # =================================================================
        if period_type == 'YTD':
            start_date = ytd_start
            end_date = ytd_end
            year = current_year
        elif period_type == 'QTD':
            start_date = qtd_start
            end_date = qtd_end
            year = current_year
        elif period_type == 'MTD':
            start_date = mtd_start
            end_date = mtd_end
            year = current_year
        else:  # Custom
            start_date = start_date_input
            end_date = end_date_input
            # Validation
            if start_date > end_date:
                end_date = start_date
            # Use start_date's year for KPI matching
            year = start_date.year
        
        # Build filter values dict
        filter_values = {
            'period_type': period_type,
            'year': year,
            'start_date': start_date,
            'end_date': end_date,
            'kpi_center_ids': kpi_center_ids,
            'kpi_type_filter': kpi_type_filter,
            'entity_ids': entity_ids,
            'exclude_internal_revenue': exclude_internal,
            'show_yoy': True,  # Always enabled
            'only_with_kpi': only_with_kpi,
        }
        
        return filter_values, submitted
    
    # =========================================================================
    # LEGACY METHOD - For backward compatibility
    # =========================================================================
    
    def render_sidebar_filters(
        self,
        kpi_center_df: pd.DataFrame,
        entity_df: pd.DataFrame = None,
        available_years: List[int] = None
    ) -> Dict:
        """
        Legacy method - redirects to render_filter_form for backward compatibility.
        """
        filter_values, _ = self.render_filter_form(
            kpi_center_df=kpi_center_df,
            entity_df=entity_df
        )
        filter_values['submitted'] = True  # Always consider as submitted for legacy
        return filter_values
    
    # =========================================================================
    # ACCESS INFO
    # =========================================================================
    
    def _render_access_info(self):
        """Display access level info in sidebar."""
        if self.access.can_access_page():
            st.caption("🔓 Full Access - All KPI Centers")
        else:
            st.error("🚫 Access Denied")
    
    # =========================================================================
    # FILTER SUMMARY
    # =========================================================================
    
    @staticmethod
    def get_filter_summary(filters: Dict) -> str:
        """Get human-readable summary of current filters."""
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