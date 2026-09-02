# db-dit-prices: ฐานข้อมูลราคาสินค้าอุปโภคบริโภค กรมการค้าภายใน (DIT)

ฐานข้อมูลจัดเก็บราคาจำหน่ายปลีก-ส่ง และราคากลางสินค้าอุปโภคบริโภครายวันของประเทศไทย จากระบบ Open Data API ของ **กรมการค้าภายใน (Department of Internal Trade - DIT) กระทรวงพาณิชย์**

---

## 1. ข้อมูลภาพรวม (Overview & Architecture)

- **ชื่อฐานข้อมูล (`DB_NAME`):** `dit_product_prices`
- **ระบบการจัดเก็บ:** Star Schema Architecture
- **ชุดข้อมูลหลัก:**
  1. **`dim_product` (Dimension):** บัญชีสินค้า 730 รายการ จำแนกตาม `product_id`, ชื่อสินค้า, หมวดหมู่ (`category_name`), กลุ่มสินค้า (`group_name`) และหน่วยนับ (`unit`)
  2. **`fact_daily_product_price` (Fact):** ราคาต่ำสุด (`price_min`), ราคาสูงสุด (`price_max`), และราคาเฉลี่ย (`price_avg`) รายวันตั้งแต่ปี 2010 ถึงปัจจุบัน (~2.17+ ล้านแถว)
  3. **`data_ingestion_log` (Audit):** บันทึกประวัติและ SHA-256 Checksum ของทุกการประมวลผล

```mermaid
erDiagram
    dim_product ||--o{ fact_daily_product_price : "product_id"
    data_ingestion_log

    dim_product {
        varchar(20) product_id PK "รหัสสินค้า เช่น P11001"
        varchar(255) product_name "ชื่อสินค้าภาษาไทย"
        varchar(100) category_name "หมวดหมู่หลัก เช่น ขายปลีก, ขายส่ง"
        varchar(100) group_name "กลุ่มสินค้า เช่น เนื้อสัตว์, พืชผัก"
        varchar(50) unit "หน่วย เช่น บาท/กก., บาท/ฟอง"
    }

    fact_daily_product_price {
        date price_date PK "วันที่สำรวจราคา (YYYY-MM-DD)"
        varchar(20) product_id PK,FK "รหัสสินค้า"
        decimal(10,2) price_min "ราคาต่ำสุด (บาท)"
        decimal(10,2) price_max "ราคาสูงสุด (บาท)"
        decimal(10,2) price_avg "ราคาเฉลี่ย ((min+max)/2)"
    }
```

---

## 2. โครงสร้างโฟลเดอร์ (Project Structure)

```text
db-dit-prices/
├── config/
│   └── db_config.py             # จัดการ Connection, Pool และ Packet Buffer
├── database/
│   ├── schema.sql               # DDL Schema ภาษาไทย (utf8mb4_unicode_ci)
│   ├── init_db.py               # สคริปต์สร้าง Database และ Tables
│   └── data_dictionary.md       # พจนานุกรมข้อมูลและ ER-Diagram
├── etl/
│   ├── normalizers.py           # ฟังก์ชัน Clean ข้อความ, แปลง Date และตัวเลข
│   ├── transformers.py          # Streaming Chunk Transformers
│   └── loaders.py               # Bulk Upsert (ON DUPLICATE KEY UPDATE) & Logger
├── master_data/                 # ข้อมูล Master Reference
│   └── tbl_product&unit.csv     # บัญชีรายการสินค้าและหน่วยนับ 730 รายการ
├── scripts/
│   ├── check_status.py          # เช็คสถานะจำนวนแถวใน Database แบบ Real-time
│   ├── fetch_dit_api.py         # Multi-threaded DIT API Downloader พร้อม Retry Backoff
│   ├── ingest_historical.py     # Ingest ข้อมูลย้อนหลัง 2.17M แถวแบบ Streaming Chunks
│   ├── sync_monthly_api.py      # Automated Monthly Pipeline (Airflow-ready)
│   └── verify_database.py       # ตรวจสอบ Data Integrity & Sanity Check
├── raw_data/                    # โฟลเดอร์เก็บไฟล์ CSV ชั่วคราว / Snapshots
└── README.md
```

---

## 3. วิธีการใช้งานสคริปต์ (How to Run)

### 3.1 สร้าง Database และโครงสร้างตาราง

```powershell
python db-dit-prices/database/init_db.py
```

### 3.2 โหลดข้อมูลประวัติศาสตร์ทั้งหมด (~2.17 ล้านแถว)

```powershell
python db-dit-prices/scripts/ingest_historical.py
```

### 3.3 รันระบบ Sync ข้อมูลรายเดือนผ่าน API อัตโนมัติ (Airflow-Ready Pipeline)

สคริปต์ `sync_monthly_api.py` จะยิงเรียก DIT API สำหรับสินค้าทั้ง 730 ตัวพร้อมกันแบบขนาน และนำเข้าสู่ MariaDB พร้อมคำนวณราคาเฉลี่ยทันที:

```powershell
# 1. รันดึงข้อมูลงวดเดือนปัจจุบัน (Default)
python db-dit-prices/scripts/sync_monthly_api.py

# 2. ระบุงวดเดือนที่ต้องการเจาะจง (เช่น เดือนสิงหาคม 2026)
python db-dit-prices/scripts/sync_monthly_api.py --month 2026-08

# 3. ระบุช่วงวันที่แบบ Custom Range
python db-dit-prices/scripts/sync_monthly_api.py --from-date 2026-08-01 --to-date 2026-08-31

# 4. ดึงซ้ำเฉพาะรายการที่เคยล้มเหลว (Targeted Retry Failed Items)
python db-dit-prices/scripts/sync_monthly_api.py --month 2026-08 --retry-failed db-dit-prices/raw_data/failed_ids_2026_08_01_2026_08_31.csv

# 5. ดึงเฉพาะรหัสสินค้าที่ระบุเจาะจง
python db-dit-prices/scripts/sync_monthly_api.py --month 2026-08 --products P11001,P11002,P11009

# 6. หาก Server DIT ปฏิเสธการยิงพร้อมกันหลาย Request (Gentle Mode: 1 Worker)
python db-dit-prices/scripts/sync_monthly_api.py --month 2026-08 --workers 1 --retry-failed db-dit-prices/raw_data/failed_ids_2026_08_01_2026_08_31.csv
```

### 3.4 ตรวจสอบสถานะและรายงานความถูกต้อง

```powershell
# ดูสรุปจำนวนข้อมูลปัจจุบัน
python db-dit-prices/scripts/check_status.py

# ตรวจสอบความถูกต้องและ Integrity Report
python db-dit-prices/scripts/verify_database.py
```

---

## 4. ตัวอย่างการนำไปเชื่อมต่อกับ Apache Airflow (Airflow DAG Integration)

คุณสามารถนำสคริปต์ `sync_monthly_api.py` ไปตั้งเวลาใน Airflow DAG ได้อย่างง่ายดาย:

```python
from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime

with DAG(
    dag_id="dit_price_monthly_sync",
    start_date=datetime(2026, 1, 1),
    schedule_interval="0 18 L * *", # รันทุกวันสิ้นเดือน เวลา 18:00 น.
    catchup=False
) as dag:

    sync_task = BashOperator(
        task_id="sync_dit_prices",
        bash_command="python D:/MySQL/mysql/db-dit-prices/scripts/sync_monthly_api.py"
    )
```

---

## 5. จุดเด่นและระบบความทนทาน (Resilience & Reliability)

### 1. สืบทอดข้อดีเดิม: มีระบบ Crash-Safe Auto-Resume & Checkpointing 100%
- ขณะที่ระบบกำลังยิง API จะมีการบันทึกรหัสสินค้าที่ดึงสำเร็จแล้วลงไฟล์ `checked_ids_*.txt` และ `checkpoint_*.csv` แบบ Real-time ทันที
- หากเน็ตตัด ไฟดับ หรือกดยกเลิกกลางคัน เมื่อกลับมารันคำสั่งเดิมซ้ำ ระบบจะขึ้นแจ้งเตือน:
  `Auto-Resume: Found 450 completed products in tracking log. Targeting 278 remaining products (Skipping 450 already checked)...`
- ทำให้ระบบ **ดึงต่อเฉพาะสินค้าที่ยังเหลืออยู่ทันที** ไม่ต้องเสียเวลายิงซ้ำรายการที่เสร็จไปแล้ว

### 2. Multi-Pass Auto-Retry (วนซ้ำรายการที่ล้มเหลว 3 รอบ)
- หากรายการใดเจอปัญหา DIT Server สะดุด (Timeout/Empty Response) ระบบจะมีกลไก Exponential Backoff หน่วงเวลาแล้ววนกลับมาดึงซ้ำใน Pass ที่ 2 และ 3 ให้จนครบ
- หากรายการใดยังล้มเหลวจริงๆ จะถูก Export ออกมาเป็น `failed_ids_*.csv` และบันทึกสถานะ `PARTIAL` ลงในตาราง `data_ingestion_log` ให้ทราบ

| ฟังก์ชันการทำงาน | ระบบเดิมที่คุณเคยทำ | ระบบใหม่ที่เราปรับปรุงให้ |
| :--- | :--- | :--- |
| **ความเร็วในการดึงข้อมูล** | รันทีละรายการ (Single Thread) ช้ามาก | **3 Parallel Threads** (ThreadPoolExecutor) เร็วขึ้น 3-5 เท่า โดยไม่โดน Server บล็อก |
| **กระบวนการรวมข้อมูล** | ต้องรันสคริปต์แยก → ได้ CSV รายเดือน → เปิด `combine.py` อ่าน CSV 2 ล้านแถวมา `concat` → เสี่ยง RAM หมดและช้ามาก | **End-to-End Pipeline ในคำสั่งเดียว** สตรีมข้อมูลตรงเข้า MariaDB ทันที ไม่ต้องรวมไฟล์ CSV อีกต่อไป |
| **การป้องกันข้อมูลซ้ำซ้อน** | เสี่ยงข้อมูลเบิ้ลหากรันเดือนเดิมซ้ำ | **Idempotent 100%** ด้วย Primary Key (`price_date`, `product_id`) และ `ON DUPLICATE KEY UPDATE` ทำให้รันซ้ำกี่ครั้งข้อมูลก็ยังถูกต้อง |
| **การตรวจสอบย้อนหลัง** | ไม่มีประวัติบันทึก | มีตาราง **`data_ingestion_log`** บันทึกเวลา จำนวนแถว และสถานะการทำงานทุกรอบ |
| **การใช้งานร่วมกับ Airflow** | ต้องเขียนสคริปต์เชื่อมโยงหลายไฟล์ | **พร้อมเสียบเข้า Airflow DAG ได้ทันที** ด้วยคำสั่ง CLI ที่รองรับ Parameter |
