# Data Dictionary & Entity-Relationship Documentation

## 1. Visual ER-Diagram

```mermaid
erDiagram
    dim_currency ||--o{ fact_daily_exchange_rate : "references"

    dim_currency {
        char(3) currency_code PK "ISO 4217 Currency Code"
        varchar(100) country_name "Country / Economic Zone Name (Thai)"
        varchar(100) currency_name "Currency Unit Name (Thai)"
        int unit_multiplier "Unit Multiplier (e.g., JPY=100, IDR=1000, default=1)"
        timestamp created_at "Record Creation Time"
        timestamp updated_at "Record Last Update Time"
    }

    fact_daily_exchange_rate {
        bigint id PK "Surrogate Key (Auto Increment)"
        date rate_date "Effective Date (YYYY-MM-DD)"
        char(3) currency_code FK "Currency Code Reference"
        decimal(12_4) buying_sight_bill "Buying Sight Bill Rate (Nullable)"
        decimal(12_4) buying_transfer "Buying Transfer Rate (Nullable)"
        decimal(12_4) selling "Selling Rate (Nullable)"
        timestamp created_at "Record Creation Time"
        timestamp updated_at "Record Last Update Time"
    }
```

---

## 2. Table: `dim_currency`

| Column Name | Data Type | Constraints | Nullable | Default | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `currency_code` | `CHAR(3)` | `PRIMARY KEY` | No | - | รหัสสกุลเงินมาตรฐาน ISO 4217 เช่น USD, JPY, EUR |
| `country_name` | `VARCHAR(100)` | - | No | - | ชื่อประเทศหรือเขตเศรษฐกิจ (ภาษาไทย) เช่น สหรัฐอเมริกา, ญี่ปุ่น |
| `currency_name` | `VARCHAR(100)` | - | No | - | ชื่อหน่วยสกุลเงิน (ภาษาไทย) เช่น ดอลลาร์, เยน, ยูโร |
| `unit_multiplier` | `INT` | - | No | `1` | ตัวคูณต่อหน่วยคำนวณอัตราแลกเปลี่ยน (เช่น JPY = 100, IDR = 1000) |
| `created_at` | `TIMESTAMP` | - | No | `CURRENT_TIMESTAMP` | วันที่และเวลาที่บันทึกข้อมูลเข้าระบบ |
| `updated_at` | `TIMESTAMP` | - | No | `CURRENT_TIMESTAMP ON UPDATE` | วันที่และเวลาที่แก้ไขข้อมูลล่าสุด |

---

## 3. Table: `fact_daily_exchange_rate`

| Column Name | Data Type | Constraints | Nullable | Default | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | `BIGINT` | `PRIMARY KEY`, `AUTO_INCREMENT` | No | - | รหัส Primary Key ลำดับรายการ |
| `rate_date` | `DATE` | `INDEX`, `UNIQUE (rate_date, currency_code)` | No | - | วันที่มีผลบังคับใช้อัตราแลกเปลี่ยน (มาตรฐาน `YYYY-MM-DD`) |
| `currency_code` | `CHAR(3)` | `FOREIGN KEY` $\rightarrow$ `dim_currency.currency_code` | No | - | รหัสสกุลเงิน 3 หลัก |
| `buying_sight_bill`| `DECIMAL(12, 4)` | - | Yes | `NULL` | อัตราซื้อตั๋วเงิน (บาท/หน่วย) |
| `buying_transfer` | `DECIMAL(12, 4)` | - | Yes | `NULL` | อัตราซื้อเงินโอน (บาท/หน่วย) รวมเรทซื้อของสกุลเงินรองและ PKR |
| `selling` | `DECIMAL(12, 4)` | - | Yes | `NULL` | อัตราขาย (บาท/หน่วย) |
| `created_at` | `TIMESTAMP` | - | No | `CURRENT_TIMESTAMP` | วันที่และเวลาที่บันทึกข้อมูลเข้าระบบ |
| `updated_at` | `TIMESTAMP` | - | No | `CURRENT_TIMESTAMP ON UPDATE` | วันที่และเวลาที่แก้ไขข้อมูลล่าสุด |

---

## 4. Business Transformation & Ingestion Rules
1. **Date Normalization:**
   - Input format `MM/DD/YYYY` (File 1) and `DD/MM/YYYY` (File 2) $\rightarrow$ Converted to `YYYY-MM-DD`.
2. **Type Mapping & Clean:**
   - `ซื้อตั๋วเงิน` $\rightarrow$ `buying_sight_bill`
   - `ซื้อเงินโอน`, `ซื้อเงินโอน 1/`, `ซื้อ` $\rightarrow$ `buying_transfer`
   - `ขาย` $\rightarrow$ `selling`
   - `อัตรากลาง` $\rightarrow$ ตัดทิ้ง (สามารถคำนวณแบบ dynamic เป็น `(buying_transfer + selling)/2` ได้)
3. **Idempotency Strategy:**
   - Ingestion uses `INSERT INTO fact_daily_exchange_rate (...) VALUES (...) ON DUPLICATE KEY UPDATE buying_sight_bill=VALUES(buying_sight_bill), buying_transfer=VALUES(buying_transfer), selling=VALUES(selling)`.
