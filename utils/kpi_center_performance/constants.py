# utils/kpi_center_performance/constants.py
"""
Constants for KPI Center Performance Module

"""

# =====================================================================
# ROLE DEFINITIONS
# =====================================================================

# Roles allowed to access this page
ALLOWED_ROLES = ['admin', 'GM', 'MD', 'sales_manager']

# =====================================================================
# COLOR SCHEME - SYNCED with Salesperson page
# =====================================================================

COLORS = {
    # Primary colors for charts
    "primary": "#1f77b4",              # Blue
    "secondary": "#aec7e8",            # Light Blue
    "neutral": "#d3d3d3",              # Light Gray
    
    # Metric colors
    "revenue": "#FFA500",              # Orange
    "gross_profit": "#1f77b4",         # Blue
    "gp1": "#2ca02c",                  # Green
    "gross_profit_1": "#2ca02c",       # Green (same as gp1)
    "gross_profit_percent": "#800080", # Purple
    
    # Target & Achievement
    "target": "#d62728",               # Red
    "achievement": "#2ca02c",          # Green
    "achievement_good": "#28a745",     # Green (≥100%)
    "achievement_bad": "#dc3545",      # Red (<100%)
    
    # Complex KPIs
    "new_customer": "#17becf",         # Cyan
    "new_product": "#bcbd22",          # Olive
    "new_business": "#e377c2",         # Pink
    
    # YoY Comparison
    "current_year": "#1f77b4",         # Blue
    "previous_year": "#aec7e8",        # Light Blue
    "yoy_positive": "#28a745",         # Green
    "yoy_negative": "#dc3545",         # Red
    
    # Customer count
    "customer_count": "#27ae60",       # Green
    
    # Risk indicators
    "overdue": "#dc3545",              # Red
    "at_risk": "#ffc107",              # Yellow
    "ok": "#28a745",                   # Green
    
    # Misc
    "text_dark": "#333333",
    "text_light": "#666666",
    "grid": "#e0e0e0",
}

# =====================================================================
# MONTH ORDER
# =====================================================================

MONTH_ORDER = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
]

# =====================================================================
# PERIOD DEFINITIONS
# =====================================================================

PERIOD_TYPES = ['YTD', 'QTD', 'MTD', 'Custom']

# KPI Center Types
KPI_CENTER_TYPES = ['Sales Team', 'Product Line', 'Region', 'Channel', 'Other']

# =====================================================================
# BUSINESS LOGIC SETTINGS
# =====================================================================

# Lookback period for "new" customer/product determination
LOOKBACK_YEARS = 5

# =====================================================================
# CHART DIMENSIONS
# =====================================================================

CHART_WIDTH = 'container'  # Use container width for responsive charts
CHART_HEIGHT = 350

# =====================================================================
# CACHE SETTINGS
# =====================================================================

CACHE_TTL_SECONDS = 1800  # 30 minutes

# =====================================================================
# EXPORT SETTINGS
# =====================================================================

EXCEL_STYLES = {
    "header_fill_color": "1f77b4",
    "header_font_color": "FFFFFF",
    "currency_format": '#,##0',
    "percent_format": '0.0%',
    "date_format": 'YYYY-MM-DD',
}