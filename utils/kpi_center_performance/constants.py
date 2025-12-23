# utils/kpi_center_performance/constants.py
"""
Constants for KPI Center Performance Module

Centralized configuration for:
- Role definitions (simplified - page-level access only)
- Color schemes
- Chart settings
- KPI configurations
- Period definitions

VERSION: 1.0.0
"""

# =====================================================================
# ROLE DEFINITIONS (Simplified - page-level access only)
# =====================================================================

# Roles that can access KPI Center Performance page
ALLOWED_ROLES = ['admin', 'GM', 'MD', 'sales_manager']

# =====================================================================
# COLOR SCHEME
# =====================================================================

COLORS = {
    # Primary/Secondary (general use)
    "primary": "#1f77b4",              # Blue
    "secondary": "#ff7f0e",            # Orange
    
    # Primary metrics
    "revenue": "#FFA500",              # Orange
    "gross_profit": "#1f77b4",         # Blue
    "gp1": "#2ca02c",                  # Green
    "gross_profit_1": "#2ca02c",       # Green (same as gp1)
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
    
    # KPI Center Types
    "territory": "#3498db",            # Blue
    "internal": "#9b59b6",             # Purple
    "other": "#95a5a6",                # Gray
    
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
    "gross_profit_1": {
        "name": "gross_profit_1",
        "display_name": "GP1",
        "unit": "USD",
        "format": "${:,.0f}",
        "icon": "📊"
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
# KPI CENTER TYPE DEFINITIONS
# =====================================================================

KPI_CENTER_TYPES = {
    "TERRITORY": {
        "name": "Territory",
        "icon": "🌍",
        "color": "#3498db"
    },
    "INTERNAL": {
        "name": "Internal",
        "icon": "🏢",
        "color": "#9b59b6"
    },
}

# =====================================================================
# BUSINESS LOGIC SETTINGS
# =====================================================================

# Lookback period for "new" customer/product determination
LOOKBACK_YEARS = 5

# =====================================================================
# CHART DIMENSIONS
# =====================================================================

CHART_WIDTH = 800
CHART_HEIGHT = 400

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