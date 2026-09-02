# Data Pipeline & Warehouse: Thailand Food Export (`food_export`)

## 1. System Overview
The **`food_export`** database is designed for high-performance extraction, normalization, and analytical warehousing of Thailand's international food, agricultural, and commodity trade export statistics from the **Ministry of Commerce (MOC Trade Report API)**.

---

## 2. Master Dimension Catalog: `dim_hs11_code`
Contains all **30,906 unique 11-digit HS statistical codes** consolidated across all 4 customs tariff revisions (2007, 2012, 2017, 2022) with a complete 4-level hierarchy:
- **Level 2 (Chapter):** 2-digit code (`hs_2_code`) + Thai & English Chapter Descriptions
- **Level 4 (Heading):** 4-digit code (`hs_4_code`) + Thai & English Heading Descriptions
- **Level 8 (Subheading):** 8-digit code (`hs_8_code`) + Thai & English Subheading Descriptions
- **Level 11 (Statistical):** 11-digit code (`hs_11_code`) + Thai & English Commodity Descriptions
- **Lifecycle Tracking:** `first_seen_revision`, `latest_revision`, and `is_active_2022`.

---

## 3. Quick Start & Execution

### Step 1: Initialize Database & Schema
```powershell
python db-food-export/database/init_db.py
```

### Step 2: Build / Rebuild Master HS Dimension Table
Fetches all revisions from MOC API and upserts 30,906 records into MariaDB:
```powershell
python db-food-export/scripts/build_dim_hs_code.py
```

### Step 3: Verify Integrity & Observability
```powershell
python db-food-export/scripts/verify_database.py
```
