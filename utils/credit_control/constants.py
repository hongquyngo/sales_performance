# utils/credit_control/constants.py
"""Constants for Credit Control Module. VERSION: 1.0.0"""

ALERT_LEVELS = {
    'BLOCKED':          {'severity': 'critical', 'color': '#8B0000', 'icon': '🚫', 'order': 0},
    'OVER_LIMIT':       {'severity': 'critical', 'color': '#DC3545', 'icon': '🔴', 'order': 1},
    'OVERDUE_BLOCK':    {'severity': 'critical', 'color': '#DC3545', 'icon': '🔴', 'order': 2},
    'LIMIT_WARNING':    {'severity': 'warning',  'color': '#FFC107', 'icon': '🟡', 'order': 3},
    'OVERDUE_WARNING':  {'severity': 'warning',  'color': '#FF8C00', 'icon': '🟠', 'order': 4},
    'HAS_OUTSTANDING':  {'severity': 'info',     'color': '#17A2B8', 'icon': '🔵', 'order': 5},
    'CLEAR':            {'severity': 'ok',       'color': '#28A745', 'icon': '🟢', 'order': 6},
    'VIP_EXEMPT':       {'severity': 'ok',       'color': '#6F42C1', 'icon': '👑', 'order': 7},
}

RECIPIENT_ROLES = {
    'assigned_sales':   {'source': 'ar_view'},
    'sales_manager':    {'source': 'employee_hierarchy'},
    'customer_contact': {'source': 'contacts_table'},
    'finance':          {'source': 'email_group', 'group_name': 'Finance'},
    'gm':               {'source': 'email_group', 'group_name': 'Management'},
}

DEFAULT_COOLDOWN_DAYS = 7
MAX_NOTIFICATIONS_PER_CUSTOMER_PER_DAY = 3
