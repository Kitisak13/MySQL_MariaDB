import re
from datetime import datetime
from typing import Optional, Any
import pandas as pd
import numpy as np

def clean_text(val: Any, max_len: Optional[int] = None) -> Optional[str]:
    """Cleans text values, removes leading/trailing spaces, and converts NaNs to None."""
    if pd.isna(val) or val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "null", "n/a"):
        return None
    if max_len:
        s = s[:max_len]
    return s

def clean_product_id(val: Any) -> Optional[str]:
    """Cleans product_id string (e.g. 'P11001')."""
    s = clean_text(val, max_len=20)
    if not s:
        return None
    return s.upper()

def parse_date(val: Any) -> Optional[str]:
    """
    Parses various date formats (e.g. '2026-01-05T00:00:00', '2026-01-05', '05/01/2026')
    into standard 'YYYY-MM-DD' database format.
    """
    if pd.isna(val) or val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "null"):
        return None

    # Common ISO format '2026-01-05T00:00:00'
    if "T" in s:
        s = s.split("T")[0]

    # Clean any whitespace or extra characters
    s = s.split(" ")[0].strip()

    # If format is already YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s

    # Try parsing alternative formats
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return None

def clean_decimal(val: Any) -> Optional[float]:
    """Cleans numerical values and returns float rounded to 2 decimals, or None."""
    if pd.isna(val) or val is None:
        return None
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return None
        return round(f, 2)
    except (ValueError, TypeError):
        return None
