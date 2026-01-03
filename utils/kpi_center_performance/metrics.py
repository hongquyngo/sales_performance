# utils/kpi_center_performance/metrics.py
"""
KPI Calculations for KPI Center Performance

"""

import logging
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from .constants import MONTH_ORDER

logger = logging.getLogger(__name__)


class KPICenterMetrics:
    """
    KPI calculations for KPI Center performance.
    
    Usage:
        metrics = KPICenterMetrics(sales_df, targets_df)
        
        overview = metrics.calculate_overview_metrics('YTD', 2025)
        monthly = metrics.prepare_monthly_summary()
        by_kpi_center = metrics.aggregate_by_kpi_center()
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
    # PERIOD CONTEXT ANALYSIS
    # =========================================================================
    
    @staticmethod
    def analyze_period_context(start_date: date, end_date: date) -> Dict:
        """
        Analyze the selected period relative to today.
        
        Determines if period is historical, current, or future for proper
        handling of backlog and forecast displays.
        """
        today = date.today()
        
        is_historical = end_date < today
        is_future = start_date > today
        is_current = not is_historical and not is_future
        
        days_until_end = (end_date - today).days
        
        if is_historical:
            period_status = 'historical'
            show_forecast = False
            forecast_message = "📅 Forecast not available for historical periods"
        elif is_future:
            period_status = 'future'
            show_forecast = True
            forecast_message = "📅 Future period - showing projected backlog only"
        else:
            period_status = 'current'
            show_forecast = True
            forecast_message = None
        
        return {
            'is_historical': is_historical,
            'is_current': is_current,
            'is_future': is_future,
            'today': today,
            'days_until_end': days_until_end,
            'period_status': period_status,
            'show_forecast': show_forecast,
            'forecast_message': forecast_message
        }
    
    # =========================================================================
    # OVERVIEW METRICS
    # =========================================================================
    
    def calculate_overview_metrics(
        self,
        period_type: str = 'YTD',
        year: int = None,
        start_date: date = None,
        end_date: date = None
    ) -> Dict:
        """
        Calculate overview KPI metrics.
        
        Returns dict with:
        - total_revenue, total_gp, total_gp1
        - total_customers, total_orders
        - gp_percent, gp1_percent
        - revenue_target, revenue_achievement (if targets available)
        - gp_target, gp_achievement (if targets available)
        """
        if self.sales_df.empty:
            return self._get_empty_overview()
        
        df = self.sales_df.copy()
        
        # Calculate totals
        total_revenue = df['sales_by_kpi_center_usd'].sum()
        total_gp = df['gross_profit_by_kpi_center_usd'].sum()
        total_gp1 = df['gp1_by_kpi_center_usd'].sum() if 'gp1_by_kpi_center_usd' in df.columns else 0
        total_customers = df['customer_id'].nunique()
        total_orders = df['inv_number'].nunique() if 'inv_number' in df.columns else 0
        
        # Calculate percentages
        gp_percent = (total_gp / total_revenue * 100) if total_revenue > 0 else 0
        gp1_percent = (total_gp1 / total_revenue * 100) if total_revenue > 0 else 0
        
        metrics = {
            'total_revenue': total_revenue,
            'total_gp': total_gp,
            'total_gp1': total_gp1,
            'total_customers': total_customers,
            'total_orders': total_orders,
            'gp_percent': round(gp_percent, 2),
            'gp1_percent': round(gp1_percent, 2),
        }
        
        # Add target-based metrics if targets available
        if not self.targets_df.empty:
            proration = self._calculate_proration(period_type, year, start_date, end_date)
            
            # Revenue target and achievement
            revenue_targets = self._get_target_for_kpi('revenue')
            if revenue_targets > 0:
                prorated_revenue_target = revenue_targets * proration
                
                # Get actual from KPI centers with revenue target
                kpi_centers_with_revenue_target = self._get_kpi_centers_with_target('revenue')
                if kpi_centers_with_revenue_target:
                    actual_revenue = df[df['kpi_center_id'].isin(kpi_centers_with_revenue_target)]['sales_by_kpi_center_usd'].sum()
                else:
                    actual_revenue = total_revenue
                
                metrics['revenue_target'] = prorated_revenue_target
                metrics['revenue_achievement'] = (actual_revenue / prorated_revenue_target * 100) if prorated_revenue_target > 0 else 0
            
            # GP target and achievement
            gp_targets = self._get_target_for_kpi('gross_profit')
            if gp_targets > 0:
                prorated_gp_target = gp_targets * proration
                
                kpi_centers_with_gp_target = self._get_kpi_centers_with_target('gross_profit')
                if kpi_centers_with_gp_target:
                    actual_gp = df[df['kpi_center_id'].isin(kpi_centers_with_gp_target)]['gross_profit_by_kpi_center_usd'].sum()
                else:
                    actual_gp = total_gp
                
                metrics['gp_target'] = prorated_gp_target
                metrics['gp_achievement'] = (actual_gp / prorated_gp_target * 100) if prorated_gp_target > 0 else 0
            
            # GP1 target and achievement
            gp1_targets = self._get_target_for_kpi('gross_profit_1')
            if gp1_targets > 0:
                prorated_gp1_target = gp1_targets * proration
                
                kpi_centers_with_gp1_target = self._get_kpi_centers_with_target('gross_profit_1')
                if kpi_centers_with_gp1_target:
                    actual_gp1 = df[df['kpi_center_id'].isin(kpi_centers_with_gp1_target)]['gp1_by_kpi_center_usd'].sum()
                else:
                    actual_gp1 = total_gp1
                
                metrics['gp1_target'] = prorated_gp1_target
                metrics['gp1_achievement'] = (actual_gp1 / prorated_gp1_target * 100) if prorated_gp1_target > 0 else 0
        
        return metrics
    
    def _get_empty_overview(self) -> Dict:
        """Return empty overview metrics."""
        return {
            'total_revenue': 0,
            'total_gp': 0,
            'total_gp1': 0,
            'total_customers': 0,
            'total_orders': 0,
            'gp_percent': 0,
            'gp1_percent': 0,
        }
    
    def _get_target_for_kpi(self, kpi_name: str) -> float:
        """Get sum of targets for a specific KPI type."""
        if self.targets_df.empty:
            return 0
        
        mask = self.targets_df['kpi_name'].str.lower() == kpi_name.lower()
        return self.targets_df[mask]['annual_target_value_numeric'].sum()
    
    def _get_kpi_centers_with_target(self, kpi_name: str) -> List[int]:
        """Get list of KPI Center IDs that have a specific KPI target."""
        if self.targets_df.empty:
            return []
        
        mask = self.targets_df['kpi_name'].str.lower() == kpi_name.lower()
        return self.targets_df[mask]['kpi_center_id'].unique().tolist()
    
    def _calculate_proration(
        self,
        period_type: str,
        year: int = None,
        start_date: date = None,
        end_date: date = None
    ) -> float:
        """
        Calculate proration factor for targets.
        
        Returns:
            Float between 0 and 1 representing portion of year
        """
        today = date.today()
        year = year or today.year
        
        if period_type == 'YTD':
            if year == today.year:
                days_in_year = 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365
                days_elapsed = (today - date(year, 1, 1)).days + 1
                return days_elapsed / days_in_year
            else:
                return 1.0
        
        elif period_type == 'QTD':
            current_quarter = (today.month - 1) // 3 + 1
            quarter_start = date(year, (current_quarter - 1) * 3 + 1, 1)
            days_in_quarter = (date(year, current_quarter * 3 + 1, 1) if current_quarter < 4 
                              else date(year + 1, 1, 1)) - quarter_start
            days_elapsed = (today - quarter_start).days + 1
            return (days_elapsed / days_in_quarter.days) * 0.25
        
        elif period_type == 'MTD':
            import calendar
            days_in_month = calendar.monthrange(year, today.month)[1]
            return today.day / days_in_month / 12
        
        elif period_type == 'Custom' and start_date and end_date:
            total_days = (end_date - start_date).days + 1
            days_in_year = 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365
            return total_days / days_in_year
        
        return 1.0
    
    # =========================================================================
    # YOY METRICS
    # =========================================================================
    
    def calculate_yoy_metrics(
        self,
        current_sales_df: pd.DataFrame,
        previous_sales_df: pd.DataFrame
    ) -> Dict:
        """
        Calculate Year-over-Year comparison metrics.
        
        Returns dict with YoY growth percentages.
        """
        def safe_sum(df, col):
            if df.empty or col not in df.columns:
                return 0
            return df[col].sum()
        
        def calc_growth(current, previous):
            if previous == 0:
                return None if current == 0 else 100.0
            return ((current - previous) / previous) * 100
        
        current_revenue = safe_sum(current_sales_df, 'sales_by_kpi_center_usd')
        previous_revenue = safe_sum(previous_sales_df, 'sales_by_kpi_center_usd')
        
        current_gp = safe_sum(current_sales_df, 'gross_profit_by_kpi_center_usd')
        previous_gp = safe_sum(previous_sales_df, 'gross_profit_by_kpi_center_usd')
        
        current_gp1 = safe_sum(current_sales_df, 'gp1_by_kpi_center_usd')
        previous_gp1 = safe_sum(previous_sales_df, 'gp1_by_kpi_center_usd')
        
        current_customers = current_sales_df['customer_id'].nunique() if not current_sales_df.empty else 0
        previous_customers = previous_sales_df['customer_id'].nunique() if not previous_sales_df.empty else 0
        
        return {
            'total_revenue_yoy': calc_growth(current_revenue, previous_revenue),
            'total_gp_yoy': calc_growth(current_gp, previous_gp),
            'total_gp1_yoy': calc_growth(current_gp1, previous_gp1),
            'total_customers_yoy': calc_growth(current_customers, previous_customers),
            
            'current_revenue': current_revenue,
            'previous_revenue': previous_revenue,
            'current_gp': current_gp,
            'previous_gp': previous_gp,
            'current_gp1': current_gp1,
            'previous_gp1': previous_gp1,
            'current_customers': current_customers,
            'previous_customers': previous_customers,
        }
    
    # =========================================================================
    # OVERALL KPI ACHIEVEMENT
    # =========================================================================
    
    def calculate_overall_kpi_achievement(
        self,
        period_type: str = 'YTD',
        year: int = None,
        start_date: date = None,
        end_date: date = None,
        complex_kpis_by_center: Dict = None  # NEW v3.3.1
    ) -> Dict:
        """
        Calculate weighted average KPI achievement across all assigned KPIs.
        
        UPDATED v3.3.1: Synced with Progress tab logic:
        - Aggregate targets & actuals by KPI type
        - Only include actuals from centers WITH that KPI target
        - Use target-proportion weights for currency KPIs
        - Include complex KPIs (new business, new customers, new products)
        
        Formula: Σ(KPI_Achievement × Derived_Weight) / Σ(Derived_Weights)
        """
        if self.targets_df.empty:
            return {'overall_achievement': None, 'kpi_count': 0}
        
        proration = self._calculate_proration(period_type, year, start_date, end_date)
        
        # KPI column mapping
        kpi_column_map = {
            'revenue': 'sales_by_kpi_center_usd',
            'gross_profit': 'gross_profit_by_kpi_center_usd',
            'gross_profit_1': 'gp1_by_kpi_center_usd',
            'gp1': 'gp1_by_kpi_center_usd',
        }
        
        # Currency vs count KPIs
        currency_kpis = ['revenue', 'gross_profit', 'gross_profit_1', 'gp1', 'new_business_revenue']
        
        # =========================================================
        # Step 1: Aggregate targets & actuals by KPI type
        # Only include actuals from centers WITH that KPI target
        # =========================================================
        kpi_aggregates = {}
        
        for kpi_name in self.targets_df['kpi_name'].unique():
            kpi_lower = kpi_name.lower() if kpi_name else ''
            
            # Get targets for this KPI
            kpi_targets = self.targets_df[self.targets_df['kpi_name'] == kpi_name]
            total_annual_target = kpi_targets['annual_target_value_numeric'].sum()
            
            if total_annual_target <= 0:
                continue
            
            # Get list of KPI Centers that have THIS KPI target
            centers_with_this_kpi = kpi_targets['kpi_center_id'].unique().tolist()
            
            # Prorated target
            total_prorated_target = total_annual_target * proration
            
            # Sum actuals ONLY from centers that have this KPI target
            total_actual = 0
            if kpi_lower in kpi_column_map:
                col = kpi_column_map[kpi_lower]
                if not self.sales_df.empty and col in self.sales_df.columns:
                    filtered_sales = self.sales_df[
                        self.sales_df['kpi_center_id'].isin(centers_with_this_kpi)
                    ]
                    total_actual = filtered_sales[col].sum() if not filtered_sales.empty else 0
            elif kpi_lower in ['new_business_revenue', 'num_new_customers', 'num_new_products']:
                # Sum complex KPIs ONLY from centers that have this KPI target
                if complex_kpis_by_center:
                    for center_id in centers_with_this_kpi:
                        if center_id in complex_kpis_by_center:
                            total_actual += complex_kpis_by_center[center_id].get(kpi_lower, 0)
            
            # Achievement
            achievement = (total_actual / total_prorated_target * 100) if total_prorated_target > 0 else 0
            
            kpi_aggregates[kpi_name] = {
                'kpi_name': kpi_name,
                'kpi_lower': kpi_lower,
                'annual_target': total_annual_target,
                'prorated_target': total_prorated_target,
                'actual': total_actual,
                'achievement': achievement,
                'is_currency': kpi_lower in currency_kpis,
                'centers_count': len(centers_with_this_kpi)
            }
        
        if not kpi_aggregates:
            return {'overall_achievement': None, 'kpi_count': 0}
        
        # =========================================================
        # Step 2: Derive weights from target proportion
        # Currency KPIs: weight = target / total_currency_targets × 80%
        # Count KPIs: equal split of 20%
        # =========================================================
        currency_kpi_data = {k: v for k, v in kpi_aggregates.items() if v['is_currency']}
        count_kpi_data = {k: v for k, v in kpi_aggregates.items() if not v['is_currency']}
        
        total_currency_target = sum(v['prorated_target'] for v in currency_kpi_data.values())
        
        # Calculate weighted achievement
        total_weighted_achievement = 0
        total_derived_weight = 0
        kpi_details = []
        
        # Process currency KPIs (weight = target proportion × 80% if count KPIs exist, else 100%)
        currency_weight_pool = 80 if count_kpi_data else 100
        for kpi_name, data in currency_kpi_data.items():
            if total_currency_target > 0:
                derived_weight = (data['prorated_target'] / total_currency_target) * currency_weight_pool
            else:
                derived_weight = currency_weight_pool / len(currency_kpi_data) if currency_kpi_data else 0
            
            total_weighted_achievement += data['achievement'] * derived_weight
            total_derived_weight += derived_weight
            kpi_details.append({
                'kpi_name': kpi_name,
                'achievement': data['achievement'],
                'weight': derived_weight,
                'is_currency': True
            })
        
        # Process count KPIs (equal split of 20%)
        if count_kpi_data:
            count_weight_pool = 20 if currency_kpi_data else 100
            per_count_weight = count_weight_pool / len(count_kpi_data)
            
            for kpi_name, data in count_kpi_data.items():
                total_weighted_achievement += data['achievement'] * per_count_weight
                total_derived_weight += per_count_weight
                kpi_details.append({
                    'kpi_name': kpi_name,
                    'achievement': data['achievement'],
                    'weight': per_count_weight,
                    'is_currency': False
                })
        
        # =========================================================
        # Step 3: Calculate overall
        # =========================================================
        if total_derived_weight > 0:
            overall = total_weighted_achievement / total_derived_weight
            return {
                'overall_achievement': round(overall, 1),
                'kpi_count': len(kpi_aggregates),
                'total_weight': total_derived_weight,
                'kpi_details': kpi_details,
                'calculation_method': 'target_proportion'  # NEW: For UI tooltip
            }
        
        return {'overall_achievement': None, 'kpi_count': 0}
    
    # NOTE: _get_individual_kpi_center_actual() REMOVED in v4.0.0 - never called
    
    # =========================================================================
    # PRORATED TARGET HELPER - NEW v3.1.0 (synced with Salesperson)
    # =========================================================================
    
    def _get_prorated_target(
        self,
        kpi_name: str,
        period_type: str,
        year: int = None,
        start_date: date = None,
        end_date: date = None
    ) -> Optional[float]:
        """
        Get prorated target for a specific KPI based on period type.
        
        NEW v3.1.0: Helper for KPI Progress tab (synced with Salesperson).
        
        Args:
            kpi_name: KPI name (e.g., 'revenue', 'gross_profit')
            period_type: 'YTD', 'QTD', 'MTD', or 'Custom'
            year: Target year
            start_date: Start date for Custom period
            end_date: End date for Custom period
            
        Returns:
            Prorated target value or None if no target exists
        """
        if self.targets_df.empty:
            return None
        
        # Get annual target for this KPI
        mask = self.targets_df['kpi_name'].str.lower() == kpi_name.lower()
        kpi_targets = self.targets_df[mask]
        
        if kpi_targets.empty:
            return None
        
        annual_target = kpi_targets['annual_target_value_numeric'].sum()
        
        if annual_target <= 0:
            return None
        
        # Calculate proration factor
        proration = self._calculate_proration(period_type, year, start_date, end_date)
        
        return annual_target * proration
    
    def get_kpi_progress_data(
        self,
        period_type: str,
        year: int,
        start_date: date = None,
        end_date: date = None,
        complex_kpis: Dict = None
    ) -> List[Dict]:
        """
        Get KPI progress data for all assigned KPIs.
        
        NEW v3.1.0: Used by KPI Progress tab (synced with Salesperson).
        
        Args:
            period_type: Period type for proration
            year: Target year
            start_date: Start date
            end_date: End date
            complex_kpis: Pre-calculated complex KPIs dict
            
        Returns:
            List of dicts with KPI progress data for each KPI type
        """
        if self.targets_df.empty:
            return []
        
        # Map KPI names to column names in sales_df
        kpi_column_map = {
            'revenue': 'sales_by_kpi_center_usd',
            'gross_profit': 'gross_profit_by_kpi_center_usd',
            'gross_profit_1': 'gp1_by_kpi_center_usd',
            'gp1': 'gp1_by_kpi_center_usd',
        }
        
        # Complex KPIs that need special handling
        complex_kpi_names = ['num_new_customers', 'num_new_products', 'new_business_revenue']
        
        # Display name mapping
        kpi_display_names = {
            'revenue': 'Revenue',
            'gross_profit': 'Gross Profit',
            'gross_profit_1': 'GP1',
            'gp1': 'GP1',
            'num_new_customers': 'New Customers',
            'num_new_products': 'New Products',
            'new_business_revenue': 'New Business Revenue',
        }
        
        # KPIs that should show currency format
        currency_kpis = ['revenue', 'gross_profit', 'gross_profit_1', 'gp1', 'new_business_revenue']
        
        kpi_progress = []
        
        for kpi_name in self.targets_df['kpi_name'].str.lower().unique():
            # Get KPI Centers who have this specific KPI target
            kpi_centers_with_target = self.targets_df[
                self.targets_df['kpi_name'].str.lower() == kpi_name
            ]['kpi_center_id'].unique().tolist()
            
            # Get total annual target
            kpi_target = self.targets_df[
                self.targets_df['kpi_name'].str.lower() == kpi_name
            ]['annual_target_value_numeric'].sum()
            
            if kpi_target <= 0:
                continue
            
            # Calculate actual value - ONLY from KPI Centers who have this KPI target
            actual = 0
            if kpi_name in kpi_column_map:
                col_name = kpi_column_map[kpi_name]
                if not self.sales_df.empty and col_name in self.sales_df.columns:
                    filtered_sales = self.sales_df[
                        self.sales_df['kpi_center_id'].isin(kpi_centers_with_target)
                    ]
                    actual = filtered_sales[col_name].sum() if not filtered_sales.empty else 0
            elif kpi_name in complex_kpi_names and complex_kpis:
                # Use pre-calculated complex KPIs
                if kpi_name == 'num_new_customers':
                    actual = complex_kpis.get('num_new_customers', 0)
                elif kpi_name == 'num_new_products':
                    actual = complex_kpis.get('num_new_products', 0)
                elif kpi_name == 'new_business_revenue':
                    actual = complex_kpis.get('new_business_revenue', 0)
            
            # Get display name
            display_name = kpi_display_names.get(kpi_name, kpi_name.replace('_', ' ').title())
            
            # Get prorated target
            prorated_target = self._get_prorated_target(
                kpi_name, period_type, year, start_date, end_date
            )
            if prorated_target is None or prorated_target <= 0:
                prorated_target = kpi_target  # Fallback to annual
            
            # Calculate achievement
            achievement = (actual / prorated_target * 100) if prorated_target > 0 else 0
            
            kpi_progress.append({
                'kpi_name': kpi_name,
                'display_name': display_name,
                'actual': actual,
                'annual_target': kpi_target,
                'prorated_target': prorated_target,
                'achievement': achievement,
                'is_currency': kpi_name in currency_kpis,
                'kpi_center_count': len(kpi_centers_with_target)
            })
        
        # Sort by display name for consistent ordering
        kpi_progress.sort(key=lambda x: x['display_name'])
        
        return kpi_progress
    
    # =========================================================================
    # HIERARCHY ROLLUP TARGETS - NEW v3.2.0
    # =========================================================================
    
    def calculate_rollup_targets(
        self,
        hierarchy_df: pd.DataFrame,
        queries_instance = None
    ) -> Dict[int, Dict]:
        """
        Calculate rolled-up targets for all KPI Centers.
        
        NEW v3.2.0: Used by My KPIs tab for hierarchy display.
        
        Logic:
        - Leaf nodes: Direct targets only
        - Parent nodes: Sum of all descendants' targets (+ own direct if any)
        
        Args:
            hierarchy_df: DataFrame with kpi_center_id, level, is_leaf
            queries_instance: KPICenterQueries instance for descendant lookup
            
        Returns:
            Dict[kpi_center_id] = {
                'targets': List[{kpi_name, annual, monthly, quarterly, unit, weight}],
                'source': 'Direct' | 'Rollup' | 'Mixed',
                'children_count': int,
                'children_names': List[str]
            }
        """
        if self.targets_df.empty or hierarchy_df.empty:
            return {}
        
        result = {}
        
        # KPI display names
        kpi_display_names = {
            'revenue': 'Revenue',
            'gross_profit': 'Gross Profit',
            'gross_profit_1': 'GP1',
            'gp1': 'GP1',
            'num_new_customers': 'Num New Customers',
            'num_new_products': 'Num New Products',
            'new_business_revenue': 'New Business Revenue',
        }
        
        # Icons for display
        kpi_icons = {
            'revenue': '💰',
            'gross_profit': '📈',
            'gross_profit_1': '📊',
            'gp1': '📊',
            'num_new_customers': '👥',
            'num_new_products': '📦',
            'new_business_revenue': '💼',
        }
        
        for _, row in hierarchy_df.iterrows():
            kpi_center_id = row['kpi_center_id']
            kpi_center_name = row['kpi_center_name']
            is_leaf = row.get('is_leaf', 1) == 1
            
            # Get direct targets for this center
            direct_targets = self.targets_df[
                self.targets_df['kpi_center_id'] == kpi_center_id
            ].copy()
            
            has_direct = not direct_targets.empty
            
            # Get descendant targets
            descendants_targets = pd.DataFrame()
            children_names = []
            
            if not is_leaf and queries_instance:
                descendants = queries_instance.get_all_descendants(kpi_center_id)
                if descendants:
                    descendants_targets = self.targets_df[
                        self.targets_df['kpi_center_id'].isin(descendants)
                    ].copy()
                    
                    # Get children names for display
                    children_with_targets = descendants_targets['kpi_center_name'].unique().tolist()
                    children_names = children_with_targets
            
            has_children = not descendants_targets.empty
            
            # Determine source
            if has_direct and has_children:
                source = 'Mixed'
            elif has_direct:
                source = 'Direct'
            elif has_children:
                source = 'Rollup'
            else:
                continue  # Skip centers with no targets at all
            
            # Merge targets: Direct + Sum(Children)
            all_targets = pd.concat([direct_targets, descendants_targets], ignore_index=True)
            
            # Aggregate by kpi_name
            merged_targets = []
            for kpi_name in all_targets['kpi_name'].unique():
                kpi_rows = all_targets[all_targets['kpi_name'] == kpi_name]
                
                # Sum numeric values
                annual = kpi_rows['annual_target_value_numeric'].sum() if 'annual_target_value_numeric' in kpi_rows.columns else 0
                
                # Monthly and quarterly might be strings, try to convert
                monthly = 0
                quarterly = 0
                if 'monthly_target_value' in kpi_rows.columns:
                    try:
                        monthly = pd.to_numeric(kpi_rows['monthly_target_value'], errors='coerce').sum()
                    except:
                        monthly = annual / 12
                if 'quarterly_target_value' in kpi_rows.columns:
                    try:
                        quarterly = pd.to_numeric(kpi_rows['quarterly_target_value'], errors='coerce').sum()
                    except:
                        quarterly = annual / 4
                
                # Get unit (should be same for all)
                unit = kpi_rows['unit_of_measure'].iloc[0] if 'unit_of_measure' in kpi_rows.columns else ''
                
                # Weight only applies to direct assignments
                weight = None
                if source == 'Direct' and 'weight_numeric' in kpi_rows.columns:
                    weight = kpi_rows['weight_numeric'].iloc[0]
                
                # Get display name and icon
                kpi_lower = kpi_name.lower() if kpi_name else ''
                display_name = kpi_display_names.get(kpi_lower, kpi_name.replace('_', ' ').title() if kpi_name else '')
                icon = kpi_icons.get(kpi_lower, '📋')
                
                merged_targets.append({
                    'kpi_name': kpi_name,
                    'display_name': f"{icon} {display_name}",
                    'annual_target': annual,
                    'monthly_target': monthly if not pd.isna(monthly) else annual / 12,
                    'quarterly_target': quarterly if not pd.isna(quarterly) else annual / 4,
                    'unit': unit,
                    'weight': weight,
                    'is_currency': kpi_lower in ['revenue', 'gross_profit', 'gross_profit_1', 'gp1', 'new_business_revenue']
                })
            
            # Sort by display name
            merged_targets.sort(key=lambda x: x['display_name'])
            
            result[kpi_center_id] = {
                'kpi_center_id': kpi_center_id,
                'kpi_center_name': kpi_center_name,
                'targets': merged_targets,
                'source': source,
                'children_count': len(children_names),
                'children_names': children_names,
                'level': row.get('level', 0),
                'is_leaf': is_leaf
            }
        
        return result
    
    # =========================================================================
    # PER-CENTER PROGRESS - NEW v3.2.0
    # =========================================================================
    
    def calculate_per_center_progress(
        self,
        hierarchy_df: pd.DataFrame,
        queries_instance,
        period_type: str,
        year: int,
        start_date: date = None,
        end_date: date = None,
        complex_kpis_by_center: Dict = None
    ) -> Dict[int, Dict]:
        """
        Calculate KPI progress for each KPI Center.
        
        NEW v3.2.0: Used by Progress tab for per-center breakdown.
        
        Logic:
        - Leaf nodes: Calculate achievement from direct actuals vs targets
        - Parent nodes: Weighted average of children's overall achievements
        
        Args:
            hierarchy_df: DataFrame with kpi_center_id, level, is_leaf
            queries_instance: KPICenterQueries for hierarchy lookups
            period_type: For target proration
            year: Target year
            start_date, end_date: For Custom period
            complex_kpis_by_center: Dict[kpi_center_id] = {kpi_name: actual}
            
        Returns:
            Dict[kpi_center_id] = {
                'kpi_center_id', 'kpi_center_name', 'level', 'is_leaf',
                'kpis': List[{kpi_name, actual, target, achievement, weight}],
                'overall': float (weighted average),
                'total_weight': float,
                'source': 'Direct' | 'Rollup'
            }
        """
        if hierarchy_df.empty:
            return {}
        
        # Calculate proration factor
        proration = self._calculate_proration(period_type, year, start_date, end_date)
        
        # KPI column mapping
        kpi_column_map = {
            'revenue': 'sales_by_kpi_center_usd',
            'gross_profit': 'gross_profit_by_kpi_center_usd',
            'gross_profit_1': 'gp1_by_kpi_center_usd',
            'gp1': 'gp1_by_kpi_center_usd',
        }
        
        # Display names
        kpi_display_names = {
            'revenue': 'Revenue',
            'gross_profit': 'Gross Profit',
            'gross_profit_1': 'GP1',
            'gp1': 'GP1',
            'num_new_customers': 'New Customers',
            'num_new_products': 'New Products',
            'new_business_revenue': 'New Business Revenue',
        }
        
        # Icons
        kpi_icons = {
            'revenue': '💰',
            'gross_profit': '📈',
            'gross_profit_1': '📊',
            'gp1': '📊',
            'num_new_customers': '👥',
            'num_new_products': '📦',
            'new_business_revenue': '💼',
        }
        
        # Currency KPIs
        currency_kpis = ['revenue', 'gross_profit', 'gross_profit_1', 'gp1', 'new_business_revenue']
        
        result = {}
        
        # First pass: Calculate for all leaf nodes
        for _, row in hierarchy_df.iterrows():
            kpi_center_id = row['kpi_center_id']
            kpi_center_name = row['kpi_center_name']
            is_leaf = row.get('is_leaf', 1) == 1
            level = row.get('level', 0)
            
            if not is_leaf:
                continue  # Process parents in second pass
            
            # Get targets for this center
            center_targets = self.targets_df[
                self.targets_df['kpi_center_id'] == kpi_center_id
            ]
            
            if center_targets.empty:
                continue  # Skip centers without KPI assignment
            
            # Get actuals for this center
            center_sales = self.sales_df[
                self.sales_df['kpi_center_id'] == kpi_center_id
            ] if not self.sales_df.empty else pd.DataFrame()
            
            # Calculate per-KPI progress
            kpis = []
            total_weighted_achievement = 0
            total_weight = 0
            
            for _, target in center_targets.iterrows():
                kpi_name = target['kpi_name']
                kpi_lower = kpi_name.lower() if kpi_name else ''
                annual_target = target.get('annual_target_value_numeric', 0) or 0
                weight = target.get('weight_numeric', 100) or 100
                
                if annual_target <= 0:
                    continue
                
                # Calculate prorated target
                prorated_target = annual_target * proration
                
                # Get actual value
                actual = 0
                if kpi_lower in kpi_column_map:
                    col = kpi_column_map[kpi_lower]
                    if not center_sales.empty and col in center_sales.columns:
                        actual = center_sales[col].sum()
                elif complex_kpis_by_center and kpi_center_id in complex_kpis_by_center:
                    actual = complex_kpis_by_center[kpi_center_id].get(kpi_lower, 0)
                
                # Calculate achievement
                achievement = (actual / prorated_target * 100) if prorated_target > 0 else 0
                
                # Display name and icon
                display_name = kpi_display_names.get(kpi_lower, kpi_name.replace('_', ' ').title() if kpi_name else '')
                icon = kpi_icons.get(kpi_lower, '📋')
                
                kpis.append({
                    'kpi_name': kpi_name,
                    'display_name': f"{icon} {display_name}",
                    'actual': actual,
                    'prorated_target': prorated_target,
                    'annual_target': annual_target,
                    'achievement': achievement,
                    'weight': weight,
                    'is_currency': kpi_lower in currency_kpis
                })
                
                total_weighted_achievement += achievement * weight
                total_weight += weight
            
            if not kpis:
                continue
            
            # Calculate overall
            overall = total_weighted_achievement / total_weight if total_weight > 0 else None
            
            result[kpi_center_id] = {
                'kpi_center_id': kpi_center_id,
                'kpi_center_name': kpi_center_name,
                'level': level,
                'is_leaf': True,
                'kpis': kpis,
                'overall': overall,
                'total_weight': total_weight,
                'source': 'Direct'
            }
        
        # =====================================================================
        # Second pass: Calculate for parent nodes
        # NEW v3.3.0: Aggregate KPIs with Target-Proportion Weights
        # Instead of averaging children's overall, we:
        # 1. Aggregate targets & actuals by KPI type from all descendants
        # 2. Calculate achievement per KPI
        # 3. Derive weight from target proportion (currency KPIs)
        # 4. Calculate weighted overall
        # =====================================================================
        max_level = hierarchy_df['level'].max() if 'level' in hierarchy_df.columns else 0
        
        for current_level in range(max_level - 1, -1, -1):
            level_centers = hierarchy_df[hierarchy_df['level'] == current_level]
            
            for _, row in level_centers.iterrows():
                kpi_center_id = row['kpi_center_id']
                kpi_center_name = row['kpi_center_name']
                is_leaf = row.get('is_leaf', 1) == 1
                
                if is_leaf:
                    continue  # Already processed
                
                if kpi_center_id in result:
                    continue  # Already processed
                
                # Get leaf descendants
                leaf_descendants = queries_instance.get_leaf_descendants(kpi_center_id)
                
                if not leaf_descendants:
                    continue
                
                # =========================================================
                # Step 1: Aggregate targets by KPI type from all descendants
                # =========================================================
                descendants_targets = self.targets_df[
                    self.targets_df['kpi_center_id'].isin(leaf_descendants)
                ]
                
                if descendants_targets.empty:
                    continue
                
                # Get descendants' sales data
                descendants_sales = self.sales_df[
                    self.sales_df['kpi_center_id'].isin(leaf_descendants)
                ] if not self.sales_df.empty else pd.DataFrame()
                
                # =========================================================
                # Step 2: Calculate per-KPI aggregated metrics
                # FIXED v3.3.1: Only aggregate actual from descendants 
                # that have target for this specific KPI
                # =========================================================
                kpi_aggregates = {}  # {kpi_name: {target, actual, achievement}}
                
                for kpi_name in descendants_targets['kpi_name'].unique():
                    kpi_lower = kpi_name.lower() if kpi_name else ''
                    
                    # Get targets for this KPI and which descendants have it
                    kpi_targets = descendants_targets[
                        descendants_targets['kpi_name'] == kpi_name
                    ]
                    total_annual_target = kpi_targets['annual_target_value_numeric'].sum()
                    
                    if total_annual_target <= 0:
                        continue
                    
                    # CRITICAL: Get list of descendants that have THIS KPI target
                    # Only these descendants should contribute to actual
                    descendants_with_this_kpi = kpi_targets['kpi_center_id'].unique().tolist()
                    
                    # Prorated target
                    total_prorated_target = total_annual_target * proration
                    
                    # Sum actuals ONLY from descendants that have this KPI target
                    total_actual = 0
                    if kpi_lower in kpi_column_map:
                        col = kpi_column_map[kpi_lower]
                        if not descendants_sales.empty and col in descendants_sales.columns:
                            # FIXED: Filter to only descendants with this KPI target
                            filtered_sales = descendants_sales[
                                descendants_sales['kpi_center_id'].isin(descendants_with_this_kpi)
                            ]
                            total_actual = filtered_sales[col].sum() if not filtered_sales.empty else 0
                    elif kpi_lower in ['new_business_revenue', 'num_new_customers', 'num_new_products']:
                        # Sum complex KPIs ONLY from descendants that have this KPI target
                        if complex_kpis_by_center:
                            for child_id in descendants_with_this_kpi:  # FIXED: was leaf_descendants
                                if child_id in complex_kpis_by_center:
                                    total_actual += complex_kpis_by_center[child_id].get(kpi_lower, 0)
                    
                    # Achievement
                    achievement = (total_actual / total_prorated_target * 100) if total_prorated_target > 0 else 0
                    
                    kpi_aggregates[kpi_name] = {
                        'kpi_name': kpi_name,
                        'kpi_lower': kpi_lower,
                        'annual_target': total_annual_target,
                        'prorated_target': total_prorated_target,
                        'actual': total_actual,
                        'achievement': achievement,
                        'is_currency': kpi_lower in currency_kpis,
                        'contributing_centers': len(descendants_with_this_kpi)  # NEW: For display
                    }
                
                if not kpi_aggregates:
                    continue
                
                # =========================================================
                # Step 3: Derive weights from Target Proportion
                # Currency KPIs: weight = target / total_currency_targets
                # Count KPIs: equal weight, combined at fixed ratio
                # =========================================================
                
                # Separate currency vs count KPIs
                currency_kpi_data = {k: v for k, v in kpi_aggregates.items() if v['is_currency']}
                count_kpi_data = {k: v for k, v in kpi_aggregates.items() if not v['is_currency']}
                
                # Total currency targets for proportion calculation
                total_currency_target = sum(v['prorated_target'] for v in currency_kpi_data.values())
                
                # Build KPIs list with derived weights
                kpis = []
                total_weighted_achievement = 0
                total_derived_weight = 0
                
                # Process currency KPIs (weight = target proportion)
                for kpi_name, data in currency_kpi_data.items():
                    if total_currency_target > 0:
                        derived_weight = (data['prorated_target'] / total_currency_target) * 100
                    else:
                        derived_weight = 100 / len(currency_kpi_data) if currency_kpi_data else 0
                    
                    display_name = kpi_display_names.get(data['kpi_lower'], kpi_name.replace('_', ' ').title())
                    icon = kpi_icons.get(data['kpi_lower'], '📋')
                    
                    kpis.append({
                        'kpi_name': kpi_name,
                        'display_name': f"{icon} {display_name}",
                        'actual': data['actual'],
                        'prorated_target': data['prorated_target'],
                        'annual_target': data['annual_target'],
                        'achievement': data['achievement'],
                        'weight': derived_weight,
                        'weight_source': 'target_proportion',
                        'is_currency': True,
                        'contributing_centers': data.get('contributing_centers', 0)  # NEW v3.3.1
                    })
                    
                    total_weighted_achievement += data['achievement'] * derived_weight
                    total_derived_weight += derived_weight
                
                # Process count KPIs (equal weight among themselves)
                # Count KPIs contribute 20% of total if there are currency KPIs, 100% otherwise
                if count_kpi_data:
                    count_kpi_total_weight = 20 if currency_kpi_data else 100
                    per_count_kpi_weight = count_kpi_total_weight / len(count_kpi_data)
                    
                    for kpi_name, data in count_kpi_data.items():
                        display_name = kpi_display_names.get(data['kpi_lower'], kpi_name.replace('_', ' ').title())
                        icon = kpi_icons.get(data['kpi_lower'], '📋')
                        
                        kpis.append({
                            'kpi_name': kpi_name,
                            'display_name': f"{icon} {display_name}",
                            'actual': data['actual'],
                            'prorated_target': data['prorated_target'],
                            'annual_target': data['annual_target'],
                            'achievement': data['achievement'],
                            'weight': per_count_kpi_weight,
                            'weight_source': 'equal_split',
                            'is_currency': False,
                            'contributing_centers': data.get('contributing_centers', 0)  # NEW v3.3.1
                        })
                        
                        total_weighted_achievement += data['achievement'] * per_count_kpi_weight
                        total_derived_weight += per_count_kpi_weight
                
                # Normalize weights if currency KPIs exist (they should sum to 80%, count to 20%)
                if currency_kpi_data and count_kpi_data:
                    # Rescale currency weights to sum to 80%
                    currency_weight_sum = sum(k['weight'] for k in kpis if k['is_currency'])
                    if currency_weight_sum > 0:
                        for kpi in kpis:
                            if kpi['is_currency']:
                                kpi['weight'] = (kpi['weight'] / currency_weight_sum) * 80
                    
                    # Recalculate weighted achievement
                    total_weighted_achievement = sum(k['achievement'] * k['weight'] for k in kpis)
                    total_derived_weight = sum(k['weight'] for k in kpis)
                
                # Calculate overall
                overall = total_weighted_achievement / total_derived_weight if total_derived_weight > 0 else None
                
                # Sort KPIs by display name
                kpis.sort(key=lambda x: x['display_name'])
                
                # Collect children summary for display
                children_summary = []
                for child_id in leaf_descendants:
                    if child_id in result:
                        child_data = result[child_id]
                        children_summary.append({
                            'name': child_data['kpi_center_name'],
                            'achievement': child_data.get('overall'),
                            'weight': child_data.get('total_weight', 100)
                        })
                
                result[kpi_center_id] = {
                    'kpi_center_id': kpi_center_id,
                    'kpi_center_name': kpi_center_name,
                    'level': current_level,
                    'is_leaf': False,
                    'kpis': kpis,  # NEW: Parents now have aggregated KPIs
                    'overall': overall,
                    'total_weight': total_derived_weight,
                    'source': 'Aggregated',  # Changed from 'Rollup'
                    'children_count': len(leaf_descendants),
                    'children_summary': children_summary,
                    'calculation_method': 'target_proportion'  # NEW: For help tooltip
                }
        
        return result
    
    # =========================================================================
    # BACKLOG METRICS
    # =========================================================================
    
    def calculate_backlog_metrics(
        self,
        total_backlog_df: pd.DataFrame,
        in_period_backlog_df: pd.DataFrame,
        period_type: str = 'YTD',
        year: int = None,
        start_date: date = None,
        end_date: date = None
    ) -> Dict:
        """
        Calculate backlog and forecast metrics.
        
        GP1 backlog is estimated using GP1/GP ratio from invoiced data.
        """
        metrics = {
            'total_backlog_revenue': 0,
            'total_backlog_gp': 0,
            'total_backlog_gp1': 0,
            'backlog_orders': 0,
            'in_period_backlog_revenue': 0,
            'in_period_backlog_gp': 0,
            'in_period_backlog_gp1': 0,
            'in_period_orders': 0,
            'gp1_gp_ratio': 1.0,
        }
        
        # Calculate GP1/GP ratio from invoiced data
        if not self.sales_df.empty:
            total_gp = self.sales_df['gross_profit_by_kpi_center_usd'].sum()
            total_gp1 = self.sales_df['gp1_by_kpi_center_usd'].sum() if 'gp1_by_kpi_center_usd' in self.sales_df.columns else 0
            if total_gp > 0:
                metrics['gp1_gp_ratio'] = total_gp1 / total_gp
        
        # Total backlog
        if not total_backlog_df.empty:
            metrics['total_backlog_revenue'] = total_backlog_df['total_backlog_usd'].sum()
            metrics['total_backlog_gp'] = total_backlog_df['total_backlog_gp_usd'].sum()
            metrics['total_backlog_gp1'] = metrics['total_backlog_gp'] * metrics['gp1_gp_ratio']
            metrics['backlog_orders'] = total_backlog_df['backlog_orders'].sum()
        
        # In-period backlog
        if not in_period_backlog_df.empty:
            metrics['in_period_backlog_revenue'] = in_period_backlog_df['in_period_backlog_usd'].sum()
            metrics['in_period_backlog_gp'] = in_period_backlog_df['in_period_backlog_gp_usd'].sum()
            metrics['in_period_backlog_gp1'] = metrics['in_period_backlog_gp'] * metrics['gp1_gp_ratio']
            metrics['in_period_orders'] = in_period_backlog_df['in_period_orders'].sum()
        
        # Calculate forecast = invoiced + in-period backlog
        invoiced_revenue = self.sales_df['sales_by_kpi_center_usd'].sum() if not self.sales_df.empty else 0
        invoiced_gp = self.sales_df['gross_profit_by_kpi_center_usd'].sum() if not self.sales_df.empty else 0
        invoiced_gp1 = self.sales_df['gp1_by_kpi_center_usd'].sum() if not self.sales_df.empty else 0
        
        metrics['current_invoiced_revenue'] = invoiced_revenue
        metrics['current_invoiced_gp'] = invoiced_gp
        metrics['current_invoiced_gp1'] = invoiced_gp1
        
        metrics['forecast_revenue'] = invoiced_revenue + metrics['in_period_backlog_revenue']
        metrics['forecast_gp'] = invoiced_gp + metrics['in_period_backlog_gp']
        metrics['forecast_gp1'] = invoiced_gp1 + metrics['in_period_backlog_gp1']
        
        # Period context
        if start_date and end_date:
            metrics['period_context'] = self.analyze_period_context(start_date, end_date)
        
        return metrics
    
    def calculate_pipeline_forecast_metrics(
        self,
        total_backlog_df: pd.DataFrame,
        in_period_backlog_df: pd.DataFrame,
        period_type: str = 'YTD',
        year: int = None,
        start_date: date = None,
        end_date: date = None
    ) -> Dict:
        """
        Calculate pipeline & forecast metrics with KPI filtering.
        
        For each KPI (Revenue/GP/GP1): Only includes invoiced + backlog from 
        KPI centers who have that specific KPI target assigned.
        """
        proration = self._calculate_proration(period_type, year, start_date, end_date)
        
        # GP1/GP ratio for estimation
        gp1_gp_ratio = 1.0
        if not self.sales_df.empty:
            total_gp = self.sales_df['gross_profit_by_kpi_center_usd'].sum()
            total_gp1 = self.sales_df['gp1_by_kpi_center_usd'].sum() if 'gp1_by_kpi_center_usd' in self.sales_df.columns else 0
            if total_gp > 0:
                gp1_gp_ratio = total_gp1 / total_gp
        
        result = {
            'revenue': self._calculate_kpi_pipeline('revenue', proration, total_backlog_df, in_period_backlog_df),
            'gross_profit': self._calculate_kpi_pipeline('gross_profit', proration, total_backlog_df, in_period_backlog_df),
            'gp1': self._calculate_kpi_pipeline('gross_profit_1', proration, total_backlog_df, in_period_backlog_df, gp1_gp_ratio),
            'summary': {
                'total_backlog_revenue': total_backlog_df['total_backlog_usd'].sum() if not total_backlog_df.empty else 0,
                'total_backlog_gp': total_backlog_df['total_backlog_gp_usd'].sum() if not total_backlog_df.empty else 0,
                'total_backlog_gp1': (total_backlog_df['total_backlog_gp_usd'].sum() * gp1_gp_ratio) if not total_backlog_df.empty else 0,
                'backlog_orders': int(total_backlog_df['backlog_orders'].sum()) if not total_backlog_df.empty else 0,
                'gp1_gp_ratio': gp1_gp_ratio,
            },
            'period_context': self.analyze_period_context(start_date, end_date) if start_date and end_date else {},
        }
        
        return result
    
    def _calculate_kpi_pipeline(
        self,
        kpi_name: str,
        proration: float,
        total_backlog_df: pd.DataFrame,
        in_period_backlog_df: pd.DataFrame,
        gp1_ratio: float = 1.0
    ) -> Dict:
        """Calculate pipeline metrics for a specific KPI type."""
        # Get KPI centers with this target
        kpi_centers = self._get_kpi_centers_with_target(kpi_name)
        
        # Get target
        target = self._get_target_for_kpi(kpi_name)
        prorated_target = target * proration if target > 0 else None
        
        # Column mapping
        if kpi_name in ['revenue']:
            sales_col = 'sales_by_kpi_center_usd'
            backlog_col = 'total_backlog_usd'
            in_period_col = 'in_period_backlog_usd'
            use_ratio = False
        elif kpi_name in ['gross_profit']:
            sales_col = 'gross_profit_by_kpi_center_usd'
            backlog_col = 'total_backlog_gp_usd'
            in_period_col = 'in_period_backlog_gp_usd'
            use_ratio = False
        else:  # gp1
            sales_col = 'gp1_by_kpi_center_usd'
            backlog_col = 'total_backlog_gp_usd'  # Will apply ratio
            in_period_col = 'in_period_backlog_gp_usd'  # Will apply ratio
            use_ratio = True
        
        # Calculate invoiced from filtered KPI centers
        if kpi_centers and not self.sales_df.empty:
            filtered_sales = self.sales_df[self.sales_df['kpi_center_id'].isin(kpi_centers)]
            invoiced = filtered_sales[sales_col].sum() if sales_col in filtered_sales.columns else 0
        else:
            invoiced = self.sales_df[sales_col].sum() if not self.sales_df.empty and sales_col in self.sales_df.columns else 0
        
        # Calculate backlog from filtered KPI centers
        if kpi_centers and not in_period_backlog_df.empty:
            filtered_backlog = in_period_backlog_df[in_period_backlog_df['kpi_center_id'].isin(kpi_centers)]
            in_period_backlog = filtered_backlog[in_period_col].sum() if in_period_col in filtered_backlog.columns else 0
        else:
            in_period_backlog = in_period_backlog_df[in_period_col].sum() if not in_period_backlog_df.empty and in_period_col in in_period_backlog_df.columns else 0
        
        # Apply GP1 ratio if needed
        if use_ratio:
            in_period_backlog *= gp1_ratio
        
        # Forecast and gap
        forecast = invoiced + in_period_backlog
        gap = (forecast - prorated_target) if prorated_target else None
        gap_percent = (gap / prorated_target * 100) if prorated_target and prorated_target > 0 else None
        forecast_achievement = (forecast / prorated_target * 100) if prorated_target and prorated_target > 0 else None
        
        # FIXED: Changed employee_count to kpi_center_count for consistency
        return {
            'invoiced': invoiced,
            'in_period_backlog': in_period_backlog,
            'target': prorated_target,
            'forecast': forecast,
            'gap': gap,
            'gap_percent': gap_percent,
            'forecast_achievement': forecast_achievement,
            'kpi_center_count': len(kpi_centers),  # FIXED: was employee_count
        }
    
    # =========================================================================
    # IN-PERIOD BACKLOG ANALYSIS
    # =========================================================================
    
    @staticmethod
    def analyze_in_period_backlog(
        backlog_detail_df: pd.DataFrame,
        start_date: date,
        end_date: date
    ) -> Dict:
        """
        Analyze backlog with ETD within the selected period.
        
        Provides detailed breakdown of overdue vs on-track orders.
        """
        today = date.today()
        result = {
            'total_value': 0,
            'total_gp': 0,
            'total_count': 0,
            'overdue_value': 0,
            'overdue_gp': 0,
            'overdue_count': 0,
            'on_track_value': 0,
            'on_track_gp': 0,
            'on_track_count': 0,
            'status': 'empty',
            'overdue_warning': None
        }
        
        if backlog_detail_df.empty:
            return result
        
        df = backlog_detail_df.copy()
        
        # Ensure ETD is datetime
        if 'etd' in df.columns:
            df['etd'] = pd.to_datetime(df['etd'], errors='coerce')
        else:
            return result
        
        # Filter to in-period (ETD within date range)
        in_period = df[
            (df['etd'].dt.date >= start_date) & 
            (df['etd'].dt.date <= end_date)
        ]
        
        if in_period.empty:
            return result
        
        # Get value columns
        value_col = 'backlog_by_kpi_center_usd' if 'backlog_by_kpi_center_usd' in in_period.columns else None
        gp_col = 'backlog_gp_by_kpi_center_usd' if 'backlog_gp_by_kpi_center_usd' in in_period.columns else None
        
        # Total in-period
        result['total_count'] = len(in_period)
        if value_col:
            result['total_value'] = in_period[value_col].sum()
        if gp_col:
            result['total_gp'] = in_period[gp_col].sum()
        
        # Split: Overdue (ETD < today) vs On-track (ETD >= today)
        overdue = in_period[in_period['etd'].dt.date < today]
        on_track = in_period[in_period['etd'].dt.date >= today]
        
        # Overdue metrics
        result['overdue_count'] = len(overdue)
        if value_col and not overdue.empty:
            result['overdue_value'] = overdue[value_col].sum()
        if gp_col and not overdue.empty:
            result['overdue_gp'] = overdue[gp_col].sum()
        
        # On-track metrics
        result['on_track_count'] = len(on_track)
        if value_col and not on_track.empty:
            result['on_track_value'] = on_track[value_col].sum()
        if gp_col and not on_track.empty:
            result['on_track_gp'] = on_track[gp_col].sum()
        
        # Determine status
        if result['overdue_count'] > 0:
            result['status'] = 'has_overdue'
            overdue_pct = (result['overdue_value'] / result['total_value'] * 100) if result['total_value'] > 0 else 0
            result['overdue_warning'] = (
                f"⚠️ {result['overdue_count']} orders (${result['overdue_value']:,.0f}, "
                f"{overdue_pct:.0f}%) are overdue"
            )
        else:
            result['status'] = 'healthy'
        
        return result
    
    # =========================================================================
    # MONTHLY SUMMARY
    # =========================================================================
    
    def prepare_monthly_summary(self) -> pd.DataFrame:
        """
        Prepare monthly breakdown of metrics.
        
        Returns DataFrame with monthly revenue, GP, GP1, customer count.
        """
        if self.sales_df.empty:
            return self._get_empty_monthly_summary()
        
        df = self.sales_df.copy()
        
        # Ensure invoice_month exists
        if 'invoice_month' not in df.columns or df['invoice_month'].isna().all():
            if 'inv_date' in df.columns:
                df['inv_date'] = pd.to_datetime(df['inv_date'], errors='coerce')
                df['invoice_month'] = df['inv_date'].dt.strftime('%b')
            else:
                return self._get_empty_monthly_summary()
        
        # Group by month
        monthly = df.groupby('invoice_month').agg({
            'sales_by_kpi_center_usd': 'sum',
            'gross_profit_by_kpi_center_usd': 'sum',
            'gp1_by_kpi_center_usd': 'sum' if 'gp1_by_kpi_center_usd' in df.columns else 'count',
            'customer_id': pd.Series.nunique
        }).reset_index()
        
        monthly.columns = ['invoice_month', 'revenue', 'gross_profit', 'gp1', 'customer_count']
        
        # If gp1 column was count (fallback), set to 0
        if 'gp1_by_kpi_center_usd' not in df.columns:
            monthly['gp1'] = 0
        
        # Calculate GP%
        monthly['gp_percent'] = (monthly['gross_profit'] / monthly['revenue'] * 100).round(2)
        monthly['gp1_percent'] = (monthly['gp1'] / monthly['revenue'] * 100).round(2)
        
        # Ensure all months present
        all_months = pd.DataFrame({'invoice_month': MONTH_ORDER})
        monthly = all_months.merge(monthly, on='invoice_month', how='left').fillna(0)
        
        # Add month order for sorting
        monthly['month_order'] = monthly['invoice_month'].apply(
            lambda x: MONTH_ORDER.index(x) if x in MONTH_ORDER else 12
        )
        monthly = monthly.sort_values('month_order')
        
        # Calculate cumulative
        monthly['cumulative_revenue'] = monthly['revenue'].cumsum()
        monthly['cumulative_gp'] = monthly['gross_profit'].cumsum()
        monthly['cumulative_gp1'] = monthly['gp1'].cumsum()
        
        return monthly
    
    def _get_empty_monthly_summary(self) -> pd.DataFrame:
        """Return empty monthly summary."""
        return pd.DataFrame({
            'invoice_month': MONTH_ORDER,
            'revenue': [0] * 12,
            'gross_profit': [0] * 12,
            'gp1': [0] * 12,
            'customer_count': [0] * 12,
            'gp_percent': [0] * 12,
            'gp1_percent': [0] * 12,
            'cumulative_revenue': [0] * 12,
            'cumulative_gp': [0] * 12,
            'cumulative_gp1': [0] * 12,
            'month_order': list(range(12)),
        })
    
    # =========================================================================
    # KPI CENTER AGGREGATION
    # =========================================================================
    
    def aggregate_by_kpi_center(self) -> pd.DataFrame:
        """
        Aggregate metrics by KPI Center for ranking and comparison.
        
        Returns:
            DataFrame with per-KPI-Center metrics
        """
        if self.sales_df.empty:
            return pd.DataFrame()
        
        df = self.sales_df.copy()
        
        # Group by KPI Center
        by_kpi_center = df.groupby(['kpi_center_id', 'kpi_center']).agg({
            'sales_by_kpi_center_usd': 'sum',
            'gross_profit_by_kpi_center_usd': 'sum',
            'gp1_by_kpi_center_usd': 'sum' if 'gp1_by_kpi_center_usd' in df.columns else 'count',
            'customer_id': pd.Series.nunique,
            'inv_number': pd.Series.nunique if 'inv_number' in df.columns else 'count'
        }).reset_index()
        
        by_kpi_center.columns = ['kpi_center_id', 'kpi_center', 'revenue', 'gross_profit', 'gp1', 'customers', 'invoices']
        
        # If gp1 was count (fallback), set to 0
        if 'gp1_by_kpi_center_usd' not in df.columns:
            by_kpi_center['gp1'] = 0
        
        # Calculate percentages
        by_kpi_center['gp_percent'] = (by_kpi_center['gross_profit'] / by_kpi_center['revenue'] * 100).round(2)
        by_kpi_center['gp1_percent'] = (by_kpi_center['gp1'] / by_kpi_center['revenue'] * 100).round(2)
        
        # Add kpi_type if available
        if 'kpi_type' in df.columns:
            kpi_types = df.groupby('kpi_center_id')['kpi_type'].first().reset_index()
            by_kpi_center = by_kpi_center.merge(kpi_types, on='kpi_center_id', how='left')
        
        # Add targets if available
        if not self.targets_df.empty:
            # Get revenue targets
            revenue_targets = self.targets_df[
                self.targets_df['kpi_name'].str.lower() == 'revenue'
            ][['kpi_center_id', 'annual_target_value_numeric']].copy()
            revenue_targets.columns = ['kpi_center_id', 'revenue_target']
            
            by_kpi_center = by_kpi_center.merge(revenue_targets, on='kpi_center_id', how='left')
            
            # Calculate achievement
            by_kpi_center['revenue_achievement'] = (
                by_kpi_center['revenue'] / by_kpi_center['revenue_target'] * 100
            ).round(1)
            
            # GP targets
            gp_targets = self.targets_df[
                self.targets_df['kpi_name'].str.lower() == 'gross_profit'
            ][['kpi_center_id', 'annual_target_value_numeric']].copy()
            gp_targets.columns = ['kpi_center_id', 'gp_target']
            
            by_kpi_center = by_kpi_center.merge(gp_targets, on='kpi_center_id', how='left')
            by_kpi_center['gp_achievement'] = (
                by_kpi_center['gross_profit'] / by_kpi_center['gp_target'] * 100
            ).round(1)
        
        return by_kpi_center.sort_values('revenue', ascending=False)
    
    # =========================================================================
    # BACKLOG BY MONTH PREPARATION
    # =========================================================================
    
    def prepare_backlog_by_month(
        self,
        backlog_by_month_df: pd.DataFrame,
        year: int = None
    ) -> pd.DataFrame:
        """
        Prepare backlog by ETD month for display.
        """
        if backlog_by_month_df.empty:
            return pd.DataFrame()
        
        df = backlog_by_month_df.copy()
        
        # Filter to year if provided
        if year and 'etd_year' in df.columns:
            df = df[df['etd_year'] == year]
        
        return df
    
    # =========================================================================
    # TOP CUSTOMERS/BRANDS ANALYSIS
    # =========================================================================
    
    def prepare_top_customers_by_metric(
        self,
        metric: str = 'revenue',
        top_percent: float = 0.8
    ) -> pd.DataFrame:
        """
        Get top customers that make up specified percentage of metric.
        """
        if self.sales_df.empty:
            return pd.DataFrame()
        
        df = self.sales_df.copy()
        
        # Map metric to column
        metric_map = {
            'revenue': 'sales_by_kpi_center_usd',
            'gross_profit': 'gross_profit_by_kpi_center_usd',
            'gp1': 'gp1_by_kpi_center_usd'
        }
        col = metric_map.get(metric, 'sales_by_kpi_center_usd')
        
        # Group by customer
        customer_data = df.groupby(['customer_id', 'customer']).agg({
            'sales_by_kpi_center_usd': 'sum',
            'gross_profit_by_kpi_center_usd': 'sum',
            'gp1_by_kpi_center_usd': 'sum' if 'gp1_by_kpi_center_usd' in df.columns else 'count'
        }).reset_index()
        
        customer_data.columns = ['customer_id', 'customer', 'revenue', 'gross_profit', 'gp1']
        
        if 'gp1_by_kpi_center_usd' not in df.columns:
            customer_data['gp1'] = 0
        
        # Sort by selected metric
        customer_data = customer_data.sort_values(metric, ascending=False)
        total_metric = customer_data[metric].sum()
        
        if total_metric == 0:
            return pd.DataFrame()
        
        # Calculate cumulative
        customer_data['cumulative_value'] = customer_data[metric].cumsum()
        customer_data['cumulative_percent'] = customer_data['cumulative_value'] / total_metric
        customer_data['percent_contribution'] = customer_data[metric] / total_metric * 100
        
        # Find cutoff
        exceed_mask = customer_data['cumulative_percent'] > top_percent
        
        if exceed_mask.any():
            first_exceed_idx = exceed_mask.idxmax()
            top_customers = customer_data.loc[:first_exceed_idx].copy()
        else:
            top_customers = customer_data.copy()
        
        return top_customers
    
    def prepare_top_brands_by_metric(
        self,
        metric: str = 'revenue',
        top_percent: float = 0.8
    ) -> pd.DataFrame:
        """
        Get top brands that make up specified percentage of metric.
        """
        if self.sales_df.empty:
            return pd.DataFrame()
        
        df = self.sales_df.copy()
        
        # Map metric to column
        metric_map = {
            'revenue': 'sales_by_kpi_center_usd',
            'gross_profit': 'gross_profit_by_kpi_center_usd',
            'gp1': 'gp1_by_kpi_center_usd'
        }
        col = metric_map.get(metric, 'sales_by_kpi_center_usd')
        
        # Group by brand
        brand_data = df.groupby('brand').agg({
            'sales_by_kpi_center_usd': 'sum',
            'gross_profit_by_kpi_center_usd': 'sum',
            'gp1_by_kpi_center_usd': 'sum' if 'gp1_by_kpi_center_usd' in df.columns else 'count'
        }).reset_index()
        
        brand_data.columns = ['brand', 'revenue', 'gross_profit', 'gp1']
        
        if 'gp1_by_kpi_center_usd' not in df.columns:
            brand_data['gp1'] = 0
        
        # Sort by selected metric
        brand_data = brand_data.sort_values(metric, ascending=False)
        total_metric = brand_data[metric].sum()
        
        if total_metric == 0:
            return pd.DataFrame()
        
        # Calculate cumulative
        brand_data['cumulative_value'] = brand_data[metric].cumsum()
        brand_data['cumulative_percent'] = brand_data['cumulative_value'] / total_metric
        brand_data['percent_contribution'] = brand_data[metric] / total_metric * 100
        
        # Find cutoff
        exceed_mask = brand_data['cumulative_percent'] > top_percent
        
        if exceed_mask.any():
            first_exceed_idx = exceed_mask.idxmax()
            top_brands = brand_data.loc[:first_exceed_idx].copy()
        else:
            top_brands = brand_data.copy()
        
        return top_brands
    
    # =========================================================================
    # IN-PERIOD BACKLOG ANALYSIS - NEW v3.0.0 (synced with Salesperson)
    # =========================================================================
    
    @staticmethod
    def analyze_in_period_backlog(
        backlog_detail_df: pd.DataFrame,
        start_date,
        end_date
    ) -> Dict:
        """
        Analyze backlog with ETD within the selected period.
        Provides detailed breakdown of overdue vs on-track orders.
        
        SYNCED v3.0.0 with Salesperson module.
        
        Args:
            backlog_detail_df: Detailed backlog records
            start_date: Period start date
            end_date: Period end date
            
        Returns:
            Dict with:
            - total_value, total_gp, total_count
            - overdue_value, overdue_gp, overdue_count
            - on_track_value, on_track_gp, on_track_count
            - status: 'empty', 'historical', 'has_overdue', 'healthy'
            - overdue_warning: str (if applicable)
        """
        from datetime import date
        
        today = date.today()
        result = {
            'total_value': 0,
            'total_gp': 0,
            'total_count': 0,
            'overdue_value': 0,
            'overdue_gp': 0,
            'overdue_count': 0,
            'on_track_value': 0,
            'on_track_gp': 0,
            'on_track_count': 0,
            'status': 'empty',
            'overdue_warning': None
        }
        
        if backlog_detail_df.empty:
            return result
        
        df = backlog_detail_df.copy()
        
        # Ensure ETD is datetime
        if 'etd' in df.columns:
            df['etd'] = pd.to_datetime(df['etd'], errors='coerce')
        else:
            return result
        
        # Filter to in-period (ETD within date range)
        in_period = df[
            (df['etd'].dt.date >= start_date) & 
            (df['etd'].dt.date <= end_date)
        ]
        
        if in_period.empty:
            return result
        
        # Detect column names (KPI Center uses different names)
        value_col = None
        gp_col = None
        
        for col_name in ['backlog_by_kpi_center_usd', 'backlog_usd', 'backlog_revenue']:
            if col_name in in_period.columns:
                value_col = col_name
                break
        
        for col_name in ['backlog_gp_by_kpi_center_usd', 'backlog_gp_usd', 'backlog_gp']:
            if col_name in in_period.columns:
                gp_col = col_name
                break
        
        # Total in-period
        result['total_count'] = len(in_period)
        if value_col:
            result['total_value'] = in_period[value_col].sum()
        if gp_col:
            result['total_gp'] = in_period[gp_col].sum()
        
        # Split: Overdue (ETD < today) vs On-track (ETD >= today)
        overdue = in_period[in_period['etd'].dt.date < today]
        on_track = in_period[in_period['etd'].dt.date >= today]
        
        # Overdue metrics
        result['overdue_count'] = len(overdue)
        if value_col and not overdue.empty:
            result['overdue_value'] = overdue[value_col].sum()
        if gp_col and not overdue.empty:
            result['overdue_gp'] = overdue[gp_col].sum()
        
        # On-track metrics
        result['on_track_count'] = len(on_track)
        if value_col and not on_track.empty:
            result['on_track_value'] = on_track[value_col].sum()
        if gp_col and not on_track.empty:
            result['on_track_gp'] = on_track[gp_col].sum()
        
        # Determine status
        is_historical_period = end_date < today
        
        if is_historical_period:
            result['status'] = 'historical'
            if result['overdue_count'] > 0:
                result['overdue_warning'] = (
                    f"⚠️ {result['overdue_count']} orders with ETD in period are overdue. "
                    f"Total value: ${result['overdue_value']:,.0f}. Please review and update."
                )
        elif result['overdue_count'] > 0:
            result['status'] = 'has_overdue'
            result['overdue_warning'] = (
                f"⚠️ {result['overdue_count']} orders are past ETD. "
                f"Value: ${result['overdue_value']:,.0f}"
            )
        else:
            result['status'] = 'healthy'
        
        return result