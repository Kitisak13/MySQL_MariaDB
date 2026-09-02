# Data Dictionary - Food & Commodity Export Data Warehouse (`food_export`)

## Overview
Database **`food_export`** is designed to store, manage, and analyze Thailand's international food and commodity export statistics sourced from the Ministry of Commerce (MOC Trade Report API).

---

## Entity-Relationship Diagram (ERD)

```mermaid
erDiagram
    dim_hs11_code ||--o{ fact_food_export : "categorizes"
    dim_country ||--o{ fact_food_export : "destination"

    dim_hs11_code {
        char(11) hs_11_code PK "11-digit statistical code"
        text hs_11_description_th "11-digit Thai description"
        text hs_11_description_en "11-digit English description"
        char(8) hs_8_code "8-digit subheading"
        text hs_8_description_th "8-digit Thai description"
        text hs_8_description_en "8-digit English description"
        char(4) hs_4_code "4-digit heading"
        text hs_4_description_th "4-digit Thai description"
        text hs_4_description_en "4-digit English description"
        char(2) hs_2_code "2-digit chapter"
        text hs_2_description_th "2-digit Thai description"
        text hs_2_description_en "2-digit English description"
        varchar(20) unit_code "Unit code (e.g. KGM, C62)"
        varchar(50) unit_name "Unit name description"
        smallint first_seen_revision "Earliest revision (e.g. 2007)"
        smallint latest_revision "Latest revision (e.g. 2022)"
        tinyint is_active_2022 "1=Active, 0=Deprecated"
        timestamp created_at "Record creation timestamp"
        timestamp updated_at "Record update timestamp"
    }

    dim_country {
        varchar(10) country_code PK "ISO 2-letter country code"
        varchar(150) country_name_th "Country name in Thai"
        varchar(150) country_name_en "Country name in English"
        varchar(50) region_code "Geographical region code"
        varchar(100) region_name "Geographical region name"
        timestamp created_at "Record creation timestamp"
        timestamp updated_at "Record update timestamp"
    }

    fact_food_export {
        bigint id PK "Auto-incrementing surrogate ID"
        smallint export_year "Observation year (e.g. 2015-2026)"
        tinyint export_month "Observation month (1-12)"
        varchar(10) country_code FK "Destination country code"
        char(11) hs_11_code FK "11-digit HS Code"
        decimal quantity "Monthly export quantity"
        decimal acc_quantity "YTD accumulated export quantity"
        decimal value_usd "Monthly export value in USD"
        decimal acc_value_usd "YTD accumulated export value in USD"
        decimal value_thb "Monthly export value in THB"
        decimal acc_value_thb "YTD accumulated export value in THB"
        varchar(20) unit_code "Unit of measure"
        timestamp created_at "Ingestion timestamp"
        timestamp updated_at "Update timestamp"
    }

    data_ingestion_log {
        bigint id PK "Log ID"
        varchar(100) dataset_name "Dataset identifier"
        varchar(255) file_or_source "Source endpoint or description"
        date period_start "Start period of batch"
        date period_end "End period of batch"
        int total_rows "Number of rows ingested"
        char(64) file_hash "SHA-256 Hash if applicable"
        varchar(20) status "SUCCESS, PARTIAL, FAILED"
        decimal duration_seconds "Processing duration"
        timestamp ingested_at "Timestamp of log execution"
    }
```

---

## Table Schemas

### 1. `dim_hs11_code` (Master Dimension: 4-Level HS Code Hierarchy)
- **Primary Key:** `hs_11_code`
- **Total Unique Codes:** 30,906 records (across 2007, 2012, 2017, 2022 revisions)
- **Hierarchy Columns:**
  - Level 2: `hs_2_code`, `hs_2_description_th`, `hs_2_description_en`
  - Level 4: `hs_4_code`, `hs_4_description_th`, `hs_4_description_en`
  - Level 8: `hs_8_code`, `hs_8_description_th`, `hs_8_description_en`
  - Level 11: `hs_11_code`, `hs_11_description_th`, `hs_11_description_en`

### 2. `dim_country` (Destination Countries & Geographical Regions)
- **Primary Key:** `country_code`

### 3. `fact_food_export` (Monthly Trade Export Facts)
- **Primary Key:** `id`
- **Unique Constraint:** (`export_year`, `export_month`, `country_code`, `hs_11_code`)

### 4. `data_ingestion_log` (Pipeline Audit & Observability)
- **Primary Key:** `id`
