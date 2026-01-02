# utils/kpi_center_performance/queries.py
"""
KPI Center Performance Data Queries

VERSION: 3.8.2
CHANGELOG:
- v3.8.2: Restored get_kpi_center_list() and get_kpi_center_achievement_summary()
          for potential future use and backward compatibility
- v3.8.1: Restored get_leaf_descendants() - still used by metrics.py
- v3.8.0: Cleanup - Removed unused functions after Phase 2 optimization
          Removed: get_kpi_targets, get_backlog_data, get_backlog_in_period,
                   get_backlog_by_month, get_backlog_detail, get_backlog_risk_analysis
          File reduced from 1445 to ~880 lines (~39% reduction)
- v3.7.0: Phase 2 Optimization
          Added get_all_backlog_raw() for Pandas-based backlog processing
          Added get_kpi_targets_multi_year() to replace per-year loop
          Expected savings: ~8s per page load
- v3.6.0: Removed Complex KPI methods (now handled by complex_kpi_calculator.py)
          Added get_lookback_sales_data() for Pandas-based processing
- v3.5.0: Added DEBUG_QUERY_TIMING for terminal timing output
"""

import logging
import time
from datetime import date, datetime
from typing import List, Optional, Tuple, Dict
import pandas as pd
import streamlit as st
from sqlalchemy import text

from utils.db import get_db_engine
from .constants import LOOKBACK_YEARS, CACHE_TTL_SECONDS
from .access_control import AccessControl

logger = logging.getLogger(__name__)

# =============================================================================
# DEBUG TIMING FLAG - Set to True to see SQL query timings in terminal
# =============================================================================
DEBUG_QUERY_TIMING = True


class KPICenterQueries:
    """
    Data loading class for KPI Center performance.
    
    Usage:
        access = AccessControl(user_role)
        queries = KPICenterQueries(access)
        
        sales_df = queries.get_sales_data(start_date, end_date)
        targets_df = queries.get_kpi_targets(year)
    """
    
    def __init__(self, access_control: AccessControl):
        """
        Initialize with access control.
        
        Args:
            access_control: AccessControl instance for filtering
        """
        self.access = access_control
        self._engine = None
    
    @property
    def engine(self):
        """Lazy load database engine."""
        if self._engine is None:
            self._engine = get_db_engine()
        return self._engine
    
    # =========================================================================
    # KPI CENTER HIERARCHY HELPERS
    # Note: get_kpi_center_hierarchy() moved to setup/queries.py (v3.4.0)
    # =========================================================================
    
    def get_child_kpi_center_ids(self, parent_id: int) -> List[int]:
        """
        Get all child KPI Center IDs for a given parent (recursive).
        
        Args:
            parent_id: Parent KPI Center ID
            
        Returns:
            List of child KPI Center IDs (including grandchildren, etc.)
        """
        query = """
            WITH RECURSIVE children AS (
                -- Base case: direct children
                SELECT id AS kpi_center_id
                FROM kpi_centers
                WHERE parent_center_id = :parent_id
                  AND delete_flag = 0
                
                UNION ALL
                
                -- Recursive case: grandchildren
                SELECT kc.id
                FROM kpi_centers kc
                INNER JOIN children c ON kc.parent_center_id = c.kpi_center_id
                WHERE kc.delete_flag = 0
            )
            SELECT kpi_center_id FROM children
        """
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query), {'parent_id': parent_id})
                return [row[0] for row in result]
        except Exception as e:
            logger.error(f"Error fetching child KPI Centers: {e}")
            return []
    
    # =========================================================================
    # CORE SALES DATA
    # =========================================================================
    
    def get_sales_data(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None,
        include_children: bool = True
    ) -> pd.DataFrame:
        """
        Get sales data aggregated by KPI Center.
        
        Args:
            start_date: Start of period
            end_date: End of period
            kpi_center_ids: Optional list of KPI Centers to filter
            entity_ids: Optional list of entity IDs to filter
            include_children: Include child KPI Centers in totals
            
        Returns:
            DataFrame with sales transactions
        """
        if not self.access.can_access_page():
            return pd.DataFrame()
        
        # Expand to include children if requested
        if kpi_center_ids:
            kpi_center_ids = self.access.validate_selected_kpi_centers(kpi_center_ids)
            if include_children:
                expanded_ids = set(kpi_center_ids)
                for parent_id in kpi_center_ids:
                    child_ids = self.get_child_kpi_center_ids(parent_id)
                    expanded_ids.update(child_ids)
                kpi_center_ids = list(expanded_ids)
        else:
            kpi_center_ids = self.access.get_accessible_kpi_center_ids()
        
        if not kpi_center_ids:
            return pd.DataFrame()
        
        query = """
            SELECT 
                data_source,
                unified_line_id,
                kpi_center_id,
                kpi_center,
                kpi_type,
                split_rate_percent,
                inv_date,
                inv_number,
                vat_number,
                legal_entity,
                legal_entity_id,
                customer,
                customer_id,
                customer_code,
                customer_type,
                customer_po_number,
                oc_number,
                oc_date,
                product_id,
                product_pn,
                pt_code,
                brand,
                sales_by_kpi_center_usd,
                gross_profit_by_kpi_center_usd,
                gp1_by_kpi_center_usd,
                broker_commission_by_kpi_center_usd,
                invoice_month,
                invoice_year
            FROM unified_sales_by_kpi_center_view
            WHERE inv_date BETWEEN :start_date AND :end_date
              AND kpi_center_id IN :kpi_center_ids
        """
        
        params = {
            'start_date': start_date,
            'end_date': end_date,
            'kpi_center_ids': tuple(kpi_center_ids)
        }
        
        if entity_ids:
            query += " AND legal_entity_id IN :entity_ids"
            params['entity_ids'] = tuple(entity_ids)
        
        query += " ORDER BY inv_date DESC"
        
        return self._execute_query(query, params, "sales_data")
    
    # =========================================================================
    # LOOKBACK SALES DATA (NEW v3.5.0 - for Pandas optimization)
    # =========================================================================
    
    def get_lookback_sales_data(
        self,
        end_date: date,
        lookback_years: int = 5
    ) -> pd.DataFrame:
        """
        Load ALL sales data for Pandas-based processing.
        
        NEW v3.5.0: This method loads data once for:
        1. Sidebar options extraction (KPI Centers, Entities, Years)
        2. Complex KPI calculations (New Customers, New Products, New Business)
        
        PERFORMANCE:
        - Replaces 4 lookup queries (~5.7s) + 9 Complex KPI queries (~27s)
        - Total before: ~33s
        - Total after: ~3s (one SQL query) + ~0.3s (Pandas) = ~3.3s
        - Savings: ~90%
        
        Args:
            end_date: End date for lookback period
            lookback_years: Number of years to look back (default 5)
            
        Returns:
            DataFrame with ALL sales data including:
            - KPI Center info (for sidebar & filtering)
            - Entity info (for sidebar & filtering)
            - Customer info (for Complex KPIs)
            - Product info (for Complex KPIs)
            - Date info (for filtering & analysis)
            - Amounts (for calculations)
        """
        lookback_start = date(end_date.year - lookback_years, 1, 1)
        
        query = """
            SELECT 
                -- KPI Center info (for sidebar & filtering)
                kpi_center_id,
                kpi_center AS kpi_center_name,
                kpi_type,
                split_rate_percent,
                
                -- Entity info (for sidebar & filtering)
                legal_entity_id,
                legal_entity,
                
                -- Date info (for filtering & analysis)
                inv_date,
                inv_number,
                invoice_month,
                invoice_year,
                
                -- Customer info (for Complex KPIs)
                customer_id,
                customer,
                customer_code,
                customer_type,
                
                -- Product info (for Complex KPIs)
                product_id,
                product_pn,
                pt_code,
                brand,
                legacy_code,
                
                -- Amounts (for calculations)
                sales_by_kpi_center_usd,
                gross_profit_by_kpi_center_usd,
                gp1_by_kpi_center_usd
            FROM unified_sales_by_kpi_center_view
            WHERE inv_date >= :lookback_start
        """
        
        return self._execute_query(
            query, 
            {'lookback_start': lookback_start}, 
            "lookback_sales_data"
        )
    
    # =========================================================================
    # BACKLOG RAW DATA (NEW v3.7.0 - for Pandas optimization)
    # =========================================================================
    
    def get_all_backlog_raw(
        self,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None,
        include_children: bool = True
    ) -> pd.DataFrame:
        """
        Load ALL raw backlog data for Pandas-based processing.
        
        NEW v3.7.0: This method loads data once for:
        1. Backlog Summary (by KPI Center)
        2. Backlog In-Period (filtered by ETD)
        3. Backlog By Month (grouped by ETD month)
        4. Backlog Detail (raw records)
        5. Backlog Risk Analysis
        
        PERFORMANCE:
        - Replaces 4 SQL queries (~6.3s) with 1 query (~1.6s)
        - Savings: ~75%
        
        Args:
            kpi_center_ids: Optional list of KPI Center IDs to filter
            entity_ids: Optional list of entity IDs to filter
            include_children: Include child KPI Centers
            
        Returns:
            DataFrame with ALL backlog records (uninvoiced orders)
        """
        if not self.access.can_access_page():
            return pd.DataFrame()
        
        # Expand KPI Center IDs to include children
        if kpi_center_ids:
            kpi_center_ids = self.access.validate_selected_kpi_centers(kpi_center_ids)
            if include_children:
                expanded_ids = set(kpi_center_ids)
                for parent_id in kpi_center_ids:
                    child_ids = self.get_child_kpi_center_ids(parent_id)
                    expanded_ids.update(child_ids)
                kpi_center_ids = list(expanded_ids)
        else:
            kpi_center_ids = self.access.get_accessible_kpi_center_ids()
        
        if not kpi_center_ids:
            return pd.DataFrame()
        
        # Query all columns needed for all aggregations
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
                entity_id,
                
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
            WHERE kpi_center_id IN :kpi_center_ids
              AND (invoice_completion_percent < 100 OR invoice_completion_percent IS NULL)
        """
        
        params = {'kpi_center_ids': tuple(kpi_center_ids)}
        
        if entity_ids:
            query += " AND entity_id IN :entity_ids"
            params['entity_ids'] = tuple(entity_ids)
        
        query += " ORDER BY backlog_by_kpi_center_usd DESC"
        
        return self._execute_query(query, params, "backlog_raw_all")
    
    # =========================================================================
    # KPI TARGETS MULTI-YEAR (NEW v3.7.0 - replaces per-year loop)
    # =========================================================================
    
    def get_kpi_targets_multi_year(
        self,
        years: List[int],
        kpi_center_ids: List[int] = None,
        include_children: bool = True
    ) -> pd.DataFrame:
        """
        Get KPI targets for multiple years in a single query.
        
        NEW v3.7.0: Replaces per-year loop that called get_kpi_targets() 3 times.
        
        PERFORMANCE:
        - Before: 3 queries (0.115s each) + overhead = ~3.7s
        - After: 1 query = ~0.15s
        - Savings: ~96%
        
        Args:
            years: List of years to query (e.g., [2024, 2025, 2026])
            kpi_center_ids: Optional list of KPI Centers
            include_children: Include child KPI Centers
            
        Returns:
            DataFrame with KPI assignments for all specified years
        """
        if not self.access.can_access_page():
            return pd.DataFrame()
        
        if not years:
            return pd.DataFrame()
        
        # Expand KPI Center IDs
        if kpi_center_ids:
            kpi_center_ids = self.access.validate_selected_kpi_centers(kpi_center_ids)
            if include_children:
                expanded_ids = set(kpi_center_ids)
                for parent_id in kpi_center_ids:
                    child_ids = self.get_child_kpi_center_ids(parent_id)
                    expanded_ids.update(child_ids)
                kpi_center_ids = list(expanded_ids)
        else:
            kpi_center_ids = self.access.get_accessible_kpi_center_ids()
        
        if not kpi_center_ids:
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
              AND kpi_center_id IN :kpi_center_ids
            ORDER BY year, kpi_center_name, kpi_name
        """
        
        params = {
            'years': tuple(years),
            'kpi_center_ids': tuple(kpi_center_ids)
        }
        
        return self._execute_query(query, params, "kpi_targets_multi_year")
    
    def get_previous_year_data(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None
    ) -> pd.DataFrame:
        """
        Get previous year's sales data for the same period.
        
        Args:
            start_date: Current period start
            end_date: Current period end
            kpi_center_ids: Optional filter
            entity_ids: Optional filter
            
        Returns:
            DataFrame with previous year's sales
        """
        # Calculate previous year dates
        prev_start = date(start_date.year - 1, start_date.month, start_date.day)
        try:
            prev_end = date(end_date.year - 1, end_date.month, end_date.day)
        except ValueError:
            # Handle Feb 29 -> Feb 28
            prev_end = date(end_date.year - 1, end_date.month, 28)
        
        return self.get_sales_data(
            start_date=prev_start,
            end_date=prev_end,
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids
        )

    # =========================================================================
    # LOOKUP DATA METHODS
    # =========================================================================
    
    def get_kpi_center_list(self) -> pd.DataFrame:
        """
        Get list of KPI Centers for filter dropdowns.
        
        Returns:
            DataFrame with kpi_center_id, kpi_center_name, kpi_type, parent_center_id
        """
        query = """
            SELECT DISTINCT
                kc.id AS kpi_center_id,
                kc.name AS kpi_center_name,
                kc.type AS kpi_type,
                kc.parent_center_id,
                kc.description
            FROM kpi_centers kc
            INNER JOIN unified_sales_by_kpi_center_view u ON kc.id = u.kpi_center_id
            WHERE kc.delete_flag = 0
            ORDER BY kc.type, kc.name
        """
        
        return self._execute_query(query, {}, "kpi_center_list")

    def get_kpi_center_achievement_summary(
        self,
        year: int,
        kpi_center_ids: List[int] = None,
        proration: float = 1.0
    ) -> pd.DataFrame:
        """
        Get KPI Center achievement summary for comparison chart.
        
        Returns DataFrame with kpi_center, revenue, target, achievement
        suitable for build_achievement_bar_chart().
        
        Args:
            year: Target year
            kpi_center_ids: Optional list of KPI Center IDs
            proration: Target proration factor (0-1)
            
        Returns:
            DataFrame with columns: kpi_center_id, kpi_center, revenue, 
                                   target, achievement
        """
        if not self.access.can_access_page():
            return pd.DataFrame()
        
        if kpi_center_ids:
            kpi_center_ids = self.access.validate_selected_kpi_centers(kpi_center_ids)
        else:
            kpi_center_ids = self.access.get_accessible_kpi_center_ids()
        
        if not kpi_center_ids:
            return pd.DataFrame()
        
        query = """
            WITH sales_summary AS (
                SELECT 
                    kpi_center_id,
                    kpi_center,
                    SUM(sales_by_kpi_center_usd) as revenue,
                    SUM(gross_profit_by_kpi_center_usd) as gross_profit
                FROM unified_sales_by_kpi_center_view
                WHERE invoice_year = :year
                  AND kpi_center_id IN :kpi_center_ids
                GROUP BY kpi_center_id, kpi_center
            ),
            targets AS (
                SELECT 
                    kpi_center_id,
                    MAX(CASE WHEN LOWER(kpi_name) = 'revenue' THEN annual_target_value_numeric END) as revenue_target
                FROM sales_kpi_center_assignments_view
                WHERE year = :year
                  AND kpi_center_id IN :kpi_center_ids
                GROUP BY kpi_center_id
            )
            SELECT 
                s.kpi_center_id,
                s.kpi_center,
                s.revenue,
                s.gross_profit,
                COALESCE(t.revenue_target, 0) as annual_target,
                COALESCE(t.revenue_target, 0) * :proration as prorated_target,
                CASE 
                    WHEN COALESCE(t.revenue_target, 0) * :proration > 0 
                    THEN (s.revenue / (t.revenue_target * :proration)) * 100
                    ELSE NULL 
                END as achievement
            FROM sales_summary s
            LEFT JOIN targets t ON s.kpi_center_id = t.kpi_center_id
            ORDER BY achievement DESC NULLS LAST
        """
        
        params = {
            'year': year,
            'kpi_center_ids': tuple(kpi_center_ids),
            'proration': proration
        }
        
        return self._execute_query(query, params, "kpi_center_achievement_summary")

    # =========================================================================
    # HIERARCHY METHODS - NEW v3.2.0
    # =========================================================================
    def get_hierarchy_with_levels(
        self,
        kpi_type: str = None,
        include_all_types: bool = False
    ) -> pd.DataFrame:
        """
        Get KPI Center hierarchy with calculated levels.
        
        NEW v3.2.0: Dynamic level calculation using recursive CTE.
        
        Args:
            kpi_type: Filter by KPI type (TERRITORY, BRAND, etc.)
            include_all_types: If True, include all types
            
        Returns:
            DataFrame with columns:
            - kpi_center_id, kpi_center_name, kpi_type
            - parent_center_id, level, is_leaf
            - path (for sorting/display)
        """
        query = """
            WITH RECURSIVE hierarchy AS (
                -- Base case: root nodes (no parent)
                SELECT 
                    kc.id as kpi_center_id,
                    kc.name as kpi_center_name,
                    kc.type as kpi_type,
                    kc.parent_center_id,
                    0 as level,
                    CAST(kc.name AS CHAR(1000)) as path
                FROM prostechvn.kpi_centers kc
                WHERE kc.parent_center_id IS NULL
                  AND kc.delete_flag = 0
                
                UNION ALL
                
                -- Recursive case: children
                SELECT 
                    kc.id,
                    kc.name,
                    kc.type,
                    kc.parent_center_id,
                    h.level + 1,
                    CONCAT(h.path, ' > ', kc.name)
                FROM prostechvn.kpi_centers kc
                INNER JOIN hierarchy h ON kc.parent_center_id = h.kpi_center_id
                WHERE kc.delete_flag = 0
            ),
            children_count AS (
                SELECT 
                    parent_center_id,
                    COUNT(*) as child_count
                FROM prostechvn.kpi_centers
                WHERE delete_flag = 0 AND parent_center_id IS NOT NULL
                GROUP BY parent_center_id
            )
            SELECT 
                h.kpi_center_id,
                h.kpi_center_name,
                h.kpi_type,
                h.parent_center_id,
                h.level,
                h.path,
                CASE WHEN cc.child_count IS NULL OR cc.child_count = 0 THEN 1 ELSE 0 END as is_leaf,
                COALESCE(cc.child_count, 0) as direct_children_count
            FROM hierarchy h
            LEFT JOIN children_count cc ON h.kpi_center_id = cc.parent_center_id
            WHERE 1=1
        """
        
        if kpi_type and not include_all_types:
            query += " AND h.kpi_type = :kpi_type"
        
        query += " ORDER BY h.level, h.path"
        
        params = {'kpi_type': kpi_type} if kpi_type else {}
        
        return self._execute_query(query, params, "hierarchy_with_levels")
    def get_all_descendants(
        self,
        kpi_center_id: int,
        include_self: bool = False
    ) -> List[int]:
        """
        Get all descendant KPI Center IDs for a given parent.
        
        NEW v3.2.0: Recursive descendant lookup.
        
        Args:
            kpi_center_id: Parent KPI Center ID
            include_self: Whether to include the parent itself
            
        Returns:
            List of descendant KPI Center IDs
        """
        query = """
            WITH RECURSIVE descendants AS (
                -- Start with direct children
                SELECT id as kpi_center_id
                FROM prostechvn.kpi_centers
                WHERE parent_center_id = :parent_id
                  AND delete_flag = 0
                
                UNION ALL
                
                -- Recursive: get children of children
                SELECT kc.id
                FROM prostechvn.kpi_centers kc
                INNER JOIN descendants d ON kc.parent_center_id = d.kpi_center_id
                WHERE kc.delete_flag = 0
            )
            SELECT kpi_center_id FROM descendants
        """
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query), {'parent_id': kpi_center_id})
                descendants = [row[0] for row in result]
                
                if include_self:
                    descendants.insert(0, kpi_center_id)
                
                return descendants
        except Exception as e:
            logger.error(f"Error getting descendants for {kpi_center_id}: {e}")
            return [kpi_center_id] if include_self else []
    
    def get_leaf_descendants(
        self,
        kpi_center_id: int
    ) -> List[int]:
        """
        Get only leaf (no children) descendants for a KPI Center.
        
        Used for parent progress calculation in metrics.py.
        
        Args:
            kpi_center_id: Parent KPI Center ID
            
        Returns:
            List of leaf descendant KPI Center IDs
        """
        query = """
            WITH RECURSIVE descendants AS (
                -- Start with the center itself
                SELECT 
                    id as kpi_center_id,
                    id as original_id
                FROM prostechvn.kpi_centers
                WHERE id = :parent_id
                  AND delete_flag = 0
                
                UNION ALL
                
                -- Recursive: get all descendants
                SELECT kc.id, d.original_id
                FROM prostechvn.kpi_centers kc
                INNER JOIN descendants d ON kc.parent_center_id = d.kpi_center_id
                WHERE kc.delete_flag = 0
            ),
            leaf_nodes AS (
                SELECT d.kpi_center_id
                FROM descendants d
                WHERE NOT EXISTS (
                    SELECT 1 FROM prostechvn.kpi_centers kc
                    WHERE kc.parent_center_id = d.kpi_center_id
                      AND kc.delete_flag = 0
                )
                AND d.kpi_center_id != :parent_id  -- Exclude parent itself
            )
            SELECT kpi_center_id FROM leaf_nodes
        """
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query), {'parent_id': kpi_center_id})
                return [row[0] for row in result]
        except Exception as e:
            logger.error(f"Error getting leaf descendants for {kpi_center_id}: {e}")
            return []

    def get_ancestors(
        self,
        kpi_center_id: int,
        include_self: bool = False
    ) -> List[int]:
        """
        Get all ancestor KPI Center IDs for a given center.
        
        NEW v3.2.0: For hierarchy traversal.
        
        Args:
            kpi_center_id: KPI Center ID
            include_self: Whether to include the center itself
            
        Returns:
            List of ancestor KPI Center IDs (from immediate parent to root)
        """
        query = """
            WITH RECURSIVE ancestors AS (
                -- Start with immediate parent
                SELECT parent_center_id as kpi_center_id, 1 as depth
                FROM prostechvn.kpi_centers
                WHERE id = :center_id
                  AND parent_center_id IS NOT NULL
                  AND delete_flag = 0
                
                UNION ALL
                
                -- Recursive: get parent of parent
                SELECT kc.parent_center_id, a.depth + 1
                FROM prostechvn.kpi_centers kc
                INNER JOIN ancestors a ON kc.id = a.kpi_center_id
                WHERE kc.parent_center_id IS NOT NULL
                  AND kc.delete_flag = 0
            )
            SELECT kpi_center_id FROM ancestors ORDER BY depth
        """
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query), {'center_id': kpi_center_id})
                ancestors = [row[0] for row in result]
                
                if include_self:
                    ancestors.insert(0, kpi_center_id)
                
                return ancestors
        except Exception as e:
            logger.error(f"Error getting ancestors for {kpi_center_id}: {e}")
            return [kpi_center_id] if include_self else []
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _execute_query(
        self, 
        query: str, 
        params: dict, 
        query_name: str = "query"
    ) -> pd.DataFrame:
        """
        Execute SQL query and return DataFrame.
        
        UPDATED v3.5.0: Added timing output to terminal.
        """
        start_time = time.perf_counter()
        
        try:
            logger.debug(f"Executing {query_name}")
            df = pd.read_sql(text(query), self.engine, params=params)
            
            elapsed = time.perf_counter() - start_time
            
            if DEBUG_QUERY_TIMING:
                print(f"   📊 SQL [{query_name}]: {elapsed:.3f}s → {len(df):,} rows")
            
            logger.debug(f"{query_name} returned {len(df)} rows")
            return df
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            if DEBUG_QUERY_TIMING:
                print(f"   ❌ SQL [{query_name}]: {elapsed:.3f}s → ERROR: {e}")
            logger.error(f"Error executing {query_name}: {e}")
            return pd.DataFrame()