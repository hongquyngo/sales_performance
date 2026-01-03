# utils/kpi_center_performance/data_loader.py
"""
Unified Data Loader for KPI Center Performance

VERSION: 4.0.1

CHANGELOG:
- v4.0.1: RESTORED progress bar from v3.9.0 in _load_all_raw_data()
- v4.0.0: Initial unified data loading architecture

Single source of truth for all raw data loading.
Load ONCE, filter MANY times.

Principles:
1. Load all raw data in one go (4 SQL queries)
2. Cache in session_state for duration of session
3. Only reload when cache expired or data unavailable
4. All filtering done via DataProcessor (Pandas-based)
"""

import logging
import time
from datetime import date, datetime
from typing import Dict, List, Optional, Set, Tuple
import pandas as pd
import streamlit as st
from sqlalchemy import text

from .constants import (
    LOOKBACK_YEARS,
    MIN_DATA_YEAR,
    MAX_FUTURE_YEARS,
    CACHE_TTL_SECONDS,
    CACHE_KEY_UNIFIED,
    DEBUG_TIMING,
)

logger = logging.getLogger(__name__)


class UnifiedDataLoader:
    """
    Load and cache all raw data needed for KPI Center Performance.
    
    This class implements the "Load Once, Filter Many" pattern:
    - 4 SQL queries load ALL data needed for the page
    - Data is cached in session_state
    - Subsequent filter changes use cached data (instant)
    - Only reload when cache expires (TTL) or data unavailable
    
    Usage:
        loader = UnifiedDataLoader(access_control)
        unified_cache = loader.get_unified_data()
        filter_options = loader.extract_filter_options(unified_cache)
    """
    
    def __init__(self, access_control):
        """
        Initialize with access control.
        
        Args:
            access_control: AccessControl instance for permission checks
        """
        self.access = access_control
        self._engine = None
    
    @property
    def engine(self):
        """Lazy load database engine."""
        if self._engine is None:
            from utils.db import get_db_engine
            self._engine = get_db_engine()
        return self._engine
    
    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================
    
    def get_unified_data(self, force_reload: bool = False) -> Dict:
        """
        Get unified raw data (cached or fresh).
        
        This is the main entry point. It returns cached data if available
        and valid, otherwise loads fresh data from database.
        
        Args:
            force_reload: If True, bypass cache and reload from DB
            
        Returns:
            Dict containing:
            - sales_raw_df: 5 years of sales data
            - backlog_raw_df: All pending orders
            - targets_raw_df: 5 years of KPI targets
            - hierarchy_df: KPI Center hierarchy
            - _metadata: Loading info (timestamps, ranges)
        """
        if not self.access.can_access_page():
            return self._empty_cache()
        
        # Check if we can use cached data
        if not force_reload and not self._needs_reload():
            if DEBUG_TIMING:
                print(f"♻️ Using cached unified data")
            return st.session_state[CACHE_KEY_UNIFIED]
        
        # Load fresh data
        return self._load_all_raw_data()
    
    def _needs_reload(self) -> bool:
        """
        Check if data needs to be reloaded.
        
        Reload conditions:
        1. No cache exists
        2. Cache expired (TTL)
        
        Note: Unlike previous version, we do NOT reload when:
        - Filter values change (handled by DataProcessor)
        - Date range changes within lookback period
        """
        cache = st.session_state.get(CACHE_KEY_UNIFIED)
        
        if cache is None:
            logger.info("Cache miss: no cached data")
            return True
        
        # Check if cache has required data
        if cache.get('sales_raw_df') is None:
            logger.info("Cache miss: missing sales_raw_df")
            return True
        
        # Check TTL
        loaded_at = cache.get('_loaded_at')
        if loaded_at:
            elapsed = (datetime.now() - loaded_at).total_seconds()
            if elapsed > CACHE_TTL_SECONDS:
                logger.info(f"Cache expired: {elapsed:.0f}s > {CACHE_TTL_SECONDS}s TTL")
                return True
        
        return False
    
    def _empty_cache(self) -> Dict:
        """Return empty cache structure."""
        return {
            'sales_raw_df': pd.DataFrame(),
            'backlog_raw_df': pd.DataFrame(),
            'targets_raw_df': pd.DataFrame(),
            'hierarchy_df': pd.DataFrame(),
            '_loaded_at': None,
            '_lookback_start': None,
            '_lookback_end': None,
        }
    
    # =========================================================================
    # DATA LOADING
    # =========================================================================
    
    def _load_all_raw_data(self) -> Dict:
        """
        Load all raw data from database.
        
        Executes 4 SQL queries:
        1. Sales data (5 years lookback)
        2. Backlog data (all pending)
        3. Targets data (5 years)
        4. Hierarchy data (static)
        """
        today = date.today()
        lookback_start = date(max(today.year - LOOKBACK_YEARS, MIN_DATA_YEAR), 1, 1)
        lookback_end = date(today.year + MAX_FUTURE_YEARS, 12, 31)
        
        # Years for targets (lookback + future)
        target_years = list(range(lookback_start.year, lookback_end.year + 1))
        
        if DEBUG_TIMING:
            print(f"\n{'='*60}")
            print(f"📦 LOADING UNIFIED RAW DATA")
            print(f"   Period: {lookback_start} → {lookback_end}")
            print(f"   Lookback: {LOOKBACK_YEARS} years")
            print(f"{'='*60}")
        
        data = {}
        total_start = time.perf_counter()
        
        # =====================================================================
        # PROGRESS BAR - Restored from v3.9.0
        # =====================================================================
        progress_bar = st.progress(0, text="🔄 Loading unified data...")
        
        try:
            # =====================================================================
            # 1. SALES RAW DATA (largest dataset)
            # =====================================================================
            progress_bar.progress(10, text="📊 Loading sales data...")
            start = time.perf_counter()
            data['sales_raw_df'] = self._load_sales_raw(lookback_start)
            elapsed = time.perf_counter() - start
            if DEBUG_TIMING:
                print(f"   📊 SQL [sales_raw]: {elapsed:.3f}s → {len(data['sales_raw_df']):,} rows")
            
            # =====================================================================
            # 2. BACKLOG RAW DATA
            # =====================================================================
            progress_bar.progress(40, text="📦 Loading backlog data...")
            start = time.perf_counter()
            data['backlog_raw_df'] = self._load_backlog_raw()
            elapsed = time.perf_counter() - start
            if DEBUG_TIMING:
                print(f"   📊 SQL [backlog_raw]: {elapsed:.3f}s → {len(data['backlog_raw_df']):,} rows")
            
            # =====================================================================
            # 3. TARGETS RAW DATA
            # =====================================================================
            progress_bar.progress(70, text="🎯 Loading KPI targets...")
            start = time.perf_counter()
            data['targets_raw_df'] = self._load_targets_raw(target_years)
            elapsed = time.perf_counter() - start
            if DEBUG_TIMING:
                print(f"   📊 SQL [targets_raw]: {elapsed:.3f}s → {len(data['targets_raw_df']):,} rows")
            
            # =====================================================================
            # 4. HIERARCHY DATA
            # =====================================================================
            progress_bar.progress(90, text="🏢 Loading hierarchy...")
            start = time.perf_counter()
            data['hierarchy_df'] = self._load_hierarchy()
            elapsed = time.perf_counter() - start
            if DEBUG_TIMING:
                print(f"   📊 SQL [hierarchy]: {elapsed:.3f}s → {len(data['hierarchy_df']):,} rows")
            
            progress_bar.progress(100, text="✅ Data loaded successfully!")
            
        finally:
            # Clear progress bar after short delay
            import time as _time
            _time.sleep(0.3)
            progress_bar.empty()
        
        # =====================================================================
        # METADATA
        # =====================================================================
        data['_loaded_at'] = datetime.now()
        data['_lookback_start'] = lookback_start
        data['_lookback_end'] = lookback_end
        data['_lookback_years'] = LOOKBACK_YEARS
        data['_target_years'] = target_years
        
        total_elapsed = time.perf_counter() - total_start
        if DEBUG_TIMING:
            print(f"{'='*60}")
            print(f"✅ UNIFIED DATA LOADED: {total_elapsed:.3f}s total")
            print(f"{'='*60}\n")
        
        # Store in session state
        st.session_state[CACHE_KEY_UNIFIED] = data
        
        logger.info(
            f"Unified data loaded: sales={len(data['sales_raw_df'])}, "
            f"backlog={len(data['backlog_raw_df'])}, "
            f"targets={len(data['targets_raw_df'])}, "
            f"hierarchy={len(data['hierarchy_df'])}"
        )
        
        return data
    
    def _load_sales_raw(self, lookback_start: date) -> pd.DataFrame:
        """
        Load all sales data from lookback_start.
        
        This single query replaces:
        - load_lookup_data() lookback query
        - get_sales_data() query
        - get_previous_year_data() query
        
        All these are now extracted from this one dataset.
        """
        query = """
            SELECT 
                -- Identifiers
                data_source,
                unified_line_id,
                
                -- KPI Center info
                kpi_center_id,
                kpi_center,
                kpi_type,
                split_rate_percent,
                
                -- Entity info
                legal_entity_id,
                legal_entity,
                
                -- Date info
                inv_date,
                inv_number,
                vat_number,
                invoice_month,
                invoice_year,
                
                -- Customer info
                customer_id,
                customer,
                customer_code,
                customer_type,
                
                -- Product info
                product_id,
                product_pn,
                pt_code,
                brand,
                legacy_code,
                
                -- Order info
                oc_number,
                oc_date,
                customer_po_number,
                
                -- Amounts (split-adjusted)
                sales_by_kpi_center_usd,
                gross_profit_by_kpi_center_usd,
                gp1_by_kpi_center_usd,
                broker_commission_by_kpi_center_usd
                
            FROM unified_sales_by_kpi_center_view
            WHERE inv_date >= :lookback_start
            ORDER BY inv_date DESC
        """
        
        try:
            df = pd.read_sql(text(query), self.engine, params={'lookback_start': lookback_start})
            return df
        except Exception as e:
            logger.error(f"Error loading sales_raw: {e}")
            return pd.DataFrame()
    
    def _load_backlog_raw(self) -> pd.DataFrame:
        """
        Load all pending backlog orders.
        
        Loads ALL pending orders regardless of KPI Center selection.
        Filtering is done later by DataProcessor.
        """
        query = """
            SELECT 
                -- Order info
                oc_number,
                oc_date,
                etd,
                etd_year,
                etd_month,
                
                -- Customer info
                customer,
                customer_id,
                customer_type,
                customer_po_number,
                
                -- Product info
                product_pn,
                pt_code,
                package_size,
                brand,
                
                -- KPI Center info
                kpi_center,
                kpi_center_id,
                kpi_type,
                split_rate_percent,
                
                -- Entity info
                legal_entity,
                entity_id AS legal_entity_id,
                
                -- Amounts
                backlog_by_kpi_center_usd,
                backlog_gp_by_kpi_center_usd,
                
                -- Status info
                pending_type,
                days_until_etd,
                days_since_order,
                status,
                invoice_completion_percent
                
            FROM backlog_by_kpi_center_flat_looker_view
            WHERE invoice_completion_percent < 100 
               OR invoice_completion_percent IS NULL
            ORDER BY backlog_by_kpi_center_usd DESC
        """
        
        try:
            df = pd.read_sql(text(query), self.engine)
            return df
        except Exception as e:
            logger.error(f"Error loading backlog_raw: {e}")
            return pd.DataFrame()
    
    def _load_targets_raw(self, years: List[int]) -> pd.DataFrame:
        """
        Load all KPI targets for specified years.
        
        Loads ALL targets regardless of KPI Center selection.
        Filtering is done later by DataProcessor.
        """
        if not years:
            return pd.DataFrame()
        
        query = """
            SELECT 
                kpi_center_id,
                kpi_center_name,
                kpi_center_type,
                parent_center_id,
                year,
                kpi_type_id,
                kpi_name,
                unit_of_measure,
                annual_target_value,
                annual_target_value_numeric,
                weight,
                weight_numeric,
                monthly_target_value,
                quarterly_target_value,
                notes,
                is_current_year
            FROM sales_kpi_center_assignments_view
            WHERE year IN :years
            ORDER BY year DESC, kpi_center_name, kpi_name
        """
        
        try:
            df = pd.read_sql(text(query), self.engine, params={'years': tuple(years)})
            return df
        except Exception as e:
            logger.error(f"Error loading targets_raw: {e}")
            return pd.DataFrame()
    
    def _load_hierarchy(self) -> pd.DataFrame:
        """
        Load KPI Center hierarchy with calculated levels.
        
        Uses recursive CTE to build hierarchy tree with:
        - Level (0 = root, 1 = first child level, etc.)
        - Path (for display sorting)
        - is_leaf flag
        - has_children count
        """
        query = """
            WITH RECURSIVE hierarchy AS (
                -- Base case: root nodes (no parent)
                SELECT 
                    kc.id AS kpi_center_id,
                    kc.name AS kpi_center_name,
                    kc.type AS kpi_type,
                    kc.parent_center_id,
                    kc.description,
                    0 AS level,
                    CAST(kc.name AS CHAR(1000)) AS path
                FROM kpi_centers kc
                WHERE kc.parent_center_id IS NULL
                  AND (kc.delete_flag = 0 OR kc.delete_flag IS NULL)
                
                UNION ALL
                
                -- Recursive case: children
                SELECT 
                    kc.id,
                    kc.name,
                    kc.type,
                    kc.parent_center_id,
                    kc.description,
                    h.level + 1,
                    CONCAT(h.path, ' > ', kc.name)
                FROM kpi_centers kc
                INNER JOIN hierarchy h ON kc.parent_center_id = h.kpi_center_id
                WHERE kc.delete_flag = 0 OR kc.delete_flag IS NULL
            ),
            children_count AS (
                SELECT 
                    parent_center_id,
                    COUNT(*) AS child_count
                FROM kpi_centers
                WHERE (delete_flag = 0 OR delete_flag IS NULL)
                  AND parent_center_id IS NOT NULL
                GROUP BY parent_center_id
            )
            SELECT 
                h.kpi_center_id,
                h.kpi_center_name,
                h.kpi_type,
                h.parent_center_id,
                h.description,
                h.level,
                h.path,
                CASE WHEN cc.child_count IS NULL OR cc.child_count = 0 THEN 1 ELSE 0 END AS is_leaf,
                COALESCE(cc.child_count, 0) AS has_children
            FROM hierarchy h
            LEFT JOIN children_count cc ON h.kpi_center_id = cc.parent_center_id
            ORDER BY h.level, h.path
        """
        
        try:
            df = pd.read_sql(text(query), self.engine)
            
            # Convert has_children to boolean
            if not df.empty and 'has_children' in df.columns:
                df['has_children'] = df['has_children'].astype(bool)
            
            return df
        except Exception as e:
            logger.error(f"Error loading hierarchy: {e}")
            return pd.DataFrame()
    
    # =========================================================================
    # EXTRACT FILTER OPTIONS (from cached data)
    # =========================================================================
    
    def extract_filter_options(self, data: Dict) -> Dict:
        """
        Extract filter options from cached raw data.
        
        This replaces the need for separate SQL queries for filter dropdowns.
        All options are extracted from the already-loaded raw data.
        
        Args:
            data: Unified cache dict from get_unified_data()
            
        Returns:
            Dict with filter options:
            - kpi_centers: DataFrame with hierarchy info
            - entities: DataFrame with entity_id, entity_name
            - years: List of available years
            - kpi_types: List of KPI types
            - kpi_centers_with_assignment: Set of KPI Center IDs with targets
            - kpi_types_with_assignment: Set of KPI Types with targets
        """
        start_time = time.perf_counter()
        
        sales_df = data.get('sales_raw_df', pd.DataFrame())
        targets_df = data.get('targets_raw_df', pd.DataFrame())
        hierarchy_df = data.get('hierarchy_df', pd.DataFrame())
        
        options = {
            # KPI Centers from hierarchy (with level, parent info)
            'kpi_centers': hierarchy_df.copy() if not hierarchy_df.empty else pd.DataFrame(),
            
            # Entities extracted from sales data
            'entities': self._extract_entities(sales_df),
            
            # Years extracted from sales data
            'years': self._extract_years(sales_df),
            
            # KPI Types from hierarchy
            'kpi_types': self._extract_kpi_types(hierarchy_df),
            
            # KPI Centers with assignments (for "Only with KPI" filter)
            'kpi_centers_with_assignment': self._extract_assigned_centers(targets_df),
            
            # KPI Types with assignments
            'kpi_types_with_assignment': self._extract_assigned_types(targets_df),
        }
        
        elapsed = time.perf_counter() - start_time
        if DEBUG_TIMING:
            print(f"   📊 [extract_filter_options] {elapsed:.3f}s")
        
        return options
    
    def _extract_entities(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extract unique entities from sales data."""
        if df.empty or 'legal_entity_id' not in df.columns:
            return pd.DataFrame(columns=['entity_id', 'entity_name'])
        
        entities = df.groupby(['legal_entity_id', 'legal_entity']).size().reset_index(name='_count')
        entities = entities.rename(columns={
            'legal_entity_id': 'entity_id',
            'legal_entity': 'entity_name'
        })[['entity_id', 'entity_name']].drop_duplicates()
        
        return entities.sort_values('entity_name').reset_index(drop=True)
    
    def _extract_years(self, df: pd.DataFrame) -> List[int]:
        """Extract unique years from sales data."""
        if df.empty or 'invoice_year' not in df.columns:
            return [date.today().year]
        
        years = df['invoice_year'].dropna().unique().astype(int).tolist()
        return sorted(years, reverse=True)
    
    def _extract_kpi_types(self, df: pd.DataFrame) -> List[str]:
        """Extract unique KPI types from hierarchy."""
        if df.empty or 'kpi_type' not in df.columns:
            return []
        
        return sorted(df['kpi_type'].dropna().unique().tolist())
    
    def _extract_assigned_centers(self, df: pd.DataFrame) -> Set[int]:
        """Extract KPI Center IDs that have target assignments."""
        if df.empty or 'kpi_center_id' not in df.columns:
            return set()
        
        return set(df['kpi_center_id'].unique().tolist())
    
    def _extract_assigned_types(self, df: pd.DataFrame) -> Set[str]:
        """Extract KPI Types that have target assignments."""
        if df.empty or 'kpi_center_type' not in df.columns:
            return set()
        
        return set(df['kpi_center_type'].dropna().unique().tolist())
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def get_kpi_centers_with_assignments_by_year(
        self,
        year: int,
        kpi_type: str = None
    ) -> List[int]:
        """
        Get KPI Center IDs with assignments for a specific year.
        
        Uses cached targets_raw_df instead of SQL query.
        Includes ancestors (parents) of assigned centers.
        
        Args:
            year: Year to check
            kpi_type: Optional KPI type filter
            
        Returns:
            List of KPI Center IDs with assignments (includes ancestors)
        """
        cache = st.session_state.get(CACHE_KEY_UNIFIED)
        if not cache:
            return []
        
        targets_df = cache.get('targets_raw_df', pd.DataFrame())
        hierarchy_df = cache.get('hierarchy_df', pd.DataFrame())
        
        if targets_df.empty:
            return []
        
        # Filter targets by year
        mask = targets_df['year'] == year
        if kpi_type:
            mask = mask & (targets_df['kpi_center_type'] == kpi_type)
        
        direct_ids = set(targets_df[mask]['kpi_center_id'].unique().tolist())
        
        if not direct_ids or hierarchy_df.empty:
            return list(direct_ids)
        
        # Add ancestors (parents) of assigned centers
        all_ids = direct_ids.copy()
        for kpc_id in direct_ids:
            ancestors = self._get_ancestors_from_hierarchy(kpc_id, hierarchy_df)
            all_ids.update(ancestors)
        
        return list(all_ids)
    
    def _get_ancestors_from_hierarchy(
        self,
        kpi_center_id: int,
        hierarchy_df: pd.DataFrame
    ) -> List[int]:
        """Get all ancestor IDs for a KPI Center from hierarchy DataFrame."""
        ancestors = []
        current_id = kpi_center_id
        
        while True:
            row = hierarchy_df[hierarchy_df['kpi_center_id'] == current_id]
            if row.empty:
                break
            
            parent_id = row['parent_center_id'].iloc[0]
            if pd.isna(parent_id):
                break
            
            ancestors.append(int(parent_id))
            current_id = int(parent_id)
        
        return ancestors
    
    def get_descendants(
        self,
        kpi_center_id: int,
        include_self: bool = True
    ) -> List[int]:
        """
        Get all descendant IDs for a KPI Center.
        
        Uses cached hierarchy_df instead of SQL query.
        
        Args:
            kpi_center_id: Parent KPI Center ID
            include_self: Whether to include the parent itself
            
        Returns:
            List of descendant KPI Center IDs
        """
        cache = st.session_state.get(CACHE_KEY_UNIFIED)
        if not cache:
            return [kpi_center_id] if include_self else []
        
        hierarchy_df = cache.get('hierarchy_df', pd.DataFrame())
        if hierarchy_df.empty:
            return [kpi_center_id] if include_self else []
        
        # Build parent-child map
        children_map = {}
        for _, row in hierarchy_df.iterrows():
            parent = row['parent_center_id']
            if pd.notna(parent):
                parent = int(parent)
                if parent not in children_map:
                    children_map[parent] = []
                children_map[parent].append(int(row['kpi_center_id']))
        
        # BFS to get all descendants
        descendants = []
        if include_self:
            descendants.append(kpi_center_id)
        
        queue = [kpi_center_id]
        while queue:
            current = queue.pop(0)
            children = children_map.get(current, [])
            descendants.extend(children)
            queue.extend(children)
        
        return descendants
    
    def expand_kpi_center_ids_with_children(
        self,
        kpi_center_ids: List[int]
    ) -> List[int]:
        """
        Expand KPI Center IDs to include all descendants.
        
        When user selects a parent, this includes all children.
        
        Args:
            kpi_center_ids: List of selected KPI Center IDs
            
        Returns:
            Expanded list including all descendants
        """
        if not kpi_center_ids:
            return kpi_center_ids
        
        expanded = set()
        for kpc_id in kpi_center_ids:
            descendants = self.get_descendants(kpc_id, include_self=True)
            expanded.update(descendants)
        
        return list(expanded)
    
    def clear_cache(self):
        """Clear the unified data cache."""
        if CACHE_KEY_UNIFIED in st.session_state:
            del st.session_state[CACHE_KEY_UNIFIED]
        logger.info("Unified data cache cleared")