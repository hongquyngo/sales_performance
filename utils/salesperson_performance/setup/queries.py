# utils/salesperson_performance/setup/queries.py
"""
SQL Queries for Setup Tab - Salesperson Performance

Full CRUD operations for:
- Sales Split Rules (sales_split_by_customer_product)
- KPI Assignments (sales_employee_kpi_assignments)
- Salespeople Management

v1.0.0 - Initial version based on KPI Center Performance setup pattern
"""

import logging
from datetime import date, datetime
from typing import List, Optional, Dict, Tuple, Any
import pandas as pd
from sqlalchemy import text

from utils.db import get_db_engine

logger = logging.getLogger(__name__)


class SalespersonSetupQueries:
    """
    Database queries for Salesperson Setup tab functionality.
    
    Usage:
        from utils.salesperson_performance.setup import SalespersonSetupQueries
        
        setup_queries = SalespersonSetupQueries()
        
        # Read
        split_df = setup_queries.get_sales_split_data(employee_ids=[1, 2, 3])
        
        # Create
        result = setup_queries.create_split_rule(
            customer_id=1, product_id=100, sale_person_id=5,
            split_percentage=50, valid_from=date.today(), valid_to=date(2025,12,31)
        )
        
        # Update
        setup_queries.update_split_rule(rule_id=123, split_percentage=60)
        
        # Delete
        setup_queries.delete_split_rule(rule_id=123)
    """
    
    def __init__(self, user_id: str = None):
        """
        Initialize with database engine.
        
        Args:
            user_id: Current user UUID for audit trail
        """
        self._engine = None
        self.user_id = user_id
    
    @property
    def engine(self):
        """Lazy load database engine."""
        if self._engine is None:
            self._engine = get_db_engine()
        return self._engine
    
    # =========================================================================
    # SALES SPLIT RULES - READ
    # =========================================================================
    
    def get_sales_split_data(
        self,
        # Entity filters
        employee_ids: List[int] = None,
        customer_ids: List[int] = None,
        product_ids: List[int] = None,
        brand_ids: List[int] = None,
        
        # Period filters
        period_year: int = None,
        period_start: date = None,
        period_end: date = None,
        
        # Rule attribute filters
        status_filter: str = None,         # 'ok', 'incomplete_split', 'over_100_split'
        approval_filter: str = None,       # 'approved', 'pending', 'all'
        split_min: float = None,
        split_max: float = None,
        
        # System filters
        include_deleted: bool = False,
        
        # Pagination
        limit: int = None
    ) -> pd.DataFrame:
        """
        Get Sales Split assignments with comprehensive filtering.
        
        Period filter uses OVERLAPPING logic: rule's [valid_from, valid_to] 
        overlaps with [period_start, period_end]
        
        Args:
            employee_ids: Filter by Salesperson IDs
            customer_ids: Filter by Customer IDs
            product_ids: Filter by Product IDs
            brand_ids: Filter by Brand IDs
            
            period_year: Filter rules overlapping this year
            period_start: Custom period start date
            period_end: Custom period end date
            
            status_filter: Filter by split status
            approval_filter: Filter by approval status
            split_min: Minimum split percentage
            split_max: Maximum split percentage
            
            include_deleted: If True, show deleted rules too
            
            limit: Limit number of results
            
        Returns:
            DataFrame with split assignments
        """
        query = """
            SELECT 
                -- Primary ID
                ss.id AS split_id,
                
                -- Salesperson
                ss.sale_person_id,
                CONCAT(e.first_name, ' ', e.last_name) AS salesperson_name,
                e.email AS salesperson_email,
                e.status AS salesperson_status,
                
                -- Customer
                ss.customer_id,
                c.company_code,
                c.english_name AS customer_name,
                CONCAT(c.company_code, ' | ', c.english_name) AS customer_display,
                
                -- Product
                ss.product_id,
                p.pt_code,
                p.name AS product_name,
                p.package_size,
                CONCAT(p.pt_code, ' | ', p.name, ' (', COALESCE(p.package_size, ''), ')') AS product_display,
                
                -- Brand
                p.brand_id,
                b.brand_name AS brand,
                
                -- Split
                ss.split_percentage,
                CONCAT(FORMAT(ss.split_percentage, 0), '%') AS split_percentage_display,
                
                -- Period
                ss.valid_from AS effective_from,
                ss.valid_to AS effective_to,
                CONCAT(
                    COALESCE(DATE_FORMAT(ss.valid_from, '%Y-%m-%d'), 'Start'),
                    ' → ',
                    COALESCE(DATE_FORMAT(ss.valid_to, '%Y-%m-%d'), 'No End')
                ) AS effective_period,
                DATEDIFF(ss.valid_to, CURDATE()) AS days_until_expiry,
                
                -- Approval
                ss.is_approved,
                CASE 
                    WHEN ss.is_approved = 1 THEN 'Approved'
                    ELSE 'Pending'
                END AS approval_status,
                
                -- Approver
                ss.approved_by AS approved_by_employee_id,
                CONCAT(approver.first_name, ' ', approver.last_name) AS approved_by_name,
                
                -- Creator (stored as UUID string)
                ss.created_by AS created_by_uuid,
                ss.created_date,
                
                -- Modifier
                ss.modified_date,
                
                -- Version
                ss.version,
                
                -- Delete flag
                COALESCE(ss.delete_flag, 0) AS delete_flag,
                
                -- Validation: Calculate total split for this customer-product combo
                (
                    SELECT COALESCE(SUM(ss2.split_percentage), 0)
                    FROM sales_split_by_customer_product ss2
                    WHERE ss2.customer_id = ss.customer_id
                      AND ss2.product_id = ss.product_id
                      AND (ss2.delete_flag = 0 OR ss2.delete_flag IS NULL)
                      AND (ss2.valid_to >= CURDATE() OR ss2.valid_to IS NULL)
                ) AS total_split_percentage,
                
                -- Split status
                CASE 
                    WHEN (
                        SELECT COALESCE(SUM(ss2.split_percentage), 0)
                        FROM sales_split_by_customer_product ss2
                        WHERE ss2.customer_id = ss.customer_id
                          AND ss2.product_id = ss.product_id
                          AND (ss2.delete_flag = 0 OR ss2.delete_flag IS NULL)
                          AND (ss2.valid_to >= CURDATE() OR ss2.valid_to IS NULL)
                    ) = 100 THEN 'ok'
                    WHEN (
                        SELECT COALESCE(SUM(ss2.split_percentage), 0)
                        FROM sales_split_by_customer_product ss2
                        WHERE ss2.customer_id = ss.customer_id
                          AND ss2.product_id = ss.product_id
                          AND (ss2.delete_flag = 0 OR ss2.delete_flag IS NULL)
                          AND (ss2.valid_to >= CURDATE() OR ss2.valid_to IS NULL)
                    ) > 100 THEN 'over_100_split'
                    ELSE 'incomplete_split'
                END AS split_status
                
            FROM sales_split_by_customer_product ss
            LEFT JOIN employees e ON ss.sale_person_id = e.id
            LEFT JOIN companies c ON ss.customer_id = c.id
            LEFT JOIN products p ON ss.product_id = p.id
            LEFT JOIN brands b ON p.brand_id = b.id
            LEFT JOIN employees approver ON ss.approved_by = approver.id
            WHERE 1=1
        """
        
        params = {}
        
        # =====================================================================
        # SYSTEM FILTER: delete_flag
        # =====================================================================
        if not include_deleted:
            query += " AND (ss.delete_flag = 0 OR ss.delete_flag IS NULL)"
        
        # =====================================================================
        # PERIOD FILTER - Overlapping logic
        # =====================================================================
        if period_year:
            query += """
                AND (ss.valid_from <= :period_end OR ss.valid_from IS NULL)
                AND (ss.valid_to >= :period_start OR ss.valid_to IS NULL)
            """
            params['period_start'] = date(period_year, 1, 1)
            params['period_end'] = date(period_year, 12, 31)
        elif period_start or period_end:
            if period_start:
                query += " AND (ss.valid_to >= :period_start OR ss.valid_to IS NULL)"
                params['period_start'] = period_start
            if period_end:
                query += " AND (ss.valid_from <= :period_end OR ss.valid_from IS NULL)"
                params['period_end'] = period_end
        
        # =====================================================================
        # ENTITY FILTERS
        # =====================================================================
        if employee_ids:
            query += " AND ss.sale_person_id IN :employee_ids"
            params['employee_ids'] = tuple(employee_ids)
        
        if customer_ids:
            query += " AND ss.customer_id IN :customer_ids"
            params['customer_ids'] = tuple(customer_ids)
        
        if product_ids:
            query += " AND ss.product_id IN :product_ids"
            params['product_ids'] = tuple(product_ids)
        
        if brand_ids:
            query += """ AND ss.product_id IN (
                SELECT id FROM products WHERE brand_id IN :brand_ids AND delete_flag = 0
            )"""
            params['brand_ids'] = tuple(brand_ids)
        
        # =====================================================================
        # RULE ATTRIBUTE FILTERS
        # =====================================================================
        if status_filter and status_filter != 'all':
            # Filter by computed split status using HAVING or subquery
            if status_filter == 'ok':
                query += """ AND (
                    SELECT COALESCE(SUM(ss2.split_percentage), 0)
                    FROM sales_split_by_customer_product ss2
                    WHERE ss2.customer_id = ss.customer_id
                      AND ss2.product_id = ss.product_id
                      AND (ss2.delete_flag = 0 OR ss2.delete_flag IS NULL)
                      AND (ss2.valid_to >= CURDATE() OR ss2.valid_to IS NULL)
                ) = 100"""
            elif status_filter == 'over_100_split':
                query += """ AND (
                    SELECT COALESCE(SUM(ss2.split_percentage), 0)
                    FROM sales_split_by_customer_product ss2
                    WHERE ss2.customer_id = ss.customer_id
                      AND ss2.product_id = ss.product_id
                      AND (ss2.delete_flag = 0 OR ss2.delete_flag IS NULL)
                      AND (ss2.valid_to >= CURDATE() OR ss2.valid_to IS NULL)
                ) > 100"""
            elif status_filter == 'incomplete_split':
                query += """ AND (
                    SELECT COALESCE(SUM(ss2.split_percentage), 0)
                    FROM sales_split_by_customer_product ss2
                    WHERE ss2.customer_id = ss.customer_id
                      AND ss2.product_id = ss.product_id
                      AND (ss2.delete_flag = 0 OR ss2.delete_flag IS NULL)
                      AND (ss2.valid_to >= CURDATE() OR ss2.valid_to IS NULL)
                ) < 100"""
        
        if approval_filter == 'approved':
            query += " AND ss.is_approved = 1"
        elif approval_filter == 'pending':
            query += " AND (ss.is_approved = 0 OR ss.is_approved IS NULL)"
        
        if split_min is not None:
            query += " AND ss.split_percentage >= :split_min"
            params['split_min'] = split_min
        
        if split_max is not None:
            query += " AND ss.split_percentage <= :split_max"
            params['split_max'] = split_max
        
        # =====================================================================
        # ORDERING & LIMIT
        # =====================================================================
        query += " ORDER BY salesperson_name, customer_name, product_name"
        
        if limit:
            query += f" LIMIT {limit}"
        
        return self._execute_query(query, params, "sales_split_data")
    
    def get_split_summary_stats(
        self,
        period_year: int = None,
        period_start: date = None,
        period_end: date = None,
        include_deleted: bool = False
    ) -> Dict:
        """
        Get summary statistics for split rules with period filter.
        
        Returns:
            Dict with counts: total, ok, incomplete, over_100, pending, expiring_soon
        """
        query = """
            SELECT 
                COUNT(*) as total_rules,
                SUM(CASE 
                    WHEN (
                        SELECT COALESCE(SUM(ss2.split_percentage), 0)
                        FROM sales_split_by_customer_product ss2
                        WHERE ss2.customer_id = ss.customer_id
                          AND ss2.product_id = ss.product_id
                          AND (ss2.delete_flag = 0 OR ss2.delete_flag IS NULL)
                          AND (ss2.valid_to >= CURDATE() OR ss2.valid_to IS NULL)
                    ) = 100 THEN 1 ELSE 0 
                END) as ok_count,
                SUM(CASE 
                    WHEN (
                        SELECT COALESCE(SUM(ss2.split_percentage), 0)
                        FROM sales_split_by_customer_product ss2
                        WHERE ss2.customer_id = ss.customer_id
                          AND ss2.product_id = ss.product_id
                          AND (ss2.delete_flag = 0 OR ss2.delete_flag IS NULL)
                          AND (ss2.valid_to >= CURDATE() OR ss2.valid_to IS NULL)
                    ) < 100 THEN 1 ELSE 0 
                END) as incomplete_count,
                SUM(CASE 
                    WHEN (
                        SELECT COALESCE(SUM(ss2.split_percentage), 0)
                        FROM sales_split_by_customer_product ss2
                        WHERE ss2.customer_id = ss.customer_id
                          AND ss2.product_id = ss.product_id
                          AND (ss2.delete_flag = 0 OR ss2.delete_flag IS NULL)
                          AND (ss2.valid_to >= CURDATE() OR ss2.valid_to IS NULL)
                    ) > 100 THEN 1 ELSE 0 
                END) as over_100_count,
                SUM(CASE WHEN ss.is_approved = 0 OR ss.is_approved IS NULL THEN 1 ELSE 0 END) as pending_count,
                SUM(CASE 
                    WHEN ss.valid_to BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 30 DAY) 
                    THEN 1 ELSE 0 
                END) as expiring_soon_count
            FROM sales_split_by_customer_product ss
            WHERE 1=1
        """
        
        params = {}
        
        if not include_deleted:
            query += " AND (ss.delete_flag = 0 OR ss.delete_flag IS NULL)"
        
        if period_year:
            query += """
                AND (ss.valid_from <= :period_end OR ss.valid_from IS NULL)
                AND (ss.valid_to >= :period_start OR ss.valid_to IS NULL)
            """
            params['period_start'] = date(period_year, 1, 1)
            params['period_end'] = date(period_year, 12, 31)
        elif period_start or period_end:
            if period_start:
                query += " AND (ss.valid_to >= :period_start OR ss.valid_to IS NULL)"
                params['period_start'] = period_start
            if period_end:
                query += " AND (ss.valid_from <= :period_end OR ss.valid_from IS NULL)"
                params['period_end'] = period_end
        
        df = self._execute_query(query, params, "split_summary_stats")
        
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
    
    def get_split_rule_years(self) -> List[int]:
        """Get list of years that have split rules."""
        query = """
            SELECT DISTINCT year FROM (
                SELECT YEAR(valid_from) as year
                FROM sales_split_by_customer_product
                WHERE (delete_flag = 0 OR delete_flag IS NULL)
                  AND valid_from IS NOT NULL
                
                UNION
                
                SELECT YEAR(valid_to) as year
                FROM sales_split_by_customer_product
                WHERE (delete_flag = 0 OR delete_flag IS NULL)
                  AND valid_to IS NOT NULL
            ) years
            WHERE year IS NOT NULL
            ORDER BY year DESC
        """
        
        df = self._execute_query(query, {}, "split_rule_years")
        
        if df.empty:
            return [date.today().year]
        
        years = df['year'].dropna().astype(int).tolist()
        
        current_year = date.today().year
        if current_year not in years:
            years.append(current_year)
        
        return sorted(set(years), reverse=True)
    
    # =========================================================================
    # SALES SPLIT RULES - CREATE
    # =========================================================================
    
    def create_split_rule(
        self,
        customer_id: int,
        product_id: int,
        sale_person_id: int,
        split_percentage: float,
        valid_from: date,
        valid_to: date = None,
        is_approved: bool = False
    ) -> Dict:
        """
        Create a new sales split rule.
        
        Returns:
            Dict with success, id, message
        """
        query = """
            INSERT INTO sales_split_by_customer_product (
                customer_id, product_id, sale_person_id, split_percentage,
                valid_from, valid_to, is_approved,
                created_by, created_date, version, delete_flag
            ) VALUES (
                :customer_id, :product_id, :sale_person_id, :split_percentage,
                :valid_from, :valid_to, :is_approved,
                :created_by, NOW(), 0, 0
            )
        """
        
        params = {
            'customer_id': customer_id,
            'product_id': product_id,
            'sale_person_id': sale_person_id,
            'split_percentage': split_percentage,
            'valid_from': valid_from,
            'valid_to': valid_to,
            'is_approved': 1 if is_approved else 0,
            'created_by': self.user_id
        }
        
        return self._execute_insert(query, params, "create_split_rule")
    
    # =========================================================================
    # SALES SPLIT RULES - UPDATE
    # =========================================================================
    
    def update_split_rule(
        self,
        rule_id: int,
        split_percentage: float = None,
        valid_from: date = None,
        valid_to: date = None,
        sale_person_id: int = None,
        is_approved: bool = None
    ) -> Dict:
        """
        Update an existing split rule.
        
        Returns:
            Dict with success, count, message
        """
        set_parts = ["modified_date = NOW()", "version = version + 1"]
        params = {'rule_id': rule_id}
        
        if split_percentage is not None:
            set_parts.append("split_percentage = :split_percentage")
            params['split_percentage'] = split_percentage
        
        if valid_from is not None:
            set_parts.append("valid_from = :valid_from")
            params['valid_from'] = valid_from
        
        if valid_to is not None:
            set_parts.append("valid_to = :valid_to")
            params['valid_to'] = valid_to
        
        if sale_person_id is not None:
            set_parts.append("sale_person_id = :sale_person_id")
            params['sale_person_id'] = sale_person_id
        
        if is_approved is not None:
            set_parts.append("is_approved = :is_approved")
            params['is_approved'] = 1 if is_approved else 0
        
        query = f"""
            UPDATE sales_split_by_customer_product
            SET {', '.join(set_parts)}
            WHERE id = :rule_id
        """
        
        return self._execute_update(query, params, "update_split_rule")
    
    # =========================================================================
    # SALES SPLIT RULES - DELETE
    # =========================================================================
    
    def delete_split_rule(self, rule_id: int) -> Dict:
        """
        Soft delete a split rule.
        
        Returns:
            Dict with success, count, message
        """
        query = """
            UPDATE sales_split_by_customer_product
            SET delete_flag = 1, modified_date = NOW(), version = version + 1
            WHERE id = :rule_id
        """
        
        return self._execute_update(query, {'rule_id': rule_id}, "delete_split_rule")
    
    # =========================================================================
    # SALES SPLIT RULES - VALIDATION
    # =========================================================================
    
    def validate_split_percentage(
        self,
        customer_id: int,
        product_id: int,
        new_percentage: float,
        exclude_rule_id: int = None
    ) -> Dict:
        """
        Validate that total split percentage won't exceed 100%.
        
        Returns:
            Dict with current_total, new_total, is_valid, remaining
        """
        query = """
            SELECT COALESCE(SUM(split_percentage), 0) as current_total
            FROM sales_split_by_customer_product
            WHERE customer_id = :customer_id
              AND product_id = :product_id
              AND (delete_flag = 0 OR delete_flag IS NULL)
              AND (valid_to >= CURDATE() OR valid_to IS NULL)
        """
        
        params = {'customer_id': customer_id, 'product_id': product_id}
        
        if exclude_rule_id:
            query += " AND id != :exclude_rule_id"
            params['exclude_rule_id'] = exclude_rule_id
        
        df = self._execute_query(query, params, "validate_split")
        current_total = float(df.iloc[0]['current_total']) if not df.empty else 0
        new_total = current_total + new_percentage
        
        return {
            'current_total': current_total,
            'new_total': new_total,
            'is_valid': new_total <= 100,
            'remaining': max(0, 100 - new_total)
        }
    
    # =========================================================================
    # KPI ASSIGNMENTS - READ
    # =========================================================================
    
    def get_kpi_assignments(
        self,
        year: int = None,
        employee_ids: List[int] = None,
        kpi_type_ids: List[int] = None
    ) -> pd.DataFrame:
        """
        Get KPI assignments for employees.
        
        Args:
            year: Filter by year
            employee_ids: Filter by employee IDs
            kpi_type_ids: Filter by KPI type IDs
            
        Returns:
            DataFrame with assignments
        """
        query = """
            SELECT 
                a.id AS assignment_id,
                a.employee_id,
                CONCAT(e.first_name, ' ', e.last_name) AS employee_name,
                e.email AS employee_email,
                e.status AS employee_status,
                a.kpi_type_id,
                kt.name AS kpi_name,
                kt.uom AS unit_of_measure,
                a.year,
                a.annual_target_value,
                FORMAT(a.annual_target_value, 0) AS annual_target_formatted,
                a.annual_target_value AS annual_target_value_numeric,
                a.weight,
                CONCAT(a.weight, '%') AS weight_display,
                a.weight AS weight_numeric,
                a.annual_target_value / 12 AS monthly_target_value,
                a.annual_target_value / 4 AS quarterly_target_value,
                a.notes,
                a.created_at,
                a.updated_at,
                a.created_by AS created_by_uuid,
                a.version
            FROM sales_employee_kpi_assignments a
            JOIN employees e ON a.employee_id = e.id
            JOIN kpi_types kt ON a.kpi_type_id = kt.id
            WHERE a.delete_flag = 0
              AND e.delete_flag = 0
              AND kt.delete_flag = 0
        """
        
        params = {}
        
        if year:
            query += " AND a.year = :year"
            params['year'] = year
        
        if employee_ids:
            query += " AND a.employee_id IN :employee_ids"
            params['employee_ids'] = tuple(employee_ids)
        
        if kpi_type_ids:
            query += " AND a.kpi_type_id IN :kpi_type_ids"
            params['kpi_type_ids'] = tuple(kpi_type_ids)
        
        query += " ORDER BY employee_name, kt.name"
        
        return self._execute_query(query, params, "kpi_assignments")
    
    def get_assignment_weight_summary(self, year: int) -> pd.DataFrame:
        """
        Get weight sum by employee for validation.
        
        Returns:
            DataFrame with employee_id, employee_name, total_weight
        """
        query = """
            SELECT 
                a.employee_id,
                CONCAT(e.first_name, ' ', e.last_name) AS employee_name,
                SUM(a.weight) AS total_weight,
                COUNT(*) AS kpi_count
            FROM sales_employee_kpi_assignments a
            JOIN employees e ON a.employee_id = e.id
            WHERE a.delete_flag = 0
              AND e.delete_flag = 0
              AND a.year = :year
            GROUP BY a.employee_id, employee_name
            ORDER BY employee_name
        """
        
        return self._execute_query(query, {'year': year}, "assignment_weight_summary")
    
    def get_assignment_issues_summary(self, year: int) -> Dict:
        """
        Get assignment issues summary for display in issues panel.
        
        Returns:
            Dict with no_assignment_count, weight_issues_count, and details
        """
        result = {
            'no_assignment_count': 0,
            'no_assignment_details': [],
            'weight_issues_count': 0,
            'weight_issues_details': []
        }
        
        # Active salespeople without assignments
        no_assign_query = """
            SELECT e.id, CONCAT(e.first_name, ' ', e.last_name) AS name, e.email
            FROM employees e
            WHERE e.delete_flag = 0
              AND e.status = 'ACTIVE'
              AND e.id NOT IN (
                  SELECT DISTINCT employee_id 
                  FROM sales_employee_kpi_assignments 
                  WHERE year = :year AND delete_flag = 0
              )
              AND e.id IN (
                  SELECT DISTINCT sale_person_id 
                  FROM sales_split_by_customer_product 
                  WHERE delete_flag = 0 AND (valid_to >= CURDATE() OR valid_to IS NULL)
              )
            ORDER BY name
        """
        no_assign_df = self._execute_query(no_assign_query, {'year': year}, "employees_without_assignment")
        
        if not no_assign_df.empty:
            result['no_assignment_count'] = len(no_assign_df)
            result['no_assignment_details'] = no_assign_df.to_dict('records')
        
        # Weight issues
        weight_query = """
            SELECT 
                a.employee_id,
                CONCAT(e.first_name, ' ', e.last_name) AS employee_name,
                SUM(a.weight) AS total_weight
            FROM sales_employee_kpi_assignments a
            JOIN employees e ON a.employee_id = e.id
            WHERE a.delete_flag = 0
              AND e.delete_flag = 0
              AND a.year = :year
            GROUP BY a.employee_id, employee_name
            HAVING total_weight != 100
            ORDER BY employee_name
        """
        weight_df = self._execute_query(weight_query, {'year': year}, "weight_issues")
        
        if not weight_df.empty:
            result['weight_issues_count'] = len(weight_df)
            result['weight_issues_details'] = weight_df.to_dict('records')
        
        return result
    
    def get_available_years(self) -> List[int]:
        """Get list of years that have assignments."""
        query = """
            SELECT DISTINCT year
            FROM sales_employee_kpi_assignments
            WHERE delete_flag = 0
            ORDER BY year DESC
        """
        
        df = self._execute_query(query, {}, "available_years")
        
        if df.empty:
            return [date.today().year]
        
        years = df['year'].tolist()
        current_year = date.today().year
        if current_year not in years:
            years.append(current_year)
        
        return sorted(set(years), reverse=True)
    
    # =========================================================================
    # KPI ASSIGNMENTS - CREATE
    # =========================================================================
    
    def create_assignment(
        self,
        employee_id: int,
        kpi_type_id: int,
        year: int,
        annual_target_value: int,
        weight: int,
        notes: str = None
    ) -> Dict:
        """
        Create a new KPI assignment.
        
        Returns:
            Dict with success, id, message
        """
        # Check for duplicate
        check_query = """
            SELECT id FROM sales_employee_kpi_assignments
            WHERE employee_id = :employee_id
              AND kpi_type_id = :kpi_type_id
              AND year = :year
              AND delete_flag = 0
        """
        existing = self._execute_query(check_query, {
            'employee_id': employee_id,
            'kpi_type_id': kpi_type_id,
            'year': year
        }, "check_duplicate")
        
        if not existing.empty:
            return {
                'success': False,
                'id': None,
                'message': 'Assignment already exists for this employee, KPI type, and year'
            }
        
        query = """
            INSERT INTO sales_employee_kpi_assignments (
                employee_id, kpi_type_id, year, annual_target_value, weight,
                notes, created_by, created_at, version, delete_flag
            ) VALUES (
                :employee_id, :kpi_type_id, :year, :annual_target_value, :weight,
                :notes, :created_by, NOW(), 0, 0
            )
        """
        
        params = {
            'employee_id': employee_id,
            'kpi_type_id': kpi_type_id,
            'year': year,
            'annual_target_value': annual_target_value,
            'weight': weight,
            'notes': notes,
            'created_by': self.user_id
        }
        
        return self._execute_insert(query, params, "create_assignment")
    
    # =========================================================================
    # KPI ASSIGNMENTS - UPDATE
    # =========================================================================
    
    def update_assignment(
        self,
        assignment_id: int,
        annual_target_value: int = None,
        weight: int = None,
        notes: str = None
    ) -> Dict:
        """
        Update an existing KPI assignment.
        
        Returns:
            Dict with success, count, message
        """
        set_parts = ["updated_at = NOW()", "version = version + 1"]
        params = {'assignment_id': assignment_id}
        
        if annual_target_value is not None:
            set_parts.append("annual_target_value = :annual_target_value")
            params['annual_target_value'] = annual_target_value
        
        if weight is not None:
            set_parts.append("weight = :weight")
            params['weight'] = weight
        
        if notes is not None:
            set_parts.append("notes = :notes")
            params['notes'] = notes
        
        query = f"""
            UPDATE sales_employee_kpi_assignments
            SET {', '.join(set_parts)}
            WHERE id = :assignment_id
        """
        
        return self._execute_update(query, params, "update_assignment")
    
    # =========================================================================
    # KPI ASSIGNMENTS - DELETE
    # =========================================================================
    
    def delete_assignment(self, assignment_id: int) -> Dict:
        """
        Soft delete a KPI assignment.
        
        Returns:
            Dict with success, count, message
        """
        query = """
            UPDATE sales_employee_kpi_assignments
            SET delete_flag = 1, updated_at = NOW(), version = version + 1
            WHERE id = :assignment_id
        """
        
        return self._execute_update(query, {'assignment_id': assignment_id}, "delete_assignment")
    
    # =========================================================================
    # KPI ASSIGNMENTS - VALIDATION
    # =========================================================================
    
    def validate_assignment_weight(
        self,
        employee_id: int,
        year: int,
        new_weight: int,
        exclude_assignment_id: int = None
    ) -> Dict:
        """
        Validate that total weight won't exceed 100%.
        
        Returns:
            Dict with current_total, new_total, is_valid
        """
        query = """
            SELECT COALESCE(SUM(weight), 0) as current_total
            FROM sales_employee_kpi_assignments
            WHERE employee_id = :employee_id
              AND year = :year
              AND delete_flag = 0
        """
        
        params = {'employee_id': employee_id, 'year': year}
        
        if exclude_assignment_id:
            query += " AND id != :exclude_assignment_id"
            params['exclude_assignment_id'] = exclude_assignment_id
        
        df = self._execute_query(query, params, "validate_weight")
        current_total = int(df.iloc[0]['current_total']) if not df.empty else 0
        new_total = current_total + new_weight
        
        return {
            'current_total': current_total,
            'new_total': new_total,
            'is_valid': new_total <= 100,
            'remaining': max(0, 100 - new_total)
        }
    
    # =========================================================================
    # SALESPEOPLE - READ
    # =========================================================================
    
    def get_salespeople(
        self,
        status_filter: str = None,
        include_inactive: bool = False
    ) -> pd.DataFrame:
        """
        Get list of salespeople (employees with sales splits).
        
        Args:
            status_filter: Filter by status ('ACTIVE', 'INACTIVE', 'TERMINATED', 'ON_LEAVE')
            include_inactive: If True, include inactive/terminated employees
            
        Returns:
            DataFrame with salespeople info
        """
        query = """
            SELECT 
                e.id AS employee_id,
                CONCAT(e.first_name, ' ', e.last_name) AS employee_name,
                e.email,
                e.phone,
                e.status,
                e.commencement_date,
                e.termination_date,
                
                -- Position info
                p.name AS position_name,
                t.name AS title_name,
                d.name AS department_name,
                
                -- Manager info
                CONCAT(m.first_name, ' ', m.last_name) AS manager_name,
                
                -- Stats
                (
                    SELECT COUNT(*) 
                    FROM sales_split_by_customer_product ss 
                    WHERE ss.sale_person_id = e.id 
                      AND (ss.delete_flag = 0 OR ss.delete_flag IS NULL)
                      AND (ss.valid_to >= CURDATE() OR ss.valid_to IS NULL)
                ) AS active_split_count,
                
                (
                    SELECT COUNT(*) 
                    FROM sales_employee_kpi_assignments a 
                    WHERE a.employee_id = e.id 
                      AND a.delete_flag = 0 
                      AND a.year = YEAR(CURDATE())
                ) AS current_year_kpi_count
                
            FROM employees e
            LEFT JOIN positions p ON e.position_id = p.id
            LEFT JOIN titles t ON e.title_id = t.id
            LEFT JOIN departments d ON e.department_id = d.id
            LEFT JOIN employees m ON e.manager_id = m.id
            WHERE e.delete_flag = 0
        """
        
        params = {}
        
        if status_filter:
            query += " AND e.status = :status_filter"
            params['status_filter'] = status_filter
        elif not include_inactive:
            query += " AND e.status = 'ACTIVE'"
        
        # Only show employees who have splits (are salespeople)
        query += """ AND e.id IN (
            SELECT DISTINCT sale_person_id FROM sales_split_by_customer_product
            WHERE delete_flag = 0 OR delete_flag IS NULL
        )"""
        
        query += " ORDER BY employee_name"
        
        return self._execute_query(query, params, "salespeople")
    
    def get_salespeople_for_dropdown(
        self,
        include_inactive: bool = False
    ) -> pd.DataFrame:
        """Get salespeople for dropdown selection."""
        query = """
            SELECT 
                e.id AS employee_id,
                CONCAT(e.first_name, ' ', e.last_name) AS employee_name,
                e.email,
                e.status
            FROM employees e
            WHERE e.delete_flag = 0
        """
        
        if not include_inactive:
            query += " AND e.status = 'ACTIVE'"
        
        query += " ORDER BY employee_name"
        
        return self._execute_query(query, {}, "salespeople_dropdown")
    
    # =========================================================================
    # LOOKUP DATA
    # =========================================================================
    
    def get_customers_for_dropdown(
        self,
        search: str = None,
        limit: int = 100
    ) -> pd.DataFrame:
        """Get customers for dropdown selection."""
        query = """
            SELECT 
                id AS customer_id,
                company_code,
                english_name AS customer_name,
                CONCAT(company_code, ' | ', english_name) AS display_name
            FROM companies
            WHERE delete_flag = 0
              AND is_customer = 1
        """
        
        params = {}
        
        if search:
            query += """ AND (
                company_code LIKE :search 
                OR english_name LIKE :search
                OR vietnamese_name LIKE :search
            )"""
            params['search'] = f"%{search}%"
        
        query += f" ORDER BY company_code LIMIT {limit}"
        
        return self._execute_query(query, params, "customers_dropdown")
    
    def get_products_for_dropdown(
        self,
        search: str = None,
        brand_id: int = None,
        limit: int = 100
    ) -> pd.DataFrame:
        """Get products for dropdown selection."""
        query = """
            SELECT 
                p.id AS product_id,
                p.pt_code,
                p.name AS product_name,
                p.package_size,
                b.brand_name,
                CONCAT(p.pt_code, ' | ', p.name, ' (', COALESCE(p.package_size, ''), ')') AS display_name
            FROM products p
            LEFT JOIN brands b ON p.brand_id = b.id
            WHERE p.delete_flag = 0
        """
        
        params = {}
        
        if search:
            query += """ AND (
                p.pt_code LIKE :search 
                OR p.name LIKE :search
            )"""
            params['search'] = f"%{search}%"
        
        if brand_id:
            query += " AND p.brand_id = :brand_id"
            params['brand_id'] = brand_id
        
        query += f" ORDER BY p.pt_code LIMIT {limit}"
        
        return self._execute_query(query, params, "products_dropdown")
    
    def get_brands_for_dropdown(self) -> pd.DataFrame:
        """Get brands for dropdown selection."""
        query = """
            SELECT 
                id AS brand_id,
                brand_name
            FROM brands
            WHERE delete_flag = 0
            ORDER BY brand_name
        """
        
        return self._execute_query(query, {}, "brands_dropdown")
    
    def get_kpi_types(self) -> pd.DataFrame:
        """Get KPI types for dropdown selection."""
        query = """
            SELECT 
                id AS kpi_type_id,
                name AS kpi_name,
                description,
                uom AS unit_of_measure,
                default_weight
            FROM kpi_types
            WHERE delete_flag = 0
            ORDER BY name
        """
        
        return self._execute_query(query, {}, "kpi_types")
    
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
    
    def _execute_insert(
        self,
        query: str,
        params: dict,
        operation_name: str = "insert"
    ) -> Dict:
        """Execute INSERT and return result with new ID."""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query), params)
                conn.commit()
                
                last_id_result = conn.execute(text("SELECT LAST_INSERT_ID() as id"))
                last_id = last_id_result.fetchone()[0]
                
                logger.info(f"{operation_name} successful, id={last_id}")
                return {
                    'success': True,
                    'id': last_id,
                    'message': f'{operation_name} completed successfully'
                }
        except Exception as e:
            logger.error(f"Error in {operation_name}: {e}")
            return {
                'success': False,
                'id': None,
                'message': str(e)
            }
    
    def _execute_update(
        self,
        query: str,
        params: dict,
        operation_name: str = "update"
    ) -> Dict:
        """Execute UPDATE/DELETE and return result."""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query), params)
                conn.commit()
                
                rows_affected = result.rowcount
                logger.info(f"{operation_name} successful, {rows_affected} rows affected")
                return {
                    'success': True,
                    'count': rows_affected,
                    'message': f'{operation_name} completed successfully'
                }
        except Exception as e:
            logger.error(f"Error in {operation_name}: {e}")
            return {
                'success': False,
                'count': 0,
                'message': str(e)
            }