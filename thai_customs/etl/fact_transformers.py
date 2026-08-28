import re
import pandas as pd
import numpy as np
from typing import Tuple, List, Dict, Any
from etl.normalizers import normalize_year, pad_hs_code, pad_stat_code, clean_text, clean_decimal

def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Strips leading/trailing whitespace from column names."""
    df.columns = [str(c).strip() for c in df.columns]
    return df

def find_column(df: pd.DataFrame, candidates: List[str]) -> str:
    """Finds first matching column name from a list of candidate strings."""
    for cand in candidates:
        if cand in df.columns:
            return cand
    for cand in candidates:
        for c in df.columns:
            if cand.lower() in c.lower():
                return c
    raise KeyError(f"None of {candidates} found in dataframe columns: {df.columns.tolist()}")

def transform_country_chunk(chunk: pd.DataFrame, trade_type: str) -> Tuple[List[tuple], List[tuple], float]:
    """
    Transforms chunk for ctm_06_11 (Import) or ctm_06_12 (Export).
    Returns (fact_records, hs_dim_records, total_value_thb).
    """
    df = clean_column_names(chunk)
    
    val_col = find_column(df, ["มูลค่านำเข้าเงินบาท", "มูลค่าส่งออกเงินบาท", "มูลค่า"])
    country_col = find_column(df, ["รหัสประเทศกำเนิด", "รหัสประเทศปลายทาง", "รหัสประเทศ"])
    unit_col = find_column(df, ["หน่วยตามรหัสสถิติ", "หน่วยตามรหัสสถิต", "หน่วย"])
    
    fact_records = []
    hs_records = []
    total_val = 0.0

    for _, row in df.iterrows():
        y_raw = row["ปีแม่แบบ"]
        m_raw = row["เดือนแม่แบบ"]
        
        ce_year = normalize_year(y_raw)
        month = int(float(m_raw)) if pd.notna(m_raw) else 1
        period_date = f"{ce_year:04d}-{month:02d}-01"
        
        hs = pad_hs_code(row["พิกัดศุลกากร 8 หลัก"])
        stat = pad_stat_code(row["รหัสสถิติ"])
        unit = clean_text(row.get(unit_col), max_len=10) or ""
        desc_th = clean_text(row.get("คำอธิบายไทย"), max_len=500)
        desc_en = clean_text(row.get("คำอธิบาย"), max_len=500)
        
        country = clean_text(row.get(country_col), max_len=10) or "UNKNOWN"
        qty = clean_decimal(row.get("น้ำหนัก/ปริมาณสถิติ"))
        val = clean_decimal(row.get(val_col)) or 0.0
        total_val += val
        
        fact_records.append((
            period_date, ce_year, month, trade_type, country, hs, stat, unit, qty, val
        ))
        
        if desc_th or desc_en:
            hs_records.append((hs, stat, unit, desc_th, desc_en))
            
    return fact_records, hs_records, total_val

def transform_transport_chunk(chunk: pd.DataFrame, trade_type: str) -> Tuple[List[tuple], List[tuple], float]:
    """
    Transforms chunk for ctm_06_17 (Import) or ctm_06_18 (Export).
    Returns (fact_records, transport_dim_records, total_value_thb).
    """
    df = clean_column_names(chunk)
    
    val_col = find_column(df, ["มูลค่านำเข้าเงินบาท", "มูลค่าส่งออกเงินบาท", "มูลค่า"])
    trans_code_col = find_column(df, ["ขนส่งโดยทาง", "ประเภทการขนส่ง"])
    trans_desc_col = find_column(df, ["คำอธิบายขนส่งโดยทาง", "คำอธิบายประเภทการขนส่ง", "คำอธิบาย"])
    unit_col = find_column(df, ["หน่วยตามรหัสสถิติ", "หน่วยตามรหัสสถิต", "หน่วย"])
    
    fact_records = []
    trans_dim_records = []
    total_val = 0.0

    for _, row in df.iterrows():
        ce_year = normalize_year(row["ปีแม่แบบ"])
        month = int(float(row["เดือนแม่แบบ"])) if pd.notna(row["เดือนแม่แบบ"]) else 1
        period_date = f"{ce_year:04d}-{month:02d}-01"
        
        hs = pad_hs_code(row["พิกัดศุลกากร 8 หลัก"])
        stat = pad_stat_code(row["รหัสสถิติ"])
        unit = clean_text(row.get(unit_col), max_len=10) or ""
        
        try:
            trans_code = int(float(row.get(trans_code_col, 0)))
        except Exception:
            trans_code = 0
            
        trans_desc = clean_text(row.get(trans_desc_col), max_len=100) or "ไม่ระบุ"
        qty = clean_decimal(row.get("น้ำหนัก/ปริมาณสถิติ"))
        val = clean_decimal(row.get(val_col)) or 0.0
        total_val += val
        
        fact_records.append((
            period_date, ce_year, month, trade_type, trans_code, hs, stat, unit, qty, val
        ))
        
        if trans_code > 0:
            trans_dim_records.append((trans_code, trans_desc))
            
    return fact_records, trans_dim_records, total_val

def transform_port_chunk(chunk: pd.DataFrame, trade_type: str) -> Tuple[List[tuple], List[tuple], float]:
    """
    Transforms chunk for ctm_06_15 (Import) or ctm_06_16 (Export).
    Returns (fact_records, port_dim_records, total_value_thb).
    """
    df = clean_column_names(chunk)
    
    val_col = find_column(df, ["มูลค่านำเข้าเงินบาท", "มูลค่าส่งออกเงินบาท", "มูลค่า"])
    port_col = find_column(df, ["ด่าน/สถานที่ตรวจปล่อย", "ด่าน/สถานที่รับบรรทุก", "ท่า/ด่านศุลกากร", "ด่านศุลกากร"])
    office_col = find_column(df, ["สำนัก/สำนักงานศุลกากร", "สำนักงานศุลกากร"])
    unit_col = find_column(df, ["หน่วยตามรหัสสถิติ", "หน่วยตามรหัสสถิต", "หน่วย"])
    
    fact_records = []
    port_dim_records = []
    total_val = 0.0

    for _, row in df.iterrows():
        ce_year = normalize_year(row["ปีแม่แบบ"])
        month = int(float(row["เดือนแม่แบบ"])) if pd.notna(row["เดือนแม่แบบ"]) else 1
        period_date = f"{ce_year:04d}-{month:02d}-01"
        
        hs = pad_hs_code(row["พิกัดศุลกากร 8 หลัก"])
        stat = pad_stat_code(row["รหัสสถิติ"])
        unit = clean_text(row.get(unit_col), max_len=10) or ""
        
        port_name = clean_text(row.get(port_col), max_len=255) or "ไม่ระบุ"
        office_short = clean_text(row.get(office_col), max_len=50)
        
        qty = clean_decimal(row.get("น้ำหนัก/ปริมาณสถิติ"))
        val = clean_decimal(row.get(val_col)) or 0.0
        total_val += val
        
        fact_records.append((
            period_date, ce_year, month, trade_type, port_name, office_short, hs, stat, unit, qty, val
        ))
        
        port_dim_records.append((port_name, office_short))
            
    return fact_records, port_dim_records, total_val

def transform_office_chunk(chunk: pd.DataFrame, trade_type: str) -> Tuple[List[tuple], List[tuple], float]:
    """
    Transforms chunk for ctm_06_13 (Import) or ctm_06_14 (Export).
    Returns (fact_records, office_dim_records, total_value_thb).
    """
    df = clean_column_names(chunk)
    
    val_col = find_column(df, ["มูลค่านำเข้าเงินบาท", "มูลค่าส่งออกเงินบาท", "มูลค่า"])
    office_col = find_column(df, ["สำนัก/สำนักงานศุลกากร", "สำนักงานศุลกากร"])
    unit_col = find_column(df, ["หน่วยตามรหัสสถิติ", "หน่วยตามรหัสสถิต", "หน่วย"])
    
    fact_records = []
    office_dim_records = []
    total_val = 0.0

    for _, row in df.iterrows():
        ce_year = normalize_year(row["ปีแม่แบบ"])
        month = int(float(row["เดือนแม่แบบ"])) if pd.notna(row["เดือนแม่แบบ"]) else 1
        period_date = f"{ce_year:04d}-{month:02d}-01"
        
        hs = pad_hs_code(row["พิกัดศุลกากร 8 หลัก"])
        stat = pad_stat_code(row["รหัสสถิติ"])
        unit = clean_text(row.get(unit_col), max_len=10) or ""
        
        office_name = clean_text(row.get(office_col), max_len=255) or "ไม่ระบุ"
        qty = clean_decimal(row.get("น้ำหนัก/ปริมาณสถิติ"))
        val = clean_decimal(row.get(val_col)) or 0.0
        total_val += val
        
        fact_records.append((
            period_date, ce_year, month, trade_type, office_name, hs, stat, unit, qty, val
        ))
        
        office_dim_records.append((office_name,))
            
    return fact_records, office_dim_records, total_val
