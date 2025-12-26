# utils/kpi_center_performance/queries.py
"""
SQL Queries and Data Loading for KPI Center Performance

Handles all database interactions:
- Sales data from unified_sales_by_kpi_center_view
- KPI targets from sales_kpi_center_assignments_view
- Backlog from backlog_by_kpi_center_flat_looker_view
- KPI Center split configuration
- Complex KPIs (new customers, products, business revenue)
- Parent-Child rollup for KPI Center hierarchy

VERSION: 2.9.0
CHANGELOG:
- v2.9.0: FIXED Complex KPIs not filtering by entity_ids:
          - get_new_customers(): Added entity_ids filter to SQL query
          - get_new_customers_detail(): Added entity_ids filter to SQL query
          - get_new_products(): Added entity_ids filter to SQL query
          - get_new_products_detail(): Added entity_ids filter to SQL query
          - get_new_business_revenue(): Added entity_ids filter to SQL query
          - get_new_business_detail(): Added entity_ids filter to SQL query
          - Now Complex KPIs properly reflect Legal Entity filter changes
- v2.7.0: FIXED Double Counting & New Business Revenue calculation:
          - Issue #1: Added `selected_kpi_types` parameter to detect single vs multiple types
            * Single type selected → Full credit for that type
            * Multiple types selected → Deduplicate per entity to avoid double counting
          - Issue #2: Changed MAX() to SUM() in get_new_business_revenue()
            * Now correctly sums all revenue from new combos within period
            * Fixed get_new_business_detail() similarly
- v2.6.1: REFACTORED Complex KPIs with GLOBAL scope (Option B):
          - New Customer: customer_id only, global across all KPI Centers
          - New Product: product_id only, global across all KPI Centers
          - New Business: (customer_id, product_id) combo, global scope
          - Returns individual records with split_rate_percent for weighted counting
          - Weighted count formula: sum(split_rate_percent) / 100
          - Matches Salesperson page logic exactly
- v2.2.0: Added helper methods for Phase 2:
          - calculate_complex_kpi_value(): Single complex KPI calculator
          - get_kpi_center_achievement_summary(): Achievement comparison data
- v2.0.0: Added detail queries for complex KPIs (popup support)
          - get_new_customers_detail()
          - get_new_products_detail()
          - get_new_business_detail()
          Added backlog risk analysis query
          - get_backlog_risk_analysis()
"""

import logging
from datetime import date, datetime
from typing import List, Optional, Tuple, Dict
import pandas as pd
import streamlit as st
from sqlalchemy import text

from utils.db import get_db_engine
from .constants import LOOKBACK_YEARS, CACHE_TTL_SECONDS
from .access_control import AccessControl

logger = logging.getLogger(__name__)


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
    # KPI CENTER HIERARCHY
    # =========================================================================
    
    def get_kpi_center_hierarchy(self) -> pd.DataFrame:
        """
        Get KPI Center hierarchy with parent-child relationships.
        
        Returns:
            DataFrame with columns: kpi_center_id, kpi_center_name, kpi_type, 
                                   parent_center_id, level
        """
        query = """
            WITH RECURSIVE kpi_hierarchy AS (
                -- Base case: root KPI centers (no parent)
                SELECT 
                    id AS kpi_center_id,
                    name AS kpi_center_name,
                    type AS kpi_type,
                    parent_center_id,
                    0 AS level
                FROM kpi_centers
                WHERE parent_center_id IS NULL
                  AND delete_flag = 0
                
                UNION ALL
                
                -- Recursive case: child KPI centers
                SELECT 
                    kc.id,
                    kc.name,
                    kc.type,
                    kc.parent_center_id,
                    kh.level + 1
                FROM kpi_centers kc
                INNER JOIN kpi_hierarchy kh ON kc.parent_center_id = kh.kpi_center_id
                WHERE kc.delete_flag = 0
            )
            SELECT * FROM kpi_hierarchy
            ORDER BY level, kpi_center_name
        """
        
        return self._execute_query(query, {}, "kpi_center_hierarchy")
    
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
    # BACKLOG DATA
    # =========================================================================
    
    def get_backlog_data(
        self,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None,
        include_children: bool = True
    ) -> pd.DataFrame:
        """
        Get backlog summary by KPI Center.
        Only includes uninvoiced orders (invoice_completion_percent < 100).
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
        include_children: bool = True
    ) -> pd.DataFrame:
        """
        Get backlog with ETD within specified period.
        Only includes uninvoiced orders.
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
        include_children: bool = True
    ) -> pd.DataFrame:
        """
        Get backlog grouped by ETD month/year.
        Only includes uninvoiced orders.
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
    # BACKLOG RISK ANALYSIS (NEW v2.0.0)
    # =========================================================================
    
    def get_backlog_risk_analysis(
        self,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None,
        start_date: date = None,
        end_date: date = None
    ) -> Dict:
        """
        Analyze backlog for overdue and risk factors.
        
        Returns:
            Dictionary with:
            - overdue_orders: Orders with ETD in the past
            - overdue_revenue: Total revenue at risk
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
    # COMPLEX KPIs (New Customers, Products, Business Revenue)
    # REFACTORED v2.6.1: Use GLOBAL scope for all metrics
    # - New Customer: customer_id only (global, not per KPI Center)
    # - New Product: product_id only (global, not per KPI Center)  
    # - New Business: customer_id + product_id combo (global)
    # =========================================================================
    
    def get_new_customers(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None,
        include_children: bool = True,
        selected_kpi_types: List[str] = None
    ) -> pd.DataFrame:
        """
        Get NEW CUSTOMERS with GLOBAL scope.
        
        A customer is "new to COMPANY" if their first invoice (across ALL KPI Centers)
        within the 5-year lookback falls within the selected date range.
        
        Returns individual records with split_rate_percent for weighted counting.
        Weighted count = sum(split_rate_percent) / 100
        
        UPDATED v2.7.0:
        - Added `selected_kpi_types` parameter for double-counting prevention
        - Single type selected → Returns per (customer_id, kpi_center_id) for full credit
        - Multiple types selected → Deduplicates per customer_id to avoid double counting
        
        Args:
            start_date: Period start date
            end_date: Period end date
            kpi_center_ids: List of KPI Center IDs to filter
            entity_ids: List of entity IDs to filter (not used currently)
            include_children: Include child KPI Centers
            selected_kpi_types: List of selected KPI types (e.g., ['Territory', 'Vertical'])
                               If None or single type → no deduplication across types
                               If multiple types → deduplicate per customer_id
        
        Returns:
            DataFrame with: customer_id, customer_code, customer, kpi_center_id, 
                           kpi_center, split_rate_percent, first_sale_date
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
        
        lookback_start = date(end_date.year - LOOKBACK_YEARS, 1, 1)
        
        # Determine if we need to deduplicate across types
        # Multiple types selected → dedupe per customer_id to avoid double counting
        dedupe_across_types = selected_kpi_types and len(selected_kpi_types) > 1
        
        # Build filter conditions - FIXED v2.9.0
        entity_filter = "AND s.legal_entity_id IN :entity_ids" if entity_ids else ""
        # CRITICAL FIX v2.9.0: Filter by kpi_type!
        kpi_type_filter = "AND s.kpi_type IN :kpi_types" if selected_kpi_types else ""
        
        if dedupe_across_types:
            # MULTIPLE TYPES: Deduplicate per customer_id (count each customer only once)
            query = f"""
                WITH 
                -- ================================================================
                -- Step 1: Find first invoice date for each customer (GLOBALLY)
                -- ================================================================
                customer_first_sale AS (
                    SELECT 
                        customer_id,
                        MIN(inv_date) AS first_sale_date
                    FROM unified_sales_by_kpi_center_view
                    WHERE inv_date >= :lookback_start
                      AND customer_id IS NOT NULL
                    GROUP BY customer_id
                ),
                
                -- ================================================================
                -- Step 2: Filter to customers with first sale in selected period
                -- ================================================================
                new_customers AS (
                    SELECT customer_id, first_sale_date
                    FROM customer_first_sale
                    WHERE first_sale_date BETWEEN :start_date AND :end_date
                ),
                
                -- ================================================================
                -- Step 3: Get all records from first sale date
                -- FIXED v2.9.0: Added entity_ids AND kpi_type filters
                -- ================================================================
                first_day_records AS (
                    SELECT 
                        s.customer_id,
                        s.customer_code,
                        s.customer,
                        s.kpi_center_id,
                        s.kpi_center,
                        s.kpi_type,
                        s.split_rate_percent,
                        nc.first_sale_date
                    FROM new_customers nc
                    JOIN unified_sales_by_kpi_center_view s
                        ON nc.customer_id = s.customer_id
                        AND s.inv_date = nc.first_sale_date
                    WHERE s.kpi_center_id IN :kpi_center_ids
                    {kpi_type_filter}
                    {entity_filter}
                ),
                
                -- ================================================================
                -- Step 4: DEDUPLICATE per customer_id (NOT per kpi_center_id)
                -- When multiple types selected, count each customer only ONCE
                -- Concatenate KPI Centers for display
                -- ================================================================
                deduplicated AS (
                    SELECT 
                        customer_id,
                        MAX(customer_code) AS customer_code,
                        MAX(customer) AS customer,
                        -- Use MIN kpi_center_id for consistency (or could use any)
                        MIN(kpi_center_id) AS kpi_center_id,
                        GROUP_CONCAT(DISTINCT kpi_center ORDER BY kpi_center SEPARATOR ', ') AS kpi_center,
                        -- For weighted count: use 100% since we're counting once per customer
                        100.0 AS split_rate_percent,
                        first_sale_date
                    FROM first_day_records
                    GROUP BY customer_id, first_sale_date
                )
                
                SELECT 
                    customer_id,
                    customer_code,
                    customer,
                    kpi_center_id,
                    kpi_center,
                    split_rate_percent,
                    first_sale_date
                FROM deduplicated
                ORDER BY first_sale_date DESC, customer
            """
        else:
            # SINGLE TYPE: Keep per (customer_id, kpi_center_id) for full credit
            # NOTE: entity_filter and kpi_type_filter already built above
            
            query = f"""
                WITH 
                -- ================================================================
                -- Step 1: Find first invoice date for each customer (GLOBALLY)
                -- No kpi_center_id in GROUP BY = company-wide first sale
                -- ================================================================
                customer_first_sale AS (
                    SELECT 
                        customer_id,
                        MIN(inv_date) AS first_sale_date
                    FROM unified_sales_by_kpi_center_view
                    WHERE inv_date >= :lookback_start
                      AND customer_id IS NOT NULL
                    GROUP BY customer_id
                ),
                
                -- ================================================================
                -- Step 2: Filter to customers with first sale in selected period
                -- ================================================================
                new_customers AS (
                    SELECT customer_id, first_sale_date
                    FROM customer_first_sale
                    WHERE first_sale_date BETWEEN :start_date AND :end_date
                ),
                
                -- ================================================================
                -- Step 3: Get all records from first sale date
                -- Credit ALL KPI Centers that sold on first day
                -- FIXED v2.9.0: Added entity_ids AND kpi_type filters
                -- ================================================================
                first_day_records AS (
                    SELECT 
                        s.customer_id,
                        s.customer_code,
                        s.customer,
                        s.kpi_center_id,
                        s.kpi_center,
                        s.split_rate_percent,
                        nc.first_sale_date
                    FROM new_customers nc
                    JOIN unified_sales_by_kpi_center_view s
                        ON nc.customer_id = s.customer_id
                        AND s.inv_date = nc.first_sale_date
                    WHERE s.kpi_center_id IN :kpi_center_ids
                    {kpi_type_filter}
                    {entity_filter}
                ),
                
                -- ================================================================
                -- Step 4: Deduplicate per (customer_id, kpi_center_id)
                -- Each combo counted once even if multiple invoice lines
                -- ================================================================
                deduplicated AS (
                    SELECT 
                        customer_id,
                        MAX(customer_code) AS customer_code,
                        MAX(customer) AS customer,
                        kpi_center_id,
                        MAX(kpi_center) AS kpi_center,
                        MAX(split_rate_percent) AS split_rate_percent,
                        first_sale_date
                    FROM first_day_records
                    GROUP BY customer_id, kpi_center_id, first_sale_date
                )
                
                SELECT 
                    customer_id,
                    customer_code,
                    customer,
                    kpi_center_id,
                    kpi_center,
                    split_rate_percent,
                    first_sale_date
                FROM deduplicated
                ORDER BY first_sale_date DESC, customer
            """
        
        params = {
            'lookback_start': lookback_start,
            'start_date': start_date,
            'end_date': end_date,
            'kpi_center_ids': tuple(kpi_center_ids)
        }
        
        # Add kpi_types to params if provided - CRITICAL FIX v2.9.0
        if selected_kpi_types:
            params['kpi_types'] = tuple(selected_kpi_types)
        
        # Add entity_ids to params if provided
        if entity_ids:
            params['entity_ids'] = tuple(entity_ids)
        
        return self._execute_query(query, params, "new_customers")
    
    def get_new_customers_detail(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None,
        selected_kpi_types: List[str] = None
    ) -> pd.DataFrame:
        """
        Get detailed NEW CUSTOMERS with first sale revenue info.
        Used for popup drill-down.
        
        Same as get_new_customers() but includes first day revenue/GP.
        
        Returns:
            DataFrame with: customer_id, customer_code, customer, kpi_center_id,
                           kpi_center, split_rate_percent, first_sale_date,
                           first_day_revenue, first_day_gp
        """
        if not self.access.can_access_page():
            return pd.DataFrame()
        
        if kpi_center_ids:
            kpi_center_ids = self.access.validate_selected_kpi_centers(kpi_center_ids)
        else:
            kpi_center_ids = self.access.get_accessible_kpi_center_ids()
        
        if not kpi_center_ids:
            return pd.DataFrame()
        
        lookback_start = date(end_date.year - LOOKBACK_YEARS, 1, 1)
        
        # Build filter conditions - FIXED v2.9.0
        entity_filter = "AND s.legal_entity_id IN :entity_ids" if entity_ids else ""
        # CRITICAL FIX v2.9.0: Filter by kpi_type!
        kpi_type_filter = "AND s.kpi_type IN :kpi_types" if selected_kpi_types else ""
        
        query = f"""
            WITH 
            -- Step 1: Find first invoice date for each customer (GLOBALLY)
            customer_first_sale AS (
                SELECT 
                    customer_id,
                    MIN(inv_date) AS first_sale_date
                FROM unified_sales_by_kpi_center_view
                WHERE inv_date >= :lookback_start
                  AND customer_id IS NOT NULL
                GROUP BY customer_id
            ),
            
            -- Step 2: Filter to customers with first sale in selected period
            new_customers AS (
                SELECT customer_id, first_sale_date
                FROM customer_first_sale
                WHERE first_sale_date BETWEEN :start_date AND :end_date
            ),
            
            -- Step 3: Aggregate first day sales per (customer, kpi_center)
            -- FIXED v2.9.0: Added entity_ids AND kpi_type filters
            first_day_sales AS (
                SELECT 
                    s.customer_id,
                    MAX(s.customer_code) AS customer_code,
                    MAX(s.customer) AS customer,
                    s.kpi_center_id,
                    MAX(s.kpi_center) AS kpi_center,
                    MAX(s.split_rate_percent) AS split_rate_percent,
                    nc.first_sale_date,
                    SUM(s.sales_by_kpi_center_usd) AS first_day_revenue,
                    SUM(s.gross_profit_by_kpi_center_usd) AS first_day_gp
                FROM new_customers nc
                JOIN unified_sales_by_kpi_center_view s
                    ON nc.customer_id = s.customer_id
                    AND s.inv_date = nc.first_sale_date
                WHERE s.kpi_center_id IN :kpi_center_ids
                {kpi_type_filter}
                {entity_filter}
                GROUP BY s.customer_id, s.kpi_center_id, nc.first_sale_date
            )
            
            SELECT 
                customer_id,
                customer_code,
                customer,
                kpi_center_id,
                kpi_center,
                split_rate_percent,
                first_sale_date,
                first_day_revenue,
                first_day_gp
            FROM first_day_sales
            ORDER BY first_sale_date DESC, customer
        """
        
        params = {
            'lookback_start': lookback_start,
            'start_date': start_date,
            'end_date': end_date,
            'kpi_center_ids': tuple(kpi_center_ids)
        }
        
        # Add kpi_types to params if provided - CRITICAL FIX v2.9.0
        if selected_kpi_types:
            params['kpi_types'] = tuple(selected_kpi_types)
        
        # Add entity_ids to params if provided
        if entity_ids:
            params['entity_ids'] = tuple(entity_ids)
        
        return self._execute_query(query, params, "new_customers_detail")
    
    # =========================================================================
    # COMPLEX KPIs - NEW PRODUCTS (REFACTORED v2.6.1)
    # =========================================================================
    
    def get_new_products(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None,
        include_children: bool = True,
        selected_kpi_types: List[str] = None
    ) -> pd.DataFrame:
        """
        Get NEW PRODUCTS with GLOBAL scope.
        
        A product is "new" if its first sale (to ANY customer, by ANY KPI Center)
        within the 5-year lookback falls within the selected date range.
        
        Uses only product_id as identifier (no fallback to legacy_code/pt_code).
        
        UPDATED v2.7.0:
        - Added `selected_kpi_types` parameter for double-counting prevention
        - Single type selected → Returns per (product_id, kpi_center_id) for full credit
        - Multiple types selected → Deduplicates per product_id to avoid double counting
        
        Args:
            start_date: Period start date
            end_date: Period end date
            kpi_center_ids: List of KPI Center IDs to filter
            entity_ids: List of entity IDs to filter (not used currently)
            include_children: Include child KPI Centers
            selected_kpi_types: List of selected KPI types (e.g., ['Territory', 'Vertical'])
                               If None or single type → no deduplication across types
                               If multiple types → deduplicate per product_id
        
        Returns:
            DataFrame with: product_id, product_pn, pt_code, brand, kpi_center_id,
                           kpi_center, split_rate_percent, first_sale_date
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
        
        lookback_start = date(end_date.year - LOOKBACK_YEARS, 1, 1)
        
        # Determine if we need to deduplicate across types
        dedupe_across_types = selected_kpi_types and len(selected_kpi_types) > 1
        
        # Build filter conditions - FIXED v2.9.0
        entity_filter = "AND s.legal_entity_id IN :entity_ids" if entity_ids else ""
        # CRITICAL FIX v2.9.0: Filter by kpi_type!
        kpi_type_filter = "AND s.kpi_type IN :kpi_types" if selected_kpi_types else ""
        
        if dedupe_across_types:
            # MULTIPLE TYPES: Deduplicate per product_id (count each product only once)
            query = f"""
                WITH 
                -- ================================================================
                -- Step 1: Find first sale date for each product (GLOBALLY)
                -- ================================================================
                product_first_sale AS (
                    SELECT 
                        product_id,
                        MIN(inv_date) AS first_sale_date
                    FROM unified_sales_by_kpi_center_view
                    WHERE inv_date >= :lookback_start
                      AND product_id IS NOT NULL
                    GROUP BY product_id
                ),
                
                -- ================================================================
                -- Step 2: Filter to products with first sale in selected period
                -- ================================================================
                new_products AS (
                    SELECT product_id, first_sale_date
                    FROM product_first_sale
                    WHERE first_sale_date BETWEEN :start_date AND :end_date
                ),
                
                -- ================================================================
                -- Step 3: Get all records from first sale date
                -- FIXED v2.9.0: Added entity_ids AND kpi_type filters
                -- ================================================================
                first_day_records AS (
                    SELECT 
                        s.product_id,
                        s.product_pn,
                        s.pt_code,
                        s.brand,
                        s.kpi_center_id,
                        s.kpi_center,
                        s.kpi_type,
                        s.split_rate_percent,
                        np.first_sale_date
                    FROM new_products np
                    JOIN unified_sales_by_kpi_center_view s
                        ON np.product_id = s.product_id
                        AND s.inv_date = np.first_sale_date
                    WHERE s.kpi_center_id IN :kpi_center_ids
                      AND s.product_id IS NOT NULL
                      {kpi_type_filter}
                      {entity_filter}
                ),
                
                -- ================================================================
                -- Step 4: DEDUPLICATE per product_id (NOT per kpi_center_id)
                -- When multiple types selected, count each product only ONCE
                -- ================================================================
                deduplicated AS (
                    SELECT 
                        product_id,
                        MAX(product_pn) AS product_pn,
                        MAX(pt_code) AS pt_code,
                        MAX(brand) AS brand,
                        MIN(kpi_center_id) AS kpi_center_id,
                        GROUP_CONCAT(DISTINCT kpi_center ORDER BY kpi_center SEPARATOR ', ') AS kpi_center,
                        -- For weighted count: use 100% since we're counting once per product
                        100.0 AS split_rate_percent,
                        first_sale_date
                    FROM first_day_records
                    GROUP BY product_id, first_sale_date
                )
                
                SELECT 
                    product_id,
                    product_pn,
                    pt_code,
                    brand,
                    kpi_center_id,
                    kpi_center,
                    split_rate_percent,
                    first_sale_date
                FROM deduplicated
                ORDER BY first_sale_date DESC, product_pn
            """
        else:
            # SINGLE TYPE: Keep per (product_id, kpi_center_id) for full credit
            query = f"""
                WITH 
                -- ================================================================
                -- Step 1: Find first sale date for each product (GLOBALLY)
                -- Uses product_id only - no fallback to legacy_code/pt_code
                -- ================================================================
                product_first_sale AS (
                    SELECT 
                        product_id,
                        MIN(inv_date) AS first_sale_date
                    FROM unified_sales_by_kpi_center_view
                    WHERE inv_date >= :lookback_start
                      AND product_id IS NOT NULL
                    GROUP BY product_id
                ),
                
                -- ================================================================
                -- Step 2: Filter to products with first sale in selected period
                -- ================================================================
                new_products AS (
                    SELECT product_id, first_sale_date
                    FROM product_first_sale
                    WHERE first_sale_date BETWEEN :start_date AND :end_date
                ),
                
                -- ================================================================
                -- Step 3: Get all records from first sale date
                -- Credit ALL KPI Centers that sold on first day
                -- FIXED v2.9.0: Added entity_ids AND kpi_type filters
                -- ================================================================
                first_day_records AS (
                    SELECT 
                        s.product_id,
                        s.product_pn,
                        s.pt_code,
                        s.brand,
                        s.kpi_center_id,
                        s.kpi_center,
                        s.split_rate_percent,
                        np.first_sale_date
                    FROM new_products np
                    JOIN unified_sales_by_kpi_center_view s
                        ON np.product_id = s.product_id
                        AND s.inv_date = np.first_sale_date
                    WHERE s.kpi_center_id IN :kpi_center_ids
                      AND s.product_id IS NOT NULL
                      {kpi_type_filter}
                      {entity_filter}
                ),
                
                -- ================================================================
                -- Step 4: Deduplicate per (product_id, kpi_center_id)
                -- ================================================================
                deduplicated AS (
                    SELECT 
                        product_id,
                        MAX(product_pn) AS product_pn,
                        MAX(pt_code) AS pt_code,
                        MAX(brand) AS brand,
                        kpi_center_id,
                        MAX(kpi_center) AS kpi_center,
                        MAX(split_rate_percent) AS split_rate_percent,
                        first_sale_date
                    FROM first_day_records
                    GROUP BY product_id, kpi_center_id, first_sale_date
                )
                
                SELECT 
                    product_id,
                    product_pn,
                    pt_code,
                    brand,
                    kpi_center_id,
                    kpi_center,
                    split_rate_percent,
                    first_sale_date
                FROM deduplicated
                ORDER BY first_sale_date DESC, product_pn
            """
        
        params = {
            'lookback_start': lookback_start,
            'start_date': start_date,
            'end_date': end_date,
            'kpi_center_ids': tuple(kpi_center_ids)
        }
        
        # Add kpi_types to params if provided - CRITICAL FIX v2.9.0
        if selected_kpi_types:
            params['kpi_types'] = tuple(selected_kpi_types)
        
        # Add entity_ids to params if provided
        if entity_ids:
            params['entity_ids'] = tuple(entity_ids)
        
        return self._execute_query(query, params, "new_products")
    
    def get_new_products_detail(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None,
        selected_kpi_types: List[str] = None
    ) -> pd.DataFrame:
        """
        Get detailed NEW PRODUCTS with first sale revenue info.
        Used for popup drill-down.
        
        Returns:
            DataFrame with: product_id, product_pn, pt_code, brand, kpi_center_id,
                           kpi_center, split_rate_percent, first_sale_date,
                           first_day_revenue, first_day_gp
        """
        if not self.access.can_access_page():
            return pd.DataFrame()
        
        if kpi_center_ids:
            kpi_center_ids = self.access.validate_selected_kpi_centers(kpi_center_ids)
        else:
            kpi_center_ids = self.access.get_accessible_kpi_center_ids()
        
        if not kpi_center_ids:
            return pd.DataFrame()
        
        lookback_start = date(end_date.year - LOOKBACK_YEARS, 1, 1)
        
        # Build filter conditions - FIXED v2.9.0
        entity_filter = "AND s.legal_entity_id IN :entity_ids" if entity_ids else ""
        # CRITICAL FIX v2.9.0: Filter by kpi_type!
        kpi_type_filter = "AND s.kpi_type IN :kpi_types" if selected_kpi_types else ""
        
        query = f"""
            WITH 
            -- Step 1: Find first sale date for each product (GLOBALLY)
            product_first_sale AS (
                SELECT 
                    product_id,
                    MIN(inv_date) AS first_sale_date
                FROM unified_sales_by_kpi_center_view
                WHERE inv_date >= :lookback_start
                  AND product_id IS NOT NULL
                GROUP BY product_id
            ),
            
            -- Step 2: Filter to products with first sale in selected period
            new_products AS (
                SELECT product_id, first_sale_date
                FROM product_first_sale
                WHERE first_sale_date BETWEEN :start_date AND :end_date
            ),
            
            -- Step 3: Aggregate first day sales per (product, kpi_center)
            -- FIXED v2.9.0: Added entity_ids AND kpi_type filters
            first_day_sales AS (
                SELECT 
                    s.product_id,
                    MAX(s.product_pn) AS product_pn,
                    MAX(s.pt_code) AS pt_code,
                    MAX(s.brand) AS brand,
                    s.kpi_center_id,
                    MAX(s.kpi_center) AS kpi_center,
                    MAX(s.split_rate_percent) AS split_rate_percent,
                    np.first_sale_date,
                    SUM(s.sales_by_kpi_center_usd) AS first_day_revenue,
                    SUM(s.gross_profit_by_kpi_center_usd) AS first_day_gp
                FROM new_products np
                JOIN unified_sales_by_kpi_center_view s
                    ON np.product_id = s.product_id
                    AND s.inv_date = np.first_sale_date
                WHERE s.kpi_center_id IN :kpi_center_ids
                  AND s.product_id IS NOT NULL
                  {kpi_type_filter}
                  {entity_filter}
                GROUP BY s.product_id, s.kpi_center_id, np.first_sale_date
            )
            
            SELECT 
                product_id,
                product_pn,
                pt_code,
                brand,
                kpi_center_id,
                kpi_center,
                split_rate_percent,
                first_sale_date,
                first_day_revenue,
                first_day_gp
            FROM first_day_sales
            ORDER BY first_sale_date DESC, product_pn
        """
        
        params = {
            'lookback_start': lookback_start,
            'start_date': start_date,
            'end_date': end_date,
            'kpi_center_ids': tuple(kpi_center_ids)
        }
        
        # Add kpi_types to params if provided - CRITICAL FIX v2.9.0
        if selected_kpi_types:
            params['kpi_types'] = tuple(selected_kpi_types)
        
        # Add entity_ids to params if provided
        if entity_ids:
            params['entity_ids'] = tuple(entity_ids)
        
        return self._execute_query(query, params, "new_products_detail")
    
    # =========================================================================
    # COMPLEX KPIs - NEW BUSINESS REVENUE (REFACTORED v2.6.1)
    # =========================================================================
    
    def get_new_business_revenue(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None,
        selected_kpi_types: List[str] = None
    ) -> pd.DataFrame:
        """
        Get new business revenue - first-time customer-product combinations.
        
        FIXED v2.7.0:
        - Changed MAX() to SUM() to correctly aggregate all revenue from new combos
        - Added `selected_kpi_types` for consistency (though New Business Revenue
          already deduplicates per combo by design)
        
        Returns:
            DataFrame with: num_new_combos, new_business_revenue, new_business_gp, new_business_gp1
        """
        if not self.access.can_access_page():
            return pd.DataFrame()
        
        if kpi_center_ids:
            kpi_center_ids = self.access.validate_selected_kpi_centers(kpi_center_ids)
        else:
            kpi_center_ids = self.access.get_accessible_kpi_center_ids()
        
        if not kpi_center_ids:
            return pd.DataFrame()
        
        lookback_start = date(end_date.year - LOOKBACK_YEARS, 1, 1)
        
        # Build filter conditions - FIXED v2.9.0
        entity_filter = "AND s.legal_entity_id IN :entity_ids" if entity_ids else ""
        # CRITICAL FIX v2.9.0: Filter by kpi_type!
        kpi_type_filter = "AND s.kpi_type IN :kpi_types" if selected_kpi_types else ""
        
        query = f"""
            WITH 
            -- ================================================================
            -- Step 1: Find first sale date for each (customer, product) combo
            -- GLOBAL scope: No kpi_center_id in GROUP BY
            -- ================================================================
            combo_first_sale AS (
                SELECT 
                    customer_id,
                    product_id,
                    MIN(inv_date) AS first_combo_date
                FROM unified_sales_by_kpi_center_view
                WHERE inv_date >= :lookback_start
                AND customer_id IS NOT NULL
                AND product_id IS NOT NULL
                GROUP BY customer_id, product_id
            ),
            
            -- ================================================================
            -- Step 2: Identify combos that are "new" (first sale within period)
            -- ================================================================
            new_combos AS (
                SELECT customer_id, product_id, first_combo_date
                FROM combo_first_sale
                WHERE first_combo_date BETWEEN :start_date AND :end_date
            ),
            
            -- ================================================================
            -- Step 3: Get ALL revenue from new combos within period
            -- (not just first day - includes repeat orders of new combos)
            -- FIXED v2.9.0: Added entity_ids AND kpi_type filters
            -- ================================================================
            new_business_sales AS (
                SELECT 
                    s.kpi_center_id,
                    s.kpi_center,
                    s.customer_id,
                    s.product_id,
                    s.sales_by_kpi_center_usd,
                    s.gross_profit_by_kpi_center_usd,
                    s.gp1_by_kpi_center_usd
                FROM new_combos nc
                JOIN unified_sales_by_kpi_center_view s
                    ON nc.customer_id = s.customer_id
                    AND nc.product_id = s.product_id
                WHERE s.inv_date BETWEEN :start_date AND :end_date
                AND s.kpi_center_id IN :kpi_center_ids
                AND s.product_id IS NOT NULL
                {kpi_type_filter}
                {entity_filter}
            ),
            
            -- ================================================================
            -- Step 4: FIXED - Deduplicate per combo & SUM revenue
            -- When same combo sold by multiple KPI Centers (Territory + Vertical),
            -- count only ONCE but SUM all revenue within the combo
            -- ================================================================
            combo_deduplicated AS (
                SELECT 
                    customer_id,
                    product_id,
                    SUM(sales_by_kpi_center_usd) AS combo_revenue,
                    SUM(gross_profit_by_kpi_center_usd) AS combo_gp,
                    SUM(gp1_by_kpi_center_usd) AS combo_gp1
                FROM new_business_sales
                GROUP BY customer_id, product_id
            )
            
            -- ================================================================
            -- Final: Aggregate totals (single row result)
            -- ================================================================
            SELECT 
                COUNT(*) AS num_new_combos,
                SUM(combo_revenue) AS new_business_revenue,
                SUM(combo_gp) AS new_business_gp,
                SUM(combo_gp1) AS new_business_gp1
            FROM combo_deduplicated
        """
        
        params = {
            'lookback_start': lookback_start,
            'start_date': start_date,
            'end_date': end_date,
            'kpi_center_ids': tuple(kpi_center_ids)
        }
        
        # Add kpi_types to params if provided - CRITICAL FIX v2.9.0
        if selected_kpi_types:
            params['kpi_types'] = tuple(selected_kpi_types)
        
        # Add entity_ids to params if provided
        if entity_ids:
            params['entity_ids'] = tuple(entity_ids)
        
        return self._execute_query(query, params, "new_business_revenue")


    def get_new_business_detail(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None,
        selected_kpi_types: List[str] = None
    ) -> pd.DataFrame:
        """
        Get detailed NEW BUSINESS combos with revenue breakdown.
        Used for popup drill-down.
        
        FIXED v2.7.0:
        - Changed MAX() to SUM() for revenue aggregation
        - GROUP_CONCAT KPI Centers for display (shows all assigned KPI Centers)
        
        Returns:
            DataFrame with: customer_id, customer_code, customer, product_id, product_pn,
                        pt_code, brand, kpi_center (comma-separated list), split_rate_percent,
                        first_sale_date, new_business_revenue, new_business_gp
        """
        if not self.access.can_access_page():
            return pd.DataFrame()
        
        if kpi_center_ids:
            kpi_center_ids = self.access.validate_selected_kpi_centers(kpi_center_ids)
        else:
            kpi_center_ids = self.access.get_accessible_kpi_center_ids()
        
        if not kpi_center_ids:
            return pd.DataFrame()
        
        lookback_start = date(end_date.year - LOOKBACK_YEARS, 1, 1)
        
        # Build filter conditions - FIXED v2.9.0
        entity_filter = "AND s.legal_entity_id IN :entity_ids" if entity_ids else ""
        # CRITICAL FIX v2.9.0: Filter by kpi_type!
        kpi_type_filter = "AND s.kpi_type IN :kpi_types" if selected_kpi_types else ""
        
        query = f"""
            WITH 
            -- Step 1: Find first sale date for each (customer, product) combo (GLOBAL)
            combo_first_sale AS (
                SELECT 
                    customer_id,
                    product_id,
                    MIN(inv_date) AS first_combo_date
                FROM unified_sales_by_kpi_center_view
                WHERE inv_date >= :lookback_start
                AND customer_id IS NOT NULL
                AND product_id IS NOT NULL
                GROUP BY customer_id, product_id
            ),
            
            -- Step 2: Identify combos that are "new" (first sale within period)
            new_combos AS (
                SELECT customer_id, product_id, first_combo_date
                FROM combo_first_sale
                WHERE first_combo_date BETWEEN :start_date AND :end_date
            ),
            
            -- Step 3: Get all sales records for new combos
            -- FIXED v2.9.0: Added entity_ids AND kpi_type filters
            new_business_sales AS (
                SELECT 
                    s.customer_id,
                    s.customer_code,
                    s.customer,
                    s.product_id,
                    s.product_pn,
                    s.pt_code,
                    s.brand,
                    s.kpi_center_id,
                    s.kpi_center,
                    s.split_rate_percent,
                    nc.first_combo_date AS first_sale_date,
                    s.sales_by_kpi_center_usd,
                    s.gross_profit_by_kpi_center_usd
                FROM new_combos nc
                JOIN unified_sales_by_kpi_center_view s
                    ON nc.customer_id = s.customer_id
                    AND nc.product_id = s.product_id
                WHERE s.inv_date BETWEEN :start_date AND :end_date
                AND s.kpi_center_id IN :kpi_center_ids
                AND s.product_id IS NOT NULL
                {kpi_type_filter}
                {entity_filter}
            )
            
            -- ================================================================
            -- FIXED: Deduplicate per combo, GROUP_CONCAT KPI Centers, SUM revenue
            -- ================================================================
            SELECT 
                customer_id,
                MAX(customer_code) AS customer_code,
                MAX(customer) AS customer,
                product_id,
                MAX(product_pn) AS product_pn,
                MAX(pt_code) AS pt_code,
                MAX(brand) AS brand,
                -- Show all assigned KPI Centers as comma-separated list
                GROUP_CONCAT(DISTINCT kpi_center ORDER BY kpi_center SEPARATOR ', ') AS kpi_center,
                MAX(split_rate_percent) AS split_rate_percent,
                MAX(first_sale_date) AS first_sale_date,
                -- FIXED: SUM all revenue within the combo (not MAX)
                SUM(sales_by_kpi_center_usd) AS new_business_revenue,
                SUM(gross_profit_by_kpi_center_usd) AS new_business_gp
            FROM new_business_sales
            GROUP BY customer_id, product_id
            ORDER BY new_business_revenue DESC
        """
        
        params = {
            'lookback_start': lookback_start,
            'start_date': start_date,
            'end_date': end_date,
            'kpi_center_ids': tuple(kpi_center_ids)
        }
        
        # Add kpi_types to params if provided - CRITICAL FIX v2.9.0
        if selected_kpi_types:
            params['kpi_types'] = tuple(selected_kpi_types)
        
        # Add entity_ids to params if provided
        if entity_ids:
            params['entity_ids'] = tuple(entity_ids)
        
        return self._execute_query(query, params, "new_business_detail")


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
    
    def get_entity_list(self) -> pd.DataFrame:
        """Get list of legal entities for filter dropdown."""
        query = """
            SELECT DISTINCT
                legal_entity_id AS entity_id,
                legal_entity AS entity_name
            FROM unified_sales_by_kpi_center_view
            WHERE legal_entity_id IS NOT NULL
            ORDER BY legal_entity
        """
        
        return self._execute_query(query, {}, "entity_list")
    
    def get_available_years(self) -> List[int]:
        """Get list of years with sales data."""
        query = """
            SELECT DISTINCT invoice_year
            FROM unified_sales_by_kpi_center_view
            WHERE invoice_year IS NOT NULL
            ORDER BY invoice_year DESC
        """
        
        df = self._execute_query(query, {}, "available_years")
        if df.empty:
            return [datetime.now().year]
        
        return df['invoice_year'].tolist()
    
    def get_kpi_split_data(
        self,
        kpi_center_ids: List[int] = None
    ) -> pd.DataFrame:
        """
        Get KPI Center split assignments.
        
        Returns DataFrame with split assignments including customer, product, percentage.
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
            SELECT 
                kpi_center_id,
                kpi_center_name,
                kpi_type,
                customer_name,
                customer_id,
                product_pn,
                product_id,
                pt_code,
                brand,
                split_percentage,
                effective_period,
                approval_status,
                total_split_percentage_by_type,
                kpi_split_status
            FROM kpi_center_split_looker_view
            WHERE kpi_center_id IN :kpi_center_ids
              AND approval_status = 'approved'
            ORDER BY kpi_center_name, customer_name
        """
        
        params = {'kpi_center_ids': tuple(kpi_center_ids)}
        
        return self._execute_query(query, params, "kpi_split_data")
    
    # =========================================================================
    # COMPLEX KPI VALUE CALCULATOR (UPDATED v2.6.1)
    # =========================================================================
    
    def calculate_complex_kpi_value(
        self,
        kpi_type: str,
        start_date: date,
        end_date: date,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None,
        selected_kpi_types: List[str] = None
    ) -> dict:
        """
        Calculate value for a complex KPI type.
        
        UPDATED v2.7.0: Added selected_kpi_types parameter for double-counting prevention.
        - Single type selected → Full credit for that type
        - Multiple types selected → Deduplicate per entity to avoid double counting
        
        Args:
            kpi_type: 'new_customers', 'new_products', or 'new_business'
            start_date: Period start
            end_date: Period end
            kpi_center_ids: Optional list of KPI Center IDs
            entity_ids: Optional list of entity IDs (for filtering)
            selected_kpi_types: List of selected KPI types (e.g., ['Territory', 'Vertical'])
            
        Returns:
            dict with: value, count, detail_available, by_kpi_center
        """
        try:
            if kpi_type == 'new_customers':
                df = self.get_new_customers(
                    start_date=start_date,
                    end_date=end_date,
                    kpi_center_ids=kpi_center_ids,
                    entity_ids=entity_ids,
                    selected_kpi_types=selected_kpi_types
                )
                if df.empty:
                    return {'value': 0, 'count': 0, 'detail_available': False}
                
                # Weighted counting: sum(split_rate_percent) / 100
                weighted_count = df['split_rate_percent'].fillna(100).sum() / 100
                
                # Aggregate by KPI Center for detail
                by_kpi_center = df.groupby(['kpi_center_id', 'kpi_center']).agg({
                    'split_rate_percent': lambda x: x.fillna(100).sum() / 100
                }).reset_index()
                by_kpi_center.columns = ['kpi_center_id', 'kpi_center', 'num_new_customers']
                
                return {
                    'value': weighted_count,
                    'count': weighted_count,
                    'detail_available': True,
                    'by_kpi_center': by_kpi_center.to_dict('records')
                }
            
            elif kpi_type == 'new_products':
                df = self.get_new_products(
                    start_date=start_date,
                    end_date=end_date,
                    kpi_center_ids=kpi_center_ids,
                    entity_ids=entity_ids,
                    selected_kpi_types=selected_kpi_types
                )
                if df.empty:
                    return {'value': 0, 'count': 0, 'detail_available': False}
                
                # Weighted counting: sum(split_rate_percent) / 100
                weighted_count = df['split_rate_percent'].fillna(100).sum() / 100
                
                # Aggregate by KPI Center for detail
                by_kpi_center = df.groupby(['kpi_center_id', 'kpi_center']).agg({
                    'split_rate_percent': lambda x: x.fillna(100).sum() / 100
                }).reset_index()
                by_kpi_center.columns = ['kpi_center_id', 'kpi_center', 'num_new_products']
                
                return {
                    'value': weighted_count,
                    'count': weighted_count,
                    'detail_available': True,
                    'by_kpi_center': by_kpi_center.to_dict('records')
                }
            
            elif kpi_type == 'new_business':
                df = self.get_new_business_revenue(
                    start_date=start_date,
                    end_date=end_date,
                    kpi_center_ids=kpi_center_ids,
                    entity_ids=entity_ids,
                    selected_kpi_types=selected_kpi_types
                )
                if df.empty:
                    return {'value': 0, 'count': 0, 'detail_available': False}
                
                total_revenue = df['new_business_revenue'].sum()
                total_combos = int(df['num_new_combos'].sum())
                return {
                    'value': total_revenue,
                    'count': total_combos,
                    'detail_available': True,
                    'by_kpi_center': df[['kpi_center_id', 'kpi_center', 'num_new_combos', 'new_business_revenue']].to_dict('records') if 'kpi_center_id' in df.columns else []
                }
            
            else:
                logger.warning(f"Unknown KPI type: {kpi_type}")
                return {'value': 0, 'count': 0, 'detail_available': False}
        
        except Exception as e:
            logger.error(f"Error calculating complex KPI {kpi_type}: {e}")
            return {'value': 0, 'count': 0, 'detail_available': False}
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
        """
        try:
            logger.debug(f"Executing {query_name}")
            df = pd.read_sql(text(query), self.engine, params=params)
            logger.debug(f"{query_name} returned {len(df)} rows")
            return df
        except Exception as e:
            logger.error(f"Error executing {query_name}: {e}")
            return pd.DataFrame()