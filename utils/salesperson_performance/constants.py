# utils/salesperson_performance/constants.py
"""
Constants for Salesperson Performance Module

Centralized configuration for:
- Role definitions
- Color schemes
- Chart settings
- KPI configurations
- Period definitions
"""

# =====================================================================
# ROLE DEFINITIONS
# =====================================================================

# Full access: can view all salespeople across all entities
FULL_ACCESS_ROLES = ['admin', 'GM', 'MD']

# Team access: can view self + direct/indirect reports
TEAM_ACCESS_ROLES = ['sales_manager']

# Self access: can only view own data
SELF_ACCESS_ROLES = ['sales', 'viewer']

# =====================================================================
# COLOR SCHEME
# =====================================================================

COLORS = {
    # Primary metrics
    "revenue": "#FFA500",              # Orange
    "gross_profit": "#1f77b4",         # Blue
    "gp1": "#2ca02c",                  # Green
    "gross_profit_percent": "#800080", # Purple
    
    # Target & Achievement
    "target": "#d62728",               # Red
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

MONTH_MAPPING = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"
}

# =====================================================================
# PERIOD DEFINITIONS
# =====================================================================

PERIOD_TYPES = ['YTD', 'QTD', 'MTD', 'Custom']

QUARTER_MONTHS = {
    1: [1, 2, 3],
    2: [4, 5, 6],
    3: [7, 8, 9],
    4: [10, 11, 12]
}

# =====================================================================
# KPI CONFIGURATIONS
# =====================================================================

KPI_TYPES = {
    "revenue": {
        "name": "revenue",
        "display_name": "Revenue",
        "unit": "USD",
        "format": "${:,.0f}",
        "icon": "💰"
    },
    "gross_profit": {
        "name": "gross_profit",
        "display_name": "Gross Profit",
        "unit": "USD",
        "format": "${:,.0f}",
        "icon": "📈"
    },
    "num_new_customers": {
        "name": "num_new_customers",
        "display_name": "New Customers",
        "unit": "customer",
        "format": "{:.1f}",
        "icon": "👥"
    },
    "num_new_products": {
        "name": "num_new_products",
        "display_name": "New Products",
        "unit": "product",
        "format": "{:.1f}",
        "icon": "📦"
    },
    "new_business_revenue": {
        "name": "new_business_revenue",
        "display_name": "New Business Revenue",
        "unit": "USD",
        "format": "${:,.0f}",
        "icon": "💼"
    },
}

# =====================================================================
# BUSINESS LOGIC SETTINGS
# =====================================================================

# Lookback period for "new" customer/product determination
# A customer is "new" if their first invoice is within lookback period
LOOKBACK_YEARS = 5

# Commission multiplier for GP1 calculation (from existing views)
COMMISSION_MULTIPLIER = 1.2

# =====================================================================
# CHART DIMENSIONS
# =====================================================================

CHART_WIDTH = 800
CHART_HEIGHT = 400

PIE_CHART_WIDTH = 400
PIE_CHART_HEIGHT = 300

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
