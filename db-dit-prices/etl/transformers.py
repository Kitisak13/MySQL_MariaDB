import pandas as pd
from typing import List, Tuple, Optional, Dict, Any
from etl.normalizers import parse_date, clean_product_id, clean_decimal, clean_text

def transform_dim_products(df: pd.DataFrame) -> List[Tuple]:
    """
    Transforms DataFrame of product catalog into tuples for dim_product insertion:
    (product_id, product_name, category_name, group_name, unit)
    """
    records = []
    seen = set()

    for _, row in df.iterrows():
        p_id = clean_product_id(row.get("product_id"))
        if not p_id or p_id in seen:
            continue
        seen.add(p_id)

        p_name = clean_text(row.get("product_name"), max_len=255)
        if not p_name:
            continue
        cat_name = clean_text(row.get("category_name"), max_len=100)
        grp_name = clean_text(row.get("group_name"), max_len=100)
        unit = clean_text(row.get("unit"), max_len=50)

        records.append((p_id, p_name, cat_name, grp_name, unit))

    return records

def transform_fact_prices_chunk(df: pd.DataFrame) -> List[Tuple]:
    """
    Transforms a DataFrame chunk into tuples for fact_daily_product_price insertion:
    (price_date, product_id, price_min, price_max, price_avg)
    """
    records = []

    for _, row in df.iterrows():
        p_date = parse_date(row.get("date"))
        p_id = clean_product_id(row.get("product_id"))

        if not p_date or not p_id:
            continue

        p_min = clean_decimal(row.get("price_min"))
        p_max = clean_decimal(row.get("price_max"))

        # Auto-correct inverted min/max if surveyor entered them in reverse
        if p_min is not None and p_max is not None and p_min > p_max:
            p_min, p_max = p_max, p_min

        # Calculate average price
        if p_min is not None and p_max is not None:
            p_avg = round((p_min + p_max) / 2.0, 2)
        elif p_min is not None:
            p_avg = p_min
        elif p_max is not None:
            p_avg = p_max
        else:
            p_avg = None

        records.append((p_date, p_id, p_min, p_max, p_avg))

    return records
