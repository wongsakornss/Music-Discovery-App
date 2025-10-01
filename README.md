# MusicDiscoveryApp

เว็บแอปพลิเคชันสำหรับ **ค้นหาเพลง ค้นหาศิลปิน และสร้างเพลย์ลิสต์**  
ทำงานบน **Flask + SQLite** พร้อมเชื่อมต่อกับ **Last.fm API** และ **Spotify Web API**

## ✨ Features
- ค้นหาเพลง/ศิลปินตาม Tag หรือชื่อ
- แสดงเพลงยอดนิยมและศิลปินที่ใกล้เคียง
- จัดการ Playlist ส่วนตัว (เพิ่ม/ลบเพลง(ยังลบไม่ได้), แชร์สาธารณะ)
- Export Playlist ไปยัง Spotify
- รองรับการเก็บ token ด้วย OAuth2 (Spotify)

## Project Structure
- `app.py` – Flask entry point, routes
- `lastfm.py` – Last.fm API client
- `models.py` – Data models เช่น `Track`
- `storage.py` – Database layer (SQLite + SQLAlchemy)
- `templates/` – HTML templates
- `static/` – Static files (css, js, favicon)
- `requirements.txt` – Dependencies
- `.env` – environment variables

## How to run
```bash
# ติดตั้ง dependencies
pip install -r requirements.txt

# สร้างไฟล์ .env จาก .env.example แล้วใส่ API keys
cp .env.example .env

# รันเซิร์ฟเวอร์
flask run
