from typing import List, Dict, Any, Tuple, Optional
from etl.normalizers import clean_str, to_decimal, format_date

def transform_api_export_rows(raw_rows: List[Dict[str, Any]], year: int, month: int, hs_11_code: str) -> List[Dict[str, Any]]:
    """
    Transforms raw JSON records from MOC Trade Report API into structured fact records.
    """
    export_date = format_date(year, month)
    transformed = []

    for item in raw_rows:
        country_code = clean_str(item.get("country_code"))
        if not country_code:
            continue

        transformed.append({
            "export_date": export_date,
            "export_year": year,
            "export_month": month,
            "country_code": country_code[:10],
            "country_name_th": clean_str(item.get("country_name_th")),
            "country_name_en": clean_str(item.get("country_name_en")),
            "hs_11_code": hs_11_code,
            "quantity": to_decimal(item.get("quantity")),
            "acc_quantity": to_decimal(item.get("acc_quantity")),
            "value_usd": to_decimal(item.get("value_usd")),
            "acc_value_usd": to_decimal(item.get("acc_value_usd")),
            "value_thb": to_decimal(item.get("value_baht")),
            "acc_value_thb": to_decimal(item.get("acc_value_baht")),
            "unit_code": clean_str(item.get("unit_code"))
        })

    return transformed
