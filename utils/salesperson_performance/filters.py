# utils/salesperson_performance/filters.py
"""
Sidebar Filter Components for Salesperson Performance

Renders filter UI elements:
- Period selector (YTD/QTD/MTD/Custom)
- Year selector
- Salesperson selector (role-based)
- Entity selector
- YoY comparison toggle
- Metric view selector
"""

import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import streamlit as st

from .constants import PERIOD_TYPES, MONTH_ORDER
from .access_control import AccessControl

logger = logging.getLogger(__name__)


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
        }
    
    # =========================================================================
    # PERIOD & YEAR SELECTORS
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
                index=0,  # Default YTD
                key="filter_period_type"
            )
        
        with col2:
            current_year = datetime.now().year
            
            if not available_years:
                available_years = [current_year, current_year - 1]
            else:
                # Ensure all years are integers
                available_years = [int(y) for y in available_years]
            
            year = st.selectbox(
                "📆 Year",
                options=available_years,
                index=0,  # Default to most recent
                key="filter_year"
            )
            
            # Ensure year is integer
            year = int(year)
        
        return period_type, year
    
    def _render_date_range(
        self,
        period_type: str,
        year: int
    ) -> Tuple[date, date]:
        """
        Render date range inputs based on period type.
        For Custom, show date pickers. Otherwise, calculate automatically.
        """
        today = date.today()
        
        if period_type == 'Custom':
            col1, col2 = st.sidebar.columns(2)
            
            with col1:
                start_date = st.date_input(
                    "Start Date",
                    value=date(year, 1, 1),
                    key="filter_start_date"
                )
            
            with col2:
                end_date = st.date_input(
                    "End Date",
                    value=min(today, date(year, 12, 31)),
                    key="filter_end_date"
                )
            
            # Validate
            if start_date > end_date:
                st.sidebar.error("⚠️ Start date must be before end date")
                end_date = start_date
        
        else:
            # Calculate based on period type
            start_date, end_date = self._calculate_period_dates(period_type, year)
            
            # Display the date range (read-only info)
            st.sidebar.caption(
                f"📅 {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
            )
        
        return start_date, end_date
    
    @staticmethod
    def _calculate_period_dates(period_type: str, year: int) -> Tuple[date, date]:
        """Calculate start and end dates for period type."""
        today = date.today()
        
        # Ensure year is integer
        year = int(year)
        
        if period_type == 'YTD':
            start = date(year, 1, 1)
            end = min(today, date(year, 12, 31))
        
        elif period_type == 'QTD':
            # Current quarter start
            if today.year == year:
                quarter = (today.month - 1) // 3 + 1
            else:
                quarter = 4  # Full year if past year
            
            quarter_start_month = (quarter - 1) * 3 + 1
            start = date(year, quarter_start_month, 1)
            end = min(today, date(year, 12, 31))
        
        elif period_type == 'MTD':
            if today.year == year:
                start = date(year, today.month, 1)
                end = today
            else:
                # If past year, use December
                start = date(year, 12, 1)
                end = date(year, 12, 31)
        
        else:
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
        """
        Render salesperson selector based on access level.
        
        - Full access: Multi-select all with Select All/Clear buttons
        - Team access: Multi-select team only
        - Self access: Disabled, auto-select self
        """
        access_level = self.access.get_access_level()
        
        if salesperson_df.empty:
            st.sidebar.warning("No salespeople available")
            return []
        
        if access_level == 'self':
            # Self access - show as disabled info
            employee_id = self.access.employee_id
            
            # Find name for display
            name_row = salesperson_df[salesperson_df['employee_id'] == employee_id]
            if not name_row.empty:
                name = name_row['sales_name'].iloc[0]
            else:
                name = f"Employee #{employee_id}"
            
            st.sidebar.markdown("**👤 Salesperson**")
            st.sidebar.info(f"📌 {name}")
            
            return [employee_id] if employee_id else []
        
        else:
            # Team or Full access - improved multi-select with expander
            options = sorted(salesperson_df['sales_name'].tolist())
            id_map = dict(zip(
                salesperson_df['sales_name'],
                salesperson_df['employee_id']
            ))
            
            # Initialize session state for selected salespeople
            if 'selected_salespeople' not in st.session_state:
                st.session_state.selected_salespeople = options.copy()
            
            # Salesperson section header with count
            total_count = len(options)
            selected_count = len(st.session_state.get('selected_salespeople', options))
            
            st.sidebar.markdown(f"**👥 Salesperson** ({selected_count}/{total_count})")
            
            # Quick action buttons
            col1, col2 = st.sidebar.columns(2)
            with col1:
                if st.button("✅ All", key="btn_select_all", use_container_width=True):
                    st.session_state.selected_salespeople = options.copy()
                    st.rerun()
            with col2:
                if st.button("❌ Clear", key="btn_clear_all", use_container_width=True):
                    st.session_state.selected_salespeople = []
                    st.rerun()
            
            # Expander with checkboxes for better UX
            with st.sidebar.expander(f"📋 Select Salespeople", expanded=False):
                # Search box
                search_term = st.text_input(
                    "🔍 Search",
                    key="salesperson_search",
                    placeholder="Type to filter...",
                    label_visibility="collapsed"
                )
                
                # Filter options based on search
                if search_term:
                    filtered_options = [
                        name for name in options 
                        if search_term.lower() in name.lower()
                    ]
                else:
                    filtered_options = options
                
                # Checkboxes in a scrollable container
                selected_in_expander = []
                
                for name in filtered_options:
                    is_selected = name in st.session_state.get('selected_salespeople', options)
                    if st.checkbox(
                        name,
                        value=is_selected,
                        key=f"chk_sp_{name}"
                    ):
                        selected_in_expander.append(name)
                
                # Update session state based on checkboxes
                # Keep non-filtered selections + add filtered selections
                if search_term:
                    non_filtered = [
                        n for n in st.session_state.get('selected_salespeople', [])
                        if n not in filtered_options
                    ]
                    st.session_state.selected_salespeople = non_filtered + selected_in_expander
                else:
                    st.session_state.selected_salespeople = selected_in_expander
            
            # Show selected count summary
            selected_names = st.session_state.get('selected_salespeople', options)
            
            if len(selected_names) == 0:
                st.sidebar.warning("⚠️ Select at least one")
            elif len(selected_names) <= 3:
                # Show names if few selected
                st.sidebar.caption(f"Selected: {', '.join(selected_names)}")
            else:
                st.sidebar.caption(f"✓ {len(selected_names)} salespeople selected")
            
            # Convert names to IDs
            selected_ids = [id_map[name] for name in selected_names if name in id_map]
            
            return selected_ids
    
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