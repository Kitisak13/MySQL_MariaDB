from decimal import Decimal, InvalidOperation
from datetime import date
from typing import Optional, Any

def clean_str(val: Any) -> Optional[str]:
    """Strips whitespace and nullifies empty strings."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s and s.lower() not in ("nan", "none", "null", "") else None

def to_decimal(val: Any, default: Decimal = Decimal("0.0000")) -> Decimal:
    """Converts value to Decimal with 4-decimal precision."""
    if val is None:
        return default
    try:
        s = str(val).replace(",", "").strip()
        if not s or s.lower() in ("nan", "none", "null", ""):
            return default
        return round(Decimal(s), 4)
    except (InvalidOperation, ValueError, TypeError):
        return default

def format_date(year: int, month: int) -> date:
    """Returns the first day of the observation month (e.g. 2016-05-01)."""
    return date(year, month, 1)
