# คู่มือการติดตั้งระบบ Guasha House บน Hostinger

โปรเจกต์นี้ได้รับการเตรียมไฟล์สำหรับ Deploy บน Hostinger ไว้อย่างสมบูรณ์ รองรับทั้ง **Hostinger VPS** (แนะนำที่สุด) และ **Hostinger Web/Cloud Hosting (hPanel)**

---

## วิธีที่ 1: ติดตั้งบน Hostinger VPS (แนะนำที่สุด ⭐⭐⭐⭐⭐)

Hostinger VPS (Ubuntu 22.04 / 24.04) เหมาะกับ FastAPI มากที่สุด รันผ่าน Docker ได้ในคำสั่งเดียว

### ขั้นตอนที่ 1: เชื่อมต่อ SSH เข้า VPS
เปิด Terminal ในเครื่องของคุณแล้วเชื่อมต่อเข้า VPS ของ Hostinger:
```bash
ssh root@<IP_ของ_VPS>
```

### ขั้นตอนที่ 2: Clone โค้ดโปรเจกต์
```bash
git clone https://github.com/Amaraporn48/guasha-house.git
cd guasha-house
```

### ขั้นตอนที่ 3: รันสคริปต์ติดตั้งอัตโนมัติ
```bash
chmod +x hostinger_setup.sh
./hostinger_setup.sh
```
สคริปต์จะทำการ:
1. ติดตั้ง Docker & Docker Compose อัตโนมัติ (ถ้ายังไม่มี)
2. สร้างไฟล์ `.env` พร้อมสุ่ม `JWT_SECRET_KEY` ที่ปลอดภัยให้ทันที
3. Build และเปิดใช้งาน Container บน Port `8000`

### ขั้นตอนที่ 4: ตั้งค่า Database (ในไฟล์ `.env`)
แก้ไขไฟล์ `.env` เพื่อใส่ `DATABASE_URL` ของ PostgreSQL (เช่น Supabase หรือ PostgreSQL บน VPS):
```bash
nano .env
```
ใส่ค่า:
```env
ENVIRONMENT=production
JWT_SECRET_KEY=คีย์ที่สร้างไว้
DATABASE_URL=postgresql://user:password@host:5432/dbname
```
จากนั้นสั่ง Restart:
```bash
docker compose up -d --build
```

### ขั้นตอนที่ 5: ตั้งค่า Nginx และ SSL โดเมน (Optional)
หากต้องการผูกโดเมน (เช่น `billing.guashahouse.com`) พร้อม HTTPS:
```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```
สร้างไฟล์ config `/etc/nginx/sites-available/guashahouse`:
```nginx
server {
    server_name yourdomain.com;

    client_max_body_size 20M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
เปิดใช้งานและขอ SSL ฟรี:
```bash
sudo ln -s /etc/nginx/sites-available/guashahouse /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d yourdomain.com
```

---

## วิธีที่ 2: ติดตั้งบน Hostinger Web Hosting / Cloud Hosting (hPanel)

หากใช้แพ็กเกจ Web Hosting ทั่วไปที่มี hPanel:

1. อัปโหลดไฟล์โปรเจกต์ทั้งหมดขึ้น Hostinger ผ่าน File Manager หรือ Git
2. ไปที่ hPanel $\rightarrow$ เมนู **Advanced** $\rightarrow$ **Python Applications** $\rightarrow$ คลิก **Create Application**
3. กรอกข้อมูลดังนี้:
   - **Python version**: เลือก `3.10` หรือ `3.11`
   - **Application root**: `public_html` (หรือโฟลเดอร์ที่วางโค้ด)
   - **Application URL**: โดเมนของคุณ
   - **Application startup file**: `passenger_wsgi.py`
   - **Application Entry point**: `application`
4. คลิก **Create**
5. เลื่อนลงมาที่ส่วน **Configuration files** หรือรันคำสั่ง pip:
   - ติดตั้ง dependencies: `pip install -r requirements.txt`
6. เพิ่ม **Environment Variables** ใน hPanel:
   - `ENVIRONMENT` = `production`
   - `JWT_SECRET_KEY` = `(ใส่คีย์สุ่มยาวอย่างน้อย 32 ตัวอักษร)`
   - `DATABASE_URL` = `(PostgreSQL Connection String)`
7. กด **Restart** Application ในหน้า hPanel

---

## คำสั่งจัดการที่มีประโยชน์ (Hostinger VPS)
- ดูสถานะ Container: `docker compose ps`
- ดู Log การทำงาน: `docker compose logs -f`
- หยุดระบบ: `docker compose down`
- อัปเดตโค้ดเวอร์ชันใหม่:
  ```bash
  git pull origin main
  docker compose up -d --build
  ```
