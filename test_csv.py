import pandas as pd
import chardet
import os

csv_path = r"C:\Users\Test\docling\tests\data\csv\thaiv1.csv"
md_path = os.path.splitext(csv_path)[0] + ".md"

# ตรวจ encoding ของไฟล์
with open(csv_path, "rb") as f:
    rawdata = f.read(10000)
detected = chardet.detect(rawdata)
encoding_used = detected["encoding"] or "utf-8"
print(f"🔍 ตรวจพบ encoding: {encoding_used}")

# อ่าน CSV โดยบังคับทุกคอลัมน์เป็น string เพื่อไม่ให้เสียข้อมูล
df = pd.read_csv(csv_path, encoding=encoding_used, dtype=str)

# แปลง DataFrame → Markdown
md_table = df.to_markdown(index=False)

# เขียนไฟล์ Markdown
with open(md_path, "w", encoding="utf-8") as f:
    f.write(md_table)

print(f"✅ สร้างไฟล์ Markdown รองรับภาษาไทยแล้ว: {md_path}")
