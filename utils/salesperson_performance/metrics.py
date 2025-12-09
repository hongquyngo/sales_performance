# utils/salesperson_performance/metrics.py
"""
KPI Calculations for Salesperson Performance

Handles all metric calculations:
- Period aggregations (YTD/QTD/MTD)
- Target comparisons and achievement rates
- YoY growth calculations
- Complex KPI metrics (new customers/products/business)
- Data aggregations by salesperson/period
"""

import logging
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from .constants import MONTH_ORDER, QUARTER_MONTHS, KPI_TYPES

logger = logging.getLogger(__name__)


class SalespersonMetrics:
    """
    KPI calculations for salesperson performance.
    
    Usage:
        metrics = SalespersonMetrics(sales_df, targets_df)
        
        overview = metrics.calculate_overview_metrics('YTD', 2025)
        monthly = metrics.prepare_monthly_summary()
        by_salesperson = metrics.aggregate_by_salesperson()
    """
    
    def __init__(
        self, 
        sales_df: pd.DataFrame, 
        targets_df: pd.DataFrame = None
    ):
        """
        Initialize with data.
        
        Args:
            sales_df: Sales data from unified view
            targets_df: KPI targets (optional)
        """
        self.sales_df = sales_df
        self.targets_df = targets_df if targets_df is not None else pd.DataFrame()
    
    # =========================================================================
    # PERIOD DATE CALCULATIONS
    # =========================================================================
    
    @staticmethod
    def calculate_period_dates(
        period_type: str,
        year: int,
        custom_start: date = None,
        custom_end: date = None
    ) -> Tuple[date, date]:
        """
        Calculate start and end dates for a period type.
        
        Args:
            period_type: 'YTD', 'QTD', 'MTD', or 'Custom'
            year: Year for calculation
            custom_start: Custom start date (for 'Custom' period)
            custom_end: Custom end date (for 'Custom' period)
            
        Returns:
            Tuple of (start_date, end_date)
        """
        today = date.today()
        
        if period_type == 'YTD':
            start = date(year, 1, 1)
            end = min(today, date(year, 12, 31))
        
        elif period_type == 'QTD':
            current_quarter = (today.month - 1) // 3 + 1
            quarter_start_month = (current_quarter - 1) * 3 + 1
            start = date(year, quarter_start_month, 1)
            end = min(today, date(year, 12, 31))
        
        elif period_type == 'MTD':
            start = date(year, today.month, 1)
            end = today
        
        elif period_type == 'Custom' and custom_start and custom_end:
            start = custom_start
            end = custom_end
        
        else:
            # Default to YTD
            start = date(year, 1, 1)
            end = min(today, date(year, 12, 31))
        
        return start, end
    
    @staticmethod
    def get_elapsed_months(year: int, as_of_date: date = None) -> int:
        """Get number of elapsed months in year as of given date."""
        if as_of_date is None:
            as_of_date = date.today()
        
        if as_of_date.year == year:
            return as_of_date.month
        elif as_of_date.year > year:
            return 12
        else:
            return 0
    
    # =========================================================================
    # OVERVIEW METRICS
    # =========================================================================
    
    def calculate_overview_metrics(
        self,
        period_type: str = 'YTD',
        year: int = None
    ) -> Dict:
        """
        Calculate overview KPIs for display in metric cards.
        
        Args:
            period_type: Period type for target proration
            year: Year for target lookup
            
        Returns:
            Dict with all overview metrics
        """
        if year is None:
            year = datetime.now().year
        
        df = self.sales_df
        
        if df.empty:
            return self._get_empty_metrics()
        
        # === Basic Counts ===
        total_customers = df['customer_id'].nunique()
        total_invoices = df['inv_number'].nunique()
        total_orders = df['oc_number'].nunique()
        
        # === Financial Metrics ===
        total_revenue = df['sales_by_split_usd'].sum()
        total_gp = df['gross_profit_by_split_usd'].sum()
        total_gp1 = df['gp1_by_split_usd'].sum()
        total_commission = df['allocated_broker_commission_usd'].sum()
        
        # === Percentages ===
        gp_percent = (total_gp / total_revenue * 100) if total_revenue else 0
        gp1_percent = (total_gp1 / total_revenue * 100) if total_revenue else 0
        
        # === Target Comparison ===
        revenue_target = self._get_prorated_target('revenue', period_type, year)
        gp_target = self._get_prorated_target('gross_profit', period_type, year)
        
        revenue_achievement = (total_revenue / revenue_target * 100) if revenue_target else None
        gp_achievement = (total_gp / gp_target * 100) if gp_target else None
        
        return {
            # Counts
            'total_customers': total_customers,
            'total_invoices': total_invoices,
            'total_orders': total_orders,
            
            # Financial
            'total_revenue': total_revenue,
            'total_gp': total_gp,
            'total_gp1': total_gp1,
            'total_commission': total_commission,
            
            # Percentages
            'gp_percent': round(gp_percent, 2),
            'gp1_percent': round(gp1_percent, 2),
            
            # Targets
            'revenue_target': revenue_target,
            'gp_target': gp_target,
            'revenue_achievement': round(revenue_achievement, 1) if revenue_achievement else None,
            'gp_achievement': round(gp_achievement, 1) if gp_achievement else None,
        }
    
    def _get_empty_metrics(self) -> Dict:
        """Return empty metrics dict."""
        return {
            'total_customers': 0,
            'total_invoices': 0,
            'total_orders': 0,
            'total_revenue': 0,
            'total_gp': 0,
            'total_gp1': 0,
            'total_commission': 0,
            'gp_percent': 0,
            'gp1_percent': 0,
            'revenue_target': None,
            'gp_target': None,
            'revenue_achievement': None,
            'gp_achievement': None,
        }
    
    # =========================================================================
    # TARGET CALCULATIONS
    # =========================================================================
    
    def _get_prorated_target(
        self,
        kpi_name: str,
        period_type: str,
        year: int
    ) -> Optional[float]:
        """
        Get prorated target based on period type.
        
        Proration logic:
        - YTD: annual × (elapsed_months / 12)
        - QTD: annual / 4
        - MTD: annual / 12
        - Custom: annual × (days_in_period / 365)
        """
        if self.targets_df.empty:
            return None
        
        # Filter for this KPI
        kpi_rows = self.targets_df[
            self.targets_df['kpi_name'].str.lower() == kpi_name.lower()
        ]
        
        if kpi_rows.empty:
            return None
        
        # Sum annual targets across all filtered salespeople
        annual_target = kpi_rows['annual_target_value_numeric'].sum()
        
        if annual_target <= 0:
            return None
        
        # Prorate based on period
        if period_type == 'YTD':
            elapsed_months = self.get_elapsed_months(year)
            return annual_target * elapsed_months / 12
        
        elif period_type == 'QTD':
            return annual_target / 4
        
        elif period_type == 'MTD':
            return annual_target / 12
        
        else:
            # For custom, return full annual
            return annual_target
    
    def get_target_for_salesperson(
        self,
        employee_id: int,
        kpi_name: str,
        period_type: str = 'YTD',
        year: int = None
    ) -> Optional[float]:
        """Get prorated target for a specific salesperson."""
        if self.targets_df.empty:
            return None
        
        if year is None:
            year = datetime.now().year
        
        row = self.targets_df[
            (self.targets_df['employee_id'] == employee_id) &
            (self.targets_df['kpi_name'].str.lower() == kpi_name.lower())
        ]
        
        if row.empty:
            return None
        
        annual_target = float(row['annual_target_value_numeric'].iloc[0])
        
        if period_type == 'YTD':
            elapsed_months = self.get_elapsed_months(year)
            return annual_target * elapsed_months / 12
        elif period_type == 'QTD':
            return annual_target / 4
        elif period_type == 'MTD':
            return annual_target / 12
        else:
            return annual_target
    
    # =========================================================================
    # COMPLEX KPI METRICS
    # =========================================================================
    
    def calculate_complex_kpis(
        self,
        new_customers_df: pd.DataFrame,
        new_products_df: pd.DataFrame,
        new_business_df: pd.DataFrame
    ) -> Dict:
        """
        Calculate complex KPIs with proportional split counting.
        
        Args:
            new_customers_df: New customers data
            new_products_df: New products data
            new_business_df: New business revenue data
            
        Returns:
            Dict with complex KPI metrics
        """
        # New customers: count × split_rate / 100 (proportional)
        if not new_customers_df.empty:
            new_customer_count = new_customers_df['split_rate_percent'].sum() / 100
        else:
            new_customer_count = 0
        
        # New products: count × split_rate / 100 (proportional)
        if not new_products_df.empty:
            new_product_count = new_products_df['split_rate_percent'].sum() / 100
        else:
            new_product_count = 0
        
        # New business revenue (already split in query)
        if not new_business_df.empty:
            new_business_revenue = new_business_df['new_business_revenue'].sum()
            new_business_gp = new_business_df['new_business_gp'].sum() if 'new_business_gp' in new_business_df.columns else 0
        else:
            new_business_revenue = 0
            new_business_gp = 0
        
        # Get targets for complex KPIs
        customer_target = self._get_kpi_target_value('num_new_customers')
        product_target = self._get_kpi_target_value('num_new_products')
        business_target = self._get_kpi_target_value('new_business_revenue')
        
        return {
            'new_customer_count': round(new_customer_count, 1),
            'new_product_count': round(new_product_count, 1),
            'new_business_revenue': new_business_revenue,
            'new_business_gp': new_business_gp,
            
            'new_customer_target': customer_target,
            'new_product_target': product_target,
            'new_business_target': business_target,
            
            'new_customer_achievement': self._calc_achievement(new_customer_count, customer_target),
            'new_product_achievement': self._calc_achievement(new_product_count, product_target),
            'new_business_achievement': self._calc_achievement(new_business_revenue, business_target),
        }
    
    def _get_kpi_target_value(self, kpi_name: str) -> Optional[float]:
        """Get total target value for a KPI (sum across all salespeople)."""
        if self.targets_df.empty:
            return None
        
        rows = self.targets_df[
            self.targets_df['kpi_name'].str.lower() == kpi_name.lower()
        ]
        
        if rows.empty:
            return None
        
        return rows['annual_target_value_numeric'].sum()
    
    @staticmethod
    def _calc_achievement(actual: float, target: Optional[float]) -> Optional[float]:
        """Calculate achievement percentage."""
        if target is None or target <= 0:
            return None
        return round(actual / target * 100, 1)
    
    # =========================================================================
    # YoY COMPARISON
    # =========================================================================
    
    def calculate_yoy_comparison(
        self,
        current_metrics: Dict,
        previous_metrics: Dict
    ) -> Dict:
        """
        Calculate YoY growth for all metrics.
        
        Args:
            current_metrics: Current period metrics
            previous_metrics: Same period last year metrics
            
        Returns:
            Dict with YoY growth percentages
        """
        yoy = {}
        
        compare_keys = [
            'total_revenue', 'total_gp', 'total_gp1',
            'total_customers', 'total_invoices', 'total_orders'
        ]
        
        for key in compare_keys:
            current = current_metrics.get(key, 0) or 0
            previous = previous_metrics.get(key, 0) or 0
            
            if previous > 0:
                growth = (current - previous) / previous * 100
                yoy[f'{key}_yoy'] = round(growth, 1)
                yoy[f'{key}_yoy_abs'] = current - previous
            else:
                yoy[f'{key}_yoy'] = None
                yoy[f'{key}_yoy_abs'] = current
        
        return yoy
    
    # =========================================================================
    # MONTHLY SUMMARY
    # =========================================================================
    
    def prepare_monthly_summary(self) -> pd.DataFrame:
        """
        Prepare monthly summary data for charts.
        
        Returns:
            DataFrame with monthly aggregations including cumulative values.
        """
        df = self.sales_df
        
        if df.empty:
            return self._get_empty_monthly_summary()
        
        # Ensure invoice_month is available
        if 'invoice_month' not in df.columns:
            df = df.copy()
            df['invoice_month'] = pd.to_datetime(df['inv_date']).dt.strftime('%b')
        
        # Group by month
        monthly = df.groupby('invoice_month').agg({
            'sales_by_split_usd': 'sum',
            'gross_profit_by_split_usd': 'sum',
            'gp1_by_split_usd': 'sum',
            'customer_id': pd.Series.nunique,
            'inv_number': pd.Series.nunique
        }).reset_index()
        
        monthly.columns = [
            'invoice_month', 'revenue', 'gross_profit', 'gp1',
            'customer_count', 'invoice_count'
        ]
        
        # Calculate GP%
        monthly['gp_percent'] = monthly.apply(
            lambda row: (row['gross_profit'] / row['revenue'] * 100) 
            if row['revenue'] > 0 else 0,
            axis=1
        )
        
        # Ensure all months present
        all_months = pd.DataFrame({'invoice_month': MONTH_ORDER})
        monthly = all_months.merge(monthly, on='invoice_month', how='left').fillna(0)
        
        # Calculate cumulative values
        monthly['cumulative_revenue'] = monthly['revenue'].cumsum()
        monthly['cumulative_gp'] = monthly['gross_profit'].cumsum()
        monthly['cumulative_gp1'] = monthly['gp1'].cumsum()
        
        return monthly
    
    def _get_empty_monthly_summary(self) -> pd.DataFrame:
        """Return empty monthly summary with all months."""
        return pd.DataFrame({
            'invoice_month': MONTH_ORDER,
            'revenue': [0] * 12,
            'gross_profit': [0] * 12,
            'gp1': [0] * 12,
            'customer_count': [0] * 12,
            'invoice_count': [0] * 12,
            'gp_percent': [0] * 12,
            'cumulative_revenue': [0] * 12,
            'cumulative_gp': [0] * 12,
            'cumulative_gp1': [0] * 12,
        })
    
    # =========================================================================
    # AGGREGATE BY SALESPERSON
    # =========================================================================
    
    def aggregate_by_salesperson(self) -> pd.DataFrame:
        """
        Aggregate metrics by salesperson for detail table.
        
        Returns:
            DataFrame with one row per salesperson.
        """
        df = self.sales_df
        
        if df.empty:
            return pd.DataFrame()
        
        # Group by salesperson
        summary = df.groupby(['sales_id', 'sales_name', 'sales_email']).agg({
            'sales_by_split_usd': 'sum',
            'gross_profit_by_split_usd': 'sum',
            'gp1_by_split_usd': 'sum',
            'allocated_broker_commission_usd': 'sum',
            'customer_id': pd.Series.nunique,
            'inv_number': pd.Series.nunique,
            'oc_number': pd.Series.nunique,
        }).reset_index()
        
        summary.columns = [
            'sales_id', 'sales_name', 'sales_email',
            'revenue', 'gross_profit', 'gp1', 'commission',
            'customers', 'invoices', 'orders'
        ]
        
        # Calculate percentages
        summary['gp_percent'] = (summary['gross_profit'] / summary['revenue'] * 100).round(2)
        summary['gp_percent'] = summary['gp_percent'].fillna(0)
        
        # Add targets and achievement if available
        if not self.targets_df.empty:
            summary = self._add_targets_to_summary(summary)
        
        # Sort by revenue descending
        summary = summary.sort_values('revenue', ascending=False)
        
        return summary
    
    def _add_targets_to_summary(self, summary: pd.DataFrame) -> pd.DataFrame:
        """Add target and achievement columns to salesperson summary."""
        # Get revenue targets
        revenue_targets = self.targets_df[
            self.targets_df['kpi_name'].str.lower() == 'revenue'
        ][['employee_id', 'annual_target_value_numeric']].copy()
        
        revenue_targets.columns = ['sales_id', 'revenue_target_annual']
        
        # Get GP targets
        gp_targets = self.targets_df[
            self.targets_df['kpi_name'].str.lower() == 'gross_profit'
        ][['employee_id', 'annual_target_value_numeric']].copy()
        
        gp_targets.columns = ['sales_id', 'gp_target_annual']
        
        # Merge
        summary = summary.merge(revenue_targets, on='sales_id', how='left')
        summary = summary.merge(gp_targets, on='sales_id', how='left')
        
        # Calculate prorated targets (YTD)
        elapsed_months = self.get_elapsed_months(datetime.now().year)
        prorate_factor = elapsed_months / 12
        
        summary['revenue_target'] = summary['revenue_target_annual'] * prorate_factor
        summary['gp_target'] = summary['gp_target_annual'] * prorate_factor
        
        # Calculate achievement
        summary['revenue_achievement'] = (
            summary['revenue'] / summary['revenue_target'] * 100
        ).round(1)
        summary['gp_achievement'] = (
            summary['gross_profit'] / summary['gp_target'] * 100
        ).round(1)
        
        # Handle NaN
        summary['revenue_achievement'] = summary['revenue_achievement'].fillna(0)
        summary['gp_achievement'] = summary['gp_achievement'].fillna(0)
        
        return summary
    
    # =========================================================================
    # TOP N ANALYSIS (Pareto)
    # =========================================================================
    
    def prepare_top_customers_by_gp(
        self,
        top_percent: float = 0.8
    ) -> pd.DataFrame:
        """
        Prepare top customers contributing to specified % of GP.
        Uses cumulative percentage cutoff (Pareto analysis).
        
        Args:
            top_percent: Cumulative cutoff (e.g., 0.8 for top 80%)
            
        Returns:
            DataFrame with top customers and cumulative %
        """
        df = self.sales_df
        
        if df.empty:
            return pd.DataFrame()
        
        # Group by customer
        customer_gp = df.groupby(['customer_id', 'customer']).agg({
            'gross_profit_by_split_usd': 'sum',
            'sales_by_split_usd': 'sum'
        }).reset_index()
        
        customer_gp.columns = ['customer_id', 'customer', 'gross_profit', 'revenue']
        
        # Sort and calculate cumulative
        customer_gp = customer_gp.sort_values('gross_profit', ascending=False)
        total_gp = customer_gp['gross_profit'].sum()
        
        customer_gp['cumulative_gp'] = customer_gp['gross_profit'].cumsum()
        customer_gp['cumulative_percent'] = customer_gp['cumulative_gp'] / total_gp
        customer_gp['gp_percent_contribution'] = customer_gp['gross_profit'] / total_gp * 100
        
        # Find cutoff index (include first row that exceeds threshold)
        exceed_mask = customer_gp['cumulative_percent'] > top_percent
        
        if exceed_mask.any():
            first_exceed_idx = exceed_mask.idxmax()
            top_customers = customer_gp.loc[:first_exceed_idx].copy()
        else:
            top_customers = customer_gp.copy()
        
        return top_customers
    
    def prepare_top_brands_by_gp(
        self,
        top_percent: float = 0.8
    ) -> pd.DataFrame:
        """
        Prepare top brands contributing to specified % of GP.
        """
        df = self.sales_df
        
        if df.empty:
            return pd.DataFrame()
        
        # Group by brand
        brand_gp = df.groupby('brand').agg({
            'gross_profit_by_split_usd': 'sum',
            'sales_by_split_usd': 'sum'
        }).reset_index()
        
        brand_gp.columns = ['brand', 'gross_profit', 'revenue']
        
        # Sort and calculate cumulative
        brand_gp = brand_gp.sort_values('gross_profit', ascending=False)
        total_gp = brand_gp['gross_profit'].sum()
        
        brand_gp['cumulative_gp'] = brand_gp['gross_profit'].cumsum()
        brand_gp['cumulative_percent'] = brand_gp['cumulative_gp'] / total_gp
        brand_gp['gp_percent_contribution'] = brand_gp['gross_profit'] / total_gp * 100
        
        # Find cutoff
        exceed_mask = brand_gp['cumulative_percent'] > top_percent
        
        if exceed_mask.any():
            first_exceed_idx = exceed_mask.idxmax()
            top_brands = brand_gp.loc[:first_exceed_idx].copy()
        else:
            top_brands = brand_gp.copy()
        
        return top_brands
