# Thai Customs Trade Data Platform (ระบบฐานข้อมูลนำเข้า-ส่งออก กรมศุลกากร)

ระบบฐานข้อมูล MariaDB/MySQL และ Data Pipeline อัตโนมัติสำหรับรวบรวมข้อมูลสถิติการนำเข้า-ส่งออกสินค้าของประเทศไทย จากระบบ Open Data กรมศุลกากรไทย ครอบคลุมข้อมูลทั้ง 8 ชุดข้อมูลย้อนหลังตั้งแต่ปี 2560 (2017) ถึงปัจจุบัน

---

## 1. รายการชุดข้อมูลทั้ง 8 ชุด (8 Datasets Catalog)

| Dataset ID  | ประเภท | ชื่อชุดข้อมูล                      | ตารางปลายทาง (Fact Table) |
| :---------- | :----: | :--------------------------------- | :------------------------ |
| `ctm_06_11` | Import | การนำเข้าสินค้า รายประเทศกำเนิด    | `fact_trade_by_country`   |
| `ctm_06_12` | Export | การส่งออกสินค้า รายประเทศปลายทาง   | `fact_trade_by_country`   |
| `ctm_06_17` | Import | การนำเข้าสินค้า ตามประเภทการขนส่ง  | `fact_trade_by_transport` |
| `ctm_06_18` | Export | การส่งออกสินค้า ตามประเภทการขนส่ง  | `fact_trade_by_transport` |
| `ctm_06_15` | Import | การนำเข้าสินค้า รายด่านศุลกากร     | `fact_trade_by_port`      |
| `ctm_06_16` | Export | การส่งออกสินค้า รายด่านศุลกากร     | `fact_trade_by_port`      |
| `ctm_06_13` | Import | การนำเข้าสินค้า รายสำนักงานศุลกากร | `fact_trade_by_office`    |
| `ctm_06_14` | Export | การส่งออกสินค้า รายสำนักงานศุลกากร | `fact_trade_by_office`    |

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
├── master_data/                 # Master Dimension Reference Files
│   ├── Dim_HS Code.csv          # Master ลำดับชั้นสินค้า 4 ระดับ (2, 4, 8, 11 หลัก)
│   └── Dim_COUNTRY_REGION_CIA.xlsx # Master รหัสประเทศและลำดับชั้นภูมิภาค CIA / ISO 3166
├── scripts/
│   ├── check_status.py          # ตรวจสอบจำนวนแถวและสถานะการนำเข้าแบบ Real-Time
│   ├── download_customs_data.py # ดาวน์โหลดข้อมูลทั้ง 8 ชุดจาก CKAN API
│   ├── ingest_all_customs.py    # Ingest ข้อมูลย้อนหลังทั้งหมดลง MySQL (Resumable)
│   ├── load_dim_country.py      # โหลด Master ประเทศและภูมิภาคเข้า dim_country
│   ├── load_dim_hs_code.py      # โหลด Master ลำดับชั้นสินค้าเข้า dim_hs_code
│   ├── sync_monthly_customs.py  # ตรวจสอบและอัปเดต Restatement ย้อนหลัง 2 ปีอัตโนมัติ
│   ├── tune_db.py               # ปรับแต่ง Buffer Pool และ Indexes ประสิทธิภาพสูง
│   └── verify_customs_db.py     # ตรวจสอบความถูกต้องและสถิติภาพรวม
├── raw_data/                    # โฟลเดอร์เก็บข้อมูลดิบชั่วคราว (ถูก Ignore ไม่ขึ้น Git)
└── README.md
```

---

## 3. วิธีการใช้งานสคริปต์ (How to Run)

### 3.1 เริ่มต้นสร้างตารางฐานข้อมูล

```powershell
python db-thai_customs/database/init_db.py
```

### 3.2 ดาวน์โหลดข้อมูลดิบทั้ง 8 ชุดจากกรมศุลกากร

```powershell
python db-thai_customs/scripts/download_customs_data.py
```

### 3.3 นำเข้าข้อมูลประวัติศาสตร์ทั้งหมด (Historical Backfill)

```powershell
python db-thai_customs/scripts/ingest_all_customs.py
```

### 3.4 รันระบบ Sync รายเดือนและปรับปรุงข้อมูลงวดแก้ปรับปรุงย้อนหลัง 2 ปี (Monthly Restatement Sync)

```powershell
python db-thai_customs/scripts/sync_monthly_customs.py
```

### 3.5 ตรวจสอบความถูกต้องและรายงานสถิติ (Verification Report)

```powershell
python db-thai_customs/scripts/verify_customs_db.py
```

## 4. การอัปเดตข้อมูลรายเดือนและแก้ไขย้อนหลัง (Data Sync & Update)

รันคำสั่ง:

```powershell
python db-thai_customs/scripts/sync_monthly_customs.py          # ตรวจสอบและอัปเดต 2 ปีล่าสุด (Default)
python db-thai_customs/scripts/sync_monthly_customs.py --years 1 # ตรวจสอบและอัปเดต 1 ปีล่าสุด
python db-thai_customs/scripts/sync_monthly_customs.py --years 5 # ตรวจสอบและอัปเดต 5 ปีล่าสุด
```

**หมายเหตุ:**
หากอยู่ที่โฟลเดอร์ `db-thai_customs` อยู่แล้วสามารถรัน:

```powershell
python scripts/sync_monthly_customs.py
```

ได้เลยครับ

## 5 กลไกการทำงานของคำสั่งนี้

```python
python scripts/sync_monthly_customs.py
```

เมื่อคุณรันคำสั่ง sync_monthly_customs.py สคริปต์จะเชื่อมต่อไปยัง CKAN API ของกรมศุลกากรทั้ง 8 Datasets และดำเนินการให้โดยอัตโนมัติ:

1. กรณีที่ 1: มีข้อมูลเดือนใหม่ออกมา (เช่น กรกฎาคม 2026)
   ระบบจะพบไฟล์ใหม่ ..._ปี_2569_(เช่น กรกฎาคม).csv บนหน้าเว็บที่ยังไม่เคยโหลด
   ระบบทำการ **ดาวน์โหลด** -> **Clean & Normalize ข้อมูล** -> **Bulk Insert** เข้าสู่ตาราง Fact ทันที

2. กรณีที่ 2: มีการ Adjust/แก้ไขข้อมูลย้อนหลัง (Restatements เช่น ย้อนหลังปี 2024–2026)
   ระบบจะตรวจสอบ Checksum (file_hash) และ last_modified ของไฟล์ย้อนหลัง 2 ปีอัตโนมัติ
   หากพบว่าไฟล์ของเดือน/ปีใดมีตัวเลขเปลี่ยนไปจากเดิม: ระบบจะ **ดาวน์โหลดไฟล์เวอร์ชันล่าสุด** -> **ลบเฉพาะงวดเดือน/ปีนั้นออก** -> **Bulk Insert ข้อมูลชุดใหม่** แทนที่ทันที (Atomic Partition Overwrite)
   ป้องกันปัญหาข้อมูลเบิ้ล หรือ Transaction เก่าที่ถูกยกเลิกไปแล้วค้างอยู่ใน DB ได้แบบ 100%

3. กรณีที่ไม่มีข้อมูลใหม่และไม่มีการแก้ไข:
   ระบบจะตรวจสอบอย่างรวดเร็วและขึ้นแจ้งว่า [UP-TO-DATE] No data change detected โดยไม่โหลดซ้ำ ใช้เวลาเพียงไม่กี่วินาทีครับ
