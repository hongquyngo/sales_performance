# utils/salesperson_performance/export.py
"""
Formatted Excel Export for Salesperson Performance

Creates professional Excel reports with:
- Cover sheet with KPI summary
- Salesperson summary with conditional formatting
- Monthly breakdown
- Detailed transactions

Uses openpyxl for formatting capabilities.
"""

import logging
from datetime import datetime
from io import BytesIO
from typing import Dict, List, Optional
import pandas as pd

from openpyxl import Workbook
from openpyxl.styles import (
    Font, Alignment, Border, Side, PatternFill, NamedStyle
)
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import ColorScaleRule, FormulaRule

from .constants import EXCEL_STYLES

logger = logging.getLogger(__name__)


class SalespersonExport:
    """
    Excel report generator for salesperson performance.
    
    Usage:
        exporter = SalespersonExport()
        excel_bytes = exporter.create_report(
            summary_df=summary_df,
            monthly_df=monthly_df,
            metrics=metrics,
            filters=filters
        )
        
        st.download_button(
            label="Download Report",
            data=excel_bytes,
            file_name="salesperson_performance.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    """
    
    def __init__(self):
        """Initialize with default styles."""
        self.wb = None
        self._init_styles()
    
    def _init_styles(self):
        """Initialize reusable styles."""
        # Colors
        self.header_fill = PatternFill(
            start_color=EXCEL_STYLES['header_fill_color'],
            end_color=EXCEL_STYLES['header_fill_color'],
            fill_type='solid'
        )
        
        self.header_font = Font(
            bold=True,
            color=EXCEL_STYLES['header_font_color'],
            size=11
        )
        
        self.title_font = Font(bold=True, size=16)
        self.subtitle_font = Font(bold=True, size=12)
        self.normal_font = Font(size=11)
        
        # Borders
        thin_border = Side(style='thin', color='000000')
        self.cell_border = Border(
            left=thin_border,
            right=thin_border,
            top=thin_border,
            bottom=thin_border
        )
        
        # Alignments
        self.center_align = Alignment(horizontal='center', vertical='center')
        self.right_align = Alignment(horizontal='right', vertical='center')
        self.left_align = Alignment(horizontal='left', vertical='center')
        
        # Number formats
        self.currency_format = EXCEL_STYLES['currency_format']
        self.percent_format = EXCEL_STYLES['percent_format']
    
    # =========================================================================
    # MAIN EXPORT METHOD
    # =========================================================================
    
    def create_report(
        self,
        summary_df: pd.DataFrame,
        monthly_df: pd.DataFrame,
        metrics: Dict,
        filters: Dict,
        detail_df: pd.DataFrame = None,
        complex_kpis: Dict = None,
        yoy_metrics: Dict = None
    ) -> BytesIO:
        """
        Create formatted Excel report with multiple sheets.
        
        Args:
            summary_df: Salesperson summary data
            monthly_df: Monthly breakdown data
            metrics: Overview metrics dict
            filters: Filter settings dict
            detail_df: Optional detailed transactions
            complex_kpis: Optional complex KPI metrics
            yoy_metrics: Optional YoY comparison metrics
            
        Returns:
            BytesIO containing Excel file
        """
        self.wb = Workbook()
        
        # Create sheets
        self._create_cover_sheet(metrics, filters, complex_kpis, yoy_metrics)
        self._create_summary_sheet(summary_df)
        self._create_monthly_sheet(monthly_df)
        
        if detail_df is not None and not detail_df.empty:
            self._create_detail_sheet(detail_df)
        
        # Remove default empty sheet if exists
        if 'Sheet' in self.wb.sheetnames:
            del self.wb['Sheet']
        
        # Save to BytesIO
        output = BytesIO()
        self.wb.save(output)
        output.seek(0)
        
        logger.info("Excel report created successfully")
        return output
    
    # =========================================================================
    # COVER SHEET
    # =========================================================================
    
    def _create_cover_sheet(
        self,
        metrics: Dict,
        filters: Dict,
        complex_kpis: Dict = None,
        yoy_metrics: Dict = None
    ):
        """Create cover page with KPI summary."""
        ws = self.wb.active
        ws.title = "Summary"
        
        row = 1
        
        # Title
        ws.cell(row=row, column=1, value="Salesperson Performance Report")
        ws.cell(row=row, column=1).font = self.title_font
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
        row += 2
        
        # Report Info
        ws.cell(row=row, column=1, value="Report Period:")
        ws.cell(row=row, column=2, value=f"{filters.get('period_type', 'YTD')} {filters.get('year', '')}")
        row += 1
        
        ws.cell(row=row, column=1, value="Date Range:")
        start_date = filters.get('start_date', '')
        end_date = filters.get('end_date', '')
        ws.cell(row=row, column=2, value=f"{start_date} to {end_date}")
        row += 1
        
        ws.cell(row=row, column=1, value="Generated:")
        ws.cell(row=row, column=2, value=datetime.now().strftime('%Y-%m-%d %H:%M'))
        row += 2
        
        # Main KPIs Section
        ws.cell(row=row, column=1, value="Key Performance Indicators")
        ws.cell(row=row, column=1).font = self.subtitle_font
        row += 1
        
        kpi_rows = [
            ("Total Revenue", f"${metrics.get('total_revenue', 0):,.0f}"),
            ("Gross Profit", f"${metrics.get('total_gp', 0):,.0f}"),
            ("GP1", f"${metrics.get('total_gp1', 0):,.0f}"),
            ("GP %", f"{metrics.get('gp_percent', 0):.1f}%"),
            ("Total Customers", f"{metrics.get('total_customers', 0):,}"),
            ("Total Invoices", f"{metrics.get('total_invoices', 0):,}"),
            ("Total Orders", f"{metrics.get('total_orders', 0):,}"),
        ]
        
        # Add achievement if available
        if metrics.get('revenue_achievement'):
            kpi_rows.append(("Revenue Achievement", f"{metrics['revenue_achievement']:.1f}%"))
        if metrics.get('gp_achievement'):
            kpi_rows.append(("GP Achievement", f"{metrics['gp_achievement']:.1f}%"))
        
        for label, value in kpi_rows:
            ws.cell(row=row, column=1, value=label)
            ws.cell(row=row, column=2, value=value)
            ws.cell(row=row, column=2).alignment = self.right_align
            row += 1
        
        row += 1
        
        # Complex KPIs Section (if provided)
        if complex_kpis:
            ws.cell(row=row, column=1, value="Complex KPIs")
            ws.cell(row=row, column=1).font = self.subtitle_font
            row += 1
            
            complex_rows = [
                ("New Customers", f"{complex_kpis.get('new_customer_count', 0):.1f}"),
                ("New Products", f"{complex_kpis.get('new_product_count', 0):.1f}"),
                ("New Business Revenue", f"${complex_kpis.get('new_business_revenue', 0):,.0f}"),
            ]
            
            for label, value in complex_rows:
                ws.cell(row=row, column=1, value=label)
                ws.cell(row=row, column=2, value=value)
                ws.cell(row=row, column=2).alignment = self.right_align
                row += 1
            
            row += 1
        
        # YoY Comparison (if provided)
        if yoy_metrics:
            ws.cell(row=row, column=1, value="Year-over-Year Comparison")
            ws.cell(row=row, column=1).font = self.subtitle_font
            row += 1
            
            yoy_rows = [
                ("Revenue YoY", yoy_metrics.get('total_revenue_yoy')),
                ("GP YoY", yoy_metrics.get('total_gp_yoy')),
                ("Customers YoY", yoy_metrics.get('total_customers_yoy')),
            ]
            
            for label, value in yoy_rows:
                ws.cell(row=row, column=1, value=label)
                if value is not None:
                    ws.cell(row=row, column=2, value=f"{value:+.1f}%")
                else:
                    ws.cell(row=row, column=2, value="N/A")
                ws.cell(row=row, column=2).alignment = self.right_align
                row += 1
        
        # Adjust column widths
        ws.column_dimensions['A'].width = 25
        ws.column_dimensions['B'].width = 20
    
    # =========================================================================
    # SUMMARY SHEET
    # =========================================================================
    
    def _create_summary_sheet(self, df: pd.DataFrame):
        """Create salesperson summary sheet with formatting."""
        if df.empty:
            return
        
        ws = self.wb.create_sheet("By Salesperson")
        
        # Define columns to export
        columns = [
            ('sales_name', 'Salesperson', 25),
            ('sales_email', 'Email', 30),
            ('revenue', 'Revenue (USD)', 15),
            ('gross_profit', 'Gross Profit (USD)', 18),
            ('gp1', 'GP1 (USD)', 15),
            ('gp_percent', 'GP %', 10),
            ('customers', 'Customers', 12),
            ('invoices', 'Invoices', 10),
        ]
        
        # Add target columns if present
        if 'revenue_target' in df.columns:
            columns.append(('revenue_target', 'Revenue Target', 15))
            columns.append(('revenue_achievement', 'Achievement %', 14))
        
        # Write headers
        for col_idx, (col_name, header, width) in enumerate(columns, 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.fill = self.header_fill
            cell.font = self.header_font
            cell.alignment = self.center_align
            cell.border = self.cell_border
            ws.column_dimensions[get_column_letter(col_idx)].width = width
        
        # Write data
        for row_idx, row_data in enumerate(df.itertuples(index=False), 2):
            for col_idx, (col_name, _, _) in enumerate(columns, 1):
                if hasattr(row_data, col_name):
                    value = getattr(row_data, col_name)
                else:
                    # Try to get by index from dataframe
                    try:
                        value = df.iloc[row_idx - 2][col_name]
                    except:
                        value = ''
                
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.border = self.cell_border
                
                # Apply formatting based on column type
                if col_name in ['revenue', 'gross_profit', 'gp1', 'revenue_target']:
                    cell.number_format = self.currency_format
                    cell.alignment = self.right_align
                elif col_name in ['gp_percent', 'revenue_achievement']:
                    cell.alignment = self.right_align
                elif col_name in ['customers', 'invoices']:
                    cell.alignment = self.center_align
        
        # Add conditional formatting for achievement column
        if 'revenue_achievement' in df.columns:
            achievement_col = None
            for col_idx, (col_name, _, _) in enumerate(columns, 1):
                if col_name == 'revenue_achievement':
                    achievement_col = get_column_letter(col_idx)
                    break
            
            if achievement_col:
                # Red for <80%, Yellow for 80-100%, Green for >=100%
                ws.conditional_formatting.add(
                    f'{achievement_col}2:{achievement_col}{len(df) + 1}',
                    ColorScaleRule(
                        start_type='num', start_value=50, start_color='F8696B',
                        mid_type='num', mid_value=100, mid_color='FFEB84',
                        end_type='num', end_value=150, end_color='63BE7B'
                    )
                )
        
        # Freeze header row
        ws.freeze_panes = 'A2'
    
    # =========================================================================
    # MONTHLY SHEET
    # =========================================================================
    
    def _create_monthly_sheet(self, df: pd.DataFrame):
        """Create monthly breakdown sheet."""
        if df.empty:
            return
        
        ws = self.wb.create_sheet("Monthly")
        
        columns = [
            ('invoice_month', 'Month', 12),
            ('revenue', 'Revenue (USD)', 15),
            ('gross_profit', 'Gross Profit (USD)', 18),
            ('gp1', 'GP1 (USD)', 15),
            ('gp_percent', 'GP %', 10),
            ('customer_count', 'Customers', 12),
            ('cumulative_revenue', 'Cumulative Revenue', 18),
            ('cumulative_gp', 'Cumulative GP', 15),
        ]
        
        # Write headers
        for col_idx, (col_name, header, width) in enumerate(columns, 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.fill = self.header_fill
            cell.font = self.header_font
            cell.alignment = self.center_align
            cell.border = self.cell_border
            ws.column_dimensions[get_column_letter(col_idx)].width = width
        
        # Write data
        for row_idx, row_data in enumerate(df.itertuples(index=False), 2):
            for col_idx, (col_name, _, _) in enumerate(columns, 1):
                try:
                    value = getattr(row_data, col_name) if hasattr(row_data, col_name) else df.iloc[row_idx - 2][col_name]
                except:
                    value = ''
                
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.border = self.cell_border
                
                if col_name in ['revenue', 'gross_profit', 'gp1', 'cumulative_revenue', 'cumulative_gp']:
                    cell.number_format = self.currency_format
                    cell.alignment = self.right_align
                elif col_name == 'gp_percent':
                    cell.alignment = self.right_align
                elif col_name in ['customer_count']:
                    cell.alignment = self.center_align
        
        # Freeze header
        ws.freeze_panes = 'A2'
    
    # =========================================================================
    # DETAIL SHEET
    # =========================================================================
    
    def _create_detail_sheet(self, df: pd.DataFrame):
        """Create detailed transactions sheet."""
        if df.empty:
            return
        
        ws = self.wb.create_sheet("Details")
        
        # Select relevant columns
        detail_columns = [
            'inv_date', 'inv_number', 'sales_name', 'customer', 
            'product_pn', 'brand', 'sales_by_split_usd', 
            'gross_profit_by_split_usd', 'split_rate_percent'
        ]
        
        # Filter to available columns
        available_cols = [c for c in detail_columns if c in df.columns]
        
        if not available_cols:
            return
        
        export_df = df[available_cols].copy()
        
        # Rename columns for display
        rename_map = {
            'inv_date': 'Invoice Date',
            'inv_number': 'Invoice #',
            'sales_name': 'Salesperson',
            'customer': 'Customer',
            'product_pn': 'Product',
            'brand': 'Brand',
            'sales_by_split_usd': 'Revenue (USD)',
            'gross_profit_by_split_usd': 'GP (USD)',
            'split_rate_percent': 'Split %'
        }
        
        export_df.rename(columns=rename_map, inplace=True)
        
        # Write to sheet
        for col_idx, column in enumerate(export_df.columns, 1):
            cell = ws.cell(row=1, column=col_idx, value=column)
            cell.fill = self.header_fill
            cell.font = self.header_font
            cell.alignment = self.center_align
            cell.border = self.cell_border
            ws.column_dimensions[get_column_letter(col_idx)].width = 15
        
        for row_idx, row in enumerate(export_df.itertuples(index=False), 2):
            for col_idx, value in enumerate(row, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.border = self.cell_border
        
        # Freeze header
        ws.freeze_panes = 'A2'


