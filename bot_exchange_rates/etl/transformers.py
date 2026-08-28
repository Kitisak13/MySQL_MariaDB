import re
import pandas as pd
import numpy as np
from typing import Optional

def parse_currency_info(currency_code: str, raw_name: str) -> dict:
    """
    Parses country name, currency name, and unit multiplier from BOT currency description.
    Example: 'ญี่ปุ่น : เยน (100 เยน) (JPY)' -> Country: ญี่ปุ่น, Name: เยน, Multiplier: 100
    """
    code = currency_code.strip()
    raw = raw_name.strip()
    
    parts = raw.split(" : ")
    country = parts[0].strip() if len(parts) > 1 else raw
    remainder = parts[1].strip() if len(parts) > 1 else raw

    # Detect unit multiplier e.g. (100 เยน), (1,000 รูเปีย)
    unit_multiplier = 1
    unit_match = re.search(r"\(([\d,]+)\s*([^)]+)\)", remainder)
    if unit_match and unit_match.group(1).replace(",", "").isdigit():
        val = int(unit_match.group(1).replace(",", ""))
        if val > 1:
            unit_multiplier = val

    # Clean currency name by stripping code and multiplier annotations
    cname = remainder
    cname = re.sub(r"\s*\([A-Z]{3}\)$", "", cname)
    cname = re.sub(r"\s*\([\d,]+\s*[^)]+\)", "", cname).strip()

    return {
        "currency_code": code,
        "country_name": country,
        "currency_name": cname,
        "unit_multiplier": unit_multiplier
    }

def extract_currency_dimension(csv_path: str) -> pd.DataFrame:
    """
    Extracts unique currencies from the historical unpivoted file to populate dim_currency.
    """
    df = pd.read_csv(csv_path, usecols=["Currency_id", "Currency"], low_memory=False)
    unique_rows = df.drop_duplicates(subset=["Currency_id"]).dropna()
    
    records = []
    for _, row in unique_rows.iterrows():
        records.append(parse_currency_info(row["Currency_id"], row["Currency"]))
        
    dim_df = pd.DataFrame(records)
    dim_df.sort_values(by="currency_code", inplace=True)
    return dim_df

def transform_historical_unpivoted(csv_path: str) -> pd.DataFrame:
    """
    Transforms File 1 (2002-2024 unpivoted EAV format) into wide fact table format.
    - Drops 'อัตรากลาง'
    - Maps 'ซื้อเงินโอน', 'ซื้อเงินโอน 1/', 'ซื้อ' -> buying_transfer
    - Maps 'ซื้อตั๋วเงิน' -> buying_sight_bill
    - Maps 'ขาย' -> selling
    - Normalizes MM/DD/YYYY dates to YYYY-MM-DD
    - Pivots into a single record per date & currency
    """
    df = pd.read_csv(
        csv_path,
        usecols=["Currency_id", "Type_id", "Value", "Date"],
        low_memory=False
    )
    
    # 1. Filter out mid rate
    df = df[df["Type_id"] != "อัตรากลาง"].copy()
    
    # 2. Map rate types
    type_map = {
        "ซื้อตั๋วเงิน": "buying_sight_bill",
        "ซื้อเงินโอน": "buying_transfer",
        "ซื้อเงินโอน 1/": "buying_transfer",
        "ซื้อ": "buying_transfer",
        "ขาย": "selling"
    }
    df["rate_type"] = df["Type_id"].map(type_map)
    df.dropna(subset=["rate_type"], inplace=True)
    
    # 3. Clean value column
    df["Value"] = pd.to_numeric(df["Value"], errors="coerce")
    
    # 4. Standardize date (File 1 format: MM/DD/YYYY)
    df["rate_date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y", errors="coerce").dt.strftime("%Y-%m-%d")
    df.dropna(subset=["rate_date"], inplace=True)
    
    # 5. Clean currency code
    df["currency_code"] = df["Currency_id"].str.strip()
    
    # 6. Pivot table
    df_pivoted = df.pivot_table(
        index=["rate_date", "currency_code"],
        columns="rate_type",
        values="Value",
        aggfunc="first"
    ).reset_index()
    
    # Ensure all target columns exist
    for col in ["buying_sight_bill", "buying_transfer", "selling"]:
        if col not in df_pivoted.columns:
            df_pivoted[col] = np.nan
            
    df_pivoted = df_pivoted[["rate_date", "currency_code", "buying_sight_bill", "buying_transfer", "selling"]]
    return df_pivoted

def transform_monthly_pivoted(csv_path_or_df) -> pd.DataFrame:
    """
    Transforms File 2 or monthly batch update CSVs (Wide format) into fact table format.
    - Columns: ['สกุลเงิน', 'ซื้อตั๋วเงิน', 'ซื้อเงินโอน', 'ขาย', 'Date']
    - Standardizes DD/MM/YYYY dates to YYYY-MM-DD
    """
    if isinstance(csv_path_or_df, str):
        df = pd.read_csv(csv_path_or_df, low_memory=False)
    else:
        df = csv_path_or_df.copy()
        
    rename_map = {
        "สกุลเงิน": "currency_code",
        "ซื้อตั๋วเงิน": "buying_sight_bill",
        "ซื้อเงินโอน": "buying_transfer",
        "ขาย": "selling",
        "Date": "rate_date"
    }
    df.rename(columns=rename_map, inplace=True)
    
    # Clean currency code
    df["currency_code"] = df["currency_code"].astype(str).str.strip()
    
    # Clean numeric columns
    for col in ["buying_sight_bill", "buying_transfer", "selling"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = np.nan
            
    # Standardize date (Format: DD/MM/YYYY or D/M/YYYY)
    df["rate_date"] = pd.to_datetime(df["rate_date"], format="%d/%m/%Y", errors="coerce").dt.strftime("%Y-%m-%d")
    df.dropna(subset=["rate_date", "currency_code"], inplace=True)
    
    df = df[["rate_date", "currency_code", "buying_sight_bill", "buying_transfer", "selling"]]
    return df
