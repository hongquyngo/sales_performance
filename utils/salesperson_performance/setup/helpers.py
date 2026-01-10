# utils/salesperson_performance/setup/helpers.py
"""
Helper Utilities for Setup Module

Contains utility functions used across setup sub-tabs:
- Period validation (active/expired status checks)
- Date formatting helpers

VERSION: 1.0.0
"""

from datetime import date
from typing import Optional


def is_period_active(period_str: str, today_str: Optional[str] = None) -> bool:
    """
    Check if today falls within the effective period.
    
    Args:
        period_str: Period string in format "YYYY-MM-DD -> YYYY-MM-DD"
        today_str: Today's date in format "YYYY-MM-DD" (defaults to current date)
    
    Returns:
        True if period is active (today is within range)
        
    Example:
        >>> is_period_active("2025-01-01 -> 2025-12-31", "2025-06-15")
        True
        >>> is_period_active("2024-01-01 -> 2024-12-31", "2025-06-15")
        False
    """
    if today_str is None:
        today_str = date.today().strftime('%Y-%m-%d')
    
    if not period_str or ' -> ' not in str(period_str):
        return True  # No period defined = always active
    
    try:
        start, end = str(period_str).split(' -> ')
        return start.strip() <= today_str <= end.strip()
    except (ValueError, AttributeError):
        return True


def is_period_expired(period_str: str, today_str: Optional[str] = None) -> bool:
    """
    Check if the effective period has ended.
    
    Args:
        period_str: Period string in format "YYYY-MM-DD -> YYYY-MM-DD"
        today_str: Today's date in format "YYYY-MM-DD" (defaults to current date)
    
    Returns:
        True if period has expired (end date < today)
        
    Example:
        >>> is_period_expired("2024-01-01 -> 2024-12-31", "2025-06-15")
        True
        >>> is_period_expired("2025-01-01 -> 2025-12-31", "2025-06-15")
        False
    """
    if today_str is None:
        today_str = date.today().strftime('%Y-%m-%d')
    
    if not period_str or ' -> ' not in str(period_str):
        return False  # No period defined = never expired
    
    try:
        _, end = str(period_str).split(' -> ')
        return end.strip() < today_str
    except (ValueError, AttributeError):
        return False


def format_period_display(period_str: str) -> str:
    """
    Format period string for display.
    
    Args:
        period_str: Period string in format "YYYY-MM-DD -> YYYY-MM-DD"
        
    Returns:
        Formatted string like "Jan 01, 2025 - Dec 31, 2025"
    """
    if not period_str or ' -> ' not in str(period_str):
        return "No period defined"
    
    try:
        start_str, end_str = str(period_str).split(' -> ')
        start = date.fromisoformat(start_str.strip())
        end = date.fromisoformat(end_str.strip())
        return f"{start.strftime('%b %d, %Y')} - {end.strftime('%b %d, %Y')}"
    except (ValueError, AttributeError):
        return period_str


def get_period_status(period_str: str, today_str: Optional[str] = None) -> str:
    """
    Get the status of a period as a string.
    
    Args:
        period_str: Period string in format "YYYY-MM-DD -> YYYY-MM-DD"
        today_str: Today's date (defaults to current date)
        
    Returns:
        'active', 'expired', 'future', or 'undefined'
    """
    if today_str is None:
        today_str = date.today().strftime('%Y-%m-%d')
    
    if not period_str or ' -> ' not in str(period_str):
        return 'undefined'
    
    try:
        start, end = str(period_str).split(' -> ')
        start = start.strip()
        end = end.strip()
        
        if today_str < start:
            return 'future'
        elif today_str > end:
            return 'expired'
        else:
            return 'active'
    except (ValueError, AttributeError):
        return 'undefined'
