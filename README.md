# MySQL & MariaDB Data Platform Repository

คลังรวมโปรเจกต์ฐานข้อมูล, สคริปต์ DDL/Schema, Data Pipelines, ETL Ingestion และ Data Modeling สำหรับ MySQL / MariaDB (Local XAMPP / Production)

---

## 1. โครงสร้างการจัดเก็บใน Repository (Repository Architecture)

เพื่อความเป็นระเบียบและรองรับการขยายตัวของหลายฐานข้อมูลในอนาคต Repository นี้ถูกออกแบบให้แยกโฟลเดอร์ตามแต่ละฐานข้อมูล/โดเมนอย่างชัดเจน:

```text
MySQL_MariaDB/
├── .gitignore                      # กรองไฟล์ Raw data (CSV, XLSX), Secrets (.env), Cache ออกจาก Git
├── .env.example                    # แม่แบบการตั้งค่าการเชื่อมต่อฐานข้อมูล
├── AGENTS.md                       # ข้อกำหนดทางสถาปัตยกรรมและมาตรฐานวิศวกรรมข้อมูล
├── README.md                       # เอกสารสารบัญภาพรวมของคลังข้อมูล
│
├── db-bot_exchange_rates/          # [Database 1] ฐานข้อมูลอัตราแลกเปลี่ยนเงินตราต่างประเทศ (ธปท.)
│   ├── config/                     # Connection helper & database configuration
│   ├── database/                   # DDL schema.sql, init_db.py, data_dictionary.md
│   ├── etl/                        # Data cleaning, transformation & bulk loaders
│   ├── scripts/                    # Ingestion runners (historical, monthly batch, verification)
│   └── README.md                   # คู่มือเฉพาะสำหรับฐานข้อมูล db-bot_exchange_rates
│
├── db-thai_customs/                # [Database 2] ฐานข้อมูลสถิติการนำเข้า-ส่งออกสินค้า (กรมศุลกากรไทย)
│   ├── config/                     # Connection helper & Max Packet configuration
│   ├── database/                   # DDL schema.sql, init_db.py, data_dictionary.md
│   ├── etl/                        # Fact transformers, normalizers & loaders
│   ├── master_data/                # Master reference data (HS Code & Country/Region)
│   ├── scripts/                    # CKAN Downloader, Ingestion, Monthly Sync, Verification
│   └── README.md                   # คู่มือเฉพาะสำหรับฐานข้อมูล db-thai_customs
│
├── db-dit-prices/                  # [Database 3] ฐานข้อมูลราคาสินค้าอุปโภคบริโภค (กรมการค้าภายใน)
│   ├── config/                     # Connection helper & database configuration
│   ├── database/                   # DDL schema.sql, init_db.py, data_dictionary.md
│   ├── etl/                        # Normalizers, transformers & bulk loaders
│   ├── master_data/                # Product & Unit catalog (730 items)
│   ├── scripts/                    # API Downloader, Historical Ingest, Monthly Sync, Verify
│   └── README.md                   # คู่มือเฉพาะสำหรับฐานข้อมูล db-dit-prices
│
├── demo/                           # โค้ดตัวอย่างการใช้งาน MySQL Connector / Tutorials
│   ├── mysql-connector-create-tables.ipynb
│   ├── mysql-connector-insert-data.ipynb
│   ├── mysql-connector-query-data.ipynb
│   └── ...
│
└── documents/                      # เอกสารอ้างอิงและ Developer Guides
    └── MySQL Connector_Python Developer Guide.pdf
```

---

## 2. รายชื่อฐานข้อมูลใน Repository (Databases Catalog)

| ลำดับ | โฟลเดอร์โปรเจกต์                                      | ชื่อฐานข้อมูล (`DB_NAME`) | รายละเอียด                                                               | รูปแบบสถาปัตยกรรม                                        |
| :---: | :---------------------------------------------------- | :------------------------ | :----------------------------------------------------------------------- | :------------------------------------------------------- |
|   1   | [`db-bot_exchange_rates/`](db-bot_exchange_rates/)   | `bot_exchange_rates`      | ข้อมูลอัตราแลกเปลี่ยนรายวันจากธนาคารแห่งประเทศไทย (BOT) ปี 2002–ปัจจุบัน | Star Schema (`dim_currency`, `fact_daily_exchange_rate`) |
|   2   | [`db-thai_customs/`](db-thai_customs/)               | `thai_customs`            | ข้อมูลสถิติการนำเข้า-ส่งออกสินค้า กรมศุลกากรไทย (8 Datasets) ปี 2017–ปัจจุบัน | Star Schema (4 Fact Tables, 5 Dimension Tables)          |
|   3   | [`db-dit-prices/`](db-dit-prices/)                   | `dit_product_prices`      | ข้อมูลราคาจำหน่ายปลีก-ส่ง สินค้าอุปโภคบริโภค กรมการค้าภายใน (DIT) ปี 2010–ปัจจุบัน | Star Schema (`dim_product`, `fact_daily_product_price`) |
|   4   | _(Future Databases: `db-<project_name>/`)_            | _TBD_                     | _(สามารถเพิ่มโฟลเดอร์สำหรับฐานข้อมูลใหม่ได้ตามโครงสร้างนี้)_             | -                                                        |

---

## 3. มาตรฐานการเพิ่ม Database ใหม่ (Contribution Guidelines)

เมื่อต้องการเพิ่มฐานข้อมูลใหม่เข้าไปใน Repository ให้สร้างโฟลเดอร์ย่อยระดับ Root โดยใช้ชื่อ `db-<database_name>/` เช่น `db-my_project/` โดยมีโครงสร้างภายในดังนี้:

1. `config/`: จัดการ Connection สำหรับ Database นั้นๆ
2. `database/`: บรรจุ `schema.sql`, `init_db.py`, และ `data_dictionary.md`
3. `etl/`: ฟังก์ชัน Extract, Transform (Clean), และ Load
4. `scripts/`: สคริปต์สำหรับรัน Ingestion และ Verify
5. `README.md`: อธิบาย ERD และวิธีใช้งานของ Database นั้นๆ

---

## 4. เริ่มต้นใช้งาน (Quick Start)

1. Clone repository นี้ลงเครื่อง:
   ```bash
   git clone https://github.com/Kitisak13/MySQL_MariaDB.git
   cd MySQL_MariaDB
   ```
2. สร้างไฟล์ `.env` โดยคัดลอกจาก `.env.example`:
   ```bash
   cp .env.example .env
   ```
3. ติดตั้ง Dependencies ที่จำเป็น:
   ```bash
   pip install mysql-connector-python pandas python-dotenv
   ```
4. เลือกไปยังโฟลเดอร์ฐานข้อมูลที่ต้องการใช้งาน เช่น [`db-bot_exchange_rates/`](db-bot_exchange_rates/) หรือ [`db-thai_customs/`](db-thai_customs/) และปฏิบัติตามคู่มือในโฟลเดอร์นั้นๆ

## 5. การรัน Script Update ข้อมูลรายเดือนใหม่ (ตัวอย่าง: db-bot_exchange_rates)

### แบบที่ 1: รันจาก Root Directory (`D:\MySQL\mysql`) [แนะนำ]
```powershell
python db-bot_exchange_rates/scripts/ingest_monthly.py --file "path\to\new_file.csv"
```

### แบบที่ 2: รันจากโฟลเดอร์ของฐานข้อมูล (`D:\MySQL\mysql\db-bot_exchange_rates`)
```powershell
cd db-bot_exchange_rates
python scripts/ingest_monthly.py --file "path\to\new_file.csv"
```
