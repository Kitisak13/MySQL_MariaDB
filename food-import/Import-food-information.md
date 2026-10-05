# ดึงข้อมูล import ของรหัสสินค้าที่ขึ้นต้นด้วย 07,08,20 เท่านั้น

```
ในส่วนของการนำเข้าข้อมูล ไม่ต้องนำเข้า MySQL นะครับ เพราะข้อมูล import ชุดนี้เป็นงานด่วน เจ้านายอยากให้รวบรวมข้อมูลอย่างเร็วที่สุด จึงได้ให้รวบรวมเป็นผลลัพธ์ไฟล์ csv ออกมาเลย แล้วค่อยดึง dimension จากฐาน db-food-export เดิมมา merge ให้เป็นตารางเดียวที่มีคอลัมน์สำคัญๆเหมือนเดิม โดย dim_country ให้ดึงชื่อประเทศเต็ม กับ region มา ส่วน dim_hs11_code ให้ดึงทุกอย่างมา ยกเว้น  first_seen_revision , latest_revision ,is_active_2022 created_at,updated_at
```

นีืคือ api ในการดึงข้อมูล hs-code-11 digits ของแต่ละเวอร์ชั่น
(limit=0 คือดึงข้อมูลทั้งหมด)

เวอร์ชั่น 2007
https://tradereport.moc.go.th/api/harmonizestructure?revision=2007&digits=11&limit=0

เวอร์ชั่น 2012
https://tradereport.moc.go.th/api/harmonizestructure?revision=2012&digits=11&limit=0

เวอร์ชั่น 2017
https://tradereport.moc.go.th/api/harmonizestructure?revision=2017&digits=11&limit=0

เวอร์ชั่น 2022
https://tradereport.moc.go.th/api/harmonizestructure?revision=2022&digits=11&limit=0

# API ในการดึงข้อมูลนำเข้า

ตัวอย่าง api จากกระทรวงพาณิชย์ ที่ใช้ดึงข้อมูลนำเข้า (limit=0 คือดึงข้อมูลทั้งหมด)

https://tradereport.moc.go.th/api/importharmonizecountries?year=2017&month=12&hs_code=10063040001&limit=0
