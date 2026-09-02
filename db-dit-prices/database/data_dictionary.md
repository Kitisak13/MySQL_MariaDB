# Data Dictionary - DIT Product Prices Database (`dit_product_prices`)

## 1. Entity-Relationship Diagram (ERD)

```mermaid
erDiagram
    dim_product ||--o{ fact_daily_product_price : "product_id"
    data_ingestion_log

    dim_product {
        varchar(20) product_id PK "Unique Product ID (e.g. P11001)"
        varchar(255) product_name "Product Name in Thai"
        varchar(100) category_name "Category (e.g. ขายปลีก, ขายส่ง)"
        varchar(100) group_name "Group Name (e.g. เนื้อสัตว์, พืชผัก)"
        varchar(50) unit "Unit of measurement (e.g. บาท/กก.)"
        timestamp created_at
        timestamp updated_at
    }

    fact_daily_product_price {
        date price_date PK "Observation Date (YYYY-MM-DD)"
        varchar(20) product_id PK,FK "Foreign Key to dim_product"
        decimal(10,2) price_min "Minimum survey price"
        decimal(10,2) price_max "Maximum survey price"
        decimal(10,2) price_avg "Average daily price"
        timestamp created_at
        timestamp updated_at
    }

    data_ingestion_log {
        bigint id PK "Auto Increment"
        varchar(100) dataset_name "Dataset Identifier"
        varchar(255) file_or_source "Source File or API endpoint"
        date period_start "Earliest date in batch"
        date period_end "Latest date in batch"
        int total_rows "Rows Ingested"
        char(64) file_hash "SHA-256 Checksum"
        varchar(20) status "SUCCESS / FAILED"
        decimal(10,2) duration_seconds "Execution time"
        timestamp ingested_at
    }
```

---

## 2. Table Specifications

### 2.1 Dimension Tables

#### Table: `dim_product`
| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `product_id` | `VARCHAR(20)` | `PRIMARY KEY` | รหัสสินค้าตามมาตรฐาน DIT เช่น `P11001` |
| `product_name` | `VARCHAR(255)` | `NOT NULL, INDEX` | ชื่อสินค้าภาษาไทย เช่น `สุกรชำแหละ เนื้อสัน สันใน` |
| `category_name`| `VARCHAR(100)` | `INDEX` | หมวดหมู่การจำหน่าย เช่น `ขายปลีก`, `ขายส่ง` |
| `group_name` | `VARCHAR(100)` | `INDEX` | กลุ่มสินค้าหลัก เช่น `เนื้อสัตว์`, `พืชผัก`, `ผลไม้`, `ข้าวสาร` |
| `unit` | `VARCHAR(50)` | - | หน่วยวัดราคา เช่น `บาท/กก.`, `บาท/ฟอง`, `บาท/ตัว` |
| `created_at` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | วันที่สร้างเรคคอร์ด |
| `updated_at` | `TIMESTAMP` | `ON UPDATE CURRENT_TIMESTAMP`| วันที่แก้ไขล่าสุด |

---

### 2.2 Fact Tables

#### Table: `fact_daily_product_price`
| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `price_date` | `DATE` | `PK (Part 1), INDEX` | วันที่สำรวจราคามาตรฐาน (`YYYY-MM-DD`) |
| `product_id` | `VARCHAR(20)` | `PK (Part 2), FK, INDEX` | รหัสสินค้า เชื่อมโยงกับ `dim_product.product_id` |
| `price_min` | `DECIMAL(10,2)` | - | ราคาต่ำสุดประจำวัน (บาท) |
| `price_max` | `DECIMAL(10,2)` | - | ราคาสูงสุดประจำวัน (บาท) |
| `price_avg` | `DECIMAL(10,2)` | - | ราคาเฉลี่ยประจำวัน (บาท) คำนวณจาก `(price_min + price_max) / 2` |
| `created_at` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | วันที่บันทึกข้อมูลเข้าฐานข้อมูล |
| `updated_at` | `TIMESTAMP` | `ON UPDATE CURRENT_TIMESTAMP`| วันที่อัปเดตข้อมูลล่าสุด |

---

### 2.3 Audit & Ingestion Logs

#### Table: `data_ingestion_log`
| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT` | `PK, AUTO_INCREMENT` | รหัสลำดับ Audit Log |
| `dataset_name` | `VARCHAR(100)` | `INDEX` | ชื่อชุดข้อมูล เช่น `historical_backfill`, `monthly_api_sync` |
| `file_or_source`| `VARCHAR(255)` | `INDEX` | ชื่อไฟล์หรือ Endpoint ที่ใช้ดึง |
| `period_start` | `DATE` | - | วันที่เริ่มต้นของข้อมูลในชุดที่โหลด |
| `period_end` | `DATE` | - | วันที่สิ้นสุดของข้อมูลในชุดที่โหลด |
| `total_rows` | `INT` | - | จำนวนแถวที่นำเข้าสำเร็จ |
| `file_hash` | `CHAR(64)` | - | SHA-256 Checksum ของไฟล์ต้นฉบับ |
| `status` | `VARCHAR(20)` | - | สถานะการทำงาน (`SUCCESS`, `FAILED`) |
| `duration_seconds`| `DECIMAL(10,2)`| - | ระยะเวลาประมวลผล (วินาที) |
| `ingested_at` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | เวลาที่โหลดข้อมูล |
