# utils/legal_entity_performance/filters.py
"""
Sidebar Filter Components for Legal Entity Performance
Aligned with kpi_center_performance/filters.py

VERSION: 2.0.0
- Uses PERIOD_TYPES (YTD/QTD/MTD/LY/Custom) synced with KPI center
- analyze_period helper for date range calculation
- custom_start_date for dynamic loading trigger
"""

import logging
import calendar
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import streamlit as st

from .constants import PERIOD_TYPES, MONTH_ORDER, CACHE_KEY_UNIFIED

logger = logging.getLogger(__name__)


# =============================================================================
# PERIOD ANALYSIS (synced with KPI center)
# =============================================================================

def analyze_period(period_type: str, year: int) -> Dict:
    """
    Calculate date range and metadata for a given period type.
    Synced with kpi_center_performance/filters.py analyze_period().
    
    Returns:
        Dict with start_date, end_date, display_label, is_current_period
    """
    today = date.today()
    
    if period_type == 'YTD':
        start_date = date(year, 1, 1)
        end_date = min(today, date(year, 12, 31))
        label = f"YTD {year}"
    
    elif period_type == 'QTD':
        current_quarter = (today.month - 1) // 3 + 1
        quarter = current_quarter if year == today.year else 4
        start_date = date(year, (quarter - 1) * 3 + 1, 1)
        quarter_end_month = quarter * 3
        last_day = calendar.monthrange(year, quarter_end_month)[1]
        end_date = min(today, date(year, quarter_end_month, last_day))
        label = f"Q{quarter} {year}"
    
    elif period_type == 'MTD':
        month = today.month if year == today.year else 12
        start_date = date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        end_date = min(today, date(year, month, last_day))
        label = f"{start_date.strftime('%b')} {year}"
    
    elif period_type == 'LY':
        ly = year - 1
        start_date = date(ly, 1, 1)
        end_date = date(ly, 12, 31)
        label = f"LY {ly}"
        year = ly  # Override year for consistency
    
    else:  # Custom
        start_date = date(year, 1, 1)
        end_date = today
        label = "Custom"
    
    is_current = (year == today.year and end_date >= today)
    
    return {
        'start_date': start_date,
        'end_date': end_date,
        'year': year,
        'display_label': label,
        'is_current_period': is_current,
    }


# =============================================================================
# MAIN FILTER CLASS
# =============================================================================

class LegalEntityFilters:
    """Render and manage sidebar filters."""
    
    def __init__(self, access_control=None):
        self.access = access_control
    
    def render_sidebar_filters(
        self,
        entity_df: pd.DataFrame,
        available_years: list,
    ) -> Dict:
        """
        Render sidebar filters and return selected values.
        
        Returns dict with:
            period_type, year, start_date, end_date, entity_ids,
            customer_type, show_yoy, custom_start_date, submitted
        """
        current_year = date.today().year
        today = date.today()
        
        with st.sidebar:
            st.header("🏢 Legal Entity Performance")
            
            # =============================================================
            # PERIOD SELECTION (synced with KPI center)
            # =============================================================
            st.subheader("📅 Period")
            
            period_type = st.selectbox(
                "Period Type",
                options=PERIOD_TYPES,
                index=0,
                key='le_period_type'
            )
            
            year = st.selectbox(
                "Year",
                options=available_years if available_years else [current_year],
                index=0,
                key='le_year'
            )
            
            # Calculate date range
            period_info = analyze_period(period_type, year)
            start_date = period_info['start_date']
            end_date = period_info['end_date']
            effective_year = period_info['year']
            
            # Override for QTD/MTD when not current year
            if period_type == 'QTD' and year != current_year:
                quarter = st.selectbox(
                    "Quarter", options=[1, 2, 3, 4], index=3,
                    key='le_quarter'
                )
                start_date = date(year, (quarter - 1) * 3 + 1, 1)
                qem = quarter * 3
                end_date = date(year, qem, calendar.monthrange(year, qem)[1])
            
            elif period_type == 'MTD' and year != current_year:
                month = st.selectbox(
                    "Month", options=list(range(1, 13)),
                    format_func=lambda m: date(2000, m, 1).strftime('%B'),
                    index=11, key='le_month'
                )
                start_date = date(year, month, 1)
                end_date = date(year, month, calendar.monthrange(year, month)[1])
            
            elif period_type == 'Custom':
                col1, col2 = st.columns(2)
                with col1:
                    start_date = st.date_input(
                        "From", value=date(year, 1, 1), key='le_custom_start'
                    )
                with col2:
                    end_date = st.date_input(
                        "To", value=today, key='le_custom_end'
                    )
            
            st.caption(f"📅 {start_date.strftime('%d %b %Y')} → {end_date.strftime('%d %b %Y')}")
            
            # Dynamic loading warning
            custom_start_date = None
            if period_type == 'Custom':
                custom_start_date = start_date
                cache = st.session_state.get(CACHE_KEY_UNIFIED)
                if cache:
                    cached_start = cache.get('_lookback_start')
                    if cached_start and start_date < cached_start:
                        st.warning(
                            f"⚠️ Custom period before cached range "
                            f"({start_date} < {cached_start}). "
                            f"Data will be reloaded."
                        )
            
            # =============================================================
            # ENTITY SELECTION
            # =============================================================
            st.subheader("🏢 Legal Entity")
            
            entity_options = []
            entity_id_map = {}
            if not entity_df.empty:
                for _, row in entity_df.iterrows():
                    name = str(row.get('legal_entity', 'Unknown'))
                    eid = row.get('legal_entity_id')
                    entity_options.append(name)
                    entity_id_map[name] = eid
            
            selected_entities = st.multiselect(
                "Select Entities",
                options=entity_options,
                default=[],
                placeholder="All entities",
                key='le_entity_filter'
            )
            entity_ids = [entity_id_map[n] for n in selected_entities if n in entity_id_map]
            
            # =============================================================
            # CUSTOMER TYPE
            # =============================================================
            st.subheader("👤 Filters")
            
            customer_type = st.selectbox(
                "Customer Type",
                options=['All', 'External', 'Internal'],
                index=0,
                key='le_customer_type'
            )
            
            # =============================================================
            # OPTIONS
            # =============================================================
            show_yoy = st.checkbox("📊 Show YoY comparison", value=True, key='le_show_yoy')
            
            # =============================================================
            # APPLY
            # =============================================================
            submitted = st.button(
                "🔄 Apply Filters", type="primary",
                use_container_width=True, key='le_apply_btn'
            )
        
        return {
            'period_type': period_type,
            'year': effective_year,
            'start_date': start_date,
            'end_date': end_date,
            'entity_ids': entity_ids,
            'customer_type': customer_type,
            'customer_ids': [],
            'product_ids': [],
            'brand_filter': [],
            'show_yoy': show_yoy,
            'submitted': submitted,
            'custom_start_date': custom_start_date,
        }
    
    def validate_filters(self, filter_values: dict) -> Tuple[bool, Optional[str]]:
        """Validate filter selections."""
        start = filter_values.get('start_date')
        end = filter_values.get('end_date')
        if start and end and start > end:
            return False, "Start date must be before end date"
        return True, None
    
    def get_filter_summary(self, filters: dict) -> str:
        """Generate human-readable filter summary."""
        pt = filters.get('period_type', 'YTD')
        year = filters.get('year', '')
        
        if pt == 'Custom':
            label = (
                f"{filters['start_date'].strftime('%d %b %Y')} → "
                f"{filters['end_date'].strftime('%d %b %Y')}"
            )
        elif pt == 'LY':
            label = f"LY {year}"
        elif pt == 'QTD':
            q = (filters['start_date'].month - 1) // 3 + 1
            label = f"Q{q} {year}"
        elif pt == 'MTD':
            label = f"{filters['start_date'].strftime('%B')} {year}"
        else:
            label = f"YTD {year}"
        
        parts = [label]
        
        entity_ids = filters.get('entity_ids', [])
        parts.append(f"{len(entity_ids)} entity(ies)" if entity_ids else "All entities")
        
        ct = filters.get('customer_type', 'All')
        if ct != 'All':
            parts.append(ct)
        
        return " | ".join(parts)
