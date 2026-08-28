import re
import pandas as pd
import numpy as np
from typing import Optional, Union

def normalize_year(be_year: Union[int, str, float]) -> int:
    """
    Converts Buddhist Era (BE e.g. 2568) to Common Era (CE e.g. 2025).
    """
    try:
        y = int(float(be_year))
        if y > 2400:
            return y - 543
        return y
    except Exception:
        return 2025

def pad_hs_code(hs_val: Union[int, str, float]) -> str:
    """
    Pads HS code to 8 characters with leading zeros (e.g. 1061900 -> '01061900').
    """
    if pd.isna(hs_val) or hs_val is None:
        return "00000000"
    hs_str = re.sub(r"\D", "", str(hs_val).split(".")[0])
    return hs_str.zfill(8)[:8]

def pad_stat_code(stat_val: Union[int, str, float]) -> str:
    """
    Pads Statistical code to 3 characters with leading zeros (e.g. 90 -> '090', 0 -> '000').
    """
    if pd.isna(stat_val) or stat_val is None:
        return "000"
    stat_str = re.sub(r"\D", "", str(stat_val).split(".")[0])
    return stat_str.zfill(3)[:3]

def clean_text(val: Optional[str], max_len: int = 500) -> Optional[str]:
    """
    Strips whitespace and sanitizes text strings.
    """
    if pd.isna(val) or val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("nan", "null", "none", "n/a"):
        return None
    return s[:max_len]

def clean_decimal(val: Union[int, float, str, None]) -> Optional[float]:
    """
    Converts numeric value to clean float, converting NaN / null to None.
    """
    if pd.isna(val) or val is None:
        return None
    try:
        f = float(str(val).replace(",", "").strip())
        if np.isnan(f) or np.isinf(f):
            return None
        return f
    except Exception:
        return None
