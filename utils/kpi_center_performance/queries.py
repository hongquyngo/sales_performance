# utils/kpi_center_performance/queries.py
"""
KPI Center Performance Data Queries

VERSION: 3.6.0
CHANGELOG:
- v3.6.0: Removed Complex KPI methods (now handled by complex_kpi_calculator.py)
          Removed get_entity_list, get_available_years (extracted from lookback)
          Removed calculate_complex_kpi_value (replaced by ComplexKPICalculator)
          Added get_lookback_sales_data() for Pandas-based processing
          File reduced from 2779 to 1248 lines (~55% reduction)
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
    # KPI TARGETS
    # =========================================================================
    
    def get_kpi_targets(
        self,
        year: int,
        kpi_center_ids: List[int] = None,
        include_children: bool = True
    ) -> pd.DataFrame:
        """
        Get KPI targets for specified year and KPI Centers.
        
        Args:
            year: Target year
            kpi_center_ids: Optional list of KPI Centers
            include_children: Include child KPI Centers
            
        Returns:
            DataFrame with KPI assignments
        """
        if not self.access.can_access_page():
            return pd.DataFrame()
        
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
            WHERE year = :year
              AND kpi_center_id IN :kpi_center_ids
            ORDER BY kpi_center_name, kpi_name
        """
        
        params = {
            'year': year,
            'kpi_center_ids': tuple(kpi_center_ids)
        }
        
        return self._execute_query(query, params, "kpi_targets")
    
    # =========================================================================
    # BACKLOG DATA - UPDATED v2.14.0: Added exclude_internal parameter
    # =========================================================================
    
    def get_backlog_data(
        self,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None,
        include_children: bool = True,
        exclude_internal: bool = True  # NEW v2.14.0
    ) -> pd.DataFrame:
        """
        Get backlog summary by KPI Center.
        Only includes uninvoiced orders (invoice_completion_percent < 100).
        
        NEW v2.14.0: Added exclude_internal parameter
        - When True (default): Sets backlog_by_kpi_center_usd = 0 for Internal customers
        - GP values are preserved (same business logic as Sales data)
        
        Args:
            kpi_center_ids: Optional list of KPI Center IDs to filter
            entity_ids: Optional list of entity IDs to filter
            include_children: Include child KPI Centers
            exclude_internal: If True, set revenue = 0 for Internal customers (keep GP)
        """
        if not self.access.can_access_page():
            return pd.DataFrame()
        
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
        
        # NEW v2.14.0: Use CASE WHEN to set revenue = 0 for Internal customers
        if exclude_internal:
            query = """
                SELECT 
                    kpi_center_id,
                    kpi_center,
                    kpi_type,
                    COUNT(DISTINCT oc_number) AS backlog_orders,
                    SUM(CASE 
                        WHEN customer_type = 'Internal' THEN 0 
                        ELSE backlog_by_kpi_center_usd 
                    END) AS total_backlog_usd,
                    SUM(backlog_gp_by_kpi_center_usd) AS total_backlog_gp_usd
                FROM backlog_by_kpi_center_flat_looker_view
                WHERE kpi_center_id IN :kpi_center_ids
                  AND (invoice_completion_percent < 100 OR invoice_completion_percent IS NULL)
            """
        else:
            query = """
                SELECT 
                    kpi_center_id,
                    kpi_center,
                    kpi_type,
                    COUNT(DISTINCT oc_number) AS backlog_orders,
                    SUM(backlog_by_kpi_center_usd) AS total_backlog_usd,
                    SUM(backlog_gp_by_kpi_center_usd) AS total_backlog_gp_usd
                FROM backlog_by_kpi_center_flat_looker_view
                WHERE kpi_center_id IN :kpi_center_ids
                  AND (invoice_completion_percent < 100 OR invoice_completion_percent IS NULL)
            """
        
        params = {'kpi_center_ids': tuple(kpi_center_ids)}
        
        if entity_ids:
            query += " AND entity_id IN :entity_ids"
            params['entity_ids'] = tuple(entity_ids)
        
        query += " GROUP BY kpi_center_id, kpi_center, kpi_type"
        
        return self._execute_query(query, params, "backlog_data")
    
    def get_backlog_in_period(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None,
        include_children: bool = True,
        exclude_internal: bool = True  # NEW v2.14.0
    ) -> pd.DataFrame:
        """
        Get backlog with ETD within specified period.
        Only includes uninvoiced orders.
        
        NEW v2.14.0: Added exclude_internal parameter
        - When True (default): Sets backlog_by_kpi_center_usd = 0 for Internal customers
        - GP values are preserved
        """
        if not self.access.can_access_page():
            return pd.DataFrame()
        
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
        
        # NEW v2.14.0: Use CASE WHEN for exclude_internal
        if exclude_internal:
            query = """
                SELECT 
                    kpi_center_id,
                    kpi_center,
                    kpi_type,
                    COUNT(DISTINCT oc_number) AS in_period_orders,
                    SUM(CASE 
                        WHEN customer_type = 'Internal' THEN 0 
                        ELSE backlog_by_kpi_center_usd 
                    END) AS in_period_backlog_usd,
                    SUM(backlog_gp_by_kpi_center_usd) AS in_period_backlog_gp_usd
                FROM backlog_by_kpi_center_flat_looker_view
                WHERE kpi_center_id IN :kpi_center_ids
                  AND (invoice_completion_percent < 100 OR invoice_completion_percent IS NULL)
                  AND etd BETWEEN :start_date AND :end_date
            """
        else:
            query = """
                SELECT 
                    kpi_center_id,
                    kpi_center,
                    kpi_type,
                    COUNT(DISTINCT oc_number) AS in_period_orders,
                    SUM(backlog_by_kpi_center_usd) AS in_period_backlog_usd,
                    SUM(backlog_gp_by_kpi_center_usd) AS in_period_backlog_gp_usd
                FROM backlog_by_kpi_center_flat_looker_view
                WHERE kpi_center_id IN :kpi_center_ids
                  AND (invoice_completion_percent < 100 OR invoice_completion_percent IS NULL)
                  AND etd BETWEEN :start_date AND :end_date
            """
        
        params = {
            'kpi_center_ids': tuple(kpi_center_ids),
            'start_date': start_date,
            'end_date': end_date
        }
        
        if entity_ids:
            query += " AND entity_id IN :entity_ids"
            params['entity_ids'] = tuple(entity_ids)
        
        query += " GROUP BY kpi_center_id, kpi_center, kpi_type"
        
        return self._execute_query(query, params, "backlog_in_period")
    
    def get_backlog_by_month(
        self,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None,
        include_children: bool = True,
        exclude_internal: bool = True  # NEW v2.14.0
    ) -> pd.DataFrame:
        """
        Get backlog grouped by ETD month/year.
        Only includes uninvoiced orders.
        
        NEW v2.14.0: Added exclude_internal parameter
        - When True (default): Sets backlog_by_kpi_center_usd = 0 for Internal customers
        - GP values are preserved
        """
        if not self.access.can_access_page():
            return pd.DataFrame()
        
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
        
        # NEW v2.14.0: Use CASE WHEN for exclude_internal
        if exclude_internal:
            query = """
                SELECT 
                    etd_year,
                    etd_month,
                    COUNT(DISTINCT oc_number) AS backlog_orders,
                    SUM(CASE 
                        WHEN customer_type = 'Internal' THEN 0 
                        ELSE backlog_by_kpi_center_usd 
                    END) AS backlog_usd,
                    SUM(backlog_gp_by_kpi_center_usd) AS backlog_gp_usd
                FROM backlog_by_kpi_center_flat_looker_view
                WHERE kpi_center_id IN :kpi_center_ids
                  AND (invoice_completion_percent < 100 OR invoice_completion_percent IS NULL)
            """
        else:
            query = """
                SELECT 
                    etd_year,
                    etd_month,
                    COUNT(DISTINCT oc_number) AS backlog_orders,
                    SUM(backlog_by_kpi_center_usd) AS backlog_usd,
                    SUM(backlog_gp_by_kpi_center_usd) AS backlog_gp_usd
                FROM backlog_by_kpi_center_flat_looker_view
                WHERE kpi_center_id IN :kpi_center_ids
                  AND (invoice_completion_percent < 100 OR invoice_completion_percent IS NULL)
            """
        
        params = {'kpi_center_ids': tuple(kpi_center_ids)}
        
        if entity_ids:
            query += " AND entity_id IN :entity_ids"
            params['entity_ids'] = tuple(entity_ids)
        
        query += """
            GROUP BY etd_year, etd_month
            ORDER BY etd_year, 
                     FIELD(etd_month, 'Jan','Feb','Mar','Apr','May','Jun',
                                      'Jul','Aug','Sep','Oct','Nov','Dec')
        """
        
        return self._execute_query(query, params, "backlog_by_month")
    
    def get_backlog_detail(
        self,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None,
        include_children: bool = True,
        limit: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Get detailed backlog records for drill-down.
        Only includes uninvoiced orders.
        
        NOTE: This function returns RAW data with ALL columns including Internal.
        The exclude_internal logic is NOT applied here because the detail table
        should show all records. Revenue exclusion is handled in metrics calculation.
        
        Args:
            kpi_center_ids: Optional list of KPI Center IDs to filter
            entity_ids: Optional list of entity IDs to filter
            include_children: Include child KPI Centers
            limit: Optional row limit (None = no limit)
        
        Returns:
            DataFrame with individual backlog line items
        """
        if not self.access.can_access_page():
            return pd.DataFrame()
        
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
                oc_number,
                oc_date,
                etd,
                customer,
                customer_id,
                customer_type,
                customer_po_number,
                product_pn,
                pt_code,
                package_size,
                brand,
                kpi_center,
                kpi_center_id,
                kpi_type,
                legal_entity,
                entity_id,
                backlog_by_kpi_center_usd,
                backlog_gp_by_kpi_center_usd,
                split_rate_percent,
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
        
        if limit is not None:
            query += f" LIMIT {limit}"
        
        return self._execute_query(query, params, "backlog_detail")
    
    # =========================================================================
    # BACKLOG RISK ANALYSIS - UPDATED v2.14.0: Added exclude_internal
    # =========================================================================
    
    def get_backlog_risk_analysis(
        self,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None,
        start_date: date = None,
        end_date: date = None,
        exclude_internal: bool = True  # NEW v2.14.0
    ) -> Dict:
        """
        Analyze backlog for overdue and risk factors.
        
        NEW v2.14.0: Added exclude_internal parameter
        - When True (default): Revenue metrics exclude Internal, GP metrics kept
        
        Returns:
            Dictionary with:
            - overdue_orders: Orders with ETD in the past
            - overdue_revenue: Total revenue at risk (excludes Internal if flag set)
            - at_risk_orders: Orders with ETD within 7 days
            - in_period_overdue: Overdue orders within selected period
        """
        if not self.access.can_access_page():
            return {}
        
        if kpi_center_ids:
            kpi_center_ids = self.access.validate_selected_kpi_centers(kpi_center_ids)
        else:
            kpi_center_ids = self.access.get_accessible_kpi_center_ids()
        
        if not kpi_center_ids:
            return {}
        
        # NEW v2.14.0: Use CASE WHEN for revenue metrics when exclude_internal=True
        if exclude_internal:
            query = """
                SELECT 
                    COUNT(DISTINCT CASE WHEN days_until_etd < 0 THEN oc_number END) AS overdue_orders,
                    SUM(CASE 
                        WHEN days_until_etd < 0 AND customer_type != 'Internal' 
                        THEN backlog_by_kpi_center_usd 
                        ELSE 0 
                    END) AS overdue_revenue,
                    SUM(CASE WHEN days_until_etd < 0 THEN backlog_gp_by_kpi_center_usd ELSE 0 END) AS overdue_gp,
                    COUNT(DISTINCT CASE WHEN days_until_etd BETWEEN 0 AND 7 THEN oc_number END) AS at_risk_orders,
                    SUM(CASE 
                        WHEN days_until_etd BETWEEN 0 AND 7 AND customer_type != 'Internal'
                        THEN backlog_by_kpi_center_usd 
                        ELSE 0 
                    END) AS at_risk_revenue,
                    COUNT(DISTINCT oc_number) AS total_orders,
                    SUM(CASE 
                        WHEN customer_type != 'Internal' 
                        THEN backlog_by_kpi_center_usd 
                        ELSE 0 
                    END) AS total_backlog
                FROM backlog_by_kpi_center_flat_looker_view
                WHERE kpi_center_id IN :kpi_center_ids
                  AND (invoice_completion_percent < 100 OR invoice_completion_percent IS NULL)
            """
        else:
            query = """
                SELECT 
                    COUNT(DISTINCT CASE WHEN days_until_etd < 0 THEN oc_number END) AS overdue_orders,
                    SUM(CASE WHEN days_until_etd < 0 THEN backlog_by_kpi_center_usd ELSE 0 END) AS overdue_revenue,
                    SUM(CASE WHEN days_until_etd < 0 THEN backlog_gp_by_kpi_center_usd ELSE 0 END) AS overdue_gp,
                    COUNT(DISTINCT CASE WHEN days_until_etd BETWEEN 0 AND 7 THEN oc_number END) AS at_risk_orders,
                    SUM(CASE WHEN days_until_etd BETWEEN 0 AND 7 THEN backlog_by_kpi_center_usd ELSE 0 END) AS at_risk_revenue,
                    COUNT(DISTINCT oc_number) AS total_orders,
                    SUM(backlog_by_kpi_center_usd) AS total_backlog
                FROM backlog_by_kpi_center_flat_looker_view
                WHERE kpi_center_id IN :kpi_center_ids
                  AND (invoice_completion_percent < 100 OR invoice_completion_percent IS NULL)
            """
        
        params = {'kpi_center_ids': tuple(kpi_center_ids)}
        
        if entity_ids:
            query += " AND entity_id IN :entity_ids"
            params['entity_ids'] = tuple(entity_ids)
        
        df = self._execute_query(query, params, "backlog_risk_analysis")
        
        if df.empty:
            return {}
        
        row = df.iloc[0]
        
        # Get in-period overdue if dates provided
        in_period_overdue = 0
        in_period_overdue_revenue = 0
        
        if start_date and end_date:
            # NEW v2.14.0: Apply same exclude_internal logic to period query
            if exclude_internal:
                period_query = """
                    SELECT 
                        COUNT(DISTINCT CASE WHEN days_until_etd < 0 THEN oc_number END) AS overdue_orders,
                        SUM(CASE 
                            WHEN days_until_etd < 0 AND customer_type != 'Internal'
                            THEN backlog_by_kpi_center_usd 
                            ELSE 0 
                        END) AS overdue_revenue
                    FROM backlog_by_kpi_center_flat_looker_view
                    WHERE kpi_center_id IN :kpi_center_ids
                      AND (invoice_completion_percent < 100 OR invoice_completion_percent IS NULL)
                      AND etd BETWEEN :start_date AND :end_date
                """
            else:
                period_query = """
                    SELECT 
                        COUNT(DISTINCT CASE WHEN days_until_etd < 0 THEN oc_number END) AS overdue_orders,
                        SUM(CASE WHEN days_until_etd < 0 THEN backlog_by_kpi_center_usd ELSE 0 END) AS overdue_revenue
                    FROM backlog_by_kpi_center_flat_looker_view
                    WHERE kpi_center_id IN :kpi_center_ids
                      AND (invoice_completion_percent < 100 OR invoice_completion_percent IS NULL)
                      AND etd BETWEEN :start_date AND :end_date
                """
            params['start_date'] = start_date
            params['end_date'] = end_date
            
            if entity_ids:
                period_query += " AND entity_id IN :entity_ids"
            
            period_df = self._execute_query(period_query, params, "in_period_overdue")
            if not period_df.empty:
                in_period_overdue = period_df.iloc[0]['overdue_orders'] or 0
                in_period_overdue_revenue = period_df.iloc[0]['overdue_revenue'] or 0
        
        return {
            'overdue_orders': int(row.get('overdue_orders') or 0),
            'overdue_revenue': float(row.get('overdue_revenue') or 0),
            'overdue_gp': float(row.get('overdue_gp') or 0),
            'at_risk_orders': int(row.get('at_risk_orders') or 0),
            'at_risk_revenue': float(row.get('at_risk_revenue') or 0),
            'total_orders': int(row.get('total_orders') or 0),
            'total_backlog': float(row.get('total_backlog') or 0),
            'in_period_overdue': int(in_period_overdue),
            'in_period_overdue_revenue': float(in_period_overdue_revenue),
            'overdue_percent': (float(row.get('overdue_revenue') or 0) / float(row.get('total_backlog') or 1)) * 100
        }
    
    # =========================================================================
    # COMPLEX KPIs - REMOVED in v3.6.0
    # =========================================================================
    # The following methods have been removed and replaced with Pandas-based
    # calculations in complex_kpi_calculator.py:
    # 
    # - get_new_customers()
    # - get_new_customers_detail()
    # - get_new_products()
    # - get_new_products_detail()
    # - get_new_business_revenue()
    # - get_new_business_detail()
    # - get_new_business_by_kpi_center()
    # - get_new_customers_by_kpi_center()
    # - get_new_products_by_kpi_center()
    #
    # Performance improvement: 9 SQL queries (~27s) → 1 Pandas calculation (~0.3s)
    # See: utils/kpi_center_performance/complex_kpi_calculator.py
    # =========================================================================

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
    
    # =========================================================================
    # REMOVED in v3.6.0:
    # - get_entity_list() → extracted from lookback data in main page
    # - get_available_years() → extracted from lookback data in main page
    # - calculate_complex_kpi_value() → replaced by ComplexKPICalculator
    # =========================================================================

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
        
        NEW v3.2.0: Used for parent progress calculation.
        
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