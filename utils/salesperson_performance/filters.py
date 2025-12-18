# utils/salesperson_performance/filters.py
"""
Sidebar Filter Components for Salesperson Performance

Renders filter UI elements:
- Period selector (YTD/QTD/MTD/Custom)
- Year selector
- Salesperson selector (role-based)
- Entity selector
- Internal revenue filter (NEW)
- YoY comparison toggle
- Metric view selector

CHANGELOG:
- v1.2.0: Added MultiSelectFilter with Excluded option
          - render_multiselect_filter(): Reusable filter component
          - apply_multiselect_filter(): Apply filter logic to DataFrame
          - FilterResult dataclass for clean return values
- v1.1.0: Added exclude_internal_revenue checkbox to filter out internal company revenue
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
import streamlit as st

from .constants import PERIOD_TYPES, MONTH_ORDER
from .access_control import AccessControl

logger = logging.getLogger(__name__)


# =============================================================================
# MULTISELECT FILTER WITH EXCLUDED OPTION
# =============================================================================

@dataclass
class FilterResult:
    """
    Result from a multiselect filter with excluded option.
    
    Attributes:
        selected: List of selected values (empty if "All" or nothing selected)
        excluded: True if "Excl" checkbox is ticked
        is_active: True if filter should be applied (has selections and not "All")
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
    
    Layout:
    ```
    Label                    ☐ Excl
    [Multiselect dropdown with tags    ]
    ```
    
    Args:
        label: Filter label (e.g., "Customer", "Brand")
        options: List of options to choose from
        key: Unique key for Streamlit widgets
        default_excluded: Default state of Excl checkbox (False = include mode)
        placeholder: Placeholder text for empty multiselect
        help_text: Optional help tooltip
        max_selections: Optional limit on number of selections
        container: Optional Streamlit container (default: st)
        
    Returns:
        FilterResult with selected values, excluded flag, and is_active flag
        
    Example:
        >>> result = render_multiselect_filter(
        ...     label="Brand",
        ...     options=["3M", "Henkel", "Momentive"],
        ...     key="brand_filter"
        ... )
        >>> if result.is_active:
        ...     if result.excluded:
        ...         df = df[~df['brand'].isin(result.selected)]
        ...     else:
        ...         df = df[df['brand'].isin(result.selected)]
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
    
    Args:
        df: DataFrame to filter
        column: Column name to filter on
        filter_result: FilterResult from render_multiselect_filter
        
    Returns:
        Filtered DataFrame
        
    Example:
        >>> brand_filter = render_multiselect_filter("Brand", brands, "brand")
        >>> df = apply_multiselect_filter(df, 'brand', brand_filter)
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


def render_filter_row(
    df: pd.DataFrame,
    filter_configs: List[Dict],
    num_columns: int = 5
) -> Dict[str, FilterResult]:
    """
    Render a row of multiselect filters with consistent layout.
    
    Args:
        df: DataFrame to get options from
        filter_configs: List of filter configurations, each containing:
            - column: DataFrame column name
            - label: Display label
            - key: Unique widget key
            - max_options: Optional limit on options shown (default 100)
            - sort: Whether to sort options (default True)
        num_columns: Number of columns in the row (default 5)
        
    Returns:
        Dict mapping column names to FilterResult objects
        
    Example:
        >>> filters = render_filter_row(sales_df, [
        ...     {'column': 'customer', 'label': 'Customer', 'key': 'cust'},
        ...     {'column': 'brand', 'label': 'Brand', 'key': 'brand'},
        ...     {'column': 'product_pn', 'label': 'Product', 'key': 'prod'},
        ... ])
        >>> for col, result in filters.items():
        ...     df = apply_multiselect_filter(df, col, result)
    """
    results = {}
    
    # Create columns
    cols = st.columns(num_columns)
    
    for idx, config in enumerate(filter_configs):
        col_idx = idx % num_columns
        
        column = config['column']
        label = config.get('label', column.replace('_', ' ').title())
        key = config.get('key', f"filter_{column}")
        max_options = config.get('max_options', 100)
        sort_options = config.get('sort', True)
        
        # Get options from DataFrame
        if column in df.columns:
            options = df[column].dropna().unique().tolist()
            if sort_options:
                options = sorted(options)
            if max_options and len(options) > max_options:
                options = options[:max_options]
        else:
            options = []
        
        with cols[col_idx]:
            results[column] = render_multiselect_filter(
                label=label,
                options=options,
                key=key
            )
    
    return results


def apply_all_filters(
    df: pd.DataFrame,
    filter_results: Dict[str, FilterResult]
) -> pd.DataFrame:
    """
    Apply multiple filters to a DataFrame.
    
    Args:
        df: DataFrame to filter
        filter_results: Dict from render_filter_row
        
    Returns:
        Filtered DataFrame
    """
    for column, result in filter_results.items():
        df = apply_multiselect_filter(df, column, result)
    return df


def get_active_filter_summary(filter_results: Dict[str, FilterResult]) -> str:
    """
    Get human-readable summary of active filters.
    
    Args:
        filter_results: Dict of filter results
        
    Returns:
        Summary string like "Brand: 3M, Henkel (excl) | Customer: VINFAST"
    """
    parts = []
    
    for column, result in filter_results.items():
        if result.is_active:
            label = column.replace('_', ' ').title()
            values = ', '.join(str(v) for v in result.selected[:3])
            if len(result.selected) > 3:
                values += f" +{len(result.selected) - 3} more"
            
            mode = " (excl)" if result.excluded else ""
            parts.append(f"{label}: {values}{mode}")
    
    return " | ".join(parts) if parts else "No filters applied"


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
    
    Args:
        label: Filter label
        key: Unique widget key
        placeholder: Placeholder text
        help_text: Optional help tooltip
        container: Optional Streamlit container
        
    Returns:
        TextSearchResult with query, excluded flag, and is_active flag
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
    
    Args:
        df: DataFrame to filter
        columns: List of column names to search in
        search_result: TextSearchResult from render_text_search_filter
        case_sensitive: Whether search is case-sensitive
        
    Returns:
        Filtered DataFrame
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
    
    Args:
        label: Filter label (e.g., "Min Amount ($)")
        key: Unique widget key
        default_min: Default minimum value
        step: Step increment
        help_text: Optional help tooltip
        container: Optional Streamlit container
        
    Returns:
        NumberRangeResult
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
    
    Args:
        df: DataFrame to filter
        column: Column name to filter on
        filter_result: NumberRangeResult
        
    Returns:
        Filtered DataFrame
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
# SALESPERSON FILTERS CLASS (Original - kept for backward compatibility)
# =============================================================================

class SalespersonFilters:
    """
    Sidebar filter components with role-based access control.
    
    Usage:
        access = AccessControl(user_role, employee_id)
        filters = SalespersonFilters(access)
        
        filter_values = filters.render_all_filters(
            salesperson_options_df,
            entity_options_df,
            available_years
        )
    """
    
    def __init__(self, access_control: AccessControl):
        """
        Initialize with access control.
        
        Args:
            access_control: AccessControl instance
        """
        self.access = access_control
    
    # =========================================================================
    # MAIN RENDER METHOD
    # =========================================================================
    
    def render_all_filters(
        self,
        salesperson_df: pd.DataFrame,
        entity_df: pd.DataFrame,
        available_years: List[int]
    ) -> Dict:
        """
        Render all sidebar filters and return selected values.
        
        Args:
            salesperson_df: Salesperson options (employee_id, sales_name)
            entity_df: Entity options (entity_id, entity_name)
            available_years: List of available years
            
        Returns:
            Dict with all filter values:
            {
                'period_type': str,
                'year': int,
                'start_date': date,
                'end_date': date,
                'employee_ids': List[int],
                'entity_ids': List[int],
                'compare_yoy': bool,
                'exclude_internal_revenue': bool,
                'metric_view': str
            }
        """
        st.sidebar.header("🎛️ Filters")
        
        # Period and Year
        period_type, year = self._render_period_year_selector(available_years)
        
        # Date range based on period
        start_date, end_date = self._render_date_range(period_type, year)
        
        st.sidebar.divider()
        
        # Salesperson filter (respects access control)
        employee_ids = self._render_salesperson_filter(salesperson_df)
        
        # Entity filter
        entity_ids = self._render_entity_filter(entity_df)
        
        st.sidebar.divider()
        
        # Display access info
        self._render_access_info()
        
        return {
            'period_type': period_type,
            'year': year,
            'start_date': start_date,
            'end_date': end_date,
            'employee_ids': employee_ids,
            'entity_ids': entity_ids,
            'compare_yoy': True,  # Always enabled
            'exclude_internal_revenue': True,  # Default exclude
        }
    
    def render_filter_form(
        self,
        salesperson_df: pd.DataFrame,
        entity_df: pd.DataFrame,
        default_start_date: date = None,
        default_end_date: date = None
    ) -> Tuple[Dict, bool]:
        """
        Render filters inside a form - only applies when user clicks Apply.
        This prevents page reruns on every filter change.
        
        Args:
            salesperson_df: Salesperson options
            entity_df: Entity options  
            default_start_date: Default start date (from DB - Jan 1 of latest sales year)
            default_end_date: Default end date (from DB - max backlog ETD or today)
        
        Returns:
            Tuple of (filter_values dict, submitted boolean)
        """
        # Initialize session state for filter values if not exists
        if 'applied_filters' not in st.session_state:
            st.session_state.applied_filters = None
        
        # Default dates if not provided
        today = date.today()
        if default_start_date is None:
            default_start_date = date(today.year, 1, 1)
        if default_end_date is None:
            default_end_date = today
        
        with st.sidebar:
            st.header("🎛️ Filters")
            
            with st.form("filter_form", border=False):
                # =====================================================
                # DATE RANGE (Simple picker - no period type needed)
                # =====================================================
                st.markdown("**📅 Date Range**")
                st.caption("📊 Applies to Sales data. Backlog shows full pipeline.")
                
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    start_date = st.date_input(
                        "Start",
                        value=default_start_date,
                        key="form_start_date",
                        help="Period start date. Sales/Invoice data will be filtered from this date."
                    )
                with col_d2:
                    end_date = st.date_input(
                        "End",
                        value=default_end_date,
                        key="form_end_date",
                        help="Period end date. If in the past, Forecast will not be available."
                    )
                
                # Validation
                if start_date > end_date:
                    st.error("⚠️ Start date must be before end date")
                    end_date = start_date
                
                # Derive year from start_date for KPI target matching
                year = start_date.year
                
                st.divider()
                
                # =====================================================
                # SALESPERSON FILTER
                # =====================================================
                st.markdown("**👤 Salesperson**")
                if salesperson_df.empty:
                    employee_ids = []
                    st.warning("No salespeople available")
                else:
                    all_salespeople = salesperson_df['sales_name'].tolist()
                    id_map = dict(zip(salesperson_df['sales_name'], salesperson_df['employee_id']))
                    
                    if self.access.get_access_level() == 'full':
                        options = ['All'] + all_salespeople
                        default = ['All']
                    elif self.access.get_access_level() == 'team':
                        team_ids = self.access.get_accessible_employee_ids()
                        team_names = salesperson_df[
                            salesperson_df['employee_id'].isin(team_ids)
                        ]['sales_name'].tolist()
                        options = ['All Team'] + team_names
                        default = ['All Team']
                    else:
                        my_id = self.access.employee_id
                        my_row = salesperson_df[salesperson_df['employee_id'] == my_id]
                        if not my_row.empty:
                            options = [my_row.iloc[0]['sales_name']]
                            default = options
                        else:
                            options = all_salespeople[:1] if all_salespeople else []
                            default = options
                    
                    selected_names = st.multiselect(
                        "Select",
                        options=options,
                        default=default,
                        key="form_salesperson",
                        label_visibility="collapsed"
                    )
                    
                    # Convert to IDs
                    if 'All' in selected_names:
                        employee_ids = list(id_map.values())
                    elif 'All Team' in selected_names:
                        employee_ids = self.access.get_accessible_employee_ids()
                    else:
                        employee_ids = [id_map[name] for name in selected_names if name in id_map]
                
                st.divider()
                
                # =====================================================
                # ENTITY FILTER
                # =====================================================
                st.markdown("**🏢 Legal Entity**")
                if entity_df.empty:
                    entity_ids = []
                else:
                    entity_options = ['All'] + entity_df['entity_name'].tolist()
                    entity_id_map = dict(zip(entity_df['entity_name'], entity_df['entity_id']))
                    
                    selected_entities = st.multiselect(
                        "Select",
                        options=entity_options,
                        default=['All'],
                        key="form_entity",
                        label_visibility="collapsed"
                    )
                    
                    if 'All' in selected_entities or not selected_entities:
                        entity_ids = []  # No filter
                    else:
                        entity_ids = [entity_id_map[name] for name in selected_entities if name in entity_id_map]
                
                st.divider()
                
                # =====================================================
                # SUBMIT BUTTON
                # =====================================================
                submitted = st.form_submit_button(
                    "🔍 Apply Filters",
                    use_container_width=True,
                    type="primary"
                )
            
            # Show access info outside form
            self._render_access_info()
        
        # Determine period type based on date range
        period_type = self._infer_period_type(start_date, end_date, year)
        
        filter_values = {
            'period_type': period_type,
            'year': year,
            'start_date': start_date,
            'end_date': end_date,
            'employee_ids': employee_ids,
            'entity_ids': entity_ids,
            'compare_yoy': True,
            'exclude_internal_revenue': True,
        }
        
        return filter_values, submitted
    
    def _infer_period_type(self, start_date: date, end_date: date, year: int) -> str:
        """Infer period type from date range."""
        today = date.today()
        
        # Check if YTD
        if start_date == date(year, 1, 1):
            if end_date >= today or end_date == date(year, 12, 31):
                return 'YTD'
        
        # Check if QTD
        quarter_starts = [date(year, 1, 1), date(year, 4, 1), date(year, 7, 1), date(year, 10, 1)]
        if start_date in quarter_starts:
            return 'QTD'
        
        # Check if MTD
        if start_date.day == 1 and start_date.month == end_date.month:
            return 'MTD'
        
        return 'Custom'
    
    # =========================================================================
    # PERIOD & DATE SELECTORS
    # =========================================================================
    
    def _render_period_year_selector(
        self,
        available_years: List[int]
    ) -> Tuple[str, int]:
        """Render period type and year selectors."""
        col1, col2 = st.sidebar.columns(2)
        
        with col1:
            period_type = st.selectbox(
                "📅 Period",
                options=PERIOD_TYPES,
                index=0,
                key="filter_period"
            )
        
        with col2:
            current_year = datetime.now().year
            if not available_years:
                available_years = [current_year, current_year - 1]
            
            year = st.selectbox(
                "📆 Year",
                options=sorted(available_years, reverse=True),
                index=0,
                key="filter_year"
            )
        
        return period_type, int(year)
    
    def _render_date_range(
        self,
        period_type: str,
        year: int
    ) -> Tuple[date, date]:
        """Calculate and optionally render custom date range."""
        start_date, end_date = self._calculate_period_dates(period_type, year)
        
        if period_type == 'Custom':
            col1, col2 = st.sidebar.columns(2)
            with col1:
                start_date = st.date_input(
                    "Start Date",
                    value=start_date,
                    key="filter_start_date"
                )
            with col2:
                end_date = st.date_input(
                    "End Date",
                    value=end_date,
                    key="filter_end_date"
                )
        else:
            # Show calculated range as info
            st.sidebar.caption(
                f"📅 {start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"
            )
        
        return start_date, end_date
    
    @staticmethod
    def _calculate_period_dates(period_type: str, year: int) -> Tuple[date, date]:
        """Calculate start and end dates for period type."""
        today = date.today()
        year = int(year)
        
        if period_type == 'YTD':
            start = date(year, 1, 1)
            end = min(today, date(year, 12, 31))
        
        elif period_type == 'QTD':
            current_quarter = (today.month - 1) // 3 + 1
            quarter_start_month = (current_quarter - 1) * 3 + 1
            start = date(year, quarter_start_month, 1)
            end = min(today, date(year, 12, 31))
        
        elif period_type == 'MTD':
            start = date(year, today.month, 1)
            end = today
        
        else:  # Custom
            start = date(year, 1, 1)
            end = min(today, date(year, 12, 31))
        
        return start, end
    
    # =========================================================================
    # SALESPERSON FILTER
    # =========================================================================
    
    def _render_salesperson_filter(
        self,
        salesperson_df: pd.DataFrame
    ) -> List[int]:
        """Render salesperson filter based on access level."""
        if salesperson_df.empty:
            st.sidebar.warning("No salespeople available")
            return []
        
        access_level = self.access.get_access_level()
        
        # Build options based on access level
        all_salespeople = salesperson_df['sales_name'].tolist()
        id_map = dict(zip(
            salesperson_df['sales_name'],
            salesperson_df['employee_id']
        ))
        
        if access_level == 'full':
            options = ['All'] + all_salespeople
            default = ['All']
            label = "👤 Salesperson"
        
        elif access_level == 'team':
            # Filter to team members only
            team_ids = self.access.get_accessible_employee_ids()
            team_names = salesperson_df[
                salesperson_df['employee_id'].isin(team_ids)
            ]['sales_name'].tolist()
            
            options = ['All Team'] + team_names
            default = ['All Team']
            label = "👥 Team Member"
        
        else:
            # Self only
            my_id = self.access.employee_id
            my_row = salesperson_df[salesperson_df['employee_id'] == my_id]
            
            if not my_row.empty:
                my_name = my_row.iloc[0]['sales_name']
                return [my_id]  # No selection needed
            else:
                return []
        
        # Render multiselect
        selected = st.sidebar.multiselect(
            label,
            options=options,
            default=default,
            key="filter_salesperson"
        )
        
        # Convert to IDs
        if 'All' in selected:
            return list(id_map.values())
        elif 'All Team' in selected:
            return self.access.get_accessible_employee_ids()
        else:
            return [id_map[name] for name in selected if name in id_map]
    
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
        
        selected = st.sidebar.multiselect(
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
        access_level = self.access.get_access_level()
        team_size = self.access.get_team_size()
        
        # Icon and label based on access level
        if access_level == 'full':
            icon = "🔓"
            label = "Full Access"
        elif access_level == 'team':
            icon = "👥"
            label = f"Team Access ({team_size} members)"
        else:
            icon = "👤"
            label = "Personal View"
        
        st.sidebar.caption(f"{icon} {label}")
    
    # =========================================================================
    # QUICK FILTERS (Alternative Rendering)
    # =========================================================================
    
    def render_quick_period_buttons(self) -> str:
        """
        Render quick period selection as buttons (alternative to dropdown).
        Can be used in main content area.
        """
        col1, col2, col3, col4 = st.columns(4)
        
        period = 'YTD'  # Default
        
        with col1:
            if st.button("YTD", use_container_width=True):
                period = 'YTD'
        
        with col2:
            if st.button("QTD", use_container_width=True):
                period = 'QTD'
        
        with col3:
            if st.button("MTD", use_container_width=True):
                period = 'MTD'
        
        with col4:
            if st.button("Custom", use_container_width=True):
                period = 'Custom'
        
        return period
    
    # =========================================================================
    # FILTER STATE HELPERS
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
        
        # Salespeople count
        emp_count = len(filters.get('employee_ids', []))
        if emp_count == 1:
            parts.append("1 salesperson")
        elif emp_count > 1:
            parts.append(f"{emp_count} salespeople")
        
        # Internal revenue status (NEW)
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
        
        # Check employee selection
        if not filters.get('employee_ids'):
            return False, "Please select at least one salesperson"
        
        # Check year range (reasonable bounds)
        if filters['year'] < 2010 or filters['year'] > 2100:
            return False, "Invalid year selected"
        
        return True, None


# =============================================================================
# STANDALONE FILTER FUNCTIONS
# =============================================================================

def render_period_selector_simple() -> Tuple[str, int, date, date]:
    """
    Simple period selector without access control.
    Returns: (period_type, year, start_date, end_date)
    """
    col1, col2 = st.columns(2)
    
    with col1:
        period_type = st.selectbox(
            "Period",
            options=PERIOD_TYPES,
            index=0
        )
    
    with col2:
        current_year = datetime.now().year
        year = st.selectbox(
            "Year",
            options=[current_year, current_year - 1, current_year - 2],
            index=0
        )
    
    start_date, end_date = SalespersonFilters._calculate_period_dates(period_type, year)
    
    return period_type, year, start_date, end_date


def analyze_period(filter_values: Dict) -> Dict:
    """
    Analyze period to determine comparison type and which sections to show.
    
    Args:
        filter_values: Dict containing start_date, end_date, year
        
    Returns:
        Dict with:
        - is_historical: True if end_date < today
        - is_multi_year: True if period spans more than 1 year
        - years_in_period: List of years covered [2023, 2024, 2025]
        - show_backlog: True if backlog section should be shown
        - comparison_type: 'yoy' or 'multi_year'
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
    # Allow if end_date is within current month or future
    show_backlog = end >= date(today.year, today.month, 1)
    
    return {
        'is_historical': is_historical,
        'is_multi_year': is_multi_year,
        'years_in_period': years_in_period,
        'show_backlog': show_backlog,
        'comparison_type': 'multi_year' if is_multi_year else 'yoy',
    }