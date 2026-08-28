import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin

# URL ของหน้าเว็บชุดข้อมูลหลัก
base_url = "https://catalog.customs.go.th/dataset/ctm_06_12"

# สร้างโฟลเดอร์สำหรับเก็บไฟล์
download_dir = "การส่งออกรายประเทศปลายทาง_ctm_06_12"
os.makedirs(download_dir, exist_ok=True)

response = requests.get(base_url)
response.raise_for_status()
soup = BeautifulSoup(response.text, 'html.parser')

links = soup.find_all('a')
print("เริ่มการดาวน์โหลดไฟล์ CSV...\n" + "-"*30)

for link in links:
    text = link.get_text().strip()
    href = link.get('href')
    
    # 1. กรองเฉพาะลิงก์ที่ระบุว่าเป็นไฟล์ CSV
    if href and 'CSV' in text:
        # ลิงก์นี้คือ "หน้ารายละเอียด" ไม่ใช่ไฟล์โดยตรง
        resource_page_url = urljoin(base_url, href)
        
        # ตั้งชื่อไฟล์
        safe_filename = text.replace(" ", "_").replace("/", "-").replace("(", "").replace(")", "")
        if not safe_filename.lower().endswith('.csv'):
            safe_filename += ".csv"
            
        filepath = os.path.join(download_dir, safe_filename)
        print(f"กำลังตรวจสอบ: {safe_filename}")
        
        try:
            # 2. เข้าไปที่หน้ารายละเอียดเพื่อหาลิงก์ดาวน์โหลดไฟล์จริง
            res_page = requests.get(resource_page_url)
            res_page.raise_for_status()
            res_soup = BeautifulSoup(res_page.text, 'html.parser')
            
            # ค้นหาปุ่มดาวน์โหลด (อ้างอิงจาก class ของระบบ CKAN ของกรมศุลกากร)
            download_btn = res_soup.find('a', class_='resource-url-analytics')
            
            if download_btn and download_btn.get('href'):
                real_download_url = download_btn.get('href')
                
                # ดาวน์โหลดไฟล์ CSV จากลิงก์จริง
                csv_response = requests.get(real_download_url)
                csv_response.raise_for_status()
                
                with open(filepath, 'wb') as f:
                    f.write(csv_response.content)
                print("--> บันทึกไฟล์ CSV สำเร็จ\n")
            else:
                print("--> [ข้าม] หาปุ่มดาวน์โหลดไม่พบในหน้านี้\n")
                
        except Exception as e:
            print(f"--> [ข้อผิดพลาด]: {e}\n")

print("-" * 30 + "\nดาวน์โหลดเสร็จสิ้น!")