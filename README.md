# Cookie Run Bot

บอทเล่น **Cookie Run: OvenBreak** อัตโนมัติบน Android emulator (MuMu, Nox) ผ่าน ADB
มี UI (tkinter) ตรวจจับ emulator, สั่งบอทแยกอิสระรายหน้าจอ, และมี log แสดงผลแบบเรียลไทม์
รองรับทั้ง **Windows และ macOS**

## บอททำอะไร

วนลูปฟาร์ม: จับภาพหน้าจอ → เทียบว่าตอนนี้อยู่หน้าไหนของเกม → กดปุ่มให้อัตโนมัติ
(lobby → Play → เล่น → mystery box → result → OK → เริ่มใหม่) ระหว่างวิ่งจะกด Jump เป็นระยะ

> ไม่มี AI หลบสิ่งกีดขวาง — คุกกี้จะวิ่งจนชนแล้วจบรอบ จากนั้นบอทเริ่มรอบใหม่เอง

## ติดตั้ง

ต้องมี Python 3.9+ และ `adb` อยู่ใน PATH (MuMu/Nox มี adb ติดมาให้ หรือ set env var `ADB=/path/to/adb`)

```bash
python3 -m venv env
./env/bin/pip install -r requirements.txt   # Windows: env\Scripts\pip install -r requirements.txt
```

`tkinter` มากับ Python อยู่แล้ว (Windows/macOS)

## ใช้งาน

```bash
./env/bin/python cookie_bot.py              # Windows: env\Scripts\python cookie_bot.py
```

1. เปิด emulator (MuMu/Nox) ให้เข้าเกม Cookie Run
2. กด **Detect Emulators** — emulator ที่เจอจะขึ้นในตาราง
3. เลือกรายการแล้วกด **Start Selected** / **Stop Selected** / **Remove Selected** เพื่อคุมทีละหน้าจอ
   หรือ **Start All** / **Stop All** เพื่อคุมทุกหน้าจอพร้อมกัน
4. ติ๊ก **Use boosts** ถ้าอยากให้บอทกด boost ที่ต้องใช้ไอเทม (ค่าเริ่มต้นปิดไว้)

## ปรับแต่ง

- **จุดที่กดเพี้ยน** — แก้ค่าพิกัด (เป็นสัดส่วน 0–1 ของหน้าจอ) ใน `STATES` / `JUMP` ใน `cookie_bot.py`
- **Detect ไม่เจอ** — เพิ่มพอร์ต ADB ของ emulator ใน `EMULATOR_PORTS`
- **เพิ่มหน้าเกมใหม่** — ใส่รูปใน `images/` แล้วเพิ่ม entry ใน `STATES` จากนั้นรัน self-test

```bash
./env/bin/python cookie_bot.py --self-test   # เช็คว่าเทียบภาพทุก state ถูกต้อง
```

## แก้ปัญหา

- **หน้าต่างว่างเปล่าบน macOS** — เป็นบั๊กของ Tk 8.5 ตัวระบบ ทางแก้ถาวรคือใช้ Python จาก python.org (มากับ Tk 8.6)
- **`adb not found`** — ติดตั้ง adb หรือ set `ADB=/path/to/adb`

ดูรายละเอียดสถาปัตยกรรมได้ที่ `CLAUDE.md`
