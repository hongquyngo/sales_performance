# utils/salesperson_performance/queries.py
"""
SQL Queries and Data Loading for Salesperson Performance

Handles all database interactions:
- Sales data from unified_sales_by_salesperson_view
- KPI targets from sales_employee_kpi_assignments_view
- Complex KPIs (new customers, products, business revenue)
- Lookup data (salespeople list, entities, years)

All queries respect access control filtering.
Uses @st.cache_data for performance.

CHANGELOG:
- v1.5.0: FIXED backlog queries to filter uninvoiced only
          - Added condition: invoice_completion_percent < 100 OR IS NULL
          - Affects: get_backlog_data, get_backlog_in_period, 
                     get_backlog_by_month, get_backlog_detail
          - Backlog now correctly represents UNINVOICED value only
- v1.4.0: REFACTORED get_new_products() to use legacy_code from unified view
          - No longer needs JOIN with products table
          - Uses COALESCE(product_id, legacy_code) as unified product key
          - Correctly identifies products sold in history (via legacy_code) 
            that appear in realtime (via product_id)
          - Handles edge cases: NULL product_id in history, NULL legacy_code in old realtime
- v1.3.0: Fixed duplicate counting bug - unified view has multiple rows per invoice (1 per product)
          Added GROUP BY deduplication: each customer/product + salesperson combo counted once
          NEW BUSINESS REVENUE: Now includes ALL revenue from new combos in period (not just first day)
          A combo is "new" if first sale (in 5yr lookback) falls within selected period
- v1.2.0: Fixed lookback calculation - now uses end_date.year instead of start_date.year
          Fixed RANK() instead of ROW_NUMBER() to credit all salespeople who made
          first sale on same day (split credit scenario)
- v1.1.0: Fixed num_new_customers logic - now "new to company" instead of "new to salesperson"
          Changed PARTITION BY customer_id, sales_id -> PARTITION BY customer_id
"""

import logging
from datetime import date, datetime
from typing import List, Optional, Tuple
import pandas as pd
import streamlit as st
from sqlalchemy import text

from utils.db import get_db_engine
from .constants import LOOKBACK_YEARS, CACHE_TTL_SECONDS
from .access_control import AccessControl

logger = logging.getLogger(__name__)


class SalespersonQueries:
    """
    Data loading class for salesperson performance.
    
    Usage:
        access = AccessControl(user_role, employee_id)
        queries = SalespersonQueries(access)
        
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
    # CORE SALES DATA
    # =========================================================================
    
    def get_sales_data(
        self,
        start_date: date,
        end_date: date,
        employee_ids: List[int] = None,
        entity_ids: List[int] = None
    ) -> pd.DataFrame:
        """
        Load sales data from unified_sales_by_salesperson_view.
        
        Args:
            start_date: Start date for filtering
            end_date: End date for filtering
            employee_ids: Optional list of specific employee IDs (will be validated)
            entity_ids: Optional list of legal entity IDs
            
        Returns:
            DataFrame with sales data
        """
        # Validate employee_ids against access control
        if employee_ids:
            employee_ids = self.access.validate_selected_employees(employee_ids)
        else:
            employee_ids = self.access.get_accessible_employee_ids()
        
        if not employee_ids:
            logger.warning("No accessible employee IDs, returning empty DataFrame")
            return pd.DataFrame()
        
        # Build query
        query = """
            SELECT 
                data_source,
                unified_line_id,
                sales_id,
                sales_name,
                sales_email,
                employment_status,
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
                sales_by_split_usd,
                gross_profit_by_split_usd,
                gp1_by_split_usd,
                allocated_broker_commission_usd,
                invoice_month,
                invoice_year
            FROM unified_sales_by_salesperson_view
            WHERE inv_date BETWEEN :start_date AND :end_date
              AND sales_id IN :employee_ids
        """
        
        params = {
            'start_date': start_date,
            'end_date': end_date,
            'employee_ids': tuple(employee_ids)
        }
        
        # Add entity filter if provided
        if entity_ids:
            query += " AND legal_entity_id IN :entity_ids"
            params['entity_ids'] = tuple(entity_ids)
        
        query += " ORDER BY inv_date DESC"
        
        return self._execute_query(query, params, "sales_data")
    
    def get_sales_data_cached(
        self,
        start_date: date,
        end_date: date,
        employee_ids_tuple: tuple = None,
        entity_ids_tuple: tuple = None
    ) -> pd.DataFrame:
        """
        Cached version of get_sales_data.
        Use tuples instead of lists for cache key compatibility.
        """
        return _get_sales_data_cached(
            start_date, 
            end_date,
            employee_ids_tuple or tuple(self.access.get_accessible_employee_ids()),
            entity_ids_tuple
        )
    
    # =========================================================================
    # KPI TARGETS
    # =========================================================================
    
    def get_kpi_targets(
        self,
        year: int,
        employee_ids: List[int] = None
    ) -> pd.DataFrame:
        """
        Load KPI targets from sales_employee_kpi_assignments_view.
        
        Args:
            year: Year to get targets for
            employee_ids: Optional list of employee IDs
            
        Returns:
            DataFrame with KPI targets
        """
        if employee_ids:
            employee_ids = self.access.validate_selected_employees(employee_ids)
        else:
            employee_ids = self.access.get_accessible_employee_ids()
        
        if not employee_ids:
            return pd.DataFrame()
        
        query = """
            SELECT 
                employee_id,
                employee_name,
                email,
                status,
                year,
                kpi_type_id,
                kpi_name,
                annual_target_value,
                annual_target_value_numeric,
                unit_of_measure,
                weight_numeric,
                monthly_target_value,
                quarterly_target_value,
                is_current_year
            FROM sales_employee_kpi_assignments_view
            WHERE year = :year
              AND employee_id IN :employee_ids
        """
        
        params = {
            'year': year,
            'employee_ids': tuple(employee_ids)
        }
        
        return self._execute_query(query, params, "kpi_targets")
    
    # =========================================================================
    # COMPLEX KPIs - NEW CUSTOMERS
    # =========================================================================
    
    def get_new_customers(
        self,
        start_date: date,
        end_date: date,
        employee_ids: List[int] = None
    ) -> pd.DataFrame:
        """
        Get customers with first invoice to COMPANY in period (vs 5-year lookback).
        
        A customer is "new to company" if:
        - The first invoice for this customer (globally, any salesperson)
        - Falls within the specified date range
        - When looking back LOOKBACK_YEARS years
        
        Credit is given to the salesperson who made the first sale.
        
        Returns DataFrame with: customer_id, customer, sales_id, sales_name,
                               split_rate_percent, first_invoice_date
        
        UPDATED v1.1.0: Changed from "new to salesperson" to "new to company"
        - Old: PARTITION BY customer_id, sales_id (customer is new if first sale BY THIS SALESPERSON)
        - New: PARTITION BY customer_id (customer is new if first sale EVER TO COMPANY)
        """
        if employee_ids:
            employee_ids = self.access.validate_selected_employees(employee_ids)
        else:
            employee_ids = self.access.get_accessible_employee_ids()
        
        if not employee_ids:
            return pd.DataFrame()
        
        # Lookback: 5 years from start of end_date's year
        lookback_start = date(end_date.year - LOOKBACK_YEARS, 1, 1)
        
        # FIXED v1.1.0: PARTITION BY customer_id (new to company, not new to salesperson)
        # FIXED v1.2.0: RANK() instead of ROW_NUMBER() to credit all salespeople 
        #               who made first sale on same day
        # FIXED v1.3.0: Added deduplication - each customer+salesperson combo counted once
        query = """
            WITH first_customer_date AS (
                -- Step 1: Find first invoice date for each customer (globally)
                SELECT 
                    customer_id,
                    MIN(inv_date) as first_invoice_date
                FROM unified_sales_by_salesperson_view
                WHERE inv_date >= :lookback_start
                GROUP BY customer_id
            ),
            first_day_records AS (
                -- Step 2: Get all records from first invoice date
                SELECT 
                    u.customer_id,
                    u.customer,
                    u.sales_id,
                    u.sales_name,
                    u.split_rate_percent,
                    fcd.first_invoice_date
                FROM first_customer_date fcd
                JOIN unified_sales_by_salesperson_view u 
                    ON fcd.customer_id = u.customer_id 
                    AND u.inv_date = fcd.first_invoice_date
            ),
            deduplicated AS (
                -- Step 3: Deduplicate per customer + salesperson (count each combo once)
                SELECT 
                    customer_id,
                    MAX(customer) as customer,
                    sales_id,
                    MAX(sales_name) as sales_name,
                    MAX(split_rate_percent) as split_rate_percent,
                    first_invoice_date
                FROM first_day_records
                GROUP BY customer_id, sales_id, first_invoice_date
            )
            SELECT 
                customer_id,
                customer,
                sales_id,
                sales_name,
                split_rate_percent,
                first_invoice_date
            FROM deduplicated
            WHERE first_invoice_date BETWEEN :start_date AND :end_date
              AND sales_id IN :employee_ids
            ORDER BY first_invoice_date DESC
        """
        
        params = {
            'lookback_start': lookback_start,
            'start_date': start_date,
            'end_date': end_date,
            'employee_ids': tuple(employee_ids)
        }
        
        return self._execute_query(query, params, "new_customers")
    
    # =========================================================================
    # COMPLEX KPIs - NEW PRODUCTS (REFACTORED v1.4.0)
    # =========================================================================
    
    def get_new_products(
        self,
        start_date: date,
        end_date: date,
        employee_ids: List[int] = None
    ) -> pd.DataFrame:
        """
        Get products with first invoice ever in period (any customer).
        
        A product is "new" if:
        - The first invoice for this product (globally, any salesperson)
        - Falls within the specified date range
        - When looking back LOOKBACK_YEARS years
        
        REFACTORED v1.4.0: 
        - Uses COALESCE(product_id, legacy_code) as unified product key
        - Handles history data (has legacy_code, may lack product_id)
        - Handles realtime data (has product_id, now also has legacy_code)
        - No longer needs JOIN with products table
        - Correctly identifies same product across different identifier systems
        
        Logic:
        1. Create unified product key using COALESCE(legacy_code, product_id)
           - Prefer legacy_code because it bridges history and realtime
           - Fall back to product_id for products without legacy mapping
        2. Find MIN(inv_date) for each unified product key
        3. Filter to products where first sale is within selected period
        4. Credit all salespeople who sold on the first day (split scenario)
        5. Deduplicate per (product, salesperson) combo
        
        Returns DataFrame with: product_id, product_pn, legacy_code, brand,
                               sales_id, sales_name, split_rate_percent, first_sale_date
        """
        if employee_ids:
            employee_ids = self.access.validate_selected_employees(employee_ids)
        else:
            employee_ids = self.access.get_accessible_employee_ids()
        
        if not employee_ids:
            return pd.DataFrame()
        
        # Lookback: 5 years from start of end_date's year
        lookback_start = date(end_date.year - LOOKBACK_YEARS, 1, 1)
        
        query = """
            WITH 
            -- ================================================================
            -- Step 1: Create unified product key and find first sale date
            -- Priority: legacy_code (bridges systems) > product_id (fallback)
            -- ================================================================
            first_sale_by_product AS (
                SELECT 
                    -- Unified key: prefer legacy_code, fallback to product_id
                    COALESCE(legacy_code, CAST(product_id AS CHAR)) AS product_key,
                    MIN(inv_date) as first_sale_date
                FROM unified_sales_by_salesperson_view
                WHERE inv_date >= :lookback_start
                  AND (product_id IS NOT NULL OR legacy_code IS NOT NULL)
                GROUP BY COALESCE(legacy_code, CAST(product_id AS CHAR))
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
            -- Join back to get full product info and salesperson attribution
            -- UPDATED v1.5.0: Added pt_code, package_size from unified view
            -- ================================================================
            first_day_records AS (
                SELECT 
                    u.product_id,
                    u.product_pn,
                    u.pt_code,
                    u.package_size,
                    u.legacy_code,
                    u.brand,
                    u.sales_id,
                    u.sales_name,
                    u.split_rate_percent,
                    np.first_sale_date
                FROM new_products np
                JOIN unified_sales_by_salesperson_view u 
                    ON COALESCE(u.legacy_code, CAST(u.product_id AS CHAR)) = np.product_key
                    AND u.inv_date = np.first_sale_date
            ),
            
            -- ================================================================
            -- Step 4: Deduplicate - Each (product_key, sales_id) counted once
            -- Handles multiple invoice lines for same product on same day
            -- ================================================================
            deduplicated AS (
                SELECT 
                    -- Use MAX to get non-null values where available
                    MAX(product_id) as product_id,
                    MAX(product_pn) as product_pn,
                    MAX(pt_code) as pt_code,
                    MAX(package_size) as package_size,
                    MAX(legacy_code) as legacy_code,
                    MAX(brand) as brand,
                    sales_id,
                    MAX(sales_name) as sales_name,
                    MAX(split_rate_percent) as split_rate_percent,
                    first_sale_date,
                    -- Keep product_key for grouping
                    COALESCE(MAX(legacy_code), CAST(MAX(product_id) AS CHAR)) as product_key
                FROM first_day_records
                GROUP BY 
                    COALESCE(legacy_code, CAST(product_id AS CHAR)),
                    sales_id, 
                    first_sale_date
            )
            
            -- ================================================================
            -- Final: Return results filtered by accessible salespeople
            -- UPDATED v1.5.0: pt_code, package_size from unified view directly
            -- ================================================================
            SELECT 
                product_id,
                product_pn,
                pt_code,
                package_size,
                legacy_code,
                brand,
                sales_id,
                sales_name,
                split_rate_percent,
                first_sale_date
            FROM deduplicated
            WHERE sales_id IN :employee_ids
            ORDER BY first_sale_date DESC
        """
        
        params = {
            'lookback_start': lookback_start,
            'start_date': start_date,
            'end_date': end_date,
            'employee_ids': tuple(employee_ids)
        }
        
        return self._execute_query(query, params, "new_products")
    
    # =========================================================================
    # COMPLEX KPIs - NEW BUSINESS REVENUE
    # =========================================================================
    
    def get_new_business_revenue(
        self,
        start_date: date,
        end_date: date,
        employee_ids: List[int] = None
    ) -> pd.DataFrame:
        """
        Get revenue from first product sale to each customer.
        
        "New business" = first time a specific product is sold to a specific customer.
        Revenue is attributed based on the sales split percentage.
        
        UPDATED v1.4.0: Uses unified product key (legacy_code or product_id)
        to correctly identify customer-product combinations across systems.
        
        Returns DataFrame with: sales_id, sales_name, new_business_revenue, new_combos_count
        """
        if employee_ids:
            employee_ids = self.access.validate_selected_employees(employee_ids)
        else:
            employee_ids = self.access.get_accessible_employee_ids()
        
        if not employee_ids:
            return pd.DataFrame()
        
        # Lookback: 5 years from start of end_date's year
        lookback_start = date(end_date.year - LOOKBACK_YEARS, 1, 1)
        
        # FIXED v1.3.0: Get ALL revenue from "new" combos within period
        #               A combo is "new" if its first sale ever (in lookback) falls within period
        #               Revenue = all sales of that combo in period, not just first day
        # UPDATED v1.4.0: Use unified product key for consistent combo identification
        query = """
            WITH 
            -- ================================================================
            -- Step 1: Find first sale date for each customer-product combo
            -- Use unified product key to bridge history and realtime
            -- ================================================================
            first_combo_date AS (
                SELECT 
                    customer_id,
                    COALESCE(legacy_code, CAST(product_id AS CHAR)) AS product_key,
                    MIN(inv_date) as first_combo_date
                FROM unified_sales_by_salesperson_view
                WHERE inv_date >= :lookback_start
                  AND (product_id IS NOT NULL OR legacy_code IS NOT NULL)
                GROUP BY customer_id, COALESCE(legacy_code, CAST(product_id AS CHAR))
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
                    u.customer_id,
                    COALESCE(u.legacy_code, CAST(u.product_id AS CHAR)) AS product_key,
                    u.sales_id,
                    u.sales_name,
                    u.sales_by_split_usd,
                    u.gross_profit_by_split_usd
                FROM new_combos nc
                JOIN unified_sales_by_salesperson_view u 
                    ON nc.customer_id = u.customer_id 
                    AND COALESCE(u.legacy_code, CAST(u.product_id AS CHAR)) = nc.product_key
                WHERE u.inv_date BETWEEN :start_date AND :end_date
            )
            
            -- ================================================================
            -- Final: Aggregate by salesperson
            -- ================================================================
            SELECT 
                sales_id,
                sales_name,
                SUM(sales_by_split_usd) as new_business_revenue,
                SUM(gross_profit_by_split_usd) as new_business_gp,
                COUNT(DISTINCT CONCAT(customer_id, '-', product_key)) as new_combos_count
            FROM all_revenue_in_period
            WHERE sales_id IN :employee_ids
            GROUP BY sales_id, sales_name
            ORDER BY new_business_revenue DESC
        """
        
        params = {
            'lookback_start': lookback_start,
            'start_date': start_date,
            'end_date': end_date,
            'employee_ids': tuple(employee_ids)
        }
        
        return self._execute_query(query, params, "new_business_revenue")
    
    def get_new_business_detail(
        self,
        start_date: date,
        end_date: date,
        employee_ids: List[int] = None
    ) -> pd.DataFrame:
        """
        Get detailed line items for new business (first customer-product combos).
        
        NEW v1.5.0: Returns line-by-line detail instead of aggregate.
        Used for popover display showing each new combo.
        
        Returns DataFrame with: customer, product info (pt_code, product_pn, package_size),
                               brand, salesperson, revenue, GP, first_combo_date
        """
        if employee_ids:
            employee_ids = self.access.validate_selected_employees(employee_ids)
        else:
            employee_ids = self.access.get_accessible_employee_ids()
        
        if not employee_ids:
            return pd.DataFrame()
        
        # Lookback: 5 years from start of end_date's year
        lookback_start = date(end_date.year - LOOKBACK_YEARS, 1, 1)
        
        query = """
            WITH 
            -- ================================================================
            -- Step 1: Find first sale date for each customer-product combo
            -- ================================================================
            first_combo_date AS (
                SELECT 
                    customer_id,
                    COALESCE(legacy_code, CAST(product_id AS CHAR)) AS product_key,
                    MIN(inv_date) as first_combo_date
                FROM unified_sales_by_salesperson_view
                WHERE inv_date >= :lookback_start
                  AND (product_id IS NOT NULL OR legacy_code IS NOT NULL)
                GROUP BY customer_id, COALESCE(legacy_code, CAST(product_id AS CHAR))
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
            -- Step 3: Get detailed revenue data for new combos
            -- Aggregate by combo + salesperson
            -- UPDATED: package_size from unified view directly
            -- ================================================================
            combo_detail AS (
                SELECT 
                    u.customer_id,
                    u.customer,
                    MAX(u.product_id) as product_id,
                    MAX(u.product_pn) as product_pn,
                    MAX(u.pt_code) as pt_code,
                    MAX(u.package_size) as package_size,
                    MAX(u.brand) as brand,
                    u.sales_id,
                    MAX(u.sales_name) as sales_name,
                    MAX(u.split_rate_percent) as split_rate_percent,
                    nc.first_combo_date,
                    SUM(u.sales_by_split_usd) as revenue,
                    SUM(u.gross_profit_by_split_usd) as gross_profit
                FROM new_combos nc
                JOIN unified_sales_by_salesperson_view u 
                    ON nc.customer_id = u.customer_id 
                    AND COALESCE(u.legacy_code, CAST(u.product_id AS CHAR)) = nc.product_key
                WHERE u.inv_date BETWEEN :start_date AND :end_date
                  AND u.sales_id IN :employee_ids
                GROUP BY 
                    u.customer_id, 
                    u.customer,
                    COALESCE(u.legacy_code, CAST(u.product_id AS CHAR)),
                    u.sales_id,
                    nc.first_combo_date
            )
            
            -- ================================================================
            -- Final: Return directly from combo_detail (no JOIN needed)
            -- ================================================================
            SELECT 
                customer,
                product_pn,
                pt_code,
                package_size,
                brand,
                sales_name,
                split_rate_percent,
                first_combo_date,
                revenue,
                gross_profit
            FROM combo_detail
            ORDER BY revenue DESC
        """
        
        params = {
            'lookback_start': lookback_start,
            'start_date': start_date,
            'end_date': end_date,
            'employee_ids': tuple(employee_ids)
        }
        
        return self._execute_query(query, params, "new_business_detail")
    
    # =========================================================================
    # LOOKUP DATA
    # =========================================================================
    
    def get_salesperson_options(
        self,
        start_date: date = None,
        end_date: date = None,
        year: int = None
    ) -> pd.DataFrame:
        """
        Get list of salespeople who have sales data for dropdown selection.
        Only returns salespeople with actual sales records.
        Filtered by access control.
        
        Args:
            start_date: Optional start date filter (if both dates provided)
            end_date: Optional end date filter (if both dates provided)
            year: Optional year filter (alternative to date range)
        
        Returns DataFrame with: employee_id, sales_name, email, invoice_count
        """
        accessible_ids = self.access.get_accessible_employee_ids()
        
        if not accessible_ids:
            return pd.DataFrame()
        
        # Query salespeople from actual sales data
        query = """
            SELECT DISTINCT
                sales_id as employee_id,
                sales_name,
                sales_email as email,
                COUNT(DISTINCT inv_number) as invoice_count
            FROM unified_sales_by_salesperson_view
            WHERE sales_id IN :employee_ids
              AND sales_id IS NOT NULL
              AND sales_name IS NOT NULL
        """
        
        params = {'employee_ids': tuple(accessible_ids)}
        
        # Add date filter if provided
        if start_date and end_date:
            query += " AND inv_date BETWEEN :start_date AND :end_date"
            params['start_date'] = start_date
            params['end_date'] = end_date
        elif year:
            query += " AND invoice_year = :year"
            params['year'] = int(year)
        
        query += """
            GROUP BY sales_id, sales_name, sales_email
            HAVING COUNT(DISTINCT inv_number) > 0
            ORDER BY sales_name
        """
        
        return self._execute_query(query, params, "salesperson_options")
    
    def get_entity_options(self) -> pd.DataFrame:
        """
        Get list of legal entities that have sales data.
        
        Returns DataFrame with: entity_id, entity_name, entity_code, invoice_count
        """
        query = """
            SELECT DISTINCT
                legal_entity_id as entity_id,
                legal_entity as entity_name,
                COUNT(DISTINCT inv_number) as invoice_count
            FROM unified_sales_by_salesperson_view
            WHERE legal_entity_id IS NOT NULL
              AND legal_entity IS NOT NULL
            GROUP BY legal_entity_id, legal_entity
            HAVING COUNT(DISTINCT inv_number) > 0
            ORDER BY legal_entity
        """
        
        return self._execute_query(query, {}, "entity_options")
    
    def get_available_years(self) -> List[int]:
        """
        Get list of years that have sales data.
        
        Returns sorted list of years (descending).
        """
        query = """
            SELECT DISTINCT invoice_year
            FROM unified_sales_by_salesperson_view
            WHERE invoice_year IS NOT NULL
            ORDER BY invoice_year DESC
        """
        
        df = self._execute_query(query, {}, "available_years")
        
        if df.empty:
            current_year = datetime.now().year
            return [current_year, current_year - 1]
        
        # Ensure years are integers
        return [int(y) for y in df['invoice_year'].tolist()]
    
    def get_default_date_range(self) -> Tuple[date, date]:
        """
        Get default date range based on actual data in database.
        
        Start: January 1st of the most recent year with sales data
        End: Today (for current period analysis)
        
        Note: Backlog is NOT filtered by this date range.
        Date range only applies to sales/invoice data.
        
        Returns:
            Tuple of (start_date, end_date)
        """
        today = date.today()
        
        # Get most recent year with sales
        query_year = """
            SELECT MAX(invoice_year) as max_year
            FROM unified_sales_by_salesperson_view
            WHERE invoice_year IS NOT NULL
        """
        df_year = self._execute_query(query_year, {}, "max_sales_year")
        
        if df_year.empty or df_year['max_year'].iloc[0] is None:
            start_date = date(today.year, 1, 1)
        else:
            max_year = int(df_year['max_year'].iloc[0])
            start_date = date(max_year, 1, 1)
        
        # End date is always today for current period
        end_date = today
        
        return start_date, end_date
    
    # =========================================================================
    # YoY COMPARISON DATA
    # =========================================================================
    
    def get_previous_year_data(
        self,
        start_date: date,
        end_date: date,
        employee_ids: List[int] = None,
        entity_ids: List[int] = None
    ) -> pd.DataFrame:
        """
        Get same period data from previous year for YoY comparison.
        
        Args:
            start_date: Current period start date
            end_date: Current period end date
            employee_ids: Optional employee filter
            entity_ids: Optional entity filter
            
        Returns:
            DataFrame with previous year data
        """
        # Calculate previous year dates
        prev_start = date(start_date.year - 1, start_date.month, start_date.day)
        
        # Handle leap year for end date
        try:
            prev_end = date(end_date.year - 1, end_date.month, end_date.day)
        except ValueError:
            # Feb 29 -> Feb 28 for non-leap year
            prev_end = date(end_date.year - 1, end_date.month, 28)
        
        return self.get_sales_data(prev_start, prev_end, employee_ids, entity_ids)
    
    # =========================================================================
    # BACKLOG DATA (Outstanding)
    # =========================================================================
    
    def get_backlog_data(
        self,
        employee_ids: List[int] = None,
        entity_ids: List[int] = None
    ) -> pd.DataFrame:
        """
        Get total backlog/outstanding data by salesperson.
        
        Returns DataFrame with total backlog revenue and GP by salesperson.
        """
        if employee_ids:
            employee_ids = self.access.validate_selected_employees(employee_ids)
        else:
            employee_ids = self.access.get_accessible_employee_ids()
        
        if not employee_ids:
            return pd.DataFrame()
        
        # UPDATED: Backlog = Uninvoiced value only
        # Filter out rows where invoice_completion_percent = 100
        query = """
            SELECT 
                sales_id,
                sales_name,
                SUM(backlog_sales_by_split_usd) as total_backlog_revenue,
                SUM(backlog_gp_by_split_usd) as total_backlog_gp,
                COUNT(DISTINCT oc_number) as backlog_orders,
                COUNT(DISTINCT customer_id) as backlog_customers
            FROM backlog_by_salesperson_looker_view
            WHERE sales_id IN :employee_ids
              AND (invoice_completion_percent < 100 OR invoice_completion_percent IS NULL)
        """
        
        params = {'employee_ids': tuple(employee_ids)}
        
        if entity_ids:
            query += " AND entity_id IN :entity_ids"
            params['entity_ids'] = tuple(entity_ids)
        
        query += " GROUP BY sales_id, sales_name"
        
        return self._execute_query(query, params, "backlog_data")
    
    def get_backlog_in_period(
        self,
        start_date: date,
        end_date: date,
        employee_ids: List[int] = None,
        entity_ids: List[int] = None
    ) -> pd.DataFrame:
        """
        Get backlog with ETD falling within the specified period.
        This represents backlog expected to convert to invoice in the period.
        
        Args:
            start_date: Period start date
            end_date: Period end date
            employee_ids: Optional employee filter
            entity_ids: Optional entity filter
            
        Returns DataFrame with in-period backlog by salesperson.
        """
        if employee_ids:
            employee_ids = self.access.validate_selected_employees(employee_ids)
        else:
            employee_ids = self.access.get_accessible_employee_ids()
        
        if not employee_ids:
            return pd.DataFrame()
        
        # UPDATED: Backlog = Uninvoiced value only
        query = """
            SELECT 
                sales_id,
                sales_name,
                SUM(backlog_sales_by_split_usd) as in_period_backlog_revenue,
                SUM(backlog_gp_by_split_usd) as in_period_backlog_gp,
                COUNT(DISTINCT oc_number) as in_period_orders,
                COUNT(DISTINCT customer_id) as in_period_customers
            FROM backlog_by_salesperson_looker_view
            WHERE sales_id IN :employee_ids
              AND etd BETWEEN :start_date AND :end_date
              AND (invoice_completion_percent < 100 OR invoice_completion_percent IS NULL)
        """
        
        params = {
            'employee_ids': tuple(employee_ids),
            'start_date': start_date,
            'end_date': end_date
        }
        
        if entity_ids:
            query += " AND entity_id IN :entity_ids"
            params['entity_ids'] = tuple(entity_ids)
        
        query += " GROUP BY sales_id, sales_name"
        
        return self._execute_query(query, params, "backlog_in_period")
    
    def get_backlog_by_month(
        self,
        employee_ids: List[int] = None,
        entity_ids: List[int] = None
    ) -> pd.DataFrame:
        """
        Get backlog grouped by ETD month for forecasting.
        
        Returns DataFrame with backlog by ETD month.
        """
        if employee_ids:
            employee_ids = self.access.validate_selected_employees(employee_ids)
        else:
            employee_ids = self.access.get_accessible_employee_ids()
        
        if not employee_ids:
            return pd.DataFrame()
        
        # UPDATED: Backlog = Uninvoiced value only
        query = """
            SELECT 
                etd_year,
                etd_month,
                SUM(backlog_sales_by_split_usd) as backlog_revenue,
                SUM(backlog_gp_by_split_usd) as backlog_gp,
                COUNT(DISTINCT oc_number) as order_count
            FROM backlog_by_salesperson_looker_view
            WHERE sales_id IN :employee_ids
              AND etd IS NOT NULL
              AND (invoice_completion_percent < 100 OR invoice_completion_percent IS NULL)
        """
        
        params = {'employee_ids': tuple(employee_ids)}
        
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
        employee_ids: List[int] = None,
        entity_ids: List[int] = None,
        limit: int = 100
    ) -> pd.DataFrame:
        """
        Get detailed backlog records for drill-down.
        
        Returns DataFrame with individual backlog line items.
        """
        if employee_ids:
            employee_ids = self.access.validate_selected_employees(employee_ids)
        else:
            employee_ids = self.access.get_accessible_employee_ids()
        
        if not employee_ids:
            return pd.DataFrame()
        
        # UPDATED v1.5.0: Backlog = Uninvoiced value only
        # Added: customer_po_number, pt_code, package_size for enhanced display
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
                sales_name,
                sales_id,
                legal_entity,
                backlog_sales_by_split_usd,
                backlog_gp_by_split_usd,
                split_rate_percent,
                pending_type,
                days_until_etd,
                status,
                invoice_completion_percent
            FROM backlog_by_salesperson_looker_view
            WHERE sales_id IN :employee_ids
              AND (invoice_completion_percent < 100 OR invoice_completion_percent IS NULL)
        """
        
        params = {'employee_ids': tuple(employee_ids)}
        
        if entity_ids:
            query += " AND entity_id IN :entity_ids"
            params['entity_ids'] = tuple(entity_ids)
        
        query += f"""
            ORDER BY backlog_sales_by_split_usd DESC
            LIMIT {limit}
        """
        
        return self._execute_query(query, params, "backlog_detail")
    
    # =========================================================================
    # SALES SPLIT DATA
    # =========================================================================
    
    def get_sales_split_data(
        self,
        employee_ids: List[int] = None
    ) -> pd.DataFrame:
        """
        Get sales split assignments for salespeople.
        
        Returns DataFrame with split assignments including customer, product, percentage.
        """
        if employee_ids:
            employee_ids = self.access.validate_selected_employees(employee_ids)
        else:
            employee_ids = self.access.get_accessible_employee_ids()
        
        if not employee_ids:
            return pd.DataFrame()
        
        query = """
            SELECT 
                ss.sales_id,
                ss.sales_name,
                ss.sales_email,
                ss.employment_status,
                c.english_name as customer,
                c.id as customer_id,
                COALESCE(p.name, 'All Products') as product_pn,
                p.id as product_id,
                ss.split_percentage,
                ss.effective_period,
                ss.approval_status
            FROM sales_split_full_looker_view ss
            LEFT JOIN companies c ON ss.customer_id = c.id
            LEFT JOIN products p ON ss.product_id = p.id
            WHERE ss.sales_id IN :employee_ids
              AND ss.approval_status = 'approved'
            ORDER BY ss.sales_name, c.english_name
        """
        
        params = {'employee_ids': tuple(employee_ids)}
        
        return self._execute_query(query, params, "sales_split_data")
    
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
        
        Args:
            query: SQL query string
            params: Query parameters
            query_name: Name for logging
            
        Returns:
            DataFrame with results
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
    employee_ids: tuple,
    entity_ids: tuple = None
) -> pd.DataFrame:
    """
    Cached version of sales data query.
    Note: Uses tuple for cache key compatibility.
    """
    engine = get_db_engine()
    
    query = """
        SELECT 
            data_source,
            unified_line_id,
            sales_id,
            sales_name,
            sales_email,
            employment_status,
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
            sales_by_split_usd,
            gross_profit_by_split_usd,
            gp1_by_split_usd,
            allocated_broker_commission_usd,
            invoice_month,
            invoice_year
        FROM unified_sales_by_salesperson_view
        WHERE inv_date BETWEEN :start_date AND :end_date
          AND sales_id IN :employee_ids
    """
    
    params = {
        'start_date': start_date,
        'end_date': end_date,
        'employee_ids': employee_ids
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


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def get_kpi_targets_cached(year: int, employee_ids: tuple) -> pd.DataFrame:
    """Cached KPI targets query."""
    engine = get_db_engine()
    
    query = """
        SELECT 
            employee_id,
            employee_name,
            email,
            status,
            year,
            kpi_type_id,
            kpi_name,
            annual_target_value,
            annual_target_value_numeric,
            unit_of_measure,
            weight_numeric,
            monthly_target_value,
            quarterly_target_value,
            is_current_year
        FROM sales_employee_kpi_assignments_view
        WHERE year = :year
          AND employee_id IN :employee_ids
    """
    
    try:
        return pd.read_sql(text(query), engine, params={
            'year': year,
            'employee_ids': employee_ids
        })
    except Exception as e:
        logger.error(f"Error in cached KPI query: {e}")
        return pd.DataFrame()