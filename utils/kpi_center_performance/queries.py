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

VERSION: 2.6.0
CHANGELOG:
- v2.6.0: REFACTORED Complex KPIs to match Salesperson page logic:
          - SYNCED product_key: COALESCE(CAST(product_id AS CHAR), legacy_code)
          - FIXED New Business combo scope: Global (not per KPI Center)
          - ADDED weighted counting: Returns split_rate_percent for fractional credit
          - ADDED deduplication: GROUP BY (kpi_center, entity) before counting
          - ADDED customer_code to new_customers_detail for display
          - UPDATED calculate_complex_kpi_value() to use weighted counting
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
    # =========================================================================
    
    def get_new_customers(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None,
        include_children: bool = True
    ) -> pd.DataFrame:
        """
        Get NEW CUSTOMERS by KPI Center with weighted counting support.
        
        REFACTORED v2.6.0 to match Salesperson page logic:
        - A customer is "new to COMPANY" if their first invoice (globally, ANY KPI Center)
          within the 5-year lookback falls within the selected period
        - Credit goes to KPI Centers that made first-day sales
        - Returns individual records with split_rate_percent for weighted counting
        - Deduplicates per (customer_id, kpi_center_id) combo
        
        Returns:
            DataFrame with: customer_id, customer_code, customer, kpi_center_id, 
                           kpi_center, split_rate_percent, first_invoice_date
                           
        Usage for weighted count:
            df = queries.get_new_customers(start_date, end_date)
            weighted_count = df['split_rate_percent'].sum() / 100
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
        
        query = """
            WITH first_customer_date AS (
                -- Step 1: Find first invoice date for each customer (GLOBALLY - any KPI Center)
                SELECT 
                    customer_id,
                    MIN(inv_date) AS first_invoice_date
                FROM unified_sales_by_kpi_center_view
                WHERE inv_date >= :lookback_start
                  AND customer_id IS NOT NULL
                GROUP BY customer_id
            ),
            first_day_records AS (
                -- Step 2: Get all records from first invoice date
                SELECT 
                    u.customer_id,
                    u.customer_code,
                    u.customer,
                    u.kpi_center_id,
                    u.kpi_center,
                    u.split_rate_percent,
                    fcd.first_invoice_date
                FROM first_customer_date fcd
                JOIN unified_sales_by_kpi_center_view u 
                    ON fcd.customer_id = u.customer_id 
                    AND u.inv_date = fcd.first_invoice_date
            ),
            deduplicated AS (
                -- Step 3: Deduplicate per (customer_id, kpi_center_id) combo
                -- Each combo counted once, use MAX to get non-null values
                SELECT 
                    customer_id,
                    MAX(customer_code) AS customer_code,
                    MAX(customer) AS customer,
                    kpi_center_id,
                    MAX(kpi_center) AS kpi_center,
                    MAX(split_rate_percent) AS split_rate_percent,
                    first_invoice_date
                FROM first_day_records
                GROUP BY customer_id, kpi_center_id, first_invoice_date
            )
            -- Step 4: Filter by period and selected KPI Centers
            SELECT 
                customer_id,
                customer_code,
                customer,
                kpi_center_id,
                kpi_center,
                split_rate_percent,
                first_invoice_date
            FROM deduplicated
            WHERE first_invoice_date BETWEEN :start_date AND :end_date
              AND kpi_center_id IN :kpi_center_ids
            ORDER BY first_invoice_date DESC
        """
        
        params = {
            'lookback_start': lookback_start,
            'start_date': start_date,
            'end_date': end_date,
            'kpi_center_ids': tuple(kpi_center_ids)
        }
        
        return self._execute_query(query, params, "new_customers")
    
    def get_new_customers_detail(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None
    ) -> pd.DataFrame:
        """
        Get detailed list of NEW CUSTOMERS with first sale info.
        Used for popup drill-down.
        
        UPDATED v2.6.0: Added split_rate_percent for display.
        
        Returns:
            DataFrame with: customer, customer_code, customer_id, kpi_center, 
                           first_sale_date, split_rate_percent,
                           first_day_revenue, first_day_gp, first_day_gp1
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
        
        query = """
            WITH customer_first_sale AS (
                SELECT 
                    customer_id,
                    MIN(inv_date) AS first_sale_date
                FROM unified_sales_by_kpi_center_view
                WHERE inv_date >= :lookback_start
                  AND customer_id IS NOT NULL
                GROUP BY customer_id
            ),
            new_customers_in_period AS (
                SELECT customer_id, first_sale_date
                FROM customer_first_sale
                WHERE first_sale_date BETWEEN :start_date AND :end_date
            )
            SELECT 
                s.customer,
                s.customer_id,
                s.customer_code,
                s.kpi_center,
                s.kpi_center_id,
                nc.first_sale_date,
                MAX(s.split_rate_percent) AS split_rate_percent,
                SUM(s.sales_by_kpi_center_usd) AS first_day_revenue,
                SUM(s.gross_profit_by_kpi_center_usd) AS first_day_gp,
                SUM(s.gp1_by_kpi_center_usd) AS first_day_gp1
            FROM unified_sales_by_kpi_center_view s
            INNER JOIN new_customers_in_period nc 
                ON s.customer_id = nc.customer_id 
                AND s.inv_date = nc.first_sale_date
            WHERE s.kpi_center_id IN :kpi_center_ids
            GROUP BY s.customer, s.customer_id, s.customer_code, 
                     s.kpi_center, s.kpi_center_id, nc.first_sale_date
            ORDER BY first_day_revenue DESC
        """
        
        params = {
            'lookback_start': lookback_start,
            'start_date': start_date,
            'end_date': end_date,
            'kpi_center_ids': tuple(kpi_center_ids)
        }
        
        return self._execute_query(query, params, "new_customers_detail")
    
    def get_new_products(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None,
        include_children: bool = True
    ) -> pd.DataFrame:
        """
        Get NEW PRODUCTS by KPI Center with weighted counting support.
        
        REFACTORED v2.6.0 to match Salesperson page logic:
        - A product is "new" if its first sale ever (to ANY customer, by ANY KPI Center)
          within the 5-year lookback falls within the selected period
        - SYNCED product_key: COALESCE(CAST(product_id AS CHAR), legacy_code)
        - Credit goes to KPI Centers that made first-day sales
        - Returns individual records with split_rate_percent for weighted counting
        - Deduplicates per (product_key, kpi_center_id) combo
        
        Returns:
            DataFrame with: product_id, product_pn, pt_code, legacy_code, brand,
                           kpi_center_id, kpi_center, split_rate_percent, first_sale_date
                           
        Usage for weighted count:
            df = queries.get_new_products(start_date, end_date)
            weighted_count = df['split_rate_percent'].sum() / 100
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
        
        # SYNCED v2.6.0: Use same product_key logic as Salesperson
        query = """
            WITH 
            -- ================================================================
            -- Step 1: Create unified product key and find first sale date
            -- SYNCED: Priority product_id > legacy_code (same as Salesperson)
            -- ================================================================
            first_sale_by_product AS (
                SELECT 
                    COALESCE(CAST(product_id AS CHAR), legacy_code) AS product_key,
                    MIN(inv_date) AS first_sale_date
                FROM unified_sales_by_kpi_center_view
                WHERE inv_date >= :lookback_start
                  AND (product_id IS NOT NULL OR legacy_code IS NOT NULL)
                GROUP BY COALESCE(CAST(product_id AS CHAR), legacy_code)
            ),
            
            -- ================================================================
            -- Step 2: Filter to products with first sale in selected period
            -- ================================================================
            new_products AS (
                SELECT product_key, first_sale_date
                FROM first_sale_by_product
                WHERE first_sale_date BETWEEN :start_date AND :end_date
            ),
            
            -- ================================================================
            -- Step 3: Get all sales records from first sale date
            -- ================================================================
            first_day_records AS (
                SELECT 
                    u.product_id,
                    u.product_pn,
                    u.pt_code,
                    u.legacy_code,
                    u.brand,
                    u.kpi_center_id,
                    u.kpi_center,
                    u.split_rate_percent,
                    np.first_sale_date
                FROM new_products np
                JOIN unified_sales_by_kpi_center_view u 
                    ON COALESCE(CAST(u.product_id AS CHAR), u.legacy_code) = np.product_key
                    AND u.inv_date = np.first_sale_date
            ),
            
            -- ================================================================
            -- Step 4: Deduplicate per (product_key, kpi_center_id) combo
            -- ================================================================
            deduplicated AS (
                SELECT 
                    MAX(product_id) AS product_id,
                    MAX(product_pn) AS product_pn,
                    MAX(pt_code) AS pt_code,
                    MAX(legacy_code) AS legacy_code,
                    MAX(brand) AS brand,
                    kpi_center_id,
                    MAX(kpi_center) AS kpi_center,
                    MAX(split_rate_percent) AS split_rate_percent,
                    first_sale_date,
                    COALESCE(CAST(MAX(product_id) AS CHAR), MAX(legacy_code)) AS product_key
                FROM first_day_records
                GROUP BY 
                    COALESCE(CAST(product_id AS CHAR), legacy_code),
                    kpi_center_id, 
                    first_sale_date
            )
            
            -- ================================================================
            -- Step 5: Return results filtered by accessible KPI Centers
            -- ================================================================
            SELECT 
                product_id,
                product_pn,
                pt_code,
                legacy_code,
                brand,
                kpi_center_id,
                kpi_center,
                split_rate_percent,
                first_sale_date
            FROM deduplicated
            WHERE kpi_center_id IN :kpi_center_ids
            ORDER BY first_sale_date DESC
        """
        
        params = {
            'lookback_start': lookback_start,
            'start_date': start_date,
            'end_date': end_date,
            'kpi_center_ids': tuple(kpi_center_ids)
        }
        
        return self._execute_query(query, params, "new_products")
    
    def get_new_products_detail(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None
    ) -> pd.DataFrame:
        """
        Get detailed list of NEW PRODUCTS with first sale info.
        Used for popup drill-down.
        
        UPDATED v2.6.0: 
        - SYNCED product_key: COALESCE(CAST(product_id AS CHAR), legacy_code)
        - Added split_rate_percent for display
        
        Returns:
            DataFrame with: product_pn, pt_code, brand, kpi_center, first_sale_date,
                           first_customers, split_rate_percent, first_day_revenue, first_day_gp
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
        
        # SYNCED v2.6.0: Use same product_key logic as Salesperson
        query = """
            WITH product_first_sale AS (
                SELECT 
                    COALESCE(CAST(product_id AS CHAR), legacy_code) AS product_key,
                    MIN(inv_date) AS first_sale_date
                FROM unified_sales_by_kpi_center_view
                WHERE inv_date >= :lookback_start
                  AND (product_id IS NOT NULL OR legacy_code IS NOT NULL)
                GROUP BY COALESCE(CAST(product_id AS CHAR), legacy_code)
            ),
            new_products_in_period AS (
                SELECT product_key, first_sale_date
                FROM product_first_sale
                WHERE first_sale_date BETWEEN :start_date AND :end_date
            )
            SELECT 
                s.product_pn,
                s.pt_code,
                s.brand,
                s.kpi_center,
                s.kpi_center_id,
                np.first_sale_date,
                GROUP_CONCAT(DISTINCT s.customer SEPARATOR ', ') AS first_customers,
                MAX(s.split_rate_percent) AS split_rate_percent,
                SUM(s.sales_by_kpi_center_usd) AS first_day_revenue,
                SUM(s.gross_profit_by_kpi_center_usd) AS first_day_gp
            FROM unified_sales_by_kpi_center_view s
            INNER JOIN new_products_in_period np 
                ON COALESCE(CAST(s.product_id AS CHAR), s.legacy_code) = np.product_key
                AND s.inv_date = np.first_sale_date
            WHERE s.kpi_center_id IN :kpi_center_ids
            GROUP BY s.product_pn, s.pt_code, s.brand, 
                     s.kpi_center, s.kpi_center_id, np.first_sale_date
            ORDER BY first_day_revenue DESC
        """
        
        params = {
            'lookback_start': lookback_start,
            'start_date': start_date,
            'end_date': end_date,
            'kpi_center_ids': tuple(kpi_center_ids)
        }
        
        return self._execute_query(query, params, "new_products_detail")
    
    def get_new_business_revenue(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None,
        include_children: bool = True
    ) -> pd.DataFrame:
        """
        Get NEW BUSINESS REVENUE by KPI Center.
        
        REFACTORED v2.6.0 to match Salesperson page logic:
        - CRITICAL FIX: Combo is now (customer_id, product_key) - GLOBAL, not per KPI Center
        - New business = revenue from customer-product combinations where the first sale
          of that combo (GLOBALLY - any KPI Center) falls within the selected period
        - SYNCED product_key: COALESCE(CAST(product_id AS CHAR), legacy_code)
        - Includes ALL revenue from new combos in the period, not just first day
        
        Returns:
            DataFrame with: kpi_center_id, kpi_center, num_new_combos, 
                           new_business_revenue, new_business_gp, new_business_gp1
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
        
        # REFACTORED v2.6.0: Combo is GLOBAL (not per KPI Center)
        query = """
            WITH 
            -- ================================================================
            -- Step 1: Find first sale date for each customer-product combo GLOBALLY
            -- CRITICAL: Do NOT include kpi_center_id in GROUP BY
            -- SYNCED: product_key uses same logic as Salesperson
            -- ================================================================
            first_combo_date AS (
                SELECT 
                    customer_id,
                    COALESCE(CAST(product_id AS CHAR), legacy_code) AS product_key,
                    MIN(inv_date) AS first_combo_date
                FROM unified_sales_by_kpi_center_view
                WHERE inv_date >= :lookback_start
                  AND customer_id IS NOT NULL
                  AND (product_id IS NOT NULL OR legacy_code IS NOT NULL)
                GROUP BY customer_id, COALESCE(CAST(product_id AS CHAR), legacy_code)
            ),
            
            -- ================================================================
            -- Step 2: Identify combos that are "new" (first sale within period)
            -- ================================================================
            new_combos AS (
                SELECT customer_id, product_key, first_combo_date
                FROM first_combo_date
                WHERE first_combo_date BETWEEN :start_date AND :end_date
            ),
            
            -- ================================================================
            -- Step 3: Get ALL revenue from new combos within period
            -- (not just first day - includes repeat orders of new combos)
            -- ================================================================
            all_revenue_in_period AS (
                SELECT 
                    u.kpi_center_id,
                    u.kpi_center,
                    u.customer_id,
                    COALESCE(CAST(u.product_id AS CHAR), u.legacy_code) AS product_key,
                    u.sales_by_kpi_center_usd,
                    u.gross_profit_by_kpi_center_usd,
                    u.gp1_by_kpi_center_usd
                FROM new_combos nc
                JOIN unified_sales_by_kpi_center_view u 
                    ON nc.customer_id = u.customer_id 
                    AND COALESCE(CAST(u.product_id AS CHAR), u.legacy_code) = nc.product_key
                WHERE u.inv_date BETWEEN :start_date AND :end_date
                  AND u.kpi_center_id IN :kpi_center_ids
            )
            
            -- ================================================================
            -- Step 4: Aggregate by KPI Center
            -- ================================================================
            SELECT 
                kpi_center_id,
                kpi_center,
                COUNT(DISTINCT CONCAT(customer_id, '-', product_key)) AS num_new_combos,
                SUM(sales_by_kpi_center_usd) AS new_business_revenue,
                SUM(gross_profit_by_kpi_center_usd) AS new_business_gp,
                SUM(gp1_by_kpi_center_usd) AS new_business_gp1
            FROM all_revenue_in_period
            GROUP BY kpi_center_id, kpi_center
            ORDER BY new_business_revenue DESC
        """
        
        params = {
            'lookback_start': lookback_start,
            'start_date': start_date,
            'end_date': end_date,
            'kpi_center_ids': tuple(kpi_center_ids)
        }
        
        return self._execute_query(query, params, "new_business_revenue")
    
    def get_new_business_detail(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None
    ) -> pd.DataFrame:
        """
        Get detailed NEW BUSINESS combos with revenue breakdown.
        Used for popup drill-down.
        
        REFACTORED v2.6.0: 
        - CRITICAL FIX: Combo is GLOBAL (not per KPI Center)
        - SYNCED product_key: COALESCE(CAST(product_id AS CHAR), legacy_code)
        - Added customer_code and split_rate_percent for display
        
        Returns:
            DataFrame with: customer, customer_code, product_pn, pt_code, brand,
                           kpi_center, first_sale_date, split_rate_percent,
                           period_revenue, period_gp, period_gp1, invoice_count
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
        
        # REFACTORED v2.6.0: Combo is GLOBAL
        query = """
            WITH 
            -- ================================================================
            -- Step 1: Find first sale date for each customer-product combo GLOBALLY
            -- ================================================================
            first_combo_date AS (
                SELECT 
                    customer_id,
                    COALESCE(CAST(product_id AS CHAR), legacy_code) AS product_key,
                    MIN(inv_date) AS first_combo_date
                FROM unified_sales_by_kpi_center_view
                WHERE inv_date >= :lookback_start
                  AND customer_id IS NOT NULL
                  AND (product_id IS NOT NULL OR legacy_code IS NOT NULL)
                GROUP BY customer_id, COALESCE(CAST(product_id AS CHAR), legacy_code)
            ),
            
            -- ================================================================
            -- Step 2: Identify combos that are "new"
            -- ================================================================
            new_combos AS (
                SELECT customer_id, product_key, first_combo_date
                FROM first_combo_date
                WHERE first_combo_date BETWEEN :start_date AND :end_date
            ),
            
            -- ================================================================
            -- Step 3: Get detailed revenue data for new combos
            -- Aggregate by combo + kpi_center
            -- ================================================================
            combo_detail AS (
                SELECT 
                    u.customer_id,
                    MAX(u.customer_code) AS customer_code,
                    u.customer,
                    MAX(u.product_id) AS product_id,
                    MAX(u.product_pn) AS product_pn,
                    MAX(u.pt_code) AS pt_code,
                    MAX(u.brand) AS brand,
                    u.kpi_center_id,
                    MAX(u.kpi_center) AS kpi_center,
                    MAX(u.split_rate_percent) AS split_rate_percent,
                    nc.first_combo_date,
                    SUM(u.sales_by_kpi_center_usd) AS period_revenue,
                    SUM(u.gross_profit_by_kpi_center_usd) AS period_gp,
                    SUM(u.gp1_by_kpi_center_usd) AS period_gp1,
                    COUNT(DISTINCT u.inv_number) AS invoice_count
                FROM new_combos nc
                JOIN unified_sales_by_kpi_center_view u 
                    ON nc.customer_id = u.customer_id 
                    AND COALESCE(CAST(u.product_id AS CHAR), u.legacy_code) = nc.product_key
                WHERE u.inv_date BETWEEN :start_date AND :end_date
                  AND u.kpi_center_id IN :kpi_center_ids
                GROUP BY 
                    u.customer_id, 
                    u.customer,
                    COALESCE(CAST(u.product_id AS CHAR), u.legacy_code),
                    u.kpi_center_id,
                    nc.first_combo_date
            )
            
            SELECT 
                customer,
                customer_code,
                product_pn,
                pt_code,
                brand,
                kpi_center,
                split_rate_percent,
                first_combo_date AS first_sale_date,
                period_revenue,
                period_gp,
                period_gp1,
                invoice_count
            FROM combo_detail
            ORDER BY period_revenue DESC
        """
        
        params = {
            'lookback_start': lookback_start,
            'start_date': start_date,
            'end_date': end_date,
            'kpi_center_ids': tuple(kpi_center_ids)
        }
        
        return self._execute_query(query, params, "new_business_detail")
    
    # =========================================================================
    # LOOKUP DATA
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
    # COMPLEX KPI VALUE CALCULATOR - UPDATED v2.6.0
    # =========================================================================
    
    def calculate_complex_kpi_value(
        self,
        kpi_type: str,
        start_date: date,
        end_date: date,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None
    ) -> Dict:
        """
        Calculate a single complex KPI value for specific KPI Centers.
        
        UPDATED v2.6.0: Now uses weighted counting (split_rate_percent / 100).
        
        Args:
            kpi_type: One of 'new_customers', 'new_products', 'new_business'
            start_date: Period start date
            end_date: Period end date
            kpi_center_ids: Optional list of KPI Center IDs to filter
            entity_ids: Optional list of entity IDs to filter
            
        Returns:
            Dict with:
                - value: The calculated KPI value (weighted count or revenue)
                - count: Number of records
                - detail_available: Whether detail data exists
        """
        if not self.access.can_access_page():
            return {'value': 0, 'count': 0, 'detail_available': False}
        
        if kpi_center_ids:
            kpi_center_ids = self.access.validate_selected_kpi_centers(kpi_center_ids)
        else:
            kpi_center_ids = self.access.get_accessible_kpi_center_ids()
        
        if not kpi_center_ids:
            return {'value': 0, 'count': 0, 'detail_available': False}
        
        try:
            if kpi_type == 'new_customers':
                df = self.get_new_customers(
                    start_date=start_date,
                    end_date=end_date,
                    kpi_center_ids=kpi_center_ids,
                    entity_ids=entity_ids
                )
                if df.empty:
                    return {'value': 0, 'count': 0, 'detail_available': False}
                
                # UPDATED v2.6.0: Weighted count = sum(split_rate_percent) / 100
                weighted_count = df['split_rate_percent'].fillna(100).sum() / 100
                return {
                    'value': weighted_count,
                    'count': len(df),
                    'detail_available': True
                }
            
            elif kpi_type == 'new_products':
                df = self.get_new_products(
                    start_date=start_date,
                    end_date=end_date,
                    kpi_center_ids=kpi_center_ids,
                    entity_ids=entity_ids
                )
                if df.empty:
                    return {'value': 0, 'count': 0, 'detail_available': False}
                
                # UPDATED v2.6.0: Weighted count = sum(split_rate_percent) / 100
                weighted_count = df['split_rate_percent'].fillna(100).sum() / 100
                return {
                    'value': weighted_count,
                    'count': len(df),
                    'detail_available': True
                }
            
            elif kpi_type == 'new_business':
                df = self.get_new_business_revenue(
                    start_date=start_date,
                    end_date=end_date,
                    kpi_center_ids=kpi_center_ids,
                    entity_ids=entity_ids
                )
                if df.empty:
                    return {'value': 0, 'count': 0, 'detail_available': False}
                
                total_revenue = df['new_business_revenue'].sum()
                total_combos = int(df['num_new_combos'].sum())
                return {
                    'value': total_revenue,
                    'count': total_combos,
                    'detail_available': True,
                    'by_kpi_center': df[['kpi_center_id', 'kpi_center', 'num_new_combos', 'new_business_revenue']].to_dict('records')
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


# =============================================================================
# CACHED QUERY FUNCTIONS (Module-level for st.cache_data)
# =============================================================================

@st.cache_data(ttl=CACHE_TTL_SECONDS)
def _get_sales_data_cached(
    start_date: date,
    end_date: date,
    kpi_center_ids: tuple,
    entity_ids: tuple = None
) -> pd.DataFrame:
    """
    Cached version of sales data query.
    """
    engine = get_db_engine()
    
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
        'kpi_center_ids': kpi_center_ids
    }
    
    if entity_ids:
        query += " AND legal_entity_id IN :entity_ids"
        params['entity_ids'] = entity_ids
    
    query += " ORDER BY inv_date DESC"
    
    try:
        return pd.read_sql(text(query), engine, params=params)
    except Exception as e:
        logger.error(f"Error in cached sales query: {e}")
        return pd.DataFrame()