# MusicDiscoveryApp

เว็บแอปพลิเคชันสำหรับการค้นหาเพลง, สร้างเพลย์ลิสต์ และส่งออกเพลย์ลิสต์ไปยัง **Spotify** หรือ **CSV**  
เชื่อมต่อด้วย **Last.fm API** และ **Spotify Web API**  
พัฒนาด้วย **Flask + SQLite + TailwindCSS**

---

## ✨ ฟีเจอร์หลัก

- 🔎 **ค้นหาเพลง**
  - ค้นหาตาม **ศิลปิน**, **แท็ก (แนวเพลง)**, หรือ **อารมณ์ (Mood)** เช่น “อ่านหนังสือ”, “ออกกำลังกาย”
  - แสดง **ศิลปินที่คล้ายกัน** เพื่อค้นหาเพิ่มเติม

- 🎼 **จัดการเพลย์ลิสต์**
  - สร้าง, แก้ไข, ลบเพลย์ลิสต์
  - เพิ่ม / ลบเพลงในเพลย์ลิสต์
  - ย้ายตำแหน่งเพลง (ขึ้น/ลง)
  - แชร์เพลย์ลิสต์แบบสาธารณะผ่านลิงก์ (`/p/<token>`)

- 😎 **แนะนำเพลงตามอารมณ์ (Mood-based)**
  - กรอกข้อความอารมณ์ → ระบบจะแปลงเป็นแท็ก Last.fm อัตโนมัติ
  - เพิ่มเพลงเข้ารายการได้ทันที
  - ปุ่ม **Build Top 10** เพื่อสร้างเพลย์ลิสต์อัตโนมัติจากแท็กที่เลือก

- 📤 **การส่งออก (Export)**
  - ส่งออกเพลย์ลิสต์ (10 เพลงแรก) เป็นไฟล์ CSV
  - ส่งออกเพลย์ลิสต์ตรงไปยัง Spotify (OAuth2 Integration)

- 👤 **ระบบผู้ใช้**
  - ลงทะเบียน / เข้าสู่ระบบ
  - ผู้ใช้แต่ละคนมีเพลย์ลิสต์ของตัวเอง
  - หน้าโปรไฟล์พร้อมสถิติ เช่น จำนวนเพลงทั้งหมด และจำนวนศิลปินที่ไม่ซ้ำ

---

## 🏗️ เทคโนโลยีที่ใช้

- **Backend:** Python, Flask, SQLAlchemy  
- **Frontend:** Jinja2 Templates, TailwindCSS  
- **Database:** SQLite (สามารถปรับไปใช้ PostgreSQL/MySQL ได้)  
- **API ภายนอก:**  
  - Last.fm API (ข้อมูลเพลง)  
  - Spotify Web API (ส่งออกเพลย์ลิสต์)  
- **Auth:** Flask-Login, Spotify OAuth2  
- **Deployment:** Docker, Gunicorn  

---

## Project Structure
- `app.py` – Flask main app
- `lastfm.py` – Last.fm API client
- `models.py` – Data models เช่น `Track`
- `storage.py` – Database repository (SQLite + SQLAlchemy)
- `templates/` – HTML templates
- `static/` – Static files (css, js, favicon)
- `requirements.txt` – Dependencies
- `.env` – environment variables
- `tests/` – Unit tests (pytest)
- `Dockerfile` – สำหรับ Deployment

## How to run
### 1. โคลนโปรเจกต์
```bash
git clone https://github.com/wongsakornss/music-discovery-app.git
cd music-discovery-app
```
### 2. ตั้งค่า Environment
### วิธีรันด้วย Python (Flask)
```bash
# สร้าง Virtual Environment
python -m venv env

# เปิดใช้งาน Virtual Environment
env\Scripts\activate

# ติดตั้ง dependencies
pip install -r requirements.txt

# สร้างไฟล์ .env จาก .env.example แล้วใส่ API keys
cp .env.example .env

# รันเซิร์ฟเวอร์บนเครื่อง
flask run

#เปิดเบราว์เซอร์ที่
http://127.0.0.1:5000
```
### รันเซิร์ฟเวอร์บน Docker
```bash
# สร้าง Docker Image
docker build -t musicapp .

# รัน Container
docker run -d --name musicapp -p 5000:5000 --env-file .env musicapp

# เปิดเบราว์เซอร์ที่
http://127.0.0.1:5000
