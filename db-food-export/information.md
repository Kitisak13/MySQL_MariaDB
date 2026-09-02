# สร้าง dim-hs11-code table

ระบบพิกัดกรมศุลกากรจะมีอัพเดทและแก้ไขทุกๆ 5 ปี แต่ละการปรับก็จะมีรหัสใหม่เพิ่มมาและบางครั้งก็ลบรหัสของเวอร์ชั่นเก่าออกไป แต่ผมต้องการรหัสจากทุกเวอร์ชั่นครับ แล้วค่อยมาทำให้เป็น unique เพื่อไม่ให้รหัสจะทุกเวอร์ชั่นซ้ำกัน เราก็จะได้รหัส 11 หลักทั้งหมดจากทุกเวอร์ชั่น

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

# API ในการดึงข้อมูลส่งออก

ตัวอย่าง api จากกระทรวงพาณิชย์ ที่ใช้ดึงข้อมูลส่งออก (limit=0 คือดึงข้อมูลทั้งหมด)

https://tradereport.moc.go.th/api/exportharmonizecountries?year=2017&month=12&hs_code=10063040001&limit=0
