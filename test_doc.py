import win32com.client as win32
import os

doc_path = r"C:\Users\Test\docling\tests\data\docx\โครงสร้างองค์กร.docx"
md_path = os.path.splitext(doc_path)[0] + ".md"

if not os.path.exists(doc_path):
    raise FileNotFoundError(f"❌ ไม่พบไฟล์: {doc_path}")

word = win32.gencache.EnsureDispatch('Word.Application')
word.Visible = False
word.DisplayAlerts = 0  # ปิดแจ้งเตือน

try:
    doc = word.Documents.Open(doc_path)
    text = doc.Content.Text
    doc.Close()
finally:
    word.Quit()

# เขียนเป็น UTF-8 เพื่อรองรับภาษาไทย
with open(md_path, "w", encoding="utf-8") as f:
    f.write(text)

print(f"✅ แปลงไฟล์ .doc เป็น Markdown แล้ว: {md_path}")
