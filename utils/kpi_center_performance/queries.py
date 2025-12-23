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

VERSION: 2.0.0
CHANGELOG:
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
        Get count of NEW CUSTOMERS by KPI Center.
        
        A customer is "new to company" if their first invoice (across ALL KPI Centers)
        within the lookback period falls within the selected date range.
        
        Credit goes to ALL KPI Centers that sold to the customer on their first day.
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
            WITH customer_first_sale AS (
                -- Find each customer's first sale date (company-wide)
                SELECT 
                    customer_id,
                    MIN(inv_date) AS first_sale_date
                FROM unified_sales_by_kpi_center_view
                WHERE inv_date >= :lookback_start
                  AND customer_id IS NOT NULL
                GROUP BY customer_id
            ),
            new_customers_in_period AS (
                -- Customers whose first sale falls within selected period
                SELECT customer_id, first_sale_date
                FROM customer_first_sale
                WHERE first_sale_date BETWEEN :start_date AND :end_date
            ),
            kpi_center_credit AS (
                -- Credit KPI centers that sold to new customers on first day
                SELECT DISTINCT
                    s.kpi_center_id,
                    s.kpi_center,
                    nc.customer_id,
                    s.customer
                FROM unified_sales_by_kpi_center_view s
                INNER JOIN new_customers_in_period nc 
                    ON s.customer_id = nc.customer_id 
                    AND s.inv_date = nc.first_sale_date
                WHERE s.kpi_center_id IN :kpi_center_ids
            )
            SELECT 
                kpi_center_id,
                kpi_center,
                COUNT(DISTINCT customer_id) AS num_new_customers,
                GROUP_CONCAT(DISTINCT customer ORDER BY customer SEPARATOR ', ') AS new_customer_names
            FROM kpi_center_credit
            GROUP BY kpi_center_id, kpi_center
            ORDER BY num_new_customers DESC
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
        
        Returns:
            DataFrame with: customer, customer_id, kpi_center, first_sale_date, 
                           first_sale_revenue, first_sale_gp
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
        Get count of NEW PRODUCTS by KPI Center.
        
        A product is "new" if its first sale ever (to any customer, by any KPI Center)
        within the lookback period falls within the selected date range.
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
            WITH product_first_sale AS (
                SELECT 
                    COALESCE(product_id, pt_code) AS product_key,
                    MIN(inv_date) AS first_sale_date
                FROM unified_sales_by_kpi_center_view
                WHERE inv_date >= :lookback_start
                  AND (product_id IS NOT NULL OR pt_code IS NOT NULL)
                GROUP BY COALESCE(product_id, pt_code)
            ),
            new_products_in_period AS (
                SELECT product_key, first_sale_date
                FROM product_first_sale
                WHERE first_sale_date BETWEEN :start_date AND :end_date
            ),
            kpi_center_credit AS (
                SELECT DISTINCT
                    s.kpi_center_id,
                    s.kpi_center,
                    np.product_key,
                    s.product_pn
                FROM unified_sales_by_kpi_center_view s
                INNER JOIN new_products_in_period np 
                    ON COALESCE(s.product_id, s.pt_code) = np.product_key
                    AND s.inv_date = np.first_sale_date
                WHERE s.kpi_center_id IN :kpi_center_ids
            )
            SELECT 
                kpi_center_id,
                kpi_center,
                COUNT(DISTINCT product_key) AS num_new_products,
                GROUP_CONCAT(DISTINCT product_pn ORDER BY product_pn SEPARATOR ', ') AS new_product_names
            FROM kpi_center_credit
            GROUP BY kpi_center_id, kpi_center
            ORDER BY num_new_products DESC
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
        
        Returns:
            DataFrame with: product_pn, brand, kpi_center, first_sale_date,
                           first_sale_revenue, first_sale_gp, first_customer
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
            WITH product_first_sale AS (
                SELECT 
                    COALESCE(product_id, pt_code) AS product_key,
                    MIN(inv_date) AS first_sale_date
                FROM unified_sales_by_kpi_center_view
                WHERE inv_date >= :lookback_start
                  AND (product_id IS NOT NULL OR pt_code IS NOT NULL)
                GROUP BY COALESCE(product_id, pt_code)
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
                SUM(s.sales_by_kpi_center_usd) AS first_day_revenue,
                SUM(s.gross_profit_by_kpi_center_usd) AS first_day_gp
            FROM unified_sales_by_kpi_center_view s
            INNER JOIN new_products_in_period np 
                ON COALESCE(s.product_id, s.pt_code) = np.product_key
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
        
        New business = revenue from customer-product combinations where the first sale
        of that combo (within lookback) falls within the selected period.
        
        Includes ALL revenue from new combos in the period, not just first day.
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
            WITH combo_first_sale AS (
                SELECT 
                    customer_id,
                    COALESCE(product_id, pt_code) AS product_key,
                    kpi_center_id,
                    MIN(inv_date) AS first_sale_date
                FROM unified_sales_by_kpi_center_view
                WHERE inv_date >= :lookback_start
                  AND customer_id IS NOT NULL
                  AND (product_id IS NOT NULL OR pt_code IS NOT NULL)
                GROUP BY customer_id, COALESCE(product_id, pt_code), kpi_center_id
            ),
            new_combos AS (
                SELECT customer_id, product_key, kpi_center_id, first_sale_date
                FROM combo_first_sale
                WHERE first_sale_date BETWEEN :start_date AND :end_date
            ),
            new_business_sales AS (
                SELECT 
                    s.kpi_center_id,
                    s.kpi_center,
                    s.customer_id,
                    s.customer,
                    COALESCE(s.product_id, s.pt_code) AS product_key,
                    s.product_pn,
                    s.sales_by_kpi_center_usd,
                    s.gross_profit_by_kpi_center_usd,
                    s.gp1_by_kpi_center_usd
                FROM unified_sales_by_kpi_center_view s
                INNER JOIN new_combos nc 
                    ON s.customer_id = nc.customer_id
                    AND COALESCE(s.product_id, s.pt_code) = nc.product_key
                    AND s.kpi_center_id = nc.kpi_center_id
                WHERE s.inv_date BETWEEN :start_date AND :end_date
                  AND s.kpi_center_id IN :kpi_center_ids
            )
            SELECT 
                kpi_center_id,
                kpi_center,
                COUNT(DISTINCT CONCAT(customer_id, '-', product_key)) AS num_new_combos,
                SUM(sales_by_kpi_center_usd) AS new_business_revenue,
                SUM(gross_profit_by_kpi_center_usd) AS new_business_gp,
                SUM(gp1_by_kpi_center_usd) AS new_business_gp1
            FROM new_business_sales
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
        
        Returns:
            DataFrame with: customer, product_pn, brand, kpi_center,
                           first_sale_date, period_revenue, period_gp
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
            WITH combo_first_sale AS (
                SELECT 
                    customer_id,
                    COALESCE(product_id, pt_code) AS product_key,
                    kpi_center_id,
                    MIN(inv_date) AS first_sale_date
                FROM unified_sales_by_kpi_center_view
                WHERE inv_date >= :lookback_start
                  AND customer_id IS NOT NULL
                  AND (product_id IS NOT NULL OR pt_code IS NOT NULL)
                GROUP BY customer_id, COALESCE(product_id, pt_code), kpi_center_id
            ),
            new_combos AS (
                SELECT customer_id, product_key, kpi_center_id, first_sale_date
                FROM combo_first_sale
                WHERE first_sale_date BETWEEN :start_date AND :end_date
            )
            SELECT 
                s.customer,
                s.customer_id,
                s.product_pn,
                s.pt_code,
                s.brand,
                s.kpi_center,
                s.kpi_center_id,
                nc.first_sale_date,
                SUM(s.sales_by_kpi_center_usd) AS period_revenue,
                SUM(s.gross_profit_by_kpi_center_usd) AS period_gp,
                SUM(s.gp1_by_kpi_center_usd) AS period_gp1,
                COUNT(DISTINCT s.inv_number) AS invoice_count
            FROM unified_sales_by_kpi_center_view s
            INNER JOIN new_combos nc 
                ON s.customer_id = nc.customer_id
                AND COALESCE(s.product_id, s.pt_code) = nc.product_key
                AND s.kpi_center_id = nc.kpi_center_id
            WHERE s.inv_date BETWEEN :start_date AND :end_date
              AND s.kpi_center_id IN :kpi_center_ids
            GROUP BY s.customer, s.customer_id, s.product_pn, s.pt_code, s.brand,
                     s.kpi_center, s.kpi_center_id, nc.first_sale_date
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