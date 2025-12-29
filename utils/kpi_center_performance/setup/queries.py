# utils/kpi_center_performance/setup/queries.py
"""
SQL Queries for Setup Tab - KPI Center Performance

Handles all database interactions for Setup tab:
- KPI Center Split Rules (Read - later CRUD)
- KPI Assignments (Read - later CRUD)
- Hierarchy data
- Validation queries

VERSION: 1.0.0
CHANGELOG:
- v1.0.0: Initial extraction from main queries.py
          - get_kpi_split_data() moved here
          - get_kpi_center_hierarchy() moved here (wrapper to main)
          - Added get_split_validation_summary()
          - Prepared structure for future CRUD operations
"""

import logging
from datetime import date, datetime
from typing import List, Optional, Dict, Tuple
import pandas as pd
from sqlalchemy import text

from utils.db import get_db_engine

logger = logging.getLogger(__name__)


class SetupQueries:
    """
    Database queries for Setup tab functionality.
    
    Usage:
        from utils.kpi_center_performance.setup import SetupQueries
        
        setup_queries = SetupQueries()
        split_df = setup_queries.get_kpi_split_data(kpi_center_ids=[1, 2, 3])
    """
    
    def __init__(self):
        """Initialize with database engine."""
        self._engine = None
    
    @property
    def engine(self):
        """Lazy load database engine."""
        if self._engine is None:
            self._engine = get_db_engine()
        return self._engine
    
    # =========================================================================
    # KPI SPLIT RULES - READ
    # =========================================================================
    
    def get_kpi_split_data(
        self,
        kpi_center_ids: List[int] = None,
        customer_ids: List[int] = None,
        product_ids: List[int] = None,
        kpi_type: str = None,
        status_filter: str = None,  # 'ok', 'incomplete', 'over_100'
        approval_filter: str = None,  # 'approved', 'pending', 'all'
        active_only: bool = True,
        limit: int = None
    ) -> pd.DataFrame:
        """
        Get KPI Center split assignments with enhanced filtering.
        
        Args:
            kpi_center_ids: Filter by KPI Center IDs
            customer_ids: Filter by Customer IDs
            product_ids: Filter by Product IDs
            kpi_type: Filter by KPI type (TERRITORY, VERTICAL, etc.)
            status_filter: Filter by split status
            approval_filter: Filter by approval status
            active_only: Only show rules with valid_to >= today
            limit: Limit number of results
            
        Returns:
            DataFrame with split assignments
        """
        query = """
            SELECT 
                kpi_center_split_id,
                kpi_center_id,
                kpi_center_name,
                kpi_type,
                customer_id,
                customer_name,
                company_code,
                product_id,
                product_pn,
                pt_code,
                brand,
                split_percentage,
                effective_from,
                effective_to,
                effective_period,
                is_approved,
                approval_status,
                total_split_percentage_by_type,
                kpi_split_status,
                existing_kpi_split_structure
            FROM kpi_center_split_looker_view
            WHERE 1=1
        """
        
        params = {}
        
        # KPI Center filter
        if kpi_center_ids:
            query += " AND kpi_center_id IN :kpi_center_ids"
            params['kpi_center_ids'] = tuple(kpi_center_ids)
        
        # Customer filter
        if customer_ids:
            query += " AND customer_id IN :customer_ids"
            params['customer_ids'] = tuple(customer_ids)
        
        # Product filter
        if product_ids:
            query += " AND product_id IN :product_ids"
            params['product_ids'] = tuple(product_ids)
        
        # KPI Type filter
        if kpi_type:
            query += " AND kpi_type = :kpi_type"
            params['kpi_type'] = kpi_type
        
        # Status filter
        if status_filter and status_filter != 'all':
            query += " AND kpi_split_status = :status_filter"
            params['status_filter'] = status_filter
        
        # Approval filter
        if approval_filter == 'approved':
            query += " AND is_approved = 1"
        elif approval_filter == 'pending':
            query += " AND (is_approved = 0 OR is_approved IS NULL)"
        # 'all' or None = no filter
        
        # Active only filter
        if active_only:
            query += " AND (effective_to >= CURDATE() OR effective_to IS NULL)"
        
        query += " ORDER BY kpi_center_name, customer_name, product_pn"
        
        if limit:
            query += f" LIMIT {limit}"
        
        return self._execute_query(query, params, "kpi_split_data")
    
    def get_split_validation_summary(self) -> Dict:
        """
        Get summary of split rule validation status.
        
        Returns:
            Dict with counts: total, ok, incomplete, over_100, pending, expiring_soon
        """
        query = """
            SELECT 
                COUNT(*) as total_rules,
                SUM(CASE WHEN kpi_split_status = 'ok' THEN 1 ELSE 0 END) as ok_count,
                SUM(CASE WHEN kpi_split_status = 'incomplete_split' THEN 1 ELSE 0 END) as incomplete_count,
                SUM(CASE WHEN kpi_split_status = 'over_100_split' THEN 1 ELSE 0 END) as over_100_count,
                SUM(CASE WHEN is_approved = 0 OR is_approved IS NULL THEN 1 ELSE 0 END) as pending_count,
                SUM(CASE 
                    WHEN effective_to BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 30 DAY) 
                    THEN 1 ELSE 0 
                END) as expiring_soon_count
            FROM kpi_center_split_looker_view
            WHERE effective_to >= CURDATE() OR effective_to IS NULL
        """
        
        df = self._execute_query(query, {}, "split_validation_summary")
        
        if df.empty:
            return {
                'total_rules': 0,
                'ok_count': 0,
                'incomplete_count': 0,
                'over_100_count': 0,
                'pending_count': 0,
                'expiring_soon_count': 0
            }
        
        row = df.iloc[0]
        return {
            'total_rules': int(row.get('total_rules', 0) or 0),
            'ok_count': int(row.get('ok_count', 0) or 0),
            'incomplete_count': int(row.get('incomplete_count', 0) or 0),
            'over_100_count': int(row.get('over_100_count', 0) or 0),
            'pending_count': int(row.get('pending_count', 0) or 0),
            'expiring_soon_count': int(row.get('expiring_soon_count', 0) or 0)
        }
    
    def get_split_by_customer_product(
        self,
        customer_id: int,
        product_id: int,
        kpi_type: str = None
    ) -> pd.DataFrame:
        """
        Get all split rules for a specific customer-product combination.
        Used to show current splits when adding/editing.
        
        Args:
            customer_id: Customer ID
            product_id: Product ID
            kpi_type: Optional KPI type filter
            
        Returns:
            DataFrame with all splits for this combo
        """
        query = """
            SELECT 
                kpi_center_id,
                kpi_center_name,
                kpi_type,
                split_percentage,
                effective_from,
                effective_to,
                is_approved,
                approval_status
            FROM kpi_center_split_looker_view
            WHERE customer_id = :customer_id
              AND product_id = :product_id
              AND (effective_to >= CURDATE() OR effective_to IS NULL)
        """
        
        params = {
            'customer_id': customer_id,
            'product_id': product_id
        }
        
        if kpi_type:
            query += " AND kpi_type = :kpi_type"
            params['kpi_type'] = kpi_type
        
        query += " ORDER BY kpi_type, kpi_center_name"
        
        return self._execute_query(query, params, "split_by_customer_product")
    
    # =========================================================================
    # KPI CENTER HIERARCHY
    # =========================================================================
    
    def get_kpi_center_hierarchy(
        self,
        kpi_type: str = None,
        include_stats: bool = False
    ) -> pd.DataFrame:
        """
        Get KPI Center hierarchy with parent-child relationships.
        
        Args:
            kpi_type: Filter by KPI type
            include_stats: Include statistics (split count, assignment count)
            
        Returns:
            DataFrame with columns: kpi_center_id, kpi_center_name, kpi_type,
                                   parent_center_id, level, is_leaf, etc.
        """
        if include_stats:
            query = """
                WITH RECURSIVE kpi_hierarchy AS (
                    -- Base case: root KPI centers (no parent)
                    SELECT 
                        id AS kpi_center_id,
                        name AS kpi_center_name,
                        type AS kpi_type,
                        description,
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
                        kc.description,
                        kc.parent_center_id,
                        kh.level + 1
                    FROM kpi_centers kc
                    INNER JOIN kpi_hierarchy kh ON kc.parent_center_id = kh.kpi_center_id
                    WHERE kc.delete_flag = 0
                ),
                split_counts AS (
                    SELECT 
                        kpi_center_id,
                        COUNT(*) as split_count
                    FROM kpi_center_split_looker_view
                    WHERE effective_to >= CURDATE() OR effective_to IS NULL
                    GROUP BY kpi_center_id
                ),
                assignment_counts AS (
                    SELECT 
                        kpi_center_id,
                        COUNT(*) as assignment_count,
                        MAX(year) as latest_year
                    FROM sales_kpi_center_assignments_view
                    GROUP BY kpi_center_id
                ),
                children_count AS (
                    SELECT 
                        parent_center_id,
                        COUNT(*) as child_count
                    FROM kpi_centers
                    WHERE delete_flag = 0 AND parent_center_id IS NOT NULL
                    GROUP BY parent_center_id
                )
                SELECT 
                    h.kpi_center_id,
                    h.kpi_center_name,
                    h.kpi_type,
                    h.description,
                    h.parent_center_id,
                    h.level,
                    CASE WHEN cc.child_count IS NULL OR cc.child_count = 0 THEN 1 ELSE 0 END as is_leaf,
                    COALESCE(cc.child_count, 0) as children_count,
                    COALESCE(sc.split_count, 0) as split_count,
                    COALESCE(ac.assignment_count, 0) as assignment_count,
                    ac.latest_year
                FROM kpi_hierarchy h
                LEFT JOIN children_count cc ON h.kpi_center_id = cc.parent_center_id
                LEFT JOIN split_counts sc ON h.kpi_center_id = sc.kpi_center_id
                LEFT JOIN assignment_counts ac ON h.kpi_center_id = ac.kpi_center_id
                WHERE 1=1
            """
        else:
            query = """
                WITH RECURSIVE kpi_hierarchy AS (
                    -- Base case: root KPI centers (no parent)
                    SELECT 
                        id AS kpi_center_id,
                        name AS kpi_center_name,
                        type AS kpi_type,
                        description,
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
                        kc.description,
                        kc.parent_center_id,
                        kh.level + 1
                    FROM kpi_centers kc
                    INNER JOIN kpi_hierarchy kh ON kc.parent_center_id = kh.kpi_center_id
                    WHERE kc.delete_flag = 0
                ),
                children_count AS (
                    SELECT 
                        parent_center_id,
                        COUNT(*) as child_count
                    FROM kpi_centers
                    WHERE delete_flag = 0 AND parent_center_id IS NOT NULL
                    GROUP BY parent_center_id
                )
                SELECT 
                    h.kpi_center_id,
                    h.kpi_center_name,
                    h.kpi_type,
                    h.description,
                    h.parent_center_id,
                    h.level,
                    CASE WHEN cc.child_count IS NULL OR cc.child_count = 0 THEN 1 ELSE 0 END as is_leaf,
                    COALESCE(cc.child_count, 0) as children_count
                FROM kpi_hierarchy h
                LEFT JOIN children_count cc ON h.kpi_center_id = cc.parent_center_id
                WHERE 1=1
            """
        
        params = {}
        
        if kpi_type:
            query += " AND h.kpi_type = :kpi_type"
            params['kpi_type'] = kpi_type
        
        query += " ORDER BY h.kpi_type, h.level, h.kpi_center_name"
        
        return self._execute_query(query, params, "kpi_center_hierarchy")
    
    def get_kpi_centers_for_dropdown(
        self,
        kpi_type: str = None,
        exclude_ids: List[int] = None
    ) -> pd.DataFrame:
        """
        Get KPI Centers for dropdown selection (e.g., parent selection).
        
        Args:
            kpi_type: Filter by type (for parent selection, should match child type)
            exclude_ids: IDs to exclude (e.g., self and descendants when editing)
            
        Returns:
            DataFrame with id, name, type for dropdown options
        """
        query = """
            SELECT 
                id AS kpi_center_id,
                name AS kpi_center_name,
                type AS kpi_type,
                parent_center_id
            FROM kpi_centers
            WHERE delete_flag = 0
        """
        
        params = {}
        
        if kpi_type:
            query += " AND type = :kpi_type"
            params['kpi_type'] = kpi_type
        
        if exclude_ids:
            query += " AND id NOT IN :exclude_ids"
            params['exclude_ids'] = tuple(exclude_ids)
        
        query += " ORDER BY type, name"
        
        return self._execute_query(query, params, "kpi_centers_dropdown")
    
    # =========================================================================
    # KPI ASSIGNMENTS - READ
    # =========================================================================
    
    def get_kpi_assignments(
        self,
        year: int = None,
        kpi_center_ids: List[int] = None,
        kpi_type_id: int = None
    ) -> pd.DataFrame:
        """
        Get KPI assignments for display and editing.
        
        Args:
            year: Filter by year
            kpi_center_ids: Filter by KPI Center IDs
            kpi_type_id: Filter by KPI type ID
            
        Returns:
            DataFrame with assignment details including weight sums
        """
        query = """
            SELECT 
                a.kpi_center_id,
                a.kpi_center_name,
                a.kpi_center_type,
                a.parent_center_id,
                a.year,
                a.kpi_type_id,
                a.kpi_name,
                a.kpi_description,
                a.unit_of_measure,
                a.annual_target_value,
                a.weight,
                a.annual_target_value_numeric,
                a.weight_numeric,
                a.monthly_target_value,
                a.quarterly_target_value,
                a.notes
            FROM sales_kpi_center_assignments_view a
            WHERE 1=1
        """
        
        params = {}
        
        if year:
            query += " AND a.year = :year"
            params['year'] = year
        
        if kpi_center_ids:
            query += " AND a.kpi_center_id IN :kpi_center_ids"
            params['kpi_center_ids'] = tuple(kpi_center_ids)
        
        if kpi_type_id:
            query += " AND a.kpi_type_id = :kpi_type_id"
            params['kpi_type_id'] = kpi_type_id
        
        query += " ORDER BY a.kpi_center_name, a.kpi_name"
        
        return self._execute_query(query, params, "kpi_assignments")
    
    def get_assignment_weight_summary(
        self,
        year: int
    ) -> pd.DataFrame:
        """
        Get weight sum per KPI Center for a year.
        Used for validation (total should be 100%).
        
        Args:
            year: Target year
            
        Returns:
            DataFrame with kpi_center_id, kpi_center_name, total_weight
        """
        query = """
            SELECT 
                kpi_center_id,
                kpi_center_name,
                year,
                SUM(weight_numeric) as total_weight,
                COUNT(*) as kpi_count
            FROM sales_kpi_center_assignments_view
            WHERE year = :year
            GROUP BY kpi_center_id, kpi_center_name, year
            ORDER BY kpi_center_name
        """
        
        return self._execute_query(query, {'year': year}, "assignment_weight_summary")
    
    def get_kpi_types(self) -> pd.DataFrame:
        """
        Get all KPI types for dropdown selection.
        
        Returns:
            DataFrame with id, name, description, uom
        """
        query = """
            SELECT 
                id,
                name,
                description,
                uom
            FROM kpi_types
            WHERE delete_flag = 0
            ORDER BY name
        """
        
        return self._execute_query(query, {}, "kpi_types")
    
    def get_available_years(self) -> List[int]:
        """
        Get list of years with KPI assignments.
        
        Returns:
            List of years
        """
        query = """
            SELECT DISTINCT year
            FROM sales_kpi_center_assignments
            WHERE delete_flag = 0
            ORDER BY year DESC
        """
        
        df = self._execute_query(query, {}, "available_years")
        
        if df.empty:
            return [datetime.now().year]
        
        return df['year'].tolist()
    
    # =========================================================================
    # LOOKUP QUERIES
    # =========================================================================
    
    def get_customers_for_dropdown(
        self,
        search: str = None,
        limit: int = 100
    ) -> pd.DataFrame:
        """
        Get customers for dropdown selection.
        
        Args:
            search: Optional search string
            limit: Maximum results
            
        Returns:
            DataFrame with customer info
        """
        query = """
            SELECT DISTINCT
                c.id as customer_id,
                c.english_name as customer_name,
                c.company_code
            FROM companies c
            WHERE c.delete_flag = 0
              AND c.customer_flag = 1
        """
        
        params = {}
        
        if search:
            query += """
                AND (
                    c.english_name LIKE :search
                    OR c.company_code LIKE :search
                )
            """
            params['search'] = f"%{search}%"
        
        query += f" ORDER BY c.english_name LIMIT {limit}"
        
        return self._execute_query(query, params, "customers_dropdown")
    
    def get_products_for_dropdown(
        self,
        search: str = None,
        brand_id: int = None,
        limit: int = 100
    ) -> pd.DataFrame:
        """
        Get products for dropdown selection.
        
        Args:
            search: Optional search string
            brand_id: Optional brand filter
            limit: Maximum results
            
        Returns:
            DataFrame with product info
        """
        query = """
            SELECT 
                p.id as product_id,
                p.name as product_name,
                p.pt_code,
                b.brand_name
            FROM products p
            LEFT JOIN brands b ON p.brand_id = b.id
            WHERE p.delete_flag = 0
        """
        
        params = {}
        
        if search:
            query += """
                AND (
                    p.name LIKE :search
                    OR p.pt_code LIKE :search
                )
            """
            params['search'] = f"%{search}%"
        
        if brand_id:
            query += " AND p.brand_id = :brand_id"
            params['brand_id'] = brand_id
        
        query += f" ORDER BY p.name LIMIT {limit}"
        
        return self._execute_query(query, params, "products_dropdown")
    
    def get_brands_for_dropdown(self) -> pd.DataFrame:
        """
        Get brands for dropdown selection.
        
        Returns:
            DataFrame with brand info
        """
        query = """
            SELECT 
                id as brand_id,
                brand_name
            FROM brands
            WHERE delete_flag = 0
            ORDER BY brand_name
        """
        
        return self._execute_query(query, {}, "brands_dropdown")
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _execute_query(
        self, 
        query: str, 
        params: dict, 
        query_name: str = "query"
    ) -> pd.DataFrame:
        """Execute SQL query and return DataFrame."""
        try:
            logger.debug(f"Executing {query_name}")
            df = pd.read_sql(text(query), self.engine, params=params)
            logger.debug(f"{query_name} returned {len(df)} rows")
            return df
        except Exception as e:
            logger.error(f"Error executing {query_name}: {e}")
            return pd.DataFrame()