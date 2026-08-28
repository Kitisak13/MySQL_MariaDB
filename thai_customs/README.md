# Thai Customs Trade Data Platform (ระบบฐานข้อมูลนำเข้า-ส่งออก กรมศุลกากร)

ระบบฐานข้อมูล MariaDB/MySQL และ Data Pipeline อัตโนมัติสำหรับรวบรวมข้อมูลสถิติการนำเข้า-ส่งออกสินค้าของประเทศไทย จากระบบ Open Data กรมศุลกากรไทย ครอบคลุมข้อมูลทั้ง 8 ชุดข้อมูลย้อนหลังตั้งแต่ปี 2560 (2017) ถึงปัจจุบัน

---

## 1. รายการชุดข้อมูลทั้ง 8 ชุด (8 Datasets Catalog)

| Dataset ID | ประเภท | ชื่อชุดข้อมูล | ตารางปลายทาง (Fact Table) |
| :--- | :---: | :--- | :--- |
| `ctm_06_11` | Import | การนำเข้าสินค้า รายประเทศกำเนิด | `fact_trade_by_country` |
| `ctm_06_12` | Export | การส่งออกสินค้า รายประเทศปลายทาง | `fact_trade_by_country` |
| `ctm_06_17` | Import | การนำเข้าสินค้า ตามประเภทการขนส่ง | `fact_trade_by_transport` |
| `ctm_06_18` | Export | การส่งออกสินค้า ตามประเภทการขนส่ง | `fact_trade_by_transport` |
| `ctm_06_15` | Import | การนำเข้าสินค้า รายด่านศุลกากร | `fact_trade_by_port` |
| `ctm_06_16` | Export | การส่งออกสินค้า รายด่านศุลกากร | `fact_trade_by_port` |
| `ctm_06_13` | Import | การนำเข้าสินค้า รายสำนักงานศุลกากร | `fact_trade_by_office` |
| `ctm_06_14` | Export | การส่งออกสินค้า รายสำนักงานศุลกากร | `fact_trade_by_office` |

---

## 2. โครงสร้างโฟลเดอร์ (Project Structure)

```text
thai_customs/
├── config/
│   └── db_config.py             # การตั้งค่าการเชื่อมต่อฐานข้อมูล
├── database/
│   ├── schema.sql               # DDL Schema สำหรับ MariaDB (utf8mb4)
│   ├── init_db.py               # สคริปต์สร้างฐานข้อมูลและตาราง
│   └── data_dictionary.md       # พจนานุกรมข้อมูลและ Mermaid ER-Diagram
├── etl/
│   ├── normalizers.py           # การแปลงปี พ.ศ. -> ค.ศ., Pad 0 พิกัด HS และรหัสสถิติ
│   ├── fact_transformers.py     # Streaming Chunk Transformers
│   └── loaders.py               # Atomic Partition Overwrite & Audit Logging
├── scripts/
│   ├── download_customs_data.py # ดาวน์โหลดข้อมูลทั้ง 8 ชุดจาก CKAN API
│   ├── ingest_all_customs.py    # Ingest ข้อมูลย้อนหลังทั้งหมดลง MySQL
│   ├── sync_monthly_customs.py  # ตรวจสอบและอัปเดต Restatement ย้อนหลัง 2 ปีอัตโนมัติ
│   └── verify_customs_db.py     # ตรวจสอบความถูกต้องและสถิติภาพรวม
├── raw_data/                    # โฟลเดอร์เก็บข้อมูลดิบ (~10GB, ถูก Ignore ไม่ขึ้น Git)
└── README.md
```

---

## 3. วิธีการใช้งานสคริปต์ (How to Run)

### 3.1 เริ่มต้นสร้างตารางฐานข้อมูล
```powershell
python thai_customs/database/init_db.py
```

### 3.2 ดาวน์โหลดข้อมูลดิบทั้ง 8 ชุดจากกรมศุลกากร
```powershell
python thai_customs/scripts/download_customs_data.py
```

### 3.3 นำเข้าข้อมูลประวัติศาสตร์ทั้งหมด (Historical Backfill)
```powershell
python thai_customs/scripts/ingest_all_customs.py
```

### 3.4 รันระบบ Sync รายเดือนและปรับปรุงข้อมูลงวดแก้ปรับปรุงย้อนหลัง 2 ปี (Monthly Restatement Sync)
```powershell
python thai_customs/scripts/sync_monthly_customs.py
```

### 3.5 ตรวจสอบความถูกต้องและรายงานสถิติ (Verification Report)
```powershell
python thai_customs/scripts/verify_customs_db.py
```
