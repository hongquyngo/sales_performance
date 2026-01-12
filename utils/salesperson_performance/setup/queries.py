# utils/salesperson_performance/setup/queries.py
"""
SQL Queries for Setup Tab - Salesperson Performance

Full CRUD operations for:
- Sales Split Rules (sales_split_by_customer_product)
- KPI Assignments (sales_employee_kpi_assignments)
- Salespeople Management


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
    # SALES SPLIT RULES - READ (v1.1.0 - Using View + Audit Trail)
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
        
        # Audit filters (v1.1.0 - NEW, v1.4.2 - FIXED)
        created_by_employee_id: int = None,    # Filter by creator employee ID (via keycloak_id)
        approved_by_employee_id: int = None,   # Filter by approver employee ID
        created_date_from: date = None,       # Created date range start
        created_date_to: date = None,         # Created date range end
        modified_date_from: date = None,      # Modified date range start
        modified_date_to: date = None,        # Modified date range end
        
        # System filters
        include_deleted: bool = False,
        
        # Pagination
        limit: int = None
    ) -> pd.DataFrame:
        """
        Get Sales Split assignments with comprehensive filtering.
        
        v1.1.0 Changes:
        - Now uses sales_split_full_looker_view for better performance
        - Added audit trail filters (created_by, approved_by, date ranges)
        - Period filter uses OVERLAPPING logic
        
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
            
            created_by_employee_id: Filter by creator employee ID (joins via keycloak_id)
            approved_by_employee_id: Filter by approver employee ID (employees.id)
            created_date_from: Filter created_date >= this
            created_date_to: Filter created_date <= this
            modified_date_from: Filter modified_date >= this
            modified_date_to: Filter modified_date <= this
            
            include_deleted: If True, show deleted rules too
            
            limit: Limit number of results
            
        Returns:
            DataFrame with split assignments
        """
        # Use view for optimized query
        query = """
            SELECT 
                split_id,
                sale_person_id,
                salesperson_name,
                salesperson_email,
                salesperson_status,
                customer_id,
                company_code,
                customer_name,
                customer_display,
                product_id,
                pt_code,
                product_name,
                package_size,
                product_display,
                brand_id,
                brand,
                split_percentage,
                split_percentage_display,
                effective_from,
                effective_to,
                effective_period,
                days_until_expiry,
                period_status,
                is_approved,
                approval_status,
                approved_by_employee_id,
                approved_by_name,
                approved_by_email,
                created_by_raw,
                created_by_employee_id,
                created_by_keycloak_id,
                created_by_name,
                created_by_email,
                created_by_user_id,
                created_by_username,
                created_by_role,
                created_date,
                modified_date,
                version,
                delete_flag,
                total_split_percentage,
                total_split_percentage_all,
                split_status,
                existing_split_structure
            FROM sales_split_full_looker_view
            WHERE 1=1
        """
        
        params = {}
        
        # =====================================================================
        # NOTE: View already has WHERE ss.delete_flag = 0, so include_deleted
        # parameter has no effect when using the view. This is kept for API
        # compatibility but deleted records cannot be retrieved from view.
        # To show deleted records, would need direct table query (not implemented).
        # =====================================================================
        
        # =====================================================================
        # PERIOD FILTER - Overlapping logic
        # =====================================================================
        if period_year:
            query += """
                AND (effective_from <= :period_end OR effective_from IS NULL)
                AND (effective_to >= :period_start OR effective_to IS NULL)
            """
            params['period_start'] = date(period_year, 1, 1)
            params['period_end'] = date(period_year, 12, 31)
        elif period_start or period_end:
            if period_start:
                query += " AND (effective_to >= :period_start OR effective_to IS NULL)"
                params['period_start'] = period_start
            if period_end:
                query += " AND (effective_from <= :period_end OR effective_from IS NULL)"
                params['period_end'] = period_end
        
        # =====================================================================
        # ENTITY FILTERS
        # =====================================================================
        if employee_ids:
            query += " AND sale_person_id IN :employee_ids"
            params['employee_ids'] = tuple(employee_ids)
        
        if customer_ids:
            query += " AND customer_id IN :customer_ids"
            params['customer_ids'] = tuple(customer_ids)
        
        if product_ids:
            query += " AND product_id IN :product_ids"
            params['product_ids'] = tuple(product_ids)
        
        if brand_ids:
            query += " AND brand_id IN :brand_ids"
            params['brand_ids'] = tuple(brand_ids)
        
        # =====================================================================
        # RULE ATTRIBUTE FILTERS
        # =====================================================================
        if status_filter and status_filter != 'all':
            query += " AND split_status = :status_filter"
            params['status_filter'] = status_filter
        
        if approval_filter == 'approved':
            query += " AND is_approved = 1"
        elif approval_filter == 'pending':
            query += " AND (is_approved = 0 OR is_approved IS NULL)"
        
        if split_min is not None:
            query += " AND split_percentage >= :split_min"
            params['split_min'] = split_min
        
        if split_max is not None:
            query += " AND split_percentage <= :split_max"
            params['split_max'] = split_max
        
        # =====================================================================
        # AUDIT FILTERS (v1.1.0 - NEW, v1.4.2 - FIXED)
        # =====================================================================
        if created_by_employee_id:
            query += " AND created_by_employee_id = :created_by_employee_id"
            params['created_by_employee_id'] = created_by_employee_id
        
        if approved_by_employee_id:
            query += " AND approved_by_employee_id = :approved_by_employee_id"
            params['approved_by_employee_id'] = approved_by_employee_id
        
        if created_date_from:
            query += " AND DATE(created_date) >= :created_date_from"
            params['created_date_from'] = created_date_from
        
        if created_date_to:
            query += " AND DATE(created_date) <= :created_date_to"
            params['created_date_to'] = created_date_to
        
        if modified_date_from:
            query += " AND DATE(modified_date) >= :modified_date_from"
            params['modified_date_from'] = modified_date_from
        
        if modified_date_to:
            query += " AND DATE(modified_date) <= :modified_date_to"
            params['modified_date_to'] = modified_date_to
        
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
        include_deleted: bool = False,
        employee_ids: List[int] = None  # v1.2.0: Added for Setup tab sync
    ) -> Dict:
        """
        Get summary statistics for split rules with period filter.
        
        v1.1.0: Uses view for consistent status calculation.
        v1.2.0: Added employee_ids filter to sync metrics with data table.
        
        Returns:
            Dict with counts: total, ok, incomplete, over_100, pending, expiring_soon
        """
        query = """
            SELECT 
                COUNT(*) as total_rules,
                SUM(CASE WHEN split_status = 'ok' THEN 1 ELSE 0 END) as ok_count,
                SUM(CASE WHEN split_status = 'incomplete_split' THEN 1 ELSE 0 END) as incomplete_count,
                SUM(CASE WHEN split_status = 'over_100_split' THEN 1 ELSE 0 END) as over_100_count,
                SUM(CASE WHEN is_approved = 0 OR is_approved IS NULL THEN 1 ELSE 0 END) as pending_count,
                SUM(CASE WHEN period_status IN ('critical', 'warning') THEN 1 ELSE 0 END) as expiring_soon_count
            FROM sales_split_full_looker_view
            WHERE 1=1
        """
        
        params = {}
        
        if not include_deleted:
            query += " AND (delete_flag = 0 OR delete_flag IS NULL)"
        
        # v1.2.0: Employee filter for access control
        if employee_ids:
            query += " AND sale_person_id IN :employee_ids"
            params['employee_ids'] = tuple(employee_ids)
        
        if period_year:
            query += """
                AND (effective_from <= :period_end OR effective_from IS NULL)
                AND (effective_to >= :period_start OR effective_to IS NULL)
            """
            params['period_start'] = date(period_year, 1, 1)
            params['period_end'] = date(period_year, 12, 31)
        elif period_start or period_end:
            if period_start:
                query += " AND (effective_to >= :period_start OR effective_to IS NULL)"
                params['period_start'] = period_start
            if period_end:
                query += " AND (effective_from <= :period_end OR effective_from IS NULL)"
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
    # SALES SPLIT RULES - BULK APPROVAL (v1.5.0)
    # =========================================================================
    
    def bulk_approve_split_rules(
        self,
        rule_ids: List[int],
        approver_employee_id: int = None
    ) -> Dict:
        """
        Bulk approve multiple split rules in a single transaction.
        
        v1.5.0: New method for bulk approval workflow.
        
        Args:
            rule_ids: List of rule IDs to approve
            approver_employee_id: Employee ID of the approver (for audit)
            
        Returns:
            Dict with success, count, message
        """
        if not rule_ids:
            return {
                'success': False,
                'count': 0,
                'message': 'No rules selected'
            }
        
        # Build placeholders for IN clause
        placeholders = ','.join([f':id_{i}' for i in range(len(rule_ids))])
        params = {f'id_{i}': rid for i, rid in enumerate(rule_ids)}
        
        # Add approver info
        if approver_employee_id:
            params['approver_id'] = approver_employee_id
            approver_clause = ", approved_by = :approver_id"
        else:
            approver_clause = ""
        
        query = f"""
            UPDATE sales_split_by_customer_product
            SET is_approved = 1,
                modified_date = NOW(),
                version = version + 1
                {approver_clause}
            WHERE id IN ({placeholders})
              AND (delete_flag = 0 OR delete_flag IS NULL)
        """
        
        return self._execute_update(query, params, f"bulk_approve_{len(rule_ids)}_rules")
    
    def bulk_disapprove_split_rules(self, rule_ids: List[int]) -> Dict:
        """
        Bulk disapprove (reset to pending) multiple split rules.
        
        v1.5.0: New method for bulk disapproval workflow.
        
        Args:
            rule_ids: List of rule IDs to disapprove
            
        Returns:
            Dict with success, count, message
        """
        if not rule_ids:
            return {
                'success': False,
                'count': 0,
                'message': 'No rules selected'
            }
        
        # Build placeholders for IN clause
        placeholders = ','.join([f':id_{i}' for i in range(len(rule_ids))])
        params = {f'id_{i}': rid for i, rid in enumerate(rule_ids)}
        
        query = f"""
            UPDATE sales_split_by_customer_product
            SET is_approved = 0,
                approved_by = NULL,
                modified_date = NOW(),
                version = version + 1
            WHERE id IN ({placeholders})
              AND (delete_flag = 0 OR delete_flag IS NULL)
        """
        
        return self._execute_update(query, params, f"bulk_disapprove_{len(rule_ids)}_rules")
    
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
    
    def get_assignment_summary_by_type(self, year: int) -> pd.DataFrame:
        """
        Get assignment summary by KPI type for a year.
        
        NEW v1.1.0: Synced with KPI Center Performance pattern.
        
        Args:
            year: Target year
            
        Returns:
            DataFrame with kpi_name, kpi_type_id, unit_of_measure, employee_count, total_target
        """
        query = """
            SELECT 
                kt.name as kpi_name,
                kt.id as kpi_type_id,
                kt.uom as unit_of_measure,
                COUNT(DISTINCT a.employee_id) as employee_count,
                SUM(a.annual_target_value) as total_target
            FROM sales_employee_kpi_assignments a
            JOIN kpi_types kt ON a.kpi_type_id = kt.id
            WHERE a.year = :year 
              AND a.delete_flag = 0
              AND kt.delete_flag = 0
            GROUP BY kt.id, kt.name, kt.uom
            ORDER BY kt.name
        """
        
        return self._execute_query(query, {'year': year}, "assignment_summary_by_type")
    
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
    
    def get_assignment_issues_summary(
        self, 
        year: int,
        employee_ids: List[int] = None  # FIX v1.3.1: Filter by team scope
    ) -> Dict:
        """
        Get assignment issues summary for display in issues panel.
        
        FIX v1.3.1: Added employee_ids parameter to filter by team scope.
        
        Args:
            year: Year to check assignments
            employee_ids: Optional list of employee IDs to filter (team scope)
        
        Returns:
            Dict with no_assignment_count, weight_issues_count, total_assignments, and details
        """
        result = {
            'no_assignment_count': 0,
            'no_assignment_details': [],
            'weight_issues_count': 0,
            'weight_issues_details': [],
            'total_assignments': 0  # NEW: Track total count
        }
        
        # Build employee filter clause
        emp_filter = ""
        params = {'year': year}
        
        if employee_ids is not None and len(employee_ids) > 0:
            emp_ids_str = ','.join(str(id) for id in employee_ids)
            emp_filter = f"AND e.id IN ({emp_ids_str})"
        
        # Active salespeople without assignments
        no_assign_query = f"""
            SELECT e.id, CONCAT(e.first_name, ' ', e.last_name) AS name, e.email
            FROM employees e
            WHERE e.delete_flag = 0
              AND e.status = 'ACTIVE'
              {emp_filter}
              AND e.id NOT IN (
                  SELECT DISTINCT employee_id 
                  FROM sales_employee_kpi_assignments 
                  WHERE year = :year AND delete_flag = 0
              )
              AND e.id IN (
                  SELECT DISTINCT sale_person_id 
                  FROM sales_split_by_customer_product 
                  WHERE (delete_flag = 0 OR delete_flag IS NULL) 
                    AND (valid_to >= CURDATE() OR valid_to IS NULL)
              )
            ORDER BY name
        """
        no_assign_df = self._execute_query(no_assign_query, params, "employees_without_assignment")
        
        if not no_assign_df.empty:
            result['no_assignment_count'] = len(no_assign_df)
            result['no_assignment_details'] = no_assign_df.to_dict('records')
        
        # Weight issues - also filter by employee_ids
        weight_filter = ""
        if employee_ids is not None and len(employee_ids) > 0:
            emp_ids_str = ','.join(str(id) for id in employee_ids)
            weight_filter = f"AND a.employee_id IN ({emp_ids_str})"
        
        weight_query = f"""
            SELECT 
                a.employee_id,
                CONCAT(e.first_name, ' ', e.last_name) AS employee_name,
                SUM(a.weight) AS total_weight
            FROM sales_employee_kpi_assignments a
            JOIN employees e ON a.employee_id = e.id
            WHERE a.delete_flag = 0
              AND e.delete_flag = 0
              AND a.year = :year
              {weight_filter}
            GROUP BY a.employee_id, employee_name
            HAVING total_weight != 100
            ORDER BY employee_name
        """
        weight_df = self._execute_query(weight_query, params, "weight_issues")
        
        if not weight_df.empty:
            result['weight_issues_count'] = len(weight_df)
            result['weight_issues_details'] = weight_df.to_dict('records')
        
        # NEW: Get total assignments count (for Quick Stats)
        total_filter = ""
        if employee_ids is not None and len(employee_ids) > 0:
            emp_ids_str = ','.join(str(id) for id in employee_ids)
            total_filter = f"AND employee_id IN ({emp_ids_str})"
        
        total_query = f"""
            SELECT COUNT(*) as cnt 
            FROM sales_employee_kpi_assignments
            WHERE year = :year 
              AND (delete_flag = 0 OR delete_flag IS NULL)
              {total_filter}
        """
        total_df = self._execute_query(total_query, params, "total_assignments")
        if not total_df.empty:
            result['total_assignments'] = int(total_df.iloc[0]['cnt'])
        
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
    # EMPLOYEES FOR AUDIT FILTERS (v1.4.2 - FIXED)
    # =========================================================================
    
    def get_creators_for_dropdown(self) -> pd.DataFrame:
        """
        Get employees who have created split rules (for Created By filter).
        
        v1.4.2: FIXED - created_by stores keycloak_id, not user_id.
        This function joins via employees.keycloak_id.
        
        Returns:
            DataFrame with employee_id, employee_name, keycloak_id
        """
        query = """
            SELECT DISTINCT
                e.id AS employee_id,
                CONCAT(e.first_name, ' ', e.last_name) AS employee_name,
                e.email,
                e.keycloak_id
            FROM employees e
            WHERE e.delete_flag = 0
              AND e.keycloak_id IN (
                  SELECT DISTINCT created_by 
                  FROM sales_split_by_customer_product 
                  WHERE created_by IS NOT NULL
                    AND (delete_flag = 0 OR delete_flag IS NULL)
              )
            ORDER BY employee_name
        """
        
        return self._execute_query(query, {}, "creators_dropdown")
    
    def get_users_for_dropdown(self) -> pd.DataFrame:
        """
        Get users for audit filter dropdowns (Created By filter).
        
        NEW v1.1.0: For audit trail filters.
        DEPRECATED v1.4.2: Use get_creators_for_dropdown() instead for split rules.
        
        Returns:
            DataFrame with user_id, username, full_name
        """
        query = """
            SELECT 
                u.id AS user_id,
                u.username,
                COALESCE(
                    CONCAT(e.first_name, ' ', e.last_name),
                    u.username
                ) AS full_name,
                u.email,
                u.role
            FROM users u
            LEFT JOIN employees e ON u.employee_id = e.id
            WHERE u.is_active = 1
              AND (u.delete_flag = 0 OR u.delete_flag IS NULL)
            ORDER BY full_name
        """
        
        return self._execute_query(query, {}, "users_dropdown")
    
    def get_approvers_for_dropdown(self) -> pd.DataFrame:
        """
        Get employees who have approved rules (for Approved By filter).
        
        NEW v1.1.0: For audit trail filters.
        Note: In sales_split, approved_by is FK to employees.id, not users.id
        
        Returns:
            DataFrame with employee_id, employee_name
        """
        query = """
            SELECT DISTINCT
                e.id AS employee_id,
                CONCAT(e.first_name, ' ', e.last_name) AS employee_name,
                e.email
            FROM employees e
            WHERE e.delete_flag = 0
              AND e.id IN (
                  SELECT DISTINCT approved_by 
                  FROM sales_split_by_customer_product 
                  WHERE approved_by IS NOT NULL
              )
            ORDER BY employee_name
        """
        
        return self._execute_query(query, {}, "approvers_dropdown")
    
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
    
    def get_customers_with_splits(self, employee_ids: List[int] = None) -> pd.DataFrame:
        """
        Get customers that have split rules (for filter dropdown).
        
        v1.5.2: New method for multiselect filter.
        
        Args:
            employee_ids: Optional filter by salesperson scope
            
        Returns:
            DataFrame with customer_id, company_code, customer_name, display_name
        """
        query = """
            SELECT DISTINCT
                c.id AS customer_id,
                c.company_code,
                c.english_name AS customer_name,
                CONCAT(c.company_code, ' | ', c.english_name) AS display_name
            FROM companies c
            INNER JOIN sales_split_by_customer_product ss ON c.id = ss.customer_id
            WHERE c.delete_flag = 0
              AND (ss.delete_flag = 0 OR ss.delete_flag IS NULL)
        """
        
        params = {}
        
        if employee_ids:
            query += " AND ss.sale_person_id IN :employee_ids"
            params['employee_ids'] = tuple(employee_ids)
        
        query += " ORDER BY c.company_code"
        
        return self._execute_query(query, params, "customers_with_splits")
    
    def get_products_with_splits(self, employee_ids: List[int] = None) -> pd.DataFrame:
        """
        Get products that have split rules (for filter dropdown).
        
        v1.5.2: New method for multiselect filter.
        
        Args:
            employee_ids: Optional filter by salesperson scope
            
        Returns:
            DataFrame with product_id, pt_code, product_name, display_name
        """
        query = """
            SELECT DISTINCT
                p.id AS product_id,
                p.pt_code,
                p.name AS product_name,
                CONCAT(p.pt_code, ' | ', p.name) AS display_name
            FROM products p
            INNER JOIN sales_split_by_customer_product ss ON p.id = ss.product_id
            WHERE p.delete_flag = 0
              AND (ss.delete_flag = 0 OR ss.delete_flag IS NULL)
        """
        
        params = {}
        
        if employee_ids:
            query += " AND ss.sale_person_id IN :employee_ids"
            params['employee_ids'] = tuple(employee_ids)
        
        query += " ORDER BY p.pt_code"
        
        return self._execute_query(query, params, "products_with_splits")
    
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