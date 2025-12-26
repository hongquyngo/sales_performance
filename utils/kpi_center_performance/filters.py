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
- KPI Type filter (single selection)

REQUIREMENTS:
- Streamlit >= 1.33.0 (for @st.fragment support)

VERSION: 2.13.0
CHANGELOG:
- v2.13.0: SYNCED with Salesperson filters v2.5.0:
          - Added TextSearchResult dataclass for text search filters
          - Added render_text_search_filter() for OC#/Customer PO search
          - Added apply_text_search_filter() for multi-column text search
          - Added render_number_filter alias for consistency with Salesperson
- v2.12.0: ADDED Hierarchy Display for KPI Center dropdown:
          - Added _build_hierarchy_display_options() helper
          - Parent KPI Centers now visible with 📁 prefix
          - Children indented with tree-like structure (├─, └─)
          - Expansion works when user selects parent
          - load_lookup_data() in main page updated to include parents
          - FIXED: _get_kpi_centers_with_assignments() now includes parents
            Business rule: If child has KPI assignment, parent is also considered
            as having assignment (parent KPI = sum of children KPIs)
- v2.11.0: MAJOR REFACTOR - All filters in single @st.fragment:
          - Entity now filters by KPI Type (like KPI Center)
          - Date Range moved into fragment
          - YTD/QTD/MTD: date pickers show values but DISABLED
          - Custom: date pickers ENABLED
          - Added _get_entities_by_kpi_type() helper
          - Removed st.form - fragment handles instant updates
          - Submit button triggers page rerun via session_state flag
- v2.10.2: UX improvement - Always reset KPI Center to ['All'] when KPI Type changes:
          - Previous: Only reset when selection became invalid (inconsistent behavior)
          - Now: Track KPI Type changes via _prev_kpi_type session state
          - Switching to ANY new KPI Type → KPI Center resets to ['All']
          - Provides consistent, predictable UX
- v2.10.1: BUGFIX - Double-click required to change KPI Type:
          - Root cause: Mixing `index` param with `key` param in selectbox
          - Fix: Use widget key directly for session_state management
          - Removed `index` param from selectbox (let Streamlit manage via key)
          - Fixed checkbox: Removed `value` param, use key only
- v2.10.0: ADDED KPI Type → KPI Center dependency (NO PAGE RELOAD):
          - KPI Type and KPI Center wrapped in @st.fragment (requires Streamlit >= 1.33)
          - Changing KPI Type ONLY reruns the fragment, not the whole page
          - KPI Center options filter instantly based on selected KPI Type
          - Values passed to form via session_state
          - "Only with KPI" checkbox also in fragment for instant filtering
          - Form now only contains: Date Range, Entity, Exclude Internal
- v2.8.0: KPI Type filter changed to SINGLE SELECTION:
          - Removed "All Types" option to prevent double counting
          - Same transaction can be split across multiple KPI Types
          - Default: TERRITORY
          - Help text explains single selection requirement
- v2.3.0: BUGFIX - Parent-Child Hierarchy & Dynamic Year Check
          - Added _expand_kpi_center_ids_with_children() to expand parent → all children
          - Fixed "Only with KPI" checkbox to check years based on selected period
            (YTD/QTD/MTD → current_year, Custom → years in date range)
          - Added kpi_center_ids_expanded to filter_values for client-side filtering
          - Added kpi_center_ids_selected for display purposes (original user selection)
- v2.2.0: SYNCED UI with Salesperson page
          - Period definitions shown in tooltip (?) icon next to Period label
          - Identical tooltip format for Start/End date inputs
          - Same caption "Applies to Sales data. Backlog shows full pipeline."
          - Clean UI without visible text block clutter
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
    
    UPDATED v2.12.0: Now includes all ancestors (parents) of KPI Centers 
    with direct assignments. Business logic: Parent KPI = sum of children KPIs,
    so if any child has assignment, parent should also be considered as having assignment.
    
    Args:
        years: List of years to check
        
    Returns:
        List of kpi_center_ids with KPI assignments (direct or inherited from children)
    """
    if not years:
        return []
    
    try:
        from utils.db import get_db_engine
        engine = get_db_engine()
        
        # Query includes:
        # 1. KPI Centers with direct assignments
        # 2. All ancestors (parents) of those KPI Centers
        query = """
            WITH RECURSIVE 
            -- Step 1: Get KPI Centers with direct assignments
            direct_assignments AS (
                SELECT DISTINCT kpi_center_id
                FROM sales_kpi_center_assignments_view 
                WHERE year IN :years
            ),
            
            -- Step 2: Get all ancestors (parents) recursively
            all_with_ancestors AS (
                -- Base case: direct assignments
                SELECT kpi_center_id, kpi_center_id AS original_id
                FROM direct_assignments
                
                UNION
                
                -- Recursive case: parents of KPI Centers
                SELECT kc.parent_center_id AS kpi_center_id, awa.original_id
                FROM kpi_centers kc
                INNER JOIN all_with_ancestors awa ON kc.id = awa.kpi_center_id
                WHERE kc.parent_center_id IS NOT NULL
                  AND (kc.delete_flag = 0 OR kc.delete_flag IS NULL)
            )
            
            SELECT DISTINCT kpi_center_id 
            FROM all_with_ancestors
            WHERE kpi_center_id IS NOT NULL
            ORDER BY kpi_center_id
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(query), {'years': tuple(years)})
            ids = [row[0] for row in result]
            logger.debug(f"KPI Centers with assignments (incl. parents): {len(ids)} for years {years}")
            return ids
            
    except Exception as e:
        logger.error(f"Error fetching KPI Centers with assignments: {e}")
        return []


# =============================================================================
# ENTITY BY KPI TYPE HELPER - NEW v2.11.0
# =============================================================================

def _get_entities_by_kpi_type(kpi_type: str = None) -> pd.DataFrame:
    """
    Get Legal Entities that have sales data for the selected KPI Type.
    
    Args:
        kpi_type: KPI Type to filter by (e.g., 'TERRITORY', 'VERTICAL')
                  If None, returns all entities with sales data
        
    Returns:
        DataFrame with columns: entity_id, entity_name
    """
    try:
        from utils.db import get_db_engine
        engine = get_db_engine()
        
        if kpi_type:
            query = """
                SELECT DISTINCT
                    v.legal_entity_id AS entity_id,
                    COALESCE(c.english_name, v.legal_entity) AS entity_name
                FROM unified_sales_by_kpi_center_view v
                LEFT JOIN companies c ON v.legal_entity_id = c.id
                WHERE v.legal_entity_id IS NOT NULL
                  AND v.kpi_type = :kpi_type
                ORDER BY entity_name
            """
            df = pd.read_sql(text(query), engine, params={'kpi_type': kpi_type})
        else:
            query = """
                SELECT DISTINCT
                    v.legal_entity_id AS entity_id,
                    COALESCE(c.english_name, v.legal_entity) AS entity_name
                FROM unified_sales_by_kpi_center_view v
                LEFT JOIN companies c ON v.legal_entity_id = c.id
                WHERE v.legal_entity_id IS NOT NULL
                ORDER BY entity_name
            """
            df = pd.read_sql(text(query), engine)
        
        return df
        
    except Exception as e:
        logger.error(f"Error fetching entities by KPI Type: {e}")
        return pd.DataFrame(columns=['entity_id', 'entity_name'])


# =============================================================================
# PARENT-CHILD HIERARCHY HELPER - NEW v2.3.0
# =============================================================================

def _expand_kpi_center_ids_with_children(kpi_center_ids: List[int]) -> List[int]:
    """
    Expand KPI Center IDs to include all children (recursive).
    
    When user selects a parent KPI Center, this function finds all 
    descendant KPI Centers and returns the complete list.
    
    Args:
        kpi_center_ids: List of selected KPI Center IDs (may include parents)
        
    Returns:
        List of KPI Center IDs including all descendants
        
    Example:
        Input: [1]  (where 1 is parent of 101, 102, 103)
        Output: [1, 101, 102, 103]
    """
    if not kpi_center_ids:
        return kpi_center_ids
    
    try:
        from utils.db import get_db_engine
        engine = get_db_engine()
        
        # Use recursive CTE to get all descendants
        query = """
            WITH RECURSIVE all_centers AS (
                -- Base case: selected centers
                SELECT id AS kpi_center_id
                FROM kpi_centers 
                WHERE id IN :selected_ids
                  AND (delete_flag = 0 OR delete_flag IS NULL)
                
                UNION ALL
                
                -- Recursive case: all descendants
                SELECT kc.id
                FROM kpi_centers kc
                INNER JOIN all_centers ac ON kc.parent_center_id = ac.kpi_center_id
                WHERE kc.delete_flag = 0 OR kc.delete_flag IS NULL
            )
            SELECT DISTINCT kpi_center_id FROM all_centers
            ORDER BY kpi_center_id
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(query), {'selected_ids': tuple(kpi_center_ids)})
            expanded_ids = [row[0] for row in result]
            
            # Log expansion for debugging
            if len(expanded_ids) > len(kpi_center_ids):
                logger.info(
                    f"KPI Center IDs expanded: {len(kpi_center_ids)} → {len(expanded_ids)} "
                    f"(added {len(expanded_ids) - len(kpi_center_ids)} children)"
                )
            
            return expanded_ids
            
    except Exception as e:
        logger.error(f"Error expanding KPI Center IDs with children: {e}")
        # Fallback: return original IDs
        return kpi_center_ids


# =============================================================================
# HIERARCHY DISPLAY HELPER - NEW v2.12.0
# =============================================================================

def _build_hierarchy_display_options(
    kpi_center_df: pd.DataFrame,
    kpi_type_filter: str = None
) -> Tuple[List[str], Dict[str, int], Dict[int, str]]:
    """
    Build display options for KPI Center dropdown with hierarchy visualization.
    
    Creates indented tree-like display names for KPI Centers:
    - Parent nodes: 📁 prefix
    - Children: indented with ├─ or └─
    
    Args:
        kpi_center_df: DataFrame with columns:
            - kpi_center_id
            - kpi_center_name  
            - kpi_type
            - parent_center_id (optional)
            - level (optional)
            - has_children (optional)
        kpi_type_filter: Optional KPI Type to filter by
        
    Returns:
        Tuple of:
        - options: List of display names (sorted by hierarchy)
        - display_to_id: Dict mapping display_name → kpi_center_id
        - id_to_display: Dict mapping kpi_center_id → display_name
        
    Example output:
        options = [
            '📁 ALL',
            '  📁 PTV',
            '    HAN',
            '    DAN',
            '    SGN',
            '  📁 OVERSEA',
            '    📁 SEA',
            '      PTP',
            '      ROSEA',
            '    ROW',
        ]
    """
    if kpi_center_df.empty:
        return [], {}, {}
    
    df = kpi_center_df.copy()
    
    # Filter by KPI Type if specified
    if kpi_type_filter and 'kpi_type' in df.columns:
        df = df[df['kpi_type'] == kpi_type_filter]
    
    if df.empty:
        return [], {}, {}
    
    # Check if hierarchy columns exist
    has_hierarchy = all(col in df.columns for col in ['parent_center_id', 'level', 'has_children'])
    
    if not has_hierarchy:
        # Fallback: flat list (no hierarchy info)
        options = sorted(df['kpi_center_name'].tolist())
        display_to_id = dict(zip(df['kpi_center_name'], df['kpi_center_id']))
        id_to_display = dict(zip(df['kpi_center_id'], df['kpi_center_name']))
        return options, display_to_id, id_to_display
    
    # Build hierarchy tree
    options = []
    display_to_id = {}
    id_to_display = {}
    
    # Create lookup dicts
    id_to_row = {row['kpi_center_id']: row for _, row in df.iterrows()}
    children_map = {}  # parent_id → list of children rows
    
    for _, row in df.iterrows():
        parent_id = row.get('parent_center_id')
        if pd.notna(parent_id):
            parent_id = int(parent_id)
            if parent_id not in children_map:
                children_map[parent_id] = []
            children_map[parent_id].append(row)
    
    # Sort children by name
    for parent_id in children_map:
        children_map[parent_id] = sorted(children_map[parent_id], key=lambda x: x['kpi_center_name'])
    
    def build_tree(node_id: int, indent: str = "", is_last: bool = True, is_root: bool = True):
        """Recursively build tree display."""
        if node_id not in id_to_row:
            return
        
        row = id_to_row[node_id]
        name = row['kpi_center_name']
        has_children = row.get('has_children', False)
        kpi_center_id = row['kpi_center_id']
        
        # Build display name
        if is_root:
            # Root level - no indent
            prefix = "📁 " if has_children else ""
            display_name = f"{prefix}{name}"
        else:
            # Child level - with indent
            branch = "└─ " if is_last else "├─ "
            prefix = "📁 " if has_children else ""
            display_name = f"{indent}{branch}{prefix}{name}"
        
        options.append(display_name)
        display_to_id[display_name] = kpi_center_id
        id_to_display[kpi_center_id] = display_name
        
        # Process children
        if node_id in children_map:
            children = children_map[node_id]
            for i, child_row in enumerate(children):
                child_id = child_row['kpi_center_id']
                is_last_child = (i == len(children) - 1)
                
                # Calculate new indent
                if is_root:
                    new_indent = "  "
                else:
                    extension = "   " if is_last else "│  "
                    new_indent = indent + extension
                
                build_tree(child_id, new_indent, is_last_child, is_root=False)
    
    # Find root nodes (no parent or parent not in current filtered set)
    root_nodes = []
    filtered_ids = set(df['kpi_center_id'].tolist())
    
    for _, row in df.iterrows():
        parent_id = row.get('parent_center_id')
        if pd.isna(parent_id) or int(parent_id) not in filtered_ids:
            root_nodes.append(row)
    
    # Sort root nodes by name
    root_nodes = sorted(root_nodes, key=lambda x: x['kpi_center_name'])
    
    # Build tree for each root
    for i, root_row in enumerate(root_nodes):
        is_last_root = (i == len(root_nodes) - 1)
        build_tree(root_row['kpi_center_id'], "", is_last_root, is_root=True)
    
    return options, display_to_id, id_to_display


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
        if not self.is_active:
            return "FilterResult(inactive)"
        return f"FilterResult({mode} {len(self.selected)} items)"


def render_multiselect_with_exclude(
    label: str,
    options: List[Any],
    default: List[Any] = None,
    key: str = None,
    help_text: str = None,
    ctx = None
) -> FilterResult:
    """
    Render a multiselect with an Exclude checkbox.
    
    Args:
        label: Label for the multiselect
        options: List of options
        default: Default selected values
        key: Unique key prefix for widgets
        help_text: Help text for multiselect
        ctx: Streamlit context (st or st.sidebar)
        
    Returns:
        FilterResult with selected items, exclude flag, and is_active flag
    """
    if ctx is None:
        ctx = st
    
    if default is None:
        default = []
    
    # Layout: Label with Exclude checkbox on right
    col1, col2 = ctx.columns([3, 1])
    
    with col1:
        ctx.markdown(f"**{label}**")
    
    with col2:
        excluded = ctx.checkbox(
            "Excl",
            value=False,
            key=f"{key}_exclude",
            help="Tick to EXCLUDE items matching this condition"
        )
    
    # Multiselect
    selected = ctx.multiselect(
        label=label,
        options=options,
        default=default,
        key=f"{key}_select",
        help=help_text,
        label_visibility="collapsed"
    )
    
    # Determine if filter is active
    is_active = len(selected) > 0 and selected != ['All']
    
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
    Apply multiselect filter to DataFrame.
    
    Args:
        df: DataFrame to filter
        column: Column name to filter on
        filter_result: FilterResult from render_multiselect_with_exclude
        
    Returns:
        Filtered DataFrame
    """
    if df.empty or not filter_result.is_active:
        return df
    
    if column not in df.columns:
        return df
    
    if filter_result.excluded:
        # EXCLUDE mode: keep rows NOT in selected
        return df[~df[column].isin(filter_result.selected)]
    else:
        # INCLUDE mode: keep rows IN selected
        return df[df[column].isin(filter_result.selected)]


# =============================================================================
# TEXT SEARCH FILTER - NEW v2.13.0 (SYNCED with Salesperson)
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
    ctx = None
) -> TextSearchResult:
    """
    Render a text search filter with Excl option.
    
    Args:
        label: Filter label
        key: Unique widget key
        placeholder: Placeholder text
        help_text: Optional help tooltip
        ctx: Optional Streamlit context
        
    Returns:
        TextSearchResult with query, excluded flag, and is_active flag
    """
    if ctx is None:
        ctx = st
    
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
    """Result from a number range filter."""
    min_value: Optional[float]
    max_value: Optional[float]
    excluded: bool
    is_active: bool


def render_number_filter_with_exclude(
    label: str,
    default_min: float = 0,
    step: float = 1000,
    key: str = None,
    help_text: str = None,
    ctx = None
) -> NumberRangeResult:
    """
    Render a number input with Exclude checkbox.
    """
    if ctx is None:
        ctx = st
    
    # Layout
    col1, col2 = ctx.columns([3, 1])
    
    with col1:
        ctx.markdown(f"**{label}**")
    
    with col2:
        excluded = ctx.checkbox(
            "Excl",
            value=False,
            key=f"{key}_exclude",
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
    - Period definitions shown in tooltip (?) next to Period label
    - Same date range logic and UI layout
    - Same period type behavior (YTD/QTD/MTD for current_year)
    - Identical tooltip text for Start/End inputs
    - Same caption note about Sales data vs Backlog
    
    UPDATED v2.12.0:
    - KPI Center dropdown now shows hierarchy with indent/prefix
    - Parent KPI Centers visible with 📁 prefix
    - Children indented with tree-like structure
    
    UPDATED v2.11.0:
    - ALL filters now in single @st.fragment (no full page rerun)
    - Entity filters by KPI Type (dynamic)
    - Date pickers: disabled for YTD/QTD/MTD, enabled for Custom
    - No more st.form - fragment handles all updates
    
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
            default_end_date: date = None,
            kpi_types_with_assignment: set = None,
        ) -> Tuple[Dict, bool]:
            """
            Render ALL filters inside a single @st.fragment.
            No full page rerun when filters change - only fragment reruns.
            
            v2.12.0 IMPROVEMENTS:
            - KPI Center dropdown now shows hierarchy with tree-like display
            - Parent KPI Centers visible with 📁 prefix
            
            v2.11.0 IMPROVEMENTS:
            - Entity dropdown now filters by KPI Type
            - Date pickers: DISABLED for YTD/QTD/MTD, ENABLED for Custom
            - All filters in fragment for instant feedback
            - Submit button sets flag to trigger main page data reload
            
            Args:
                kpi_center_df: KPI Center options (with hierarchy columns if available)
                entity_df: Entity options (fallback if _get_entities_by_kpi_type fails)
                default_start_date: Default start date (from DB - Jan 1 of latest sales year)
                default_end_date: Default end date (from DB - max backlog ETD or today)
                kpi_types_with_assignment: Set of KPI Types that have KPI assignments
            
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
            
            # Pre-calculate date ranges for CURRENT YEAR
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
                # ALL FILTERS WRAPPED IN SINGLE FRAGMENT - v2.11.0
                # Changes here only rerun fragment, not whole page
                # =================================================================
                
                @st.fragment
                def all_filters_fragment():
                    """
                    Single fragment containing ALL filter controls.
                    Values are passed to outer scope via session_state.
                    """
                    
                    # =========================================================
                    # 1. KPI TYPE FILTER
                    # =========================================================
                    kpi_type_filter_local = 'TERRITORY'
                    available_types = []
                    
                    if not kpi_center_df.empty and 'kpi_type' in kpi_center_df.columns:
                        all_types = set(kpi_center_df['kpi_type'].dropna().unique().tolist())
                        
                        if kpi_types_with_assignment:
                            available_types = sorted(all_types & kpi_types_with_assignment)
                        else:
                            available_types = sorted(all_types)
                        
                        if available_types:
                            # Initialize session state
                            if 'frag_kpi_type' not in st.session_state:
                                st.session_state.frag_kpi_type = (
                                    'TERRITORY' if 'TERRITORY' in available_types 
                                    else available_types[0]
                                )
                            
                            # Ensure current value is still valid
                            if st.session_state.frag_kpi_type not in available_types:
                                st.session_state.frag_kpi_type = available_types[0]
                            
                            selected_type = st.selectbox(
                                "KPI Type",
                                options=available_types,
                                key="frag_kpi_type",
                                help="Select KPI Type. KPI Center and Entity options update instantly."
                            )
                            
                            kpi_type_filter_local = selected_type
                    
                    # =========================================================
                    # 2. ONLY WITH KPI CHECKBOX
                    # =========================================================
                    if 'frag_only_with_kpi' not in st.session_state:
                        st.session_state.frag_only_with_kpi = True
                    
                    only_with_kpi_local = st.checkbox(
                        "Only with KPI assignment",
                        key="frag_only_with_kpi",
                        help="Show only KPI Centers with KPI targets assigned."
                    )
                    
                    # Get KPI Centers with assignments
                    kpi_check_years_local = [current_year]
                    kpi_center_ids_with_kpi = []
                    if only_with_kpi_local:
                        kpi_center_ids_with_kpi = _get_kpi_centers_with_assignments(kpi_check_years_local)
                    
                    # =========================================================
                    # 3. KPI CENTER FILTER (filtered by KPI Type) - UPDATED v2.12.0
                    # =========================================================
                    st.markdown("**🎯 KPI Center**")
                    
                    filtered_kc_df = kpi_center_df.copy()
                    kpi_center_ids_local = []
                    
                    if not kpi_center_df.empty:
                        # Filter by KPI Type
                        if 'kpi_type' in kpi_center_df.columns and kpi_type_filter_local:
                            filtered_kc_df = filtered_kc_df[filtered_kc_df['kpi_type'] == kpi_type_filter_local]
                        
                        # Filter by KPI assignment
                        if only_with_kpi_local and kpi_center_ids_with_kpi:
                            filtered_kc_df = filtered_kc_df[
                                filtered_kc_df['kpi_center_id'].isin(kpi_center_ids_with_kpi)
                            ]
                        
                        # Show info
                        total_in_type = len(kpi_center_df[kpi_center_df['kpi_type'] == kpi_type_filter_local]) if 'kpi_type' in kpi_center_df.columns else len(kpi_center_df)
                        filtered_count = len(filtered_kc_df)
                        hidden_count = total_in_type - filtered_count
                        
                        if hidden_count > 0:
                            st.caption(f"📋 {filtered_count} with KPI in {current_year} ({hidden_count} hidden)")
                    
                    if filtered_kc_df.empty:
                        st.warning(f"No KPI Centers for type '{kpi_type_filter_local}'")
                    else:
                        # =====================================================
                        # BUILD HIERARCHY DISPLAY - NEW v2.12.0
                        # =====================================================
                        hierarchy_options, display_to_id, id_to_display = _build_hierarchy_display_options(
                            filtered_kc_df,
                            kpi_type_filter=None  # Already filtered above
                        )
                        
                        # Add 'All' option at the beginning
                        options = ['All'] + hierarchy_options
                        
                        # Track previous KPI Type to detect changes
                        prev_kpi_type = st.session_state.get('_prev_kpi_type', None)
                        
                        if prev_kpi_type != kpi_type_filter_local:
                            # KPI Type changed → reset to All
                            st.session_state.frag_kpi_center = ['All']
                            st.session_state._prev_kpi_type = kpi_type_filter_local
                            # Also reset Entity when KPI Type changes
                            st.session_state.frag_entity = ['All']
                        elif 'frag_kpi_center' not in st.session_state:
                            st.session_state.frag_kpi_center = ['All']
                        
                        # Validate current selection against available options
                        current_selection = st.session_state.frag_kpi_center
                        valid_selection = [s for s in current_selection if s in options]
                        if not valid_selection:
                            valid_selection = ['All']
                        if valid_selection != current_selection:
                            st.session_state.frag_kpi_center = valid_selection
                        
                        selected_display_names = st.multiselect(
                            "Select KPI Centers",
                            options=options,
                            key="frag_kpi_center",
                            label_visibility="collapsed"
                        )
                        
                        # Convert display names back to IDs
                        if 'All' in selected_display_names or not selected_display_names:
                            kpi_center_ids_local = list(display_to_id.values())
                        else:
                            kpi_center_ids_local = [
                                display_to_id[name] 
                                for name in selected_display_names 
                                if name in display_to_id
                            ]
                    
                    st.divider()
                    
                    # =========================================================
                    # 4. ENTITY FILTER (filtered by KPI Type) - NEW v2.11.0
                    # =========================================================
                    st.markdown("**🏢 Legal Entity**")
                    
                    entity_ids_local = []
                    
                    # Get entities for selected KPI Type
                    filtered_entity_df = _get_entities_by_kpi_type(kpi_type_filter_local)
                    
                    # Fallback to provided entity_df if query fails
                    if filtered_entity_df.empty and entity_df is not None:
                        filtered_entity_df = entity_df.copy()
                    
                    if not filtered_entity_df.empty:
                        entity_count = len(filtered_entity_df)
                        st.caption(f"📋 {entity_count} entities with {kpi_type_filter_local} data")
                        
                        entity_options = ['All'] + filtered_entity_df['entity_name'].tolist()
                        entity_id_map = dict(zip(
                            filtered_entity_df['entity_name'],
                            filtered_entity_df['entity_id']
                        ))
                        
                        # Initialize entity selection
                        if 'frag_entity' not in st.session_state:
                            st.session_state.frag_entity = ['All']
                        
                        # Validate current selection against available options
                        current_selection = st.session_state.frag_entity
                        valid_selection = [e for e in current_selection if e in entity_options]
                        if not valid_selection:
                            valid_selection = ['All']
                        if valid_selection != current_selection:
                            st.session_state.frag_entity = valid_selection
                        
                        selected_entities = st.multiselect(
                            "Select entities",
                            options=entity_options,
                            key="frag_entity",
                            label_visibility="collapsed"
                        )
                        
                        if 'All' in selected_entities or not selected_entities:
                            entity_ids_local = []  # No filter
                        else:
                            entity_ids_local = [
                                entity_id_map[name]
                                for name in selected_entities
                                if name in entity_id_map
                            ]
                    else:
                        st.info("No entities found for selected KPI Type")
                    
                    st.divider()
                    
                    # =========================================================
                    # 5. DATE RANGE SECTION - IMPROVED v2.11.0
                    # =========================================================
                    st.markdown("**📅 Date Range**")
                    st.caption("Applies to Sales data. Backlog shows full pipeline.")
                    
                    # Period type radio
                    if 'frag_period_type' not in st.session_state:
                        st.session_state.frag_period_type = 'YTD'
                    
                    period_type_local = st.radio(
                        "Period",
                        options=['YTD', 'QTD', 'MTD', 'Custom'],
                        key="frag_period_type",
                        horizontal=True,
                        help=(
                            f"**YTD** (Year to Date): Jan 01 → {ytd_end.strftime('%b %d, %Y')}\n\n"
                            f"**QTD** (Q{current_quarter} to Date): {qtd_start.strftime('%b %d')} → {qtd_end.strftime('%b %d, %Y')}\n\n"
                            f"**MTD** ({today.strftime('%B')} to Date): {mtd_start.strftime('%b %d')} → {mtd_end.strftime('%b %d, %Y')}\n\n"
                            f"**Custom**: Select any date range using Start/End inputs below"
                        )
                    )
                    
                    # Determine if date pickers should be disabled
                    is_custom = (period_type_local == 'Custom')
                    
                    # Calculate display dates based on period type
                    if period_type_local == 'YTD':
                        display_start = ytd_start
                        display_end = ytd_end
                    elif period_type_local == 'QTD':
                        display_start = qtd_start
                        display_end = qtd_end
                    elif period_type_local == 'MTD':
                        display_start = mtd_start
                        display_end = mtd_end
                    else:  # Custom
                        # Use stored custom dates or defaults
                        display_start = st.session_state.get('frag_custom_start', default_start_date)
                        display_end = st.session_state.get('frag_custom_end', default_end_date)
                    
                    # Date inputs
                    col_start, col_end = st.columns(2)
                    
                    with col_start:
                        if is_custom:
                            # ENABLED - user can edit
                            start_date_input = st.date_input(
                                "Start",
                                value=display_start,
                                key="frag_start_date",
                                help="Start date for Custom period"
                            )
                            # Store custom date
                            st.session_state.frag_custom_start = start_date_input
                        else:
                            # DISABLED - just show calculated date
                            st.date_input(
                                "Start",
                                value=display_start,
                                key="frag_start_date_display",
                                disabled=True,
                                help=f"Auto-calculated for {period_type_local}"
                            )
                            start_date_input = display_start
                    
                    with col_end:
                        if is_custom:
                            # ENABLED - user can edit
                            end_date_input = st.date_input(
                                "End",
                                value=display_end,
                                key="frag_end_date",
                                help="End date for Custom period"
                            )
                            # Store custom date
                            st.session_state.frag_custom_end = end_date_input
                        else:
                            # DISABLED - just show calculated date
                            st.date_input(
                                "End",
                                value=display_end,
                                key="frag_end_date_display",
                                disabled=True,
                                help=f"Auto-calculated for {period_type_local}"
                            )
                            end_date_input = display_end
                    
                    # Final date values
                    if period_type_local == 'YTD':
                        final_start = ytd_start
                        final_end = ytd_end
                    elif period_type_local == 'QTD':
                        final_start = qtd_start
                        final_end = qtd_end
                    elif period_type_local == 'MTD':
                        final_start = mtd_start
                        final_end = mtd_end
                    else:  # Custom
                        final_start = start_date_input
                        final_end = end_date_input
                        # Validate
                        if final_start > final_end:
                            final_end = final_start
                            st.warning("⚠️ End date adjusted to match Start date")
                    
                    st.divider()
                    
                    # =========================================================
                    # 6. EXCLUDE INTERNAL REVENUE
                    # =========================================================
                    if 'frag_exclude_internal' not in st.session_state:
                        st.session_state.frag_exclude_internal = True
                    
                    exclude_internal_local = st.checkbox(
                        "Exclude internal revenue",
                        key="frag_exclude_internal",
                        help=(
                            "Exclude revenue from internal company transactions. "
                            "Gross Profit is kept intact for accurate GP% calculation."
                        )
                    )
                    
                    st.divider()
                    
                    # =========================================================
                    # 7. APPLY BUTTON
                    # =========================================================
                    if st.button(
                        "🔍 Apply Filters",
                        use_container_width=True,
                        type="primary",
                        key="frag_apply_btn"
                    ):
                        # Set flag to trigger main page data reload
                        st.session_state._filters_submitted = True
                        st.rerun()
                    
                    # =========================================================
                    # PASS VALUES TO OUTER SCOPE VIA SESSION STATE
                    # =========================================================
                    st.session_state._frag_kpi_type_filter = kpi_type_filter_local
                    st.session_state._frag_only_with_kpi = only_with_kpi_local
                    st.session_state._frag_kpi_center_ids = kpi_center_ids_local
                    st.session_state._frag_kpi_check_years = kpi_check_years_local
                    st.session_state._frag_entity_ids = entity_ids_local
                    st.session_state._frag_period_type = period_type_local
                    st.session_state._frag_start_date = final_start
                    st.session_state._frag_end_date = final_end
                    st.session_state._frag_exclude_internal = exclude_internal_local
                
                # Execute the fragment
                all_filters_fragment()
                
                # Read values from session_state
                kpi_type_filter = st.session_state.get('_frag_kpi_type_filter', 'TERRITORY')
                only_with_kpi = st.session_state.get('_frag_only_with_kpi', True)
                kpi_center_ids = st.session_state.get('_frag_kpi_center_ids', [])
                kpi_check_years = st.session_state.get('_frag_kpi_check_years', [current_year])
                entity_ids = st.session_state.get('_frag_entity_ids', [])
                period_type = st.session_state.get('_frag_period_type', 'YTD')
                start_date = st.session_state.get('_frag_start_date', ytd_start)
                end_date = st.session_state.get('_frag_end_date', ytd_end)
                exclude_internal = st.session_state.get('_frag_exclude_internal', True)
                
                # Check if submitted
                submitted = st.session_state.pop('_filters_submitted', False)
            
            # =================================================================
            # DETERMINE YEAR FROM DATES
            # =================================================================
            if period_type in ['YTD', 'QTD', 'MTD']:
                year = current_year
            else:
                year = start_date.year
            
            # =================================================================
            # RECALCULATE kpi_check_years based on actual period
            # =================================================================
            if period_type in ['YTD', 'QTD', 'MTD']:
                kpi_check_years = [current_year]
            else:
                # Custom: include all years in range
                kpi_check_years = list(range(start_date.year, end_date.year + 1))
            
            # =================================================================
            # EXPAND KPI CENTER IDs WITH CHILDREN
            # =================================================================
            kpi_center_ids_selected = kpi_center_ids.copy()
            kpi_center_ids_expanded = _expand_kpi_center_ids_with_children(kpi_center_ids)
            
            if len(kpi_center_ids_expanded) > len(kpi_center_ids_selected):
                children_added = len(kpi_center_ids_expanded) - len(kpi_center_ids_selected)
                logger.debug(f"KPI Centers: {len(kpi_center_ids_selected)} selected + {children_added} children = {len(kpi_center_ids_expanded)} total")
            
            # Build filter values dict
            filter_values = {
                'period_type': period_type,
                'year': year,
                'start_date': start_date,
                'end_date': end_date,
                'kpi_center_ids': kpi_center_ids_expanded,
                'kpi_center_ids_selected': kpi_center_ids_selected,
                'kpi_center_ids_expanded': kpi_center_ids_expanded,
                'kpi_type_filter': kpi_type_filter,
                'entity_ids': entity_ids,
                'exclude_internal_revenue': exclude_internal,
                'show_yoy': True,
                'only_with_kpi': only_with_kpi,
                'kpi_check_years': kpi_check_years,
            }
            
            return filter_values, submitted

    # =========================================================================
    # LEGACY METHOD - For backward compatibility
    # =========================================================================
    
    def render_sidebar_filters(
        self,
        kpi_center_df: pd.DataFrame,
        entity_df: pd.DataFrame = None,
        available_years: List[int] = None,
        kpi_types_with_assignment: set = None,
    ) -> Dict:
        """
        Legacy method - redirects to render_filter_form for backward compatibility.
        """
        filter_values, _ = self.render_filter_form(
            kpi_center_df=kpi_center_df,
            entity_df=entity_df,
            kpi_types_with_assignment=kpi_types_with_assignment,
        )
        filter_values['submitted'] = True
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
        kc_selected = len(filters.get('kpi_center_ids_selected', []))
        kc_expanded = len(filters.get('kpi_center_ids_expanded', filters.get('kpi_center_ids', [])))
        
        if kc_expanded > kc_selected:
            parts.append(f"{kc_selected} KPI Centers (+{kc_expanded - kc_selected} children)")
        elif kc_selected == 1:
            parts.append("1 KPI Center")
        elif kc_selected > 1:
            parts.append(f"{kc_selected} KPI Centers")
        
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

# =============================================================================
# BACKWARD COMPATIBILITY ALIASES
# =============================================================================

# Alias for old function name used in __init__.py
render_multiselect_filter = render_multiselect_with_exclude
render_number_filter = render_number_filter_with_exclude
apply_filter_to_dataframe = apply_multiselect_filter


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