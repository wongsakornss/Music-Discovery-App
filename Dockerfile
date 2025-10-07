# -------------------- Base image --------------------
FROM python:3.11-slim

# ไม่เขียน .pyc และโชว์ log แบบไม่บัฟเฟอร์
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ติดตั้งของจำเป็นตอน build แล้วล้าง cache ลดขนาด image
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && \
    rm -rf /var/lib/apt/lists/*

# -------------------- App setup --------------------
WORKDIR /app

# ติดตั้ง dependencies ล่วงหน้าเพื่อใช้ layer cache
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# คัดลอกซอร์สทั้งหมด
COPY . .

# เปิดพอร์ต
EXPOSE 5000

# ค่า default runtime (ปรับได้ตอนรัน)
ENV PORT=5000 \
    WEB_CONCURRENCY=2 \
    THREADS=4

# -------------------- Entrypoint --------------------
# ใช้ Gunicorn เป็น production server
# หมายเหตุ: app:app = ไฟล์ app.py ที่มีตัวแปร Flask ชื่อ app
CMD ["gunicorn", "-w", "2", "-k", "gthread", "--threads", "4", "-b", "0.0.0.0:5000", "app:app"]
